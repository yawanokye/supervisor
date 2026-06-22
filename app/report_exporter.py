from __future__ import annotations

import io
from collections import defaultdict
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
    return "; ".join(dict.fromkeys(values)) or "Section-level or missing-content issue"


def _category_label(value: str) -> str:
    return str(value or "other").replace("_", " ").title()


def _add_finding(doc: Document, row: Dict[str, Any]) -> None:
    heading = doc.add_paragraph()
    heading.add_run(row.get("item", "Academic finding")).bold = True

    meta = doc.add_paragraph()
    meta.add_run("Section: ").bold = True
    meta.add_run(row.get("section", ""))
    meta.add_run("    Area: ").bold = True
    meta.add_run(_category_label(row.get("category", "")))
    meta.add_run("    Priority: ").bold = True
    meta.add_run(str(row.get("severity", "")).title())

    assessment = doc.add_paragraph()
    assessment.add_run("Academic assessment: ").bold = True
    assessment.add_run(row.get("comment", ""))

    action = doc.add_paragraph()
    action.add_run("Required revision: ").bold = True
    action.add_run(row.get("required_action", ""))

    evidence = row.get("evidence") or []
    if evidence:
        best = evidence[0]
        ep = doc.add_paragraph()
        ep.add_run("Location and evidence: ").bold = True
        ep.add_run(_location_text([best]) + ". ")
        ep.add_run(best.get("text", ""))
    else:
        ep = doc.add_paragraph()
        ep.add_run("Location: ").bold = True
        ep.add_run(row.get("section", "Section-level review"))


def _add_finding_table(doc: Document, rows: List[Dict[str, Any]], title: str) -> None:
    if not rows:
        return
    doc.add_heading(title, level=1)
    table = doc.add_table(rows=1, cols=5)
    table.style = "Table Grid"
    headers = ["Section", "Academic issue", "Priority", "Evidence location", "Required revision"]
    for index, value in enumerate(headers):
        _set_cell_text(table.rows[0].cells[index], value, True)
    for row in rows:
        cells = table.add_row().cells
        _set_cell_text(cells[0], row.get("section", ""))
        _set_cell_text(cells[1], row.get("item", ""), True)
        _set_cell_text(cells[2], str(row.get("severity", "")).title())
        _set_cell_text(cells[3], _location_text(row.get("evidence") or []))
        _set_cell_text(cells[4], row.get("required_action", ""))


