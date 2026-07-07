# Environment Changes – VProfessor v1.9.9.6

No new environment variable is required.

Keep the v1.9.9.5 combined OpenAI pipeline settings, for example:

```env
VPROF_COMBINED_APP_PIPELINE=true
VPROF_ENABLE_OPENAI=true
VPROF_ENABLE_DEEPSEEK=false
VPROF_EXPERT_PROVIDER_MODE=combined_openai_pipeline

OPENAI_CLEANING_MODEL=gpt-4.1-nano
OPENAI_SECTION_ANALYSIS_MODEL=gpt-5.4-mini
OPENAI_SECTION_ANALYSIS_FALLBACK_MODEL=gpt-5.4-mini
OPENAI_FINAL_SYNTHESIS_MODEL=gpt-5.4
OPENAI_FINAL_SYNTHESIS_FALLBACK_MODEL=gpt-5.4
```

After deployment, restart both the Web Service and Worker. Run a new review or recover the interrupted job once.
