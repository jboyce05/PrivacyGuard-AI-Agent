"""FR-5 Recommendation Engine: fixed rules pick the action; a template writes the explanation."""
from __future__ import annotations

RISK_TEXT = {
    "ssn": "A Social Security number can be used for identity theft.",
    "card": "A card number can be used for fraudulent charges.",
    "email": "An email address links this text to you and can be used for spam or phishing.",
    "phone": "A phone number can be used to contact or locate someone.",
    "birth_date": "A birth date is a common identity-verification detail.",
    "password": "A password gives direct access to an account.",
    "ip_address": "An IP address can reveal a rough location or device.",
    "name": "A name ties other details in this text to a real person.",
    "health": "Health details are highly sensitive and often covered by consent rules.",
    "address": "An address reveals where a person lives or works.",
    "financial": "Financial details can enable fraud or targeting.",
    "bank": "Bank details can be used for fraudulent transfers.",
    "minor": "Information about a minor usually needs a guardian's consent to share.",
    "student_record": "Student records are protected and need consent to share.",
    "combination": "These details together can identify a specific person even if each looks harmless.",
}
FIX_TEXT = {"Redact": "removes the value and leaves a block", "Mask": "keeps only the last 4 characters",
            "Generalize": "keeps only the year", "Pseudonymize": "swaps the name for a label",
            "Remove": "deletes the value", "Keep": "leaves the value unchanged"}
ALWAYS_REDACT = {"ssn", "card", "bank", "password"}


def recommend(category: str, score: float, is_combo: bool = False) -> str:
    if is_combo:
        return "Generalize"
    if score >= 8 or category in ALWAYS_REDACT:
        return "Redact"
    if category == "name":
        return "Pseudonymize"
    if category == "birth_date":
        return "Generalize"
    return "Mask"


def explain(category: str, location: str, action: str, reason: str = "") -> str:
    why = reason or RISK_TEXT.get(category, "This detail may be personal or sensitive.")
    return f"Found {category.replace('_', ' ')} at {location}. {why} Suggested: {action}, which {FIX_TEXT[action]}."