def build_docx_report(review: Dict[str, Any]) -> bytes:
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Inches(0.65)
    section.bottom_margin = Inches(0.65)
    section.left_margin = Inches(0.7)
    section.right_margin = Inches(0.7)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("PROJECTREADY AI COMPLETE ACADEMIC REVIEW")
    run.bold = True
    run.font.size = Pt(16)

    summary = review["summary"]
    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.add_run(summary.get("filename", "Reviewed document")).bold = True

    previous_files = review.get("context_documents") or []
    previous_names = ", ".join(item.get("filename", "") for item in previous_files) or "Not required"
    alignment_value = summary.get("alignment_score")
    revision_value = summary.get("revision_score")
    comment_sources = ", ".join(summary.get("supervisor_comment_sources") or []) or "Not applicable"

    table = doc.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    summary_rows = [
        ("Document reviewed", summary.get("document_label", "")),
        ("Review stage", "Revised submission" if summary.get("revised_mode") else "Initial submission"),
        ("Academic level", summary.get("academic_level", "")),
        ("Research approach", summary.get("research_approach", "")),
        ("Previous chapter files", previous_names),
        ("Supervisor comment sources", comment_sources),
        ("Complete academic review score", f'{summary.get("academic_review_score", summary.get("overall_score", 0))}%'),
        ("Cross-chapter alignment score", f"{alignment_value}%" if alignment_value is not None else "Not applicable"),
        ("Supervisor-comment compliance", f"{revision_value}%" if revision_value is not None else "Not applicable"),
        ("Combined readiness score", f'{summary.get("overall_score", 0)}%'),
        ("Academic judgement", summary.get("readiness_label", "")),
        ("Sections reviewed", summary.get("academic_sections_reviewed", 0)),
    ]
    for label, value in summary_rows:
        cells = table.add_row().cells
        _set_cell_text(cells[0], label, True)
        _set_cell_text(cells[1], value)

    doc.add_heading("Overall Academic Assessment", level=1)
    doc.add_paragraph(review.get("overall_academic_assessment") or summary.get("readiness_meaning", ""))
    doc.add_paragraph(summary.get("readiness_meaning", ""))
    doc.add_paragraph(
        "The annotated Word copy identifies passages requiring revision in red and places the supervisor guidance immediately after them in green square brackets."
    )

    counts = doc.add_table(rows=2, cols=5)
    counts.style = "Table Grid"
    labels = ["Critical", "Major", "Moderate", "Minor", "Strengths"]
    values = [
        summary.get("critical_issues", 0),
        summary.get("major_issues", 0),
        summary.get("moderate_issues", 0),
        summary.get("minor_issues", 0),
        summary.get("strengths_identified", 0),
    ]
    for index, label in enumerate(labels):
        _set_cell_text(counts.rows[0].cells[index], label, True)
        _set_cell_text(counts.rows[1].cells[index], values[index])

    strengths = review.get("academic_strengths") or []
    if strengths:
        doc.add_heading("Academic Strengths", level=1)
        for strength in strengths:
            p = doc.add_paragraph(style="List Bullet")
            p.add_run(f'{strength.get("section", "Chapter")}: ').bold = True
            p.add_run(strength.get("observation", ""))
            if strength.get("evidence"):
                p.add_run(f' ({_location_text(strength["evidence"][:1])})')

    doc.add_heading("Priority Revision Plan", level=1)
    priorities = review.get("priority_actions") or []
    if priorities:
        for action in priorities:
            p = doc.add_paragraph(style="List Number")
            p.add_run(f'{str(action.get("severity", "")).upper()} · {action.get("section", "Chapter")}: ').bold = True
            if action.get("issue"):
                p.add_run(action.get("issue", "") + ". ")
            p.add_run(action.get("action", ""))
    else:
        doc.add_paragraph("No priority revision action was identified.")

    findings = review.get("academic_findings") or []
    critical_major = [row for row in findings if row.get("severity") in {"critical", "major"}]
    moderate_minor = [row for row in findings if row.get("severity") in {"moderate", "minor"}]
    _add_finding_table(doc, critical_major, "Critical and Major Academic Findings")
    _add_finding_table(doc, moderate_minor, "Moderate and Minor Academic Findings")

    revision_rows = review.get("revision_results") or []
    if revision_rows:
        doc.add_heading("Supervisor Comment Follow-up", level=1)
        table = doc.add_table(rows=1, cols=4)
        table.style = "Table Grid"
        for index, label in enumerate(["Earlier supervisor comment", "Assessment", "Revision evidence", "Required follow-up"]):
            _set_cell_text(table.rows[0].cells[index], label, True)
        for row in revision_rows:
            cells = table.add_row().cells
            _set_cell_text(cells[0], row.get("item", ""))
            _set_cell_text(cells[1], row.get("status_label", ""))
            _set_cell_text(cells[2], _location_text(row.get("evidence") or []))
            _set_cell_text(cells[3], row.get("required_action", ""))

    alignment_rows = review.get("alignment_results") or []
    if alignment_rows:
        doc.add_heading("Cross-Chapter Alignment Follow-up", level=1)
        table = doc.add_table(rows=1, cols=4)
        table.style = "Table Grid"
        for index, label in enumerate(["Alignment area", "Assessment", "Evidence location", "Required revision"]):
            _set_cell_text(table.rows[0].cells[index], label, True)
        for row in alignment_rows:
            cells = table.add_row().cells
            _set_cell_text(cells[0], row.get("item", ""))
            _set_cell_text(cells[1], row.get("status_label", ""))
            _set_cell_text(cells[2], _location_text(row.get("evidence") or []))
            _set_cell_text(cells[3], row.get("required_action", ""))

    doc.add_heading("Detailed Academic Review", level=1)
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in findings:
        grouped[row.get("section", "Chapter-wide review")].append(row)
    for section_name, rows in grouped.items():
        doc.add_heading(section_name, level=2)
        for row in rows:
            _add_finding(doc, row)
            doc.add_paragraph("")

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.add_run("Generated by ProjectReady AI Supervisor Assistant").italic = True

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
