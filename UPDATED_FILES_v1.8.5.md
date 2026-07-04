# Supervisor Assistant v1.8.5

## Grounded supervisory comments and level-calibrated review

This release strengthens the supervisory review and annotated document. It does not change the v1.8.4 external-examination pipeline.

### Comment accuracy and relevance

- Every academic finding must cite valid evidence from the section or subsection being reviewed.
- Findings without usable source evidence are discarded.
- A compact independent comment-accuracy audit now runs for Light, Standard and Advanced reviews.
- The audit removes unsupported, generic, misplaced and repetitive comments, corrects severity and checks source locations.
- Audit output that cannot be matched to the correct section is discarded rather than attached elsewhere.
- Document-analysis, section-review and completed-review checkpoints are versioned so older comments and table metadata are not reused.
- Exact quotations are checked against the source. An inaccurate quotation is removed and its confidence is reduced.

### Sections and subsections

- Review prompts require the exact supplied section or subsection heading for every finding.
- Evidence records now carry the full section path and a canonical section reference.
- Findings are forced back to the actual source heading, preventing comments from drifting into another chapter or subsection.
- Supervisor reports name the relevant section or subsection in each review point and source location.

### Tables

- DOCX extraction retains the table number, title, caption, table index, row number and surrounding section path.
- A caption immediately before a table is linked to that physical table.
- Table-related findings must cite a relevant table row and name the supplied table number and title.
- The annotated document places a table comment after the correct table, even when the cited evidence is the caption.
- Supervisor reports identify the table number, title and row where available.

### Safer annotated document

- Only an exact source quotation is coloured red.
- When no exact quotation exists, the comment is placed after the correct paragraph instead of colouring an arbitrary sentence.
- Missing or underdeveloped-content comments are placed under the relevant heading.
- Comments include the section or subsection heading and the table reference where applicable.

### Academic level and review depth

- Academic level now determines the quality benchmark.
- Review depth controls concision, breadth and quality-control intensity only.
- Light and Standard reviews of Professional Doctorate and PhD work remain doctoral in standard.
- Advanced review of Bachelor’s and Master’s work does not impose doctoral originality requirements.
- Separate benchmarks are supplied for Bachelor’s, Non-Research Master’s, Research Master’s or MPhil, Professional Doctorate and PhD work.

### Updated files

- `app/academic_ai_engine.py`
- `app/ai_prompts.py`
- `app/document_parser.py`
- `app/annotated_exporter.py`
- `app/report_exporter.py`
- `app/static/app.js`
- `app/templates/index.html`
- `app/main.py`
- `tests/test_fast_review_workflow.py`
- `tests/test_provider_routing.py`
- `tests/test_grounded_annotations_v185.py`
- `CHANGELOG.md`

## Validation

- 129 automated tests passed.
- All five academic levels were tested at Light, Standard and Advanced review depth.
- Table-row and table-caption annotation routing were tested.
- Cross-section evidence drift was tested and rejected.
