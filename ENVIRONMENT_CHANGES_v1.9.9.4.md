# Environment Changes — v1.9.9.4

## Purpose
v1.9.9.4 prevents review jobs from remaining indefinitely in automatic recovery when a stage has stopped progressing.

## New/confirmed settings

```env
RECOVERY_STALLED_AFTER_SECONDS=600
CLIENT_AUTO_RECOVERY_SECONDS=600
MAX_AUTO_RESUMES=4
AUTO_RESUME_JOBS=true
```

## Meaning
- `RECOVERY_STALLED_AFTER_SECONDS`: server-side time before a queued recovery with no progress is treated as stalled.
- `CLIENT_AUTO_RECOVERY_SECONDS`: browser-side limit for automatic recovery before the page stops polling and asks the user to recover manually from Review History.
- `MAX_AUTO_RESUMES`: maximum automatic resume attempts before manual recovery is required.
- `AUTO_RESUME_JOBS`: keeps normal automatic recovery enabled, but no longer allows an infinite loop.

No database migration is required.
