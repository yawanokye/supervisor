# V-Professor 2.7.2 native-comment reconciliation hotfix

## Failure corrected

The export failed because canonical findings 12, 13 and 16 were present in the final review ledger but were absent from the native Word comments. The v2.7.1 reconciliation path reused the normal grouped-comment formatter. That formatter may legitimately consolidate similar wording, apply an item limit or shorten a long grouped comment. Those presentation rules are appropriate during normal annotation, but they are unsafe as a final reconciliation mechanism because they can suppress a canonical number again.

## Corrections

- Adds a separate lossless reconciliation path for missing native-comment numbers.
- Bypasses grouped-comment deduplication, item limits and grouped-text shortening during final reconciliation.
- Creates one native Word comment for every still-missing canonical finding number.
- Retains the number at the beginning of the comment so the report and Word review pane reconcile exactly.
- Tries the quoted passage first, then the relevant section heading, and uses a stable academic-body paragraph only as the final anchor.
- Keeps normal same-anchor grouping for ordinary comments, so the document does not become over-annotated.
- Replaces provider/API-key advice with export-specific recovery guidance when the failure stage is `document-export`.
- Reuses the completed review and provider checkpoints. Recovery does not repeat the paid academic AI pass.

## Regression coverage

A targeted regression test reproduces the exact missing-number pattern 12, 13 and 16 and confirms that all three are inserted into native Word comments. A second test forces grouped native comments to retain only one item and verifies that final reconciliation restores every omitted canonical number.

## Validation

- 376 automated tests passed in an isolated test database.
- Python compilation passed.
- JavaScript syntax validation passed.
- Render YAML validation passed.
- No database, cache, log or compiled Python files are included in the release ZIP.

## Deployment and recovery

Deploy the same package to the Render web service and background worker. After both deployments finish, open the retained job and select **Recover** once. The job should resume at the DOCX export stage using the saved upload and completed academic review.
