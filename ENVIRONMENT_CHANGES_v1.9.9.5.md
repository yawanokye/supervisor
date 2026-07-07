# VProfessor v1.9.9.5 environment changes

This release adds an optional combined OpenAI thesis-review pipeline.

```env
VPROF_COMBINED_APP_PIPELINE=true
VPROF_ENABLE_OPENAI=true
VPROF_ENABLE_DEEPSEEK=false
VPROF_EXPERT_PROVIDER_MODE=combined_openai_pipeline
OPENAI_CLEANING_MODEL=gpt-4.1-nano
OPENAI_SECTION_ANALYSIS_MODEL=gpt-5.6-luna
OPENAI_SECTION_ANALYSIS_FALLBACK_MODEL=gpt-5.4-mini
OPENAI_FINAL_SYNTHESIS_MODEL=gpt-5.5
OPENAI_FINAL_SYNTHESIS_FALLBACK_MODEL=gpt-5.4
```

GPT-5.6 Luna is a limited-preview model. Keep `OPENAI_SECTION_ANALYSIS_FALLBACK_MODEL=gpt-5.4-mini` unless your OpenAI organisation has confirmed API access to `gpt-5.6-luna`.

The live review path remains synchronous. Batch API support is documented as a future queued workflow because Batch has an asynchronous completion window and is not appropriate for a live spinner review.
