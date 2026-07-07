# Render deployment

## Environment variables

Set `OPENAI_API_KEY`. GPT-5.4 mini handles fast chapter review, while GPT-5.4 handles the universal factual audit, research-intensive sections and External Assessment. Review depth changes breadth and explanation, not the factual-accuracy threshold.

## Commands

Build: `python -m pip install -r requirements.txt`

Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

Health check: `/health`

After replacing an earlier deployment, use **Clear build cache & deploy**. Keep the existing database and persistent review storage.


## Review-depth settings

```env
AI_LIGHT_SECTION_BATCH_SIZE=4
AI_SECTION_BATCH_SIZE=3
AI_ADVANCED_SECTION_BATCH_SIZE=2
AI_LIGHT_MAX_OUTPUT_TOKENS=6000
AI_STANDARD_MAX_OUTPUT_TOKENS=7500
AI_ADVANCED_MAX_OUTPUT_TOKENS=10000
AI_ADVANCED_SECOND_PASS=true
```

All three review depths use the selected academic-level benchmark. Light, Standard and Advanced Review all receive a separate GPT-5.4 evidence-grounded accuracy audit. Advanced depth may be broader, but no depth bypasses factual validation.

## Institutional portal deployment

Create or attach a PostgreSQL database and set its connection string as `DATABASE_URL`. Set a strong `SESSION_SECRET`, the initial administrator details, and `COOKIE_SECURE=true`.

Recommended variables:

```env
DATABASE_URL=postgresql://...
SESSION_SECRET=<long-random-value>
COOKIE_SECURE=true
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<strong-temporary-password>
ADMIN_NAME=System Administrator
REVIEW_STORAGE_DIR=/var/data/reviews
```

For durable annotated documents and reports, attach a Render persistent disk mounted at `/var/data`. Without a persistent disk, lecturer accounts remain in PostgreSQL but generated files stored on the service filesystem may disappear after a redeploy.

## Review file storage

The application starts with temporary storage by default:

```text
REVIEW_STORAGE_DIR=/tmp/projectready-supervisor/reviews
REVIEW_STORAGE_FALLBACK_DIR=/tmp/projectready-supervisor/reviews
```

This prevents startup failure when no persistent disk is attached. Files in
`/tmp` are temporary and can be removed when Render restarts or redeploys the
service.

For durable review reports and annotated documents:

1. Use a paid Render service.
2. Open the service's **Disks** page.
3. Add a persistent disk with mount path `/var/data`.
4. Set:

```text
REVIEW_STORAGE_DIR=/var/data/reviews
REVIEW_STORAGE_FALLBACK_DIR=/tmp/projectready-supervisor/reviews
```

The application tests the configured directory at startup. If the persistent
path is unavailable, it logs a warning and uses the temporary fallback instead
of stopping the service.

## AI provider variables

One OpenAI API key enables all three review levels and External Assessment:

```text
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_CHAPTER_MODEL=gpt-5.4-mini
OPENAI_CHAPTER_REASONING_EFFORT=high
OPENAI_EXPERT_MODEL=gpt-5.4
OPENAI_EXPERT_REASONING_EFFORT=high
OPENAI_FINAL_AUDIT_MODEL=gpt-5.4
OPENAI_FINAL_AUDIT_REASONING_EFFORT=high
OPENAI_EXTERNAL_DOMAIN_MODEL=gpt-5.4
OPENAI_EXTERNAL_DOMAIN_REASONING_EFFORT=high
OPENAI_EXTERNAL_ADJUDICATOR_MODEL=gpt-5.4
OPENAI_EXTERNAL_ADJUDICATOR_REASONING_EFFORT=xhigh
PRICE_OPENAI_CHAPTER_INPUT=0.75
PRICE_OPENAI_CHAPTER_CACHED_INPUT=0.075
PRICE_OPENAI_CHAPTER_OUTPUT=4.50
PRICE_OPENAI_EXPERT_INPUT=2.50
PRICE_OPENAI_EXPERT_CACHED_INPUT=0.25
PRICE_OPENAI_EXPERT_OUTPUT=15.00
AI_ADVANCED_SECOND_PASS=true
AI_VERIFICATION_BATCH_SIZE=12
```

The application uses the Responses API with strict structured outputs. Provider and model names remain hidden from supervisors and students. Remove any stale `OPENAI_REVIEW_MODEL=o3-mini` variable because the active workflow uses the role-specific settings above. Legacy DeepSeek variables may remain unset.

