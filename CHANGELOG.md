# V-Professor 2.3.0

## Review accuracy

- Added research-design routing for primary quantitative, primary qualitative, mixed-methods, secondary/econometric, experimental and systematic-review studies.
- Added submission-stage gating so Chapters One to Three do not receive results-reporting or moderation-results findings.
- Added whole-section contradiction checks before claiming that background logic, research gaps, professional significance, theory links, population frames, sampling justification, software or chapter organisation are missing.
- Reframed premature moderation-result comments as an objective-framework-method alignment issue.
- Removed questionnaire-study contamination from systematic-review checklists.
- Consolidated repeated purpose-alignment, conceptual-framework, regression-protocol, ethical-access and numerical-source findings using safe anchor or section scopes.
- Reordered native comments so the action required is retained before longer explanatory text.
- Preserved section and table labels in grouped native comments.
- Prevented section-only uploads from generating unsupported whole-chapter population conflicts.

## Provider choice

- Added `VPROF_PRIMARY_PROVIDER=openai|deepseek|auto`.
- Added `VPROF_FALLBACK_PROVIDER=none|openai|deepseek|auto`.
- Added `VPROF_PROVIDER_FAILOVER=true|false`.
- Added DeepSeek V4 Pro and V4 Flash defaults, thinking controls and model-specific cost accounting.
- Explicit provider selection overrides the combined OpenAI pipeline.

## Validation

- 342 automated tests passed from a clean test environment.
- Python compilation passed.
- Provider-selection, wrong-design, wrong-stage, false-positive, exact-anchor grouping and table-reference regression tests passed.
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
