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
