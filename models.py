"""Typed objects the dashboard reads. They mirror the Part 2 design (Finding, Report).

Teammates' pipeline modules should return these (or objects with the same fields).
The dashboard never receives or displays raw sensitive values, only masked previews.
"""
from __future__ import annotations
from dataclasses import dataclass, field

ACTIONS = ["Redact", "Mask", "Generalize", "Pseudonymize", "Remove", "Keep"]
LEVELS = ["Low", "Medium", "High", "Critical"]


def level_for(score: float) -> str:
    """FR-4 levels: Low <3, Medium 3-6, High 6-8, Critical 8+."""
    return "Low" if score < 3 else "Medium" if score < 6 else "High" if score < 8 else "Critical"


@dataclass
class Finding:
    id: str
    category: str
    masked_value: str          # e.g. ***-**-1234. Never the raw value.
    location: str              # page / paragraph / cell
    sensitivity: float         # base 1-10
    confidence: float          # 0-1
    exposure: float            # recipient factor
    score: float               # 0-10 after scoring
    source: str                # "pattern" | "context" | "combination"
    explanation: str           # what / why risky / what the fix changes (FR-5)
    action: str                # suggested action (FR-5)
    reason: str = ""           # one-sentence LLM reason (context findings)
    note_source: str = ""      # RAG note citation, if any
    decision: str = "pending"  # "pending" | an action name ("Keep" = ignored)


@dataclass
class Warning:
    name: str                  # e.g. "Third-party info"
    note: str
    finding_ids: list[str] = field(default_factory=list)


@dataclass
class Report:
    overall: float
    level: str
    verdict: str
    recipient: str
    warnings: list[Warning]
    findings: list[Finding]    # sorted by score, highest first
    coverage: list[str]        # what the scan could not read
