# Updated files in v1.9.7

## Supervisor token allocation and page-capacity planning

- `app/token_budget.py`
  - Estimates DOCX pages from word count and reads exact PDF page counts.
  - Converts token allocations into expected supervisory and external-examination pages.
  - Reserves estimated tokens when a review is submitted.
  - Reconciles the reservation to actual provider input and output tokens when the review completes.
  - Maintains allocation, reservation, settlement and adjustment ledger entries.

- `app/database.py`
  - Adds available, reserved, allocated and used token totals to supervisor accounts.
  - Adds estimated pages and token-accounting fields to review records.
  - Adds the `token_ledger` audit table.
  - Includes safe additive migrations for existing SQLite and PostgreSQL deployments.

- `app/main.py`
  - Adds individual and bulk administrator allocation routes.
  - Allows allocation by raw tokens, standard supervisory pages or external-examination pages.
  - Checks available allocation before a metered supervisor starts a review.
  - Persists page estimates and reservations with each review.
  - Reconciles completed reviews to provider-reported token usage.
  - Reserves a fresh budget when a completed limited review is rebuilt.

- `app/templates/admin_dashboard.html`
  - Adds institutional token totals, expected page capacity and quota state.
  - Adds bulk allocation for active supervisors, all supervisors or one department.
  - Adds individual allocation controls for every supervisor.
  - Adds a recent token-activity audit table.

- `app/templates/portal.html` and `app/templates/index.html`
  - Show each supervisor's available allocation, reserved amount, used amount and expected page capacity.

- `app/static/styles.css`
  - Adds responsive styles for token summaries, allocation forms, tables and supervisor quota cards.

- `.env.example`, `render.yaml`, `DEPLOYMENT.md`
  - Document staged quota rollout and configurable page-planning rates.

- `tests/test_token_allocation_v197.py`
  - Tests page estimation, allocation, reservation, settlement, usage counting and dashboard controls.

## Deployment behaviour

`TOKEN_QUOTA_ENFORCEMENT=false` is the recommended first-deployment setting. Existing supervisors without an allocation remain unmetered. Once an administrator assigns tokens to an account, that account is metered. After all supervisors have allocations, set `TOKEN_QUOTA_ENFORCEMENT=true` to require sufficient tokens for every supervisor.
