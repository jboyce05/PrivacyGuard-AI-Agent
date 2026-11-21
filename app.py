"""PrivacyGuard AI: privacy dashboard (report view + Approval Gate screens).

Run:  streamlit run app.py
Covers FR-7 (report display), DR-2 (human oversight: approve / choose / ignore / why / preview /
save as new copy) and the DR-1 session rules (memory only, wipe on done or 15 min idle).

Layout: one-screen "console". KPI tiles on top, then a fixed-height scrolling findings list next
to an inspector for the selected finding. Approving jumps to the next pending item, and the
before/after preview opens in a dialog, so the page itself barely scrolls. On phones the columns
stack with the inspector first. Theme is in .streamlit/config.toml; the CSS below only adds the
neon styling and hooks onto Streamlit's stable `st-key-*` classes and `data-testid` attributes.
"""
import html
import re
import time
import streamlit as st
import pipeline_adapter as pipe
from models import ACTIONS, LEVELS, level_for

IDLE_LIMIT = 15 * 60
MAX_BYTES = 10 * 1024 * 1024
LEVEL_COLOR = {"Low": "#34d399", "Medium": "#facc15", "High": "#fb923c", "Critical": "#f43f5e"}
RECIPIENTS = list(pipe.EXPOSURE.keys())
ACRONYMS = {"ssn", "ip", "dob", "iban", "mrn", "nhs", "vin"}
STATUS_ICON = {"pending": ":material/radio_button_unchecked:", "Keep": ":material/block:"}
DONE_ICON = ":material/check_circle:"

st.set_page_config(page_title="PrivacyGuard AI", page_icon="🛡️", layout="wide",
                   initial_sidebar_state="collapsed")

