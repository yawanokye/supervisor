# VProfessor background review update

## Recommended operation

Use Economy for ordinary supervisory reviews, Standard when waiting time matters most, and Batch for work that can wait overnight. Retain automatic progression for unattended processing. Select guided progression only when a supervisor wants to inspect every chapter before continuing.

Economy routes mechanical work to GPT-6 Luna and academic work to GPT-6.1 Sol using Flex where supported. Flex offers Batch-level token pricing with variable availability. The default, visible fallback selection permits a rejected capacity request to continue at standard pricing. Select the economy-only option to keep the discounted route; exhausted retries retain the job for manual recovery. A timeout or quota error does not trigger an automatic standard-price fallback.

Standard preserves the deployment's configured models. Batch submits independent core academic packets to OpenAI with the original evidence, grading instructions and structured response schema. Independent packets are grouped into JSONL, with stable custom IDs. Verification, consolidation and Word exports follow afterwards using the existing live routes. Batch discounts the batched requests, not the entire review bill. A new dependent Batch submission can add another 24-hour window.

Readiness is an approximate range, not a guaranteed deadline. Initial estimates use document size and review depth, with a Flex allowance; comparable recent jobs refine these estimates once there are enough samples. Progress and queue load update the range. Batch displays its known window separately when available. Guided estimates cover the current chapter, since human pauses cannot be predicted.

## Deployment

1. Deploy the complete `supervisor-main` directory, keeping the existing database and retained review artifacts.
2. Start the updated web service, then the worker, so the additive database migration runs once during the update. Existing jobs retain their previous guided/standard settings. New form submissions default to automatic/Economy.
3. Use a persistent shared PostgreSQL database and retained artifacts. The supplied Render configuration already enables database artifact storage and starts a separate worker. Keep `VPROF_RUN_JOBS_IN_WEB=false` and use `python -m app.worker` for that worker.
4. Keep `VPROF_WORKER_CONCURRENCY=2` or greater. The default Batch limit reserves capacity for other work. `VPROF_BATCH_WORKER_LIMIT=1` explicitly permits one active Batch job. A single-slot worker cannot provide reserved live capacity while it waits for Batch.
5. Keep the OpenAI API key on both services. Economy and Batch require model access on that account. No new Python dependencies are needed.

The browser may close only after the saved-upload response appears. Upload transmission itself needs the page to remain open. The worker continues independently afterwards, provided the hosting service remains running. Sign in and open Review history to find the result or progress link on any device. No email notification is configured by this update.

## Scholarly discovery

Enable Related works and suggested readings on the form. The default sources are Semantic Scholar, OpenAlex and Crossref. Europe PMC is an additional option for biomedical work. The system extracts the study title and declared keywords locally; when keywords are absent it derives search terms locally from the title and abstract. Optional form fields override these terms.

Only title/keyword queries go to the selected search endpoints. Each source receives at most two bounded searches, with one short retry on a rate limit. Search results are cached within the job and reused across chapters. No extra language-model call is needed for discovery; a small packet of metadata from up to six results guides the existing academic review.

Results include bibliographic details, DOI or source links, available open-access links, source provenance and the terms matched in each title. DOI/title matches against the upload identify works that appear already cited. Up to eight other matches form the suggested reading list. Ranking uses lexical title overlap, not a claim to have read or judged the whole paper. Search is not exhaustive and the system does not automatically penalise a thesis for omitting a suggested paper. Retracted records are excluded where the source supplies that status; missing metadata does not establish that a paper is unretracted.

Optional server environment variables are `OPENALEX_API_KEY`, `SEMANTIC_SCHOLAR_API_KEY`, and `SCHOLARLY_CONTACT_EMAIL` for Crossref's polite pool. Keep credentials server-side. API access, usage budgets and rate limits belong to the selected services. A missing key or unavailable service produces an explicit source status; the academic review can continue with other results.

## Recovering the reported Word export failure

The reproduced bug occurs when a missing structural section is included in the canonical findings but native-comment reconciliation tries to locate a quotation from that absent section. This update attaches the action to a labelled reviewer note instead. It does not place it on an unrelated thesis paragraph.

After deploying the update to both services, open Review history and select Recover for the affected job. Keep the saved upload and checkpoints. Do not submit a fresh review solely for this export problem. New assembled delivery checkpoints preserve the final review and usage across export retries, including the final chapter consolidation. The recovery test interrupts native export, resumes it and verifies that no academic review, audit or prose-polish call occurs.

The pasted error alone cannot establish the cause in the running deployment. The missing-section failure was reproduced locally and corrected. Other causes, including an unavailable saved source or a storage failure, still need their own diagnosis. Future failures save the exact export step, exception class and detail in `document-export-diagnostic`; the visible error includes the step and exception class. Server logs retain the traceback.

## Validation

See `VALIDATION.md` for the tested scope. API behaviour was mocked; account access and real processing duration were not tested through paid requests. The code is packaged for deployment and has not been deployed to a live service from this workspace.

Official implementation references:

- https://developers.openai.com/api/docs/guides/flex-processing
- https://developers.openai.com/api/docs/guides/batch
- https://developers.openai.com/api/reference/resources/batches/methods/create
- https://api.semanticscholar.org/api-docs/
- https://help.openalex.org/api/authentication/
- https://www.crossref.org/documentation/retrieve-metadata/rest-api/
- https://europepmc.org/RestfulWebService
