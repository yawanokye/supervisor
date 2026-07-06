# Changelog

## 1.9.8.6 - Final MPhil Standard depth and clean native comments

- Applies the degree-depth floor after public comment deduplication so Research Master’s/MPhil Standard reviews do not fall below the expected material-feedback level after quality filtering.
- Prevents duplicate placeholder comments when both the review engine and exporter detect the same bracketed drafting prompt.
- Adds deterministic MPhil-level checks for sentence-level uncited empirical sample claims, in-text/reference author-name mismatch, and environmental sustainability versus environmental performance construct ambiguity.
- Keeps native Word comments natural by removing remaining template residue and converting awkward generated instructions into direct supervisor guidance.
- No database migration or environment change is required from v1.9.8.5.

## 1.9.8.6 - Developmental comment depth and ordered review floors

- Added developmental native Word comments with issue, why it matters and revise-by guidance.
- Raised the default public comment length from 680 to 980 characters.
- Added degree/depth comment floors so Standard Research Master’s/MPhil retains more material research-intensive findings than Standard Non-Research Master’s when the same weak chapter is reviewed.
- Added evidence-retention rescue from already generated first-pass findings without making extra paid calls.
- Reduced repeated alignment comments through stronger similarity grouping.
- Added tests for developmental comments and level-ordered finding floors.

## 1.9.8.6 - All-level degree-calibrated depth

- Gives Bachelor’s, Non-Research Master’s, Research Master’s/MPhil, Professional Doctorate and PhD separate operational review contracts.
- Adds distinct per-section material-issue ceilings and independent-audit capacities for every programme level.
- Adds chapter-specific mandatory checks for Chapters One to Five at every level.
- Separates Professional Doctorate contribution-to-practice review from PhD contribution-to-knowledge review.
- Adds degree-specific primary-output and audit-output allowances while preserving bounded calls.
- Applies deterministic alignment, citation, definition, proposal-stage and language checks to every programme level.
- Updates the interface to explain the selected level’s actual scholarly benchmark.
- Preserves the DeepSeek Flash route for Bachelor’s and applied Master’s, and the DeepSeek Pro plus GPT-5.4 expert route for research-intensive degrees.

## 1.9.8.3 - Degree-calibrated Research Master’s/MPhil depth

- Separated Non-Research Master’s applied review from Research Master’s/MPhil research-intensive review.
- Routes Research Master’s/MPhil Standard first passes through DeepSeek V4 Pro instead of the ordinary Flash path.
- Adds one bounded GPT-5.4 expert audit for Research Master’s/MPhil Standard review.
- Raises the MPhil per-section material-issue capacity from four to six without creating an issue quota.
- Adds a degree-specific review contract covering critical synthesis, theory, construct roles, problem-gap evidence, alignment, methodological defensibility, source traceability and contribution.
- Adds Chapter One MPhil checks for background progression, contextual problem evidence, purpose-objective-question alignment, causal language, prospective significance, definition quality and citation-reference integrity.
- Adds deterministic, evidence-anchored MPhil checks for purpose-objective coverage, premature results language, weak definitions, citation formatting, uncited references and mixed language conventions.
- Updates the interface guidance so users can see how MPhil depth differs from Non-Research Master’s review.
- Preserves the v1.9.8.2 placeholder, truncation, duplicate-comment and internal-notice safeguards.

## 1.9.8.2 - Public comment quality gate

- Removed provider, audit, retry and manual-confirmation diagnostics from student-facing Word comments and reports.
- Rejected unresolved bracket placeholders and replaced unusable actions with concise, source-safe instructions.
- Omitted illustrative examples that contain invented details, unclosed quotations or visibly unfinished fragments.
- Consolidated semantically duplicate findings across academic, alignment and revision outputs.
- Trimmed comments only at complete sentence boundaries.
- Prevented current-year references from being labelled future-dated solely because of their year.
- Made hypothesis recommendations conditional on programme format and research design.
- Added deterministic checks for source-document placeholders, malformed question punctuation, Chapter One tense conflicts and an obvious opening subject-verb error.
- Added public-comment quality environment controls and invalidated old comment-export checkpoints.

## 1.9.8.1 - Cost and latency hotfix

- Corrected the DeepSeek thinking payload by sending `reasoning_effort` as a top-level API field.
- Runs DeepSeek V4 Flash without thinking mode for Light and Standard first-pass reviews.
- Prevents the entire first pass from being repeated through automatic OpenAI escalation.
- Replaces the expensive Standard provider fallback with GPT-5.4 nano.
- Limits Light and Standard review to one compact GPT-5.4 mini accuracy-audit request.
- Disables paid audit retries for Light and Standard review and retains only evidence-grounded deterministic fallback findings if the audit is unavailable.
- Adds 120-second fast-request timeouts, no fast-request retries, and lower bounded output limits.
- Stops a failed fast review before launching a second complete paid pass.
- Updates Render and environment defaults to match the bounded workflow.
- Adds provider-payload, fallback, latency and audit-budget regression tests.

