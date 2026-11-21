"""PrivacyGuard AI: privacy dashboard (report view + Approval Gate screens).

Run:  streamlit run app.py
Covers FR-7 (report display), DR-2 (human oversight: approve / choose / ignore / why / preview /
save as new copy) and the DR-1 session rules (memory only, wipe on done or 15 min idle).
"""
import time
import streamlit as st
import pipeline_adapter as pipe
from models import ACTIONS, LEVELS, level_for

IDLE_LIMIT = 15 * 60
LEVEL_STYLE = {"Low": ("🟢", "#1a7f37"), "Medium": ("🟡", "#9a6700"),
               "High": ("🟠", "#bc4c00"), "Critical": ("🔴", "#cf222e")}
RECIPIENTS = list(pipe.EXPOSURE.keys())

st.set_page_config(page_title="PrivacyGuard AI", page_icon="🛡️", layout="wide")


# ---------- session handling (DR-1) ----------
def wipe_session(msg=None):
    pipe.wipe(st.session_state.get("job"))
    for k in ("job", "report", "preview_open", "saved_copy", "filename"):
        st.session_state.pop(k, None)
    if msg:
        st.session_state["notice"] = msg


now = time.time()
if "report" in st.session_state and now - st.session_state.get("last_active", now) > IDLE_LIMIT:
    wipe_session("Session cleared after 15 minutes of inactivity. Scan data was wiped.")
st.session_state["last_active"] = now


# ---------- sidebar: input ----------
with st.sidebar:
    st.title("🛡️ PrivacyGuard AI")
    st.caption(f"Runs on this device. Nothing is uploaded or sent. ({pipe.MODE} pipeline)")
    recipient = st.selectbox("Who are you sharing this with?", RECIPIENTS, index=2,
                             help="Sets the exposure factor used in the risk score (FR-4).")
    tab_text, tab_file = st.tabs(["Message", "File"])
    with tab_text:
        text = st.text_area("Type or paste a message", height=180, key="msg")
    with tab_file:
        upload = st.file_uploader("Upload .txt, .md, .csv", type=["txt", "md", "csv"])
        st.caption("Under 10 MB. .docx and .pdf support comes from the Input Handler (FR-1).")
    if st.button("Scan", type="primary", use_container_width=True):
        content, fname = text, None
        if upload is not None:
            if upload.size > 10 * 1024 * 1024:
                st.error("File is over 10 MB.")
                content = ""
            else:
                content, fname = upload.getvalue().decode("utf-8", errors="replace"), upload.name
        if content.strip():
            wipe_session()
            with st.spinner("Scanning on this device…"):
                st.session_state.report, st.session_state.job = pipe.run_scan(content, recipient, fname)
                st.session_state.filename = fname
        else:
            st.warning("Add a message or a file first.")
    if "report" in st.session_state and st.button("Clear scan data now", use_container_width=True):
        wipe_session("Scan data wiped.")
        st.rerun()

if n := st.session_state.pop("notice", None):
    st.info(n)

report = st.session_state.get("report")
if report is None:
    st.header("Privacy dashboard")
    st.write("Scan a message or file to see its risk score, what was found, and suggested fixes. "
             "Nothing is changed unless you approve it.")
    st.stop()


# ---------- header: overall score + verdict (FR-7) ----------
icon, color = LEVEL_STYLE[report.level]
pending = [f for f in report.findings if f.decision == "pending"]
c1, c2, c3 = st.columns([1, 2, 1.2])
c1.metric("Overall risk", f"{report.overall:.1f} / 10")
c2.markdown(f"### {icon} <span style='color:{color}'>{report.level}</span>", unsafe_allow_html=True)
c2.write(report.verdict)
c3.metric("Reviewed", f"{len(report.findings) - len(pending)} of {len(report.findings)}")
st.progress(report.overall / 10, text=f"Scale: Low <3 · Medium 3–6 · High 6–8 · Critical 8+")

for w in report.warnings:  # compliance flags sit at the top (FR-6)
    st.warning(f"**{w.name}.** {w.note}  \nAffects {len(w.finding_ids)} item(s).", icon="⚠️")

