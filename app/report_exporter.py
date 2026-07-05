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
        parts: List[str] = []
        section = _clean(
            item.get("section_reference")
            or ((item.get("section_path") or [""])[-1] if item.get("section_path") else "")
            or item.get("heading")
        )
        if section:
            parts.append(section)
        if item.get("source_kind") == "table_row" or item.get("table_number"):
            number = _clean(item.get("table_number"))
            title = _clean(item.get("table_title"))
            table_label = f"Table {number}" if number else "Table"
            if title:
                table_label += f": {title}"
            if item.get("table_row") is not None:
                table_label += f", row {item['table_row']}"
            parts.append(table_label)
        if item.get("page") is not None:
            parts.append(f'page {item["page"]}')
        if item.get("paragraph") is not None and not item.get("table_number"):
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
    section = _normalised(row.get("section_reference") or row.get("section") or "chapter-wide review")
    evidence = row.get("evidence") or []
    if evidence:
        best = evidence[0]
        if best.get("source_kind") == "table_row" or best.get("table_index"):
            anchor = f'table:{best.get("table_index", "")}:{best.get("table_row", "")}'
        else:
            anchor = f'{best.get("document_role", "current")}:{best.get("paragraph", "")}'
    else:
        anchor = f'missing:{_normalised(row.get("category", "other"))}'
    return section, anchor


