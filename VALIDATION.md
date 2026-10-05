# VProfessor 2.11.0 validation

Validated locally on 4 October 2026 with Python 3.12 and the pinned runtime dependencies.

- Full regression suite: **456 passed**, with six dependency deprecation warnings.
- Compilation: `python3 -m compileall -q app scripts` passed.
- Labelled statistical benchmark: **6 of 6 synthetic cases passed** using `python3 scripts/benchmark_review_quality.py`.
- Provider compatibility and recovery tests use mocked HTTP responses. No paid OpenAI or DeepSeek calls were made.

The regression run used a new temporary SQLite database and review-storage directory. Reusing a test database can leave the auth test's lecturer account in place, so use a fresh database for each complete run.

## Comment placement

The placement regressions check stale paragraph ordinals, repeated quotations in different sections, ambiguous duplicate paragraphs, repeated phrases within a paragraph, wrong chapter and section evidence, stale character offsets, separate sentence ranges, quoted cells in table rows, native comment styles, inline table notes and report corrections when location verification fails. The checks inspect the actual Word XML comment ranges and inline note positions.

The exporter does not attach passage-specific comments through an arbitrary first paragraph, last paragraph or heading fallback. It requires a unique source match. An unverified finding remains numbered in the review and is listed in the report with its required correction and manual location notice. Genuine missing-section findings remain in the correction notes because the missing text cannot be quoted.

## Scope of the evidence

These checks establish the tested software behaviour. They do not establish measured accuracy, cost, latency or human-rated comment quality across real theses. Live model access has not been tested in this environment. Use `REVIEW_QUALITY_CHECK.md` for evaluation on representative submissions.

Statistical recomputation checks internal consistency when its prerequisites are explicit; it does not reproduce an analysis from raw data. A reference-list match does not verify that a source exists or supports a claim. Scanned PDFs need readable text or OCR. Word SmartArt or unsupported drawings may still need manual visual verification.

## Model selection

Set `OPENAI_MODEL=gpt-6.1-sol` and `OPENAI_MODEL_MODE=single` to use that model across OpenAI roles. Restart both web service and worker after environment changes. Compatible text-model IDs can be changed without source edits. Models must be available to the configured API account and have sufficient capacity for the requested review.

No production deployment was performed. This archive contains application source, configuration examples, documentation and tests; runtime databases and review storage are excluded.
