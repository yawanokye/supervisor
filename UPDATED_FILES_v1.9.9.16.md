# VProfessor v1.9.9.16, thorough thesis/statistical review upgrade

Updated the app so complete-thesis and multi-chapter reviews are closer to the attached PhD-level reviewed sample.

## Files updated
- `app/academic_ai_engine.py`
- `app/ai_prompts.py`
- `app/thorough_review.py`
- `app/review_enrichment.py`
- `app/ai_config.py`
- `.env.example`
- `vprofessor-openai-worker.env.example`

## What changed
- Adds a deterministic full-thesis audit for methods, results, discussion and statistical reporting.
- Flags model drift where mediation is introduced in a moderation-only study.
- Flags duplicated hypothesis numbering.
- Flags proposal-style future tense in completed methodology chapters.
- Flags missing PROCESS conditional effects/simple slopes/interaction plots.
- Flags incomplete PROCESS Model 3 reporting when lower-order and three-way terms are not clearly shown.
- Flags perceived academic support/institutional support terminology drift.
- Flags incomplete discussion markers such as `NOT DONE`.
- Flags possible R²/F-statistic inconsistencies where the reported values do not mathematically align.
- Flags table-numbering duplication or traceability problems.
- Raises default standard PhD review floor to 58 material findings, with lower but stronger floors for Research Master's and Professional Doctorate.

## Deployment env to add to web and worker
```
VPROF_STANDARD_RESEARCH_MASTERS_MIN_FINDINGS=32
VPROF_STANDARD_PROFESSIONAL_DOCTORATE_MIN_FINDINGS=42
VPROF_STANDARD_PHD_MIN_FINDINGS=58
VPROF_COMMENT_DEPTH_FLOOR_ENABLED=true
VPROF_DEVELOPMENTAL_COMMENTS=true
VPROF_SEQUENTIAL_COMMENT_REFERENCES=true
VPROF_SPECIFIC_CORRECTIONS_REQUIRED_BOTTOM=true
VPROF_NATIVE_COMMENT_STYLE=anchored_grouped
VPROF_MAX_ITEMS_PER_NATIVE_COMMENT=3
VPROF_INCLUDE_SECTION_REVIEW_COMMENTS=false
VPROF_VERIFY_DOCX_COMMENT_COUNT=true
VPROF_SHOW_FINDING_COMMENT_RECONCILIATION=true
```

The branding phrase `Meet V-Prof Priscilla Boafowaa Oppong` was not changed.
