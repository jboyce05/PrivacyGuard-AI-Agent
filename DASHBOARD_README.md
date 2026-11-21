# PrivacyGuard AI dashboard

    pip install streamlit
    streamlit run app.py
    pytest tests

- `app.py`: dashboard (overall score, compliance warnings, findings, Approve / Other fix / Ignore / Why?, before-after preview, save as new copy, masked report download)
- `.streamlit/config.toml`: dark "security console" theme, 10 MB upload limit, usage telemetry off (the app promises nothing is sent)
- `models.py`: `Finding`, `Warning`, `Report` (what the pipeline must return)
- `pipeline_adapter.py`: the only seam to teammates' code. Expose `run_scan`, `preview_changes`, `apply_all`, `wipe`, `EXPOSURE` from `privacyguard.pipeline` and the dashboard uses it automatically; otherwise it uses `demo_pipeline.py` (regex-only stand-in).
