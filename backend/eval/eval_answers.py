"""
Answer evaluation with an LLM judge.

Runs the real agent on every query, then scores three things:

1. Correctness. Does the answer contain the expected facts? For data
   queries the ground truth is an exact value computed from the source
   CSV; for document queries it is a key fact. Checked by substring, so
   this part is deterministic, not model opinion.

2. Faithfulness. For queries that searched documents, a separate LLM
   judge reads the retrieved context and the answer and decides whether
   every claim is supported. This catches hallucination: an answer can
   be fluent and still invent facts not in the sources.

3. Out-of-scope honesty. For questions the data and documents cannot
   answer, the judge checks that the agent declined instead of making
   something up.

Each query runs in a fresh session so earlier eval answers never leak
into later ones as conversation history.
"""

import asyncio
import json
import os
from pathlib import Path

import asyncpg
from openai import AsyncOpenAI
from dotenv import load_dotenv

from app.agent import run_agent
from app.search import hybrid_search

load_dotenv()

HERE = Path(__file__).parent
LABELED = HERE / "eval_set_labeled.json"
RESULTS = HERE / "eval_answers_results.json"
JUDGE_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")
CHUNK_CHARS = 500

_judge = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


FAITH_PROMPT = """You evaluate whether an answer is grounded in the provided context.

Context (the only information the answer should rely on):
{context}

Answer:
{answer}

Decide whether the answer's factual claims are supported by the context.
Respond with ONLY a JSON object, no markdown:
{{"verdict": "grounded" | "partial" | "unsupported", "reason": "<one short sentence>"}}
- grounded: every claim is supported by the context
- partial: mostly supported but at least one claim is not in the context
- unsupported: key claims are not in the context"""

OOS_PROMPT = """A user asked something the system's data and documents do NOT contain.

Question: {query}
Assistant answer: {answer}

Did the assistant appropriately say it could not find or does not have the
information, instead of fabricating an answer?
Respond with ONLY a JSON object, no markdown:
{{"appropriate": true | false, "reason": "<one short sentence>"}}"""


def parse_json(text: str) -> dict:
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)


async def judge(prompt: str) -> dict:
    resp = await _judge.chat.completions.create(
        model=JUDGE_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    try:
        return parse_json(resp.choices[0].message.content)
    except (json.JSONDecodeError, AttributeError):
        return {}


def correctness(answer: str, must_contain: list[str]) -> bool:
    low = (answer or "").lower()
    return all(term.lower() in low for term in must_contain)


async def build_context(conn, tool_trace: list) -> str:
    parts = []
    for step in tool_trace:
        if step["tool"] == "search_documents":
            q = step.get("args", {}).get("query", "")
            chunks = await hybrid_search(conn, q, top_k=5)
            for c in chunks:
                parts.append(f"[{c['filename']}] {c['content'][:CHUNK_CHARS]}")
        else:
            parts.append(f"[data:{step['tool']}] {json.dumps(step.get('result'), default=str)}")
    return "\n\n".join(parts) if parts else "(no tools were used)"


async def main():
    data = json.loads(LABELED.read_text())
    queries = data["queries"]

    conn = await asyncpg.connect(os.getenv("DATABASE_URL"))
    records = []
    try:
        for i, q in enumerate(queries, 1):
            print(f"[{i}/{len(queries)}] {q['id']}: {q['query'][:55]}...")
            run = await run_agent(conn, q["query"])  # fresh session each call
            answer = run["answer"]

            rec = {"id": q["id"], "type": q["type"], "query": q["query"], "answer": answer}

            if q["type"] == "out_of_scope":
                verdict = await judge(OOS_PROMPT.format(query=q["query"], answer=answer))
                rec["oos_appropriate"] = bool(verdict.get("appropriate"))
                rec["oos_reason"] = verdict.get("reason", "")
            else:
                rec["correct"] = correctness(answer, q.get("answer_must_contain", []))
                used_docs = any(s["tool"] == "search_documents" for s in run["tool_trace"])
                if used_docs:
                    context = await build_context(conn, run["tool_trace"])
                    v = await judge(FAITH_PROMPT.format(context=context, answer=answer))
                    rec["faithfulness"] = v.get("verdict", "unknown")
                    rec["faith_reason"] = v.get("reason", "")
            records.append(rec)
    finally:
        await conn.close()

    RESULTS.write_text(json.dumps(records, indent=2))

    # ---- aggregate ----
    def rate(items, key, val=True):
        xs = [r for r in items if key in r]
        if not xs:
            return None, 0
        hits = sum(1 for r in xs if r[key] == val)
        return hits / len(xs), len(xs)

    scored = [r for r in records if r["type"] != "out_of_scope"]
    by_type = {}
    for r in scored:
        by_type.setdefault(r["type"], []).append(r)

    print("\n=== ANSWER CORRECTNESS (contains expected facts) ===")
    overall, n = rate(scored, "correct")
    print(f"  overall: {overall:.0%}  ({sum(1 for r in scored if r.get('correct'))}/{n})")
    for t, items in by_type.items():
        r, nn = rate(items, "correct")
        print(f"  {t:<10}: {r:.0%}  ({sum(1 for x in items if x.get('correct'))}/{nn})")

    print("\n=== FAITHFULNESS (answer grounded in retrieved context) ===")
    faith = [r for r in records if "faithfulness" in r]
    counts = {"grounded": 0, "partial": 0, "unsupported": 0, "unknown": 0}
    for r in faith:
        counts[r["faithfulness"]] = counts.get(r["faithfulness"], 0) + 1
    score_map = {"grounded": 1.0, "partial": 0.5, "unsupported": 0.0, "unknown": 0.0}
    if faith:
        avg = sum(score_map.get(r["faithfulness"], 0) for r in faith) / len(faith)
        print(f"  faithfulness score: {avg:.2f}  (grounded=1, partial=0.5, unsupported=0)")
        print(f"  grounded {counts['grounded']} | partial {counts['partial']} | "
              f"unsupported {counts['unsupported']}  (n={len(faith)})")

    print("\n=== OUT-OF-SCOPE HONESTY (declined instead of fabricating) ===")
    oos = [r for r in records if "oos_appropriate" in r]
    ok = sum(1 for r in oos if r["oos_appropriate"])
    print(f"  appropriate declines: {ok}/{len(oos)}")
    for r in oos:
        mark = "ok" if r["oos_appropriate"] else "FAIL"
        print(f"    [{mark}] {r['id']}: {r.get('oos_reason','')}")

    print(f"\nWrote {RESULTS.name}")


if __name__ == "__main__":
    asyncio.run(main())
