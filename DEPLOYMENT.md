# Render deployment for MVP 0.5

## Commands

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Health check path:

```text
/health
```

## Required environment variables

Add these in Render under **Environment**:

```text
AI_REVIEW_ENABLED=true
DEEPSEEK_API_KEY=<your DeepSeek key>
OPENAI_API_KEY=<your OpenAI key>
DEEPSEEK_EXTRACT_MODEL=deepseek-v4-flash
DEEPSEEK_REVIEW_MODEL=deepseek-v4-pro
OPENAI_VERIFY_MODEL=gpt-5.4
OPENAI_PREMIUM_MODEL=gpt-5.5
AI_CONFIDENCE_THRESHOLD=0.82
AI_MAX_PARALLEL_CALLS=2
AI_STRICT_FAILURE=false
```

Copy the remaining optional controls from `.env.example` when needed.

## Recommended production mode

Use **Automatic routing** in the interface. With both keys configured, it resolves to Hybrid mode:

- DeepSeek Flash builds the compact thesis map.
- DeepSeek Pro performs the primary academic review.
- OpenAI verifies critical, uncertain, manual, and disputed decisions.
- GPT-5.5 is used only when Premium mode is selected and disagreement remains.

## Security

- Never place API keys in source files or commit them to GitHub.
- Use Render secret environment variables.
- Rotate any key that has been exposed.
- Replace the in-memory review cache before running multiple Render instances.
