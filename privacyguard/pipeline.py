"""Scan pipeline that satisfies the contract in pipeline_adapter.py:
  run_scan, preview_changes, apply_all, wipe, EXPOSURE.
Order (Part 2): Pattern Detector -> Context Analyzer -> Risk Scorer -> Recommendation Engine
-> Compliance Checker -> Report. Raw values live only in ScanJob (memory) and are wiped by wipe().
"""
from __future__ import annotations
import re
import uuid
from dataclasses import dataclass, field

from models import Finding, Report, Warning, level_for
from . import compliance, llm, recommend, scoring
from .context import context_scan, merge_overlapping
from .rules import pattern_scan

EXPOSURE = {"Private (a friend or family)": 0.8, "Unknown": 1.0, "AI tool": 1.2, "Public": 1.5}
MAX_BYTES = 10 * 1024 * 1024


@dataclass
class ScanJob:
    text: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    raw: dict = field(default_factory=dict)   # finding id -> (start, end, raw value)


def mask_value(cat: str, v: str) -> str:
    digits = re.sub(r"\W", "", v)
    if cat == "ssn": return "***-**-" + digits[-4:]
    if cat == "card": return "**** **** **** " + digits[-4:]
    if cat == "email": u, _, d = v.partition("@"); return u[:1] + "***@" + d
    if cat == "phone": return "***-***-" + digits[-4:]
    if cat == "password": return "********"
    return re.sub(r"\w", "*", v[:-2]) + v[-2:] if len(v) > 4 else "*" * len(v)


def _generalize(cat: str, raw: str) -> str:
    if cat == "birth_date":
        m = re.search(r"\d{4}", raw)
        return m.group() if m else "[GENERALIZED]"
    return "[GENERALIZED]"


def _replacement(job: ScanJob, f: Finding, raw: str, labels: dict) -> str:
    a = f.decision
    if a == "Redact": return "[REDACTED]"
    if a == "Remove": return ""
    if a == "Keep": return raw
    if a == "Mask": return "*" * max(len(raw) - 4, 0) + raw[-4:]
    if a == "Generalize": return _generalize(f.category, raw)
    if a == "Pseudonymize":
        labels.setdefault(raw.lower(), "Person " + chr(ord("A") + len(labels) % 26))
        return labels[raw.lower()]
    return raw


def run_scan(text: str, recipient: str, filename: str | None = None):
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError("Input is over 10 MB.")
    exposure = EXPOSURE.get(recipient, 1.0)
    job = ScanJob(text)

    # FR-2 + FR-3
    ctx_hits, ctx_ran = context_scan(text, recipient)
    hits = merge_overlapping(pattern_scan(text), ctx_hits)

    # FR-4 items + FR-5
    findings: list[Finding] = []
    for h in hits:
        fid = uuid.uuid4().hex[:8]
        job.raw[fid] = (h.start, h.end, h.value)
        score = round(scoring.item_score(h.sensitivity, h.confidence, exposure), 1)
        line = text.count("\n", 0, h.start) + 1
        action = recommend.recommend(h.category, score)
        findings.append(Finding(fid, h.category, mask_value(h.category, h.value), f"line {line}",
                                h.sensitivity, h.confidence, exposure, score, h.source,
                                recommend.explain(h.category, f"line {line}", action, h.reason), action,
                                reason=h.reason))

    # FR-4 combinations (single-document scan: all findings are treated as one group)
    cats = {f.category for f in findings}
    cs = scoring.combo_score([f.score for f in findings], cats) if findings else None
    if cs is not None:
        quasi = sorted(cats & scoring.QUASI)
        findings.append(Finding(uuid.uuid4().hex[:8], "combination", " + ".join(quasi), "multiple locations",
                                0, 1.0, exposure, round(cs, 1), "combination",
                                recommend.explain("combination", "multiple locations", "Generalize"), "Generalize"))

    findings.sort(key=lambda f: -f.score)
    overall = round(scoring.overall_score([f.score for f in findings]), 1)

    # FR-6
    warns = [Warning(name, compliance.NOTE, ids)
             for name, ids in compliance.check(text, [(f.id, f.category) for f in findings])]

    # FR-7
    n = len(findings)
    verdict = ("No sensitive items found." if not n else
               f"{n} sensitive item(s) found. Review before sharing with: {recipient}.")
    coverage = []
    if not llm.available() or not ctx_ran:
        coverage.append("The AI context check was unavailable (is Ollama running?). Only pattern rules ran.")
    if filename and not filename.lower().endswith((".txt", ".md", ".csv")):
        coverage.append("Only plain text was read from this file.")
    return Report(overall, level_for(overall), verdict, recipient, warns, findings, coverage), job


def preview_changes(job: ScanJob, findings):
    """Masked before / after rows. Combination findings have no span of their own and are skipped."""
    labels: dict = {}
    rows = []
    for f in sorted((f for f in findings if f.id in job.raw), key=lambda f: job.raw[f.id][0]):
        raw = job.raw[f.id][2]
        after = f.masked_value if f.decision == "Mask" else _replacement(job, f, raw, labels)
        rows.append({"Location": f.location, "Item": f.category, "Before": f.masked_value,
                     "Fix": f.decision, "After": after})
    return rows


def apply_all(job: ScanJob, findings) -> str:
    """Return a NEW string with approved fixes applied. The original input is never modified."""
    labels: dict = {}
    spans = sorted((f for f in findings if f.id in job.raw), key=lambda f: job.raw[f.id][0])
    repl = {f.id: _replacement(job, f, job.raw[f.id][2], labels) for f in spans}   # label order = text order
    out = job.text
    for f in sorted(spans, key=lambda f: -job.raw[f.id][0]):
        s, e, _ = job.raw[f.id]
        out = out[:s] + repl[f.id] + out[e:]
    return out


def wipe(job) -> None:
    if job is not None:
        job.text = ""
        job.raw.clear()
