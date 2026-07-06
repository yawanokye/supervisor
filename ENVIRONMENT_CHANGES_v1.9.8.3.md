# Environment changes for v1.9.8.3

Use `supervisor-v1.9.8.3-render.env.example` as the complete replacement environment for both the Render web service and background worker.

The four new degree-depth variables are:

```env
VPROF_RESEARCH_MASTERS_DEEP_REVIEW=true
AI_RESEARCH_MASTERS_MAX_OUTPUT_TOKENS=9000
AI_RESEARCH_MASTERS_AUDIT_MAX_OUTPUT_TOKENS=6500
OPENAI_RESEARCH_MASTERS_AUDIT_REASONING_EFFORT=high
```

In the Balanced profile:

- Non-Research Master’s Standard review uses DeepSeek V4 Flash plus one GPT-5.4 mini audit.
- Research Master’s/MPhil Standard review uses DeepSeek V4 Pro plus one bounded GPT-5.4 expert audit.
- The MPhil path does not repeat the complete first pass and does not add an automatic paid retry.

Keep the existing v1.9.8.2 public-comment quality settings enabled. Rotate all placeholders for API keys, administrator password and `SESSION_SECRET` before deployment.
