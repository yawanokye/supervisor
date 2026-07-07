# Updated files – v1.9.9.1

## Purpose
This release hardens the deterministic supervisory checklist after the v1.9.9.0 output showed little visible improvement.

## Files changed
- `app/deterministic_supervisory_checklist.py`
- `app/annotated_exporter.py`
- `app/academic_ai_engine.py`
- `.env.example`
- `README.md`
- `DEPLOYMENT.md`
- `CHANGELOG.md`
- `ENVIRONMENT_CHANGES_v1.9.9.1.md`

## Main fixes
1. Adds a hard Chapter One MPhil supervisory contract that flags obvious issues deterministically.
2. Stops section fallback comments from being placed on the title page.
3. Suppresses generic section comments such as “should be checked for its contribution…”.
4. Anchors document-level comments to the first academic chapter heading rather than institution/title-page text.
5. Keeps checklist comments specific and evidence-anchored.
