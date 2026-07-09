# VProfessor v1.9.9.11: Numbered grouped native comments

This patch corrects the over-commenting introduced by one-comment-per-finding export.

## What changed

- Native Word comments now default to a professional grouped style.
- Related findings are merged into one native comment box per section/anchor.
- Items inside each comment box are numbered, for example `1. ... 2. ...`.
- Each merged comment includes one context-specific example rather than repeating examples under every finding.
- Section-level coverage comments are disabled by default because they created generic repetition when issue findings already existed.
- Dashboard wording now uses `DOCX comment boxes` to distinguish native comment boxes from total findings.
- The full report still preserves all findings, while the DOCX presents them in a cleaner supervisor-friendly format.
- The branding text `Meet V-Prof Priscilla Boafowaa Oppong` was not changed.

## Recommended environment values

```env
VPROF_NATIVE_COMMENT_STYLE=numbered_grouped
VPROF_EXPORT_ONE_COMMENT_PER_FINDING=false
VPROF_COMMENT_MERGE_BY_SECTION=true
VPROF_MAX_ITEMS_PER_NATIVE_COMMENT=4
VPROF_INCLUDE_SECTION_REVIEW_COMMENTS=false
VPROF_SPLIT_RELATED_CONCERNS_INTO_SEPARATE_COMMENTS=false
VPROF_VERIFY_DOCX_COMMENT_COUNT=true
VPROF_SHOW_FINDING_COMMENT_RECONCILIATION=true
```

Apply these values to both the web service and the background worker.
