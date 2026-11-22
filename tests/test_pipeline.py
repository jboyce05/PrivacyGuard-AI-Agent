import pytest
from privacyguard import pipeline as p
from privacyguard import llm


def test_ssn_card_and_validators():
    r, job = p.run_scan("My SSN is 123-45-6789, card 4111 1111 1111 1111, bad 000-12-3456, bad card 1234 5678 9012 3456", "AI tool")
    cats = [f.category for f in r.findings]
    assert cats.count("ssn") == 1 and cats.count("card") == 1
    assert r.level in ("High", "Critical")
    assert all("6789" not in f.masked_value or f.masked_value.startswith("***") for f in r.findings)
    assert any("unavailable" in c for c in r.coverage)


def test_combo_and_apply_leaves_original():
    text = "Name: Jane\nDOB: 04/12/1990\nhome address 12 Main St"
    r, job = p.run_scan(text, "Public")
    assert any(f.category == "birth_date" for f in r.findings)
    for f in r.findings:
        f.decision = "Generalize"
    out = p.apply_all(job, [f for f in r.findings if f.category == "birth_date"])
    assert "1990" in out and "04/12" not in out and job.text == text


def test_wipe():
    r, job = p.run_scan("call 555-123-4567", "Unknown")
    p.wipe(job)
    assert job.text == "" and not job.raw


def test_adapter_goes_live():
    import pipeline_adapter
    assert pipeline_adapter.MODE == "live"
