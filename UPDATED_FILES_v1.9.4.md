# Updated files in v1.9.4

- `app/assessment_schemas.py` — adds the combined external adjudication schema.
- `app/ai_config.py` — adds role-specific external domain and adjudicator models and output limits.
- `app/ai_providers.py` — supports structured adjudication output normalisation.
- `app/external_assessment.py` — implements three parallel examiners plus one final adjudicator.
- `app/main.py` — invalidates old final/external outputs while retaining compatible supervisory checkpoints.
- `.env.example` — provides recommended settings for supervisory and external workflows.
- `render.yaml` — includes the new production external-examination settings.
- `README.md`, `DEPLOYMENT.md`, `CHANGELOG.md` — document the unified workflow and deployment.
- `tests/test_checkpoint_resume_ui.py`, `tests/test_external_assessment_staging.py`, `tests/test_provider_routing.py`, `tests/test_fast_review_workflow.py`, `tests/test_unified_workflows_v194.py` — regression coverage.
