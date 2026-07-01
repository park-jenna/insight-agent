"""
The agent loop with session memory, in two forms.

run_agent runs the full tool-calling cycle and returns one JSON result.
run_agent_stream runs the same cycle as an async generator, yielding
events so the client can show tokens and tool steps as they happen.

The cycle:
  1. Send the question and the tool schemas to the model.
  2. If the model requests tools, run them and feed results back.
  3. Repeat until the model answers in plain text, or a step cap is hit
     so a confused model cannot loop forever.

Each tool call records its result and how long it took. Document sources
are collected into a compact list. Session memory replays recent turns.

The loop is built directly rather than with a framework, which keeps the
control flow visible and debuggable.
"""

import json
import os
import time
import uuid as uuidlib

from openai import AsyncOpenAI
from dotenv import load_dotenv

from app.agent_tools import TOOL_SCHEMAS, execute_tool, available_datasets

load_dotenv()

CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")
DOMAIN_LABEL = os.getenv("SYSTEM_PROMPT_LABEL", "document and data assistant")
MAX_STEPS = 6
HISTORY_TURNS = 6

_client: AsyncOpenAI | None = None


class SessionNotFound(Exception):
    """A session_id was given but doesn't exist or belongs to another user."""


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or api_key == "sk-replace-me":
            raise RuntimeError("OPENAI_API_KEY is not set in .env")
        _client = AsyncOpenAI(api_key=api_key)
    return _client


# ---------- session helpers ----------

async def _resolve_session(conn, session_id, user_id):
    if session_id:
        try:
            uuidlib.UUID(str(session_id))
        except ValueError:
            session_id = None

    if session_id:
        row = await conn.fetchrow(
            "SELECT id FROM sessions WHERE id = $1::uuid AND user_id = $2",
            session_id,
            user_id,
        )
        if row:
            return row["id"]
        # a syntactically valid id that isn't ours, don't silently adopt it
        raise SessionNotFound(session_id)

    row = await conn.fetchrow(
        "INSERT INTO sessions (user_id) VALUES ($1) RETURNING id", user_id
    )
    return row["id"]


async def _load_history(conn, session_id, limit=HISTORY_TURNS):
    rows = await conn.fetch(
        """
        SELECT query, answer FROM analyses
        WHERE session_id = $1
        ORDER BY created_at DESC
        LIMIT $2
        """,
        session_id,
        limit,
    )
    return list(reversed(rows))


async def _save_turn(conn, session_id, query, answer, tool_trace, latency_ms):
    await conn.execute(
        """
        INSERT INTO analyses (session_id, query, answer, tool_calls, latency_ms)
        VALUES ($1, $2, $3, $4::jsonb, $5)
        """,
        session_id,
        query,
        answer,
        json.dumps(tool_trace, default=str),
        latency_ms,
    )


# ---------- result shaping ----------

def _trim_for_client(tool: str, result: dict):
    if tool == "search_documents" and isinstance(result, dict) and "results" in result:
        return {
            "results": [
                {"source": r.get("source"), "chunk_index": r.get("chunk_index")}
                for r in result["results"]
            ]
        }
    return result


def _collect_sources(tool_trace: list) -> list:
    counts: dict[str, int] = {}
    for step in tool_trace:
        if step["tool"] != "search_documents":
            continue
        for r in (step.get("result") or {}).get("results", []):
            fn = r.get("source")
            if fn:
                counts[fn] = counts.get(fn, 0) + 1
    sources = []
    for fn, n in counts.items():
        ext = fn.rsplit(".", 1)[-1].lower() if "." in fn else "file"
        sources.append({"filename": fn, "type": ext, "passages": n})
    return sources


# ---------- prompt ----------

def _build_system_prompt(datasets: list[dict]) -> str:
    if datasets:
        ds_lines = "\n".join(
            f"- {d['name']} ({d['rows']} rows): columns {', '.join(d['columns'])}"
            for d in datasets
        )
        ds_block = f"Available datasets you can analyze:\n{ds_lines}"
    else:
        ds_block = "No structured datasets are currently uploaded."

    return (
        f"You are a {DOMAIN_LABEL}. You answer questions using two sources:\n"
        f"1. Uploaded documents, via the search_documents tool.\n"
        f"2. Uploaded datasets, via the data analysis tools.\n\n"
        f"{ds_block}\n\n"
        f"Rules:\n"
        f"- Use search_documents for policy, eligibility, rules, or procedure questions.\n"
        f"- Use the data tools for counts, averages, trends, ratios, outliers, or period comparisons.\n"
        f"- A question may need both. Call the tools you need, then answer.\n"
        f"- Ground your answer only in tool results. When you use a document, name the source file.\n"
        f"- Before answering, check that the retrieved content actually addresses the "
        f"question. Retrieval always returns the closest chunks even when none are "
        f"relevant, so matching keywords are not the same as a real answer.\n"
        f"- If the tools do not contain information that directly answers the question, "
        f"say plainly that you could not find it in the available documents or data. "
        f"Do not infer, generalize, or fill gaps from outside knowledge. A clear "
        f"\"I could not find this\" is correct and expected; a fabricated answer is a failure."
    )