## 1.9.8 - Cost-aware multi-provider routing

- Merged the v1.9.8 routing patch into the complete v1.9.7 application rather than deploying it as a standalone overlay.
- Added Economy, Balanced and Quality routing profiles.
- Uses DeepSeek V4 Flash for inexpensive Light and Standard first-pass review in the Balanced profile.
- Uses GPT-5.4 mini for Advanced review, final accuracy auditing and selective escalation from uncertain standard reviews.
- Reserves GPT-5.4 for difficult high-risk findings and OpenAI-led external-examination judgement.
- Added bounded provider fallback between DeepSeek and OpenAI without creating a second SDK stack.
- Preserved strict Pydantic structured outputs, evidence validation, native Word comments, checkpoints, automatic recovery and token accounting.
- Added model-specific DeepSeek Flash and Pro cost accounting and aggregates the cost of selectively escalated calls.
- Allows normal supervisory reviews to remain available when only one enabled provider is configured. External examination continues to require OpenAI.
- Added routing-aware checkpoint hashes so v1.9.7 model results are not incorrectly restored under a different route.
- Updated Render and environment templates with the required routing settings.
- Passed 190 automated tests.

## 1.9.7 - Supervisor token allocation and page-capacity planning

- Added individual and bulk token allocation to the administrator dashboard.
- Added allocation by raw AI tokens, standard supervisory pages or external-examination pages.
- Added exact PDF page counts and conservative DOCX page estimates.
- Added token reservation before review execution and actual-usage reconciliation at completion.
- Added supervisor balance, reserved usage, settled usage and page-capacity displays.
- Added a persistent token ledger and safe database migrations.
- Added staged quota enforcement so existing deployments can allocate balances before blocking submissions.

## v1.9.6 — Fast grounded review with automatic recovery

- Removes automatic Paused states for provider, timeout, evidence-validation and empty-comment failures.
- Queues transient failures and retries only the interrupted stage from durable checkpoints.
- Uses exponential retry delays and a configurable retry ceiling, then fails clearly with a manual Recover action rather than looping.
- Adds a retry-generation key so a recovery request receives fresh model outputs instead of restoring the same defective provider checkpoint.
- Adds one last-mile GPT-5.4 expert rescue when proposed comments are removed by the accuracy audit, while retaining exact evidence and placement gates.
- Keeps chapter packets concurrent and verification batches small for speed.
- Preserves live stage messages during high-progress retries so the portal no longer appears frozen at an old percentage.
- Requires at least one verified native Microsoft Word comment before the annotated DOCX becomes downloadable.
- Keeps the original document text and formatting unchanged and uses the logged-in reviewer’s name as comment author.
- Passed 181 automated tests.

## v1.9.5 — Validated report and native-comment output recovery

- Splits comment verification into smaller batches and retries failed batches as focused evidence packets.
- Preserves evidence-grounded major and moderate findings when an independent audit request remains unavailable, while marking those comments for manual confirmation.
- Prevents completion when low section scores would otherwise produce an empty report and an unannotated DOCX.
- Validates that an exported annotated DOCX contains at least one native Word comment before making it downloadable.
- Hides the annotated-document download when no grounded actionable finding exists.
- Adds **Rebuild review** for completed reviews labelled **Review completed with a limitation**, reusing the saved extraction and upload.
- Reduces the default verification batch size from 48 findings to 12.
- Bumps supervisory-review, final-pipeline and native-comment export versions so defective cached output is not restored.

## v1.9.4 — Unified supervisory and external-examination workflows

- Retained the simplified v1.9.3 chapter-packet supervisory review.
- Reorganised External Assessment into three independent domain examiners running in parallel followed by one final adjudicator.
- Combined the correction schedule, oral questions, overall judgement, recommendation and confidential comments in one final structured response.
- Removed the separate corrections and decision calls that could produce inconsistent conclusions.
- Added role-specific external model settings for domain examination and final adjudication, with backwards-compatible aliases.
- Preserved exact evidence-ID validation, whole-document presence checks, numerical verification, reference-risk safeguards and deterministic recommendation consistency.
- Added a safe adjudication timeout message that instructs the user to resume while reusing all three completed examiner checkpoints.
- Reduced the active External Assessment workflow from five model calls to four.
- Bumped final and external pipeline identifiers while retaining compatible v1.9.3 supervisory chapter checkpoints.
- Added combined workflow regression tests.
- Passed 173 automated tests.

# Changelog

## v1.9.2 - Stable section recovery