## Long-running review jobs

The browser now stores the active job identifier locally and reconnects after a page refresh. Polling continues for up to two hours, while the server limits a single expert-review job to 90 minutes by default.

```text
AI_JOB_MAX_SECONDS=5400
```

A completed job returns a small polling response containing a result URL. The full review is fetched separately, which prevents oversized polling responses and reduces browser failures.

## Faster tiered OpenAI review workflow

The grouped review workflow reduces the number of OpenAI requests substantially.

- Light Review processes up to 6 sections per request.
- Standard Review processes up to 5 sections per request.
- Advanced Review processes up to 4 sections per request.
- Chapter groups use high reasoning.
- GPT-5.4 is reserved for research-intensive sections, the universal audit and External Assessment.
- Omitted sections are retried in groups of up to 6, not individually.
- Structured-output retries are disabled by default because grouped recovery handles incomplete coverage.

Recommended values:

```text
AI_LIGHT_SECTION_BATCH_SIZE=6
AI_SECTION_BATCH_SIZE=5
AI_ADVANCED_SECTION_BATCH_SIZE=4
AI_RECOVERY_BATCH_SIZE=6
AI_MAX_RECOVERY_BATCHES=2
AI_STRUCTURED_OUTPUT_RETRIES=0

OPENAI_CHAPTER_MODEL=gpt-5.4-mini
OPENAI_CHAPTER_REASONING_EFFORT=high
OPENAI_EXPERT_MODEL=gpt-5.4
OPENAI_EXPERT_REASONING_EFFORT=high
OPENAI_FINAL_AUDIT_MODEL=gpt-5.4
OPENAI_FINAL_AUDIT_REASONING_EFFORT=high
AI_ADVANCED_SECOND_PASS=true
AI_ADVANCED_AUDIT_MAX_FINDINGS=24
```

For a typical Chapter One with about 15 detected review units, Advanced Review should normally require about four primary requests and one compact audit, plus a grouped recovery request only when a section is omitted.

## Checkpoint and resume deployment requirements

The v1.8.6 pipeline persists original uploads, factual document manifests, completed AI section groups, universal accuracy-audit results and final-stage data. For the checkpoints to survive a Render restart or redeploy:

1. Use Render PostgreSQL through `DATABASE_URL`.
2. Mount persistent storage at `/var/data` and set `REVIEW_STORAGE_DIR=/var/data/reviews`.
3. Keep `AUTO_RESUME_JOBS=true`.
4. Use one web instance while relying on a Render persistent disk. A persistent disk is not shared between horizontally scaled instances.
5. For multiple web or worker instances, move the payload/checkpoint files to S3-compatible shared object storage before scaling horizontally.

Recommended environment values:

```env
AUTO_RESUME_JOBS=true
MAX_AUTO_RESUMES=3
JOB_HEARTBEAT_SECONDS=45
JOB_LEASE_SECONDS=240
JOB_STALE_AFTER_SECONDS=180
AI_MAX_PARALLEL_CALLS=4
AI_JOB_MAX_SECONDS=7200
REVIEW_STORAGE_DIR=/var/data/reviews
REVIEW_STORAGE_FALLBACK_DIR=/tmp/projectready-supervisor/reviews
```

On startup, queued, paused and interrupted processing jobs with saved payloads are reclaimed. Completed document-analysis, section-review and External Assessment checkpoints are skipped. Only the unfinished unit is repeated.

## v1.8.6 supervisory accuracy deployment

Version 1.8.6 requires `python-docx==1.2.0` so the annotated document can use native Microsoft Word comments. Use **Clear build cache & deploy** when upgrading from v1.8.5 or earlier.

The checkpoint keys changed for document analysis, supervisory review and the universal accuracy audit. Existing completed external-assessment checkpoints remain compatible, but a previously inaccurate supervisory review should be submitted as a fresh review so it is regenerated under the v1.8.6 factual manifest and annotation controls.

No new environment variable is required. Keep the existing persistent database and review storage.

## v1.8.7 native Word comment deployment

Version 1.8.7 makes native Microsoft Word comments the only annotated-document output. Use **Clear build cache & deploy** and confirm `python-docx==1.2.0` is installed.

