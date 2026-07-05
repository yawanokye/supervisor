# Updated files in v1.9.6

## Core workflow

- `app/main.py`
  - replaces automatic pause/resume loops with queued automatic recovery
  - applies bounded exponential retry and fresh retry generations
  - preserves live progress messages during recovery
  - withholds output until native comments are confirmed

- `app/academic_ai_engine.py`
  - adds retry-generation checkpoint isolation
  - adds a final GPT-5.4 grounded comment rescue
  - retains deterministic factual, section, table and placement gates

- `app/external_assessment.py`
  - adds retry-generation checkpoint isolation for the three-examiner and adjudicator workflow

- `app/annotated_exporter.py`
  - retains native Microsoft Word comments only
  - updates the annotation export version

## Interface

- `app/static/app.js`
  - displays automatic queued recovery without asking the user to resume repeatedly

## Deployment and documentation

- `render.yaml`
- `README.md`
- `CHANGELOG.md`

## Tests

- Added automatic-recovery, fresh-checkpoint, grounded-rescue and native-comment regression tests.
- Full suite: 181 tests passed.
