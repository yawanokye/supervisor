# V-Professor Supervisory Review 2.11.0

V-Professor provides degree-calibrated supervisory review and external assessment for Bachelor’s, Non-Research Master’s, Research Master’s/MPhil, Professional Doctorate and PhD work.

## Changes in 2.11.0

Comments now use a passage-specific supervisory voice with varied openings and sentence rhythm. A clear reporting repair can begin with the action. A confirmed contradiction receives a direct diagnosis. A genuine uncertainty can use a focused question followed by an instruction. The system checks repetitive openings, near duplicates, unsupported numbers and loss of corrective actions. It does not manufacture faults or enforce a comment minimum. A bounded prose repair runs only on the released shortlist, and evidence, severity and corrective obligations remain unchanged.

Comment placement now checks the actual source quotation and paragraph or table-row evidence, including its chapter and section. A stale paragraph number is relocated only when the evidence has one verified match. Reconciliation cannot attach a finding to an arbitrary heading, first paragraph or final paragraph. Different sentence findings retain separate ranges, and table-row findings target the quoted cell. If a location cannot be verified, the finding stays in the report with its correction and a manual location notice. Genuine missing-section findings remain in the correction notes. These controls apply to native and inline exports.

Statistical checks recognise declared alpha, model family, signed statistics and reported rounding. Negative adjusted R² is permitted. Cronbach’s negative alpha is investigated rather than labelled impossible. Explicit t, F and chi-square tests can be checked against their degrees of freedom and reported p-values. Bootstrap, one-sided and adjusted tests are excluded from inappropriate recomputation. Logistic output is not forced into an OLS table template.

Blank DOCX cells keep their positions. PDF tables use page geometry, and framework pages are rendered so vector arrows can be supplied to a visual model. Unsupported image formats or text-only models require manual visual verification. Scanned PDFs still require a readable text layer or a separately OCR-processed copy.

Guided chapters share cached source extraction and a reference index. The final merge retains the full internal issue ledger, so a shortened comment list cannot conceal readiness blockers. A material issue in a clean-passage sample expands AI assessment across that chapter’s remaining local units. Structural preflight is reported separately from AI assessment and does not receive a perfect quality score.

The final guided result receives a real bounded cross-chapter consistency audit, with a results ledger and explicit evidence coverage. Partial chapter sequences are labelled accurately. An empty response or unassessed supplied evidence cannot produce a completed audit flag. Completed requests keep stable hashes on resume. Background response IDs are saved before polling and reused after recovery. If temporary provider retention has expired and retrieval returns 404, recovery records that fact and requires a fresh submission. An explicit stop requests cancellation of retained background work.

## Select an OpenAI model

To switch every OpenAI role, including existing per-role settings, use:

```dotenv
OPENAI_MODEL=gpt-6.1-sol
OPENAI_MODEL_MODE=single
VPROF_PRIMARY_PROVIDER=openai
VPROF_ENABLE_OPENAI=true
```

Keep your existing `OPENAI_API_KEY`. Restart both the web service and worker after changing deployment environment variables. New work uses the selected model. Completed checkpoints remain available for recovery.

For efficient separate roles, leave `OPENAI_MODEL` blank and set `OPENAI_EXPERT_MODEL` and `OPENAI_FINAL_AUDIT_MODEL` to `gpt-6.1-sol`, retaining the routine chapter model. If you want a global fallback alongside explicit role settings, use `OPENAI_MODEL_MODE=roles`.

Compatible OpenAI text-model IDs are accepted without editing code. The adapter selects Responses or legacy Chat Completions, adjusts reasoning effort to supported values, and handles explicit parameter incompatibility without silently changing the model. Schema validation remains required when a model needs JSON mode or plain JSON. A model still needs API access and sufficient input/output capacity. Embedding, audio and image-generation models cannot perform a text review.

For an unknown model, set price estimates explicitly, for example:

```dotenv
OPENAI_MODEL_PRICES_JSON={"my-text-model":{"input":2,"cached_input":0.1,"output":10}}
```

Values are USD per million tokens. Bundled prices are estimates and can be overridden. Unknown IDs otherwise inherit role price estimates. Optional `OPENAI_MODEL_CAPABILITIES_JSON` can specify per-model `endpoint`, `reasoning`, `efforts`, `structured`, `vision` and `background` capabilities for a compatible proxy. Endpoint values are `responses` or `chat`.

## Review verification

Run `python -m pytest -q` with a fresh temporary `DATABASE_URL` and `REVIEW_STORAGE_DIR`. Run `python scripts/benchmark_review_quality.py` for six labelled statistical cases, or add `--review path/to/review.json` for descriptive comment metrics.

The included regression suite covers model switching, parameter adaptation, durable background recovery, numerical false positives, geometric tables, natural comments in Word export, duplicate budgets and genuine final-audit coverage.

The automated checks verify implementation and labelled synthetic cases. They do not measure how natural real reviews feel to a human supervisor. Use `REVIEW_QUALITY_CHECK.md` to assess representative theses before expanding production use. Statistical consistency checks do not reproduce an analysis from raw data. A reference-list match does not establish source existence or claim support.

