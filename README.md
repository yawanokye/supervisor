# V-Professor Supervisory Review 2.9.0

V-Professor provides degree-calibrated supervisory review and external assessment for Bachelor’s, Non-Research Master’s, Research Master’s/MPhil, Professional Doctorate and PhD work.

## Current-submission isolation

Every uploaded work is evidence for that review job only. A thesis, dissertation, chapter or benchmark used to test the system remains an example and is never converted into a reusable topic, institution, location, construct or correction rule.

The app rebuilds the study context from the current submission, uses earlier chapters only when they belong to the same work, and applies generic academic, methodological, statistical, language and citation standards.

## Final professional review controls

Version 2.9.0 includes the following release controls:

- complete theses are reviewed one chapter at a time, with an explicit supervisor-controlled Continue action between chapters;
- each completed chapter report and annotated chapter remains available before the next chapter starts;
- earlier completed chapters and the shared reference list are reused for cross-chapter alignment without reviewing future chapters prematurely;
- a cumulative final thesis result is assembled after the last chapter, with cross-chapter findings, statistical warnings and numbering reconciled;
- preliminary pages, the Table of Contents, navigation lists, acronyms, main chapters, references and appendices are separated before chapter detection;
- visible comments use a human supervisory budget, while repeated and lower-priority instances are grouped in an internal issue ledger;
- “effect” is accepted for appropriate regression-class, SEM, PLS-SEM, mediation and moderation estimates, while explicit causal claims remain design-sensitive;

- native Word-comment and inline annotated DOCX files are generated, validated and persisted as one atomic delivery bundle before a review is released as complete;
- current V-Professor comments are counted separately from comments already present in the uploaded source, so old comments can never make an empty new annotation export pass validation;
- every final finding number must appear in both the native and inline annotated outputs, including findings whose quoted source fragments end near citation boundaries;
- completed academic-review checkpoints are retained when document export fails, so recovery retries the annotation stage without repeating a paid provider pass;
- older completed reviews can regenerate current annotated outputs at download time when the saved source DOCX remains available;
- natural student-facing comments limited to focused supervisory prose rather than visible labels such as `Issue`, `Problem identified`, `Action required` or `Verification`;
- substantive paragraph anchoring ahead of section-heading anchoring;
- root-cause consolidation for overlapping construct, background, problem-gap and scope findings;
- strict reconciliation between the canonical finding ledger, native Word comments and the appended correction register;
- one Word comment box for related findings tied to the same exact paragraph, with every released finding number represented;
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
OPENAI_FINAL_AUDIT_REASONING_EFFORT=xhigh
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

- two thesis jobs per worker;
- three concurrent AI calls per thesis;
- 24,000-character coverage requests with packet-level checkpoints;
- Luna at low or medium effort for cleaning and high-volume coverage;
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