CSS = """<style>
/* ---- canvas: grid lines + soft neon glow ---- */
.stApp {
  background:
    radial-gradient(900px 500px at 8% -10%, rgba(34,211,238,.10), transparent 60%),
    radial-gradient(800px 500px at 105% 0%, rgba(139,92,246,.10), transparent 60%),
    linear-gradient(rgba(34,211,238,.035) 1px, transparent 1px) 0 0 / 34px 34px,
    linear-gradient(90deg, rgba(34,211,238,.035) 1px, transparent 1px) 0 0 / 34px 34px,
    #060a13;
}
[data-testid="stHeader"] { background: transparent; }
[data-testid="stMainBlockContainer"] { max-width: 1400px; padding: 1.6rem 2rem 2rem; }
@media (max-width: 640px) { [data-testid="stMainBlockContainer"] { padding: 1rem .75rem 2rem; } }

/* ---- brand + status ---- */
.pg-brand { font-family: ui-monospace, 'Cascadia Code', 'SF Mono', Menlo, Consolas, monospace;
  font-size: 1.35rem; font-weight: 700; letter-spacing: .08em; color: #e8f1ff; line-height: 1.2; }
.pg-brand b { color: #22d3ee; text-shadow: 0 0 14px rgba(34,211,238,.7); }
.pg-status { display: inline-flex; align-items: center; gap: .45rem; margin-top: .25rem;
  font: 600 .68rem/1 ui-monospace, Consolas, monospace; letter-spacing: .12em; color: #7dd3fc;
  text-transform: uppercase; }
.pg-dot { width: .5rem; height: .5rem; border-radius: 50%; background: #34d399;
  box-shadow: 0 0 0 0 rgba(52,211,153,.6); animation: pg-pulse 2s infinite; }
@keyframes pg-pulse { 0% { box-shadow: 0 0 0 0 rgba(52,211,153,.55); }
  70% { box-shadow: 0 0 0 .5rem rgba(52,211,153,0); } 100% { box-shadow: 0 0 0 0 rgba(52,211,153,0); } }
.pg-h { font: 700 .72rem/1 ui-monospace, Consolas, monospace; letter-spacing: .16em;
  text-transform: uppercase; color: #7f8fb3; margin: .15rem 0 .35rem; }
.pg-h b { color: #22d3ee; }

/* ---- KPI tiles ---- */
.pg-kpis { display: grid; grid-template-columns: 1.5fr 1fr 1fr 1fr; gap: .75rem; }
.pg-tile { position: relative; overflow: hidden; padding: .9rem 1rem; border-radius: .7rem;
  background: linear-gradient(160deg, rgba(20,30,52,.9), rgba(10,16,30,.9));
  border: 1px solid #1d2a44; animation: pg-in .45s ease-out both; min-width: 0; }
.pg-tile::after { content: ""; position: absolute; inset: 0 0 auto 0; height: 2px;
  background: linear-gradient(90deg, transparent, var(--c, #22d3ee), transparent); opacity: .8; }
.pg-tile:nth-child(2) { animation-delay: .05s; } .pg-tile:nth-child(3) { animation-delay: .1s; }
.pg-tile:nth-child(4) { animation-delay: .15s; }
@keyframes pg-in { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
.pg-label { font: 700 .66rem/1 ui-monospace, Consolas, monospace; letter-spacing: .16em;
  color: #7f8fb3; text-transform: uppercase; }
.pg-num { font: 700 1.9rem/1.1 ui-monospace, Consolas, monospace; color: #e8f1ff; margin: .35rem 0 .2rem; }
.pg-sub { font-size: .78rem; color: #9fb0d4; line-height: 1.35; display: -webkit-box;
  -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.pg-score { display: flex; gap: 1rem; align-items: center; }
/* score ring: SVG stroke that draws in (no @property, so it animates in every browser).
   Note: never put angle brackets in this CSS; the HTML sanitizer drops the whole block. */
.pg-ring { position: relative; flex: none; width: 5.2rem; height: 5.2rem; }
.pg-ring svg { width: 100%; height: 100%; transform: rotate(-90deg);
  filter: drop-shadow(0 0 6px var(--c)); }
.pg-ring circle { fill: none; stroke-width: 3.2; }
.pg-ring .bg { stroke: #18233b; }
.pg-ring .fg { stroke: var(--c); stroke-linecap: round; animation: pg-draw 1s cubic-bezier(.2,.8,.2,1) both; }
@keyframes pg-draw { from { stroke-dasharray: 0 100; } }
.pg-ring span { position: absolute; inset: 0; display: grid; place-items: center;
  font: 800 1.35rem/1 ui-monospace, Consolas, monospace; color: #fff; }
.pg-level { font: 800 1.25rem/1.1 ui-monospace, Consolas, monospace; letter-spacing: .06em;
  color: var(--c); text-transform: uppercase; text-shadow: 0 0 12px color-mix(in srgb, var(--c) 60%, transparent);
  margin: .3rem 0 .25rem; }
.pg-bar { height: .35rem; border-radius: 1rem; background: #18233b; overflow: hidden; margin-top: .45rem; }
.pg-bar i { display: block; height: 100%; width: var(--w); border-radius: 1rem;
  background: linear-gradient(90deg, #22d3ee, #8b5cf6); box-shadow: 0 0 10px rgba(34,211,238,.6);
  animation: pg-grow .8s ease-out both; }
@keyframes pg-grow { from { width: 0; } }
@media (max-width: 900px) { .pg-kpis { grid-template-columns: repeat(3, 1fr); }
  .pg-kpis .pg-score { grid-column: 1 / -1; } }
@media (max-width: 480px) { .pg-num { font-size: 1.4rem; } .pg-tile { padding: .75rem; } }

/* ---- panels ---- */
.st-key-panel_findings, .st-key-panel_inspect, .st-key-panel_export, .st-key-console {
  background: rgba(10,16,30,.72); -webkit-backdrop-filter: blur(6px); backdrop-filter: blur(6px);
  border-color: #1d2a44 !important; }
.st-key-panel_inspect { box-shadow: 0 0 0 1px rgba(34,211,238,.08), 0 0 32px rgba(34,211,238,.06); }
.st-key-console { box-shadow: 0 0 0 1px rgba(34,211,238,.15), 0 0 48px rgba(34,211,238,.10); }

/* ---- findings list rows ---- */
.st-key-findings_list button { justify-content: flex-start; text-align: left; width: 100%;
  border: 1px solid #1d2a44; border-left: 3px solid var(--c, #22d3ee); background: rgba(13,20,36,.85);
  transition: transform .15s ease, box-shadow .15s ease, border-color .15s ease, background .15s ease; }
.st-key-findings_list button:hover { transform: translateX(3px); border-color: rgba(34,211,238,.6);
  box-shadow: 0 0 16px rgba(34,211,238,.18); }
.st-key-findings_list button:active { transform: translateX(1px) scale(.99); }
.st-key-findings_list button > div { justify-content: flex-start; width: 100%; }
.st-key-findings_list button p { text-align: left; }
.st-key-findings_list button code { background: transparent; color: #7dd3fc; }
/* scrolling window: shrinks to fit short lists, scrolls when long */
.st-key-findings_list { gap: .45rem; max-height: 420px; overflow-y: auto; overscroll-behavior: contain;
  padding: 2px 6px 2px 2px; scrollbar-width: thin; scrollbar-color: #1f3b57 transparent; }
.st-key-findings_list::-webkit-scrollbar { width: 6px; }
.st-key-findings_list::-webkit-scrollbar-thumb { background: #1f3b57; border-radius: 6px; }
.st-key-findings_list::-webkit-scrollbar-thumb:hover { background: #22d3ee; }
@media (max-width: 640px) { .st-key-findings_list { max-height: 340px; } }

/* inspector first when the two columns stack on narrow screens */
@media (max-width: 640px) { [data-testid="stColumn"]:has(.st-key-panel_inspect) { order: -1; } }

/* ---- inspector ---- */
.pg-insp { display: flex; align-items: center; gap: .6rem; flex-wrap: wrap; }
.pg-chip { font: 800 .72rem/1 ui-monospace, Consolas, monospace; letter-spacing: .1em; padding: .35rem .55rem;
  border-radius: .4rem; color: #060a13; background: var(--c); box-shadow: 0 0 14px color-mix(in srgb, var(--c) 55%, transparent); }
.pg-cat { font: 700 1.15rem/1.2 ui-monospace, Consolas, monospace; color: #e8f1ff; }
.pg-val { font: 600 .95rem/1 ui-monospace, Consolas, monospace; color: #7dd3fc; padding: .3rem .5rem;
  border: 1px dashed #2a3b5e; border-radius: .4rem; }
.pg-hero { padding: 2.2rem 0 1.2rem; }
.pg-hero .t { font: 800 clamp(1.7rem, 5vw, 2.8rem)/1.1 ui-monospace, Consolas, monospace; color: #e8f1ff; }
.pg-hero .t b { color: #22d3ee; text-shadow: 0 0 22px rgba(34,211,238,.6); }
.pg-hero p { color: #9fb0d4; max-width: 38rem; margin: .7rem 0 0; }
.pg-cursor { color: #22d3ee; animation: pg-blink 1.1s steps(1) infinite; }
@keyframes pg-blink { 50% { opacity: 0; } }
.pg-feats { display: flex; gap: .5rem; flex-wrap: wrap; margin-top: .9rem; }
.pg-feats span { font: 600 .7rem/1 ui-monospace, Consolas, monospace; letter-spacing: .08em; color: #7dd3fc;
  border: 1px solid #1d3550; background: rgba(34,211,238,.06); padding: .4rem .6rem; border-radius: 2rem; }

/* ---- buttons ---- */
[data-testid="stBaseButton-primary"] { color: #041018 !important; font-weight: 700;
  box-shadow: 0 0 16px rgba(34,211,238,.35); transition: box-shadow .15s ease, transform .15s ease; }
[data-testid="stBaseButton-primary"]:hover:not(:disabled) { box-shadow: 0 0 26px rgba(34,211,238,.65);
  transform: translateY(-1px); }
[data-testid="stBaseButton-secondary"] { transition: border-color .15s ease, box-shadow .15s ease; }
[data-testid="stBaseButton-secondary"]:hover:not(:disabled) { box-shadow: 0 0 14px rgba(34,211,238,.2); }

@media (prefers-reduced-motion: reduce) {
  .stApp *, .stApp *::after { animation: none !important; transition: none !important; }
}
</style>"""
st.html(CSS)


