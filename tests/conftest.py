import os, sys, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from privacyguard import llm


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    """Unit tests never call Ollama."""
    monkeypatch.setattr(llm, "call_model", lambda *a, **k: None)
    monkeypatch.setattr(llm, "available", lambda: False)
