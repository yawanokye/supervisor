# Supervisor Assistant v1.8.6

## Universal factual and expert supervisory review

This release addresses the false, misplaced and statistically incomplete comments identified in the reviewed undergraduate project. The same factual-accuracy controls now apply to Light, Standard and Advanced review. Review depth changes the amount of feedback, not the evidential standard.

### Whole-document factual manifest

- Builds a document-wide index of chapters, exact section and subsection headings, substantive section content, tables, table captions and evidence locations before the model reviews the work.
- Prevents a chapter, results section, methodology, conclusion or recommendation section from being called missing when substantive content exists elsewhere in the document.
- Distinguishes confirmed absence, underdevelopment and extraction uncertainty.
- Treats synthetic review labels such as “whole-chapter coherence audit” as audit categories, never as document headings or annotation locations.

### Universal accuracy audit at every depth

- Every proposed issue from Light, Standard and Advanced review is independently rechecked against the full relevant source evidence.
- The audit uses the strongest configured review model and maximum reasoning regardless of selected depth.
- Unsupported findings are removed rather than softened or exported.
- If a provider audit batch fails, only high-confidence source-supported findings can proceed, after deterministic validation.
- The final gate records how many comments were kept, corrected or rejected.

### Exact sections, subsections and tables

- Findings are anchored to the actual section or subsection that contains their evidence.
- Comments that drift from one section into another are reanchored or rejected.
- Embedded and external table captions are parsed and associated with the physical table.
- Table comments use the actual table number and title from the source evidence.
- A model-generated table number that conflicts with the source is corrected automatically.
- Table claims without table evidence are rejected.

### Deterministic expert checks

The review now performs source-based checks that do not depend only on model judgement. These include:

- cross-sectional design combined with unsupported causal language
- use of a probability sample-size formula followed by non-probability respondent selection
- a methodology promising simultaneous multiple regression while the results present only separate one-predictor models
- reporting `p = .000` instead of `p < .001`
- declaration grammar such as “I … is entirely my own original work”

These checks run at every selected depth and are calibrated to the selected academic level.

### Safer annotation

- Supervisor feedback is written as native Microsoft Word comments where supported by `python-docx`.
- Comments are anchored to an exact problematic quotation, heading, table caption or relevant paragraph.
- Source text is coloured red only after exact quotation matching.
- Comments no longer become green body paragraphs that alter pagination or split tables.
- The legacy inline-comment method remains only as a fail-safe when the Word comment API is unavailable.

### Checkpoint protection

- Document-analysis, primary review, universal comment-audit and completed-review checkpoint versions were updated.
- Earlier v1.8.5 supervisory findings will not be restored into a new v1.8.6 review.
- External Assessment remains on the v1.8.4 fast grounded workflow and is not otherwise changed by this release.

### Updated files

- `app/supervisory_accuracy_guard.py` (new)
- `app/document_parser.py`
- `app/review_engine.py`
- `app/academic_ai_engine.py`
- `app/ai_prompts.py`
- `app/annotated_exporter.py`
- `app/main.py`
- `requirements.txt`
- `README.md`
- `DEPLOYMENT.md`
- `tests/test_fast_review_workflow.py`
- `tests/test_grounded_annotations_v185.py`
- `tests/test_supervisory_accuracy_v186.py` (new)
- `CHANGELOG.md`

## Validation

- 135 automated tests passed.
- Python compilation passed for the application and test suite.
- Native Word comment structure was verified in a generated DOCX.
- The sample DOCX was rendered and visually inspected to confirm that comments no longer alter the document body layout.
- Regression tests cover false missing-section claims, synthetic-location drift, incorrect table numbers, embedded captions, method-results inconsistency and deterministic accuracy-gate reporting.
