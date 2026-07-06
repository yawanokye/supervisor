# Environment Changes v1.9.8.9

v1.9.8.9 introduces an expert DeepSeek V4 Pro-only route for supervisory review.

## New variables

```env
VPROF_EXPERT_PROVIDER_MODE=deepseek_v4_pro_only
VPROF_FORCE_DEEPSEEK_V4_PRO=true
```

## Recommended expert configuration

```env
VPROF_ROUTING_PROFILE=quality
VPROF_ENABLE_OPENAI=false
VPROF_ENABLE_DEEPSEEK=true
VPROF_ENABLE_SELECTIVE_ESCALATION=false
DEEPSEEK_FAST_MODEL=deepseek-v4-pro
DEEPSEEK_QUALITY_MODEL=deepseek-v4-pro
DEEPSEEK_REVIEW_MODEL=deepseek-v4-pro
DEEPSEEK_ADVANCED_MODEL=deepseek-v4-pro
DEEPSEEK_THINKING_ENABLED=true
DEEPSEEK_REASONING_EFFORT=max
DEEPSEEK_ADVANCED_PRIMARY_REASONING_EFFORT=max
DEEPSEEK_ADVANCED_REASONING_EFFORT=max
AI_RESEARCH_MASTERS_MAX_OUTPUT_TOKENS=12000
AI_RESEARCH_MASTERS_AUDIT_MAX_OUTPUT_TOKENS=9000
VPROF_STANDARD_RESEARCH_MASTERS_MIN_FINDINGS=22
AI_CHAPTER_REVIEW_CONCURRENCY=2
AI_CHAPTER_RECOVERY_CONCURRENCY=1
AI_SECTION_BATCH_SIZE=3
AI_RECOVERY_BATCH_SIZE=4
AI_MAX_RECOVERY_BATCHES=3
AI_MAX_UNRESOLVED_SECTION_FALLBACKS=2
```

## Why OpenAI is disabled in this file

This profile is intended to test and deploy DeepSeek V4 Pro as the sole supervisory review model. If OpenAI remains enabled, the router will still honour the Pro-only mode for supervisory stages, but disabling OpenAI makes the deployment behaviour easier to audit.

External examination remains separately governed and can be re-enabled if required.
