# V-Professor Supervisory Review 2.7.0

V-Professor provides degree-calibrated supervisory review and external assessment for Bachelor’s, Non-Research Master’s, Research Master’s/MPhil, Professional Doctorate and PhD work.

## Current-submission isolation

Every uploaded work is evidence for that review job only. A thesis, dissertation, chapter or benchmark used to test the system remains an example and is never converted into a reusable topic, institution, location, construct or correction rule.

The app rebuilds the study context from the current submission, uses earlier chapters only when they belong to the same work, and applies generic academic, methodological, statistical, language and citation standards.

## Final professional review controls

Version 2.7.0 adds the following release controls:

- natural student-facing comments limited to focused supervisory prose rather than visible labels such as `Issue`, `Problem identified`, `Action required` or `Verification`;
- substantive paragraph anchoring ahead of section-heading anchoring;
- root-cause consolidation for overlapping construct, background, problem-gap and scope findings;
- strict reconciliation between the canonical finding ledger, native Word comments and the appended correction register;
- one Word comment box for related findings tied to the same exact paragraph, with every released finding number represented;
- removal of empty source comments and status labelling where an earlier missing-section comment is visibly addressed;
- checks for generic limitations that do not explain consequences for evidence or conclusions;
- checks for unsupported absolute claims while preserving proportionate academic wording;
- suppression of weak findings based only on concise chapter descriptions or unverified mandatory-section assumptions;
- preservation of exact deterministic findings such as title-purpose drift, setting inconsistency, malformed citations and unresolved document instructions.

## Provider selection

Use the same provider settings on the web service and worker.

### OpenAI

```env
VPROF_PRIMARY_PROVIDER=openai
VPROF_ENABLE_OPENAI=true
VPROF_ENABLE_DEEPSEEK=false
OPENAI_API_KEY=your-key
VPROF_FALLBACK_PROVIDER=none
VPROF_PROVIDER_FAILOVER=false
```

### DeepSeek Pro

```env
VPROF_PRIMARY_PROVIDER=deepseek
VPROF_ENABLE_DEEPSEEK=true
VPROF_ENABLE_OPENAI=false
DEEPSEEK_API_KEY=your-key
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
VPROF_FALLBACK_PROVIDER=none
VPROF_PROVIDER_FAILOVER=false
```

## Recommended review controls

```env
VPROF_NATIVE_COMMENT_STYLE=exact_anchor_grouped
VPROF_EXISTING_COMMENT_POLICY=label
VPROF_STRICT_NATIVE_RECONCILIATION=true
VPROF_HUMAN_ROOT_CAUSE_CONSOLIDATION=true
VPROF_LIMITATIONS_CONSEQUENCE_AUDIT=true
VPROF_ABSOLUTE_CLAIM_AUDIT=true
```

## Deployment

Web service:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Background worker:

```bash
python -m app.worker
```

Both services must use the same `DATABASE_URL`, provider selection and provider API key. Deploy the same code to both services. Submit unfinished or failed reviews as new jobs because the 2.7.0 checkpoint and export identifiers differ from earlier releases.

## Administrator recovery

`ADMIN_PASSWORD` creates the first administrator but does not silently overwrite a password already stored in PostgreSQL. For a controlled one-time reset, set `VPROF_RESET_ADMIN_PASSWORD_ON_STARTUP=true`, redeploy the web service, sign in, set the flag back to `false`, and redeploy again.

## Local validation

```bash
PYTHONPATH=. pytest -q
python -m compileall -q app scripts
node --check app/static/app.js
```

See `DEPLOYMENT.md`, `.env.example` and `RELEASE_NOTES_v2.7.0.md`.
