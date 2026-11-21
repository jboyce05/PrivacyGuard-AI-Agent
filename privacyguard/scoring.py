"""FR-4 Risk Scorer: item, combination, overall. Fixed formulas, no AI."""
from __future__ import annotations
import math

QUASI = {"name", "birth_date", "address", "employer", "job_title", "gender", "age"}
RISKY_PAIRS = [{"name", "birth_date"}, {"name", "address"}, {"name", "ssn"}, {"name", "phone"}]


def item_score(sensitivity: float, confidence: float, exposure: float) -> float:
    return min(10.0, sensitivity * confidence * exposure)


def combo_score(member_scores: list[float], cats: set[str]) -> float | None:
    k = len(cats & QUASI)
    if k < 2:
        return None
    s = min(10.0, max(member_scores) + 1.5 * (k - 1))
    if any(p <= cats for p in RISKY_PAIRS):
        s = max(s, 7.0)
    return s


def overall_score(scores: list[float]) -> float:
    if not scores:
        return 0.0
    others = max(sum(s >= 4 for s in scores) - 1, 0)
    return min(10.0, max(scores) + 0.5 * math.log2(1 + others))
