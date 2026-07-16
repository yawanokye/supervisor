# Environment changes, V-Professor v1.9.9.30

## Required production settings

```env
VPROF_ROUTING_PROFILE=quality
VPROF_COMBINED_APP_PIPELINE=true
VPROF_EXPERT_PROVIDER_MODE=combined_openai_pipeline

OPENAI_CLEANING_MODEL=gpt-5.6-terra
OPENAI_SECTION_ANALYSIS_MODEL=gpt-5.6-terra
OPENAI_SECTION_ANALYSIS_FALLBACK_MODEL=gpt-5.6-terra
OPENAI_FINAL_SYNTHESIS_MODEL=gpt-5.6-sol
OPENAI_FINAL_SYNTHESIS_FALLBACK_MODEL=gpt-5.6-terra
OPENAI_PHD_FINAL_SYNTHESIS_MODEL=gpt-5.6-sol
OPENAI_PHD_FINAL_SYNTHESIS_REASONING_EFFORT=high
OPENAI_EXTERNAL_DOMAIN_MODEL=gpt-5.6-terra
OPENAI_EXTERNAL_ADJUDICATOR_MODEL=gpt-5.6-sol

VPROF_ENABLE_SELECTIVE_ESCALATION=true
VPROF_ESCALATE_CONFIDENCE_BELOW=0.78
VPROF_COMMENT_SIMILARITY_THRESHOLD=0.82
VPROF_NATIVE_GROUP_LOCATION_MARKERS=false

AI_FAST_AUDIT_MAX_BATCHES=8
AI_MAX_MAP_INPUT_CHARS=90000
AI_MAX_RETRIES=1
AI_STRUCTURED_OUTPUT_RETRIES=1
AI_FAST_REQUEST_MAX_RETRIES=1
AI_EXTERNAL_ASSESSMENT_REQUEST_MAX_RETRIES=1
AI_STRICT_FAILURE=true
```

## Structural behaviour

No environment flag is required to activate the level rules. They are enforced in code:

- Bachelor’s: standard five-chapter default
- Non-Research Master’s: standard five-chapter default
- Research Master’s/MPhil: standard five-chapter default
- Professional Doctorate: standard five-chapter default
- PhD: variable chapter architecture, subject to complete prescribed-element coverage

The institutional profile is selected in the review form. `generic` is the default. UCC-specific section rules run only when `ucc` is selected.

## Settings removed from the production blueprint

The release removes unsupported or misleading flags from `render.yaml`. The application now logs any unsupported `VPROF_`, `AI_` or `OPENAI_` environment variables at startup so that a deployment cannot silently imply that an inactive safeguard is operating.

## Deployment guidance

Use `render.yaml` as the source of truth for non-secret settings. Keep only secrets and generated credentials in the Render dashboard, including `OPENAI_API_KEY`, `SESSION_SECRET` and database credentials. Avoid defining the same non-secret value in both places.

After deployment, inspect the startup log for:

- application version `1.9.9.30`
- effective cleaning, section, final synthesis, PhD synthesis and external adjudication models
- unsupported environment-variable warnings
- storage and database readiness

Existing database records do not require a migration for this release.
