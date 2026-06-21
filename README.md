# ProjectReady AI Supervisor Assistant MVP 0.5

This build combines a deterministic thesis-checklist engine with cost-efficient DeepSeek review and selective OpenAI quality control.

## Hybrid review flow

1. Python extracts DOCX/PDF text, headings, pages, paragraphs, supervisor comments, and previous chapters.
2. The local engine applies all 109 official checklist criteria and identifies candidate evidence.
3. `deepseek-v4-flash` creates a compact thesis map from the most relevant passages.
4. `deepseek-v4-pro` performs the main expert review of critical, incomplete, uncertain, alignment, and revision items.
5. `gpt-5.4` independently verifies only critical, low-confidence, manual, and disputed decisions.
6. In Premium mode, `gpt-5.5` adjudicates remaining disagreements.
7. Python validates every paragraph ID, recalculates readiness, and generates the annotated DOCX and review report.

The application ignores model reasoning content. Only the structured final decision is used.

## Review modes

- **Automatic routing**: Hybrid when both API keys exist, DeepSeek-only or OpenAI-only when one exists, and local review when neither exists.
- **Cost-efficient hybrid**: DeepSeek primary review plus selective OpenAI verification.
- **DeepSeek only**: Lowest model cost, without OpenAI verification.
- **OpenAI only**: OpenAI reviews all routed criteria.
- **Premium**: DeepSeek primary review, OpenAI verification, and premium adjudication for unresolved disagreements.
- **Local**: Rule-based checklist review without API cost.

## Install and run

```bash
python -m venv .venv
```

Activate the environment, then:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`.

## Render configuration

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Health check:

```text
/health
```

Add the environment variables from `.env.example` in the Render dashboard. At minimum, configure:

```text
DEEPSEEK_API_KEY
OPENAI_API_KEY
```

Never commit real API keys to GitHub.

## Cost controls implemented

- Relevant sections are sent instead of whole documents.
- Checklist items are grouped into small batches.
- DeepSeek Flash is used only for compact document mapping.
- DeepSeek Pro is the default academic reviewer.
- OpenAI receives only escalated decisions in Hybrid mode.
- Evidence IDs are validated against the parsed document.
- API usage and estimated cost are recorded in the review report.
- Provider failures fall back to validated local decisions unless `AI_STRICT_FAILURE=true`.

## Privacy and reliability

- OpenAI requests use `store: false`.
- API keys remain server-side.
- No model can directly edit the Word file.
- Only existing paragraph IDs are accepted as evidence.
- A model cannot mark an item YES without a valid evidence paragraph.
- The final Word annotations are produced by Python, not by the model.

## Production work still required

- Replace in-memory review storage with PostgreSQL and object storage.
- Move long AI reviews to a background queue.
- Add authentication, quotas, billing, and per-user usage limits.
- Add automated evaluation against real supervisor decisions.
- Encrypt uploaded documents at rest and apply a retention policy.
