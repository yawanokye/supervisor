# Updated files, V-Professor v1.9.9.30

## Release purpose

This release corrects the supervisory review architecture across all supported academic levels. Bachelor’s, Non-Research Master’s, Research Master’s/MPhil and Professional Doctorate reviews use the standard five-chapter research structure as the default. PhD review permits a variable chapter sequence and number, but release is allowed only when every prescribed doctoral research element is present and traceable across the thesis.

The production runtime source of truth is the `app/` package. Render starts the service with `uvicorn app.main:app` and the worker with `python -m app.worker`.

## New production modules

- `app/thesis_structure.py`
  - maps standard five-chapter roles for all non-PhD levels
  - infers PhD chapter roles from headings and substantive content
  - supports PhD chapters beyond Chapter Five without lowering prescribed-element coverage
- `app/thesis_alignment_matrix.py`
  - traces objectives, questions and hypotheses through methods, results, discussion, conclusions and recommendations
- `app/study_semantics.py`
  - provides domain-neutral extraction and consistency checks
  - prevents study-specific development examples from leaking into unrelated reviews

## Core review engine changes

- `app/document_parser.py`
  - enforces Chapters One to Five for non-PhD complete-thesis review
  - validates all prescribed PhD elements independently of chapter numbering
  - prevents an extra chapter from replacing a missing required standard chapter
- `app/review_engine.py`
  - applies flexible architecture only to PhD
  - supports PhD chapter selections up to Chapter Twenty
  - builds the thesis role map and objective-alignment matrix
  - directs statistical review to the chapters that actually contain methods, results and discussion
  - applies institutional rules only when the relevant institutional profile is selected
- `app/professional_review_pipeline.py`
  - replaces fixed chapter-number specialist assignment with functional chapter-role assignment
- `app/academic_ai_engine.py`
  - includes the PhD prescribed-element contract, role map and alignment matrix in model prompts
  - provides chapter-balanced complete-thesis auditing
  - limits institutional contracts to the selected institution
  - strengthens finding consolidation so distinct concerns are not merged merely because they share broad academic vocabulary
- `app/ai_prompts.py`
  - states the five-chapter default for all non-PhD levels
  - lists the mandatory PhD research elements and permits justified structural variation only at PhD level
- `app/external_assessment.py`
  - applies the same structure rule to external examination and re-examination

## Review-quality and contamination corrections

- `app/human_supervisory_editor.py`
- `app/final_review_quality.py`
- `app/deterministic_supervisory_checklist.py`
- `app/supervisory_accuracy_guard.py`
- `app/ucc_section_contract.py`
- `app/comment_quality.py`
- `app/student_friendly_review.py`

These modules now derive study context, constructs, population and examples from the current thesis. Generic production rules no longer insert earlier development-study terms such as fraud and internal controls, green procurement, a named bank, Ghanaian Colleges of Education or fixed sample descriptions.

## Model routing and configuration

- `app/model_router.py`
  - honours requested final and adjudication models
  - enables bounded selective escalation for low-confidence section findings
  - separates routine Terra analysis from Sol final PhD synthesis and external adjudication
- `app/ai_config.py`
  - reads `OPENAI_PHD_FINAL_SYNTHESIS_MODEL` and its reasoning effort
  - reports unsupported legacy environment variables at startup
  - uses one retry for external assessment requests by default
- `app/main.py`
  - reports version `1.9.9.30`
  - logs the effective model route and unsupported settings
  - accepts institutional profile selection
  - supports PhD-only chapter options beyond Chapter Five
- `render.yaml`
- `.env.example`
  - use GPT-5.6 Terra for routine analysis
  - use GPT-5.6 Sol for final synthesis, PhD synthesis and external adjudication
  - enable controlled retries and strict failure for incomplete critical review stages
  - disable visible body markers and apply a safer comment similarity threshold

## Interface changes

- `app/templates/index.html`
  - adds an institutional profile selector
  - explains the difference between the Professional Doctorate five-chapter default and variable PhD architecture
  - exposes Chapters Six to Twenty only for PhD review
- `app/static/app.js`
  - dynamically enables PhD-only chapter options
  - resets invalid chapter selections when a non-PhD level is chosen
  - presents level-appropriate complete-thesis guidance

## DOCX safety changes

- `app/annotated_exporter.py`
- `app/inline_annotated_exporter.py`

Visible red location markers are disabled by default. Native Word comments are anchored without changing the student’s text. Sentence and anchor handling now protects decimal numbers, temperatures, p-values, DOI strings, abbreviations and `et al.` references. When a visible marker is explicitly enabled for diagnostic use, it is appended outside the original paragraph text rather than inserted within a number or citation.

## Documentation and tests

- `README.md`
- `CHANGELOG.md`
- `ENVIRONMENT_CHANGES_v1.9.9.30.md`
- `TEST_SUMMARY_v1.9.9.30.md`
- `tests/test_v19930_structure_quality.py`
- updated structure, routing, UI, native-comment and final-product tests

The focused v1.9.9.30 release suite passes 73 tests. The complete legacy suite reports 283 passes and 28 failures, the same failure count as the baseline. The remaining failures concern obsolete model-routing expectations, retired visible body markers, old version strings, removed finding quotas, a missing external fixture and unrelated legacy portal or deployment assumptions.
