import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from streamlit.testing.v1 import AppTest
import demo_pipeline as d

SAMPLE = "Hi, my SSN is 123-45-6789 and card 4111 1111 1111 1111. Email jo.smith@example.com, born 04/12/1999."

def test_pipeline_masks_and_scores():
    r, job = d.run_scan(SAMPLE, "AI tool")
    cats = {f.category for f in r.findings}
    assert {"ssn", "card", "email", "birth_date"} <= cats
    assert r.findings[0].score == 10 and r.level == "Critical"
    assert all("123-45-6789" not in f.explanation + f.masked_value for f in r.findings)
    assert [f.score for f in r.findings] == sorted((f.score for f in r.findings), reverse=True)

def test_apply_never_mutates_original():
    r, job = d.run_scan(SAMPLE, "AI tool")
    for f in r.findings: f.decision = f.action
    out = d.apply_all(job, r.findings)
    assert "123-45-6789" not in out and job.text == SAMPLE

def test_wipe():
    _, job = d.run_scan(SAMPLE, "Public"); d.wipe(job)
    assert job.text == "" and not job.raw

def test_app_flow():
    at = AppTest.from_file(os.path.join(os.path.dirname(__file__), "..", "app.py"), default_timeout=20).run()
    assert not at.exception
    at.text_area(key="msg").set_value(SAMPLE).run()
    [b for b in at.button if b.label == "Scan"][0].click().run()
    assert not at.exception and "Critical" in " ".join(m.value for m in at.markdown)
    [b for b in at.button if b.label.startswith("Approve")][0].click().run()
    assert not at.exception
    [b for b in at.button if b.label.startswith("Done")][0].click().run()
    assert not at.exception and len(at.dataframe) == 1
