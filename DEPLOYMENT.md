# Render deployment

## Environment variables

Set `DEEPSEEK_API_KEY`. Light, Standard and Advanced Review use DeepSeek, with maximum reasoning and an independent second pass for Advanced Review.

## Commands

Build: `python -m pip install -r requirements.txt`

Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

Health check: `/health`

After replacing an earlier deployment, use **Clear build cache & deploy**. Remove obsolete OpenAI-only routing variables if they are no longer needed.


## Review-depth settings

```env
AI_LIGHT_SECTION_BATCH_SIZE=4
AI_SECTION_BATCH_SIZE=3
AI_ADVANCED_SECTION_BATCH_SIZE=2
AI_LIGHT_MAX_OUTPUT_TOKENS=6000
AI_STANDARD_MAX_OUTPUT_TOKENS=7500
AI_ADVANCED_MAX_OUTPUT_TOKENS=10000
AI_ADVANCED_SECOND_PASS=true
```

All three review levels use DeepSeek. Light and Standard Review use one primary pass at their respective academic benchmarks. Advanced Review uses maximum reasoning and an independent second-pass audit.

## Institutional portal deployment

Create or attach a PostgreSQL database and set its connection string as `DATABASE_URL`. Set a strong `SESSION_SECRET`, the initial administrator details, and `COOKIE_SECURE=true`.

Recommended variables:

```env
DATABASE_URL=postgresql://...
SESSION_SECRET=<long-random-value>
COOKIE_SECURE=true
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<strong-temporary-password>
ADMIN_NAME=System Administrator
REVIEW_STORAGE_DIR=/var/data/reviews
```

For durable annotated documents and reports, attach a Render persistent disk mounted at `/var/data`. Without a persistent disk, lecturer accounts remain in PostgreSQL but generated files stored on the service filesystem may disappear after a redeploy.

## Review file storage

The application starts with temporary storage by default:

```text
REVIEW_STORAGE_DIR=/tmp/projectready-supervisor/reviews
REVIEW_STORAGE_FALLBACK_DIR=/tmp/projectready-supervisor/reviews
```

This prevents startup failure when no persistent disk is attached. Files in
`/tmp` are temporary and can be removed when Render restarts or redeploys the
service.

For durable review reports and annotated documents:

1. Use a paid Render service.
2. Open the service's **Disks** page.
3. Add a persistent disk with mount path `/var/data`.
4. Set:

```text
REVIEW_STORAGE_DIR=/var/data/reviews
REVIEW_STORAGE_FALLBACK_DIR=/tmp/projectready-supervisor/reviews
```

The application tests the configured directory at startup. If the persistent
path is unavailable, it logs a warning and uses the temporary fallback instead
of stopping the service.

## AI provider variables

One DeepSeek API key enables all three review levels:

```text
DEEPSEEK_API_KEY=...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_REVIEW_MODEL=deepseek-v4-pro
DEEPSEEK_ADVANCED_MODEL=deepseek-v4-pro
DEEPSEEK_THINKING_ENABLED=true
DEEPSEEK_REASONING_EFFORT=high
DEEPSEEK_ADVANCED_REASONING_EFFORT=max
AI_ADVANCED_SECOND_PASS=true
AI_ADVANCED_SECTION_BATCH_SIZE=2
AI_VERIFICATION_BATCH_SIZE=2
```

Advanced Review performs a separate DeepSeek quality-control pass. OpenAI is no longer required for active review routing. Provider names are not displayed in the supervisor or student interface.

## Long-running review jobs

The browser now stores the active job identifier locally and reconnects after a page refresh. Polling continues for up to two hours, while the server limits a single expert-review job to 90 minutes by default.

```text
AI_JOB_MAX_SECONDS=5400
```

A completed job returns a small polling response containing a result URL. The full review is fetched separately, which prevents oversized polling responses and reduces browser failures.

## Faster DeepSeek review workflow

Version 1.4.1 reduces the number of model requests substantially.

- Light Review processes up to 6 sections per request.
- Standard Review processes up to 5 sections per request.
- Advanced Review processes up to 4 sections per request.
- Advanced primary review uses high reasoning.
- Maximum reasoning is reserved for one compact doctoral audit.
- Omitted sections are retried in groups of up to 6, not individually.
- Structured-output retries are disabled by default because grouped recovery handles incomplete coverage.

Recommended values:

```text
AI_LIGHT_SECTION_BATCH_SIZE=6
AI_SECTION_BATCH_SIZE=5
AI_ADVANCED_SECTION_BATCH_SIZE=4
AI_RECOVERY_BATCH_SIZE=6
AI_MAX_RECOVERY_BATCHES=2
AI_STRUCTURED_OUTPUT_RETRIES=0

DEEPSEEK_ADVANCED_PRIMARY_REASONING_EFFORT=high
DEEPSEEK_ADVANCED_REASONING_EFFORT=max
AI_ADVANCED_SECOND_PASS=true
AI_ADVANCED_AUDIT_MAX_FINDINGS=24
```

For a typical Chapter One with about 15 detected review units, Advanced Review should normally require about four primary requests and one compact audit, plus a grouped recovery request only when a section is omitted.
