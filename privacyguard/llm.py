"""Local model API (Ollama on 127.0.0.1). Section 4.4: temperature 0, JSON schema, 30s timeout, retry once.
Returns None if the model is unreachable so callers can degrade gracefully."""
from __future__ import annotations
import json
import os
import requests

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
MODEL = os.environ.get("PRIVACYGUARD_MODEL", "llama3.2")   # installed locally as llama3.2:latest (3B)
TIMEOUT = 30
COLD_TIMEOUT = 120   # first call also loads the model into memory
_warm = False


def available() -> bool:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        names = [m["name"] for m in r.json().get("models", [])]
        return any(n.split(":")[0] == MODEL.split(":")[0] for n in names)
    except Exception:
        return False


def call_model(system: str, user: str, schema: dict) -> dict | None:
    global _warm
    for _ in range(2):
        try:
            r = requests.post(f"{OLLAMA_URL}/api/chat", timeout=TIMEOUT if _warm else COLD_TIMEOUT, json={
                "model": MODEL, "stream": False, "format": schema, "options": {"temperature": 0},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
            r.raise_for_status()
            _warm = True
            return json.loads(r.json()["message"]["content"])
        except (requests.ConnectionError, requests.Timeout):
            return None          # unreachable: retrying won't help
        except (ValueError, KeyError, requests.HTTPError):
            continue             # malformed reply: retry once
    return None