- Fixed the repeated pause/resume loop at 64% during section coverage recovery.
- Added a compact GPT-5.4 focused recovery request for each omitted section.
- Reuses completed section checkpoints and retries only unresolved sections.
- Preserves unresolved sections without inventing comments or labelling present content as missing.
- Added progress messages from 64% to 67% during focused recovery.
- Limited automatic resumes so the browser and server cannot restart the same failing stage indefinitely.

## v1.9.1

- Replaces the single o3-mini workflow with role-based OpenAI routing.
- Uses GPT-5.4 mini for fast chapter-level review of Bachelor’s and taught Master’s work.
- Uses GPT-5.4 for academically decisive Research Master’s/MPhil sections and every substantive Professional Doctorate or PhD section.
- Uses GPT-5.4 for the universal factual, evidence and placement audit at Light, Standard and Advanced depth.
- Uses GPT-5.4 for every External Assessment stage and `xhigh` reasoning for the confidential final decision.
- Keeps grouped concurrent chapter review, durable checkpoints and focused evidence packets to preserve speed and control cost.
- Applies model-specific token-cost tracking for GPT-5.4 mini and GPT-5.4.
- Ignores stale `OPENAI_REVIEW_MODEL=o3-mini` settings so they cannot silently downgrade the active workflow.
- Writes the logged-in user’s full name and derived initials as the native Microsoft Word comment author instead of “Supervisor Assistant”.
- Stores the reviewer identity with the completed review and reuses it during annotated-document regeneration.
- Versions review, audit, External Assessment and annotation outputs so earlier cached results are not restored.
- Passed 159 automated tests.

## v1.9.0

- Adds **Stop review** to active queued and processing jobs in Review History and the live review workspace.
- Stops scheduling further stages, cancels the active application task and releases the worker lease.
- Preserves the uploaded document and every completed checkpoint so the review can be resumed manually later.
- Introduces a durable `stopped` status that is excluded from automatic startup recovery and delayed auto-resume.
- Adds confirmation prompts and clear portal guidance to prevent accidental stops.
- Keeps stalled-stage recovery available alongside the Stop action.
- Exposes `stop_url` in queued and active job responses for the browser client.
- Adds cancellation handling that prevents a user-stopped job from being marked complete by an older worker.
- Passed 156 automated tests.

## v1.8.9

- Moves all active supervisory-review, universal accuracy-audit, recovery and External Assessment calls to OpenAI `o3-mini` through the Responses API.
- Requires `OPENAI_API_KEY` for Light, Standard and Advanced reviews. Legacy DeepSeek settings remain dormant for backwards compatibility only.
- Uses strict OpenAI structured outputs for every academic-review and examination stage.
- Applies high reasoning effort by default while preserving the same factual manifest, exact evidence, table-placement and recommendation safeguards at every review depth.
- Adds OpenAI-specific incomplete-response and output-truncation detection so recoverable jobs pause or retry safely rather than accepting partial JSON.
- Adds request-level timeout and retry overrides to the OpenAI provider for External Assessment stages.
- Increases reasoning-model output budgets and timeouts to reduce truncation on long scholarly reviews without weakening the evidence checks.
- Updates cost tracking to the current configured o3-mini token rates.
- Changes document, academic-review, accuracy-audit and External Assessment checkpoint hashes so older provider outputs are not reused.
- Keeps provider and model names out of the supervisor and student interface.
- Passed 153 automated tests, including Responses API payload, strict-schema and incomplete-output regression tests.

## v1.8.8

- Treats institutional chapter structures as whole-chapter coverage guides rather than content requirements for the chapter heading or each subsection.
- Excludes bare chapter markers, chapter titles and heading-only parent containers from substantive section review, preventing false instructions to populate already complete chapters.
- Recognises the chapter Introduction as the place for a concise chapter purpose and roadmap, and suppresses requests for a second introduction under the chapter title when one already exists.
- Rejects unsupported claims about ANOVA, regression, correlation, tables or other analyses in strengths, findings and section summaries unless the cited section contains that material.
- Requires the named section or subsection to appear in the evidence for every comment, including cross-section findings.
- Preserves cross-section method evidence while anchoring table-related comments to the exact cited table, and removes evidence from unrelated tables.
- Uses exact, chapter-aware heading matching for native Word comments, preventing comments from being attached to keywords or same-named sections in another chapter.
- Keeps same-named sections, such as Introduction and Chapter Summary, separate by chapter in the supervisor report.
- Stops keyword entries and reference-list entries from being misclassified as independent academic sections.
- Separates References and Appendices from Chapter Five so back-matter comments are not reported under the conclusion chapter.
- Builds the study-context summary from the title, abstract, purpose, problem, delimitation, study area and population rather than countries or sectors mentioned only in the literature review.
- Invalidates earlier document-analysis, section-review, accuracy-audit and completed-review checkpoints so inaccurate v1.8.7 findings are not restored.
- Passed 151 automated tests, including attachment-derived regressions for Chapter Three structure, ANOVA claims, exact table placement, back matter and chapter-aware section grouping.
## v1.8.7

