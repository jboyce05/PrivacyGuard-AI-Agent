"""Stand-in scan pipeline so the dashboard runs before teammates' modules are merged.

Implements a tiny slice of FR-2 / FR-4 / FR-5 / FR-6 (regex only) using the formulas in
the Part 2 design. Raw values stay in `DemoJob` (memory only) and are wiped by `wipe`.
"""
from __future__ import annotations
import math, re, uuid
from dataclasses import dataclass, field
from models import Finding, Report, Warning, level_for

EXPOSURE = {"Private (a friend or family)": 0.8, "Unknown": 1.0, "AI tool": 1.2, "Public": 1.5}

RULES = {  # category: (regex, base sensitivity, keywords)
    "ssn": (r"\b\d{3}-\d{2}-\d{4}\b", 10, ["ssn", "social security"]),
    "card": (r"\b(?:\d[ -]?){13,16}\b", 9, ["card", "visa", "credit"]),
    "email": (r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", 4, ["email", "contact"]),
    "phone": (r"\b\(?\d{3}\)?[ -.]\d{3}[ -.]\d{4}\b", 5, ["phone", "call", "cell"]),
    "birth_date": (r"\b\d{1,2}/\d{1,2}/\d{4}\b", 6, ["dob", "born", "birth"]),
}
RISK_TEXT = {
    "ssn": "A Social Security number can be used for identity theft.",
    "card": "A card number can be used for fraudulent charges.",
    "email": "An email address links this text to you and can be used for spam or phishing.",
    "phone": "A phone number can be used to contact or locate someone.",
    "birth_date": "A birth date is a common identity-verification detail.",
}
FIX_TEXT = {"Redact": "removes the value and leaves a block", "Mask": "keeps only the last 4 characters",
            "Generalize": "keeps only the year", "Pseudonymize": "swaps the name for a label",
            "Remove": "deletes the value", "Keep": "leaves the value unchanged"}
FLAG_FOR = {"card": "Financial account number", "ssn": "Government ID number"}


@dataclass
class DemoJob:
    text: str
    raw: dict = field(default_factory=dict)   # finding id -> (start, end, raw value)


def _luhn(s: str) -> bool:
    d = [int(c) for c in re.sub(r"\D", "", s)][::-1]
    return len(d) >= 13 and sum(x if i % 2 == 0 else (x * 2 - 9 if x * 2 > 9 else x * 2)
                                 for i, x in enumerate(d)) % 10 == 0


def mask_value(cat: str, v: str) -> str:
    digits = re.sub(r"\W", "", v)
    if cat == "ssn": return "***-**-" + digits[-4:]
    if cat == "card": return "**** **** **** " + digits[-4:]
    if cat == "email": u, _, d = v.partition("@"); return u[:1] + "***@" + d
    if cat == "phone": return "***-***-" + digits[-4:]
    return re.sub(r"\d", "*", v[:-4]) + v[-4:]


def apply_action(cat: str, raw: str, action: str) -> str:
    digits = re.sub(r"\W", "", raw)
    return {"Redact": "[REDACTED]", "Remove": "", "Keep": raw,
            "Mask": "*" * max(len(raw) - 4, 0) + raw[-4:],
            "Generalize": raw[-4:] if cat == "birth_date" else "[GENERALIZED]",
            "Pseudonymize": "Person A"}[action]


def recommend(cat: str, score: float) -> str:
    if score >= 8 or cat in {"ssn", "card", "bank", "password"}: return "Redact"
    if cat == "birth_date": return "Generalize"
    return "Mask"


def run_scan(text: str, recipient: str, filename: str | None = None):
    job, found, exp = DemoJob(text), [], EXPOSURE.get(recipient, 1.0)
    for cat, (rx, sens, kws) in RULES.items():
        for m in re.finditer(rx, text, re.I):
            if cat == "card" and not _luhn(m.group()): continue
            near = text[max(0, m.start() - 30):m.end() + 30].lower()
            conf = 0.95 if any(k in near for k in kws) else 0.6
            score = min(10.0, sens * conf * exp)
            fid = uuid.uuid4().hex[:8]
            job.raw[fid] = (m.start(), m.end(), m.group())
            act = recommend(cat, score)
            line = text.count("\n", 0, m.start()) + 1
            found.append(Finding(fid, cat, mask_value(cat, m.group()), f"line {line}", sens, conf,
                                 exp, round(score, 1), "pattern",
                                 f"Found {cat} on line {line}. {RISK_TEXT[cat]} Suggested: {act}, "
                                 f"which {FIX_TEXT[act]}.", act))
    found.sort(key=lambda f: -f.score)
    others = sum(f.score >= 4 for f in found) - 1
    overall = min(10.0, (found[0].score + 0.5 * math.log2(1 + max(others, 0))) if found else 0.0)
    warns = [Warning(FLAG_FOR[c], "Usually comes with consent or legal rules. Not legal advice.",
                     [f.id for f in found if f.category == c]) for c in FLAG_FOR
             if any(f.category == c for f in found)]
    verdict = ("No sensitive items found." if not found else
               f"{len(found)} sensitive item(s) found. Review before sharing with: {recipient}.")
    cov = ["Demo mode: regex rules only. The AI context check is not connected yet."]
    return Report(round(overall, 1), level_for(overall), verdict, recipient, warns, found, cov), job


def preview_changes(job: DemoJob, findings):
    """Before (masked) / after rows for each approved fix. Raw values are not shown."""
    return [{"Location": f.location, "Item": f.category, "Before": f.masked_value, "Fix": f.decision,
             "After": apply_action(f.category, job.raw[f.id][2], f.decision)
             if f.decision not in ("Redact", "Mask") else
             ("[REDACTED]" if f.decision == "Redact" else f.masked_value)} for f in findings]


def apply_all(job: DemoJob, findings) -> str:
    """Write approved fixes into a NEW string. The original input is never modified."""
    out = job.text
    for f in sorted(findings, key=lambda f: -job.raw[f.id][0]):
        s, e, raw = job.raw[f.id]
        out = out[:s] + apply_action(f.category, raw, f.decision) + out[e:]
    return out


def wipe(job) -> None:
    if job is not None:
        job.text = ""; job.raw.clear()