Keep the existing persistent review storage mounted. When a user downloads an annotated document created by an older exporter, the app regenerates it from the saved source DOCX and current review findings. If that source payload is no longer available, the app asks for a fresh review rather than serving a legacy file with comments inserted into the text.

## v1.8.8 factual placement deployment

Version 1.8.8 corrects false and misplaced supervisory comments. Use **Clear build cache & deploy** and keep `python-docx==1.2.0`.

The document-analysis, primary-review, comment-audit and completed supervisory-review checkpoint keys have changed. Reviews generated with v1.8.7 or earlier must be submitted as fresh supervisory reviews, or regenerated from the stored original DOCX, so the revised section map and factual-placement controls are applied. External-assessment checkpoints are unaffected.

No new environment variable is required. Keep the existing database and persistent review storage mounted.

## Historical: v1.8.9 OpenAI o3-mini deployment

Version 1.8.9 changes all active model routing to OpenAI `o3-mini`. Set `OPENAI_API_KEY`, then use **Clear build cache & deploy**. The review, accuracy-audit, recovery and External Assessment checkpoint hashes changed so old provider outputs are not reused. Keep the existing database and persistent review storage.

Recommended values:

```env
OPENAI_REVIEW_MODEL=o3-mini
OPENAI_REVIEW_REASONING_EFFORT=high
AI_MAX_PARALLEL_CALLS=4
AI_MAX_RETRIES=1
AI_STRUCTURED_OUTPUT_RETRIES=0
```

## v1.9.0 safe stop deployment

Version 1.9.0 adds a **Stop review** action for queued or processing reviews. The action preserves completed checkpoints and the saved upload, marks the job as `stopped`, releases the worker lease and prevents automatic recovery. The user may later select **Resume**.

To stop a job that was already running before this version was deployed, temporarily set `AUTO_RESUME_JOBS=false`, deploy v1.9.0, refresh Review History and select **Stop review**. After the job shows `Stopped`, `AUTO_RESUME_JOBS` may be restored to `true`.


## v1.9.1 tiered OpenAI and named-comment deployment

Version 1.9.1 replaces the single-model o3-mini workflow with role-based routing:

- GPT-5.4 mini handles fast chapter-level assessment for Bachelor’s and taught Master’s work.
- GPT-5.4 handles research-intensive MPhil sections and every substantive Professional Doctorate or PhD section.
- GPT-5.4 performs the universal factual, evidence and placement audit for every depth and academic level.
- External Assessment uses GPT-5.4, with `xhigh` reasoning for the final confidential decision.
- Native Word comments use the logged-in lecturer’s full name and automatically derived initials, not “Supervisor Assistant”.

Use **Clear build cache & deploy**, retain the database and persistent disk, and remove `OPENAI_REVIEW_MODEL=o3-mini` from Render. Set the role-specific variables listed in the AI provider section. The review, audit and External Assessment checkpoint hashes changed, so earlier model outputs are not reused. Existing annotated files are regenerated with the named comment author when the original source DOCX remains in persistent storage. Otherwise, submit a fresh review.


## v1.9.2 focused section recovery

Recommended values:

```env
AI_FOCUSED_RECOVERY_PARALLEL_CALLS=2
AI_FOCUSED_RECOVERY_MAX_OUTPUT_TOKENS=4200
AI_FOCUSED_RECOVERY_TIMEOUT_SECONDS=240
MAX_AUTO_RESUMES=3
```

After deployment, a job already paused repeatedly at 64% may have reached the automatic-resume limit. Open Review History and select Resume once. Existing extraction and completed provider checkpoints are reused.

## v1.9.3 deployment notes

Deploy with **Clear build cache & deploy**. Keep the existing database and persistent disk.

Add or update:

```env
AI_CHAPTER_REVIEW_CONCURRENCY=4
AI_CHAPTER_PACKET_MAX_CHARS=120000
AI_CHAPTER_RECOVERY_CONCURRENCY=2
AI_CHAPTER_RECOVERY_MAX_OUTPUT_TOKENS=7000
AI_VERIFICATION_BATCH_SIZE=12
```

The old focused-section recovery variables may remain, but they are no longer used by the active supervisory-review path. Existing v1.9.2 academic checkpoints are intentionally not reused. Document extraction and durable source files remain available.


## v1.9.4 deployment notes

