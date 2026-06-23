# Changelog

## 0.9.0

- Added Light Review alongside Standard and Advanced Review.
- Light Review uses GPT-5.4 mini only and skips the second-model verification stage.
- Added a dedicated light-review prompt focused on common research flaws, obvious inconsistencies, unsupported claims, citation or source-verification concerns, recurring writing problems, and basic alignment.
- Added safeguards against presenting warning signs as proof of fraud, plagiarism, fabrication, falsification, or other misconduct.
- Limited Light Review to two material issues per section and a configurable maximum of 12 findings.
- Prevented critical-severity findings in Light Review. Obvious core omissions may be marked major, while most findings remain moderate or minor.
- Added concise, context-aware guidance and short examples where helpful.
- Added a shorter Light Review report with a clear scope notice.
- Added three review-depth options to the student interface.
- Preserved Standard routing through GPT-5.4 mini and GPT-5.4, and Advanced routing through GPT-5.4 and GPT-5.5.
