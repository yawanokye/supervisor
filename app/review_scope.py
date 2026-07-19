from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from .document_parser import CHAPTER_DISPLAY_NAMES, CHAPTER_EXPECTED_COMPONENTS, clean_text, normalised


def _norm(value: Any) -> str:
    return normalised(clean_text(value))


def _slug(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", _norm(value)).strip("-")
    return text[:72] or "section"


def _heading_level(row: Mapping[str, Any]) -> int:
    number = clean_text(row.get("section_number"))
    if number:
        # A chapter's Heading 1 style commonly represents a first-level
        # subsection such as 1.1. Reserve level 1 for the chapter title itself.
        return min(9, number.count(".") + 1)
    style = clean_text(row.get("style"))
    match = re.search(r"heading\s*(\d+)", style, flags=re.I)
    if match:
        return max(2, min(9, int(match.group(1)) + 1))
    text = clean_text(row.get("text"))
    if re.match(r"^\s*chapter\b", text, flags=re.I):
        return 1
    return 2


def _is_outline_heading(row: Mapping[str, Any]) -> bool:
    if not row.get("is_heading") or row.get("is_toc_entry"):
        return False
    text = clean_text(row.get("text"))
    if not text:
        return False
    if row.get("section_number") or row.get("chapter_marker_number"):
        return True
    style = clean_text(row.get("style")).lower()
    if "heading" in style or "title" in style:
        return True
    if re.match(r"^\s*chapter\b", text, flags=re.I):
        return True
    # Parser-level heading detection intentionally has high recall. The scope
    # selector needs higher precision so ordinary sentences beginning with
    # words such as “Background” are not offered as selectable sections.
    return (
        len(text.split()) <= 14
        and not text.endswith((".", ",", ";", ":", "?", "!"))
        and (text.isupper() or bool(re.match(r"^\d+(?:\.\d+)+\s+", text)))
    )


def parse_selected_sections(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        values = list(raw)
    else:
        text = clean_text(raw)
        if not text:
            return []
        try:
            parsed = json.loads(text)
            values = parsed if isinstance(parsed, list) else [parsed]
        except Exception:
            values = [value for value in re.split(r"[\n,;]+", text) if clean_text(value)]
    output: List[str] = []
    seen = set()
    for value in values:
        item = clean_text(value)
        key = _norm(item)
        if item and key and key not in seen:
            seen.add(key)
            output.append(item)
    return output


def expected_section_options(chapter_number: int) -> List[Dict[str, Any]]:
    components = CHAPTER_EXPECTED_COMPONENTS.get(int(chapter_number), [])
    return [
        {
            "section_key": f"expected:ch{chapter_number}:{_slug(label)}",
            "section_title": label[:1].upper() + label[1:],
            "chapter_number": int(chapter_number),
            "paragraph": None,
            "level": 2,
            "detected": False,
        }
        for label in components
    ]


def build_document_outline(paragraphs: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    chapters: Dict[int, Dict[str, Any]] = {}
    seen_sections = set()
    for row in paragraphs:
        try:
            chapter = int(row.get("chapter_number"))
        except (TypeError, ValueError):
            continue
        chapters.setdefault(
            chapter,
            {
                "chapter_number": chapter,
                "chapter_title": CHAPTER_DISPLAY_NAMES.get(chapter, f"Chapter {chapter}"),
                "sections": [],
                "paragraph_count": 0,
            },
        )
        chapters[chapter]["paragraph_count"] += 1
        if not _is_outline_heading(row):
            continue
        title = clean_text(row.get("text"))
        if not title:
            continue
        level = _heading_level(row)
        if re.match(r"^\s*chapter\b", title, flags=re.I) or row.get("chapter_marker_number"):
            if len(title.split()) > 1:
                chapters[chapter]["chapter_title"] = title
            continue
        paragraph = row.get("paragraph")
        key = f"ch{chapter}:p{paragraph or 0}:{_slug(title)}"
        signature = (chapter, _norm(title), paragraph)
        if signature in seen_sections:
            continue
        seen_sections.add(signature)
        chapters[chapter]["sections"].append(
            {
                "section_key": key,
                "section_title": title,
                "section_number": row.get("section_number"),
                "chapter_number": chapter,
                "paragraph": paragraph,
                "level": level,
                "detected": True,
            }
        )

    ordered = [chapters[number] for number in sorted(chapters)]
    for chapter in ordered:
        if not chapter["sections"]:
            chapter["sections"] = expected_section_options(chapter["chapter_number"])
            chapter["using_expected_fallback"] = True
        else:
            chapter["using_expected_fallback"] = False
    return {
        "chapters": ordered,
        "detected_chapter_numbers": [row["chapter_number"] for row in ordered],
    }


def _selection_match(option: Mapping[str, Any], selected: Sequence[str]) -> bool:
    selected_norm = {_norm(value) for value in selected}
    selected_raw = set(selected)
    return (
        clean_text(option.get("section_key")) in selected_raw
        or _norm(option.get("section_key")) in selected_norm
        or _norm(option.get("section_title")) in selected_norm
    )


def apply_selected_section_scope(
    paragraphs: Sequence[Dict[str, Any]],
    *,
    selected_chapter: int | None,
    section_scope_mode: str,
    selected_sections: Sequence[str],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    mode = clean_text(section_scope_mode or "whole_chapter").lower()
    if mode != "selected_sections":
        return list(paragraphs), {
            "mode": "whole_chapter",
            "selected_section_keys": [],
            "selected_section_titles": [],
            "selected_paragraph_numbers": [],
            "unselected_paragraph_count": 0,
        }
    if not selected_sections:
        raise ValueError("Select at least one section for the selected-sections review.")

    outline = build_document_outline(paragraphs)
    chapter_row = next(
        (row for row in outline["chapters"] if row["chapter_number"] == int(selected_chapter or 0)),
        None,
    )
    if not chapter_row:
        raise ValueError("The selected chapter could not be isolated for section-level review.")
    matched = [row for row in chapter_row["sections"] if _selection_match(row, selected_sections)]
    if not matched:
        requested = ", ".join(selected_sections[:6])
        raise ValueError(
            f"The requested section selection could not be matched to headings in the uploaded chapter: {requested}. "
            "Scan the document again and select from the detected headings."
        )
    if chapter_row.get("using_expected_fallback"):
        # Expected labels are UI guidance only. Without detected headings the
        # system cannot safely isolate the relevant text, so retain the whole
        # chapter and disclose that the selection is advisory.
        return list(paragraphs), {
            "mode": "selected_sections",
            "selection_precision": "chapter_fallback_no_detected_headings",
            "selected_section_keys": [row["section_key"] for row in matched],
            "selected_section_titles": [row["section_title"] for row in matched],
            "selected_paragraph_numbers": [int(row.get("paragraph")) for row in paragraphs if row.get("paragraph")],
            "unselected_paragraph_count": 0,
        }

    index_by_paragraph = {
        int(row.get("paragraph")): index
        for index, row in enumerate(paragraphs)
        if row.get("paragraph") is not None
    }
    selected_indexes = set()
    selected_titles = []
    selected_keys = []
    for option in matched:
        paragraph_no = option.get("paragraph")
        if paragraph_no is None or int(paragraph_no) not in index_by_paragraph:
            continue
        start_index = index_by_paragraph[int(paragraph_no)]
        start_level = int(option.get("level") or 2)
        selected_titles.append(clean_text(option.get("section_title")))
        selected_keys.append(clean_text(option.get("section_key")))
        for index in range(start_index, len(paragraphs)):
            row = paragraphs[index]
            try:
                row_chapter = int(row.get("chapter_number"))
            except (TypeError, ValueError):
                row_chapter = None
            if row_chapter != int(selected_chapter or 0):
                if index > start_index:
                    break
                continue
            if index > start_index and _is_outline_heading(row):
                level = _heading_level(row)
                if level <= start_level:
                    break
            selected_indexes.add(index)

    # Preserve the chapter heading and any parent headings needed to understand
    # the selected subsection. They are context anchors, not extra review scope.
    for index, row in enumerate(paragraphs):
        if row.get("chapter_number") != selected_chapter or not _is_outline_heading(row):
            continue
        if _heading_level(row) <= 1:
            selected_indexes.add(index)
    scoped: List[Dict[str, Any]] = []
    for index in sorted(selected_indexes):
        row = dict(paragraphs[index])
        row["selected_review_scope"] = True
        scoped.append(row)
    if not scoped:
        raise ValueError("No readable paragraph or table row was isolated for the selected sections.")
    selected_paragraphs = sorted(
        int(row.get("paragraph")) for row in scoped if row.get("paragraph") is not None
    )
    return scoped, {
        "mode": "selected_sections",
        "selection_precision": "detected_heading_boundaries",
        "selected_section_keys": selected_keys,
        "selected_section_titles": selected_titles,
        "selected_paragraph_numbers": selected_paragraphs,
        "unselected_paragraph_count": max(0, len(paragraphs) - len(scoped)),
    }


def _row_paragraph_numbers(row: Mapping[str, Any]) -> set[int]:
    numbers = set()
    for evidence in row.get("evidence") or []:
        try:
            value = evidence.get("paragraph")
            if value is None:
                value = evidence.get("paragraph_id")
            numbers.add(int(value))
        except (TypeError, ValueError):
            continue
    return numbers


def _matches_selected_title(row: Mapping[str, Any], titles: Sequence[str]) -> bool:
    haystack = _norm(" ".join(
        clean_text(row.get(key))
        for key in ("section", "section_reference", "issue_title", "item", "missing_section_label")
    ))
    return any(_norm(title) in haystack or haystack in _norm(title) for title in titles if _norm(title))


def apply_review_scope_filter(review: Dict[str, Any]) -> Dict[str, Any]:
    summary = review.get("summary") or {}
    scope = summary.get("selected_section_scope") or {}
    if scope.get("mode") != "selected_sections":
        return review
    paragraph_numbers = {int(value) for value in scope.get("selected_paragraph_numbers") or []}
    titles = list(scope.get("selected_section_titles") or [])

    def keep(row: Mapping[str, Any]) -> bool:
        evidence_numbers = _row_paragraph_numbers(row)
        if evidence_numbers:
            return bool(evidence_numbers & paragraph_numbers)
        return _matches_selected_title(row, titles)

    for key in ("academic_findings", "academic_strengths", "alignment_results", "revision_results"):
        rows = review.get(key)
        if isinstance(rows, list):
            review[key] = [row for row in rows if keep(row)]
    section_reviews = review.get("academic_section_reviews")
    if isinstance(section_reviews, list):
        review["academic_section_reviews"] = [
            row for row in section_reviews
            if _matches_selected_title(row, titles)
            or bool({int(v) for v in row.get("assessed_paragraph_ids") or [] if str(v).isdigit()} & paragraph_numbers)
        ]
    review["priority_actions"] = [
        {
            "section": row.get("section") or row.get("section_reference") or "Selected section",
            "issue": row.get("issue_title") or row.get("item") or "Revision required",
            "action": row.get("required_action") or row.get("comment") or row.get("assessment") or "Revise the marked passage.",
            "severity": row.get("severity") or "moderate",
        }
        for row in review.get("academic_findings") or []
        if row.get("status") not in {"meets_requirement", "not_applicable"}
    ][:20]
    # Derived packages may have been built before the scope filter. Remove
    # them so the report and annotated exports rebuild from the filtered
    # canonical findings rather than retaining out-of-scope comments.
    for key in (
        "professional_review",
        "articleready_quality_audit",
        "supervisory_report_spec",
        "canonical_finding_ledger",
        "supervisory_readiness",
    ):
        review.pop(key, None)
    findings = list(review.get("academic_findings") or [])
    summary["academic_findings_count"] = len(findings)
    summary["critical_issues"] = sum(1 for row in findings if str(row.get("severity") or "").lower() == "critical")
    summary["major_issues"] = sum(1 for row in findings if str(row.get("severity") or "").lower() == "major")
    summary["moderate_issues"] = sum(1 for row in findings if str(row.get("severity") or "").lower() == "moderate")
    summary["scope_filter_applied"] = True
    summary["selected_sections_reviewed"] = titles
    review["summary"] = summary
    return review
