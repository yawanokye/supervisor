# VProfessor v1.9.9.25 — Final Professional Review Quality Release

## Purpose

This release completes the student-facing supervisory and examiner review upgrade. It converts the specification-aligned diagnostic engine into a concise, natural and fully reconciled final review workflow.

## Core corrections

- Builds one canonical final finding set after global verification, false-positive removal and duplicate consolidation.
- Sorts findings by their physical position in the study and assigns the final sequence only once.
- Uses the same sequence in the report, native Word comments, red markers, inline annotations and correction tracker.
- Defaults to one precisely anchored native comment per finding.
- Places genuinely missing sections in the chapter correction tracker instead of attaching them to an unrelated sentence.
- Suppresses routine section-level PASS comments in the Word Review pane.
- Removes repetitive programme labels such as “At PhD level” and “At MPhil level” from routine comments while retaining programme calibration internally.
- Replaces repetitive traceability language with direct instructions about what must match, be documented or be reproduced.
- Distinguishes Chapter One background writing from Chapter Two literature review:
  - Chapter One uses selective evidence to move from the broad context to the specific problem.
  - Chapter Two requires deep critical synthesis of theories, methods, findings, limitations and disagreements.
- Rejects false missing-section findings when an equivalent heading exists anywhere in the study.
- Rejects comments that criticise a purpose statement or research-question section merely for being concise.
- Derives table and subsection labels from the actual evidence location.
- Consolidates overlapping findings about the same table, model or passage.
- Keeps native comments concise while the report provides a decision-led summary rather than duplicating every comment.
- Preserves detailed deterministic checking of measurement, scoring, regression, moderation, mediation, SEM, PLS-SEM and table-to-narrative consistency.

## Added

- `app/final_review_quality.py`
- `tests/test_final_review_quality_v19925.py`
- `UPDATED_FILES_v1.9.9.25.md`

## Updated

- `app/academic_ai_engine.py`
- `app/academic_review_guide.py`
- `app/ai_prompts.py`
- `app/annotated_exporter.py`
- `app/deterministic_supervisory_checklist.py`
- `app/inline_annotated_exporter.py`
- `app/professional_review_pipeline.py`
- `app/report_exporter.py`
- `app/review_enrichment.py`
- `app/student_friendly_review.py`
- `app/supervisory_review_algorithm.py`
- `app/ucc_section_contract.py`
- `.env.example`
- `vprofessor-openai-worker.env.example`
- `render.yaml`
- `CHANGELOG.md`
- relevant review and export tests

## Recommended final settings

```env
VPROF_NATIVE_COMMENT_STYLE=one_per_finding
VPROF_EXPORT_ONE_COMMENT_PER_FINDING=true
VPROF_COMMENT_MERGE_BY_SECTION=false
VPROF_MAX_ITEMS_PER_NATIVE_COMMENT=1
VPROF_INCLUDE_SECTION_REVIEW_COMMENTS=false
VPROF_SPLIT_RELATED_CONCERNS_INTO_SEPARATE_COMMENTS=true
VPROF_COMMENT_MAX_CHARS=1100

VPROF_ADD_QUALITY_EXPECTATION_TO_COMMENTS=false
VPROF_INCLUDE_DEGREE_LABEL_IN_COMMENTS=false
VPROF_INTRO_BACKGROUND_SYNTHESIS_MODE=focused
VPROF_FINAL_COMMENT_RECONCILIATION=true

VPROF_REPORT_INCLUDE_DETAILED_FINDINGS=false
VPROF_REPORT_MAX_DETAILED_FINDINGS=30

VPROF_FINDING_QUOTAS_ENABLED=false
VPROF_COMMENT_DEPTH_FLOOR_ENABLED=false
VPROF_STANDARD_NON_RESEARCH_MIN_FINDINGS=0
VPROF_STANDARD_RESEARCH_MASTERS_MIN_FINDINGS=0
VPROF_STANDARD_PROFESSIONAL_DOCTORATE_MIN_FINDINGS=0
VPROF_STANDARD_PHD_MIN_FINDINGS=0
```
