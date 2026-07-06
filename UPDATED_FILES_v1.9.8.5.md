# Updated files for v1.9.8.5

## Purpose
v1.9.8.5 corrects the review-depth behaviour observed in Light, Standard Non-Research Master's and Standard Research Master's/MPhil outputs. It makes depth visible through richer developmental Word comments rather than raw comment counts only, and it preserves the expected level ordering for the same weak chapter.

## Runtime files
- `app/academic_ai_engine.py`
- `app/ai_config.py`
- `app/ai_prompts.py`
- `app/annotated_exporter.py`
- `app/comment_quality.py`

## Deployment files
- `.env.example`
- `render.yaml`
- `supervisor-v1.9.8.5-render.env.example`
- `ENVIRONMENT_CHANGES_v1.9.8.5.md`

## Documentation and tests
- `README.md`
- `DEPLOYMENT.md`
- `CHANGELOG.md`
- `UPDATED_FILES_v1.9.8.5.md`
- `tests/test_comment_depth_v1985.py`
- Existing version-string tests updated to v1.9.8.5.
