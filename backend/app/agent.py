"""
The agent loop.

The flow is a standard tool-calling loop:

  1. Send the user's question to the model along with the tool schemas.
  2. If the model asks to call tools, run them and feed the results back.
  3. Repeat until the model answers in plain text instead of calling a
     tool, or until a step cap is hit (so a confused model can't loop
     forever).

The loop is built by hand rather than with a framework like LangChain.
That is deliberate: it keeps the control flow visible and debuggable, and
there is little to it once the shape is clear.

Uses the async OpenAI client so tool execution and the model call don't
block the event loop.
"""

import json
import os
import time

from openai import AsyncOpenAI
from dotenv import load_dotenv

from app.agent_tools import TOOL_SCHEMAS, execute_tool, available_datasets

load_dotenv()

CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")
DOMAIN_LABEL = os.getenv("SYSTEM_PROMPT_LABEL", "document and data assistant")
MAX_STEPS = 6

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or api_key == "sk-replace-me":
            raise RuntimeError("OPENAI_API_KEY is not set in .env")
        _client = AsyncOpenAI(api_key=api_key)
    return _client


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
        f"2. Uploaded datasets, via the analyze_dataset tool.\n\n"
        f"{ds_block}\n\n"
        f"Rules:\n"
        f"- Use search_documents for policy, eligibility, rules, or "
        f"procedure questions.\n"
        f"- Use analyze_dataset for counts, averages, or distributions.\n"
        f"- A question may need both. Call the tools you need, then answer.\n"
        f"- Ground your answer in what the tools return. When you use a "
        f"document, name the source file.\n"
        f"- If the tools don't contain the answer, say so plainly instead "
        f"of guessing."
    )


async def run_agent(conn, query: str) -> dict:
    client = _get_client()
    datasets = await available_datasets(conn)

    messages = [
        {"role": "system", "content": _build_system_prompt(datasets)},
        {"role": "user", "content": query},
    ]

    tool_trace = []
    start = time.time()

    for step in range(MAX_STEPS):
        resp = await client.chat.completions.create(
            model=CHAT_MODEL,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
        )
        msg = resp.choices[0].message

        # no tool calls means the model is done and this is the answer
        if not msg.tool_calls:
            return {
                "answer": msg.content,
                "steps": step + 1,
                "tool_trace": tool_trace,
                "latency_ms": int((time.time() - start) * 1000),
            }

        # record the assistant turn (with its tool calls) in the history
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

        # run each requested tool and feed the result back
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

    # ran out of steps without a final answer
    return {
        "answer": "I couldn't finish within the step limit. Try a simpler question.",
        "steps": MAX_STEPS,
        "tool_trace": tool_trace,
        "latency_ms": int((time.time() - start) * 1000),
    }
