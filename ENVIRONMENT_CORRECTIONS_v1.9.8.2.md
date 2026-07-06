# Environment corrections for v1.9.8.2

## Add

- `VPROF_ENABLE_DEEPSEEK=true`
- `VPROF_EXTERNAL_CALL_BUDGET_USD=2.00`
- `VPROF_REJECT_PLACEHOLDER_COMMENTS=true`
- `VPROF_SUPPRESS_INTERNAL_AUDIT_NOTICES=true`
- `VPROF_COMMENT_MAX_CHARS=680`
- `VPROF_COMMENT_SIMILARITY_THRESHOLD=0.62`
- `DATABASE_URL=sqlite:////var/data/supervisor.db` only when SQLite is used on the Render persistent disk. Keep the Render PostgreSQL URL when PostgreSQL is already configured.

## Change

- `AI_CONFIDENCE_THRESHOLD=0.78`
- `AI_MAX_RETRIES=0`
- `AI_TIMEOUT_SECONDS=300`
- `AI_JOB_MAX_SECONDS=5400`
- `MAX_AUTO_RESUMES=3`
- `AI_ADVANCED_MAX_OUTPUT_TOKENS=12000`
- `AI_ADVANCED_AUDIT_MAX_OUTPUT_TOKENS=8000`

## Remove

These settings are stale, unused, duplicated or superseded by role-specific variables:

- `AI_PROVIDER_FAILOVER`
- `CHAPTER_REVIEW_CONCURRENCY`
- `FINDING_AUDIT_BATCH_SIZE`
- `FINDING_AUDIT_CONCURRENCY`
- `REVIEW_COMPACT_FINAL_CONTEXT`
- `REVIEW_REUSE_EXTRACTION`
- `REVIEW_RISK_BASED_EXPERT_AUDIT`
- `REVIEW_SINGLE_PASS_PER_CHAPTER`
- `OPENAI_ADVANCED_MODEL`
- `OPENAI_MINI_MODEL`
- `OPENAI_PREMIUM_MODEL`
- `OPENAI_REASONING_EFFORT`
- `OPENAI_REVIEW_MODEL`
- `OPENAI_REVIEW_REASONING_EFFORT`
- `OPENAI_VERIFY_MODEL`
- `OPENAI_EXTERNAL_MODEL`
- `OPENAI_EXTERNAL_REASONING_EFFORT`
- `OPENAI_EXTERNAL_DECISION_REASONING_EFFORT`
- `DEEPSEEK_EXTRACT_MODEL`

## Security correction

The previous `SESSION_SECRET` appeared in a shared environment file. Replace it in Render with a new randomly generated secret. Do not reuse the old value. Rotating it signs out existing browser sessions but does not delete users, reviews or balances.
