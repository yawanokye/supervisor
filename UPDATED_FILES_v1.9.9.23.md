# VProfessor v1.9.9.23

## Clear student-facing supervision and analytical verification

This build converts checklist-style feedback into direct, natural supervisor language and strengthens the deterministic review of statistical results.

### Added

- `app/student_friendly_review.py`
  - removes app-facing wording such as “uploaded document” and “automated review”
  - rewrites missing-section findings in direct language
  - provides issue-specific academic-level expectations
  - rejects examples that do not belong to the current study
  - generates practical examples from the marked passage and current study terms

- `tests/test_clear_student_friendly_statistical_review_v19923.py`
  - tests natural missing-section language
  - tests UCC heading aliases such as “Definition of Key Concepts”
  - blocks stale banking and fraud examples
  - verifies table-level descriptive, regression, correlation and moderation checks

### Updated

- `app/ai_prompts.py`
  - requires clear student-facing comments
  - prohibits “uploaded document”, “automated review” and checklist language
  - requires table-by-table accuracy and appropriateness review

- `app/academic_ai_engine.py`
  - applies student-friendly wording before findings enter the review ledger

- `app/comment_quality.py`
  - sanitises all public findings and removes system language

- `app/reviewer_language.py`
  - consistently uses “the study”, “the work” and actual section names

- `app/review_enrichment.py`
  - validates every example against the current study and replaces stale examples

- `app/ucc_section_contract.py`
  - recognises equivalent headings such as “Definition of Key Concepts”
  - reports missing sections directly, for example “Definition of Terms is missing from Chapter One”
  - explains why the section is required and where it should be placed
  - provides a study-specific example where useful

- `app/deterministic_supervisory_checklist.py`
  - replaces technical checklist language with simple supervisory explanations

- `app/statistical_review.py`
  - checks tables as complete analytical objects
  - recomputes displayed overall means where possible
  - checks B, SE, t and confidence-interval consistency
  - checks R², F, N, predictor count and degrees of freedom
  - identifies correlations misreported as influence or effect
  - checks regression-table completeness
  - checks moderation probing and hierarchical three-way interaction terms
  - includes method-appropriateness checks
  - provides exact corrective actions and examples

- `app/professional_review_pipeline.py`
  - applies natural wording before the canonical finding ledger is created

- `app/annotated_exporter.py`
  - uses the same clear findings in native comments and detailed blue inline corrections

- `.env.example`
- `vprofessor-openai-worker.env.example`
- `render.yaml`
  - document the new student-friendly and statistical-audit controls

- `tests/test_ucc_section_contract_v1998.py`
  - removes the former predetermined comment-floor expectation

- `tests/test_native_comment_export_v187.py`
  - reflects the new direct missing-section wording

## Required environment values

```env
VPROF_STUDENT_FRIENDLY_COMMENTS=true
VPROF_CONTEXT_SPECIFIC_EXAMPLES=true
VPROF_STATISTICAL_TABLE_AUDIT=true
VPROF_ANALYSIS_APPROPRIATENESS_AUDIT=true
```

These should be set on both the web service and the background worker.
