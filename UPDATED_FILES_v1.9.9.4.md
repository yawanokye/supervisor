# Updated Files — v1.9.9.4

## Runtime
- `app/main.py`
- `app/static/app.js`
- `.env.example`

## Documentation
- `CHANGELOG.md`
- `DEPLOYMENT.md`
- `UPDATED_FILES_v1.9.9.4.md`
- `ENVIRONMENT_CHANGES_v1.9.9.4.md`

## Summary
This release fixes the recovery-loop problem where the review screen could remain too long at "Recovering the interrupted stage". It introduces a server-side stale-recovery normaliser and a browser-side recovery time limit. Once automatic recovery is no longer credible, the job stops polling, keeps the saved checkpoints and asks the user to use one manual Recover action from Review History or submit the document again.
