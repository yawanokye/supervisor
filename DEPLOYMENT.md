# V-Professor v2.7.0 Deployment Guide

## Architecture

Deploy three Render resources:

1. PostgreSQL database: `vprofessor-db`
2. Web service: `vprofessor-web`
3. Background worker: `vprofessor-worker`

The included `render.yaml` creates the resources and shares one environment definition between the web service and worker.

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

Set the following in Render without committing their real values:

```env
DATABASE_URL=<shared PostgreSQL connection>
SESSION_SECRET=<strong random value>
OPENAI_API_KEY=<secret>        # when OpenAI is enabled
DEEPSEEK_API_KEY=<secret>      # when DeepSeek is enabled
ADMIN_PASSWORD=<strong password>
```

The web service and worker must use the same database and provider settings.

## Final review controls

Keep these enabled on both services:

```env
VPROF_NATIVE_COMMENT_STYLE=exact_anchor_grouped
VPROF_EXISTING_COMMENT_POLICY=label
VPROF_STRICT_NATIVE_RECONCILIATION=true
VPROF_GROUP_SAME_ANCHOR_COMMENTS=true
VPROF_HUMAN_ROOT_CAUSE_CONSOLIDATION=true
VPROF_LIMITATIONS_CONSEQUENCE_AUDIT=true
VPROF_ABSOLUTE_CLAIM_AUDIT=true
VPROF_EXPORT_ANCHOR_RECONCILIATION=true
```

Strict native reconciliation stops export rather than releasing a report whose canonical finding numbers are absent from the native Word comments. Findings tied to the same exact paragraph may share one comment box while retaining their individual numbers.

Previous source-document comments remain separate from current V-Professor findings. Empty comments are removed, and an obvious missing-section comment may be marked as addressed when the section is visibly present in the current file.

## Provider selection

### DeepSeek

```env
VPROF_PRIMARY_PROVIDER=deepseek
VPROF_ENABLE_DEEPSEEK=true
VPROF_ENABLE_OPENAI=false
DEEPSEEK_API_KEY=<secret>
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_REVIEW_MODEL=deepseek-v4-pro
DEEPSEEK_ADVANCED_MODEL=deepseek-v4-pro
DEEPSEEK_QUALITY_MODEL=deepseek-v4-pro
DEEPSEEK_FAST_MODEL=deepseek-v4-flash
DEEPSEEK_PRIMARY_THINKING_ENABLED=false
DEEPSEEK_AUDIT_THINKING_ENABLED=true
DEEPSEEK_TRUNCATION_RECOVERY=true
DEEPSEEK_COVERAGE_UNITS_PER_REQUEST=1
DEEPSEEK_COVERAGE_HIGH_RISK_UNITS_PER_REQUEST=1
VPROF_PROVIDER_FAILOVER=false
VPROF_FALLBACK_PROVIDER=none
```

### OpenAI

```env
VPROF_PRIMARY_PROVIDER=openai
VPROF_ENABLE_OPENAI=true
VPROF_ENABLE_DEEPSEEK=false
OPENAI_API_KEY=<secret>
VPROF_PROVIDER_FAILOVER=false
VPROF_FALLBACK_PROVIDER=none
```

## Administrator bootstrap and recovery

The first administrator is created from `ADMIN_USERNAME` and `ADMIN_PASSWORD`. Normal restarts do not overwrite an administrator already stored in PostgreSQL.

For a controlled one-time reset:

```env
VPROF_RESET_ADMIN_PASSWORD_ON_STARTUP=true
```

Redeploy the web service, sign in with the configured credentials, then immediately return the flag to `false` and redeploy. The password is never printed in the startup logs. A trusted Render Shell may alternatively run:

```bash
python scripts/reset_admin_password.py
```

## Deployment sequence

1. Allow active legacy jobs to finish or stop them deliberately.
2. Deploy the 2.7.0 code to both the web service and worker.
3. Confirm the shared database and selected provider key are available to both services.
4. Confirm the web health check and worker startup logs are successful.
5. Submit a short new review job.
6. Confirm generation of the native annotated DOCX, inline annotated DOCX and supervisory action report.
7. Verify that all released finding numbers appear in the canonical report and annotated output.

Do not recover unfinished jobs created with older checkpoint identifiers. Submit them as new jobs.

## Local validation

```bash
rm -f supervisor.db
PYTHONPATH=. pytest -q
python -m compileall -q app scripts
node --check app/static/app.js
```
