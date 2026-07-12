# VProfessor v1.9.9.28

## Purpose

This release completes the final human-supervisor and examiner presentation layer. It improves semantic fit, study-specific examples, scope review, objective-model guidance, citation/language checks, exact anchors and visible numbering.

## Updated files

- `app/human_supervisory_editor.py`
- `app/final_review_quality.py`
- `app/annotated_exporter.py`
- `app/inline_annotated_exporter.py`
- `.env.example`
- `vprofessor-openai-worker.env.example`
- `render.yaml`
- `CHANGELOG.md`

## Added tests

- `tests/test_final_context_guidance_v19928.py`

## New environment controls

```env
VPROF_SEMANTIC_EXAMPLE_GATE=true
VPROF_CONTEXTUAL_ALIGNMENT_EXAMPLES=true
VPROF_SCOPE_COMPLETENESS_AUDIT=true
VPROF_MICRO_LANGUAGE_CITATION_AUDIT=true
VPROF_EXPORT_ANCHOR_RECONCILIATION=true
```

All controls default to enabled. They should be set on both the web service and worker for an explicit and reproducible deployment.