- Makes native Microsoft Word comments the only annotation output mode.
- Removes all inline green comment paragraphs, appended supervisor-note sections and red text recolouring from annotated documents.
- Preserves the document body, visible formatting, headings, tables and pagination while anchoring comments to exact quotations, paragraphs, headings or table captions.
- Places otherwise unanchored findings in document-level native comments attached to existing text rather than inserting new content.
- Regenerates older annotated outputs at download time from the saved source DOCX when persistent job payloads are available.
- Blocks delivery of legacy inline-comment files when the original source is unavailable, with a clear instruction to submit a fresh review.
- Records `annotation_mode=native_word_comments` and a versioned annotation exporter so cached legacy files are not reused.
- Passed 137 automated tests, including OOXML package checks for `word/comments.xml`, comment ranges and unchanged visible document content.

## v1.8.6

- Applies the same factual-verification and expert-review threshold to Light, Standard and Advanced supervisory reviews.
- Builds a whole-document factual manifest of exact headings, substantive section content, chapters, tables, captions and evidence locations before review.
- Rejects false missing-chapter, missing-methodology, missing-results and missing-conclusion claims when the content exists elsewhere in the document.
- Reanchors synthetic audit findings to the actual source section and prevents audit labels from becoming annotation locations.
- Runs an independent evidence-complete accuracy audit over every proposed comment at every selected depth.
- Adds a deterministic final accuracy gate that removes unsupported, misplaced, overly broad and contradictory findings.
- Parses embedded table captions, preserves the actual table number and title, corrects conflicting model references and rejects table claims without table evidence.
- Adds cross-chapter expert checks for causal language in cross-sectional designs, sampling-formula incompatibility, simultaneous-regression promises versus separate models, `p = .000` reporting and declaration grammar.
- Exports native Microsoft Word comments anchored to exact text, headings, captions or relevant paragraphs, avoiding pagination changes caused by inline green comment paragraphs.
- Versions document-analysis, primary-review, audit and completed-review checkpoints so v1.8.5 annotations are not restored.
- Passed 135 automated tests and structural/visual DOCX validation.

## v1.8.5

- Grounds every supervisory finding in evidence from the section or subsection being reviewed.
- Rejects findings without valid evidence and prevents evidence from one section being used to criticise another.
- Runs an independent compact comment-accuracy audit for Light, Standard and Advanced reviews.
- Removes unsupported, generic, misplaced and repetitive comments before the final report and annotation are produced.
- Carries exact section paths, section headings, table numbers, table titles and table rows through extraction, review, reporting and annotation.
- Requires table-related comments to identify the relevant table number and title.
- Links table-caption evidence to the physical table and places annotations after the correct table.
- Colours text red only when the quoted source text is an exact match. Otherwise, the comment is placed after the correct paragraph without arbitrary red highlighting.
- Separates academic level from review depth. Bachelor’s, Non-Research Master’s, Research Master’s or MPhil, Professional Doctorate and PhD work now receive distinct benchmarks at every review depth.
- Versions document extraction, section review, completed supervisory review and comment-audit checkpoints so previous annotations are not restored.
- Passed 129 automated tests, including every academic level at Light, Standard and Advanced depth.

## v1.8.4

- Replaces the long 87% external-assessment bottleneck with a five-stage fast grounded workflow.
- Runs foundation, results/interpretation, and integrity/contribution assessments concurrently.
- Runs the corrections schedule and final examiner decision concurrently after the domain assessments complete.
- Splits the former large evidence request into smaller, method-focused requests to reduce provider latency and schema failures.
- Reports progress as each independent stage finishes instead of remaining at 87% until every assessment request completes.
- Reduces redundant prompt material while preserving the source manifest, evidence IDs, contradiction checks, numerical verification, reference-risk safeguards, and recommendation consistency rules.
- Limits each external-assessment request to four minutes and each stage to ten minutes, then pauses safely for recovery rather than appearing to process indefinitely.
- Uses one concise evidence-grounded retry instead of three potentially long attempts.
- Invalidates the old stalled external-assessment completion checkpoint while retaining the completed document extraction and academic review checkpoints.
- Adds configurable external-assessment request timeouts, retry limits, and stage-specific output budgets.
- Passed 109 automated tests.

## v1.8.3

- Detects a processing stage that has made no checkpoint progress for 30 minutes.
- Shows **Recover stalled stage** in Review History.
- Cancels the local stuck task, releases the lease, and restarts only the interrupted stage.
- Preserves all completed checkpoints.
- Adds a 20-minute hard timeout to each external-assessment model stage.
- Stops automatic retry loops for external-assessment timeouts and provider failures.
- Prevents an old worker from completing a job after its lease has been replaced.

