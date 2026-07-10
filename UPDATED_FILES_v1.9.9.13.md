# VProfessor v1.9.9.13 Update: Anchored Grouped Native Comments with Missing-Section Inline Notes

## Purpose
This update refines the review export behaviour so the native DOCX remains professional, traceable and easy for students to act on.

## Behaviour changed
- Missing required chapter sections are no longer attached as native comments to unrelated headings or paragraphs.
- Missing-section feedback is inserted as a blue inline note at the bottom of the reviewed chapter.
- Grouped native comments remain merged to avoid excessive comment bubbles, but each numbered item now begins with a red location cue inside the Word comment box.
- Context-specific examples are retained in grouped native comments and in the inline annotated DOCX.
- Inline annotated DOCX now uses the same review finding attribution and missing-section handling as the native annotated DOCX.

## Files updated
- `app/annotated_exporter.py`
- `app/inline_annotated_exporter.py`
- `.env.example`
- `vprofessor-openai-worker.env.example`
- `tests/test_native_comment_export_v187.py`
- `UPDATED_FILES_v1.9.9.13.md`

## New environment controls
```env
VPROF_MISSING_SECTION_INLINE_BOTTOM=true
VPROF_NATIVE_GROUP_LOCATION_MARKERS=true
```

Keep these existing values for the professional export style:

```env
VPROF_NATIVE_COMMENT_STYLE=anchored_grouped
VPROF_EXPORT_ONE_COMMENT_PER_FINDING=false
VPROF_COMMENT_MERGE_BY_SECTION=true
VPROF_MAX_ITEMS_PER_NATIVE_COMMENT=3
VPROF_INCLUDE_SECTION_REVIEW_COMMENTS=false
VPROF_SPLIT_RELATED_CONCERNS_INTO_SEPARATE_COMMENTS=false
VPROF_VERIFY_DOCX_COMMENT_COUNT=true
VPROF_SHOW_FINDING_COMMENT_RECONCILIATION=true
```

## Tests
Targeted tests passed:

```text
12 passed
```
