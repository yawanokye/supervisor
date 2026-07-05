# Updated files in v1.9.3

- `app/academic_ai_engine.py`
  - Added deterministic chapter-level review packets.
  - Runs chapter packets in parallel.
  - Uses one chapter-level coverage retry instead of three recovery layers.
  - Uses larger compact factual-audit batches.
  - Added workflow metadata for diagnostics.
- `app/ai_config.py`
  - Added chapter packet size, concurrency and recovery settings.
  - Increased the default verification batch size to 48.
- `app/ai_prompts.py`
  - Critical and major findings cannot be omitted because a concise review depth was selected.
- `app/main.py`
  - Updated supervisory-review checkpoint versions.
- `.env.example`, `render.yaml`, `README.md`, `DEPLOYMENT.md`
  - Added the new deployment settings and removed the active dependency on focused-section recovery.
- `tests/`
  - Added chapter-packet, bounded-recovery and configuration tests.

Validation: 170 tests passed.
