# Supervisor Assistant v1.8.7

## Purpose

Version 1.8.7 ensures that all supervisory annotations appear in native Microsoft Word review comment boxes rather than being inserted into the thesis text.

## Updated files

### `app/annotated_exporter.py`

- Uses `Document.add_comment()` for every annotation.
- Anchors exact quotations by splitting runs without changing their visible formatting.
- Anchors paragraph-level findings to the relevant paragraph.
- Anchors table findings to the actual table caption or table content.
- Anchors missing-section and document-level findings to existing text.
- Removes inline green comments, appended review-note sections and red recolouring.
- Adds the version constant `1.8.7-native-comments`.

### `app/main.py`

- Updates the application and health version to 1.8.7.
- Stores the annotation export version and mode in the review summary.
- Regenerates older annotated files during download when the original DOCX remains in persistent job storage.
- Prevents a legacy inline-comment document from being served when it cannot be safely regenerated.

### `tests/test_native_comment_export_v187.py`

- Confirms that the visible document body and tables are unchanged.
- Confirms that comments are stored in `word/comments.xml`.
- Confirms that comment ranges exist in the document XML.
- Confirms that no green or red annotation text is inserted.
- Confirms that unplaced feedback remains in native Word comments.

## Deployment

Use **Clear build cache & deploy** on Render. Keep `python-docx==1.2.0` and retain the persistent review storage. Existing completed reviews can be upgraded when their saved source DOCX is still available. Otherwise, submit a fresh review.
