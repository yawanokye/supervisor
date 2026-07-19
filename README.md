# V-Professor Supervisory Review 2.1.1

V-Professor provides degree-calibrated supervisory review and external assessment for Bachelor’s, Non-Research Master’s, Research Master’s/MPhil, Professional Doctorate and PhD work.

## Professional supervisory workflow

- Supervisors may review a complete chapter or scan the uploaded file and select individual sections.
- Bachelor’s, Master’s and Professional Doctorate submissions normally use the five-chapter research structure.
- PhD submissions may use a justified custom chapter architecture, but all prescribed doctoral research elements must be present and integrated.
- Every material finding must pass an evidence-grounding gate before release.
- Findings are anchored to the exact sentence, paragraph, table caption, row or cell requiring action.
- Findings on the same exact sentence or paragraph share one numbered native Word comment box. Different anchors retain separate comments.
- Native comments and inline comments use the same canonical finding ledger and state the issue, problem identified, action required, academic reason and verification test.
- The inline annotated copy places the supervisor action immediately after the affected paragraph without changing the original text.
- The report presents direct actions required before supervisor approval or submission, including the exact text, action, academic reason and completion test.
- Methods and results receive route-specific checks for internal statistical accuracy, reporting adequacy and analysis appropriateness. Definitive recalculation still requires the original dataset, syntax and software output.

## Quality safeguards introduced in 2.1.0 and stabilised in 2.1.1

- chapter-only uploads are not falsely treated as complete theses;
- examples quoted in comments must be present in the current work or clearly marked as illustrative guidance;
- previous-study terminology is rejected unless grounded in the current document;
- unresolved supervisor instructions and incomplete citations are detected;
- Chapter One checks cover problem evidence, construct consistency, unit of analysis, purpose-objective-question alignment, causal language, grammar and limitation-versus-delimitation;
- decimals, p-values, temperatures, equations, citations, URLs and DOI strings are protected during annotation;
- later editing stages cannot replace evidence-locked findings with generic comments.

## Deployment

The web service runs with `uvicorn app.main:app`. Long reviews are processed by the background worker with `python -m app.worker`. Both services must use the same PostgreSQL database and OpenAI API key. See `DEPLOYMENT.md` and `.env.example`.