Use **Clear build cache & deploy**. Keep the current database and persistent disk.
The academic-review checkpoint version remains v1.9.3, so completed chapter analysis may be reused. The final pipeline and external-assessment checkpoint versions changed, so any previous five-stage external examination is regenerated by the new four-call workflow.

Recommended variables:

```env
# Shared OpenAI setup
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://api.openai.com/v1

# Supervisory review
OPENAI_CHAPTER_MODEL=gpt-5.4-mini
OPENAI_CHAPTER_REASONING_EFFORT=high
OPENAI_EXPERT_MODEL=gpt-5.4
OPENAI_EXPERT_REASONING_EFFORT=high
OPENAI_FINAL_AUDIT_MODEL=gpt-5.4
OPENAI_FINAL_AUDIT_REASONING_EFFORT=high
AI_CHAPTER_REVIEW_CONCURRENCY=4
AI_CHAPTER_PACKET_MAX_CHARS=120000
AI_CHAPTER_RECOVERY_CONCURRENCY=2
AI_CHAPTER_RECOVERY_MAX_OUTPUT_TOKENS=7000
AI_VERIFICATION_BATCH_SIZE=12

# External examination
OPENAI_EXTERNAL_DOMAIN_MODEL=gpt-5.4
OPENAI_EXTERNAL_DOMAIN_REASONING_EFFORT=high
OPENAI_EXTERNAL_ADJUDICATOR_MODEL=gpt-5.4
OPENAI_EXTERNAL_ADJUDICATOR_REASONING_EFFORT=xhigh
AI_EXTERNAL_ASSESSMENT_FOUNDATION_MAX_OUTPUT_TOKENS=8000
AI_EXTERNAL_ASSESSMENT_EVIDENCE_MAX_OUTPUT_TOKENS=8000
AI_EXTERNAL_ASSESSMENT_INTEGRITY_MAX_OUTPUT_TOKENS=6500
AI_EXTERNAL_ASSESSMENT_ADJUDICATION_MAX_OUTPUT_TOKENS=11000
AI_EXTERNAL_ASSESSMENT_STAGE_TIMEOUT_SECONDS=900
AI_EXTERNAL_ASSESSMENT_REQUEST_TIMEOUT_SECONDS=360
AI_EXTERNAL_ASSESSMENT_REQUEST_MAX_RETRIES=0

# Execution and recovery
AUTO_RESUME_JOBS=true
MAX_AUTO_RESUMES=3
AI_MAX_PARALLEL_CALLS=4
AI_JOB_MAX_SECONDS=5400
JOB_HEARTBEAT_SECONDS=45
JOB_LEASE_SECONDS=240
```

Remove stale `OPENAI_REVIEW_MODEL=o3-mini` and old external role variables from a new Render deployment. Legacy external variables remain accepted only as fallbacks.

## Supervisor token allocation

Version 1.9.7 adds an administrator token-allocation module. The dashboard can
allocate raw AI tokens or convert a requested number of standard supervisory or
external-examination pages into tokens. A review reserves an estimated amount
at submission and reconciles the reservation to the provider's reported input
and output tokens when the review completes.

Recommended staged rollout:

```env
TOKEN_ACCOUNTING_ENABLED=true
TOKEN_QUOTA_ENFORCEMENT=false
SUPERVISOR_DEFAULT_TOKEN_ALLOCATION=0
TOKEN_ESTIMATE_WORDS_PER_PAGE=450
TOKEN_RESERVE_MULTIPLIER=1.15
TOKENS_PER_PAGE_SUPERVISORY_LIGHT=2500
TOKENS_PER_PAGE_SUPERVISORY_STANDARD=3500
TOKENS_PER_PAGE_SUPERVISORY_ADVANCED=5000
TOKENS_PER_PAGE_EXTERNAL_ASSESSMENT=6500
```

With `TOKEN_QUOTA_ENFORCEMENT=false`, supervisors who have never received an
allocation remain unmetered. As soon as an allocation is assigned, that account
is metered. After all accounts have been allocated, set
`TOKEN_QUOTA_ENFORCEMENT=true` so every supervisor must have enough available
tokens before submitting a review.

PDF page counts are exact. DOCX page capacity is estimated from word count
because pagination varies with fonts, margins, spacing and the Word version.
The administrator dashboard therefore labels page figures as planning
estimates rather than guaranteed page limits.

## v1.9.8 cost-aware routing deployment

