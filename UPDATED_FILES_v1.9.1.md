# Updated files in v1.9.1

## AI routing and quality

- `app/ai_config.py`
- `app/ai_providers.py`
- `app/academic_ai_engine.py`
- `app/external_assessment.py`
- `app/main.py`

GPT-5.4 mini now handles fast chapter assessment. GPT-5.4 handles universal factual auditing, research-intensive academic review and External Assessment. Academic level determines model escalation, while Light, Standard and Advanced retain the same factual-accuracy threshold.

## Native Word comment identity

- `app/annotated_exporter.py`
- `app/main.py`

The comment author is the logged-in user’s full name. Initials are derived automatically. The generic “Supervisor Assistant” author is no longer used for native comments.

## Configuration and deployment

- `.env.example`
- `render.yaml`
- `README.md`
- `DEPLOYMENT.md`
- `CHANGELOG.md`
- `scripts/provider_smoke_test.py`

Remove any old `OPENAI_REVIEW_MODEL=o3-mini` Render variable and configure the role-specific GPT-5.4 mini/GPT-5.4 variables.

## Tests

- `tests/test_provider_routing.py`
- `tests/test_fast_review_workflow.py`
- `tests/test_openai_o3_mini_provider.py`
- `tests/test_native_comment_export_v187.py`

The suite verifies level-based model routing, GPT-5.4 universal auditing, `xhigh` reasoning support, and user-name/initials comment authorship.
