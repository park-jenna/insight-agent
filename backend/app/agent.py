"""
The agent loop with session memory.

The loop is a standard tool-calling cycle:

  1. Send the question and the tool schemas to the model.
  2. If the model requests tools, run them and feed results back.
  3. Repeat until the model answers in plain text, or a step cap is hit
     so a confused model cannot loop forever.

Session memory: each query and answer is stored per session. On a
follow-up, recent turns are replayed as conversation history so the
model can resolve references like "what about the inactive ones".
History is capped to the last few turns to stay within the context
window.

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
HISTORY_TURNS = 6  # how many prior turns to replay as context

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
    """Return an existing session id, or create a new one."""
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
    return list(reversed(rows))  # oldest first


async def _save_turn(conn, session_id, query, answer, tool_trace, latency_ms):
    await conn.execute(
        """
        INSERT INTO analyses (session_id, query, answer, tool_calls, latency_ms)
        VALUES ($1, $2, $3, $4::jsonb, $5)
        """,
        session_id,
        query,
        answer,
        json.dumps(tool_trace),
        latency_ms,
    )


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
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ],
        })

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            result = await execute_tool(conn, tc.function.name, args)
            tool_trace.append({"tool": tc.function.name, "args": args})
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
        "latency_ms": latency_ms,
    }
