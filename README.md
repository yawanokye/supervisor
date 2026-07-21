# V-Professor Supervisory Review 2.3.2

V-Professor provides degree-calibrated supervisory review and external assessment for Bachelor’s, Non-Research Master’s, Research Master’s/MPhil, Professional Doctorate and PhD work.

## Final professional review workflow

- Supervisors may review a complete chapter or select individual sections after the document is scanned.
- Bachelor’s, Master’s and Professional Doctorate work uses a five-chapter structure by default.
- PhD work may use any defensible chapter arrangement, but the system verifies the required doctoral elements and their integration.
- Every released finding must have current-document evidence, an exact sentence or paragraph anchor, a direct action and a completion test.
- Findings tied to the same exact passage share one numbered native Word comment box. Findings tied to different sentences remain separate.
- Native comments, inline annotations and the appended correction schedule are generated from one canonical finding ledger.
- Inline annotations are concise so the student’s text remains readable. The native comments and report retain the full issue, academic reason, action and verification requirement.
- Methods, measurements, tables and statistical results receive route-specific checks for accuracy, adequacy and analytical appropriateness. Definitive recalculation still requires the original data, syntax and software output.

## Quality safeguards in 2.3.2

- Reads visible tracked insertions and detects unresolved supervisor or editor instructions embedded in the academic text.
- Detects incomplete citation fragments such as an unfinished author-date citation.
- Prevents organisation-of-study sentences such as “Chapter two reviews…” from being misclassified as a new chapter heading.
- Strengthens Chapter One review of the background, current context, problem evidence, research gap, constructs, purpose, objectives, questions, significance, scope and limitations.
- Detects construct drift, one-firm versus several-firms inconsistency, unsupported causal wording, unnamed study settings and common language or citation errors.
- Uses issue-specific verification rather than one generic verification sentence.
- Deduplicates genuine root causes while preserving distinct findings on different sentences, tables or statistical defects.
- Protects decimals, p-values, equations, citations, URLs and DOI strings during annotation.
- Reconciles finding numbers only after evidence filtering, consolidation and anchor validation.

## Cost-efficient routing

- Deterministic evidence checks handle high-confidence structural, citation and language defects without another model call.
- Routine Light and Standard review uses GPT-5.6 Terra.
- Standard review does not automatically escalate to a second premium synthesis model.
- A second paid accuracy audit is limited to validity-critical, statistical, methodological, causal or low-confidence major findings.
- Standard chapter review is limited to one compact accuracy-audit batch. Findings outside that paid batch still pass deterministic evidence and export gates.
- GPT-5.6 Sol is reserved for PhD final synthesis and external-examiner adjudication, or selective escalation in Advanced review.
- Output limits, batching and checkpoint reuse reduce repeated paid processing after recovery or redeployment.

## Deployment

The web service runs with:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

The background worker runs with:

```bash
python -m app.worker
```

Both services must use the same PostgreSQL database and the API key for the selected provider. Deploy the complete package and submit unfinished reviews as new jobs because the 2.3.2 packet and checkpoint identifiers differ from earlier versions. See `DEPLOYMENT.md` and `.env.example`.

## AI provider selection

V-Professor 2.3.2 can use OpenAI or DeepSeek without code changes. Set the same provider variables on the web service and background worker.

Use OpenAI:

```env
VPROF_PRIMARY_PROVIDER=openai
VPROF_ENABLE_OPENAI=true
VPROF_ENABLE_DEEPSEEK=false
OPENAI_API_KEY=your-key
VPROF_FALLBACK_PROVIDER=none
VPROF_PROVIDER_FAILOVER=false
```

Use DeepSeek V4 Pro:

```env
VPROF_PRIMARY_PROVIDER=deepseek
VPROF_ENABLE_DEEPSEEK=true
VPROF_ENABLE_OPENAI=false
DEEPSEEK_API_KEY=your-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_REVIEW_MODEL=deepseek-v4-pro
DEEPSEEK_ADVANCED_MODEL=deepseek-v4-pro
DEEPSEEK_QUALITY_MODEL=deepseek-v4-pro
DEEPSEEK_FAST_MODEL=deepseek-v4-flash
DEEPSEEK_THINKING_ENABLED=true
DEEPSEEK_PRIMARY_THINKING_ENABLED=false
DEEPSEEK_AUDIT_THINKING_ENABLED=true
DEEPSEEK_REASONING_EFFORT=high
DEEPSEEK_ADVANCED_PRIMARY_REASONING_EFFORT=max
DEEPSEEK_TRUNCATION_RECOVERY=true
DEEPSEEK_TRUNCATION_RETRY_MULTIPLIER=1.6
DEEPSEEK_MAX_OUTPUT_TOKENS=12000
DEEPSEEK_PRIMARY_MAX_OUTPUT_TOKENS=7000
DEEPSEEK_SINGLE_TARGET_RECOVERY_MAX_OUTPUT_TOKENS=4200
DEEPSEEK_COMPACT_ISSUE_LIMIT_PER_TARGET=2
DEEPSEEK_COVERAGE_PARAGRAPHS_PER_UNIT=3
DEEPSEEK_COVERAGE_UNIT_MAX_CHARS=7000
DEEPSEEK_COVERAGE_TABLE_ROWS_PER_UNIT=4
DEEPSEEK_COVERAGE_UNITS_PER_REQUEST=1
DEEPSEEK_COVERAGE_HIGH_RISK_UNITS_PER_REQUEST=1
DEEPSEEK_COVERAGE_REQUEST_MAX_CHARS=9000
VPROF_FALLBACK_PROVIDER=none
VPROF_PROVIDER_FAILOVER=false
```

The primary chapter pass keeps hidden thinking disabled so reasoning tokens do not cut off the required JSON object. Bounded audits keep thinking enabled. To use V4 Pro for every stage, set `DEEPSEEK_FAST_MODEL=deepseek-v4-pro`. To permit a controlled fallback, enable both providers, set `VPROF_PROVIDER_FAILOVER=true`, and choose `VPROF_FALLBACK_PROVIDER=openai` or `deepseek`.

`VPROF_PRIMARY_PROVIDER` is authoritative even when `VPROF_COMBINED_APP_PIPELINE=true`.
