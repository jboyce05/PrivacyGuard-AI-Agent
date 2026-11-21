"""FR-2 Pattern Detector: regex + validators + keyword proximity."""
from __future__ import annotations
import re
from dataclasses import dataclass


@dataclass
class Hit:
    category: str
    start: int
    end: int
    value: str
    confidence: float
    sensitivity: float
    source: str = "pattern"
    reason: str = ""


def luhn(s: str) -> bool:
    d = [int(c) for c in re.sub(r"\D", "", s)][::-1]
    if not 13 <= len(d) <= 19:
        return False
    return sum(x if i % 2 == 0 else (x * 2 - 9 if x * 2 > 9 else x * 2) for i, x in enumerate(d)) % 10 == 0


def valid_ssn(s: str) -> bool:
    a, g, n = s.split("-")
    return a not in ("000", "666") and not a.startswith("9") and g != "00" and n != "0000"


def valid_ipv4(s: str) -> bool:
    return all(0 <= int(octet) <= 255 for octet in s.split("."))


# category: (regex, base sensitivity, keywords, validator)
RULES = {
    "ssn": (r"\b\d{3}-\d{2}-\d{4}\b", 10, ["ssn", "social security"], valid_ssn),
    "card": (r"\b(?:\d[ -]?){13,19}\b", 9, ["card", "visa", "mastercard", "credit", "amex"], luhn),
    "email": (r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", 4, ["email", "contact", "e-mail"], None),
    "phone": (r"(?<!\d)(?:\+?1[ -.])?\(?\d{3}\)?[ -.]\d{3}[ -.]\d{4}\b", 5, ["phone", "call", "cell", "mobile"], None),
    "birth_date": (r"\b\d{1,2}/\d{1,2}/\d{4}\b", 6, ["dob", "born", "birth", "birthday"], None),
    "password": (r"(?i)(?:password|passwd|pwd)\s*[:=]\s*\S+", 10, ["password"], None),
    "ip_address": (r"\b(?:\d{1,3}\.){3}\d{1,3}\b", 3, ["ip"], valid_ipv4),
}


def keyword_nearby(text: str, start: int, end: int, kws: list[str], window: int = 30) -> bool:
    near = text[max(0, start - window):end + window].lower()
    return any(k in near for k in kws)


def pattern_scan(text: str) -> list[Hit]:
    hits = []
    for cat, (rx, sens, kws, validator) in RULES.items():
        for m in re.finditer(rx, text):
            if validator and not validator(m.group()):
                continue
            conf = 0.95 if keyword_nearby(text, m.start(), m.end(), kws) else 0.6
            hits.append(Hit(cat, m.start(), m.end(), m.group(), conf, sens))
    return hits