def esc(s) -> str:
    return html.escape(str(s))


def pretty(category: str) -> str:
    return category.upper() if category in ACRONYMS else category.replace("_", " ").capitalize()


def css_key(fid: str) -> str:
    return "row_" + re.sub(r"\W", "_", str(fid))


def find(fid):
    return next((f for f in st.session_state.report.findings if f.id == fid), None)


# ---------- session handling (DR-1) ----------
def wipe_session(msg=None, toast=False):
    pipe.wipe(st.session_state.get("job"))
    for k in ("job", "report", "saved_copy", "filename", "active_id"):
        st.session_state.pop(k, None)
    if msg:
        st.session_state["toast" if toast else "notice"] = (
            (msg, ":material/delete_sweep:") if toast else ("info", msg))


now = time.time()
if "report" in st.session_state and now - st.session_state.get("last_active", now) > IDLE_LIMIT:
    wipe_session("Session cleared after 15 minutes of inactivity. Scan data was wiped.")
st.session_state["last_active"] = now


# ---------- callbacks (run before the rerun, so each click redraws once) ----------
def run_scan():
    content, fname = st.session_state.get("msg", ""), None
    upload = st.session_state.get("upload")
    if upload is not None:
        if upload.size > MAX_BYTES:
            st.session_state["notice"] = ("error", "That file is over 10 MB.")
            return
        content, fname = upload.getvalue().decode("utf-8", errors="replace"), upload.name
    if not content.strip():
        st.session_state["notice"] = ("warning", "Add a message or a file first.")
        return
    wipe_session()
    st.session_state.report, st.session_state.job = pipe.run_scan(
        content, st.session_state.recipient, fname)
    st.session_state.filename = fname
    n = len(st.session_state.report.findings)
    st.session_state["toast"] = (f"Scan complete: {n} finding{'s' * (n != 1)}", ":material/radar:")


