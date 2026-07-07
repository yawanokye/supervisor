from __future__ import annotations

import io
import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import RGBColor
from docx.text.paragraph import Paragraph
from docx.text.run import Run

from .annotated_exporter import (
    ACTIONABLE_STATUSES,
    _best_span,
    _comment_body,
    _format_comment_group,
    _placeholder_finding_rows,
    _preferred_evidence,
    _run_element,
    _source_locator_map,
)
from .comment_quality import public_text, sanitise_finding_rows
from .document_parser import clean_text, normalised

INLINE_ANNOTATION_EXPORT_VERSION = "1.9.9.2-inline-blue-red"
REVISION_RED = "C00000"
COMMENT_BLUE = RGBColor(0x00, 0x70, 0xC0)


_PROHIBITED_PUBLIC_RE = re.compile(
    r"\b(?:manifest|document map|paragraph id|section packet|parser|fallback|recovery|focused recovery|model response|P\d{1,4})\b",
    flags=re.I,
)


def _insert_paragraph_after(paragraph: Paragraph) -> Paragraph:
    new_p = OxmlElement("w:p")
    paragraph._p.addnext(new_p)
    return Paragraph(new_p, paragraph._parent)


def _red_run_element(text: str, source_run: Optional[Run] = None):
    return _run_element(text, source_run=source_run, colour=REVISION_RED)


def _mark_span_red(paragraph: Paragraph, start: int, end: int) -> bool:
    if start < 0 or end <= start:
        return False
    runs = list(paragraph.runs)
    cursor = 0
    changed = False
    for run in runs:
        text = run.text or ""
        run_start, run_end = cursor, cursor + len(text)
        cursor = run_end
        if not text or run_end <= start or run_start >= end:
            continue
        local_start = max(0, start - run_start)
        local_end = min(len(text), end - run_start)
        before, marked, after = text[:local_start], text[local_start:local_end], text[local_end:]
        parent = run._r.getparent()
        index = parent.index(run._r)
        for value, red in ((before, False), (marked, True), (after, False)):
            if not value:
                continue
            element = _red_run_element(value, run) if red else _run_element(value, source_run=run)
            parent.insert(index, element)
            index += 1
        parent.remove(run._r)
        changed = True
    return changed


def _add_inline_comment(paragraph: Paragraph, comments: Sequence[str]) -> None:
    body = _format_comment_group(comments)
    body = public_text(body, limit=1200, reject_placeholders=True, reject_incomplete=True)
    if not body or _PROHIBITED_PUBLIC_RE.search(body):
        return
    note = _insert_paragraph_after(paragraph)
    lead = note.add_run("Supervisor comment: ")
    lead.bold = True
    lead.font.color.rgb = COMMENT_BLUE
    lead.font.italic = True
    run = note.add_run(body)
    run.font.color.rgb = COMMENT_BLUE
    run.font.italic = True
    try:
        note.paragraph_format.space_before = paragraph.paragraph_format.space_after
        note.paragraph_format.space_after = paragraph.paragraph_format.space_after
        note.paragraph_format.left_indent = paragraph.paragraph_format.left_indent
    except Exception:
        pass


def _clean_comment(value: str) -> str:
    text = public_text(value, limit=980, reject_placeholders=True, reject_incomplete=True)
    if not text or _PROHIBITED_PUBLIC_RE.search(text):
        return ""
    return text


def _row_comment(row: Dict[str, Any]) -> str:
    return _clean_comment(_comment_body(row))


def _rows_for_inline(review: Dict[str, Any], source_map: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
    supplied_rows = (
        list(review.get("academic_findings", []))
        + list(review.get("alignment_results", []))
        + list(review.get("revision_results", []))
    )
    return sanitise_finding_rows(supplied_rows + _placeholder_finding_rows(source_map, supplied_rows))


def build_inline_annotated_docx(
    source_bytes: bytes,
    review: Dict[str, Any],
    comment_author: Optional[str] = None,
) -> bytes:
    """Create a non-native annotated DOCX.

    Areas needing revision are coloured red in the document body. The supervisor's
    explanatory comment is inserted immediately after the affected paragraph in
    blue italic text. No Word comments.xml or native comment boxes are used, so
    users can compare this output with the native-comment version.
    """
    document = Document(io.BytesIO(source_bytes))
    source_map, _ = _source_locator_map(document)
    review_rows = _rows_for_inline(review, source_map)

    after_paragraph: Dict[int, List[str]] = defaultdict(list)
    for row in review_rows:
        if row.get("status") not in ACTIONABLE_STATUSES:
            continue
        if row.get("annotation_eligible") is False:
            continue
        comment = _row_comment(row)
        if not comment:
            continue
        evidence = [
            item for item in (row.get("evidence") or [])
            if item.get("document_role", "current") == "current"
        ]
        evidence = _preferred_evidence(row, evidence)
        if not evidence:
            continue
        best = evidence[0]
        try:
            paragraph_number = int(best.get("paragraph"))
        except (TypeError, ValueError):
            continue
        locator = source_map.get(paragraph_number)
        if not locator or locator.get("kind") not in {"paragraph", "table_caption"}:
            continue
        paragraph = locator.get("paragraph")
        if paragraph is None:
            continue
        quote = clean_text(row.get("problematic_quote", ""))
        text = paragraph.text or ""
        if quote and quote in text:
            start, end = text.find(quote), text.find(quote) + len(quote)
        else:
            terms = [row.get("issue_title", ""), row.get("item", ""), row.get("section", "")]
            start, end = _best_span(text, terms, quote)
        _mark_span_red(paragraph, start, end)
        after_paragraph[paragraph_number].append(comment)

    for paragraph_number in sorted(after_paragraph, reverse=True):
        locator = source_map.get(paragraph_number) or {}
        paragraph = locator.get("paragraph")
        if paragraph is not None:
            comments = list(dict.fromkeys(after_paragraph[paragraph_number]))
            _add_inline_comment(paragraph, comments)

    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def inline_annotation_count(source_bytes: bytes, review: Dict[str, Any]) -> int:
    document = Document(io.BytesIO(source_bytes))
    source_map, _ = _source_locator_map(document)
    count = 0
    for row in _rows_for_inline(review, source_map):
        if row.get("status") in ACTIONABLE_STATUSES and row.get("annotation_eligible") is not False and _row_comment(row):
            count += 1
    return count
