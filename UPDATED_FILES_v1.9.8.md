# VProfessor v1.9.8 updated files

## Core integration

- `app/model_router.py`, new integrated cost-aware router using the existing HTTP providers
- `app/ai_config.py`, routing profiles, provider availability, model roles and multi-provider prices
- `app/academic_ai_engine.py`, routed chapter review, selective escalation and routed final audit
- `app/external_assessment.py`, OpenAI-led external assessment with DeepSeek Pro provider fallback
- `app/main.py`, application and checkpoint version update

## Deployment and documentation

- `.env.example`
- `render.yaml`
- `README.md`
- `CHANGELOG.md`
- `DEPLOYMENT.md`

## Tests

- `tests/test_model_router_v198.py`, new one-call, escalation and fallback tests
- `tests/test_provider_routing.py`, updated integrated routing expectations
- Existing workflow tests updated to the v1.9.8 checkpoint identifiers

## Compatibility

No new Python dependency was added. The router reuses the existing `httpx`
OpenAI Responses API and DeepSeek Chat Completions clients. Existing databases,
persistent review files, native Word comments and supervisor token balances are
preserved.