def select(fid):
    st.session_state.active_id = fid


def set_decision(fid, value=None, from_key=None):
    f = find(fid)
    f.decision = st.session_state[from_key] if from_key else value
    st.session_state.pop("saved_copy", None)  # an earlier copy no longer matches the choices
    if f.decision == "pending":
        return
    st.session_state["toast"] = (
        ("Ignored, kept as is", ":material/block:") if f.decision == "Keep"
        else (f"{f.decision} approved for {pretty(f.category)}", DONE_ICON))
    findings = st.session_state.report.findings  # jump to the next pending item
    i = findings.index(f)
    nxt = next((x for x in findings[i + 1:] + findings[:i] if x.decision == "pending"), None)
    if nxt:
        st.session_state.active_id = nxt.id


def scan_inputs():
    st.selectbox("Who are you sharing this with?", RECIPIENTS, index=2, key="recipient",
                 help="Sets the exposure factor used in the risk score (FR-4).")
    tab_text, tab_file = st.tabs([":material/chat: Message", ":material/upload_file: File"])
    with tab_text:
        st.text_area("Type or paste a message", height=150, key="msg",
                     placeholder="Paste an email, chat message or note…")
    with tab_file:
        st.file_uploader("Upload .txt, .md or .csv (under 10 MB)", type=["txt", "md", "csv"],
                         key="upload")
        st.caption("If a file is added it is scanned instead of the message. "
                   ".docx and .pdf support comes from the Input Handler (FR-1).")
    st.button("Scan", type="primary", icon=":material/radar:", width="stretch", on_click=run_scan)


