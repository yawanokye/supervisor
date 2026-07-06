# Updated Files - v1.9.8.7

## Runtime
- `app/annotated_exporter.py`
  - Adds section-level native Word comments for every reviewed section/subsection.
  - Anchors section review comments to exact headings where possible.
  - Keeps issue-specific comments separate from coverage comments.
  - Uses the stored section assessment so the student can see that each section was reviewed even where no material issue was exported.

## Tests
- `tests/test_auto_retry_no_pause_v196.py`
- `tests/test_native_comment_export_v187.py`
  - Updated the annotation export version assertion.

## No environment change
The existing v1.9.8.6 environment remains valid.
