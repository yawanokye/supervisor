# Updated files in v1.4.0

## AI routing and configuration

- `app/ai_config.py`
  - Routes Light, Standard and Advanced Review through DeepSeek.
  - Adds `DEEPSEEK_ADVANCED_MODEL`, maximum reasoning for Advanced Review, smaller advanced batches and an independent second pass.
- `app/academic_ai_engine.py`
  - Uses DeepSeek for Advanced Review and its quality-control pass.
  - Adds study-context locking, context validation, issue consolidation and source-verification metadata.
- `app/ai_providers.py`
  - Retained as the provider transport and structured-output validation layer.
- `scripts/provider_smoke_test.py`
  - Tests both normal and advanced DeepSeek configurations.

## Review quality and accuracy

- `app/ai_prompts.py`
  - Adds strict prohibitions against invented locations, institutions, populations, citations and statistics.
  - Requires placeholders where source context is not supplied.
  - Distinguishes missing content from weak content and requires conditional methodological advice when design details are unknown.
- `app/context_guard.py` (new)
  - Builds a context lock from the uploaded thesis.
  - Removes unrelated countries and settings from generated guidance.
  - Replaces unsupported citations and statistics with safe verification instructions.
- `app/academic_review_guide.py` (new)
  - Provides broad internal academic expectations adapted from the supplied thesis self-evaluation checklist.
  - Does not expose checklist codes or reproduce the checklist as the review.
- `app/ai_schemas.py`
  - Adds guidance type, source-verification and context-adjustment fields.

## Reports and annotations

- `app/report_exporter.py`
  - Adds a recognised study-context section.
  - Adds a dedicated evidence and source-verification section.
  - Shortens repeated assessments, actions and examples.
  - Avoids repeating source-verification findings in every section.
- `app/annotated_exporter.py`
  - Shortens green comments and limits grouped comments to the most important distinct actions.

## Configuration and documentation

- `.env.example`
- `README.md`
- `DEPLOYMENT.md`
- `CHANGELOG.md`
- `app/main.py`

## Tests

- `tests/test_provider_routing.py`
- `tests/test_context_guard.py` (new)
- `tests/test_internal_review_guide.py` (new)
