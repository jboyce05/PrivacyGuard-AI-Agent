"""Single seam between the dashboard and the rest of the team's code.

When the real pipeline exists, expose these four functions from `privacyguard.pipeline`
and the dashboard switches over automatically. Until then the demo pipeline is used.
Contract:
  run_scan(text, recipient, filename=None) -> (Report, job)
  preview_changes(job, approved_findings)  -> list[dict]  (masked before / after)
  apply_all(job, approved_findings)        -> str         (new copy; original untouched)
  wipe(job)                                -> None        (secureWipe, always called)
"""
try:
    from privacyguard.pipeline import run_scan, preview_changes, apply_all, wipe, EXPOSURE  # type: ignore
    MODE = "live"
except ImportError:
    from demo_pipeline import run_scan, preview_changes, apply_all, wipe, EXPOSURE
    MODE = "demo"