## v1.8.2

- Makes evidence-validation failures recoverable when the original upload is still stored.
- Adds a **Recover** action for existing failed jobs that still have a saved payload.
- Allows the resume endpoint to revive pre-v1.8.2 failed jobs without a database edit.
- Retries only the interrupted stage and preserves completed checkpoints.
- Exposes recovery URLs in job status responses and supports automatic browser recovery.

## v1.8.1

- Fixed the External Assessment foundation-stage failure caused when a model cited a valid manifest evidence token that was not included in that stage's bounded source excerpts.
- Removed raw evidence IDs from the compact manifest supplied to generation prompts, while retaining presence status and evidence counts. This prevents manifest-only IDs from being mistaken for citable source evidence.
- Added a grounded retry mechanism. When a failed attempt cites an otherwise valid thesis evidence ID, the next attempt receives both that ID and its full source excerpt.
- Redacted unsupported evidence tokens from retry feedback so the model is not prompted to repeat the rejected token.
- Clarified that evidence IDs are opaque tokens and must be copied exactly from `allowed_evidence_ids`, not constructed from page or paragraph numbers.
- Versioned External Assessment stage and completion checkpoints so failed v1.8.0 outputs are not restored after deployment.
- Added regression tests for manifest-ID leakage, retry-token redaction and recovery of valid out-of-selection evidence.

## v1.8.0

- Rebuilt External Assessment around a source manifest that records extracted words, chapters, research functions, tables, appendices, metadata, coverage warnings and stable evidence identifiers.
- Added functional chapter mapping so seven-chapter, doctoral and custom thesis structures are assessed by research purpose rather than a fixed five-chapter assumption.
- Added balanced evidence selection for foundation, literature, methodology, results, discussion, conclusions and ethics so later chapters cannot disappear because of sequential prompt truncation.
- Added title-page metadata recovery for candidate name, candidate number, degree programme, institution and thesis title.
- Changed the absence rule so content may be called missing only when the manifest explicitly marks it as confirmed absent. Retrieval uncertainty is never converted into an academic deficiency.
- Added evidence IDs to every assessed domain and every correction, with deterministic rejection of invented IDs, irrelevant evidence and unsupported numerical claims.
- Added method-specific examiner rubrics for PLS-SEM, covariance-based SEM, econometrics, qualitative inquiry and mixed-methods research.
- Added source-presence contradiction checks that remove defective derivative findings and stop the final report when generated conclusions conflict with the thesis.
- Added a source-evidence dossier to the confidential decision stage so the final recommendation audits earlier examiner findings against the cited thesis text.
- Added a fail-safe recommendation rule. Limited or insufficient extraction now produces an assessment-withheld outcome with low confidence, never a pass, major-correction, re-examination or fail recommendation.
- Added source coverage, evidence references and audit status to the external examination DOCX outputs and corrections schedule.
- Added a source evidence register to the examiner outputs, linking every cited evidence ID to its thesis location, heading and supporting excerpt.
- Versioned the document, academic-review, External Assessment and final checkpoints so earlier defective cached assessments are not reused.
- Added an Edmund Animley seven-chapter regression test covering the candidate metadata, literature review, conceptual model, hypotheses, methodology, PLS-SEM results, discussion, conclusions, questionnaire and ethical-clearance appendix.
- Added regression tests for DOCX chapter retention, false missing-content claims, evidence relevance, numerical grounding and extraction-based recommendation withholding.

## v1.7.0

- Added durable job payload storage so uploaded theses, context chapters and examiner documents can be reloaded after a process interruption.
- Added database-backed checkpoints for document analysis, each academic-review batch, the doctoral quality audit, every External Assessment stage and the final assembled review.
- Added automatic resume on service startup and automatic retry of recoverable provider or timeout interruptions.
- Added worker leases and heartbeats to reduce duplicate processing when a service restarts or more than one instance is active.
- Added a manual Resume action in the lecturer portal for paused jobs.
- Interrupted jobs now remain Paused and recoverable instead of being marked as permanently failed.
- Final candidate-facing or examiner reports are generated only after every compulsory stage is complete. No partial final report is issued.
- Restored checkpoints are skipped, preventing repeated model calls and repeated token charges.
- Moved synchronous document extraction and annotated-DOCX generation off the event loop.
- Increased controlled academic-review parallelism from three to four calls by default.
- Ran the independent foundation/methodology and evidence/contribution External Assessment stages concurrently, while retaining the corrections and final-decision dependency chain.
- Added persistent Render disk configuration at `/var/data` for saved payloads, checkpoints and reports.

## v1.6.2

