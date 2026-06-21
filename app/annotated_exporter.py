from __future__ import annotations

import io
import re
from collections import defaultdict
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional, Tuple

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

from .document_parser import clean_text, normalised
from .review_rules import STATUS_MANUAL, STATUS_MISSING, STATUS_PARTIAL

REVIEW_RED = "C00000"
COMMENT_GREEN = "008000"
ACTIONABLE_STATUSES = {STATUS_PARTIAL, STATUS_MISSING, STATUS_MANUAL}
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


def _set_run_colour(run_element, colour: str) -> None:
    rpr = run_element.find(qn("w:rPr"))
    if rpr is None:
        rpr = OxmlElement("w:rPr")
        run_element.insert(0, rpr)
    colour_node = rpr.find(qn("w:color"))
    if colour_node is None:
        colour_node = OxmlElement("w:color")
        rpr.append(colour_node)
    colour_node.set(qn("w:val"), colour)


def _set_italic(run_element) -> None:
    rpr = run_element.find(qn("w:rPr"))
    if rpr is None:
        rpr = OxmlElement("w:rPr")
        run_element.insert(0, rpr)
    if rpr.find(qn("w:i")) is None:
        rpr.append(OxmlElement("w:i"))


def _run_element(text: str, source_run=None, colour: Optional[str] = None, italic: bool = False):
    element = OxmlElement("w:r")
    if source_run is not None and source_run._r.rPr is not None:
        element.append(deepcopy(source_run._r.rPr))
    if colour:
        _set_run_colour(element, colour)
    if italic:
        _set_italic(element)
    node = OxmlElement("w:t")
    if text.startswith(" ") or text.endswith(" ") or "  " in text:
        node.set(XML_SPACE, "preserve")
    node.text = text
    element.append(node)
    return element


def _sentence_spans(text: str) -> List[Tuple[int, int, str]]:
    spans: List[Tuple[int, int, str]] = []
    for match in re.finditer(r"[^.!?\n]+(?:[.!?]+|$)", text or ""):
        start, end = match.span()
        if match.group(0).strip():
            spans.append((start, end, match.group(0)))
    if not spans and text:
        spans.append((0, len(text), text))
    return spans


def _best_span(text: str, matched_terms: Iterable[str]) -> Tuple[int, int]:
    terms = [normalised(term) for term in matched_terms if normalised(term)]
    spans = _sentence_spans(text)
    if not spans:
        return (0, len(text or ""))
    ranked = []
    for start, end, sentence in spans:
        low = normalised(sentence)
        hits = sum(1 for term in terms if term in low)
        ranked.append((hits, len(sentence.strip()), start, end))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    _, _, start, end = ranked[0]
    return start, end


def _concise_comment(row: Dict[str, Any]) -> str:
    code = row.get("code", "")
    item = clean_text(row.get("item", "")).rstrip(".")
    status = row.get("status")
    if row.get("review_type") == "supervisor_comment":
        short_item = item if len(item) <= 220 else item[:217].rstrip() + "..."
        if status == STATUS_MISSING:
            guidance = f"The earlier supervisor comment has not been clearly addressed: {short_item}"
        elif status == STATUS_MANUAL:
            guidance = f"Manual confirmation is required for the earlier supervisor comment: {short_item}"
        else:
            guidance = f"The earlier supervisor comment is only partly addressed. Strengthen the revision: {short_item}"
        return f"[{code} Supervisor comment follow-up: {guidance}]"
    if status == STATUS_MISSING:
        guidance = f"Add content that clearly demonstrates that {item.lower()}."
    elif status == STATUS_MANUAL:
        guidance = f"Check this passage against the relevant sections and show clearly that {item.lower()}."
    else:
        guidance = f"Strengthen this passage so it fully demonstrates that {item.lower()}. Explain the link or justification rather than merely mentioning it."
    return f"[{code} Supervisor comment: {guidance}]"


def _replace_run_with_parts(run, before: str, marked: str, after: str):
    parent = run._r.getparent()
    index = parent.index(run._r)
    created = []
    for value, colour in ((before, None), (marked, REVIEW_RED), (after, None)):
        if not value:
            created.append(None)
            continue
        element = _run_element(value, source_run=run, colour=colour)
        parent.insert(index, element)
        index += 1
        created.append(element)
    parent.remove(run._r)
    return created


def _mark_span_and_insert_comment(paragraph: Paragraph, start: int, end: int, comment: str) -> bool:
    if start >= end:
        return False
    runs = list(paragraph.runs)
    cursor = 0
    anchor = None
    changed = False

    for run in runs:
        text = run.text or ""
        run_start, run_end = cursor, cursor + len(text)
        cursor = run_end
        if not text or run_end <= start or run_start >= end:
            continue

        local_start = max(0, start - run_start)
        local_end = min(len(text), end - run_start)
        before = text[:local_start]
        marked = text[local_start:local_end]
        after = text[local_end:]
        created = _replace_run_with_parts(run, before, marked, after)
        changed = True
        marked_element = created[1]
        if local_end == len(text) or end <= run_end:
            anchor = marked_element if marked_element is not None else created[0]
        elif marked_element is not None:
            anchor = marked_element

    if changed and anchor is not None:
        parent = anchor.getparent()
        index = parent.index(anchor) + 1
        comment_element = _run_element(" " + comment, colour=COMMENT_GREEN, italic=True)
        parent.insert(index, comment_element)
        return True
    return False


