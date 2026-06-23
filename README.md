# ProjectReady AI Supervisor Assistant MVP 0.9

ProjectReady AI Supervisor Assistant provides Light, Standard and Advanced review of thesis chapters, research proposals, revised chapters, and complete theses.

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

## Review levels

- **Light Review:** GPT-5.4 mini performs one concise pass. It identifies common research flaws, obvious alignment problems, unsupported claims, recurring writing issues, and source or research-integrity warning signs that require verification. It is not a forensic misconduct assessment and does not replace a complete academic review.
- **Standard Review:** GPT-5.4 mini performs the section review, then GPT-5.4 checks important findings and omissions.
- **Advanced Review:** GPT-5.4 performs the main review, then GPT-5.5 conducts the advanced audit. GPT-5.5 is called only when Advanced Review is selected.
- Python extracts the document, validates paragraph evidence, scores the review, and produces the annotated Word file.

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


## Version 0.9 model routing

- Light Review: GPT-5.4 mini only, larger section batches, no second-model verification, and a concise report capped at the most useful findings.
- Standard Review: GPT-5.4 mini plus GPT-5.4 quality control.
- Advanced Review: GPT-5.4 plus GPT-5.5 advanced audit.
- DeepSeek is disabled and no DeepSeek key is required.
- Review requests run as background jobs and the browser polls for progress.

The in-memory job store is suitable for one Render instance. Before horizontal scaling, replace it with Redis and a worker queue.
## Report and annotation improvements

- Produces a concise human-supervisor report instead of repeating the same findings in tables and narrative sections.
- Consolidates related findings that point to the same passage.
- Uses topic-specific assessments and actions based on the study context.
- Includes short illustrative guidance where it helps the student act on the comment, without inventing evidence or citations.
- Groups successive annotations as one numbered green note, for example `[Supervisor comments: 1. ...; 2. ...]`.
- Removes repetitive internal wording such as “retain this finding” from student-facing comments.

