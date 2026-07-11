# VProfessor v1.9.9.19

## Professional reviewer and examiner pipeline

This release reorganises supervisory review around the requested scope rather than using one generic review flow.

### Scope behaviour

- **Chapter review:** assesses every section and subsection in the selected chapter, uses supporting chapters only for relevant alignment checks, and gives a bounded chapter-readiness judgement.
- **Combined-chapter review:** assesses every submitted chapter separately, then audits continuity and alignment across the selected range.
- **Complete-thesis examination:** reviews every chapter through a specialist lens, audits whole-thesis alignment, methods, results, discussion and contribution, and provides an examiner-style recommendation.

### Main quality changes

- Added a professional scope contract and specialist chapter roles.
- Added one canonical finding ledger shared by the professional report, native Word comments, inline annotated DOCX and correction list.
- Removed finding-number quotas. Findings now arise from evidence and coverage rather than a forced minimum count.
- Replaced prior-study examples with current-document, context-safe examples.
- Added methods, results and discussion audit sections, including an evidence-required classification where accuracy cannot be independently confirmed.
- Added chapter judgements, cross-chapter alignment, prioritised corrections and a scope-appropriate final recommendation.
- Protected comment markers from insertion inside words.
- Preserved the existing V-Professor branding and review delivery formats.

## Files added

- `app/professional_review_pipeline.py`
- `tests/test_professional_review_pipeline_v19919.py`

## Files updated

- `app/academic_ai_engine.py`
- `app/ai_config.py`
- `app/annotated_exporter.py`
- `app/deterministic_supervisory_checklist.py`
- `app/inline_annotated_exporter.py`
- `app/report_exporter.py`
- `app/review_enrichment.py`
- `app/static/app.js`
- `app/templates/index.html`
- `app/ucc_section_contract.py`
- `.env.example`
- `vprofessor-openai-worker.env.example`
- `render.yaml`
- `tests/test_comment_depth_v1985.py`
- `tests/test_native_comment_export_v187.py`

## Recommended environment values

```env
VPROF_PROFESSIONAL_REVIEW_PIPELINE=true
VPROF_SCOPE_SPECIFIC_REPORTS=true
VPROF_CANONICAL_FINDING_LEDGER=true
VPROF_FINDING_QUOTAS_ENABLED=false
VPROF_COMMENT_DEPTH_FLOOR_ENABLED=false
VPROF_STANDARD_NON_RESEARCH_MIN_FINDINGS=0
VPROF_STANDARD_RESEARCH_MASTERS_MIN_FINDINGS=0
VPROF_STANDARD_PROFESSIONAL_DOCTORATE_MIN_FINDINGS=0
VPROF_STANDARD_PHD_MIN_FINDINGS=0
VPROF_FULL_THESIS_EXAMINER_MODE=true
```

Apply the same review settings to the web service and background worker. The worker must retain the full AI model and review configuration because it performs the substantive review.