def _paragraph_number_map(document) -> Dict[int, Paragraph]:
    output: Dict[int, Paragraph] = {}
    counter = 0
    for paragraph in document.paragraphs:
        if clean_text(paragraph.text):
            counter += 1
            output[counter] = paragraph
    return output


def _find_heading(document, headings: Iterable[str]) -> Optional[Paragraph]:
    targets = [normalised(value) for value in headings if normalised(value)]
    for paragraph in document.paragraphs:
        raw = clean_text(paragraph.text)
        low = normalised(raw)
        if not low or "supervisor comment" in low:
            continue
        style_name = ""
        try:
            style_name = (paragraph.style.name or "").lower()
        except Exception:
            pass
        looks_like_heading = (
            "heading" in style_name
            or "title" in style_name
            or len(raw.split()) <= 15
            or bool(re.match(r"^\d+(?:\.\d+){0,3}\s+", raw))
        )
        if not looks_like_heading:
            continue
        if any(target in low or low in target for target in targets):
            return paragraph
    return None


def _insert_green_comment_after(paragraph: Paragraph, comments: List[str]) -> Paragraph:
    new_p = OxmlElement("w:p")
    paragraph._p.addnext(new_p)
    new_para = Paragraph(new_p, paragraph._parent)
    for index, comment in enumerate(comments):
        run = new_para.add_run(comment)
        run.font.color.rgb = None
        run._r.get_or_add_rPr()
        _set_run_colour(run._r, COMMENT_GREEN)
        run.italic = True
        if index < len(comments) - 1:
            run.add_break()
    return new_para


def _append_review_notes(document, comments: List[str]) -> None:
    if not comments:
        return
    heading = document.add_paragraph()
    heading.style = document.styles["Heading 1"] if "Heading 1" in document.styles else heading.style
    heading.add_run("SUPERVISOR REVIEW NOTES")
    _insert_green_comment_after(heading, comments)


def build_annotated_docx(source_bytes: bytes, review: Dict[str, Any]) -> bytes:
    document = Document(io.BytesIO(source_bytes))
    paragraph_map = _paragraph_number_map(document)

    # Evidence-linked issues are inserted immediately after the relevant red sentence.
    by_paragraph: Dict[int, Dict[Tuple[int, int], List[str]]] = defaultdict(lambda: defaultdict(list))
    missing_by_heading: Dict[Tuple[str, ...], List[str]] = defaultdict(list)
    fallback_comments: List[str] = []

    review_rows = list(review.get("results", [])) + list(review.get("alignment_results", [])) + list(review.get("revision_results", []))
    for row in review_rows:
        if row.get("status") not in ACTIONABLE_STATUSES:
            continue
        comment = _concise_comment(row)
        evidence = [
            item for item in (row.get("evidence") or [])
            if not item.get("is_heading") and item.get("document_role", "current") == "current"
        ]
        if evidence:
            best = evidence[0]
            paragraph_number = best.get("paragraph")
            paragraph = paragraph_map.get(paragraph_number)
            if paragraph is not None:
                span = _best_span(paragraph.text, best.get("matched_terms") or [])
                by_paragraph[paragraph_number][span].append(comment)
                continue
        headings = tuple(row.get("headings") or [])
        if headings:
            missing_by_heading[headings].append(comment)
        else:
            fallback_comments.append(comment)

    for paragraph_number, span_groups in by_paragraph.items():
        paragraph = paragraph_map.get(paragraph_number)
        if paragraph is None:
            continue
        # Work backwards so newly inserted comments do not alter earlier character offsets.
        for (start, end), comments in sorted(span_groups.items(), key=lambda item: item[0][0], reverse=True):
            unique_comments = list(dict.fromkeys(comments))
            combined = " ".join(unique_comments)
            _mark_span_and_insert_comment(paragraph, start, end, combined)

    # Missing requirements have no source text to colour. Place the green instruction
    # directly below the most relevant section heading.
    for headings, comments in missing_by_heading.items():
        unique_comments = list(dict.fromkeys(comments))
        heading = _find_heading(document, headings)
        if heading is not None:
            _insert_green_comment_after(heading, unique_comments)
        else:
            fallback_comments.extend(unique_comments)

    _append_review_notes(document, list(dict.fromkeys(fallback_comments)))

    output = io.BytesIO()
    document.save(output)
    return output.getvalue()