# ---------- findings list with Approval Gate controls (DR-2) ----------
st.subheader("Findings")
f1, f2 = st.columns([2, 1])
shown_levels = f1.multiselect("Show levels", LEVELS, default=LEVELS)
only_pending = f2.toggle("Pending only", value=False)
rows = [f for f in report.findings
        if (not only_pending or f.decision == "pending") and
        level_for(f.score) in shown_levels]
if not report.findings:
    st.success("No sensitive items found.")

for f in rows:
    ic = LEVEL_STYLE[level_for(f.score)][0]
    status = "⏳ pending" if f.decision == "pending" else (
        "↩️ ignored (kept as is)" if f.decision == "Keep" else f"✅ {f.decision}")
    with st.expander(f"{ic} {f.score:.1f} · {f.category} · {f.masked_value.replace('*', chr(92) + '*')} · {status}",
                     expanded=f.decision == "pending" and f.score >= 6):
        st.write(f"**Location:** {f.location}  ·  **Found by:** {f.source}")
        st.write(f.explanation)
        if f.note_source:
            st.caption(f"Source: {f.note_source}")
        b1, b2, b3, b4 = st.columns([1.4, 1.6, 1, 1])
        if b1.button(f"Approve: {f.action}", key=f"ap{f.id}"):
            f.decision = f.action; st.rerun()
        choice = b2.selectbox("Other fix", ACTIONS, index=ACTIONS.index(f.action),
                              key=f"sel{f.id}", label_visibility="collapsed")
        if b2.button("Use this instead", key=f"ch{f.id}"):
            f.decision = choice; st.rerun()
        if b3.button("Ignore", key=f"ig{f.id}"):
            f.decision = "Keep"; st.rerun()
        if b4.button("Undo", key=f"un{f.id}", disabled=f.decision == "pending"):
            f.decision = "pending"; st.rerun()
        with st.popover("Why?"):  # DR-2: detector + how the score was calculated
            raw = f.sensitivity * f.confidence * f.exposure
            st.write(f"**Detector:** {f.source}" + (f"  \n**Model reason:** {f.reason}" if f.reason else ""))
            if f.source == "combination":
                st.write("Score from the quasi-identifier group rule (+1.5 per extra identifier, "
                         "known risky pairs at least 7).")
            else:
                st.code(f"score = sensitivity × confidence × exposure\n"
                        f"      = {f.sensitivity:g} × {f.confidence:.2f} × {f.exposure:g} = {raw:.2f}\n"
                        f"      capped at 10 → {f.score:.1f}")

for c in report.coverage:
    st.caption(f"ℹ️ Not covered: {c}")

# ---------- finish: preview, confirm, save as new copy ----------
st.divider()
approved = [f for f in report.findings if f.decision not in ("pending", "Keep")]
d1, d2 = st.columns([1, 3])
if d1.button("Done: preview changes", type="primary", disabled=not approved):
    st.session_state.preview_open = True
if not approved:
    d2.caption("Approve at least one fix to preview and save a changed copy.")
if st.session_state.get("preview_open") and approved:
    st.subheader("Before and after")
    st.caption("Sensitive values stay masked on screen. Your original is never edited.")
    st.dataframe(pipe.preview_changes(st.session_state.job, approved), use_container_width=True,
                 hide_index=True)
    if st.button("Confirm and create new copy"):
        st.session_state.saved_copy = pipe.apply_all(st.session_state.job, approved)
    if "saved_copy" in st.session_state:
        name = st.session_state.get("filename") or "message.txt"
        st.success("New copy created. The original was not changed.")
        st.download_button("Download new copy", st.session_state.saved_copy,
                           file_name=f"privacyguard_{name}")

# masked report export (never contains raw values)
md = [f"# PrivacyGuard report\n\nOverall: {report.overall}/10 ({report.level}). {report.verdict}\n"]
md += [f"- ⚠️ {w.name}: {w.note}" for w in report.warnings]
md += [f"\n- **{f.category}** `{f.masked_value}` ({f.location}), score {f.score}, "
       f"suggested {f.action}, decision: {f.decision}" for f in report.findings]
md += [f"\nNot covered: {c}" for c in report.coverage]
st.download_button("Download masked report (.md)", "\n".join(md), file_name="privacyguard_report.md")
