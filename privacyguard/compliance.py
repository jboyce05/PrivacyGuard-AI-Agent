"""FR-6 Compliance Checker. Flags content that usually needs consent or legal review. Not legal advice."""
from __future__ import annotations

NOTE = "Usually comes with consent or legal rules. Not legal advice."
FLAG_FOR = {"health": "Health information", "minor": "Information about a minor",
            "student_record": "Student record", "card": "Financial account number",
            "bank": "Financial account number", "ssn": "Government ID number",
            "religion": "GDPR special category", "sexual_orientation": "GDPR special category",
            "political": "GDPR special category", "ethnicity": "GDPR special category"}
THIRD_PARTY = {"minor", "student_record", "health"}
CONFIDENTIAL_MARKERS = ["confidential", "internal use only", "do not distribute", "privileged"]


def check(text: str, findings: list[tuple[str, str]]) -> list[tuple[str, list[str]]]:
    """findings: (id, category). Returns [(flag name, [finding ids])]."""
    flags: dict[str, list[str]] = {}
    for fid, cat in findings:
        if cat in FLAG_FOR:
            flags.setdefault(FLAG_FOR[cat], []).append(fid)
    third = [fid for fid, cat in findings if cat in THIRD_PARTY]
    if third:
        flags["Third-party info"] = third
    low = text.lower()
    if any(m in low for m in CONFIDENTIAL_MARKERS):
        flags["Confidential marking"] = []
    return list(flags.items())
