PrivacyGuard AI

**A local-first privacy agent that scans text for sensitive information, scores the risk, and helps you fix it before you share it.**

PrivacyGuard AI was built for COMP 422 (AI agents). You paste a message or upload a file, say who you're sharing it with, and the agent finds personal details, explains why each one is risky, and suggests a fix. You stay in control: nothing changes until you approve it, and your original text is never modified.

## Features

- **Hybrid detection.** Regex rules with validators (Luhn check for cards, SSN and IPv4 validation, keyword proximity) catch structured data. A local LLM catches context-dependent details like names, health conditions, and student records.
- **Recipient-aware risk scoring.** The same text is riskier on a public post than in a message to a friend. Scores run 0 to 10 and map to Low, Medium, High, or Critical.
- **Combination detection.** Details that look harmless alone (name + birth date, name + address) are flagged when they appear together.
- **Compliance warnings.** Flags content that usually needs consent or legal review, such as health information, minors' data, student records, and GDPR special categories. This is not legal advice.
- **Human approval gate.** For every finding you can approve the suggested fix, pick a different one, ignore it, or ask "Why?" to see the detector and score math.
- **Before/after preview.** See exactly what will change, with sensitive values masked, before saving anything.
- **Private by design.** Everything runs on your machine, raw values stay in memory only, and the session is wiped when you finish or after 15 minutes idle.

## How it works

Each scan runs through a fixed pipeline (`privacyguard/pipeline.py`):

```
Pattern Detector → Context Analyzer → Risk Scorer → Recommendation Engine → Compliance Checker → Report
```

| Stage | Module | What it does |
|---|---|---|
| Pattern Detector | `privacyguard/rules.py` | Regex + validators for SSNs, card numbers, emails, phone numbers, birth dates, passwords, and IP addresses |
| Context Analyzer | `privacyguard/context.py` | Optional spaCy NER picks candidate sentences; a local LLM judges whether each detail is identifiable and sensitive |
| Risk Scorer | `privacyguard/scoring.py` | Fixed formulas (no AI): item, combination, and overall scores |
| Recommendation Engine | `privacyguard/recommend.py` | Rules choose the fix; a template writes the plain-language explanation |
| Compliance Checker | `privacyguard/compliance.py` | Flags categories that usually need consent or legal review |
| Local model client | `privacyguard/llm.py` | Talks to Ollama on localhost |

**Detected categories**

- *Pattern rules:* SSN, credit card, email, phone, birth date, password, IP address
- *LLM context check:* name, health, financial, address, minor, student record, bank, religion, sexual orientation, political, ethnicity, employer, job title

**Scoring**

- Item score = `min(10, sensitivity × confidence × exposure)`
- Recipient exposure factors: Private (friend or family) 0.8, Unknown 1.0, AI tool 1.2, Public 1.5
- Risk levels: Low (under 3), Medium (3 to 6), High (6 to 8), Critical (8+)

**Available fixes:** Redact, Mask, Generalize, Pseudonymize, Remove, Keep. SSNs, card numbers, bank details, and passwords are always recommended for redaction.

### Safety choices for the AI step

- The model runs locally through Ollama; no text leaves your machine.
- Temperature is 0 and replies are forced into a JSON schema.
- Each sentence is passed to the model as untrusted data, so instructions hidden in a document are not followed.
- If Ollama isn't running, the scan still works with pattern rules only, and the report says the AI context check was unavailable.

## Getting started

### Option 1: Docker (includes the local model)

```bash
git clone https://github.com/jboyce05/PrivacyGuard-AI-Agent.git
cd PrivacyGuard-AI-Agent
docker compose up --build
```

Then open <http://localhost:8501>. The first run downloads the `llama3.2` model, so it can take a few minutes before the dashboard starts. The dashboard is bound to `127.0.0.1`, so it is only reachable from your own machine.

### Option 2: Run locally

Requires Python 3.11 or newer.

```bash
git clone https://github.com/jboyce05/PrivacyGuard-AI-Agent.git
cd PrivacyGuard-AI-Agent
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

**Optional: enable the AI context check**

1. Install [Ollama](https://ollama.com) and run `ollama pull llama3.2`.
2. Keep Ollama running while you use the dashboard.

**Optional: better sentence selection with spaCy**

```bash
pip install spacy
python -m spacy download en_core_web_sm
```

### Configuration

| Variable | Default | Purpose |
|---|---|---|
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Where the local model server is running |
| `PRIVACYGUARD_MODEL` | `llama3.2` | Which Ollama model to use |

## Using the dashboard

1. Choose who you're sharing the text with.
2. Paste a message or upload a `.txt`, `.md`, or `.csv` file (under 10 MB).
3. Review the overall score, compliance warnings, and the list of findings.
4. For each finding, approve the suggested fix, pick another, ignore it, or open **Why?** to see how it was detected and scored.
5. Open the before/after preview, then save the result as a **new copy**. You can also download a masked report as Markdown.
6. Finish the session to wipe all scan data from memory.

## Testing

```bash
pytest tests
```

Unit tests never call Ollama; the test setup stubs out the model, so they run without any extra services.

## Project structure

```
├── app.py                 # Streamlit dashboard
├── models.py              # Finding, Warning, Report data classes
├── pipeline_adapter.py    # Switches between the real pipeline and the demo one
├── demo_pipeline.py       # Regex-only stand-in pipeline
├── privacyguard/          # Scan pipeline (rules, context, scoring, recommend, compliance, llm)
├── tests/                 # pytest suite
├── .streamlit/config.toml # Dark theme, 10 MB upload limit, telemetry off
├── Dockerfile
└── compose.yaml           # Dashboard + Ollama + one-time model download
```

`pipeline_adapter.py` is the single seam between the dashboard and the pipeline. If `privacyguard.pipeline` imports cleanly the dashboard runs in **live** mode; otherwise it falls back to **demo** mode.

## Limitations

- Only plain text is read from uploads (`.txt`, `.md`, `.csv`).
- The AI context check analyzes up to 60 sentences per scan and uses a small 3B-parameter model, so it can miss details or misjudge context. Treat results as a strong first pass, not a guarantee.
- Compliance warnings are prompts for review, not legal advice.