## Current-submission isolation

Every uploaded work is evidence for that review job only. A thesis, dissertation, chapter or benchmark used to test the system remains an example and is never converted into a reusable topic, institution, location, construct or correction rule.

The app rebuilds the study context from the current submission, uses earlier chapters only when they belong to the same work, and applies generic academic, methodological, statistical, language and citation standards.

## Final professional review controls

Version 2.10.0 includes the following release controls:

- deterministic local preflight handles routine structure, navigation, low-risk prose and bookkeeping before paid model review;
- Luna reviews risk-selected high-volume passages while Terra handles decisive research logic and final expert judgement;
- all results tables and statistically sensitive passages remain model-reviewed;
- every detected quantitative conceptual framework receives a mandatory expert alignment audit against the objectives, research questions, hypotheses, theory, variable roles, diagram, model specification and results;
- effect estimation may use any justified regression-class, generalized linear, multilevel, panel, time-series, SEM, PLS-SEM, mediation or moderation model rather than being restricted to OLS;
- low-risk clean-passage quality samples are 5% for Bachelor’s and non-research Master’s work, 10% for Research Master’s/MPhil, and 15% for doctoral work;

- the uploaded document is scanned immediately and a detected-chapter picker lets the supervisor choose where the guided review starts;
- every completed native Word-comment copy becomes the annotation base for the next chapter;
- the final chapter rebuilds one complete annotated thesis from the original document and the merged finding ledger, preventing duplicated comments; and
- chapters before a supervisor-selected starting point remain available as alignment context without being presented as newly reviewed chapters.

- every supervisory upload containing multiple detected chapters now enters the guided chapter sequence, including uploads submitted as Combined chapters;
- the live review screen names the current chapter and states that only that chapter is being reviewed;
- retained multi-chapter jobs from earlier builds are upgraded to guided mode when resumed; and
- internal coverage-packet wording is replaced by clear supervisor-facing progress messages.

- complete theses are reviewed one chapter at a time, with an explicit supervisor-controlled Continue action between chapters;
- each completed chapter report and annotated chapter remains available before the next chapter starts;
- earlier completed chapters and the shared reference list are reused for cross-chapter alignment without reviewing future chapters prematurely;
- a cumulative final thesis result is assembled after the last chapter, with cross-chapter findings, statistical warnings and numbering reconciled;
- preliminary pages, the Table of Contents, navigation lists, acronyms, main chapters, references and appendices are separated before chapter detection;
- visible comments use a human supervisory budget, while repeated and lower-priority instances are grouped in an internal issue ledger;
- “effect” is accepted for appropriate regression-class, SEM, PLS-SEM, mediation and moderation estimates, while explicit causal claims remain design-sensitive;

- native Word-comment and inline annotated DOCX files are generated, validated and persisted as one atomic delivery bundle before a review is released as complete;
- current V-Professor comments are counted separately from comments already present in the uploaded source, so old comments can never make an empty new annotation export pass validation;
- every source-verified annotation finding number must appear in both the native and inline annotated outputs; findings without a verified location remain in the report;
- completed academic-review checkpoints are retained when document export fails, so recovery retries the annotation stage without repeating a paid provider pass;
- older completed reviews can regenerate current annotated outputs at download time when the saved source DOCX remains available;
- natural student-facing comments limited to focused supervisory prose rather than visible labels such as `Issue`, `Problem identified`, `Action required` or `Verification`;
- substantive paragraph anchoring ahead of section-heading anchoring;
- root-cause consolidation for overlapping construct, background, problem-gap and scope findings;
- strict reconciliation between the canonical finding ledger, native Word comments and the appended correction register;
- one Word comment box for related findings tied to the same verified sentence range, with every released finding number represented;
- removal of empty source comments and status labelling where an earlier missing-section comment is visibly addressed;
- checks for generic limitations that do not explain consequences for evidence or conclusions;
- checks for unsupported absolute claims while preserving proportionate academic wording;
- suppression of weak findings based only on concise chapter descriptions or unverified mandatory-section assumptions;
- preservation of exact deterministic findings such as title-purpose drift, setting inconsistency, malformed citations and unresolved document instructions.

## Provider selection

Use the same provider settings on the web service and worker.

### OpenAI

