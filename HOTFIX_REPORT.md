# V-Professor v2.1.1 Provider Recovery Hotfix

## Failure addressed

The worker log contained three connected failures:

1. `deterministic_expert_issues() got an unexpected keyword argument 'submission_scope'`
2. Final comment-audit output reached the configured output-token ceiling.
3. Repeated request-level failures opened the global provider circuit, after which valid OpenAI configuration was incorrectly reported as `No enabled AI provider is configured`.

## Root causes

- The academic engine passed `submission_scope` to the deterministic expert layer, but the function signature had not been upgraded.
- Standard review allowed up to 100 findings in one strict verification response while allocating only about 3,200 output tokens.
- A section containing more findings than the nominal batch limit was not split.
- The router treated truncation and schema-contract failures as provider outages.
- The same OpenAI provider and model, with a different reasoning effort, could be selected as its own fallback.
- The structured-output retry repeated the same output limit after truncation.

## Corrections in v2.1.1

- Added the stable `submission_scope` argument to `deterministic_expert_issues`.
- Added a token-aware audit capacity rule. A 3,200-token audit now carries no more than seven findings.
- Split large individual sections before audit batches are assembled.
- Preserved bounded multi-batch verification through `AI_FAST_AUDIT_MAX_BATCHES`.
- Added an adaptive one-time retry after output truncation. The retry expands the output allowance within `AI_MAX_OUTPUT_TOKENS` and asks for concise, non-repetitive JSON.
- Prevented truncation, invalid JSON and schema validation failures from opening the provider circuit.
- Limited circuit opening to transport, timeout, rate-limit and service failures.
- Replaced the misleading missing-provider message with a temporary-cooldown message when credentials are present.
- Prevented the same provider/model from serving as its own fallback.
- Changed checkpoint and pipeline identifiers so failed v2.1.0 audit checkpoints are not reused as valid v2.1.1 results.

## Production environment

Keep these values on the background worker:

```env
OPENAI_API_KEY=<real key>
VPROF_ENABLE_OPENAI=true
VPROF_ENABLE_DEEPSEEK=false
VPROF_COMBINED_APP_PIPELINE=true

AI_FAST_AUDIT_BATCH_ISSUE_LIMIT=8
AI_FAST_AUDIT_MAX_BATCHES=8
AI_STRUCTURED_OUTPUT_RETRIES=1
AI_MAX_RETRIES=1
AI_MAX_OUTPUT_TOKENS=12000
AI_STRICT_FAILURE=true
```

The code also enforces a token-safe cap if an older environment still has `AI_FAST_AUDIT_BATCH_ISSUE_LIMIT=100`.

## Validation

- 329 automated tests passed.
- The exact `submission_scope` crash has a regression test.
- Four consecutive truncation failures no longer open the OpenAI circuit.
- A 3,200-token audit is limited to seven findings.
- A truncated 3,200-token strict response receives one 6,400-token recovery attempt.
- Python compilation passed.
- Render YAML validation passed.
- JavaScript syntax validation passed.
- Duplicate environment-key checks passed.

## Deployment

Deploy the package as a complete replacement. Redeploy the web service and the background worker. Stop and resubmit the failed review, or allow automatic recovery after both services are running v2.1.1. A new submission is cleaner because v2.1.1 uses new checkpoint identifiers.
