# VProfessor inline export repair

The worker starts the retained review and reaches inline document generation. Its traceback identifies a reconciliation error when an inline action lacks a verified anchor. This is an export failure, not evidence that the saved academic review needs to run again.

## Repair

The inline exporter now preserves the original source text before adding red highlighting and finding-number markers. A note that needs to be restored can therefore be checked against the same original text that passed placement validation. Restoration also avoids adding a second reference marker to a passage that was already marked.

A genuinely absent section has no source passage to quote. If the normal missing-section end note is disabled or omitted, final reconciliation creates an explicitly labelled reviewer addition for that action. It does not place the comment on an unrelated thesis paragraph. Ordinary findings with unverifiable quotations continue to stay in the report for manual location checking.

The traceback's exact RuntimeError was reproduced in both cases using the previous exporter. The production job's full findings are not available here, so the patch does not claim to have inspected that job's precise failing finding. Future unresolved placement errors identify the canonical finding number in the traceback.

## Deploy and recover

Deploy the complete `supervisor-main` directory and restart both the web service and the background worker. Keep the existing database, uploaded files and checkpoints. The worker must run the updated code, since the failure is inside the worker rather than the browser page.

Then open Review history and select Recover for the existing failed job. Do not re-upload the thesis for this export repair. The assembled delivery checkpoint and provider checkpoints are retained. Tests recover failures in native export and inline export without calling academic analysis, the academic reviewer, the final consistency audit or comment polishing again.

No new dependencies, environment variables or database migration are introduced by this hotfix. The earlier background, Flex/Batch, readiness and scholarly-discovery features are included in the full package.

## Changed files

- `app/inline_annotated_exporter.py` contains the export repair and a new inline export version.
- `app/main.py` updates the application version to 2.13.1.
- `app/templates/index.html` and `app/templates/portal.html` refresh browser asset identifiers.
- `tests/test_inline_reconciliation_v2131.py` adds five reproduction and placement cases.
- `tests/test_background_economy_v213.py` adds recovery coverage for an inline-stage failure.
- `README.md`, `CHANGELOG.md`, `VALIDATION.md` and `RELEASE_VALIDATION_v2.13.1.txt` describe the patch and validation.

## Validation

172 focused tests passed. Python compilation and JavaScript syntax checks passed. A synthetic inline Word export was rendered and both pages visually inspected. This local validation made no paid API requests and did not deploy the code or recover the production job.
