# Updated files in v1.8.9

- `app/ai_config.py`
  - Makes OpenAI the required active provider and defaults to `o3-mini` with high reasoning effort.
  - Updates o3-mini cost tracking, output budgets and request timeouts.

- `app/ai_providers.py`
  - Uses the OpenAI Responses API with strict JSON Schema output.
  - Adds structured-output retries, request-specific timeouts and incomplete-response detection.

- `app/academic_ai_engine.py`
  - Routes every review depth, recovery pass and factual-accuracy audit through OpenAI.
  - Versions review and audit checkpoints for the provider migration.

- `app/external_assessment.py`
  - Routes all five grounded examiner stages through OpenAI o3-mini.
  - Uses OpenAI cost tracking and new provider-specific checkpoint hashes.

- `app/main.py`
  - Updates the application version and completed-review checkpoint hashes to v1.8.9.

- `.env.example`, `render.yaml`, `README.md`, `DEPLOYMENT.md`
  - Document the required OpenAI variables and deployment procedure.

- `scripts/provider_smoke_test.py`
  - Tests the live o3-mini structured-output connection.

- `tests/test_provider_routing.py`
- `tests/test_external_assessment_staging.py`
- `tests/test_fast_review_workflow.py`
- `tests/test_openai_o3_mini_provider.py`
  - Verify OpenAI-only active routing, strict Responses API payloads, truncation handling and grounded external assessment.
