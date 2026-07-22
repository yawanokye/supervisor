# V-Professor Supervisory Review 2.4.0

V-Professor provides degree-calibrated supervisory review and external assessment for Bachelor’s, Non-Research Master’s, Research Master’s/MPhil, Professional Doctorate and PhD work.

## Natural supervisory comments

Native Word comments and inline annotations now read as connected supervisory prose. They no longer expose mechanical subsections such as `Issue`, `Problem identified`, `Action required` or `Verification`.

A typical comment now reads like this:

> The purpose introduces outcomes that are not represented consistently in the objectives and questions. Revise the purpose, objectives and questions together so that each study task has one matching analytical route.

Related concerns attached to the same paragraph are combined in one numbered comment box. The full revision schedule remains available at the end of the reviewed document.

## Accuracy and release controls in 2.4.0

- Reads the complete section before claiming that an introduction, objective, contribution, gap or other element is missing.
- Suppresses false findings about the normal `CHAPTER ONE` and `INTRODUCTION` heading pair.
- Verifies objective counts even when Word stores list numbers as numbering metadata.
- Reconstructs actual British and American spelling evidence instead of accepting invented examples.
- Rewrites limitation comments to match what the submitted text actually says.
- Consolidates repeated background, problem-statement, significance, terminology and purpose-alignment findings.
- Detects title-purpose claim drift such as `contribution` versus `impact`.
- Detects study-setting drift such as `Aboabo Market` versus the broader `Tamale Market`.
- Detects modal-verb errors such as `How can ... creates`.
- Requires every released finding number to be represented in the native Word comments.
- Groups all released findings attached to the same paragraph into one natural comment box.

## Provider selection and cost control

The app supports environment-controlled OpenAI or DeepSeek routing. Use the same provider settings on the web service and worker. DeepSeek primary chapter packets remain compact, non-thinking and recoverable at a single-target level to reduce structured-output truncation and repeated paid passes.

Use OpenAI:

```env
VPROF_PRIMARY_PROVIDER=openai
VPROF_ENABLE_OPENAI=true
VPROF_ENABLE_DEEPSEEK=false
OPENAI_API_KEY=your-key
VPROF_FALLBACK_PROVIDER=none
VPROF_PROVIDER_FAILOVER=false
```

Use the configured DeepSeek Pro route:

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

## Deployment

Web service:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Background worker:

```bash
python -m app.worker
```

Both services must use the same `DATABASE_URL`, provider choice and provider API key. Deploy the package to both services and submit unfinished reviews as new jobs because the 2.4.0 release and checkpoint identifiers differ from earlier versions. See `DEPLOYMENT.md` and `.env.example`.
