"""
Evaluation results route.

GET /eval/results reads the artifacts written by the offline eval scripts
(retrieval comparison, answer records, latency) and returns one combined
payload for the dashboard. Answer aggregates are computed here from the
per-query records so the eval script does not need to pre-summarize.

Evaluation is an offline batch process; this endpoint serves the latest
snapshot on disk. Missing files return null for that section rather than
failing, so the dashboard can render whatever has been run.
"""

import json
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/eval", tags=["eval"])

EVAL_DIR = Path(__file__).resolve().parents[2] / "eval"


def _load(name: str):
    path = EVAL_DIR / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def _summarize_answers(records):
    if not records:
        return None

    scored = [r for r in records if r.get("type") != "out_of_scope"]
    by_type = {}
    for r in scored:
        by_type.setdefault(r["type"], {"correct": 0, "total": 0})
        by_type[r["type"]]["total"] += 1
        if r.get("correct"):
            by_type[r["type"]]["correct"] += 1

    correct_total = sum(1 for r in scored if r.get("correct"))

    faith = [r for r in records if "faithfulness" in r]
    fcounts = {"grounded": 0, "partial": 0, "unsupported": 0}
    score_map = {"grounded": 1.0, "partial": 0.5, "unsupported": 0.0}
    fscore_sum = 0.0
    for r in faith:
        v = r["faithfulness"]
        fcounts[v] = fcounts.get(v, 0) + 1
        fscore_sum += score_map.get(v, 0.0)

    oos = [r for r in records if "oos_appropriate" in r]
    oos_ok = sum(1 for r in oos if r.get("oos_appropriate"))

    return {
        "correctness": {
            "overall": {"correct": correct_total, "total": len(scored)},
            "by_type": by_type,
        },
        "faithfulness": {
            "score": round(fscore_sum / len(faith), 3) if faith else None,
            "counts": fcounts,
            "n": len(faith),
        },
        "out_of_scope": {"appropriate": oos_ok, "total": len(oos)},
    }


@router.get("/results")
def eval_results():
    return {
        "retrieval": _load("eval_retrieval_results.json"),
        "answers": _summarize_answers(_load("eval_answers_results.json")),
        "latency": _load("eval_latency_results.json"),
    }