Version 1.9.8 is a complete replacement repository built from v1.9.7. Do not
copy only `app/model_router.py` over an older deployment. Deploy the full ZIP so
the provider routing, checkpoint hashes, cost accounting and environment
templates remain aligned.

Add both secret keys to the Render Web Service and to any separately deployed
Background Worker:

```env
OPENAI_API_KEY=...
DEEPSEEK_API_KEY=...
```

Recommended production routing:

```env
VPROF_ROUTING_PROFILE=balanced
VPROF_ENABLE_OPENAI=true
VPROF_ENABLE_DEEPSEEK=true
VPROF_ENABLE_SELECTIVE_ESCALATION=true
VPROF_ESCALATE_CONFIDENCE_BELOW=0.78
VPROF_DEFAULT_CALL_BUDGET_USD=0.75

DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_FAST_MODEL=deepseek-v4-flash
DEEPSEEK_QUALITY_MODEL=deepseek-v4-pro
DEEPSEEK_THINKING_ENABLED=true
DEEPSEEK_REASONING_EFFORT=high
DEEPSEEK_ADVANCED_PRIMARY_REASONING_EFFORT=high

OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_CHAPTER_MODEL=gpt-5.4-mini
OPENAI_CHAPTER_REASONING_EFFORT=high
OPENAI_EXPERT_MODEL=gpt-5.4
OPENAI_EXPERT_REASONING_EFFORT=high
OPENAI_FINAL_AUDIT_MODEL=gpt-5.4
OPENAI_FINAL_AUDIT_REASONING_EFFORT=high
OPENAI_EXTERNAL_DOMAIN_MODEL=gpt-5.4
OPENAI_EXTERNAL_DOMAIN_REASONING_EFFORT=high
OPENAI_EXTERNAL_ADJUDICATOR_MODEL=gpt-5.4
OPENAI_EXTERNAL_ADJUDICATOR_REASONING_EFFORT=xhigh
```

Keep the existing execution settings initially:

```env
AI_MAX_PARALLEL_CALLS=4
AI_CHAPTER_REVIEW_CONCURRENCY=4
AI_CHAPTER_PACKET_MAX_CHARS=120000
AI_CHAPTER_RECOVERY_CONCURRENCY=2
AI_VERIFICATION_BATCH_SIZE=12
AI_TIMEOUT_SECONDS=300
AI_MAX_RETRIES=1
AI_STRUCTURED_OUTPUT_RETRIES=0
TOKEN_ACCOUNTING_ENABLED=true
TOKEN_QUOTA_ENFORCEMENT=false
```

Run known Bachelor’s, Master’s, doctoral and external-examination documents
before enabling quota enforcement. Compare material-issue recall, false
positives, native comment placement, total latency and actual cost against the
v1.9.7 records.

## v1.9.8.1 cost and latency hotfix

Deploy v1.9.8.1 as a complete replacement for v1.9.8. The hotfix invalidates
only the supervisory-review checkpoints whose routing behaviour changed.
Existing users, balances, review records and stored documents remain compatible.

The hotfix fixes the DeepSeek OpenAI-compatible request shape. The `thinking`
object contains only the mode, while `reasoning_effort` is sent as a top-level
field. Flash first-pass reviews explicitly disable thinking mode.

Use these settings on the Render Web Service and any separate worker:

```env
VPROF_ROUTING_PROFILE=balanced
VPROF_ENABLE_OPENAI=true
VPROF_ENABLE_DEEPSEEK=true
VPROF_ENABLE_SELECTIVE_ESCALATION=true
VPROF_DEFAULT_CALL_BUDGET_USD=0.25

DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_FAST_MODEL=deepseek-v4-flash
DEEPSEEK_QUALITY_MODEL=deepseek-v4-pro
DEEPSEEK_THINKING_ENABLED=true

OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_FAST_MODEL=gpt-5.4-nano
OPENAI_CHAPTER_MODEL=gpt-5.4-mini
OPENAI_EXPERT_MODEL=gpt-5.4
OPENAI_FINAL_AUDIT_MODEL=gpt-5.4

AI_FAST_REQUEST_TIMEOUT_SECONDS=120
AI_FAST_REQUEST_MAX_RETRIES=0
AI_MAX_RETRIES=0
AI_STRUCTURED_OUTPUT_RETRIES=0
AI_LIGHT_MAX_OUTPUT_TOKENS=4500
AI_STANDARD_MAX_OUTPUT_TOKENS=6500
AI_LIGHT_AUDIT_MAX_OUTPUT_TOKENS=2600
AI_STANDARD_AUDIT_MAX_OUTPUT_TOKENS=3800
AI_FAST_AUDIT_BATCH_ISSUE_LIMIT=100
AI_FAST_AUDIT_MAX_BATCHES=1
```