```env
VPROF_PRIMARY_PROVIDER=openai
VPROF_ENABLE_OPENAI=true
VPROF_ENABLE_DEEPSEEK=false
OPENAI_API_KEY=your-key
OPENAI_FAST_MODEL=gpt-5.6-luna
OPENAI_CLEANING_MODEL=gpt-5.6-luna
OPENAI_CHAPTER_MODEL=gpt-5.6-luna
OPENAI_SECTION_ANALYSIS_MODEL=gpt-5.6-luna
OPENAI_EXPERT_MODEL=gpt-5.6-terra
OPENAI_FINAL_AUDIT_MODEL=gpt-5.6-terra
OPENAI_FINAL_SYNTHESIS_MODEL=gpt-5.6-terra
OPENAI_PHD_FINAL_SYNTHESIS_MODEL=gpt-5.6-terra
OPENAI_EXTERNAL_DOMAIN_MODEL=gpt-5.6-terra
OPENAI_EXTERNAL_ADJUDICATOR_MODEL=gpt-5.6-terra
OPENAI_CLEANING_REASONING_EFFORT=low
OPENAI_SECTION_ANALYSIS_REASONING_EFFORT=medium
OPENAI_CHAPTER_REASONING_EFFORT=medium
OPENAI_EXPERT_REASONING_EFFORT=high
OPENAI_FINAL_AUDIT_REASONING_EFFORT=high
OPENAI_NON_RESEARCH_MASTERS_AUDIT_REASONING_EFFORT=medium
OPENAI_RESEARCH_MASTERS_AUDIT_REASONING_EFFORT=high
OPENAI_PROFESSIONAL_DOCTORATE_AUDIT_REASONING_EFFORT=high
OPENAI_PHD_AUDIT_REASONING_EFFORT=xhigh
OPENAI_PHD_FINAL_SYNTHESIS_REASONING_EFFORT=xhigh
OPENAI_EXTERNAL_DOMAIN_REASONING_EFFORT=high
OPENAI_EXTERNAL_ADJUDICATOR_REASONING_EFFORT=xhigh
OPENAI_BACKGROUND_MODE=true
OPENAI_BACKGROUND_POLL_SECONDS=5
OPENAI_BACKGROUND_TIMEOUT_SECONDS=3600
OPENAI_PROMPT_CACHE_ENABLED=true
VPROF_FALLBACK_PROVIDER=none
VPROF_PROVIDER_FAILOVER=false
VPROF_SELECTIVE_AI_REVIEW=true
VPROF_BACHELORS_CLEAN_SAMPLE_RATE=0.05
VPROF_RESEARCH_MASTERS_CLEAN_SAMPLE_RATE=0.10
VPROF_DOCTORAL_CLEAN_SAMPLE_RATE=0.15
VPROF_QUANTITATIVE_FRAMEWORK_AUDIT=true
```

### DeepSeek Pro

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
DEEPSEEK_PRIMARY_THINKING_ENABLED=false
DEEPSEEK_AUDIT_THINKING_ENABLED=true
DEEPSEEK_TRUNCATION_RECOVERY=true
DEEPSEEK_COVERAGE_UNITS_PER_REQUEST=1
DEEPSEEK_COVERAGE_HIGH_RISK_UNITS_PER_REQUEST=1
VPROF_FALLBACK_PROVIDER=none
VPROF_PROVIDER_FAILOVER=false
```

## Recommended review controls

```env
VPROF_NATIVE_COMMENT_STYLE=exact_anchor_grouped
VPROF_EXISTING_COMMENT_POLICY=label
VPROF_STRICT_NATIVE_RECONCILIATION=true
VPROF_HUMAN_ROOT_CAUSE_CONSOLIDATION=true
VPROF_LIMITATIONS_CONSEQUENCE_AUDIT=true
VPROF_ABSOLUTE_CLAIM_AUDIT=true
```

## Deployment

Web service:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Background worker:

```bash
python -m app.worker
```

Both services must use the same `DATABASE_URL`, provider selection and provider API key. The supplied configuration keeps database artifact storage as a compatibility fallback. When `S3_BUCKET` is configured, large payloads and result files move automatically to S3-compatible object storage while PostgreSQL retains job and checkpoint state.

## Long-thesis architecture

The production defaults are tuned for 120 to 200-page work:

- one thesis job per worker by default, with controlled packet concurrency;
- three concurrent AI calls per thesis;
- 24,000-character coverage requests with packet-level checkpoints;
- Luna at low or medium effort for cleaning and risk-selected high-volume coverage;
- Terra at high effort for decisive methods, results and synthesis work;
- Terra at `xhigh` for final PhD and external adjudication;
- OpenAI background mode for `high`, `xhigh` and `max` requests;
- indefinite browser reconnection through the stored review job ID;
- a six-hour server-side academic-stage window with automatic checkpoint recovery.

For S3-compatible storage, set `VPROF_ARTIFACT_STORAGE_BACKEND=auto` and supply `S3_BUCKET`, endpoint, region and credentials. Leave the bucket empty to continue using PostgreSQL BLOB storage during migration.

For an export-stage failure from an earlier build, deploy 2.8.1 and open the existing result. The native and inline download buttons will regenerate the documents when the saved source DOCX remains available. Use **Recover** once when the job is paused or failed at document export. Submit a new job only when the original upload is no longer available.

## Administrator recovery

`ADMIN_PASSWORD` creates the first administrator but does not silently overwrite a password already stored in PostgreSQL. For a controlled one-time reset, set `VPROF_RESET_ADMIN_PASSWORD_ON_STARTUP=true`, redeploy the web service, sign in, set the flag back to `false`, and redeploy again.

## Local validation

```bash
PYTHONPATH=. pytest -q
python -m compileall -q app scripts
node --check app/static/app.js
```

See `DEPLOYMENT.md`, `.env.example` and `CHANGELOG.md`.