@st.dialog("Before and after", width="large", icon=":material/compare_arrows:")
def preview_dialog():
    approved = [f for f in st.session_state.report.findings
                if f.decision not in ("pending", "Keep")]
    st.caption("Sensitive values stay masked on screen. Your original is never edited.")
    st.dataframe(pipe.preview_changes(st.session_state.job, approved), width="stretch",
                 hide_index=True)
    if st.button("Confirm and create new copy", type="primary", icon=":material/content_copy:"):
        st.session_state.saved_copy = pipe.apply_all(st.session_state.job, approved)
    if "saved_copy" in st.session_state:
        name = st.session_state.get("filename") or "message.txt"
        st.success("New copy created. The original was not changed.")
        st.download_button("Download new copy", st.session_state.saved_copy,
                           file_name=f"privacyguard_{name}", mime="text/plain",
                           icon=":material/download:", on_click="ignore")


# ---------- top bar ----------
report = st.session_state.get("report")
bar = st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute")
bar.markdown(
    "<div class='pg-brand'>◆ PRIVACY<b>GUARD</b>_AI</div>"
    f"<div class='pg-status'><span class='pg-dot'></span>On-device · nothing sent · "
    f"{esc(pipe.MODE)} pipeline</div>", unsafe_allow_html=True)
if report is not None:
    tools = bar.container(horizontal=True, width="content", vertical_alignment="center")
    with tools.popover("New scan", icon=":material/add:"):
        scan_inputs()
    tools.button("Wipe", icon=":material/delete_sweep:", help="Clear scan data now",
                 on_click=wipe_session, args=("Scan data wiped", True))

if n := st.session_state.pop("notice", None):
    getattr(st, n[0])(n[1])
if t := st.session_state.pop("toast", None):
    st.toast(t[0], icon=t[1])

# ---------- empty state: scan console ----------
if report is None:
    _, mid, _ = st.columns([1, 2.2, 1])
    with mid:
        st.markdown(
            "<div class='pg-hero'><div class='pg-h'>// <b>scan</b> before you send</div>"
            "<div class='t'>Check it for <b>private data</b><span class='pg-cursor'>_</span></div>"
            "<p>Paste a message or add a file. PrivacyGuard flags sensitive data, scores the risk "
            "and suggests fixes. Nothing changes unless you approve it.</p>"
            "<div class='pg-feats'><span>⬢ Runs locally</span><span>⬢ Values masked on screen"
            "</span><span>⬢ You approve every fix</span></div></div>", unsafe_allow_html=True)
        with st.container(border=True, key="console"):
            scan_inputs()
    st.stop()


# ---------- KPI tiles (FR-7 score + verdict, FR-6 compliance flags at the top) ----------
findings = report.findings
pending = [f for f in findings if f.decision == "pending"]
reviewed = len(findings) - len(pending)
color = LEVEL_COLOR[report.level]
counts = {lv: sum(level_for(f.score) == lv for f in findings) for lv in LEVELS}
breakdown = " · ".join(f"{counts[lv]} {lv.lower()}" for lv in reversed(LEVELS) if counts[lv])
flags = ", ".join(w.name for w in report.warnings) or "None for this scan"
pct = round(min(report.overall / 10, 1) * 100)
done_pct = round(reviewed / len(findings) * 100) if findings else 100
st.markdown(f"""<div class="pg-kpis">
<div class="pg-tile pg-score" style="--c:{color}">
  <div class="pg-ring"><svg viewBox="0 0 36 36" aria-hidden="true">
    <circle class="bg" cx="18" cy="18" r="15.9155"/>
    <circle class="fg" cx="18" cy="18" r="15.9155" pathLength="100" stroke-dasharray="{pct} 100"/>
  </svg><span>{report.overall:.1f}</span></div>
  <div style="min-width:0"><div class="pg-label">Risk score / 10</div>
  <div class="pg-level">{esc(report.level)}</div><div class="pg-sub">{esc(report.verdict)}</div></div>
</div>
<div class="pg-tile"><div class="pg-label">Findings</div><div class="pg-num">{len(findings)}</div>
  <div class="pg-sub">{esc(breakdown) or "Nothing sensitive found"}</div></div>
<div class="pg-tile"><div class="pg-label">Reviewed</div><div class="pg-num">{reviewed}/{len(findings)}</div>
  <div class="pg-bar"><i style="--w:{done_pct}%"></i></div></div>
<div class="pg-tile" style="--c:#facc15"><div class="pg-label">Compliance flags</div>
  <div class="pg-num">{len(report.warnings)}</div><div class="pg-sub">{esc(flags)}</div></div>
</div>""", unsafe_allow_html=True)
st.write("")

