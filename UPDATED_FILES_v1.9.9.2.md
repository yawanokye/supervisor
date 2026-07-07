# Updated files in v1.9.9.2

This release addresses evidence-safety and student-facing annotation quality after testing v1.9.9.1.

## Main changes
- Prevents checklist section matching from confusing `Limitations` with `Delimitations`.
- Suppresses false Definition of Terms coverage comments when definitions are present.
- Removes internal extraction language such as manifest, document map, parser, fallback, recovery and paragraph IDs from public comments.
- Improves imperative action wording, including verbs such as populate and supply.
- Adds a non-native inline annotated DOCX export in which revision areas are coloured red and supervisor comments are inserted in blue text.

## Files changed
- app/deterministic_supervisory_checklist.py
- app/comment_quality.py
- app/annotated_exporter.py
- app/inline_annotated_exporter.py
- app/main.py
- app/static/app.js
- app/templates/index.html
- app/templates/review_detail.html
- .env.example
