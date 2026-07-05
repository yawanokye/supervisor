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
OPENAI_EXTERNAL_MODEL=gpt-5.4
OPENAI_EXTERNAL_REASONING_EFFORT=high
OPENAI_EXTERNAL_DECISION_REASONING_EFFORT=xhigh
PRICE_OPENAI_CHAPTER_INPUT=0.75
PRICE_OPENAI_CHAPTER_CACHED_INPUT=0.075
PRICE_OPENAI_CHAPTER_OUTPUT=4.50
PRICE_OPENAI_EXPERT_INPUT=2.50
PRICE_OPENAI_EXPERT_CACHED_INPUT=0.25
PRICE_OPENAI_EXPERT_OUTPUT=15.00
AI_ADVANCED_SECOND_PASS=true
AI_VERIFICATION_BATCH_SIZE=24
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
