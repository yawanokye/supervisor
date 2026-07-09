# VProfessor v1.9.9.12, evidence-anchored grouped native comments

This patch keeps the professional numbered native comment boxes, but anchors them to the exact passage, sentence, table, or nearest insertion point that needs revision. It replaces the earlier section-heading grouping, which made it difficult for students to track where changes should be made.

## Main changes

- Default native comment style changed to `anchored_grouped`.
- Related findings are merged only when they share the same evidence passage.
- Grouped comments are anchored to the exact quote or best sentence where possible.
- If the evidence points to a heading, the exporter moves the comment to the next substantive paragraph or to the nearest useful insertion point.
- Missing-section findings, such as Definition of Terms, are placed near the expected insertion area instead of on the chapter heading.
- Comments now keep more detailed guidance and a context-specific example where available.
- Decimal headings and table numbers, such as `4.2` and `Table 4.1`, are preserved in comments.
- Duplicate guidance inside a comment is removed.

## Recommended environment values

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

## Branding

The public greeting remains unchanged:

`Meet V-Prof Priscilla Boafowaa Oppong`
