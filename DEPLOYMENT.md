# V-Professor v2.1.0 Deployment Guide

## Architecture

Deploy three Render resources:

1. PostgreSQL database: `vprofessor-db`
2. Web service: `vprofessor-web`
3. Background worker: `vprofessor-worker`

The included `render.yaml` creates all three and applies one shared environment definition to the web service and worker.

## Commands

Web service:

```text
Build: python -m pip install -r requirements.txt
Start: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Background worker:

```text
Build: python -m pip install -r requirements.txt
Start: python -m app.worker
```

## Required secrets

Set `OPENAI_API_KEY` in Render. Render generates `SESSION_SECRET` and injects `DATABASE_URL` from the PostgreSQL resource when the Blueprint is used.

For a manual deployment, set:

```env
OPENAI_API_KEY=<secret>
SESSION_SECRET=<long-random-secret>
DATABASE_URL=<postgresql-connection-string>
```

The web service and worker must use the same `DATABASE_URL`. The same `SESSION_SECRET` may be shared, although only the web service uses browser sessions.

## Shared job and artifact storage

Keep:

```env
VPROF_DB_ARTIFACT_STORAGE=true
VPROF_RUN_JOBS_IN_WEB=false
REVIEW_STORAGE_DIR=/tmp/vprofessor/reviews
REVIEW_STORAGE_FALLBACK_DIR=/tmp/vprofessor/reviews
```

Render services do not share their local file systems. Database-backed artifact storage allows the worker to read uploads queued by the web service and allows the web service to deliver completed reports.

## Worker controls

Recommended starting configuration:

```env
VPROF_WORKER_CONCURRENCY=1
VPROF_WORKER_CLAIM_LIMIT=1
VPROF_WORKER_POLL_SECONDS=8
JOB_HEARTBEAT_SECONDS=30
JOB_LEASE_SECONDS=180
JOB_STALE_AFTER_SECONDS=240
AUTO_RESUME_JOBS=true
MAX_AUTO_RESUMES=2
```

Increase worker concurrency only after monitoring OpenAI rate limits, memory, database load and average job duration.

## Review models

The production route uses:

```env
OPENAI_SECTION_ANALYSIS_MODEL=gpt-5.6-terra
OPENAI_FINAL_SYNTHESIS_MODEL=gpt-5.6-sol
OPENAI_PHD_FINAL_SYNTHESIS_MODEL=gpt-5.6-sol
OPENAI_EXTERNAL_ADJUDICATOR_MODEL=gpt-5.6-sol
```

Terra handles routine extraction and section review. Sol handles bounded final synthesis and external-examiner adjudication.

## Native and inline comments

Recommended settings:

```env
VPROF_NATIVE_COMMENT_STYLE=exact_anchor_grouped
VPROF_EXPORT_ONE_COMMENT_PER_FINDING=false
VPROF_COMMENT_MERGE_BY_SECTION=true
VPROF_MAX_ITEMS_PER_NATIVE_COMMENT=8
VPROF_NATIVE_GROUP_LOCATION_MARKERS=false
```

Findings attached to the same sentence share one numbered Word comment. Findings attached to different sentences or paragraphs remain separate. Visible location markers are disabled to protect decimals, citations, equations and DOI strings.

## Section-scoped review

The web interface lets supervisors scan the uploaded chapter, select one or more detected sections and submit only those boundaries for review. Whole-chapter review remains the default. External assessment, full-thesis review and combined-chapter review ignore subsection selection and review the complete submitted scope.

## Degree structure

Bachelor’s, Non-Research Master’s, Research Master’s/MPhil and Professional Doctorate work uses the standard five-chapter research architecture as the default. A PhD may use a variable chapter structure, but the system checks for all prescribed doctoral functions and their integration.

## Administrator bootstrap

Set the following on the web service only when creating the first administrator:

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<strong-password>
ADMIN_EMAIL=<email>
ADMIN_NAME=System Administrator
```

These values do not overwrite an administrator already stored in PostgreSQL.

## Deployment sequence

1. Stop or allow active legacy jobs to finish.
2. Deploy the database, web service and worker from `render.yaml`.
3. Add `OPENAI_API_KEY`.
4. Confirm both services are Live.
5. Check worker logs for the startup message.
6. Submit a short test chapter.
7. Confirm the status moves from queued to document preparation within one or two polling cycles.
8. Confirm the output contains the annotated DOCX, inline-annotated DOCX and supervisory action report.

Old review checkpoints should not be reused because the v2.1.0 evidence-ledger, annotation and report pipeline identifiers changed.

## Validation

Run locally before deployment:

```bash
PYTHONPATH=. pytest -q
python -m compileall -q app
node --check app/static/app.js
```
