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
