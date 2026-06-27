from __future__ import annotations

import io
import re
from collections import OrderedDict, defaultdict
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

INK = "1F2937"
MUTED = "667085"
BRAND = "2F5597"
SOFT = "EEF3F8"
PALE_GREEN = "EAF4EC"
PALE_AMBER = "FFF4E5"
LINE = "D7DEE8"


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalised(value: Any) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", _clean(value).lower()).strip()


def _set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def _set_cell_text(cell, text: Any, bold: bool = False, colour: str = INK, size: float = 9.2) -> None:
    cell.text = ""
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    run = p.add_run(_clean(text))
    run.bold = bold
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor.from_string(colour)


def _set_document_styles(doc: Document) -> None:
    normal = doc.styles["Normal"]
    normal.font.name = "Aptos"
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = RGBColor.from_string(INK)
    normal.paragraph_format.space_after = Pt(5)
    normal.paragraph_format.line_spacing = 1.08

    for name, size, colour in (("Title", 18, BRAND), ("Heading 1", 14, BRAND), ("Heading 2", 11.5, INK), ("Heading 3", 10.5, INK)):
        if name not in doc.styles:
            continue
        style = doc.styles[name]
        style.font.name = "Aptos Display" if name in {"Title", "Heading 1"} else "Aptos"
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor.from_string(colour)
        style.paragraph_format.space_before = Pt(10 if name != "Title" else 0)
        style.paragraph_format.space_after = Pt(5)


def _location_text(evidence: Iterable[Dict[str, Any]]) -> str:
    values: List[str] = []
    for item in evidence:
        parts = []
        if item.get("page") is not None:
            parts.append(f'page {item["page"]}')
        if item.get("paragraph") is not None:
            parts.append(f'paragraph {item["paragraph"]}')
        if parts:
            values.append(", ".join(parts))
    return "; ".join(dict.fromkeys(values)) or "section-level guidance"


def _unique(values: Iterable[Any], limit: int | None = None) -> List[str]:
    output: List[str] = []
    seen = set()
    for value in values:
        text = _clean(value)
        key = _normalised(text)
        if not text or not key or key in seen:
            continue
        seen.add(key)
        output.append(text)
        if limit is not None and len(output) >= limit:
            break
    return output


