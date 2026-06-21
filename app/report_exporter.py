from __future__ import annotations

import io
from typing import Any, Dict, Iterable, List

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt


def _set_cell_text(cell, text: Any, bold: bool = False) -> None:
    cell.text = ""
    p = cell.paragraphs[0]
    run = p.add_run(str(text if text is not None else ""))
    run.bold = bold
    run.font.size = Pt(9)


def _location_text(evidence: Iterable[Dict[str, Any]]) -> str:
    values: List[str] = []
    for item in evidence:
        parts = []
        if item.get("source_filename"):
            parts.append(str(item["source_filename"]))
        if item.get("page") is not None:
            parts.append(f'page {item["page"]}')
        if item.get("paragraph") is not None:
            parts.append(f'paragraph {item["paragraph"]}')
        if parts:
            values.append(", ".join(parts))
    return "; ".join(dict.fromkeys(values)) or "—"


def _add_detailed_rows(doc: Document, rows: List[Dict[str, Any]]) -> None:
    for row_index, row in enumerate(rows):
        p = doc.add_paragraph()
        p.add_run(f'{row.get("code", "")}  {row.get("item", "")}').bold = True

        meta = doc.add_paragraph()
        meta.add_run("Status: ").bold = True
        meta.add_run(row.get("status_label", ""))
        meta.add_run("    Severity: ").bold = True
        meta.add_run(str(row.get("severity", "")).title())
        meta.add_run("    Confidence: ").bold = True
        meta.add_run(str(row.get("confidence", "")))

        if row.get("supervisor_comment_source"):
            source_p = doc.add_paragraph()
            source_p.add_run("Supervisor comment source: ").bold = True
            source_p.add_run(str(row["supervisor_comment_source"]))

        doc.add_paragraph(row.get("comment", ""))

        action_p = doc.add_paragraph()
        action_p.add_run("Required action: ").bold = True
        action_p.add_run(row.get("required_action", ""))

        evidence = row.get("evidence") or []
        if evidence:
            e = evidence[0]
            ep = doc.add_paragraph()
            ep.add_run("Best evidence: ").bold = True
            ep.add_run(_location_text([e]) + ". ")
            ep.add_run(e.get("text", ""))

        details = row.get("alignment_details") or {}
        unmatched = details.get("unmatched") or []
        if unmatched:
            detail_p = doc.add_paragraph()
            detail_p.add_run("Unmatched earlier items: ").bold = True
            detail_p.add_run(" | ".join(unmatched))

        revision_details = row.get("revision_details") or {}
        if revision_details:
            detail_p = doc.add_paragraph()
            detail_p.add_run("Revision comparison: ").bold = True
            fragments = [f'current match {revision_details.get("current_match_score", 0):.0%}']
            original_match = revision_details.get("original_match_score")
            if original_match is not None:
                fragments.append(f'original match {original_match:.0%}')
            similarity = revision_details.get("passage_similarity")
            if similarity is not None:
                fragments.append(f'passage similarity {similarity:.0%}')
            detail_p.add_run(", ".join(fragments))

        if row_index < len(rows) - 1:
            doc.add_paragraph("")


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
    previous_files = review.get("context_documents") or []
    previous_names = ", ".join(item.get("filename", "") for item in previous_files) or "Not required"
    alignment_value = summary.get("alignment_score")
    revision_value = summary.get("revision_score")
    comment_sources = ", ".join(summary.get("supervisor_comment_sources") or []) or "Not applicable"
    summary_rows = [
        ("Document reviewed", summary.get("document_label", "")),
        ("Review stage", "Revised submission" if summary.get("revised_mode") else "Initial submission"),
        ("Academic level", summary["academic_level"]),
        ("Research approach", summary["research_approach"]),
        ("Review scope", summary["review_scope"].replace("_", " ").title()),
        ("Previous chapter files", previous_names),
        ("Supervisor comment sources", comment_sources),
        ("Original chapter supplied", "Yes" if summary.get("original_document_supplied") else "No"),
        ("Checklist score", f'{summary.get("checklist_score", summary["overall_score"])}%'),
        ("Alignment score", f"{alignment_value}%" if alignment_value is not None else "Not applicable"),
        ("Supervisor-comment score", f"{revision_value}%" if revision_value is not None else "Not applicable"),
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
    doc.add_paragraph(
        "The annotated DOCX uses red text for passages requiring revision and green square-bracketed text for supervisor guidance."
    )

    revision_rows = review.get("revision_results") or []
    if revision_rows:
        doc.add_heading("Supervisor Comment Compliance", level=1)
        count_table = doc.add_table(rows=2, cols=4)
        count_table.style = "Table Grid"
        labels = ["Addressed", "Partly addressed", "Not addressed", "Manual confirmation"]
        values = [
            summary.get("revision_addressed", 0),
            summary.get("revision_partly_addressed", 0),
            summary.get("revision_not_addressed", 0),
            summary.get("revision_manual", 0),
        ]
        for index, label in enumerate(labels):
            _set_cell_text(count_table.rows[0].cells[index], label, True)
            _set_cell_text(count_table.rows[1].cells[index], values[index])

        revision_table = doc.add_table(rows=1, cols=5)
        revision_table.style = "Table Grid"
        for index, label in enumerate(["Code", "Supervisor comment", "Assessment", "Revision evidence", "Required action"]):
            _set_cell_text(revision_table.rows[0].cells[index], label, True)
        for row in revision_rows:
            cells = revision_table.add_row().cells
            _set_cell_text(cells[0], row.get("code", ""), True)
            _set_cell_text(cells[1], row.get("item", ""))
            _set_cell_text(cells[2], row.get("status_label", ""))
            _set_cell_text(cells[3], _location_text(row.get("evidence") or []))
            _set_cell_text(cells[4], row.get("required_action", ""))

    if previous_files:
        doc.add_heading("Previous Chapters Used for Alignment", level=1)
        context_table = doc.add_table(rows=1, cols=3)
        context_table.style = "Table Grid"
        for index, label in enumerate(["File", "Detected chapter(s)", "Paragraphs extracted"]):
            _set_cell_text(context_table.rows[0].cells[index], label, True)
        for item in previous_files:
            cells = context_table.add_row().cells
            _set_cell_text(cells[0], item.get("filename", ""))
            chapters = item.get("detected_chapters") or []
            _set_cell_text(cells[1], ", ".join(map(str, chapters)) if chapters else "Not reliably detected")
            _set_cell_text(cells[2], item.get("paragraphs_extracted", 0))

    original = review.get("original_document")
    if original:
        doc.add_heading("Original Version Used for Comparison", level=1)
        original_table = doc.add_table(rows=1, cols=3)
        original_table.style = "Table Grid"
        for index, label in enumerate(["File", "Detected chapter(s)", "Paragraphs extracted"]):
            _set_cell_text(original_table.rows[0].cells[index], label, True)
        cells = original_table.add_row().cells
        _set_cell_text(cells[0], original.get("filename", ""))
        chapters = original.get("detected_chapters") or []
        _set_cell_text(cells[1], ", ".join(map(str, chapters)) if chapters else "Not reliably detected")
        _set_cell_text(cells[2], original.get("paragraphs_extracted", 0))

    alignment_rows = review.get("alignment_results") or []
    if alignment_rows:
        doc.add_heading("Cross-Chapter Alignment Review", level=1)
        align_table = doc.add_table(rows=1, cols=5)
        align_table.style = "Table Grid"
        for index, label in enumerate(["Code", "Alignment requirement", "Assessment", "Evidence location", "Required action"]):
            _set_cell_text(align_table.rows[0].cells[index], label, True)
        for row in alignment_rows:
            cells = align_table.add_row().cells
            _set_cell_text(cells[0], row.get("code", ""), True)
            _set_cell_text(cells[1], row.get("item", ""))
            _set_cell_text(cells[2], row.get("status_label", ""))
            _set_cell_text(cells[3], _location_text(row.get("evidence") or []))
            _set_cell_text(cells[4], row.get("required_action", ""))

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
        paragraphs = sorted(
            {str(item.get("paragraph")) for item in evidence if item.get("paragraph") is not None},
            key=lambda value: int(value),
        )
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

    if revision_rows:
        doc.add_heading("Detailed Supervisor Comment Follow-up", level=1)
        _add_detailed_rows(doc, revision_rows)

    if alignment_rows:
        doc.add_heading("Detailed Alignment Findings", level=1)
        _add_detailed_rows(doc, alignment_rows)

    doc.add_heading("Detailed Checklist Review", level=1)
    _add_detailed_rows(doc, review.get("results", []))

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.add_run("Generated by ProjectReady AI Supervisor Assistant").italic = True

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
