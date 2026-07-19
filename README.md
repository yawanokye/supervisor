# V-Professor Supervisory Review 2.0.0

V-Professor provides degree-calibrated supervisory review and external assessment for Bachelor’s, Non-Research Master’s, Research Master’s/MPhil, Professional Doctorate and PhD work.

## Professional supervisory workflow

- Supervisors may review a complete chapter or scan the uploaded file and select individual sections.
- Bachelor’s, Master’s and Professional Doctorate submissions normally use the five-chapter research structure.
- PhD submissions may use a justified custom chapter architecture, but all prescribed doctoral research elements must be present and integrated.
- Findings are anchored to the exact sentence, paragraph or table row requiring action.
- Findings on the same sentence share one numbered native Word comment box. Different sentences retain separate anchors.
- The inline annotated copy places the numbered supervisor comment immediately after the affected paragraph.
- The report states the actions required before supervisor approval or submission, including location, action, academic reason and verification method.
- Methods and results receive route-specific checks for internal statistical accuracy, reporting adequacy and analysis appropriateness. Definitive recalculation still requires the original dataset, syntax and software output.

## Deployment

The web service runs with `uvicorn app.main:app`. Long reviews are processed by the background worker with `python -m app.worker`. Both services must use the same PostgreSQL database and OpenAI API key. See `DEPLOYMENT.md` and `.env.example`.