# per-row accent colours + highlight for the selected row
active = find(st.session_state.get("active_id")) or (pending or findings or [None])[0]
row_css = "".join(f".st-key-{css_key(f.id)} button{{--c:{LEVEL_COLOR[level_for(f.score)]}}}"
                  for f in findings)
if active is not None:
    row_css += (f".st-key-{css_key(active.id)} button{{background:rgba(34,211,238,.10);"
                "border-color:rgba(34,211,238,.75);box-shadow:0 0 0 1px rgba(34,211,238,.45),"
                "0 0 20px rgba(34,211,238,.22)}")
st.html(f"<style>{row_css}</style>")

left, right = st.columns([1.05, 1], gap="medium")

# ---------- findings list (scrolling window) ----------
with left, st.container(border=True, key="panel_findings"):
    head = st.container(horizontal=True, vertical_alignment="center",
                        horizontal_alignment="distribute")
    head.markdown(f"<div class='pg-h'>// <b>findings</b> · {len(pending)} pending</div>",
                  unsafe_allow_html=True)
    only_pending = head.toggle("Pending only", value=False)
    present = [lv for lv in LEVELS if counts[lv]]
    shown = st.pills("Show levels", present, selection_mode="multi", default=present,
                     format_func=lambda lv: f"{lv} ({counts[lv]})", label_visibility="collapsed")
    rows = [f for f in findings
            if (not only_pending or f.decision == "pending") and level_for(f.score) in shown]
    with st.container(border=False, key="findings_list"):
        if not findings:
            st.success("No sensitive items found.", icon=":material/verified_user:")
        elif not rows:
            st.caption("No findings match these filters.")
        for f in rows:
            st.button(f"**{f.score:.1f}** · {pretty(f.category)} · `{f.masked_value}`",
                      key=css_key(f.id), width="stretch",
                      icon=STATUS_ICON.get(f.decision, DONE_ICON), on_click=select, args=(f.id,))
    for c in report.coverage:
        st.caption(f":material/info: Not covered: {c}")

