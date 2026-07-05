# Updated files in v1.9.5

## Core fixes

- `app/academic_ai_engine.py`
  - adaptive verification batches
  - focused audit retry
  - evidence-grounded fallback comments
  - empty-output validation
- `app/annotated_exporter.py`
  - native comment count validation
  - manual-confirmation label for deterministically retained comments
  - new annotation export version
- `app/main.py`
  - prevents empty annotated downloads
  - supports rebuilding completed limited reviews
  - pauses safely when usable findings cannot be validated
- `app/templates/portal.html`
  - **Rebuild review** action
- `app/templates/review_detail.html`
  - **Rebuild review and comments** action
- `app/ai_config.py`
  - default `AI_VERIFICATION_BATCH_SIZE=12`

## Deployment setting

```env
AI_VERIFICATION_BATCH_SIZE=12
AI_MAX_PARALLEL_CALLS=4
AI_CHAPTER_REVIEW_CONCURRENCY=4
```

Existing reviews showing **Review completed with a limitation** can be rebuilt after deployment without uploading the document again, provided the saved payload remains on persistent storage.
