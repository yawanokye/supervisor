# VProfessor v1.9.9.20 — GPT-5.6 model migration

## Model mapping

- Every active `gpt-5.4`, `gpt-5.4-mini`, and `gpt-5.4-nano` route now uses `gpt-5.6-terra`.
- Every active `gpt-5.5` route now uses `gpt-5.6-sol`.
- The web and worker environment templates use the official API model IDs.
- Model-aware cost accounting distinguishes GPT-5.6 Terra from GPT-5.6 Sol.

## Deployment

Update the same model variables on both the web service and background worker, then redeploy the worker before the web service.