# ---------- inspector for the selected finding (DR-2 Approval Gate) ----------
with right:
    with st.container(border=True, key="panel_inspect"):
        if active is None:
            st.markdown("<div class='pg-h'>// <b>inspector</b></div>", unsafe_allow_html=True)
            st.caption("Nothing to review. This message looks safe to share.")
        else:
            f = active
            idx = findings.index(f)
            nav = st.container(horizontal=True, vertical_alignment="center",
                               horizontal_alignment="distribute")
            nav.markdown(f"<div class='pg-h'>// <b>inspector</b> · {idx + 1} of {len(findings)}"
                         "</div>", unsafe_allow_html=True)
            arrows = nav.container(horizontal=True, width="content", gap="xsmall")
            arrows.button("Prev", key="nav_prev", type="tertiary", icon=":material/chevron_left:",
                          disabled=idx == 0, on_click=select, args=(findings[idx - 1].id,))
            arrows.button("Next", key="nav_next", type="tertiary", icon=":material/chevron_right:",
                          icon_position="right", disabled=idx == len(findings) - 1,
                          on_click=select, args=(findings[min(idx + 1, len(findings) - 1)].id,))
            lv = level_for(f.score)
            st.markdown(
                f"<div class='pg-insp' style='--c:{LEVEL_COLOR[lv]}'>"
                f"<span class='pg-chip'>{esc(lv.upper())} {f.score:.1f}</span>"
                f"<span class='pg-cat'>{esc(pretty(f.category))}</span>"
                f"<span class='pg-val'>{esc(f.masked_value)}</span></div>", unsafe_allow_html=True)
            st.caption(f"**Location:** {f.location} · **Found by:** {f.source}")
            st.write(f.explanation)
            if f.note_source:
                st.caption(f"Source: {f.note_source}")
            for w in report.warnings:
                if f.id in w.finding_ids:
                    st.warning(f"**{w.name}.** {w.note}", icon=":material/policy:")

            acts = st.container(horizontal=True, vertical_alignment="center")
            if f.decision == "pending":
                acts.button(f"Approve: {f.action}", key=f"ap{f.id}", type="primary",
                            icon=":material/check:", on_click=set_decision, args=(f.id, f.action))
                acts.button("Ignore", key=f"ig{f.id}", icon=":material/close:",
                            on_click=set_decision, args=(f.id, "Keep"))
            else:
                acts.badge("Kept as is" if f.decision == "Keep" else f"{f.decision} approved",
                           icon=STATUS_ICON.get(f.decision, DONE_ICON),
                           color="gray" if f.decision == "Keep" else "green")
                acts.button("Undo", key=f"un{f.id}", icon=":material/undo:",
                            on_click=set_decision, args=(f.id, "pending"))
            with acts.popover("Why?", icon=":material/help:"):  # detector + score maths
                st.write(f"**Detector:** {f.source}" +
                         (f"  \n**Model reason:** {f.reason}" if f.reason else ""))
                if f.source == "combination":
                    st.write("Score from the quasi-identifier group rule (+1.5 per extra "
                             "identifier, known risky pairs at least 7).")
                else:
                    raw = f.sensitivity * f.confidence * f.exposure
                    st.code(f"score = sensitivity × confidence × exposure\n"
                            f"      = {f.sensitivity:g} × {f.confidence:.2f} × {f.exposure:g}"
                            f" = {raw:.2f}\n      capped at 10 → {f.score:.1f}", language=None)
            if f.decision == "pending":
                other = st.container(horizontal=True, vertical_alignment="bottom")
                other.selectbox("Or pick a different fix", ACTIONS, index=ACTIONS.index(f.action),
                                key=f"sel{f.id}", width=200)
                other.button("Use this instead", key=f"ch{f.id}", on_click=set_decision,
                             args=(f.id, None, f"sel{f.id}"))

    # ---------- finish: preview (dialog), confirm, save as new copy, export ----------
    approved = [f for f in findings if f.decision not in ("pending", "Keep")]
    md = [f"# PrivacyGuard report\n\nOverall: {report.overall}/10 ({report.level}). "
          f"{report.verdict}\n"]
    md += [f"- ⚠️ {w.name}: {w.note}" for w in report.warnings]
    md += [f"\n- **{f.category}** `{f.masked_value}` ({f.location}), score {f.score}, "
           f"suggested {f.action}, decision: {f.decision}" for f in findings]
    md += [f"\nNot covered: {c}" for c in report.coverage]
    with st.container(border=True, key="panel_export"):
        st.markdown(f"<div class='pg-h'>// <b>export</b> · {len(approved)} fix"
                    f"{'es' * (len(approved) != 1)} approved</div>", unsafe_allow_html=True)
        ex = st.container(horizontal=True)
        if ex.button("Done: preview changes", type="primary", icon=":material/compare_arrows:",
                     disabled=not approved,
                     help=None if approved else "Approve at least one fix first."):
            preview_dialog()
        ex.download_button("Masked report (.md)", "\n".join(md), file_name="privacyguard_report.md",
                           mime="text/markdown", icon=":material/description:", on_click="ignore")
