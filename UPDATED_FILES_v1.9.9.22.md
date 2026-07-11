# VProfessor v1.9.9.22

## Systematic coverage-driven professional review

The review pipeline now walks through the entire submitted scope in sequential paragraph, heading and table-row units. It no longer relies on a broad whole-chapter request to select only the most obvious findings.

### Review behaviour

- Every non-empty paragraph, heading and table row is assigned to exactly one review target.
- Neighbouring passages are supplied only as context.
- Methods, results, analysis, discussion and tables use smaller high-risk packets.
- A coverage ledger records every unit and target assessed.
- The review is marked incomplete when the coverage release gate does not reach 100%.
- The number of comments is evidence-led. Predetermined finding floors and minimum comment counts are disabled.
- A passage may receive no visible comment only after it has been assessed and no material issue was found.
- Native comments and inline annotations continue to use the canonical finding ledger and final document-order numbering.

## Files added

- `app/coverage_review.py`
- `tests/test_systematic_coverage_review_v19922.py`

## Files updated

- `app/academic_ai_engine.py`
- `app/ai_config.py`
- `app/ai_prompts.py`
- `app/ai_schemas.py`
- `app/professional_review_pipeline.py`
- `app/report_exporter.py`
- `app/ucc_section_contract.py`
- `.env.example`
- `vprofessor-openai-worker.env.example`
- `render.yaml`
- `CHANGELOG.md`

## Required production environment

```env
VPROF_SYSTEMATIC_COVERAGE_REVIEW=true
VPROF_COVERAGE_PARAGRAPHS_PER_UNIT=7
VPROF_COVERAGE_CONTEXT_PARAGRAPHS=1
VPROF_COVERAGE_UNIT_MAX_CHARS=12000
VPROF_COVERAGE_TABLE_ROWS_PER_UNIT=10
VPROF_COVERAGE_UNITS_PER_REQUEST=4
VPROF_COVERAGE_HIGH_RISK_UNITS_PER_REQUEST=2
VPROF_COVERAGE_REQUEST_MAX_CHARS=28000
VPROF_COVERAGE_RELEASE_GATE=true

VPROF_FINDING_QUOTAS_ENABLED=false
VPROF_COMMENT_DEPTH_FLOOR_ENABLED=false
VPROF_STANDARD_NON_RESEARCH_MIN_FINDINGS=0
VPROF_STANDARD_RESEARCH_MASTERS_MIN_FINDINGS=0
VPROF_STANDARD_PROFESSIONAL_DOCTORATE_MIN_FINDINGS=0
VPROF_STANDARD_PHD_MIN_FINDINGS=0
```

Apply the same values to the web service and background worker. The worker performs the review.
