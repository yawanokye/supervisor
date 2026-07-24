# V-Professor 2.7.3

## Annotated export completion and timing update

This release fixes a completion-path defect in the annotated delivery stage and adds an approximate time-to-completion estimate to the live review progress response.

### Root causes corrected

1. After both annotated DOCX files had been generated, validated and saved, the database completion query incorrectly called `.first()` twice. The second call raised an exception on the returned `ReviewRecord`, causing the completed export to be treated as an interrupted job and queued for recovery.
2. Export recovery rebuilt both annotated documents even when one valid artifact had already been saved.
3. The user interface remained at 98% without an estimate while DOCX comments and inline notes were being generated.

### Changes

- Corrected the database completion query.
- Reuses a saved native or inline artifact when its reconciliation audit passes.
- Saves each valid annotated artifact immediately, so a later failure does not discard completed export work.
- Updates progress to 99% after the native Word comments are complete.
- Adds elapsed time, approximate remaining seconds and estimated completion time to the job status response.
- Displays an approximate remaining-time message in the review progress panel.
- Logs annotated export duration and output counts.
- Keeps all academic checkpoints unchanged, so export-only recovery does not call the AI provider again.

### Time estimate behaviour

The estimate is approximate. It uses review depth, estimated pages, current progress and current stage. During document export, it estimates local DOCX generation separately from the academic AI review. Queued jobs do not receive a completion estimate because queue waiting time depends on worker load.

### Validation

- 380 automated tests passed.
- Python compilation passed.
- JavaScript syntax validation passed.
- Regression tests cover the double-`.first()` completion defect, export-stage ETA fields and reuse of individually saved annotated artifacts.