async def _prepare(conn, query, session_id, user_id):
    session = await _resolve_session(conn, session_id, user_id)
    datasets = await available_datasets(conn, user_id)
    history = await _load_history(conn, session)

    messages = [{"role": "system", "content": _build_system_prompt(datasets)}]
    for turn in history:
        messages.append({"role": "user", "content": turn["query"]})
        if turn["answer"]:
            messages.append({"role": "assistant", "content": turn["answer"]})
    messages.append({"role": "user", "content": query})
    return session, messages


# ---------- non-streaming loop ----------

async def run_agent(conn, query: str, user_id: str, session_id=None) -> dict:
    client = _get_client()
    session, messages = await _prepare(conn, query, session_id, user_id)

    tool_trace = []
    start = time.time()
    answer = None
    used_steps = MAX_STEPS

    for step in range(MAX_STEPS):
        resp = await client.chat.completions.create(
            model=CHAT_MODEL, messages=messages, tools=TOOL_SCHEMAS, tool_choice="auto"
        )
        msg = resp.choices[0].message
        if not msg.tool_calls:
            answer = msg.content
            used_steps = step + 1
            break

        messages.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ],
        })
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            t0 = time.perf_counter()
            result = await execute_tool(conn, tc.function.name, args, user_id)
            ms = int((time.perf_counter() - t0) * 1000)
            tool_trace.append({
                "tool": tc.function.name, "args": args,
                "result": _trim_for_client(tc.function.name, result), "ms": ms,
            })
            messages.append({
                "role": "tool", "tool_call_id": tc.id,
                "content": json.dumps(result, default=str),
            })

    if answer is None:
        answer = "I couldn't finish within the step limit. Try a simpler question."

    latency_ms = int((time.time() - start) * 1000)
    await _save_turn(conn, session, query, answer, tool_trace, latency_ms)
    return {
        "answer": answer, "session_id": str(session), "steps": used_steps,
        "tool_trace": tool_trace, "sources": _collect_sources(tool_trace),
        "latency_ms": latency_ms,
    }


# ---------- streaming loop ----------

async def run_agent_stream(conn, query: str, user_id: str, session_id=None):
    """Async generator yielding (event, data) tuples.

    Events: start, token, reset, tool, done, error. Token events carry
    answer text as it generates. Tool events fire as each tool finishes.
    Done carries the final structured run data.
    """
    client = _get_client()
    session, messages = await _prepare(conn, query, session_id, user_id)

    tool_trace = []
    start = time.time()
    answer = None
    used_steps = MAX_STEPS

    yield ("start", {"session_id": str(session)})

    for step in range(MAX_STEPS):
        stream = await client.chat.completions.create(
            model=CHAT_MODEL, messages=messages, tools=TOOL_SCHEMAS,
            tool_choice="auto", stream=True,
        )

        turn_content = ""
        calls: dict[int, dict] = {}

        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                turn_content += delta.content
                yield ("token", {"text": delta.content})
            if delta.tool_calls:
                for tcd in delta.tool_calls:
                    slot = calls.setdefault(tcd.index, {"id": None, "name": "", "args": ""})
                    if tcd.id:
                        slot["id"] = tcd.id
                    if tcd.function:
                        if tcd.function.name:
                            slot["name"] += tcd.function.name
                        if tcd.function.arguments:
                            slot["args"] += tcd.function.arguments

        if calls:
            # any text in a tool turn is a preamble, not the final answer
            if turn_content:
                yield ("reset", {})
            ordered = [calls[i] for i in sorted(calls)]
            messages.append({
                "role": "assistant",
                "content": turn_content or None,
                "tool_calls": [
                    {"id": c["id"], "type": "function",
                     "function": {"name": c["name"], "arguments": c["args"]}}
                    for c in ordered
                ],
            })
            for c in ordered:
                try:
                    args = json.loads(c["args"])
                except json.JSONDecodeError:
                    args = {}
                t0 = time.perf_counter()
                result = await execute_tool(conn, c["name"], args, user_id)
                ms = int((time.perf_counter() - t0) * 1000)
                trimmed = _trim_for_client(c["name"], result)
                tool_trace.append({"tool": c["name"], "args": args, "result": trimmed, "ms": ms})
                yield ("tool", {
                    "index": len(tool_trace), "tool": c["name"],
                    "args": args, "result": trimmed, "ms": ms,
                })
                messages.append({
                    "role": "tool", "tool_call_id": c["id"],
                    "content": json.dumps(result, default=str),
                })
        else:
            answer = turn_content
            used_steps = step + 1
            break

    if answer is None:
        answer = "I couldn't finish within the step limit. Try a simpler question."
        yield ("token", {"text": answer})

    latency_ms = int((time.time() - start) * 1000)
    await _save_turn(conn, session, query, answer, tool_trace, latency_ms)
    yield ("done", {
        "answer": answer, "session_id": str(session), "steps": used_steps,
        "tool_trace": tool_trace, "sources": _collect_sources(tool_trace),
        "latency_ms": latency_ms,
    })