For Light and Standard review, the normal request plan is now:

1. one DeepSeek V4 Flash first pass with thinking disabled;
2. GPT-5.4 nano only if Flash is unavailable;
3. one compact GPT-5.4 mini accuracy audit;
4. no automatic GPT-5.4 escalation and no paid audit retry.

If both the primary and low-cost fallback fail, the job stops clearly before
starting another complete paid pass. Advanced review and External Assessment
retain their higher-quality model routes.

Before redeploying, stop or cancel any currently running v1.9.8 review. After
deployment, submit it as a new review so it uses the v1.9.8.1 checkpoint keys.
## v1.9.8.2 public comment quality deployment

Deploy v1.9.8.2 as a complete replacement for v1.9.8.1. Stop any active review before deployment and submit it as a new review after redeployment because the supervisory and annotation checkpoint identifiers changed.

Add these variables to both the Render web service and worker when a separate worker is used:

```env
VPROF_REJECT_PLACEHOLDER_COMMENTS=true
VPROF_SUPPRESS_INTERNAL_AUDIT_NOTICES=true
VPROF_COMMENT_MAX_CHARS=680
VPROF_COMMENT_SIMILARITY_THRESHOLD=0.62
```

Remove stale `OPENAI_*_MODEL=o3-mini` variables. The active role-specific settings are `OPENAI_FAST_MODEL`, `OPENAI_CHAPTER_MODEL`, `OPENAI_EXPERT_MODEL`, `OPENAI_FINAL_AUDIT_MODEL`, `OPENAI_EXTERNAL_DOMAIN_MODEL` and `OPENAI_EXTERNAL_ADJUDICATOR_MODEL`. Also set `VPROF_ENABLE_DEEPSEEK=true` explicitly.

Rotate `SESSION_SECRET` whenever its value has been copied into a document, ticket or chat. Existing browser sessions will be signed out after rotation.



## v1.9.8.3 Research Master’s/MPhil depth deployment

Deploy v1.9.8.3 as a complete replacement for v1.9.8.2. Existing users, balances, stored reviews and the database schema remain compatible. Submit any MPhil review as a new job because the primary-review and audit checkpoint identifiers changed.

Add these settings to both the Render web service and worker:

```env
VPROF_RESEARCH_MASTERS_DEEP_REVIEW=true
AI_RESEARCH_MASTERS_MAX_OUTPUT_TOKENS=9000
AI_RESEARCH_MASTERS_AUDIT_MAX_OUTPUT_TOKENS=6500
OPENAI_RESEARCH_MASTERS_AUDIT_REASONING_EFFORT=high
```

In the Balanced profile, the expected Research Master’s/MPhil Standard path is one DeepSeek V4 Pro first pass followed by one GPT-5.4 expert audit. Non-Research Master’s Standard review retains the lower-cost Flash plus GPT-5.4 mini route. The MPhil path is intentionally deeper and may cost more than the applied Master’s route, but it remains bounded to one scholarly first pass and one expert audit.


## v1.9.8.6 all-level degree-depth deployment

Deploy v1.9.8.6 as a complete replacement for v1.9.8.3. Existing accounts, balances, stored reviews and the database schema remain compatible. Submit active reviews as new jobs because primary-review and audit checkpoint identifiers changed.

Use `supervisor-v1.9.8.6-render.env.example` on both the Render web service and worker. The new settings are:

```env
VPROF_ALL_LEVELS_DEGREE_CALIBRATED=true
AI_NON_RESEARCH_MASTERS_MAX_OUTPUT_TOKENS=7500
AI_PROFESSIONAL_DOCTORATE_MAX_OUTPUT_TOKENS=11000
AI_PHD_MAX_OUTPUT_TOKENS=12000
AI_NON_RESEARCH_MASTERS_AUDIT_MAX_OUTPUT_TOKENS=4500
AI_PROFESSIONAL_DOCTORATE_AUDIT_MAX_OUTPUT_TOKENS=7500
AI_PHD_AUDIT_MAX_OUTPUT_TOKENS=8000
OPENAI_NON_RESEARCH_MASTERS_AUDIT_REASONING_EFFORT=medium
OPENAI_PROFESSIONAL_DOCTORATE_AUDIT_REASONING_EFFORT=high
OPENAI_PHD_AUDIT_REASONING_EFFORT=xhigh
```

