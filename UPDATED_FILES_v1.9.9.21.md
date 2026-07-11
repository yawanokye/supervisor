# VProfessor v1.9.9.21: Expert sequential and detailed review

## Purpose

This release strengthens VProfessor as a professional supervisor and examiner for a single chapter, combined chapters, or a complete thesis. It corrects the numbering, anchoring, reviewer language, inline annotation detail, and results-accuracy weaknesses observed in the previous reviewed DOCX.

## Main behaviour changes

- Findings are ordered by their actual position in the work and numbered sequentially from 1 to the final finding.
- Existing stale finding numbers returned by a model are discarded before export.
- Each red number is placed beside the exact sentence or paragraph to which the correction applies.
- Native comments are grouped only when findings share the same exact evidence span.
- Comment anchors are expanded to safe word or sentence boundaries, so numbers cannot split words.
- Export-time placeholder findings are added to the canonical review before the report is generated, keeping report, native comments, inline annotations, and correction lists on one sequence.
- Student-facing language now uses “the study”, “the work”, or “the submitted work”, not “the uploaded document”.
- Level statements use the actual standard, for example “At PhD level” or “At MPhil level”, not “the selected level”.
- Native comments now state the issue, assessment, academic consequence, level-specific expectation, required correction, and a current-study example where useful.
- Inline annotations now provide a detailed blue supervisory explanation corresponding to the Detailed Professional Findings, while the affected source passage and number remain red.
- Results chapters receive deterministic checks of statistical accuracy and method-specific reporting adequacy.

## Statistical and analytical checks added

Where the relevant information is reported, the app now checks:

- coefficient, standard error, and t-statistic reconciliation
- coefficient and confidence-interval consistency
- R², F-statistic, degrees of freedom, sample size, and predictor-count consistency
- p-value and significance interpretation
- coefficient sign and narrative interpretation
- frequency, percentage, and sample-size reconciliation
- valid ranges for R², p-values, percentages, and reliability coefficients
- moderation interaction terms, incremental variance, conditional effects, simple slopes, Johnson–Neyman evidence, or interaction plots as applicable
- mediation indirect effects and bootstrap confidence intervals
- regression assumptions, multicollinearity, residual diagnostics, and uncertainty reporting
- SEM or PLS-SEM separation of measurement and structural models and validity evidence
- qualitative evidence, coding support, and trustworthiness procedures

The audit distinguishes verified inconsistencies from reporting omissions and matters requiring original analytical output.

## Files added

- `app/finding_order.py`
- `app/reviewer_language.py`
- `tests/test_expert_sequential_detailed_review_v19921.py`
- `UPDATED_FILES_v1.9.9.21.md`

## Main files updated

- `app/academic_ai_engine.py`
- `app/ai_prompts.py`
- `app/annotated_exporter.py`
- `app/comment_quality.py`
- `app/deterministic_supervisory_checklist.py`
- `app/inline_annotated_exporter.py`
- `app/main.py`
- `app/professional_review_pipeline.py`
- `app/report_exporter.py`
- `app/review_engine.py`
- `app/statistical_review.py`
- `app/ucc_section_contract.py`
- `app/static/app.js`
- `app/templates/index.html`
- `.env.example`
- `vprofessor-openai-worker.env.example`
- `render.yaml`
- `tests/test_native_comment_export_v187.py`
- `tests/test_professional_review_pipeline_v19919.py`
- `tests/test_report_all_material_corrections.py`
