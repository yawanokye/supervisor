# Render deployment

Use Python 3.12.11. The repository includes both `.python-version` and `render.yaml`.

## Required environment variables

Configure at least one academic-review provider:

```text
DEEPSEEK_API_KEY=...
```

or

```text
OPENAI_API_KEY=...
```

For the recommended hybrid review, configure both.

Also set:

```text
AI_REVIEW_ENABLED=true
AI_STRICT_FAILURE=true
PYTHON_VERSION=3.12.11
```

`AI_STRICT_FAILURE=true` prevents a failed provider call from being silently replaced with a basic keyword scan.

## Commands

Build:

```bash
python -m pip install -r requirements.txt
```

Start:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Health check:

```text
/health
```

After changing the Python version, use **Clear build cache & deploy** in Render.
