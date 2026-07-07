# VProfessor v1.9.9.7 — Structured Output Recovery and Provider Error Clarity

## Updated files

- `app/ai_providers.py`
- `app/academic_ai_engine.py`
- `.env.example`
- `README.md`
- `DEPLOYMENT.md`
- `CHANGELOG.md`
- `UPDATED_FILES_v1.9.9.7.md`
- `ENVIRONMENT_CHANGES_v1.9.9.7.md`

## Purpose

This update fixes the failure where OpenAI returned `HTTP/1.1 200 OK` but the job still stopped with the old misleading message about DeepSeek/fast providers. The failure was caused by the first chapter pass response not being converted into the strict internal academic-review schema.

## Key changes

1. Normalises section-review items inside `AcademicReviewBatch` before Pydantic validation.
2. Adds clearer OpenAI error messages showing model, purpose, and schema/truncation reason.
3. Replaces the old DeepSeek-specific first-pass failure message with a provider-agnostic message.
4. Enables one structured-output repair retry by default.
5. Reduces live section batch size to lower the chance of oversized structured JSON responses.
6. Increases live fast request timeout to support the combined OpenAI pipeline.
