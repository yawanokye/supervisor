# V-Professor v2.1.0 Evidence-Grounded Review Upgrade

## Release objective

This release addresses the weaknesses that reduced the supplied Chapter One review to approximately 4.8/10. The redesign targets an 8/10 to 10/10 professional-review range by making evidence grounding, section coverage, exact anchoring and cross-output consistency release requirements rather than optional prompt instructions.

The score target is a quality objective, not a guarantee that every future disciplinary judgement will receive a particular human rating. The bundled tests prevent the known defects from returning and provide a ten-gate acceptance benchmark for the supplied failure pattern.

## 1. Evidence-first review architecture

Every released finding is converted into one canonical record containing:

- finding identifier and severity;
- chapter and section;
- exact source text;
- paragraph and sentence identifiers;
- precise start and end offsets;
- criterion assessed;
- problem identified;
- action required;
- academic consequence;
- verification test; and
- annotation eligibility.

A finding that cannot be grounded is rejected or retained only as a clearly labelled report-level structural action. The exporter no longer searches for a convenient location after a generic comment has already been written.

## 2. Scope-aware review

The engine distinguishes among:

- complete thesis or dissertation;
- complete chapter;
- selected sections;
- proposal; and
- external assessment.

A chapter-only upload is not criticised for omitting a consolidated reference list or another component that may legitimately appear elsewhere in the complete work. Structural claims are released only after the declared submission scope is considered.

## 3. Stronger Chapter One diagnosis

The deterministic and AI review contracts now check:

- embedded supervisor instructions or unresolved drafting notes;
- incomplete parenthetical citations;
- mixed or unstable construct terminology;
- one-firm versus multiple-firm scope drift;
- imported evidence that does not establish the stated context;
- unsupported claims that the literature is scanty;
- content in the purpose that is absent from objectives or questions;
- causal language that exceeds the declared design;
- grammatical defects in research questions;
- limitations that are actually delimitations; and
- language consistency using only forms found in the current document.

These checks complement, rather than replace, the model’s conceptual and disciplinary review.

## 4. One finding ledger, three consistent outputs

Native comments, inline annotations and the final readiness report are generated from the same canonical record. A later polishing stage may shorten presentation, but it cannot introduce new constructs, examples, methods, locations or substantive judgements.

Each detailed comment uses:

1. Issue
2. Problem identified
3. Action required
4. Why this matters
5. Verification

Illustrative guidance is added only when it is context-valid and clearly presented as an example.

## 5. Exact native comments

- Findings on the same exact sentence or paragraph use one numbered Word comment box.
- Findings on different sentences remain separate even when they occur in one section.
- The original student text is not altered by visible reference markers.
- Decimal values, p-values, temperatures, equations, citations, URLs and DOI strings are protected.
- Table findings may anchor to the caption, row or cell supported by the extracted evidence.

## 6. Direct ArticleReady-style action reporting

The readiness report now shows:

- priority;
- exact location and text requiring attention;
- problem identified;
- specific action required;
- academic reason; and
- how completion will be verified.

This gives the student and supervisor an implementable correction schedule rather than a list of broad observations.

## 7. Statistical and analytical review

The existing JournalReady/ArticleReady statistical review logic remains integrated. The engine checks internal consistency, reporting adequacy, method-specific diagnostics and whether the analysis is suitable for the stated objective and data structure. It clearly distinguishes document-based verification from definitive recalculation, which requires the original dataset, syntax and software output.

## 8. Degree and chapter structure

Bachelor’s, Non-Research Master’s, Research Master’s/MPhil and Professional Doctorate work normally follow the five-chapter structure. PhD work may use any defensible chapter arrangement. The doctoral review checks for the prescribed research functions and their integration rather than penalising variation in chapter count.

## 9. Quality benchmark

The regression suite contains a ten-gate benchmark based on the supplied weak review. Release fails if the app does not detect:

1. unresolved supervisor instruction;
2. incomplete citation;
3. missing contextual problem evidence;
4. unsupported literature-gap claim;
5. construct inconsistency;
6. unit-of-analysis inconsistency;
7. purpose-objective mismatch;
8. causal claim/design mismatch;
9. research-question grammar defect; and
10. limitation-versus-delimitation confusion.

The benchmark also rejects a false missing-reference-list finding for a chapter-only upload and rejects invented examples such as terms not present in the current work.

## 10. Deployment note

Deploy v2.1.0 as a complete replacement and redeploy both the web service and background worker. Both services must use the same PostgreSQL database and OpenAI API key. Submit old or interrupted reviews as new jobs because the document-analysis, evidence-ledger and final-review checkpoint identifiers changed.
