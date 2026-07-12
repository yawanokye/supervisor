# VProfessor v1.9.9.27 — Final Human Supervisory and Examiner Release

## Purpose

This release adds a final human-supervisory editor to the systematic coverage, section-contract, measurement and statistical-audit pipeline. It is designed to make the review read like the work of an experienced supervisor or examiner without reducing academic depth.

## Added

- `app/human_supervisory_editor.py`
- `tests/test_human_supervisory_editor_v19927.py`

## Updated

- `app/final_review_quality.py`
- `app/finding_order.py`
- `app/annotated_exporter.py`
- `app/student_friendly_review.py`
- `app/inline_annotated_exporter.py`
- `.env.example`
- `vprofessor-openai-worker.env.example`
- `render.yaml`
- `CHANGELOG.md`
- `tests/test_native_comment_export_v187.py`

## Main behaviour

1. Review every relevant section, subsection, paragraph, table and analytical model.
2. Validate findings against the whole study.
3. Consolidate duplicate root causes.
4. Apply human academic judgement.
5. Rewrite retained findings in natural supervisor language.
6. Validate examples against the current study and chapter.
7. Confirm exact anchors and safe marker positions.
8. Sort by physical document position and number from 1 to N.
9. Generate all delivery outputs from the same canonical ledger.

## New environment settings

```env
VPROF_HUMAN_SUPERVISORY_EDITOR=true
VPROF_HUMAN_ROOT_CAUSE_CONSOLIDATION=true
VPROF_HUMAN_JUDGEMENT_PASS=true
```

These settings should be applied to both the web service and background worker.
