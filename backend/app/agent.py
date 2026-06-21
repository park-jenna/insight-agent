"""
The agent loop with session memory.

The loop is a standard tool-calling cycle:

  1. Send the question and the tool schemas to the model.
  2. If the model requests tools, run them and feed results back.
  3. Repeat until the model answers in plain text, or a step cap is hit
     so a confused model cannot loop forever.

Each tool call records its result and how long it took, so the client
can show a full run trace. Document sources are collected into a compact
sources list for the answer. Session memory replays recent turns so the
model can resolve follow-up references.

The loop is built directly rather than with a framework, which keeps
the control flow visible and debuggable.
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
DEV_USER_EMAIL = "dev@insightagent.local"
MAX_STEPS = 6
HISTORY_TURNS = 6

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or api_key == "sk-replace-me":
            raise RuntimeError("OPENAI_API_KEY is not set in .env")
        _client = AsyncOpenAI(api_key=api_key)
    return _client


# ---------- session helpers ----------

async def _get_dev_user(conn):
    row = await conn.fetchrow("SELECT id FROM users WHERE email = $1", DEV_USER_EMAIL)
    if row:
        return row["id"]
    row = await conn.fetchrow(
        "INSERT INTO users (email) VALUES ($1) RETURNING id", DEV_USER_EMAIL
    )
    return row["id"]


async def _resolve_session(conn, session_id, user_id):
    if session_id:
        try:
            uuidlib.UUID(str(session_id))
        except ValueError:
            session_id = None
    if session_id:
        row = await conn.fetchrow(
            "SELECT id FROM sessions WHERE id = $1::uuid", session_id
        )
        if row:
            return row["id"]
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
    """Keep the client payload small.

    Document search returns full passage text, which the model needs but
    the UI does not. Strip the text and keep source and index. Data tool
    results are small and pass through unchanged.
    """
    if tool == "search_documents" and isinstance(result, dict) and "results" in result:
        return {
            "results": [
                {"source": r.get("source"), "chunk_index": r.get("chunk_index")}
                for r in result["results"]
            ]
        }
    return result


def _collect_sources(tool_trace: list) -> list:
    """Build a compact source list from document search steps."""
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
        f"- Use search_documents for policy, eligibility, rules, or procedure "
        f"questions.\n"
        f"- Use the data tools for counts, averages, trends, ratios, outliers, "
        f"or period comparisons.\n"
        f"- A question may need both. Call the tools you need, then answer.\n"
        f"- Ground your answer in tool results. When you use a document, name "
        f"the source file.\n"
        f"- If the tools do not contain the answer, say so plainly instead of "
        f"guessing."
    )


# ---------- main loop ----------

async def run_agent(conn, query: str, session_id=None) -> dict:
    client = _get_client()
    user_id = await _get_dev_user(conn)
    session = await _resolve_session(conn, session_id, user_id)

    datasets = await available_datasets(conn)
    history = await _load_history(conn, session)

    messages = [{"role": "system", "content": _build_system_prompt(datasets)}]
    for turn in history:
        messages.append({"role": "user", "content": turn["query"]})
        if turn["answer"]:
            messages.append({"role": "assistant", "content": turn["answer"]})
    messages.append({"role": "user", "content": query})

    tool_trace = []
    start = time.time()
    answer = None
    used_steps = MAX_STEPS

    for step in range(MAX_STEPS):
        resp = await client.chat.completions.create(
            model=CHAT_MODEL,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
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
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ],
        })

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}

            t0 = time.perf_counter()
            result = await execute_tool(conn, tc.function.name, args)
            ms = int((time.perf_counter() - t0) * 1000)

            tool_trace.append({
                "tool": tc.function.name,
                "args": args,
                "result": _trim_for_client(tc.function.name, result),
                "ms": ms,
            })

            # the model still gets the full, untrimmed result
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, default=str),
            })

    if answer is None:
        answer = "I couldn't finish within the step limit. Try a simpler question."

    latency_ms = int((time.time() - start) * 1000)
    await _save_turn(conn, session, query, answer, tool_trace, latency_ms)

    return {
        "answer": answer,
        "session_id": str(session),
        "steps": used_steps,
        "tool_trace": tool_trace,
        "sources": _collect_sources(tool_trace),
        "latency_ms": latency_ms,
    }
