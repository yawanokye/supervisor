# v2.2.0, final exact-anchor and cost-efficient professional review

## Quality corrections

- Added revision-visible DOCX extraction so tracked insertions can be reviewed instead of silently disappearing from parsed text.
- Added direct detection of unresolved supervisor instructions, incomplete citation fragments, excessive historical background, unnamed single-firm settings and recurring sentence-level errors.
- Corrected chapter detection so an organisation-of-study sentence beginning with “Chapter two…” does not create a false second chapter.
- Strengthened evidence-grounded checks for local problem evidence, research gaps, construct consistency, purpose-objective-question alignment, causal claim strength and limitation-versus-delimitation.
- Added issue-specific completion verification for citations, statistics, language, scope, alignment, causal claims, gaps, constructs and contributions.
- Consolidated only genuine duplicate root causes. Different sentence anchors and different statistical defects remain separate.
- Grouped findings sharing the same exact sentence or paragraph into one numerically ordered native Word comment box.
- Shortened inline comments to the issue and immediate action while retaining full detail in native comments and the appended report.
- Ensured the native, inline and report outputs reuse one final numbered ledger.

## Cost corrections

- Replaced universal second-pass auditing with risk-selected paid auditing.
- Limited Standard chapter review to one compact paid accuracy-audit batch.
- Kept routine and final Standard synthesis on GPT-5.6 Terra.
- Reserved GPT-5.6 Sol for PhD final synthesis, external-examiner adjudication and selective Advanced escalation.
- Reduced routine output-token ceilings and increased safe section batching.
- Retained deterministic evidence, placement and public-language gates for findings that do not require a second paid model call.

## Stability

- Retained bounded truncation recovery without falsely disabling the OpenAI provider.
- Updated pipeline and checkpoint identifiers to prevent reuse of incomplete earlier-stage outputs.
- Added final release regression tests for tracked text, chapter detection, known Chapter One defects, canonical numbering, exact-anchor grouping, concise inline annotations and cost-aware routing.

# v2.1.1, provider recovery and audit stability hotfix

- Fixed the `submission_scope` interface mismatch that crashed deterministic expert checks.
- Prevented output truncation and schema errors from opening the provider circuit.
- Split comment-accuracy audits into token-safe batches.

# v2.1.0, evidence-grounded professional supervisory review

- Introduced the canonical evidence ledger, scope-aware review rules and exact source anchoring.
- Added positive grounding validation and ArticleReady-style action reporting.
