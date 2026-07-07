# Environment Changes — v1.9.9.7

Use these settings with the combined OpenAI pipeline:

```env
AI_STRUCTURED_OUTPUT_RETRIES=1
AI_FAST_REQUEST_TIMEOUT_SECONDS=240
AI_SECTION_BATCH_SIZE=2
AI_LIGHT_SECTION_BATCH_SIZE=3
AI_CHAPTER_PACKET_MAX_CHARS=80000
AI_STANDARD_MAX_OUTPUT_TOKENS=9000
```

Keep the combined OpenAI route enabled:

```env
VPROF_COMBINED_APP_PIPELINE=true
VPROF_ENABLE_OPENAI=true
VPROF_ENABLE_DEEPSEEK=false
VPROF_EXPERT_PROVIDER_MODE=combined_openai_pipeline
```

## Why these changes matter

The prior run showed OpenAI returned `200 OK`, so the key and provider were working. The crash occurred after the model response, when the app attempted to validate the structured review payload. These settings make the response smaller, give the provider more time, and permit one schema-repair retry.
