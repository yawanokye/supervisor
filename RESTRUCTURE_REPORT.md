# V-Professor v2.0.0 Professional Review Restructure

## Purpose

This release restructures V-Professor around the way a human supervisor works. The supervisor chooses the review scope, the system reviews only that scope, every material finding is anchored to the exact affected text, and the final report states the actions required before the work is ready for supervisor approval or submission.

The implementation adapts the useful action-planning, analysis-verification and readiness logic from JournalReady/ArticleReady and combines it with the thesis-structure, chapter-role and alignment logic used in ThesisReady.

## 1. Supervisor-controlled chapter and section scope

The review workspace now supports:

- one complete chapter;
- selected sections within one chapter;
- a combined chapter range;
- a complete thesis; and
- external assessment.

For a selected-section review, the supervisor uploads the chapter and selects **Scan headings**. V-Professor returns the detected chapter outline and presents checkboxes for the available sections. The selected heading boundaries are saved with the job and passed through document analysis, AI review, finding validation, reports and annotations.

Unselected sections are removed from:

- academic findings;
- section assessments;
- strengths;
- alignment and revision rows;
- priority actions;
- Word comments;
- inline comments; and
- the final action report.

Where reliable headings cannot be detected, V-Professor discloses that section selection cannot be isolated safely and retains the whole chapter rather than pretending to review an uncertain range.

## 2. Degree structure rules

The default structure for Bachelor’s, Non-Research Master’s, Research Master’s/MPhil and Professional Doctorate work remains the standard five-chapter research architecture:

1. introduction and research problem;
2. literature, theory and conceptual framing;
3. methodology;
4. results and discussion; and
5. conclusions, contribution and recommendations.

Justified additional chapters are allowed, but they cannot replace a missing core research function.

PhD work may use a variable architecture, including monograph, article-based, essay-based, portfolio, practice-based and discipline-specific structures. V-Professor classifies chapters by their actual function and checks whether the thesis contains and integrates all prescribed doctoral elements. It does not penalise a PhD merely for departing from five chapters.

## 3. ArticleReady-style supervisory action report

The final report now contains **Actions Required Before Supervisor Approval or Submission**. Each action gives:

- priority;
- exact location;
- specific correction required;
- why the correction matters academically; and
- how the supervisor or student can verify that the correction is complete.

Actions are classified as:

- **Essential before approval** for critical and major findings;
- **Strongly recommended** for moderate findings; and
- **Optional refinement** for minor findings.

The readiness decision is based on unresolved evidence-backed findings rather than a predetermined comment count.

## 4. Native Word comments

Native comments are now tied to the exact sentence, paragraph or table row that requires correction.

The export rules are:

- two or more findings on the same sentence use one native Word comment box;
- the individual actions inside that box are numbered;
- findings on different sentences remain separate, even when they occur in the same paragraph;
- comments on a table are attached to the relevant caption, row or cell evidence;
- visible location markers are not inserted into the body text; and
- decimals, p-values, temperatures, equations, citations, URLs and DOI strings remain unchanged.

The exporter no longer merges findings merely because they occur in the same section. Grouping requires a shared verified text anchor.

## 5. Inline annotated copy

The inline annotated document uses the same canonical finding ledger as the native-comment copy.

For each affected paragraph:

- the relevant sentence or passage is marked;
- one numbered supervisor note is inserted immediately after the paragraph;
- findings sharing the same sentence are grouped in that note; and
- findings concerning different sentences are kept separate and ordered by their position in the paragraph.

This ensures that the student sees the correction beside the exact passage concerned rather than in a detached appendix only.

## 6. Statistical accuracy and adequacy review

The statistical-review layer distinguishes **accuracy** from **adequacy**.

### Accuracy checks

V-Professor checks document-level internal consistency, including where applicable:

