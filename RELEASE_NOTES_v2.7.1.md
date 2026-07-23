# V-Professor 2.7.1 Annotated Artifact Recovery

## Problem corrected

A supervisory report could state that numbered comments were attached even when the downloaded DOCX contained only comments inherited from the uploaded source. The old validation counted all Word comments instead of distinguishing newly generated V-Professor comments. The inline annotated document was also generated only on demand and could disappear when the temporary source upload was no longer available.

## Release controls

- Generates native and inline annotated DOCX files as one atomic bundle before marking the review complete.
- Counts current V-Professor comments separately from previous source-document comments.
- Validates every final finding number in both annotated formats.
- Persists both annotated outputs to configured file storage and optional PostgreSQL artifact storage.
- Blocks report-only completion when either annotated document is missing or unreconciled.
- Regenerates older annotated documents from the saved source without repeating the academic provider pass.
- Retains completed academic checkpoints when only document export fails.
- Prevents strict final presentation filters from silently removing a valid finding at a citation or quotation boundary.

## Deployment

Deploy the same package to the Render web service and background worker. Keep the same `DATABASE_URL` and set `VPROF_DB_ARTIFACT_STORAGE=true` on both services unless durable object storage is configured.

For an existing review, open the result and use the native or inline download button. The current exporter will rebuild the annotated document when the saved source DOCX remains available. For a paused or failed document-export job, select **Recover** once. Submit a new review only when the original upload is unavailable.

## Validation

- 374 automated tests passed.
- Python compilation passed.
- JavaScript syntax validation passed.
- Render YAML validation passed.
- A smoke test using a DOCX with previous source comments produced reconciled native and inline annotated outputs.
- Both smoke outputs rendered successfully without clipping or overlap.
