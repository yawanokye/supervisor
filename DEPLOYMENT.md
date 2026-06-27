# Render deployment

## Environment variables

Set `OPENAI_API_KEY`. The default models are `gpt-5.4-mini`, `gpt-5.4`, and `gpt-5.5`. GPT-5.5 is used only when Advanced Review is selected.

## Commands

Build: `python -m pip install -r requirements.txt`

Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

Health check: `/health`

After replacing an earlier deployment, use **Clear build cache & deploy**. Remove all DeepSeek environment variables because they are no longer used.


## Light Review settings

```env
AI_LIGHT_SECTION_BATCH_SIZE=4
AI_LIGHT_MAX_FINDINGS=12
AI_LIGHT_MAX_OUTPUT_TOKENS=4200
```

Light Review uses GPT-5.4 mini only and does not run the independent GPT-5.4 or GPT-5.5 verification stage.

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

Configure both providers when all three review levels will be offered:

```text
DEEPSEEK_API_KEY=...
DEEPSEEK_REVIEW_MODEL=deepseek-v4-pro
DEEPSEEK_THINKING_ENABLED=true
DEEPSEEK_REASONING_EFFORT=high

OPENAI_API_KEY=...
OPENAI_REVIEW_MODEL=gpt-5.4
OPENAI_REVIEW_REASONING_EFFORT=high
```

Light and Standard Review require the DeepSeek key. Advanced Review requires the OpenAI key. Provider names are not displayed in the student or lecturer interface.

## Long-running review jobs

The browser now stores the active job identifier locally and reconnects after a page refresh. Polling continues for up to two hours, while the server limits a single expert-review job to 90 minutes by default.

```text
AI_JOB_MAX_SECONDS=5400
```

A completed job returns a small polling response containing a result URL. The full review is fetched separately, which prevents oversized polling responses and reduces browser failures.
