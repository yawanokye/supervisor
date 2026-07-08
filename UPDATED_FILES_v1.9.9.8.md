# Updated Files — v1.9.9.8 UCC Section-Level Coverage

This update strengthens the review engine so that all relevant University of Cape Coast thesis/dissertation sections are assessed at the academic level selected by the user.

## Updated files

- `app/academic_ai_engine.py`
- `app/comment_quality.py`
- `app/ucc_section_contract.py` (new)
- `.env.example`
- `tests/test_ucc_section_contract_v1998.py` (new)
- `CHANGELOG.md`
- `DEPLOYMENT.md`
- `ENVIRONMENT_CHANGES_v1.9.9.8.md`
- `UPDATED_FILES_v1.9.9.8.md`

## Main changes

- Adds a deterministic UCC section-coverage contract for Chapters One to Five.
- Preserves evidence-backed comments for distinct UCC sections after public de-duplication.
- Ensures deterministic UCC/checklist findings with internal metadata validate correctly before export.
- Derives selected chapter from parsed document content when the summary does not provide it.
- Raises the final exported comment floor using the selected academic level and relevant UCC section coverage.
