# V-Professor 2.7.2

## Native-comment reconciliation hotfix

This release fixes export-stage failures where canonical finding numbers were present in the review ledger and report but were omitted from native Word comments after grouped-comment deduplication, item limits, text shortening or anchor fallback.

### Corrections

- Adds one lossless native fallback comment for every canonical finding number omitted by normal placement.
- Bypasses grouped-comment deduplication and item limits only during final reconciliation.
- Keeps the canonical number at the beginning of each fallback comment.
- Preserves the completed academic review and provider checkpoints during export recovery.
- Replaces API-key guidance with export-specific recovery guidance when the failure stage is `document-export`.
- Does not repeat the paid academic AI pass during recovery.

### Recovery

Deploy this version to the web service and worker, then select **Recover** once on the retained job. The saved review findings and upload will be reused.
