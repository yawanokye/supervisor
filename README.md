# ProjectReady AI Supervisor Assistant MVP 1.0

ProjectReady AI Supervisor Assistant provides Light, Standard and Advanced academic review of thesis and dissertation chapters, research proposals, revised chapters and complete theses.

## Review philosophy

The official thesis self-evaluation checklist is used internally as a coverage guide. It is not presented to the student as the review, and its item numbers are not shown in the dashboard, annotated document or Word report.

All three review levels examine every detected section and subsection. The difference is the academic benchmark and degree of critical scrutiny, not the amount of the document covered.

The review covers, where relevant:

- title accuracy, focus and scope
- chapter structure, progression and coherence
- conceptual and theoretical grounding
- empirical evidence, source quality and critical synthesis
- research problem, gap, purpose, objectives, questions and hypotheses
- methodological rigour and justification
- results, interpretation, discussion, conclusions and recommendations
- cross-chapter alignment
- citation and source risks
- academic writing, terminology, grammar and presentation
- supervisor-comment compliance for revised chapters

## Review levels

### Light Review

- Reviews every section and subsection.
- Applies the standard expected of a Bachelor’s dissertation or non-research Master’s project.
- Focuses on correct structure, basic coherence, clear concepts, credible evidence, alignment, essential methodology, defensible interpretation, common research flaws, source-verification concerns and scholarly presentation.
- Uses GPT-5.4 mini.
- Provides practical, topic-aware guidance and short examples where these will help the student.

### Standard Review

- Reviews every section and subsection.
- Applies the standard expected of a Research Master’s or MPhil dissertation.
- Requires stronger critical synthesis, defensible theoretical grounding, explicit methodological justification, objective-method-result alignment and a clear research contribution.
- Uses GPT-5.4 mini for the section review and GPT-5.4 for quality control.

### Advanced Review

- Reviews every section and subsection.
- Applies the standard expected of a Professional Doctorate or PhD thesis.
- Examines originality, theoretical and methodological contribution, assumptions, robustness, alternative explanations, scholarly positioning and contribution to knowledge.
- Uses GPT-5.4 for the main review and GPT-5.5 for the advanced audit.

Python extracts the document, validates paragraph evidence, checks review coverage, scores the review and produces the annotated Word file.

## Coverage safeguard

The app requires one substantive assessment for every detected section and subsection. Short or apparently adequate sections cannot be silently omitted. Missing section reviews are retried individually. The job fails rather than exporting a report when any section remains unreviewed.

## Annotated Word output

- Existing text requiring revision is coloured red.
- A specific supervisor comment is inserted immediately afterwards in green square brackets.
- Related successive comments are consolidated as one numbered note.
- Missing content receives a green bracketed instruction beneath the relevant heading.
- Internal checklist codes are never displayed.

## Human-supervisor report

The Word report presents:

1. overall supervisor assessment
2. strengths to retain
3. priority corrections before resubmission
4. an assessment of every section and subsection
5. detailed review points only where revision is needed
6. cross-chapter alignment, where applicable
7. response to earlier supervisor comments, where applicable
8. final guidance

Examples are illustrative and must be adapted to the actual study and verified evidence.

## Model routing

- Light Review: GPT-5.4 mini
- Standard Review: GPT-5.4 mini plus GPT-5.4 quality control
- Advanced Review: GPT-5.4 plus GPT-5.5 advanced audit
- DeepSeek is disabled and no DeepSeek key is required.
- Review requests run as background jobs and the browser polls for progress.

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

The in-memory job store is suitable for one Render instance. Before horizontal scaling, replace it with Redis and a worker queue.
