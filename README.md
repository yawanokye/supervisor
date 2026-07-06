# ProjectReady AI Supervisor Assistant 1.9.8.2

ProjectReady AI Supervisor Assistant provides Light, Standard and Advanced academic review of thesis and dissertation chapters, research proposals, revised chapters and complete theses.

Version 1.9.8.2 adds a student-facing comment quality gate to the v1.9.8.1 cost and latency hotfix. In the recommended Balanced profile, DeepSeek V4 Flash performs one non-thinking Light or Standard first pass. A single compact GPT-5.4 mini accuracy audit follows. GPT-5.4 nano is the inexpensive emergency fallback if Flash is unavailable, while GPT-5.4 remains reserved for Advanced high-risk work and external-examination judgement. Strict schemas, native Microsoft Word comments, durable checkpoints, automatic recovery and supervisor token accounting remain active.

It removes internal audit diagnostics from Word comments and reports, rejects unresolved placeholder tokens, omits incomplete generated examples, consolidates duplicate findings, trims only at complete sentence boundaries, and adds deterministic checks for unresolved source-document placeholders, malformed research-question punctuation, proposal/completed-study tense conflicts and obvious opening grammar errors.

## Review philosophy

The official thesis self-evaluation checklist is used internally as a coverage guide. It is not presented to the student as the review, and its item numbers are not shown in the dashboard, annotated document or Word report.

All three review levels examine every detected substantive section and subsection. Structural chapter markers, chapter titles and heading-only parent containers are mapped but are not treated as missing-content sections. The difference is the academic benchmark and degree of critical scrutiny, not the amount of the document covered.

The review covers, where relevant:

- title accuracy, focus and scope
- chapter structure, progression and coherence
- conceptual and theoretical grounding
- empirical evidence, source quality and critical synthesis
- research problem, gap, purpose, objectives, questions and hypotheses
- methodological rigour and justification
- results, interpretation, discussion, conclusions and recommendations
- cross-chapter alignment
- citation and source risks
- academic writing, terminology, grammar and presentation
- supervisor-comment compliance for revised chapters

## Academic level and review depth

Academic level and review depth are separate controls.

- **Academic level** sets the standard expected of Bachelor’s, Non-Research Master’s, Research Master’s or MPhil, Professional Doctorate, or PhD work.
- **Review depth** controls the breadth, detail and prioritisation of feedback.
- Light, Standard and Advanced reviews all apply the same factual-verification threshold.
- A Light doctoral review remains doctoral in academic standard. An Advanced Bachelor’s review does not impose a doctoral originality requirement.

Every selected depth receives complete section coverage, source-grounded findings, an independent accuracy audit, deterministic factual checks and cross-chapter consistency checks. Python extracts the document, validates evidence, builds a factual document manifest, checks review coverage and generates the report and annotated Word file.

## Coverage safeguard

The app requires one substantive assessment for every detected substantive section and subsection. Short or apparently adequate sections cannot be silently omitted. Missing section reviews are retried individually. The system retries an unresolved stage automatically from durable checkpoints. If all automatic attempts are exhausted, the job fails clearly rather than exporting unsupported findings or an empty annotated document.

## Annotated Word output

- Feedback is created as native Microsoft Word comments, anchored to the exact quotation, section heading, table caption or relevant paragraph.
- The source text and visible formatting remain unchanged. Word shows the comment anchor using its normal review highlighting.
- Table comments identify the actual table number and title extracted from the document.
- Comments exist only in the Microsoft Word Review pane or margin. They do not become body paragraphs, alter pagination or split tables.
- Internal checklist codes and evidence identifiers are never displayed to the student.

## Human-supervisor report

The Word report presents:

1. overall supervisor assessment
2. strengths to retain
3. priority corrections before resubmission
4. an assessment of every section and subsection
5. detailed review points only where revision is needed
6. cross-chapter alignment, where applicable
7. response to earlier supervisor comments, where applicable
8. final guidance

Examples are illustrative and must be adapted to the actual study and verified evidence.

## Model routing

The routing profile is controlled by `VPROF_ROUTING_PROFILE`.