- Made review-job progress monotonic in both the server and browser.
- Delayed progress callbacks from concurrent AI stages can no longer reduce the stored percentage.
- A delayed earlier-stage callback can no longer replace the current later-stage progress message.
- Persisted database progress now retains the highest percentage reached.
- Browser polling retains the highest percentage displayed even when a stale response arrives.
- Active-job progress is saved in local storage and restored after refresh or reconnection instead of resetting to 4%.
- Starting a genuinely new review still resets the progress indicator to 2%.

## v1.6.1

- Replaced the single very large External Assessment model response with a four-stage examiner workflow.
- Generates foundation and methodology, findings and contribution, corrections and oral questions, and the final confidential recommendation separately before merging them into one validated report.
- Added concise automatic recovery for truncated, timed-out, empty, invalid or schema-incomplete assessment stages.
- Added stage-specific output-token settings so long PhD and Professional Doctorate assessments do not depend on one 9,000-token response.
- Added progress messages for each assessment stage and records staged generation in internal usage metadata.
- Limited repetitive lists and consolidated corrections to reduce token exhaustion while retaining examiner-ready depth.

## v1.6.0

- Added External Assessment as a separate workflow from Supervisory Review.
- External Assessment accepts complete theses and dissertations across Bachelor’s, taught Master’s, Research Master’s/MPhil, Professional Doctorate and PhD levels.
- The assessment standard is selected automatically from the academic level while remaining sensitive to quantitative, qualitative, mixed-method, SEM and econometric approaches.
- Added a critical Chapter One or foundational-chapter examination gate covering the problem, gap, purpose, objectives, questions or hypotheses, significance, scope and whole-thesis direction.
- Added degree-level judgements for literature and theory, methodology, results, discussion, conclusions, originality, coherence, presentation, ethics and research integrity.
- Added formal external examiner recommendations, prioritised corrections, publication potential, viva questions and confidential comments to the university.
- Added Initial Examination, Re-examination and Corrected Thesis Verification stages.
- Re-examination and corrected-thesis verification can ingest earlier examiner reports, correction schedules and an optional earlier thesis version.
- Added four DOCX outputs: full external examination report, corrections schedule, confidential recommendation and oral examination question bank.
- Doctoral external assessment accepts custom chapter titles, order and structures and judges functional completeness rather than enforcing five chapters.
- Added workflow persistence and a database migration for existing deployments.
- Added portal and completed-review links for all external examination outputs.

## v1.5.7

- Added a Combined Chapters review scope.
- Users can select Chapters 1–2, 1–3, 1–4 or 1–5.
- The selected range always begins with Chapter One and must contain every preceding chapter.
- The review is rejected before AI processing when any chapter in the selected range is missing.
- Every chapter, section and subsection in the selected range is reviewed.
- Sequential cross-chapter alignment is checked for Chapter Two and each later chapter in the selected range.
- Any chapters outside the selected range are used only as alignment context.
- Statistical diagnostics and accuracy checks run automatically when the combined range includes Chapter Three or Chapter Four.
- Added combined-range labels and metadata to the review output and AI review packet.

## v1.5.6

- Made complete-thesis structure validation level-sensitive.
- Retained the standard five-chapter completeness gate for Bachelor’s and Master’s theses.
- Allowed Professional Doctorate and PhD theses to use custom chapter numbers, order and titles.
- Added flexible doctoral functional-completeness validation covering the research problem, literature and theory, methodology, evidence and findings, discussion and synthesis, and conclusions and contribution.
- Prevented a doctoral thesis from being rejected merely because it does not follow five chapters.
- Retained rejection of genuinely incomplete doctoral uploads that omit essential research functions.
- Changed local checklist searching for doctoral complete theses from chapter-number positions to document-wide research functions.
- Added doctoral structure guidance to the interface, AI review contract and supervisor report.

## v1.5.5

- Added the missing `build_statistical_review` import in `app/review_engine.py`.
- Prevented the Chapter Three and Chapter Four review workflow from failing with `NameError`.
- Added a regression test that imports the live review engine and confirms the statistical review function is available.

## v1.5.4

- Updated the landing-page hero to show “Hello!” followed by the V-Prof introduction.
- Applied the reference blue only to `V-Prof {supervisor name}`.
- Kept the remaining hero text in the normal dark interface colour.

## v1.5.3

- Changed the Virtual Professor hero heading to the blue used in the supplied reference.
- Added a dedicated `--hero-heading` colour variable with value `#4557D5`.
- The colour change applies only to the main hero heading.

## v1.5.2

- Made chapter and section numbering optional.
- Chapter titles and recognised section headings are now the primary basis for chapter identification.
- Added direct detection of unnumbered chapter titles such as Introduction, Literature Review, Research Methods, Results and Discussion, and Summary, Conclusions and Recommendations.
- Retained section numbering such as 1.1 or 4.2 as supporting evidence where a school, department or student uses it.
- Prevented an unnumbered Introduction subsection inside a later chapter from being treated as Chapter One.
- Updated mismatch guidance so students are not instructed to number headings when numbering is not required.
- Section-heading text remains the main reference in review comments, with section numbers included only when present.

