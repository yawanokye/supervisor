# ProjectReady AI Supervisor Assistant 1.4

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
- Uses DeepSeek V4 Pro in thinking mode.
- Provides practical, topic-aware guidance and short examples where these will help the student.

### Standard Review

- Reviews every section and subsection.
- Applies the standard expected of a Research Master’s or MPhil dissertation.
- Requires stronger critical synthesis, defensible theoretical grounding, explicit methodological justification, objective-method-result alignment and a clear research contribution.
- Uses DeepSeek V4 Pro in thinking mode with a Research Master’s/MPhil review prompt.

### Advanced Review

- Reviews every section and subsection.
- Applies the standard expected of a Professional Doctorate or PhD thesis.
- Examines originality, theoretical and methodological contribution, assumptions, robustness, alternative explanations, scholarly positioning and contribution to knowledge.
- Uses DeepSeek V4 Pro with maximum reasoning and an independent DeepSeek second-pass audit.

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

- Light Review: DeepSeek V4 Pro with high reasoning, calibrated to Bachelor’s and non-research Master’s work.
- Standard Review: DeepSeek V4 Pro with high reasoning, calibrated to Research Master’s and MPhil work.
- Advanced Review: DeepSeek V4 Pro with maximum reasoning and an independent second-pass audit, calibrated to Professional Doctorate and PhD work.
- OpenAI is not required for active review routing.
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

## Institutional administrator and lecturer portals

Version 1.1 adds account-based institutional access.

### Administrator portal

Open:

```text
/admin/login
```

The administrator can:

- create lecturer accounts
- set lecturer name, username, department, email and phone
- generate a temporary password and six-digit recovery PIN
- suspend or reactivate accounts
- reset lecturer login details
- view institutional review activity

The temporary password and recovery PIN are displayed once after account creation or reset. Lecturers must change the temporary password at first login.

### Lecturer portal

Open:

```text
/login
```

Lecturers can:

- submit new chapter, proposal and full-thesis reviews
- review revised chapters against supervisor comments
- view review history and status
- download the supervisor report and annotated document
- change or recover their password

### Required production environment variables

```env
DATABASE_URL=postgresql://...
SESSION_SECRET=use-a-long-random-secret
COOKIE_SECURE=true
ADMIN_USERNAME=admin
ADMIN_PASSWORD=use-a-strong-temporary-password
ADMIN_NAME=System Administrator
ADMIN_EMAIL=
REVIEW_STORAGE_DIR=/var/data/reviews
```

Use a managed PostgreSQL database for lecturer accounts and review metadata. SQLite is suitable only for local development. Attach a persistent Render disk and mount it at `/var/data` when completed review downloads must remain available after redeployment.

The first administrator is created automatically when the database is empty. The administrator must change the temporary password at first login.

## Storage behaviour on Render

The default review-file directory is `/tmp/projectready-supervisor/reviews`.
This keeps the service operational without a disk, but files are temporary.

To retain generated reports across restarts and deploys, attach a Render
persistent disk at `/var/data` and set
`REVIEW_STORAGE_DIR=/var/data/reviews`. If that path is unavailable, the app
falls back safely to `/tmp/projectready-supervisor/reviews`.

## Review-model routing

Provider names remain hidden from supervisors and students.

- **Light Review:** DeepSeek V4 Pro in thinking mode, calibrated to Bachelor’s and non-research Master’s work.
- **Standard Review:** DeepSeek V4 Pro in thinking mode, calibrated to Research Master’s and MPhil work.
- **Advanced Review:** DeepSeek V4 Pro with maximum reasoning and an independent DeepSeek second-pass audit, calibrated to Professional Doctorate and PhD work.

Every level reviews every detected section and subsection. The difference is the academic benchmark, depth of scrutiny, reasoning effort and level of guidance.

The internal academic guide is adapted from the supplied thesis self-evaluation framework. It is used only to support coverage and is never shown as checklist codes in the report.

### Accuracy safeguards

- A study-context lock is built from the uploaded document before review.
- Examples cannot introduce a country, region, organisation, population or sector absent from the source.
- Unknown contextual details use neutral placeholders.
- New author-year citations, statistics and percentages are rejected unless they appear in the uploaded source.
- Repetitive language and citation comments are consolidated.
- Missing content is distinguished from weakly developed content.

## Institutional access interface

The shared access interface has two tabs:

- `/login` opens the Supervisor tab.
- `/admin/login` opens the Admin tab.

The tabs change the active portal and form action without combining the permission systems. Supervisor and administrator authentication remain separately enforced by the backend.