def _group_findings(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: "OrderedDict[Tuple[str, str], Dict[str, Any]]" = OrderedDict()
    for row in sorted(rows, key=lambda x: (_severity_rank(x.get("severity", "minor")), _normalised(x.get("item", "")))):
        key = _finding_anchor(row)
        group = groups.setdefault(key, {
            "section": _clean(row.get("section_reference") or row.get("section") or "Chapter-wide review"),
            "reference_label": _clean(row.get("reference_label") or row.get("section_reference") or row.get("section")),
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
    """Combine split section parts without merging same-named sections across chapters."""
    groups: "OrderedDict[Tuple[int | None, str], Dict[str, Any]]" = OrderedDict()
    for row in review.get("academic_section_reviews") or []:
        heading = _clean(row.get("heading") or row.get("section_name") or "Untitled section")
        chapter_number = row.get("chapter_number")
        try:
            chapter_number = int(chapter_number) if chapter_number is not None else None
        except (TypeError, ValueError):
            chapter_number = None
        key = (chapter_number, _normalised(heading))
        if not key[1]:
            continue
        group = groups.setdefault(key, {
            "heading": heading,
            "chapter_number": chapter_number,
            "section_path": list(row.get("section_path") or []),
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


def _row_chapter_number(row: Dict[str, Any]) -> int | None:
    value = row.get("chapter_number")
    try:
        if value is not None:
            return int(value)
    except (TypeError, ValueError):
        pass
    for evidence in row.get("evidence") or []:
        try:
            if evidence.get("chapter_number") is not None:
                return int(evidence.get("chapter_number"))
        except (TypeError, ValueError):
            continue
    return None


def _rows_for_section(
    section_name: str,
    rows: Sequence[Dict[str, Any]],
    chapter_number: int | None = None,
) -> List[Dict[str, Any]]:
    target = _normalised(section_name)
    matched = []
    for row in rows:
        source = _normalised(row.get("section_reference") or row.get("section", ""))
        if source != target:
            continue
        if chapter_number is not None and _row_chapter_number(row) not in {None, chapter_number}:
            continue
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
    reference = _clean(group.get("reference_label") or group.get("section"))
    heading.add_run(f"Review point {index}").bold = True
    if reference:
        heading.add_run(f" — {reference}").bold = True
    heading.add_run(": ").bold = True
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


CHAPTER_NAMES = {
    1: "Chapter One",
    2: "Chapter Two",
    3: "Chapter Three",
    4: "Chapter Four",
    5: "Chapter Five",
    6: "Chapter Six",
}


def _set_repeat_table_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def _prevent_row_split(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    cant_split = OxmlElement("w:cantSplit")
    tr_pr.append(cant_split)


def _set_cell_width(cell, width: float) -> None:
    cell.width = Inches(width)
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_w = tc_pr.find(qn("w:tcW"))
    if tc_w is None:
        tc_w = OxmlElement("w:tcW")
        tc_pr.append(tc_w)
    tc_w.set(qn("w:w"), str(int(width * 1440)))
    tc_w.set(qn("w:type"), "dxa")


def _compact_sentence(value: Any, limit: int = 260) -> str:
    text = _clean(value)
    text = re.sub(r"\bExample\s*:\s*", "", text, flags=re.I)
    text = re.sub(r"\bIllustrative guidance\s*:\s*", "", text, flags=re.I)
    return _trim(text, limit)


def _compact_overall_assessment(review: Dict[str, Any]) -> str:
    summary = review.get("summary") or {}
    raw = _clean(
        review.get("overall_academic_assessment")
        or summary.get("readiness_meaning")
        or ""
    )
    if not raw:
        return "The document has been reviewed at the selected academic benchmark."
    sentences = re.split(r"(?<=[.!?])\s+", raw)
    selected: List[str] = []
    total = 0
    for sentence in sentences:
        sentence = _clean(sentence)
        if not sentence:
            continue
        if total + len(sentence) > 650 and selected:
            break
        selected.append(sentence)
        total += len(sentence)
        if len(selected) >= 4:
            break
    return " ".join(selected)


def _section_strengths(
    section_name: str,
    strengths: Sequence[Dict[str, Any]],
    assessments: Sequence[str],
    chapter_number: int | None = None,
) -> List[str]:
    target = _normalised(section_name)
    matched = []
    for strength in strengths:
        source = _normalised(strength.get("section", ""))
        strength_chapter = _row_chapter_number(strength)
        if source == target and (chapter_number is None or strength_chapter in {None, chapter_number}):
            observation = _compact_sentence(strength.get("observation", ""), 210)
            if observation:
                matched.append(observation)

    return _unique(matched, 2)


def _section_corrections(
    section_name: str,
    findings: Sequence[Dict[str, Any]],
    limit: int | None = None,
    chapter_number: int | None = None,
) -> List[str]:
    rows = _rows_for_section(section_name, findings, chapter_number)
    rows = [
        row for row in rows
        if row.get("status") not in {"meets_requirement", "not_applicable"}
    ]
    rows.sort(
        key=lambda row: (
            _severity_rank(row.get("severity", "minor")),
            0 if _is_source_verification(row) else 1,
            _normalised(row.get("item", "")),
        )
    )

    output: List[str] = []
    seen = set()
    for row in rows:
        action = _compact_sentence(
            row.get("required_action")
            or row.get("comment")
            or row.get("item"),
            260,
        )
        signature = _normalised(action)
        if not action or not signature or signature in seen:
            continue
        seen.add(signature)
        output.append(action)
        if limit is not None and len(output) >= limit:
            break
    return output


def _chapter_number_from_rows(
    section_name: str,
    findings: Sequence[Dict[str, Any]],
    default_chapter: int | None,
) -> int | None:
    for row in _rows_for_section(section_name, findings, default_chapter):
        for evidence in row.get("evidence") or []:
            value = evidence.get("chapter_number")
            try:
                return int(value)
            except (TypeError, ValueError):
                continue

    match = re.search(
        r"\bchapter\s+(one|two|three|four|five|six|\d+)\b",
        section_name,
        flags=re.I,
    )
    if match:
        token = match.group(1).lower()
        words = {
            "one": 1, "two": 2, "three": 3,
            "four": 4, "five": 5, "six": 6,
        }
        return words.get(token, int(token) if token.isdigit() else None)
    return default_chapter


def _summary_units(review: Dict[str, Any]) -> List[Dict[str, Any]]:
    summary = review.get("summary") or {}
    findings = review.get("academic_findings") or []
    strengths = review.get("academic_strengths") or []
    section_rows = [
        row for row in _ordered_section_reviews(review)
        if not row.get("synthetic")
    ]

    detected_chapters = summary.get("current_chapters_detected") or []
    multi_chapter = len(detected_chapters) > 1 or str(
        summary.get("review_scope", "")
    ).lower() in {
        "complete_thesis", "complete dissertation", "full_thesis",
        "thesis", "complete",
    }

    default_chapter = summary.get("selected_chapter") or summary.get("inferred_chapter")
    try:
        default_chapter = int(default_chapter) if default_chapter else None
    except (TypeError, ValueError):
        default_chapter = None

    raw_units: List[Dict[str, Any]] = []
    for section in section_rows:
        heading = section["heading"]
        chapter_number = section.get("chapter_number")
        if chapter_number is None:
            chapter_number = _chapter_number_from_rows(
                heading, findings, default_chapter
            )
        raw_units.append({
            "label": heading,
            "chapter_number": chapter_number,
            "strengths": _section_strengths(
                heading,
                strengths,
                section.get("assessments") or [],
                chapter_number,
            ),
            "corrections": _section_corrections(heading, findings, None, chapter_number),
            "warnings": _unique(section.get("coverage_warnings") or [], 1),
            "assessments": section.get("assessments") or [],
        })

    if not multi_chapter:
        return raw_units

    grouped: "OrderedDict[int | None, Dict[str, Any]]" = OrderedDict()
    for unit in raw_units:
        chapter_number = unit["chapter_number"]
        group = grouped.setdefault(chapter_number, {
            "label": CHAPTER_NAMES.get(
                chapter_number,
                f"Chapter {chapter_number}" if chapter_number else "Whole Thesis",
            ),
            "chapter_number": chapter_number,
            "strengths": [],
            "corrections": [],
            "warnings": [],
            "assessments": [],
        })
        group["strengths"].extend(unit["strengths"])
        group["corrections"].extend(unit["corrections"])
        group["warnings"].extend(unit["warnings"])
        group["assessments"].extend(unit["assessments"])

    output = []
    for group in grouped.values():
        group["strengths"] = _unique(group["strengths"], 3)
        group["corrections"] = _unique(group["corrections"], None)
        group["warnings"] = _unique(group["warnings"], 1)
        output.append(group)
    return output


def _add_cell_list(
    cell,
    values: Sequence[str],
    *,
    numbered: bool = False,
    empty_text: str = "",
    colour: str = INK,
    size: float = 8.9,
) -> None:
    cell.text = ""
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
    cleaned = _unique(values)
    if not cleaned:
        p = cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(0)
        run = p.add_run(empty_text)
        run.italic = True
        run.font.size = Pt(size)
        run.font.color.rgb = RGBColor.from_string(MUTED)
        return

    for index, value in enumerate(cleaned, start=1):
        p = cell.paragraphs[0] if index == 1 else cell.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.line_spacing = 1.0
        if numbered:
            lead = p.add_run(f"{index}. ")
            lead.bold = True
            lead.font.size = Pt(size)
            lead.font.color.rgb = RGBColor.from_string(BRAND)
        run = p.add_run(_compact_sentence(value, 280))
        run.font.size = Pt(size)
        run.font.color.rgb = RGBColor.from_string(colour)


def _add_compact_follow_up(
    doc: Document,
    title: str,
    rows: Sequence[Dict[str, Any]],
    limit: int = 4,
) -> bool:
    rows = _actionable(rows)
    if not rows:
        return False
    doc.add_heading(title, level=1)
    added = 0
    seen = set()
    for row in sorted(
        rows,
        key=lambda item: _severity_rank(item.get("severity", "moderate")),
    ):
        action = _compact_sentence(
            row.get("required_action") or row.get("comment"), 300
        )
        signature = _normalised(action)
        if not signature or signature in seen:
            continue
        seen.add(signature)
        p = doc.add_paragraph(style="List Bullet")
        p.paragraph_format.space_after = Pt(3)
        section_name = _clean(row.get("section", "Review"))
        p.add_run(section_name + ": ").bold = True
        p.add_run(action)
        added += 1
        if added >= limit:
            break
    return added > 0

def build_docx_report(review: Dict[str, Any]) -> bytes:
    """Create a concise human-supervisor summary report.

    Detailed passage-level comments, examples, evidence locations and source
    verification notes remain in the annotated document. This report presents
    only the overall judgement, strengths and the main corrections required for
    each chapter or section.
    """
    doc = Document()
    _set_document_styles(doc)

    section = doc.sections[0]
    section.top_margin = Inches(0.58)
    section.bottom_margin = Inches(0.58)
    section.left_margin = Inches(0.62)
    section.right_margin = Inches(0.62)

    summary = review.get("summary") or {}
    depth = str(summary.get("review_depth", "standard")).lower()

    title = doc.add_paragraph(style="Title")
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.add_run("SUPERVISOR’S SUMMARY REVIEW")

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.paragraph_format.space_after = Pt(8)
    run = subtitle.add_run(_clean(summary.get("filename", "Reviewed document")))
    run.bold = True
    run.font.size = Pt(10.5)
    run.font.color.rgb = RGBColor.from_string(MUTED)

    # Compact two-pair metadata table.
    details = doc.add_table(rows=0, cols=4)
    details.style = "Table Grid"
    details.autofit = False
    pairs = [
        (
            ("Document", summary.get("document_label", "")),
            ("Academic level", summary.get("academic_level", "")),
        ),
        (
            (
                "Review stage",
                "Revised submission"
                if summary.get("revised_mode")
                else "Initial submission",
            ),
            ("Review depth", str(summary.get("review_depth", "standard")).title()),
        ),
        (
            (
                "Sections reviewed",
                summary.get("academic_sections_reviewed", ""),
            ),
            ("Overall judgement", summary.get("readiness_label", "")),
        ),
    ]
    if summary.get("thesis_structure_label"):
        pairs.append(
            (
                (
                    "Thesis structure",
                    summary.get("thesis_structure_label", ""),
                ),
                (
                    "Fixed five chapters",
                    "Required"
                    if summary.get("fixed_five_chapter_required")
                    else "Not required",
                ),
            )
        )
    for left, right in pairs:
        cells = details.add_row().cells
        for cell, width in zip(cells, (1.2, 2.35, 1.35, 2.35)):
            _set_cell_width(cell, width)
        _set_cell_shading(cells[0], SOFT)
        _set_cell_text(cells[0], left[0], True, BRAND, 8.5)
        _set_cell_text(cells[1], left[1], False, INK, 8.5)
        _set_cell_shading(cells[2], SOFT)
        _set_cell_text(cells[2], right[0], True, BRAND, 8.5)
        _set_cell_text(cells[3], right[1], False, INK, 8.5)

    context_rows = _context_summary(review)
    if context_rows:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(3)
        p.add_run("Study context used: ").bold = True
        p.add_run(
            "; ".join(
                f"{label}: {_compact_sentence(value, 180)}"
                for label, value in context_rows
            )
        )

    doc.add_heading("1. Overall Supervisor Comment", level=1)
    doc.add_paragraph(_compact_overall_assessment(review))

    judgement = doc.add_table(rows=1, cols=1)
    judgement.style = "Table Grid"
    cell = judgement.cell(0, 0)
    fill = (
        PALE_AMBER
        if summary.get("critical_issues", 0) or summary.get("major_issues", 0)
        else PALE_GREEN
    )
    _set_cell_shading(cell, fill)
    counts = (
        f'{summary.get("critical_issues", 0)} critical, '
        f'{summary.get("major_issues", 0)} major and '
        f'{summary.get("moderate_issues", 0)} moderate correction(s)'
    )
    _set_cell_text(
        cell,
        f'{summary.get("readiness_label", "Review completed")}. '
        f"The main revision workload comprises {counts}.",
        True,
        INK,
        9.3,
    )

    doc.add_heading("2. Main Strengths", level=1)
    strengths = review.get("academic_strengths") or []
    strength_values = _unique(
        (
            f'{_clean(item.get("section", "Chapter"))}: '
            f'{_compact_sentence(item.get("observation", ""), 260)}'
            for item in strengths
        ),
        5,
    )
    if strength_values:
        for value in strength_values:
            p = doc.add_paragraph(style="List Bullet")
            p.paragraph_format.space_after = Pt(3)
            p.add_run(value)
    else:
        doc.add_paragraph(
            "The document contains the required chapter framework, but the "
            "substantive strengths should become clearer after the priority "
            "corrections have been addressed."
        )

    doc.add_heading("3. Strengths and Key Corrections by Chapter or Section", level=1)
    intro = doc.add_paragraph(
        "All material corrections identified by the review are summarised below in "
        "concise action form. Detailed explanations, examples and exact locations remain "
        "in the annotated document."
    )
    intro.paragraph_format.space_after = Pt(5)

    units = _summary_units(review)
    if not units:
        doc.add_paragraph(
            "No identifiable chapter or section summary was available."
        )
    else:
        table = doc.add_table(rows=1, cols=3)
        table.style = "Table Grid"
        table.autofit = False
        header = table.rows[0]
        _set_repeat_table_header(header)
        for cell, width in zip(header.cells, (1.65, 2.2, 3.85)):
            _set_cell_width(cell, width)
            _set_cell_shading(cell, BRAND)
        _set_cell_text(header.cells[0], "Chapter / Section", True, "FFFFFF", 9)
        _set_cell_text(header.cells[1], "Strengths", True, "FFFFFF", 9)
        _set_cell_text(header.cells[2], "Key corrections required", True, "FFFFFF", 9)

        for index, unit in enumerate(units):
            row = table.add_row()
            _prevent_row_split(row)
            for cell, width in zip(row.cells, (1.65, 2.2, 3.85)):
                _set_cell_width(cell, width)
            if index % 2:
                for cell in row.cells:
                    _set_cell_shading(cell, "F8FAFC")

            _set_cell_text(
                row.cells[0],
                unit["label"],
                True,
                BRAND,
                8.8,
            )
            _add_cell_list(
                row.cells[1],
                unit.get("strengths") or [],
                empty_text="No separate strength recorded.",
                size=8.5,
            )

            corrections = list(unit.get("corrections") or [])
            corrections.extend(
                f"Review note: {_compact_sentence(warning, 220)}"
                for warning in unit.get("warnings") or []
            )
            _add_cell_list(
                row.cells[2],
                corrections,
                numbered=True,
                empty_text=(
                    "No major correction identified at the selected benchmark."
                ),
                size=8.5,
            )

    next_number = 4
    if _add_compact_follow_up(
        doc,
        f"{next_number}. Cross-Chapter Alignment",
        review.get("alignment_results") or [],
        4,
    ):
        next_number += 1

    if _add_compact_follow_up(
        doc,
        f"{next_number}. Response to Earlier Supervisor Comments",
        review.get("revision_results") or [],
        4,
    ):
        next_number += 1

    doc.add_heading(f"{next_number}. Supervisor’s Recommendation", level=1)
    final_guidance = _compact_sentence(
        summary.get("readiness_meaning", ""),
        420,
    )
    if not final_guidance:
        final_guidance = (
            "Address the corrections summarised above and the detailed comments "
            "in the annotated document before resubmission."
        )
    doc.add_paragraph(final_guidance)

    priority_actions = review.get("priority_actions") or []
    immediate = []
    seen = set()
    for action in priority_actions:
        text = _compact_sentence(action.get("action", ""), 260)
        signature = _normalised(text)
        if not text or not signature or signature in seen:
            continue
        seen.add(signature)
        immediate.append(text)
        if len(immediate) >= 5:
            break

    if immediate:
        lead = doc.add_paragraph()
        lead.paragraph_format.space_after = Pt(2)
        lead.add_run("Immediate revision priorities:").bold = True
        for index, action in enumerate(immediate, start=1):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.24)
            p.paragraph_format.first_line_indent = Inches(-0.18)
            p.paragraph_format.space_after = Pt(2)
            p.add_run(f"{index}. ").bold = True
            p.add_run(action)

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer_run = footer.add_run("AI Professor | Supervisor summary review")
    footer_run.italic = True
    footer_run.font.size = Pt(7.5)
    footer_run.font.color.rgb = RGBColor.from_string(MUTED)

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()

