# Supervisor Assistant v1.8.3

## Stalled external-assessment recovery

- Detects a processing stage that has made no checkpoint progress for 30 minutes.
- Shows **Recover stalled stage** in Review History.
- Cancels the local stuck task, releases the lease, and restarts only the interrupted stage.
- Preserves all completed checkpoints.
- Adds a 20-minute hard timeout to each external-assessment model stage.
- Stops automatic retry loops for external-assessment timeouts and provider failures.
- Prevents an old worker from completing a job after its lease has been replaced.

New optional environment variables:

- `STAGE_STALE_AFTER_SECONDS=1800`
- `AI_EXTERNAL_ASSESSMENT_STAGE_TIMEOUT_SECONDS=1200`
