# VProfessor v1.9.8.1 updated files

## Runtime code

- `app/ai_providers.py`
  - fixes the DeepSeek thinking payload
  - supports per-route thinking mode
- `app/model_router.py`
  - disables thinking for Flash review
  - uses GPT-5.4 nano as the Balanced fast fallback
  - retains DeepSeek Pro fallback in Economy mode
- `app/ai_config.py`
  - adds fast timeout, audit cap and GPT-5.4 nano settings
  - lowers Light and Standard output defaults
  - adds accurate GPT-5.4 nano cost accounting
- `app/academic_ai_engine.py`
  - prevents duplicate first-pass escalation
  - limits Light and Standard to one compact OpenAI audit
  - disables paid fast-audit retries
  - stops before repeating a completely failed fast pass
- `app/main.py`
  - updates the application and supervisory checkpoint versions

## Deployment and documentation

- `.env.example`
- `render.yaml`
- `README.md`
- `DEPLOYMENT.md`
- `CHANGELOG.md`

## Tests

- `tests/test_model_router_v198.py`
- `tests/test_cost_latency_hotfix_v1981.py`
- version-aware workflow tests

Validation result: 193 tests passed.
