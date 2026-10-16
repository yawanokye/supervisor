# VProfessor 2.13.1 validation

Validated on 16 October 2026: **172 focused tests passed** with one dependency warning. This includes the previous 166-test release suite, five new inline reconciliation cases and an additional inline-failure recovery case.

The supplied worker traceback identifies `build_inline_annotated_docx` calling reconciliation and raising `No verified source location is available for this inline finding`. Two local cases reproduced that exact failure in the previous exporter. A missing-section finding fails when its preferred note is disabled or omitted. A previously verified passage can fail after a reference marker changes its text and its presentation note needs restoration. The patch preserves the original verification text and gives absent sections their own labelled reviewer additions.

Regression tests verify correct note placement, retained manual-location findings, distinct ordered finding numbers, and no duplicate reference marker. Recovery is tested after failures in both native and inline export, with academic analysis, review, final consistency audit and prose-polish functions forbidden from being called.

A two-page synthetic inline document was rendered and both pages visually inspected. Red highlighting, blue italic notes and the explicit missing-section action were readable. Python compilation and JavaScript syntax validation passed. No paid model request or production recovery was performed from this workspace. The exact production finding that triggered the traceback is unavailable, so validation establishes the reproduced failure paths rather than claiming to have inspected the live job.

## Historical 2.13.0 validation

Validated on 16 October 2026: **166 focused tests passed** with one dependency warning. The focused release suite covers background chapter progression, Stop and lease ownership, job permissions, upload acknowledgement ordering, queue/readiness estimates, Flex routing and pricing, Batch grouping and recovery, related-work discovery and exports, plus the previous clean-revision and annotation regressions. The exact test command is recorded in the release validation log.

The export defect was reproduced with a canonical missing-section finding and no source quotation. Native export raised a reconciliation error, while inline export completed. The fix anchors the missing-section action to a labelled reviewer addition and passes native and inline audits in both grouped and individual comment modes. A separate interrupted-export test restores the saved assembled review and completes without invoking academic analysis, review, consistency-audit or prose-polish functions.

The supplied manuscript was also processed locally with synthetic export findings from several chapters plus an absent-section action. Native and inline bundle audits passed. This was an export smoke check, not an academic review of that manuscript.

A two-page suggested-reading sample was rendered and both pages visually inspected. Python modules compiled and browser JavaScript passed syntax checks. HTML templates rendered successfully. A Playwright run could not start because the runtime does not contain a Chromium executable, so browser interaction and mobile layout were not visually verified.

Provider and scholarly API behaviour used mocked responses. No paid model request, live scholarly query from the app, live deployment or production job recovery was performed. Real account access, processing times and server-specific failures remain unverified. Historical full-suite results below describe older builds, not this update.

## Historical 2.12.0 validation

Validated on 16 October 2026. The focused release suite passed **100 tests** across the new clean revision, verified placement, professional comment quality, framework assurance, atomic annotation bundle, native comments, DOCX tables guided chapter export, GPT-6 hybrid costs, and model routing tests. All application Python modules parsed successfully and browser JavaScript passed syntax validation. The application imported successfully and registered the clean revision route.

The new tests cover protected numbers, citations, uncertainty, negation, research stage, logical conjunctions, methods and construct names. They also check preserved formatting across runs, student comments after an edit, unresolved numerical conflicts, ambiguous duplicate evidence, existing comments, table cells, source quotations, comment-budget retention, authorised download access and cached export delivery.

A rendered one-page sample was visually inspected. Its grammar repair preserved bold and italic text, while conflicting item counts and ethics-stage statements remained unchanged with two native Word comments. Comment records and exact anchors were checked in Word XML because headless PDF export does not show margin comments.

This release validation used synthetic review payloads and mocked provider behaviour. No live model review or paid API call was performed. The full historical suite was not rerun for this release. The historical validation below is retained as a record of the preceding version.

The cost tests distinguish ordinary input, actual cache reads, cache writes and output, including long-context rates. They confirm that live requests receive no Batch discount and that the optional role profile routes mechanical work to Luna and academic work to Sol.

## Historical 2.11.0 validation

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
