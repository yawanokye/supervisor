from __future__ import annotations

import io
from typing import Any, Dict

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt

def _set_cell_text(cell, text: str, bold: bool = False) -> None:
    cell.text = ""
    p = cell.paragraphs[0]
    run = p.add_run(str(text or ""))
    run.bold = bold
    run.font.size = Pt(9)

def build_docx_report(review: Dict[str, Any]) -> bytes:
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Inches(0.65)
    section.bottom_margin = Inches(0.65)
    section.left_margin = Inches(0.7)
    section.right_margin = Inches(0.7)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("PROJECTREADY AI SUPERVISOR REVIEW REPORT")
    run.bold = True
    run.font.size = Pt(16)

    summary = review["summary"]
    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.add_run(summary["filename"]).bold = True

    table = doc.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    summary_rows = [
        ("Academic level", summary["academic_level"]),
        ("Research approach", summary["research_approach"]),
        ("Review scope", summary["review_scope"].replace("_", " ").title()),
        ("Overall score", f'{summary["overall_score"]}%'),
        ("Readiness", summary["readiness_label"]),
        ("Critical requirements unresolved", summary["critical_failed"]),
    ]
    for label, value in summary_rows:
        cells = table.add_row().cells
        _set_cell_text(cells[0], label, True)
        _set_cell_text(cells[1], value)

    doc.add_heading("Overall Assessment", level=1)
    doc.add_paragraph(summary["readiness_meaning"])
    doc.add_paragraph("The separate annotated DOCX uses red text for passages requiring revision and green square-bracketed text for supervisor guidance.")

    doc.add_heading("Completed Official Checklist", level=1)
    checklist = doc.add_table(rows=1, cols=5)
    checklist.style = "Table Grid"
    headers = ["Code", "Official explanatory item", "Assessment", "Page(s)", "Paragraph(s)"]
    for index, label in enumerate(headers):
        _set_cell_text(checklist.rows[0].cells[index], label, True)
    status_short = {
        "meets_requirement": "YES",
        "partly_meets_requirement": "PARTLY",
        "does_not_meet_requirement": "NO",
        "manual_review_required": "MANUAL REVIEW",
        "not_applicable": "N/A",
    }
    for row in review.get("results", []):
        evidence = row.get("evidence") or []
        pages = sorted({str(item.get("page")) for item in evidence if item.get("page") is not None})
        paragraphs = sorted({str(item.get("paragraph")) for item in evidence if item.get("paragraph") is not None}, key=lambda value: int(value))
        cells = checklist.add_row().cells
        _set_cell_text(cells[0], row.get("code", ""), True)
        _set_cell_text(cells[1], row.get("item", ""))
        _set_cell_text(cells[2], status_short.get(row.get("status"), row.get("status_label", "")))
        _set_cell_text(cells[3], ", ".join(pages) if pages else "—")
        _set_cell_text(cells[4], ", ".join(paragraphs) if paragraphs else "—")

    doc.add_paragraph(
        "A YES assessment is supported by the evidence locations shown. PARTLY and MANUAL REVIEW items must be resolved before final submission."
    )

    doc.add_heading("Priority Revision Actions", level=1)
    for action in review.get("priority_actions", []):
        p = doc.add_paragraph(style="List Number")
        p.add_run(f'{action["code"]} [{action["severity"].upper()}] ').bold = True
        p.add_run(action["action"])

    doc.add_heading("Detailed Checklist Review", level=1)
    detailed_rows = review["results"]
    for row_index, row in enumerate(detailed_rows):
        p = doc.add_paragraph()
        p.add_run(f'{row["code"]}  {row["item"]}').bold = True

        meta = doc.add_paragraph()
        meta.add_run("Status: ").bold = True
        meta.add_run(row["status_label"])
        meta.add_run("    Severity: ").bold = True
        meta.add_run(row["severity"].title())
        meta.add_run("    Confidence: ").bold = True
        meta.add_run(str(row["confidence"]))

        doc.add_paragraph(row["comment"])

        action_p = doc.add_paragraph()
        action_p.add_run("Required action: ").bold = True
        action_p.add_run(row["required_action"])

        evidence = row.get("evidence") or []
        if evidence:
            e = evidence[0]
            loc = []
            if e.get("page") is not None:
                loc.append(f'Page {e["page"]}')
            if e.get("paragraph") is not None:
                loc.append(f'paragraph {e["paragraph"]}')
            if e.get("heading"):
                loc.insert(0, e["heading"])
            ep = doc.add_paragraph()
            ep.add_run("Best evidence: ").bold = True
            ep.add_run((", ".join(loc) + ". ") if loc else "")
            ep.add_run(e.get("text", ""))
        if row_index < len(detailed_rows) - 1:
            doc.add_paragraph("")

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.add_run("Generated by ProjectReady AI Supervisor Assistant").italic = True

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
