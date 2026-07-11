# VProfessor v1.9.9.24 — Specification-Aligned Supervisory Review

This build implements the supplied **Supervisory Review Report and Review-Engine Specification** as the controlling review contract.

## Main behaviour changes

- Uses a coverage-driven process with PASS, COMMENT, VERIFY SOURCE and RE-ANALYSE statuses for every review target.
- Does not impose a predetermined number of findings or comments.
- Produces clear, student-facing, context-specific comments that state the issue, why it matters, the required correction and a current-study example when useful.
- Generates a decision-led supervisory or examiner report with scope and limitations, overall judgement, strengths, critical corrections, a statistical consistency audit, chapter plans, coverage assurance, detailed findings, evidence requirements and revision order.
- Runs deterministic measurement and statistical checks before final synthesis.
- Keeps statistical findings that were previously lost because their categories were not accepted by the strict issue schema.
- Distinguishes COMMENT, VERIFY SOURCE and RE-ANALYSE findings in the coverage ledger.
- Uses “the study”, “the work” and “the chapter”, not “uploaded document” or “uploaded text”.
- Retains one canonical finding ledger for the report, native Word comments and inline annotations.

## Files added

- `app/supervisory_review_algorithm.py`
- `tests/test_supervisory_algorithm_spec_v19924.py`
- `UPDATED_FILES_v1.9.9.24.md`

## Main files updated

- `app/academic_ai_engine.py`
- `app/ai_prompts.py`
- `app/ai_schemas.py`
- `app/coverage_review.py`
- `app/professional_review_pipeline.py`
- `app/report_exporter.py`
- `app/statistical_review.py`
- `app/student_friendly_review.py`
- `.env.example`
- `vprofessor-openai-worker.env.example`
- `render.yaml`
- `CHANGELOG.md`

## New environment settings

Apply these to both the web service and background worker:

```env
VPROF_SPEC_ALIGNED_SUPERVISORY_REPORT=true
VPROF_COVERAGE_STATUS_LEDGER=true
VPROF_MEASUREMENT_AUDIT=true
VPROF_REFERENCE_RECONCILIATION_AUDIT=true
VPROF_REQUIRE_STATISTICAL_AUDIT_FOR_RESULTS=true
```

Keep the systematic coverage settings and keep all finding quotas disabled.

## Statistical checks

The deterministic audit now supports, where the required values are printed in the work:

- displayed item-mean reconciliation
- `t = B / SE`
- approximate confidence-interval checks
- reconciliation of R², F, N, predictor count and degrees of freedom
- R² implied by F
- Cohen's f² and incremental f²
- F-change versus t² for one added predictor
- complete lower-order hierarchy for interaction models
- item allocation, response-scale, reliability and table-number consistency
- method-to-result and result-to-interpretation alignment

The app does not invent corrected coefficients. Where raw data or original software output is required, the finding is marked for verification or re-analysis.