- valid p-value, percentage, reliability and R² ranges;
- agreement between significance statements and p-values;
- coefficient-sign interpretation;
- coefficient, standard error and test-statistic reconciliation;
- coefficient and confidence-interval agreement;
- F, t, R², degrees of freedom and sample-size relationships;
- frequency, percentage and sample-size reconciliation;
- table totals and transcription consistency; and
- agreement between tables and narrative claims.

### Adequacy checks

The system detects the reported analytical route and checks the evidence expected for that route. Examples include:

- regression assumptions, uncertainty and model diagnostics;
- moderation interaction terms, conditional effects and incremental variance;
- mediation indirect effects and bootstrap intervals;
- SEM measurement and structural model separation, reliability and validity;
- panel and time-series diagnostics;
- measurement and scoring consistency;
- qualitative evidence and trustworthiness procedures; and
- methods-results-discussion alignment.

Where further analysis is required, the report states:

- the rationale;
- data or source material required;
- suitable method;
- output that must be reported; and
- consequence of omission.

V-Professor does not claim that a suggested analysis has already been performed. Definitive recalculation requires the original dataset, syntax and complete software output.

## 7. One canonical finding ledger

All outputs now rebuild from one filtered finding ledger. This reduces disagreement among:

- the on-screen review;
- native comments;
- inline comments;
- the supervisory report;
- the priority action schedule; and
- the professional review appendix.

Post-processing may validate, order, polish or group findings at an exact shared anchor. It may not invent a new study setting, construct, population, method or result.

## 8. Configuration and worker improvements

The production environment and Render Blueprint were cleaned so that every listed application variable is active in the code. Inactive or misleading flags were removed.

The deployment uses:

- PostgreSQL-backed job and artifact storage shared by web and worker;
- web-only job queuing;
- one controlled worker claim at a time by default;
- bounded retry and checkpoint recovery;
- Terra for routine section analysis;
- Sol for final synthesis, PhD synthesis and external adjudication;
- exact-anchor grouped native comments; and
- no visible body location markers.

The active UCC controls are retained but no longer incorrectly reported as unsupported. Institution-specific rules remain subject to institutional-profile gating.

## 9. Redundant material removed

The release removes:

- duplicate root-level Python modules;
- the unused legacy `hybrid_ai_engine.py`;
- obsolete environment and patch-note files;
- inactive Render and `.env` variables;
- historical deployment instructions replaced by the current v2.0.0 guide;
- local database files;
- Python bytecode and test caches; and
- outdated tests that asserted retired body markers, comment quotas or legacy pipeline identifiers, with their useful coverage rewritten for v2.0.0.

## 10. Main files added or substantially changed

### Added

- `app/review_scope.py`
- `app/submission_readiness.py`
- `tests/test_professional_section_scope_v200.py`

### Substantially revised

- `app/main.py`
- `app/review_engine.py`
- `app/academic_ai_engine.py`
- `app/annotated_exporter.py`
- `app/inline_annotated_exporter.py`
- `app/report_exporter.py`
- `app/articleready_review_bridge.py`
- `app/ai_config.py`
- `app/templates/index.html`
- `app/static/app.js`
- `app/static/styles.css`
- `render.yaml`
- `.env.example`
- `README.md`
- `DEPLOYMENT.md`
- `CHANGELOG.md`

## 11. Validation completed

The release passed:

```text
317 automated tests passed
Python application compilation passed
JavaScript syntax validation passed
Render YAML validation passed
.env.example duplicate-key check passed
Environment-to-code active-variable check passed
Production hardcoded-topic contamination scan passed
```

The tests cover section isolation, five-chapter and flexible-PhD structure, exact native anchoring, same-sentence grouping, immediate inline notes, statistical consistency, analysis adequacy, report actions, worker recovery, storage, authentication, token accounting and external assessment.

## 12. Deployment note

Deploy this repository as a complete replacement and redeploy both the web service and background worker. Submit active legacy reviews as new jobs because the document-analysis, academic-review, annotation and final-report checkpoint identifiers changed in v2.0.0.
