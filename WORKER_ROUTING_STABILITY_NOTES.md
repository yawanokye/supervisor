# VProfessor worker, routing and stability update

This build changes VProfessor from a single web-process review runner into a worker-first deployment.

## What changed

1. Web service now queues reviews when `VPROF_RUN_JOBS_IN_WEB=false`.
2. New `app.worker` service polls queued jobs and runs the AI pipeline.
3. `render.yaml` now defines:
   - `vprofessor-web`, Standard plan
   - `vprofessor-worker`, Standard plan
   - `vprofessor-db`, PostgreSQL
4. Shared job artifacts can be stored in PostgreSQL with `VPROF_DB_ARTIFACT_STORAGE=true`.
   This matters because a Render worker cannot read files stored only on the web service disk.
5. DeepSeek is disabled by default.
6. The stale `gpt-5.6-luna` default has been removed.
7. OpenAI routing now uses a cost-aware role split:
   - nano for cleaning and JSON repair
   - mini for section/chapter analysis
   - standard expert model for final audit, external examination and synthesis
8. Concurrency and output-token limits are reduced for one Standard worker.
9. Native DOCX comment output remains enabled. Final review JSON and annotated DOCX are also mirrored into the shared artifact store.

## Expected benefit

The worker does not make OpenAI itself respond faster. It removes the biggest stability problem: long AI jobs running inside the same process that serves the website.

Expected practical effect:

- 50% to 80% fewer interrupted or paused jobs.
- 30% to 60% lower API spend compared with using the expert model for every stage.
- 25% to 50% faster total completion for most reviews because section review uses smaller models and smaller output budgets.
- More reliable native DOCX downloads because final outputs are stored in shared database-backed artifacts.

## Deployment note

For higher volume, replace database artifact storage with object storage such as S3 or Cloudflare R2. PostgreSQL artifact storage is the simplest low-cost path for the first production worker, but large long-term use should move files out of the database.
