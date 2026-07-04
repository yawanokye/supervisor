# Supervisor Assistant v1.8.4

## Faster external examination without reducing review safeguards

The former external-assessment critical path was:

1. Foundation and evidence assessment in parallel
2. Corrections schedule
3. Final recommendation

A single large evidence request could hold the job at 87%, and the corrections and decision stages then ran one after another.

v1.8.4 uses two parallel waves:

### Parallel wave 1

- Foundation, literature and methodology
- Results, discussion, conclusions and structural alignment
- Academic writing, ethics, originality and publication potential

### Parallel wave 2

- Corrections and oral examination questions
- Independent examiner decision

The detailed corrections are merged with the decision before the deterministic recommendation-consistency check. This keeps the final award recommendation aligned with verified correction severity.

## Quality safeguards retained

- Complete document manifest and functional chapter map
- Balanced source-evidence selection
- Exact evidence-ID validation
- Unsupported numerical-claim detection
- Reference-risk allegation safeguards
- Presence and absence contradiction checks
- Coverage-based recommendation withholding
- Deterministic recommendation consistency adjustment
- Durable per-stage checkpoints and recovery

## New production defaults

```text
AI_EXTERNAL_ASSESSMENT_FOUNDATION_MAX_OUTPUT_TOKENS=3400
AI_EXTERNAL_ASSESSMENT_EVIDENCE_MAX_OUTPUT_TOKENS=3400
AI_EXTERNAL_ASSESSMENT_INTEGRITY_MAX_OUTPUT_TOKENS=2800
AI_EXTERNAL_ASSESSMENT_CORRECTIONS_MAX_OUTPUT_TOKENS=3400
AI_EXTERNAL_ASSESSMENT_DECISION_MAX_OUTPUT_TOKENS=2200
AI_EXTERNAL_ASSESSMENT_STAGE_TIMEOUT_SECONDS=600
AI_EXTERNAL_ASSESSMENT_REQUEST_TIMEOUT_SECONDS=240
AI_EXTERNAL_ASSESSMENT_REQUEST_MAX_RETRIES=0
```

## Updated files

- `app/assessment_schemas.py`
- `app/ai_config.py`
- `app/ai_providers.py`
- `app/external_assessment.py`
- `app/main.py`
- `.env.example`
- `tests/test_external_assessment_staging.py`
- `tests/test_checkpoint_resume_ui.py`
- `CHANGELOG.md`

## Recovery after deployment

Deploy v1.8.4 with the existing database and persistent disk. Open Review History and select **Recover stalled stage** once. The document extraction and completed academic-review checkpoints are retained. The external examination is regenerated under the new parallel workflow because the old 87% external checkpoint belongs to the superseded pipeline.
