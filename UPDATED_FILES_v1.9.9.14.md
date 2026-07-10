# VProfessor v1.9.9.14 Update: Additional Comments Label and Numbered Text References

## Purpose
This update corrects the native and inline annotated DOCX export so grouped comments remain professional while still allowing students to trace each numbered item to the exact sentence or paragraph that needs revision.

## Behaviour changed
- The missing-section bottom note heading now reads `Additional comment(s):` instead of `Supervisor inline note on missing section(s):`.
- Grouped native Word comments no longer use phrases such as `Applies to the marked passage beginning...`.
- When a native Word comment contains multiple numbered items, matching red reference markers such as `[1] [2]` are inserted beside the anchored sentence or paragraph in the document body.
- The numbered items inside the native Word comment box are still shown in red so students can match the red text references to the numbered feedback.
- Context guidance now uses `For example, ...` rather than `Context example:`.
- The inline annotated DOCX now handles the same grouped-comment wording and does not expose internal rich-text markers.

## Files updated
- `app/annotated_exporter.py`
- `app/inline_annotated_exporter.py`
- `tests/test_native_comment_export_v187.py`
- `UPDATED_FILES_v1.9.9.14.md`

## Environment values to keep
```env
VPROF_NATIVE_COMMENT_STYLE=anchored_grouped
VPROF_EXPORT_ONE_COMMENT_PER_FINDING=false
VPROF_COMMENT_MERGE_BY_SECTION=true
VPROF_MAX_ITEMS_PER_NATIVE_COMMENT=3
VPROF_INCLUDE_SECTION_REVIEW_COMMENTS=false
VPROF_SPLIT_RELATED_CONCERNS_INTO_SEPARATE_COMMENTS=false
VPROF_VERIFY_DOCX_COMMENT_COUNT=true
VPROF_SHOW_FINDING_COMMENT_RECONCILIATION=true
VPROF_MISSING_SECTION_INLINE_BOTTOM=true
VPROF_NATIVE_GROUP_LOCATION_MARKERS=true
```

## Tests
Targeted tests passed:

```text
15 passed
```
