# ProjectReady AI Supervisor Assistant MVP 0.7

ProjectReady AI Supervisor Assistant conducts a complete academic review of thesis chapters, research proposals, revised chapters, and complete theses.

## Review philosophy

The official thesis self-evaluation checklist is used internally as a coverage guide. It is not presented to the student as the review and its item numbers are not shown in the dashboard, annotated document, or Word report.

The main review is a section-by-section academic assessment covering:

- title accuracy, focus, and scope
- chapter structure, progression, and coherence
- conceptual and theoretical grounding
- empirical evidence, source quality, and critical synthesis
- research problem, gap, purpose, objectives, questions, and hypotheses
- methodological rigour and justification
- results, interpretation, discussion, conclusions, and recommendations
- cross-chapter alignment
- citation and source risks
- academic writing, terminology, grammar, and presentation
- supervisor-comment compliance for revised chapters

## Model routing

- DeepSeek performs the primary section-by-section academic review where configured.
- OpenAI independently verifies high-impact and uncertain findings where configured.
- Python extracts the document, validates paragraph evidence, scores the review, and produces the annotated Word file.
- The app does not silently present a local keyword scan as a complete expert review. At least one AI review provider must be configured.

## Annotated Word output

- Existing text requiring revision is coloured red.
- A specific supervisor comment is inserted immediately afterwards in green square brackets.
- Missing content receives a green bracketed instruction beneath the relevant heading.
- Internal checklist codes are never displayed.

## Run locally

```bash
python -m venv .venv
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Render commands

Build command:

```bash
python -m pip install -r requirements.txt
```

Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Health check:

```text
/health
```

Python is pinned to 3.12.11 through `.python-version` and `render.yaml`.


## Provider failover

The academic-review layer retries empty or schema-invalid DeepSeek JSON and automatically sends only unresolved sections to OpenAI when both providers are configured. Exact provider errors are recorded in the Render logs.


## Version 0.7 model routing

- Standard Review: GPT-5.4 mini performs batched section review, then GPT-5.4 checks the findings and identifies important omissions.
- Advanced Review: GPT-5.4 performs the main review, then GPT-5.5 conducts the advanced audit. GPT-5.5 is never called unless Advanced Review is selected.
- DeepSeek is disabled and no DeepSeek key is required.
- Review requests run as background jobs and the browser polls for progress. This avoids long HTTP requests and HTML timeout pages being parsed as JSON.

The in-memory job store is suitable for one Render instance. Before horizontal scaling, replace it with Redis and a worker queue.
