# Updated files in v1.8.8

- `app/ai_prompts.py`
  - Clarifies that chapter structures are whole-chapter guides.
  - Requires exact section and table evidence for every comment.
  - Prevents unsupported analysis claims and duplicate chapter introductions.

- `app/academic_ai_engine.py`
  - Excludes structural chapter and parent headings from substantive review.
  - Preserves chapter number and section path throughout review and reporting.
  - Applies factual validation to strengths and section assessments.
  - Versions primary and accuracy-audit checkpoints.

- `app/supervisory_accuracy_guard.py`
  - Rejects false completeness claims, unsupported ANOVA or regression claims, misplaced evidence and ambiguous table comments.
  - Preserves method evidence in valid cross-section findings while selecting the exact table anchor.

- `app/document_parser.py`
  - Treats keyword lists and reference entries as content under their actual sections.
  - Resets chapter assignment for References and Appendices.

- `app/annotated_exporter.py`
  - Uses exact chapter-aware heading and table placement for native Word comments.

- `app/report_exporter.py`
  - Keeps same-named sections separate by chapter and removes unverified assessment text from strengths.

- `app/context_guard.py`
  - Derives the reported study country, setting and field only from study-defining sections, not comparative literature.

- `app/main.py`
  - Updates the application and completion-checkpoint versions to 1.8.8.

- `tests/test_factual_placement_v188.py`
  - Adds regression tests for false Chapter Three instructions, unsupported ANOVA claims, exact table anchoring, structural parent headings, back matter and same-named sections.