## v1.5.1

- Rebuilt chapter identification around explicit chapter titles and UCC-style numbered section headings such as 1.1, 3.4 and 5.2.
- Removed global keyword leakage that could treat an Introduction subsection in Chapter Four or Five as Chapter One.
- Complete-thesis rejection messages now list every missing standard chapter function accurately.
- A selected chapter is rejected before review when the uploaded chapter title or section numbering identifies a different chapter.
- Strong component-aware fallback is retained only for genuinely unnumbered standalone chapters.
- Composite uploads are segmented by chapter, and only the selected chapter is reviewed. Other chapters remain alignment context.
- Added DOCX table-row extraction so statistics in tables are available to the academic review.
- Added section-number, table and chapter-detection metadata for clearer evidence references.
- Added model-specific diagnostic checks to Research Methods and Results and Discussion.
- Added deterministic screening for invalid p-values, R-squared values, percentages, reversed confidence intervals, coefficient-sign contradictions and p-value interpretation contradictions.
- Strengthened checks for sample-size, total, percentage, table, figure and narrative reconciliation.

## v1.5.0

- Added a complete-thesis structure gate before AI review begins.
- A complete thesis must cover the five standard research functions: Introduction, Literature Review, Research Methods, Results and Discussion, and Summary/Conclusions/Recommendations.
- Additional discipline-specific chapters are allowed and receive an integration and cross-thesis alignment audit.
- When a selected chapter is contained in a composite upload, only that chapter is reviewed. Other embedded chapters are used solely for alignment.
- Removed the requirement to upload previous chapters separately when they already exist in the main composite file.
- Strengthened Chapter One review of the research problem, objective flow, research-question alignment and hypothesis adequacy.
- Strengthened Chapter Two review of concepts, theories and critically synthesised empirical literature.
- Strengthened Chapter Three objective-method-question-hypothesis alignment and procedural defensibility.
- Strengthened Chapter Four accuracy, completeness, interpretation and discussion checks.
- Strengthened Chapter Five checks against repeating the analysis and for findings-based conclusions and recommendations.
- Kept the concise supervisor report while listing every material correction in summary form.

## v1.4.3

- Replaced the landing-page hero writeup with one concise message.
- The hero now displays: "Meet Virtual Professor {supervisor name} (V), your Academic Supervision and Assessment Assistant."
- Removed the previous eyebrow line, supporting paragraph and feature chips from the hero section.

## v1.4.2

- Replaced the bulky review-report DOCX with a concise human-supervisor summary.
- Kept the annotated Word document unchanged as the detailed review record.
- Limited the summary report to the overall comment, main strengths, and key corrections by chapter or section.
- Limited each chapter or section to two strengths and three principal corrections.
- Grouped complete-thesis reviews by chapter to prevent excessively long reports.
- Removed detailed review points, long examples, repeated locations and separate source-verification narratives from the summary report.
- Added a compact supervisor recommendation and up to five immediate revision priorities.

## v1.4.1

- Reduced Advanced Review from repeated per-section audits to one compact doctoral audit.
- Increased safe section batching for Light, Standard and Advanced Review.
- Changed Advanced primary review from maximum to high reasoning.
- Reserved maximum reasoning for the single final doctoral audit.
- Retried omitted sections in grouped batches instead of one request per section.
- Added a transparent fallback for up to two omitted short sections such as a title.
- Reduced output-token limits and repetitive findings without reducing section coverage.
- Added live section-group progress and internal API call counts.
- Disabled structured-output retries by default to prevent duplicate successful calls.

## v1.4.0

- Routed Advanced Review through DeepSeek V4 Pro with maximum reasoning.
- Added an independent DeepSeek second-pass audit for doctoral reviews.
- Removed OpenAI as a requirement for active review routing.
- Added an internal academic review guide adapted from the supplied thesis self-evaluation framework without exposing checklist codes.
- Added a document-derived context lock to prevent foreign countries, settings, organisations and populations from leaking into examples.
- Added safeguards against invented citations, reports, statistics and percentages.
- Distinguished missing sections from weakly developed sections and made unconfirmed methodological advice conditional.
- Consolidated repetitive academic-writing, terminology and source-verification findings.
- Reworked the supervisor report to show recognised study context, concise priorities, a dedicated evidence-verification section and less repetitive section reviews.
- Shortened annotated-document comments while preserving actionable guidance.

## v1.3.2

