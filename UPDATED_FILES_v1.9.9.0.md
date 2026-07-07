# VProfessor v1.9.9.0 - Deterministic Supervisory Checklist

## Updated files

- `app/deterministic_supervisory_checklist.py` - new deterministic checklist engine based on the Thesis Self-Evaluation Checklist and dissertation/thesis guidelines.
- `app/academic_ai_engine.py` - injects checklist findings into the academic review pipeline before the factual and public-comment gates.
- `.env.example` - adds deterministic checklist environment controls.
- `tests/test_deterministic_supervisory_checklist_v1990.py` - regression tests for checklist scope and title-page anchoring.
- `README.md`, `DEPLOYMENT.md`, `CHANGELOG.md` - deployment and change notes.

## Purpose

This update makes VProfessor less dependent on model luck. It evaluates uploaded work against a deterministic supervisory checklist before final comments are exported. Missing, partial and manual-verification checklist items become evidence-anchored findings and must pass the same placement and public-comment quality gates as AI-generated issues.
