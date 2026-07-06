# Environment changes for v1.9.8.6

No new environment variable is required from v1.9.8.5.

Keep these existing v1.9.8.5 settings enabled:

```env
VPROF_DEVELOPMENTAL_COMMENTS=true
VPROF_COMMENT_DEPTH_FLOOR_ENABLED=true
VPROF_COMMENT_MAX_CHARS=980
VPROF_COMMENT_SIMILARITY_THRESHOLD=0.58
VPROF_STANDARD_NON_RESEARCH_MIN_FINDINGS=14
VPROF_STANDARD_RESEARCH_MASTERS_MIN_FINDINGS=18
VPROF_STANDARD_PROFESSIONAL_DOCTORATE_MIN_FINDINGS=22
VPROF_STANDARD_PHD_MIN_FINDINGS=26
```

The v1.9.8.6 code now applies the depth floor after public-comment deduplication. This is a code-level correction and does not require a new variable.