Bachelor’s and Non-Research Master’s remain on the cost-efficient ordinary route. Research Master’s/MPhil, Professional Doctorate and PhD use DeepSeek V4 Pro for the research-intensive first pass and one bounded GPT-5.4 expert audit in the Balanced profile.


## v1.9.8.6 developmental-depth deployment

Deploy v1.9.8.6 as a complete replacement for v1.9.8.4. Existing accounts, balances, stored reviews and the database schema remain compatible. Submit active review jobs as new jobs because comment-depth and finding-retention behaviour changed.

Use `supervisor-v1.9.8.6-render.env.example` on both the Render web service and worker. The key new settings are `VPROF_DEVELOPMENTAL_COMMENTS=true`, `VPROF_COMMENT_DEPTH_FLOOR_ENABLED=true`, `VPROF_COMMENT_MAX_CHARS=980`, and the four `VPROF_STANDARD_*_MIN_FINDINGS` values.

## v1.9.8.7 deployment note

Deploy the v1.9.8.7 ZIP as the complete repository. No database migration and no new Render environment variable are required. Submit new reviews rather than resuming old checkpoints so the new section-coverage comments are generated.

## v1.9.8.8 deployment note

No database migration or environment-variable change is required. Deploy the complete v1.9.8.8 repository and restart both the Web Service and Worker. Submit new review jobs after deployment so the improved section-comment quality logic is applied.

## Deploying v1.9.8.9 Expert DeepSeek V4 Pro mode

1. Deploy the full v1.9.8.9 repository.
2. Import `supervisor-v1.9.8.9-COMPLETE.env` or add the variables in `ENVIRONMENT_CHANGES_v1.9.8.9.md`.
3. Ensure `DEEPSEEK_API_KEY` is valid and `VPROF_ENABLE_DEEPSEEK=true`.
4. For the Pro-only test, keep `VPROF_ENABLE_OPENAI=false` and submit the MPhil document as a new Standard Review.
5. Do not resume older checkpoints because they contain mixed-route and earlier comment-formatting state.

## v1.9.9.0 deterministic checklist deployment note

This release does not require a database migration. Deploy the full repository or patch and redeploy both web and worker services. Do not resume old checkpoints if you want the new deterministic checklist findings to appear in DOCX comments.

Recommended settings:

```env
VPROF_DETERMINISTIC_SUPERVISORY_CHECKLIST=true
VPROF_DETERMINISTIC_CHECKLIST_MAX_ISSUES=36
```

## v1.9.9.1 deployment note

Deploy as a full replacement of v1.9.9.0. Start new review jobs after deployment. Do not resume old checkpoints because they were created before the hard checklist and DOCX no-title-page-fallback changes.

## v1.9.9.3 deployment note

Deploy as a full replacement and start new review jobs. Do not resume old v1.9.9.2 jobs because their checkpoints do not contain the strengthened all-level degree-contract rescue.


## v1.9.9.4 deployment note

After deploying this version, do not wait indefinitely on an old browser spinner. Refresh the page and open Review History. Jobs whose automatic recovery budget is exhausted will show a Recover action if the saved upload is still available. Start new tests as fresh reviews rather than relying on an already looping browser session.

## Deploying v1.9.9.5 combined pipeline

1. Import `supervisor-v1.9.9.5-COMPLETE.env` or add the variables from `ENVIRONMENT_CHANGES_v1.9.9.5.md`.
2. Confirm that your OpenAI organisation has access to the selected models. GPT-5.6 Luna is preview/limited-access; keep the fallback model configured.
3. Restart both Render Web Service and Worker.
4. Run a fresh review. Do not resume old jobs created under previous provider routing.


## v1.9.9.6 – Combined Pipeline Summary Scope Fix

- Fixes a background review crash after a successful OpenAI Responses API call.
- Ensures the final degree-contract/checklist rescue stage always has a safe local summary object.
- Prevents `UnboundLocalError: cannot access local variable 'summary'` in `academic_ai_engine.py`.
- No database migration or environment change required.
