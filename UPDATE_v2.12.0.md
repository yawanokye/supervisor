# VProfessor clean revision update

The release follows the supplied clean manuscript's editing approach. It applies permitted local wording corrections and reserves margin comments for unresolved student work. The example manuscript was used to understand the approach and is not bundled with the app or stored as a production example.

## Behaviour

- A new clean revised Word download sits alongside the annotated manuscript and review report.
- The AI review can propose exact local replacements. A deterministic gate accepts only conservative spelling, agreement, article, repetition and limited punctuation repairs. It does not accept arbitrary paraphrasing or scholarly changes.
- Numerical disagreements, supporting sources, instruments, sampling, ethics, hypotheses and conceptual framework choices remain student decisions. Comments name the problem and the evidence or correction needed.
- The app removes a clean-copy comment only when accepted edits fully resolve an isolated editorial finding. Substantive, merged and recurring obligations remain visible.
- Every remaining finding is either anchored to a verified revised passage or explicitly retained for location checking in the report. The clean manuscript has no appended review register or inserted body markers.
- The report records every accepted original and replacement span. Its original-source findings remain intact.

## Files to deploy

Deploy the full contents of `supervisor-main` in this archive. The active changes are:

- `app/clean_revision.py` is new.
- `app/ai_schemas.py`, `app/ai_prompts.py`, `app/ai_providers.py` and `app/academic_ai_engine.py` carry exact edit proposals.
- `app/final_review_quality.py` preserves edit proposals when findings merge and prevents a merged obligation from being silently treated as resolved.
- `app/human_comment_budget.py` preserves major issues and pending editorial repairs.
- `app/annotated_exporter.py` permits the clean exporter to suppress body markers explicitly.
- `app/main.py` generates, authorises and recovers the clean download.
- `app/storage.py` saves and retrieves the clean manuscript through the existing persistence backends.
- `app/report_exporter.py` records applied corrections and remaining location checks.
- `app/static/app.js`, `app/templates/index.html` and `app/templates/review_detail.html` expose the download.
- `app/ai_config.py` and `app/model_compatibility.py` add current Luna rates and supported reasoning efforts.
- `app/model_router.py` accounts for actual cache writes and long-context rates for GPT-6 Luna and GPT-6.1 Sol.
- `tests/test_clean_revision_v212.py`, `tests/test_gpt6_hybrid_costs_v212.py`, `README.md`, `CHANGELOG.md` and `VALIDATION.md` document and verify the release.

No new environment variables, dependencies or database migrations are required for the clean revision feature. The optional `vprofessor-gpt6-hybrid.env.example` uses existing model-role settings. `HYBRID_PIPELINE_NOTES.md` distinguishes the current live pipeline from the proposed Batch and interactive-chat features. Restart both web and worker services after deploying the code. This archive uses the existing `uvicorn app.main:app` layout and excludes duplicated inactive root-level Python modules from the separately uploaded source.

## Existing reviews

Fresh reviews generate replacement proposals using the updated schemas. Existing saved reviews can regenerate a clean copy from their retained Word source, but corrections are applied only if those reviews contain exact replacement proposals. Old findings are not turned into invented corrections and downloading an existing review does not make another model call. Submit a fresh review to obtain new editorial proposals for an older manuscript.

## Validation

The focused release suite passed 100 tests. Application Python syntax, JavaScript syntax, authorised download behaviour and a rendered Word sample were checked. Live model output quality still depends on the configured model and the evidence supplied. No live API review was performed in this environment.
