# v2.1.0, evidence-grounded professional supervisory review

## Added

- Canonical evidence ledger with exact source text, paragraph and sentence anchors.
- Positive grounding validation for examples, constructs, named entities and study context.
- Scope-aware review rules for complete theses, individual chapters and selected sections.
- Chapter One diagnostic checks for unresolved supervisor instructions, incomplete citations, problem evidence, construct drift, unit-of-analysis inconsistency, purpose-objective-question mismatch, causal overstatement, research-question grammar and limitation-versus-delimitation.
- A five-part native and inline comment structure: Issue, Problem identified, Action required, Why this matters and Verification.
- Ten-gate regression benchmark covering the weaknesses found in the supplied Chapter One review.

## Improved

- Native comments now group findings only when they share the same verified sentence or paragraph anchor.
- Inline comments, native comments and readiness reports rebuild from one canonical finding record.
- Comment similarity threshold increased to 0.92 so distinct corrections are not merged merely because they share general academic terms.
- Missing-reference-list findings are released only when the submitted scope is a complete work.
- Deterministic, evidence-locked findings bypass generic human-editor rewrites.
- Readiness reports now include exact text requiring attention and a clear completion-verification method.
- Statistical findings remain separate where they concern different defects in the same table or model.

## Removed

- False chapter-only reference-list assertions.
- Invented spelling examples and ungrounded previous-study terminology.
- Separate substantive rewriting of native, inline and report outputs.
- Legacy visible body markers and low-threshold section-level finding consolidation.
