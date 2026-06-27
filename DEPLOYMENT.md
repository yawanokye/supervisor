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
