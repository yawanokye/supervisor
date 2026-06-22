# Render deployment

## Environment variables

Set `OPENAI_API_KEY`. The default models are `gpt-5.4-mini`, `gpt-5.4`, and `gpt-5.5`. GPT-5.5 is used only when Advanced Review is selected.

## Commands

Build: `python -m pip install -r requirements.txt`

Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

Health check: `/health`

After replacing an earlier deployment, use **Clear build cache & deploy**. Remove all DeepSeek environment variables because they are no longer used.
