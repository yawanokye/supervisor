# Hybrid review pipeline

The three-phase proposal is suitable as a product direction. The input rates were checked against official OpenAI documentation on 16 October 2026. These are short-context rates per million tokens and exclude regional premiums.

| Processing | Ordinary input | Cached input | Cache writes | Output |
| --- | ---: | ---: | ---: | ---: |
| GPT-6 Luna standard | $0.10 | $0.01 | $0.125 | $0.50 |
| GPT-6.1 Sol standard | $2.00 | $0.10 | $2.50 | $10.00 |
| GPT-6.1 Sol Batch | $1.00 | $0.05 | $1.25 | $5.00 |

Batch completes within a 24-hour window. Use it for an explicitly selected economy or overnight review mode. A background Responses request is not a Batch request and does not receive the Batch discount.

The 95 percent cached-input discount applies only to eligible matching input. The same document in an earlier call does not guarantee reuse. Prompts must preserve a matching prefix and compatible settings while the cache remains available. Changing the model, instructions or output schema can prevent reuse. New input, output and cache writes have separate rates. Cache writes are charged instead of ordinary input for the tokens written, not as an additional charge on the same tokens. Prompts above 272,000 input tokens have higher GPT-6 Luna/Sol rates.

## Included now

- Local structure checks and configured model routing.
- An optional `vprofessor-gpt6-hybrid.env.example` for Luna mechanical roles and Sol academic roles through the existing live API pipeline.
- Correct GPT-6 Luna price estimates and supported reasoning efforts.
- GPT-6 Luna and GPT-6.1 Sol cost estimates that distinguish cache reads, cache writes, ordinary input and output, including the long-context multiplier.
- Existing caching hints, persistent checkpoints, recovery and clean revision export.

The example is optional and does not change the deployment's existing model settings. The displayed costs remain estimates. The code does not infer a cache hit or claim a Batch discount merely because a review is asynchronous.

## Batch and Flex added in 2.13.0

Economy now requests Flex for Sol processing, with an explicit standard-price fallback option. Overnight Batch now includes durable batch IDs and custom request IDs, collection of individual results, partial-failure handling, cancellation, recovery and an explicit workflow in the interface. Successive dependent review stages may require separate Batch jobs and do not promise a whole review within one 24-hour window. Verification and export are outside the batched core work. See `UPDATE_v2.13.0.md`.

Interactive follow-up still needs an authorised conversation interface grounded in the relevant manuscript passages and previous review, with stable prefixes where useful and recorded actual cache hits. This release does not add a follow-up chat.

## Official sources

- https://developers.openai.com/api/docs/pricing
- https://developers.openai.com/api/docs/models/gpt-6-luna
- https://developers.openai.com/api/docs/models/gpt-6.1-sol
- https://developers.openai.com/api/docs/guides/batch
- https://developers.openai.com/api/docs/guides/prompt-caching
