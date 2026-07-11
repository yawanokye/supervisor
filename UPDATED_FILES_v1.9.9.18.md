# VProfessor v1.9.9.18, ArticleReady-style supervisor review upgrade

## Purpose
This update borrows the evidence-preserving review philosophy used in the ArticleReady revision module and applies it to VProfessor. The native DOCX is now treated as a delivery format only, while the review/report layer carries the full academic judgement.

## Main changes
- Added `app/articleready_review_bridge.py` for report-first, evidence-preserving review organisation.
- Updated `app/ai_prompts.py` to require ArticleReady-style method, results and discussion evaluation without assuming one method.
- Updated `app/academic_ai_engine.py` to attach the ArticleReady-style quality audit to every review payload.
- Updated `app/report_exporter.py` to add a dedicated "Method, Results and Discussion Quality Audit" section to the DOCX report.
- Corrected deterministic audit categories in `app/thorough_review.py` so method/results findings pass the public schema instead of being silently dropped.
- Added generic ArticleReady-style safeguards for objective-analysis traceability, result verifiability, discussion depth and claim strength.
- Updated `app/annotated_exporter.py` and `app/inline_annotated_exporter.py` to prevent red reference markers from splitting words in the reviewed document.
- Updated `.env.example` and `vprofessor-openai-worker.env.example` with report-first review flags.

## Behavioural correction
Native Word comments are no longer expected to carry the whole review. The app produces a stronger report first, then converts evidence-anchored corrections into native comments and inline annotations. This prevents the native DOCX layer from weakening the academic review.

## Tests
Targeted tests passed: 8 passed.
