# V-Professor 2.3.2 DeepSeek Adaptive-Recovery Hotfix

## Failure addressed

DeepSeek successfully accepted the requests, but the three primary review packets ended with `finish_reason=length`. The previous recovery still reused packets that were too large, so every packet could reach the output ceiling again and the job stopped before producing a valid `AcademicReviewBatch`.

## Corrections implemented

1. **Compact DeepSeek primary schema**
   - The first pass now returns only the evidence, judgement and correction needed for the canonical finding ledger.
   - Longer academic consequences and explanatory material are added later through deterministic enrichment and bounded verification.

2. **Smaller provider-specific coverage units**
   - Three prose targets per unit.
   - Four table rows per unit.
   - One coverage unit per DeepSeek request.
   - Maximum request size of 9,000 characters.

3. **Controlled output size**
   - DeepSeek primary output is capped at 7,000 tokens.
   - The model is instructed to return no more than two highest-impact model-generated issues for each target.
   - Routine language, citation-format and structural checks remain deterministic and do not consume a second large model response.

4. **No repeated payment for the same truncated packet**
   - A primary academic packet that returns `finish_reason=length` is not resent at the same granularity with a larger output budget.
   - Bounded final audits retain one schema-recovery retry because those requests are already small.

5. **Adaptive single-target recovery**
   - A truncated unit is split into one-target requests.
   - Each recovered target is merged back into the original canonical section record.
   - The final coverage ledger therefore remains one record per original unit rather than exposing recovery fragments.

6. **Non-fatal isolated failure handling**
   - If one isolated target still cannot be recovered, the job preserves all successfully recovered findings and marks only the unresolved coverage for manual confirmation.
   - A truncation-only first pass no longer produces the old fatal “first chapter pass could not be converted” error.

7. **Checkpoint separation**
   - New 2.3.2 pipeline identifiers prevent truncated 2.3.1 provider results from being reused.

## Cost control

The change avoids paying twice for the same oversized primary response. DeepSeek receives more, smaller input packets, but each response is shorter and bounded. Recovery is invoked only for the exact target that failed. This is more predictable than raising the output allowance for every chapter packet.

## Validation completed

- 347 automated tests passed.
- Python compilation passed.
- JavaScript syntax validation passed.
- Render YAML validation passed.
- `.env.example` duplicate-key validation passed.
- Render environment duplicate-key validation passed.
- No local database, cache or compiled Python files are included in the ZIP.

## Deployment

Deploy the ZIP as a complete replacement to both the Render web service and background worker. Apply the supplied environment values to both services. After both services are live, submit the document as a new review job. Do not reuse the failed 2.3.1 job because it contains older packet and checkpoint identifiers.

The hotfix was validated with simulated provider truncation and automated tests. It was not tested live with the user's private DeepSeek API key.
