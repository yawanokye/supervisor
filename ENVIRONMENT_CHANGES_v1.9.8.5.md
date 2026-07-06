# Environment changes for v1.9.8.5

Use `supervisor-v1.9.8.5-render.env.example` or the complete environment file as the replacement environment on both the Render Web Service and Background Worker.

## New settings

```env
VPROF_DEVELOPMENTAL_COMMENTS=true
VPROF_COMMENT_DEPTH_FLOOR_ENABLED=true
VPROF_STANDARD_NON_RESEARCH_MIN_FINDINGS=14
VPROF_STANDARD_RESEARCH_MASTERS_MIN_FINDINGS=18
VPROF_STANDARD_PROFESSIONAL_DOCTORATE_MIN_FINDINGS=22
VPROF_STANDARD_PHD_MIN_FINDINGS=26
```

## Changed settings

```env
VPROF_COMMENT_MAX_CHARS=980
VPROF_COMMENT_SIMILARITY_THRESHOLD=0.58
```

`VPROF_COMMENT_MAX_CHARS` was raised because native comments now include the issue, academic consequence and revision action. The similarity threshold was tightened so repeated alignment comments are consolidated before export.

## No database migration

No database migration is required. Existing users, balances, stored reviews and persistent review files remain compatible.
