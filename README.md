# ProjectReady AI Supervisor Assistant MVP

This is the first working foundation for a thesis-review application covering Chapters One to Five and full-thesis readiness.

## What this MVP does

- Accepts DOCX and text-based PDF files
- Reviews any single chapter independently
- Reviews a complete thesis
- Supports quantitative, qualitative, mixed-methods, SEM, and econometric studies
- Applies the full thesis self-evaluation rule bank
- Produces five review statuses
- Shows extracted page and paragraph evidence where available
- Generates expert-style comments and revision actions
- Applies critical submission gates
- Exports a Word review report
- Produces a colour-annotated copy of an uploaded DOCX
- Colours only the sentence requiring revision in red
- Inserts the required supervisor comment immediately after it in green square brackets
- Inserts green square-bracketed guidance below a section heading when required content is missing

## Run locally

```bash
python -m venv .venv
```

Activate the environment, then:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

## Deploy on Render

The included `render.yaml` can create a Render web service. The start command is:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## Important MVP limitations

1. DOCX does not contain stable page numbers. Use PDF when exact page evidence is the priority, and DOCX when an editable colour-annotated review copy is required. Paragraph numbers are reported, while PDF provides both page and paragraph locations.
2. Scanned PDFs are not supported because OCR is deliberately excluded from the first build.
3. Rule-based matching can identify evidence and omissions but cannot fully judge originality, conceptual depth, or factual accuracy.
4. The in-memory review cache must be replaced with Redis or a database before multiple-instance commercial deployment.
5. Citation verification should later be connected to CiteIntegrity rather than duplicated here.
6. The next development stage should add an evidence-constrained AI reviewer for nuanced adequacy judgements and cross-chapter mapping.

## Recommended next build

- Objective-to-question mapping
- Objective-to-method mapping
- Objective-to-results mapping
- Finding-to-conclusion mapping
- Finding-to-recommendation mapping
- Previous-versus-revised chapter comparison
- Institutional checklist upload
- User accounts, review history, payments, and database storage