- Replaced heading-based AI section keys with short stable identifiers.
- Added tolerant matching by exact key, compact key, section heading, and single-section retry.
- Prevented valid title reviews from being rejected when a provider changed the title key.
- Stopped browser polling immediately when a review job reaches failed status.
- Preserved safe provider failure details in the lecturer-facing error message.

## v1.3.1

- Removed the fixed 30-minute browser failure for active reviews.
- Added automatic reconnection after page refresh or temporary connection loss.
- Stored the active review job in browser local storage.
- Changed polling responses to return a result URL instead of the complete review object.
- Added a 90-minute server-side maximum job duration with a clear failure message.
- Added more progress updates during section coverage and recovery.
- Extended client polling to two hours with slower polling after 30 minutes.

## v1.3

- Replaced separate-looking login screens with one unified institutional access page.
- Added top-level Supervisor and Admin tabs similar to the Kanokwere role switcher.
- Preserved separate secure login routes and role permissions.
- Redesigned the login page with a responsive institutional hero and compact sign-in card.
- Changed public-facing “Lecturer” labels to “Supervisor” while retaining the internal database role for compatibility.
- Improved mobile and tablet responsiveness.

## v1.2

- Routed Light Review through DeepSeek V4 Pro.
- Routed Standard Review through DeepSeek V4 Pro.
- Routed Advanced Review through GPT-5.4.
- Removed GPT-5.5 and GPT-5.4 mini from active review routing.
- Kept complete section and subsection coverage for all review levels.
- Added DeepSeek JSON-schema reinforcement, structured-output retry, usage tracking, and provider smoke testing.
- Limited the additional quality-control pass to Advanced Review.

# Changelog

## 1.0.0

- Changed Light, Standard and Advanced Review so each level reviews every detected section and subsection.
- Reframed the three levels by academic benchmark rather than document coverage:
  - Light: Bachelor’s or non-research Master’s standard
  - Standard: Research Master’s or MPhil standard
  - Advanced: Professional Doctorate or PhD standard
- Removed the global Light Review limit of 12 findings.
- Removed the rule that automatically downgraded every critical Light Review finding.
- Added proportional severity guidance so Light Review remains less demanding while still identifying a missing core element or serious contradiction.
- Added a whole-chapter coherence audit to Light Review.
- Added a coverage contract requiring one substantive response for every section key.
- Added automatic individual retry for any section omitted from a valid batch response.
- Prevented report export when any section or subsection remains unreviewed.
- Added the review benchmark and number of sections reviewed to the Word report.
- Restructured the report to include every section and subsection, while showing detailed review points only where revision is necessary.
- Preserved context-aware examples and practical guidance across all three review levels.
- Kept the existing model routing: GPT-5.4 mini for Light, GPT-5.4 mini plus GPT-5.4 for Standard, and GPT-5.4 plus GPT-5.5 for Advanced.

## 0.9.0

- Added Light Review alongside Standard and Advanced Review.
- Added safeguards for source-verification and research-integrity warning signs.
- Added context-aware guidance and grouped annotations.

## 1.1.0

- Added secure administrator login and institutional dashboard.
- Added administrator-created lecturer accounts with generated temporary passwords and recovery PINs.
- Added lecturer login, first-login password change, password recovery, suspension and reset workflows.
- Added lecturer portal with review history, progress, downloads and revised-submission tracking.
- Added persistent account and review metadata storage through SQLite or PostgreSQL.
- Added ownership checks for review jobs, results and downloads.
- Added CSRF protection, signed sessions and login-attempt lockout.
- Added durable review JSON and annotated-document storage when `REVIEW_STORAGE_DIR` is backed by a persistent disk.

## v1.9.3 — Simplified chapter-level supervisory review

- Reorganised the active supervisory-review workflow around complete chapter packets rather than many small section batches.
- Reviews independent chapters concurrently, while long chapters split only at section boundaries.
- Replaced grouped, single-section and focused recovery chains with one bounded chapter-packet retry.
- Prevents the repeated 64% pause/resume loop caused by one omitted section response.
- Preserves unresolved sections without inventing findings or describing present content as missing.
- Increased the default factual-audit batch size from 24 to 48 findings to reduce API round trips.
- Kept GPT-5.4 mini for routine chapter review and GPT-5.4 for research-intensive review and final factual audit.
- Clarified that Light review may be concise but cannot omit critical or major issues.
- Invalidated earlier supervisory-review checkpoints by introducing v1.9.3 pipeline identifiers.
- Added chapter-packet execution and recovery configuration.
- Passed 170 automated tests.

## v1.9.8.7 - Section Coverage Comments

- Added native Word section-level review comments so every detected section or subsection receives visible feedback, even when no issue finding is exported for that section.
- Preserved the existing issue comments as primary feedback while anchoring section assessments to exact headings where possible.
- Kept comments natural and non-mechanical, without checklist labels.
- No new environment variable or database migration is required.
