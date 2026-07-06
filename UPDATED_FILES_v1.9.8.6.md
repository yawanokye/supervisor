# Updated files in v1.9.8.6

## Runtime files

- `app/academic_ai_engine.py`
  - Applies the degree/depth floor after public deduplication, so MPhil Standard reviews retain sufficient material findings after quality filtering.

- `app/annotated_exporter.py`
  - Prevents duplicate placeholder comments.
  - Keeps native Word comments natural and removes remaining template-style wording.
  - Normalises awkward action phrasing before export.

- `app/supervisory_accuracy_guard.py`
  - Adds deterministic checks for sentence-level uncited empirical sample claims.
  - Adds deterministic checks for in-text/reference author-name mismatch.
  - Adds deterministic checks for environmental sustainability versus environmental performance construct ambiguity.

- `app/main.py`
- `app/ai_config.py`
  - Version metadata updated to v1.9.8.6.

## Documentation

- `README.md`
- `CHANGELOG.md`
- `DEPLOYMENT.md`
- `UPDATED_FILES_v1.9.8.6.md`
- `ENVIRONMENT_CHANGES_v1.9.8.6.md`

## Environment

No new environment variable is required when upgrading from v1.9.8.5. Use the supplied complete v1.9.8.6 environment file, which is the v1.9.8.5 production environment renamed for consistency.
