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


def _best_span(text: str, matched_terms: Iterable[str], problematic_quote: str = "") -> Tuple[int, int]:
    quote = clean_text(problematic_quote)
    if quote:
        exact_start = text.find(quote)
        if exact_start >= 0:
            return exact_start, exact_start + len(quote)
        normalised_quote = normalised(quote)
        for start, end, sentence in _sentence_spans(text):
            if normalised_quote and normalised_quote in normalised(sentence):
                return start, end
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


def _sanitise_guidance(value: str) -> str:
    text = clean_text(value)
    patterns = [
        r"^(?:retain|keep) this finding and\s+",
        r"^require (?:the student to )?",
        r"^ask the student to\s+",
        r"^the student should\s+",
    ]
    for pattern in patterns:
        text = re.sub(pattern, "", text, flags=re.I)
    text = re.sub(r"^retain this point and\s+", "", text, flags=re.I)
    if text:
        text = text[0].upper() + text[1:]
    return text.rstrip()


def _comment_body(row: Dict[str, Any]) -> str:
    action = _sanitise_guidance(row.get("required_action", ""))
    assessment = _sanitise_guidance(row.get("comment", ""))
    if not action:
        action = assessment or "Revise this passage to address the identified academic weakness."
    example = _sanitise_guidance(row.get("illustrative_guidance", ""))
    example = re.sub(r"^for example[:,]?\s*", "", example, flags=re.I)
    body = action
    if example:
        body += f" Example: {example}"
    return body


def _format_comment_group(comments: Iterable[str]) -> str:
    unique = []
    seen = set()
    for value in comments:
        text = clean_text(value).strip("[] ").rstrip(" ;.")
        key = normalised(text)
        if not text or not key or key in seen:
            continue
        seen.add(key)
        unique.append(text)
    if not unique:
        return ""
    if len(unique) == 1:
        return f"[Supervisor comment: {unique[0]}]"
    numbered = "; ".join(f"{index}. {text}" for index, text in enumerate(unique, start=1))
    return f"[Supervisor comments: {numbered}]"

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


def _merge_nearby_span_groups(
    span_groups: Dict[Tuple[int, int], List[str]],
    max_gap: int = 24,
) -> List[Tuple[Tuple[int, int], List[str]]]:
    ordered = sorted(span_groups.items(), key=lambda item: item[0][0])
    merged: List[Tuple[Tuple[int, int], List[str]]] = []
    for (start, end), comments in ordered:
        if not merged:
            merged.append(((start, end), list(comments)))
            continue
        (previous_start, previous_end), previous_comments = merged[-1]
        if start <= previous_end + max_gap:
            merged[-1] = ((previous_start, max(previous_end, end)), previous_comments + list(comments))
        else:
            merged.append(((start, end), list(comments)))
    return merged


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
    grouped = _format_comment_group(comments)
    run = new_para.add_run(grouped)
    run.font.color.rgb = None
    run._r.get_or_add_rPr()
    _set_run_colour(run._r, COMMENT_GREEN)
    run.italic = True
    return new_para


def _append_review_notes(document, comments: List[str]) -> None:
    if not comments:
        return
    heading = document.add_paragraph()
    heading.style = document.styles["Heading 1"] if "Heading 1" in document.styles else heading.style
    heading.add_run("SUPERVISOR REVIEW NOTES")
    anchor = heading
    unique = list(dict.fromkeys(clean_text(value) for value in comments if clean_text(value)))
    for start in range(0, len(unique), 5):
        anchor = _insert_green_comment_after(anchor, unique[start:start + 5])



def _remove_trailing_empty_paragraphs(document, keep: int = 1) -> None:
    trailing = []
    for paragraph in reversed(document.paragraphs):
        if clean_text(paragraph.text):
            break
        ppr = paragraph._p.find(qn("w:pPr"))
        has_section_properties = ppr is not None and ppr.find(qn("w:sectPr")) is not None
        if "w:type=\"page\"" in paragraph._p.xml or has_section_properties:
            break
        trailing.append(paragraph)
    for paragraph in trailing[keep:]:
        parent = paragraph._p.getparent()
        if parent is not None:
            parent.remove(paragraph._p)

def build_annotated_docx(source_bytes: bytes, review: Dict[str, Any]) -> bytes:
    document = Document(io.BytesIO(source_bytes))
    paragraph_map = _paragraph_number_map(document)

    # Evidence-linked issues are inserted immediately after the relevant red sentence.
    by_paragraph: Dict[int, Dict[Tuple[int, int], List[str]]] = defaultdict(lambda: defaultdict(list))
    missing_by_heading: Dict[Tuple[str, ...], List[str]] = defaultdict(list)
    fallback_comments: List[str] = []

    review_rows = list(review.get("academic_findings", [])) + list(review.get("alignment_results", [])) + list(review.get("revision_results", []))
    for row in review_rows:
        if row.get("status") not in ACTIONABLE_STATUSES:
            continue
        comment = _comment_body(row)
        evidence = [
            item for item in (row.get("evidence") or [])
            if not item.get("is_heading") and item.get("document_role", "current") == "current"
        ]
        if evidence:
            best = evidence[0]
            paragraph_number = best.get("paragraph")
            paragraph = paragraph_map.get(paragraph_number)
            if paragraph is not None:
                span = _best_span(
                    paragraph.text,
                    best.get("matched_terms") or [],
                    row.get("problematic_quote", ""),
                )
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
        # Merge overlapping or immediately adjacent findings, then work backwards so
        # inserted comments do not alter earlier character offsets.
        merged_groups = _merge_nearby_span_groups(span_groups)
        for (start, end), comments in reversed(merged_groups):
            combined = _format_comment_group(comments)
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
    _remove_trailing_empty_paragraphs(document)

    output = io.BytesIO()
    document.save(output)
    return output.getvalue()