- **Balanced**, recommended: DeepSeek V4 Flash performs one Light or Standard first pass without thinking mode. GPT-5.4 nano is used only if Flash is unavailable. One compact GPT-5.4 mini accuracy audit follows. Advanced review starts with GPT-5.4 mini and may escalate difficult cases to GPT-5.4.
- **Economy**: DeepSeek V4 Flash handles Light and Standard review, with DeepSeek V4 Pro as the provider fallback. DeepSeek V4 Pro also handles Advanced review.
- **Quality**: OpenAI leads normal review. DeepSeek provides provider-failure fallback, while GPT-5.4 remains available for expert escalation.
- Light and Standard final audits use one GPT-5.4 mini request with bounded output and no automatic expert escalation.
- External Assessment remains OpenAI-led for the final degree recommendation. DeepSeek V4 Pro is used only if an OpenAI request fails.
- The first pass is not duplicated by automatic router escalation. The independent audit is the only normal second-model call.
- Every accepted response still passes strict Pydantic validation, exact evidence-ID checks, deterministic factual gates and native-comment placement checks.
- Routed calls aggregate both providers’ reported tokens and costs into the existing internal usage ledger. Model names are not displayed in student-facing reports.

## Automatic recovery and speed

- Independent chapter packets run concurrently.
- Transient provider, timeout and evidence-validation failures are queued and retried automatically.
- Automatic retries generate fresh provider checkpoints instead of replaying a defective response.
- The portal remains in Queued or Processing status during recovery. It does not enter an automatic Paused state.
- A final GPT-5.4 grounded rescue runs only when the normal audit would otherwise leave no valid comments.
- No report or annotated DOCX is released until factual evidence and native Word comments are confirmed.


## Token allocation and expected page capacity

The administrator dashboard converts each supervisor's allocation into estimated work capacity. PDF page counts are exact. DOCX pages are estimated from word count because Microsoft Word pagination varies with fonts, spacing, margins and application version.

At submission, the app reserves a conservative token estimate based on workflow and review depth. At completion, it reconciles the reservation to the OpenAI input and output tokens reported for the review. Unused reserved tokens return to the supervisor's available balance.

The default staged rollout leaves supervisors with no allocation unmetered until the institution is ready to enforce quotas. Once all accounts have balances, set `TOKEN_QUOTA_ENFORCEMENT=true`.

## Run locally