def _trim(value: str, limit: int) -> str:
    value = _clean(value)
    if len(value) <= limit:
        return value
    cut = value[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:") + "…"


def _severity_rank(value: str) -> int:
    return {"critical": 0, "major": 1, "moderate": 2, "minor": 3}.get(str(value).lower(), 9)


def _finding_anchor(row: Dict[str, Any]) -> Tuple[str, str]:
    section = _normalised(row.get("section", "chapter-wide review"))
    evidence = row.get("evidence") or []
    if evidence:
        best = evidence[0]
        anchor = f'{best.get("document_role", "current")}:{best.get("paragraph", "")}'
    else:
        anchor = f'missing:{_normalised(row.get("category", "other"))}'
    return section, anchor


def _group_findings(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: "OrderedDict[Tuple[str, str], Dict[str, Any]]" = OrderedDict()
    for row in sorted(rows, key=lambda x: (_severity_rank(x.get("severity", "minor")), _normalised(x.get("item", "")))):
        key = _finding_anchor(row)
        group = groups.setdefault(key, {
            "section": _clean(row.get("section", "Chapter-wide review")),
            "severity": row.get("severity", "moderate"),
            "rows": [],
            "evidence": row.get("evidence") or [],
        })
        group["rows"].append(row)
        if _severity_rank(row.get("severity", "minor")) < _severity_rank(group["severity"]):
            group["severity"] = row.get("severity", "moderate")
        if not group["evidence"] and row.get("evidence"):
            group["evidence"] = row.get("evidence")
    return list(groups.values())


def _section_summaries(review: Dict[str, Any]) -> Dict[str, List[str]]:
    summaries: Dict[str, List[str]] = defaultdict(list)
    for row in review.get("academic_section_reviews") or []:
        heading = _clean(row.get("heading") or row.get("section_name"))
        assessment = _clean(row.get("section_assessment"))
        if not heading or not assessment:
            continue
        summaries[_normalised(heading)].append(assessment)
    return {key: _unique(values, 2) for key, values in summaries.items()}


def _matching_summary(section_name: str, summaries: Dict[str, List[str]]) -> str:
    target = _normalised(section_name)
    direct = summaries.get(target)
    if direct:
        return " ".join(direct)
    for key, values in summaries.items():
        if key in target or target in key:
            return " ".join(values)
    return ""


def _is_synthetic_review_section(name: str) -> bool:
    value = _normalised(name)
    return any(term in value for term in (
        "whole chapter coherence", "whole chapter consistency", "cross chapter coherence",
        "cross chapter alignment", "supervisor comment compliance audit",
    ))


def _ordered_section_reviews(review: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Combine split section parts while preserving document order."""
    groups: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
    for row in review.get("academic_section_reviews") or []:
        heading = _clean(row.get("heading") or row.get("section_name") or "Untitled section")
        key = _normalised(heading)
        if not key:
            continue
        group = groups.setdefault(key, {
            "heading": heading,
            "assessments": [],
            "scores": [],
            "coverage_warnings": [],
            "synthetic": _is_synthetic_review_section(heading),
        })
        assessment = _clean(row.get("section_assessment"))
        if assessment:
            group["assessments"].append(assessment)
        try:
            group["scores"].append(float(row.get("section_score")))
        except (TypeError, ValueError):
            pass
        warning = _clean(row.get("coverage_warning"))
        if warning:
            group["coverage_warnings"].append(warning)
    output = []
    for group in groups.values():
        scores = group.pop("scores")
        group["score"] = round(sum(scores) / len(scores), 1) if scores else None
        group["assessments"] = _unique(group["assessments"], 3)
        group["coverage_warnings"] = _unique(group["coverage_warnings"], 2)
        output.append(group)
    return output


def _rows_for_section(section_name: str, rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    target = _normalised(section_name)
    matched = []
    for row in rows:
        source = _normalised(row.get("section", ""))
        if source == target or (source and target and (source in target or target in source)):
            matched.append(row)
    return matched


def _add_location(doc: Document, evidence: Sequence[Dict[str, Any]]) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run(f"Location: {_location_text(evidence)}")
    run.italic = True
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor.from_string(MUTED)


def _add_numbered_guidance(doc: Document, label: str, values: Sequence[str]) -> None:
    values = _unique(values)
    if not values:
        return
    lead = doc.add_paragraph()
    lead.paragraph_format.space_before = Pt(3)
    lead.paragraph_format.space_after = Pt(2)
    lead.add_run(label).bold = True
    if len(values) == 1:
        lead.add_run(" " + values[0])
        return
    for index, value in enumerate(values, start=1):
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Inches(0.25)
        p.paragraph_format.first_line_indent = Inches(-0.18)
        p.paragraph_format.space_after = Pt(2)
        p.add_run(f"{index}. ").bold = True
        p.add_run(value)


def _add_review_point(doc: Document, group: Dict[str, Any], index: int) -> None:
    rows = group["rows"]
    titles = _unique((row.get("item") for row in rows), 3)
    heading = doc.add_paragraph()
    heading.paragraph_format.space_before = Pt(7)
    heading.paragraph_format.space_after = Pt(2)
    heading.add_run(f"Review point {index}: ").bold = True
    heading.add_run(_trim("; ".join(titles) if titles else "Academic revision required", 240)).bold = True

    _add_location(doc, group.get("evidence") or [])

    assessments = _unique((_trim(row.get("comment", ""), 520) for row in rows), 2)
    if assessments:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(3)
        p.add_run("Supervisor’s assessment: ").bold = True
        p.add_run(" ".join(assessments))

    actions = _unique((_trim(row.get("required_action", ""), 460) for row in rows), 4)
    _add_numbered_guidance(doc, "Required revision:", actions)

    examples = _unique((_trim(row.get("illustrative_guidance", ""), 360) for row in rows), 1)
    if examples:
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Inches(0.18)
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(5)
        run = p.add_run("Illustrative guidance: ")
        run.bold = True
        run.font.color.rgb = RGBColor.from_string(BRAND)
        example_run = p.add_run(examples[0])
        example_run.italic = True
        example_run.font.color.rgb = RGBColor.from_string(INK)


def _actionable(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [row for row in rows if row.get("status") not in {"meets_requirement", "not_applicable"}]


def _add_follow_up_section(doc: Document, title: str, rows: Sequence[Dict[str, Any]]) -> bool:
    rows = _actionable(rows)
    if not rows:
        return False
    doc.add_heading(title, level=1)
    for index, group in enumerate(_group_findings(rows), start=1):
        _add_review_point(doc, group, index)
    return True



def _context_summary(review: Dict[str, Any]) -> List[Tuple[str, str]]:
    context = review.get("study_context") or {}
    rows: List[Tuple[str, str]] = []
    title = _clean(context.get("title_or_opening_focus"))
    if title:
        rows.append(("Study focus recognised", _trim(title, 320)))
    for label, key in (
        ("Country", "confirmed_countries"),
        ("Study location", "confirmed_locations"),
        ("Sector or field", "confirmed_sectors"),
    ):
        values = _unique(context.get(key) or [], 6)
        if values:
            rows.append((label, ", ".join(values)))
    return rows


def _is_source_verification(row: Dict[str, Any]) -> bool:
    return bool(
        row.get("source_verification_required")
        or row.get("guidance_type") == "source_verification"
        or row.get("category") in {"citations_and_sources", "ethics_and_integrity"}
    )


def _add_source_verification_summary(doc: Document, rows: Sequence[Dict[str, Any]], section_number: int) -> bool:
    selected = [row for row in rows if _is_source_verification(row)]
    if not selected:
        return False
    doc.add_heading(f"{section_number}. Evidence and Source Verification", level=1)
    intro = doc.add_paragraph(
        "The following matters require verification against original, credible sources. They are not findings of misconduct."
    )
    intro.paragraph_format.space_after = Pt(5)
    seen = set()
    count = 0
    for row in selected:
        signature = (_normalised(row.get("section", "")), _normalised(row.get("required_action", ""))[:180])
        if signature in seen or not signature[1]:
            continue
        seen.add(signature)
        count += 1
        p = doc.add_paragraph(style="List Number")
        p.paragraph_format.space_after = Pt(3)
        p.add_run(f'{_clean(row.get("section", "Chapter"))}: ').bold = True
        p.add_run(_trim(row.get("required_action", ""), 520))
        if row.get("evidence"):
            loc = p.add_run(f' ({_location_text(row.get("evidence") or [])})')
            loc.italic = True
            loc.font.color.rgb = RGBColor.from_string(MUTED)
        if count >= 10:
            break
    return True

def build_docx_report(review: Dict[str, Any]) -> bytes:
    doc = Document()
    _set_document_styles(doc)
    section = doc.sections[0]
    section.top_margin = Inches(0.65)
    section.bottom_margin = Inches(0.65)
    section.left_margin = Inches(0.72)
    section.right_margin = Inches(0.72)

    summary = review.get("summary") or {}
    depth = str(summary.get("review_depth", "standard")).lower()
    light_review = depth == "light"

    title = doc.add_paragraph(style="Title")
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.add_run("SUPERVISOR’S ACADEMIC REVIEW REPORT")

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.paragraph_format.space_after = Pt(12)
    run = subtitle.add_run(_clean(summary.get("filename", "Reviewed document")))
    run.bold = True
    run.font.size = Pt(11)
    run.font.color.rgb = RGBColor.from_string(MUTED)

    details = doc.add_table(rows=0, cols=2)
    details.style = "Table Grid"
    details.autofit = True
    detail_rows = [
        ("Document", summary.get("document_label", "")),
        ("Review stage", "Revised submission" if summary.get("revised_mode") else "Initial submission"),
        ("Academic level", summary.get("academic_level", "")),
        ("Research approach", summary.get("research_approach", "")),
        ("Review depth", str(summary.get("review_depth", "standard")).title()),
        ("Review benchmark", summary.get("review_benchmark", "")),
        ("Sections and subsections reviewed", summary.get("academic_sections_reviewed", "")),
        ("Overall judgement", summary.get("readiness_label", "")),
    ]
    if summary.get("alignment_score") is not None:
        detail_rows.append(("Cross-chapter alignment", f'{summary.get("alignment_score")}%'))
    if summary.get("revision_score") is not None:
        detail_rows.append(("Response to earlier comments", f'{summary.get("revision_score")}%'))
    for label, value in detail_rows:
        cells = details.add_row().cells
        _set_cell_shading(cells[0], SOFT)
        _set_cell_text(cells[0], label, True, BRAND)
        _set_cell_text(cells[1], value)

    context_rows = _context_summary(review)
    if context_rows:
        context_heading = doc.add_paragraph()
        context_heading.paragraph_format.space_before = Pt(8)
        context_heading.paragraph_format.space_after = Pt(3)
        context_heading.add_run("Study context used for this review").bold = True
        context_table = doc.add_table(rows=0, cols=2)
        context_table.style = "Table Grid"
        for label, value in context_rows:
            cells = context_table.add_row().cells
            _set_cell_shading(cells[0], SOFT)
            _set_cell_text(cells[0], label, True, BRAND, 8.8)
            _set_cell_text(cells[1], value, False, INK, 8.8)

    doc.add_heading("1. Overall Supervisor Assessment", level=1)
    overall = _clean(review.get("overall_academic_assessment") or summary.get("readiness_meaning"))
    doc.add_paragraph(overall)

    judgement_table = doc.add_table(rows=1, cols=1)
    judgement_table.style = "Table Grid"
    judgement_cell = judgement_table.cell(0, 0)
    fill = PALE_AMBER if summary.get("critical_issues", 0) or summary.get("major_issues", 0) else PALE_GREEN
    _set_cell_shading(judgement_cell, fill)
    judgement_text = (
        f'{summary.get("readiness_label", "Academic review completed")}. '
        f'The review identified {summary.get("critical_issues", 0)} critical, '
        f'{summary.get("major_issues", 0)} major, {summary.get("moderate_issues", 0)} moderate '
        f'and {summary.get("minor_issues", 0)} minor matter(s) at the selected review benchmark.'
    )
    _set_cell_text(judgement_cell, judgement_text, True, INK, 10)

    strengths = review.get("academic_strengths") or []
    doc.add_heading("2. Strengths to Retain", level=1)
    if strengths:
        for strength in strengths[:6]:
            p = doc.add_paragraph(style="List Bullet")
            p.paragraph_format.space_after = Pt(3)
            section_name = _clean(strength.get("section", "Chapter"))
            p.add_run(section_name + ": ").bold = True
            p.add_run(_clean(strength.get("observation", "")))
    else:
        doc.add_paragraph("No distinct strength was recorded separately from the section assessments.")

    doc.add_heading("3. Priority Corrections Before Resubmission", level=1)
    priorities = review.get("priority_actions") or []
    seen = set()
    kept = []
    for action in priorities:
        signature = (_normalised(action.get("section", "")), _normalised(action.get("action", ""))[:180])
        if not signature[1] or signature in seen:
            continue
        seen.add(signature)
        kept.append(action)
        priority_limit = 8 if depth == "light" else (10 if depth == "standard" else 12)
        if len(kept) >= priority_limit:
            break
    if kept:
        for index, action in enumerate(kept, start=1):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.22)
            p.paragraph_format.first_line_indent = Inches(-0.18)
            p.paragraph_format.space_after = Pt(3)
            p.add_run(f"{index}. ").bold = True
            p.add_run(f'{_clean(action.get("section", "Chapter"))}: ').bold = True
            p.add_run(_clean(action.get("action", "")))
    else:
        doc.add_paragraph("No priority correction was identified.")

    findings = review.get("academic_findings") or []
    next_section = 4
    if _add_source_verification_summary(doc, findings, next_section):
        next_section += 1

    doc.add_heading(f"{next_section}. Section-by-Section and Subsection Review", level=1)
    next_section += 1
    reviewed_sections = _ordered_section_reviews(review)
    used_finding_ids = set()

    actual_sections = [row for row in reviewed_sections if not row.get("synthetic")]
    if not actual_sections:
        doc.add_paragraph("No identifiable section or subsection was available for review.")
    else:
        for section_row in actual_sections:
            section_name = section_row["heading"]
            doc.add_heading(section_name, level=2)
            assessments = section_row.get("assessments") or []
            if assessments:
                p = doc.add_paragraph(_trim(" ".join(assessments), 900))
                p.paragraph_format.space_after = Pt(4)
            all_rows = _rows_for_section(section_name, findings)
            for row in all_rows:
                if row.get("finding_id"):
                    used_finding_ids.add(row.get("finding_id"))
            rows = [row for row in all_rows if not _is_source_verification(row)]
            if rows:
                for index, group in enumerate(_group_findings(rows), start=1):
                    _add_review_point(doc, group, index)
            elif all_rows:
                p = doc.add_paragraph()
                p.paragraph_format.space_after = Pt(5)
                run = p.add_run("Source-verification matters for this section are summarised in the evidence and source-verification section above.")
                run.italic = True
                run.font.color.rgb = RGBColor.from_string(MUTED)
            else:
                p = doc.add_paragraph()
                p.paragraph_format.space_after = Pt(5)
                run = p.add_run("No material revision was identified in this section at the selected review benchmark.")
                run.italic = True
                run.font.color.rgb = RGBColor.from_string(MUTED)

            for warning in section_row.get("coverage_warnings") or []:
                p = doc.add_paragraph()
                p.paragraph_format.space_after = Pt(4)
                p.add_run("Review note: ").bold = True
                p.add_run(warning)

    unmatched = [
        row for row in findings
        if (not row.get("finding_id") or row.get("finding_id") not in used_finding_ids)
        and not _is_source_verification(row)
    ]
    if unmatched:
        doc.add_heading("Whole-Chapter and Additional Observations", level=2)
        for index, group in enumerate(_group_findings(unmatched), start=1):
            _add_review_point(doc, group, index)

    if _add_follow_up_section(doc, f"{next_section}. Cross-Chapter Alignment", review.get("alignment_results") or []):
        next_section += 1
    if _add_follow_up_section(doc, f"{next_section}. Response to Earlier Supervisor Comments", review.get("revision_results") or []):
        next_section += 1

    doc.add_heading(f"{next_section}. Final Guidance", level=1)
    final_guidance = _clean(summary.get("readiness_meaning", ""))
    if final_guidance:
        doc.add_paragraph(final_guidance)
    note = doc.add_paragraph()
    note.paragraph_format.space_before = Pt(4)
    note.add_run("Use of examples: ").bold = True
    note.add_run(
        "Examples are limited to the context stated in the submitted document. Where the document does not provide a necessary detail, the report uses a neutral placeholder. Replace placeholders only with verified information from the actual study."
    )
    scope_note = doc.add_paragraph()
    scope_note.paragraph_format.space_before = Pt(5)
    scope_note.add_run("Review benchmark: ").bold = True
    scope_note.add_run(
        f'This report reviews every detected section and subsection at the {summary.get("review_benchmark", "selected academic")} standard. '
        "The difference between Light, Standard and Advanced Review is the level of academic scrutiny, not the parts of the document covered. "
        "Research-integrity concerns are raised for verification and are not treated as proof of misconduct."
    )

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer_run = footer.add_run("")
    footer_run.italic = True
    footer_run.font.size = Pt(8)
    footer_run.font.color.rgb = RGBColor.from_string(MUTED)

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
