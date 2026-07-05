# Updated files in v1.9.2

- `app/academic_ai_engine.py`: focused expert recovery for omitted sections, progressive 64–67% status, conservative evidence-safe fallback.
- `app/ai_prompts.py`: dedicated compact single-section recovery prompt.
- `app/ai_providers.py`: structured-output normalisation for a single section review.
- `app/ai_config.py`: focused recovery concurrency, token and timeout controls.
- `app/main.py`: v1.9.2 pipeline hashes and bounded automatic recovery.
- `app/static/app.js`: stops browser-driven infinite resume loops.
- `.env.example`, `render.yaml`: deployment settings.
- `tests/test_stable_coverage_recovery_v192.py`: regression coverage.
