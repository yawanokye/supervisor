# Files updated in v1.8.1

## Application files

- `app/external_assessment.py`
  - Adds exact-ID instructions, safe feedback redaction and source-backed retry expansion.
  - Changes the external stage checkpoint pipeline identifier to v1.8.1.
- `app/external_assessment_guard.py`
  - Removes uncited raw evidence IDs from the prompt-facing compact manifest while retaining counts and presence status.
- `app/main.py`
  - Changes the completed External Assessment checkpoint identifier so v1.8.0 cached reports are invalidated.

## Tests and documentation

- `tests/test_external_assessment_grounding.py`
  - Adds regression tests for unsupported evidence-ID recovery.
- `CHANGELOG.md`
- `README.md`
- `DEPLOYMENT.md`
- `UPDATED_FILES_v1.8.1.md`

## Validation

- Python compilation completed successfully.
- Full automated test suite: 106 passed.