```bash
python -m venv .venv
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Render commands

Build command:

```bash
python -m pip install -r requirements.txt
```

Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Health check:

```text
/health
```

Python is pinned to 3.12.11 through `.python-version` and `render.yaml`.

The in-memory job store is suitable for one Render instance. Before horizontal scaling, replace it with Redis and a worker queue.

## Institutional administrator and lecturer portals

Version 1.1 adds account-based institutional access.

### Administrator portal

Open:

```text
/admin/login
```

The administrator can:

- create lecturer accounts
- set lecturer name, username, department, email and phone
- generate a temporary password and six-digit recovery PIN
- suspend or reactivate accounts
- reset lecturer login details
- view institutional review activity
- allocate review tokens individually or in bulk
- allocate by raw tokens, standard supervisory pages or external-examination pages
- monitor available, reserved and used tokens with a persistent audit trail

The temporary password and recovery PIN are displayed once after account creation or reset. Lecturers must change the temporary password at first login.

### Lecturer portal

Open:

```text
/login
```

Lecturers can:

- submit new chapter, proposal and full-thesis reviews
- review revised chapters against supervisor comments
- view review history and status
- download the supervisor report and annotated document
- change or recover their password

### Required production environment variables

```env
OPENAI_API_KEY=sk-...
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
DATABASE_URL=postgresql://...
SESSION_SECRET=use-a-long-random-secret
COOKIE_SECURE=true
ADMIN_USERNAME=admin
ADMIN_PASSWORD=use-a-strong-temporary-password
ADMIN_NAME=System Administrator
ADMIN_EMAIL=
REVIEW_STORAGE_DIR=/var/data/reviews
```

Use a managed PostgreSQL database for lecturer accounts and review metadata. SQLite is suitable only for local development. Attach a persistent Render disk and mount it at `/var/data` when completed review downloads must remain available after redeployment.

The first administrator is created automatically when the database is empty. The administrator must change the temporary password at first login.

## Storage behaviour on Render

The default review-file directory is `/tmp/projectready-supervisor/reviews`.
This keeps the service operational without a disk, but files are temporary.

To retain generated reports across restarts and deploys, attach a Render
persistent disk at `/var/data` and set
`REVIEW_STORAGE_DIR=/var/data/reviews`. If that path is unavailable, the app
falls back safely to `/tmp/projectready-supervisor/reviews`.

## Review-model routing

The logged-in account’s `full_name` is stored with the review and used as the native Microsoft Word comment author. Initials are derived automatically from that name. A saved review can therefore show, for example, “Anokye Mohammed Adam” with initials “AMA” in Word’s Review pane. The exporter falls back to “Reviewer” only when no account or examiner name is available.

The old `OPENAI_REVIEW_MODEL` variable is ignored by the active workflow. Remove any stale `OPENAI_REVIEW_MODEL=o3-mini` entry from Render and use the role-specific variables shown above.

Provider names remain hidden from supervisors and students.

- The selected academic level determines the scholarly benchmark.
- The selected review depth determines breadth and detail.
- Every depth receives a universal accuracy audit, exact evidence validation and deterministic expert checks before export.

Every review covers every detected substantive section and subsection. No selected depth is permitted to bypass factual validation.

The internal academic guide is adapted from the supplied thesis self-evaluation framework. It is used only to support coverage and is never shown as checklist codes in the report.

### Accuracy safeguards

- A factual manifest is built from the whole document before review, including exact headings, chapter content, tables, captions and source locations.
- A section or chapter cannot be called missing when the manifest shows substantive content elsewhere in the document.
- Synthetic labels such as “whole-chapter audit” are never treated as document locations.
- Every finding is rechecked against its cited section, subsection or table evidence.
- Table numbers and titles are copied from parsed captions, not guessed by the model.
- Cross-chapter checks compare the method promised with the analysis actually reported, including sampling and regression consistency.
- Examples cannot introduce a country, region, organisation, population or sector absent from the source.
- New author-year citations, statistics and percentages are rejected unless they appear in the uploaded source.
- Unsupported, misplaced, overly broad and repetitive comments are removed before export.
- Missing content is distinguished from weakly developed content and extraction uncertainty.

## Institutional access interface

The shared access interface has two tabs:

- `/login` opens the Supervisor tab.
- `/admin/login` opens the Admin tab.

The tabs change the active portal and form action without combining the permission systems. Supervisor and administrator authentication remain separately enforced by the backend.
## External Assessment workflow

The workspace now provides two independent academic workflows:

- **Supervisory Review** for developmental, section-by-section guidance and annotated DOCX feedback.
- **External Assessment** for independent examination of a complete thesis or dissertation.

External Assessment produces four DOCX files:

1. Full external examination report
2. Formal corrections schedule
3. Confidential recommendation to the university
4. Oral examination question bank

The workflow supports initial examination, re-examination and corrected-thesis verification. Chapter One, or the equivalent foundational chapter, is treated as a critical examination gate. Professional Doctorate and PhD theses may use custom chapter titles, sequence and architecture.



## Grounded External Assessment generation

External Assessment first builds a source manifest before any examiner judgement is requested. The manifest records the detected chapters, research functions, metadata, tables, appendices, evidence identifiers and extraction coverage. The examiner stages then receive balanced evidence from the relevant research functions instead of a single sequential extract.

The four-stage workflow covers foundation and methodology, findings and contribution, corrections and oral questions, and the final confidential decision. Every assessed domain and correction must cite valid evidence identifiers. The app rejects invented identifiers, unsupported numerical claims, missing-content claims that conflict with the thesis, and evidence drawn from the wrong research function.

A component is never described as absent merely because it was not retrieved. Limited or insufficient extraction causes the academic recommendation to be withheld with low confidence. The candidate is not penalised for an extraction failure.

The final DOCX report shows source coverage, detected chapters, evidence references and evidence-audit status. It also includes a source evidence register that links each cited identifier to its thesis location, heading and supporting excerpt. The confidential decision stage receives the cited source excerpts and independently checks the earlier assessments before recommending an outcome.

## Durable checkpoint and resume workflow

Version 1.8.0 stores the uploaded review payload and each completed processing unit before the next unit begins. The following work is reusable after a timeout, provider interruption, Render restart or manual resume:

- document extraction and thesis structure analysis
- deterministic statistical and alignment preparation
- every completed academic section batch
- the compact doctoral quality audit
- each of the four External Assessment stages
- the final assembled review before document export

A recoverable interruption is shown as **Paused**. The service automatically retries up to `MAX_AUTO_RESUMES`, and the lecturer can also select **Resume** in the portal. The same job identifier and completed checkpoints are retained. A final report is not produced until all compulsory stages have completed.

For restart-safe operation, configure PostgreSQL and persistent shared storage. The included Render blueprint mounts a persistent disk at `/var/data` and sets:

```env
REVIEW_STORAGE_DIR=/var/data/reviews
AUTO_RESUME_JOBS=true
MAX_AUTO_RESUMES=3
JOB_HEARTBEAT_SECONDS=45
JOB_LEASE_SECONDS=240
AI_MAX_PARALLEL_CALLS=4
```

The temporary fallback path permits the app to remain available but cannot preserve uploaded files across a redeploy. For horizontal scaling beyond one Render instance, replace the disk-backed payload store with S3-compatible object storage because a Render disk is attached to only one service instance.


## v1.9.2 section recovery

When a structured chapter response omits one or more sections, the app now runs a compact focused expert recovery only for those sections. Completed checkpoints are reused. Automatic resume attempts are bounded, preventing a job from cycling indefinitely at 64%.

## v1.9.3 supervisory-review execution

The active review workflow is deliberately compact:

1. Extract and map the document once.
2. Build stable chapter packets from the mapped sections and tables.
3. Review independent chapters concurrently.
4. Retry omitted content once at chapter-packet level.
5. Run deterministic factual and placement checks.
6. Audit approved findings in compact GPT-5.4 batches.
7. Generate the report and native Word comments.

This architecture removes the repeated section-recovery loop while retaining section-level evidence and comments.

Recommended production settings:

```env
AI_CHAPTER_REVIEW_CONCURRENCY=4
AI_CHAPTER_PACKET_MAX_CHARS=120000
AI_CHAPTER_RECOVERY_CONCURRENCY=2
AI_CHAPTER_RECOVERY_MAX_OUTPUT_TOKENS=7000
AI_VERIFICATION_BATCH_SIZE=12
```


## v1.9.4 unified supervisory and external-examination execution

The application now uses two compact, evidence-grounded workflows.

### Supervisory review

1. Extract and map the document once.
2. Build complete chapter packets with their sections, tables and figures.
3. Review independent chapters concurrently.
4. Retry omitted material once at chapter-packet level.
5. Apply deterministic factual and placement checks.
6. Audit proposed findings in compact GPT-5.4 batches.
7. Generate the report and native Word comments.

### External examination

1. Build and validate one whole-thesis evidence manifest.
2. Run three independent domain examiners concurrently:
   - intellectual foundation, literature and methodology;
   - results, discussion, conclusions and cross-chapter alignment;
   - integrity, writing, originality and publication potential.
3. Run one final adjudicator that audits the three reports against source evidence and produces the corrections, oral questions, final recommendation and confidential comments together.
4. Apply deterministic evidence, numerical, reference-risk and recommendation-consistency checks before export.

This reduces the external examination from five model calls to four and removes the separate corrections and decision calls that could disagree.

Recommended production settings:

```env
# Supervisory review
AI_CHAPTER_REVIEW_CONCURRENCY=4
AI_CHAPTER_PACKET_MAX_CHARS=120000
AI_CHAPTER_RECOVERY_CONCURRENCY=2
AI_CHAPTER_RECOVERY_MAX_OUTPUT_TOKENS=7000
AI_VERIFICATION_BATCH_SIZE=12
OPENAI_CHAPTER_MODEL=gpt-5.4-mini
OPENAI_CHAPTER_REASONING_EFFORT=high
OPENAI_EXPERT_MODEL=gpt-5.4
OPENAI_EXPERT_REASONING_EFFORT=high
OPENAI_FINAL_AUDIT_MODEL=gpt-5.4
OPENAI_FINAL_AUDIT_REASONING_EFFORT=high

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
```
