# Updated files in v1.9.0

- `app/main.py`
  - Adds the authenticated, CSRF-protected stop endpoint.
  - Preserves checkpoints and payloads under a durable `stopped` state.
  - Cancels active tasks, releases leases and excludes stopped jobs from automatic recovery.
  - Exposes stop and resume URLs in job responses.
- `app/templates/portal.html`
  - Adds Stop Review for queued and processing jobs and Resume for stopped jobs.
- `app/templates/index.html`
  - Adds a live Stop Review button while a submission is processing.
- `app/static/app.js`
  - Sends stop requests, handles stopped status and returns the user to Review History.
- `app/static/styles.css`
  - Adds stopped-status and stop-button styling.
- `tests/test_user_stop_review.py`
  - Adds regression tests for the safe-stop workflow.
- `tests/test_checkpoint_resume_ui.py`
  - Extends manual-resume coverage to stopped jobs.
