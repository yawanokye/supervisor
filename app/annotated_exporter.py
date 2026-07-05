from __future__ import annotations

import io
import re
from collections import defaultdict
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from docx.text.run import Run
from docx.table import Table

from .document_parser import clean_text, normalised
from .review_rules import STATUS_MANUAL, STATUS_MISSING, STATUS_PARTIAL

ANNOTATION_EXPORT_VERSION = "1.9.1-native-comments-user-author"
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



def _shorten_comment(value: str, limit: int = 720) -> str:
    text = clean_text(value)
    if len(text) <= limit:
        return text
    shortened = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:")
    return shortened + "."

def _comment_body(row: Dict[str, Any]) -> str:
    action = _sanitise_guidance(row.get("required_action", ""))
    assessment = _sanitise_guidance(row.get("comment", ""))
    if not action:
        action = assessment or "Revise this passage to address the identified academic weakness."
    example = _sanitise_guidance(row.get("illustrative_guidance", ""))
    example = re.sub(r"^for example[:,]?\s*", "", example, flags=re.I)

    reference = clean_text(
        row.get("reference_label")
        or row.get("section_reference")
        or row.get("section")
    )
    if not row.get("table_reference"):
        table_evidence = next(
            (item for item in row.get("evidence") or [] if item.get("table_number")),
            None,
        )
        if table_evidence:
            number = clean_text(table_evidence.get("table_number", ""))
            title = clean_text(table_evidence.get("table_title", ""))
            table_reference = f"Table {number}" if number else "Table"
            if title:
                table_reference += f": {title}"
            reference = f"{reference}, {table_reference}" if reference else table_reference
    body = f"{reference}: {action}" if reference else action
    if example:
        body += f" Example: {example}"
    return _shorten_comment(body)


def _format_comment_group(comments: Iterable[str]) -> str:
    """Format text for the Word Review comment pane, not the document body."""
    unique = []
    seen = set()
    for value in comments:
        text = clean_text(value).strip("[] ").rstrip(" ;.")
        text = re.sub(r"^Supervisor comments?\s*:\s*", "", text, flags=re.I)
        key = normalised(text)
        if not text or not key or key in seen:
            continue
        seen.add(key)
        unique.append(_shorten_comment(text, 620))
        if len(unique) >= 4:
            break
    if not unique:
        return ""
    if len(unique) == 1:
        return unique[0]
    return "\n".join(f"{index}. {text}" for index, text in enumerate(unique, start=1))

def _replace_run_with_parts(run, before: str, marked: str, after: str):
    """Split a plain-text run without changing its visible formatting.

    Native Word comments must anchor to run boundaries. Splitting a run gives
    the comment an exact range while preserving the original text and run
    properties. No colour, inserted note, or tracked edit is added.
    """
    parent = run._r.getparent()
    index = parent.index(run._r)
    created = []
    for value in (before, marked, after):
        if not value:
            created.append(None)
            continue
        element = _run_element(value, source_run=run)
        parent.insert(index, element)
        index += 1
        created.append(element)
    parent.remove(run._r)
    return created


def _reviewer_initials(name: str) -> str:
    words = [part for part in re.split(r"\s+", clean_text(name)) if part]
    if not words:
        return "RV"
    initials = "".join(part[0] for part in words if part[0].isalnum()).upper()
    return (initials or "RV")[:8]


def _comment_identity(
    review: Dict[str, Any], comment_author: Optional[str] = None
) -> Tuple[str, str]:
    summary = review.get("summary") or {}
    metadata = review.get("assessment_metadata") or {}
    author = clean_text(
        comment_author
        or summary.get("reviewer_name")
        or summary.get("examiner_name")
        or metadata.get("examiner_name")
        or review.get("reviewer_name")
        or "Reviewer"
    )
    return author, _reviewer_initials(author)


def _add_native_comment(
    document,
    runs: Sequence[Run],
    comment: str,
    *,
    author: str,
    initials: str,
) -> bool:
    usable = [run for run in runs if run is not None and clean_text(run.text)]
    if not usable:
        return False
    if not hasattr(document, "add_comment"):
        raise RuntimeError(
            "Native Word comments require python-docx 1.2.0 or newer."
        )
    document.add_comment(
        runs=usable,
        text=clean_text(comment),
        author=author,
        initials=initials,
    )
    return True


def _mark_span_and_insert_comment(
    document,
    paragraph: Paragraph,
    start: int,
    end: int,
    comment: str,
    *,
    author: str,
    initials: str,
) -> bool:
    """Anchor a native comment to an exact text range.

    The paragraph text and visible formatting are preserved. The selected text
    is not recoloured and no comment paragraph is inserted into the document.
    """
    if start >= end:
        return False
    runs = list(paragraph.runs)
    cursor = 0
    marked_elements = []

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
        if created[1] is not None:
            marked_elements.append(created[1])

    if not marked_elements:
        return False
    anchor_runs = [Run(element, paragraph) for element in marked_elements]
    return _add_native_comment(
        document, anchor_runs, comment, author=author, initials=initials
    )

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


_TABLE_CAPTION_RE = re.compile(
    r"^\s*table\s+(?P<number>[A-Za-z]?\d+(?:\.\d+)*|[IVXLC]+)\b\s*[:.\-–—]?\s*(?P<title>.*)$",
    flags=re.I,
)


def _docx_blocks(document):
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def _source_locator_map(document):
    output: Dict[int, Dict[str, Any]] = {}
    tables: Dict[int, Dict[str, Any]] = {}
    paragraph_no = 0
    table_index = 0
    pending_caption: Optional[Dict[str, Any]] = None

    for block in _docx_blocks(document):
        if isinstance(block, Table):
            table_index += 1
            table_info = {
                "table": block,
                "caption_paragraph": (pending_caption or {}).get("paragraph"),
                "table_number": (pending_caption or {}).get("table_number", str(table_index)),
                "table_title": (pending_caption or {}).get("table_title", ""),
            }
            tables[table_index] = table_info
            caption_number = int((pending_caption or {}).get("paragraph_number") or 0)
            if caption_number and caption_number in output:
                output[caption_number].update({
                    "kind": "table_caption",
                    "table_index": table_index,
                    "table": block,
                    **table_info,
                })
            for row_index, row in enumerate(block.rows, start=1):
                values = [clean_text(cell.text) for cell in row.cells if clean_text(cell.text)]
                if not values:
                    continue
                paragraph_no += 1
                cell_paragraphs = []
                for cell in row.cells:
                    cell_paragraphs.extend(
                        paragraph for paragraph in cell.paragraphs
                        if clean_text(paragraph.text)
                    )
                output[paragraph_no] = {
                    "kind": "table_row",
                    "table_index": table_index,
                    "table_row": row_index,
                    "table": block,
                    "cell_paragraphs": cell_paragraphs,
                    **table_info,
                }
            pending_caption = None
            continue

        text = clean_text(block.text)
        if not text:
            continue
        paragraph_no += 1
        output[paragraph_no] = {
            "kind": "paragraph",
            "paragraph": block,
        }
        match = _TABLE_CAPTION_RE.match(text)
        if match:
            pending_caption = {
                "paragraph": block,
                "paragraph_number": paragraph_no,
                "table_number": clean_text(match.group("number")),
                "table_title": clean_text(match.group("title")),
            }

    return output, tables


def _strip_heading_number(value: str) -> str:
    return re.sub(r"^\d+(?:\.\d+){0,4}\s+", "", normalised(value)).strip()


def _find_heading(
    document,
    headings: Iterable[str],
    chapter_number: Optional[int] = None,
) -> Optional[Paragraph]:
    """Find an exact heading only. Ambiguous or partial matches are rejected."""
    targets = {normalised(value) for value in headings if normalised(value)}
    stripped_targets = {_strip_heading_number(value) for value in headings if _strip_heading_number(value)}
    candidates: List[Paragraph] = []
    active_chapter: Optional[int] = None
    chapter_words = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    }
    for paragraph in document.paragraphs:
        raw = clean_text(paragraph.text)
        low = normalised(raw)
        if not low or "supervisor comment" in low:
            continue
        chapter_match = re.fullmatch(
            r"chapter\s+(one|two|three|four|five|six|seven|eight|nine|ten|[1-9]|10)",
            low,
        )
        if chapter_match:
            token = chapter_match.group(1)
            active_chapter = int(token) if token.isdigit() else chapter_words[token]
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
        exact = low in targets or _strip_heading_number(raw) in stripped_targets
        if not exact:
            continue
        if chapter_number is not None and active_chapter != chapter_number:
            continue
        candidates.append(paragraph)
    return candidates[0] if len(candidates) == 1 else None


def _comment_on_paragraph(
    document,
    paragraph: Paragraph,
    comments: List[str],
    *,
    author: str,
    initials: str,
) -> bool:
    grouped = _format_comment_group(comments)
    runs = [run for run in paragraph.runs if clean_text(run.text)]
    return bool(
        grouped
        and runs
        and _add_native_comment(
            document, runs, grouped, author=author, initials=initials
        )
    )


def _comment_on_table(
    document,
    table: Table,
    comments: List[str],
    caption: Optional[Paragraph] = None,
    *,
    author: str,
    initials: str,
) -> bool:
    grouped = _format_comment_group(comments)
    if not grouped:
        return False
    if caption is not None:
        runs = [run for run in caption.runs if clean_text(run.text)]
        if runs and _add_native_comment(
            document, runs, grouped, author=author, initials=initials
        ):
            return True
    for row in table.rows:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                runs = [run for run in paragraph.runs if clean_text(run.text)]
                if runs and _add_native_comment(
                    document,
                    runs,
                    grouped,
                    author=author,
                    initials=initials,
                ):
                    return True
    return False


def _first_native_anchor(document) -> Optional[Paragraph]:
    """Return a stable existing paragraph for document-level comments."""
    for paragraph in document.paragraphs:
        if clean_text(paragraph.text):
            return paragraph
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    if clean_text(paragraph.text):
                        return paragraph
    return None


def _attach_document_level_comments(
    document, comments: List[str], *, author: str, initials: str
) -> None:
    """Keep unplaced findings in the Review pane without changing body text."""
    unique = list(dict.fromkeys(clean_text(value) for value in comments if clean_text(value)))
    if not unique:
        return
    anchor = _first_native_anchor(document)
    if anchor is None:
        raise RuntimeError(
            "The source document has no text that can anchor native Word comments."
        )
    for start in range(0, len(unique), 4):
        batch = unique[start:start + 4]
        prefixed = [f"Document-level review note. {value}" for value in batch]
        if not _comment_on_paragraph(
            document, anchor, prefixed, author=author, initials=initials
        ):
            raise RuntimeError("A native Word comment could not be anchored.")


def _preferred_evidence(row: Dict[str, Any], evidence: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Order evidence so the annotation lands on the exact claimed location."""
    target_section = normalised(row.get("section_reference") or row.get("section") or "")
    table_reference = clean_text(row.get("table_reference", ""))
    table_match = re.search(r"\bTable\s+([A-Za-z]?\d+(?:\.\d+)*)\b", table_reference, flags=re.I)
    target_table = normalised(table_match.group(1)) if table_match else ""
    quote = clean_text(row.get("problematic_quote", ""))

    def rank(item: Dict[str, Any]):
        item_section = normalised(item.get("section_reference") or item.get("heading") or "")
        item_table = normalised(item.get("table_number", ""))
        text = clean_text(item.get("text", ""))
        return (
            0 if target_table and item_table == target_table else 1,
            0 if quote and quote in text else 1,
            0 if target_section and item_section == target_section else 1,
            0 if item.get("is_heading") else 1,
            int(item.get("paragraph") or 0),
        )
    return sorted(evidence, key=rank)

def build_annotated_docx(
    source_bytes: bytes,
    review: Dict[str, Any],
    comment_author: Optional[str] = None,
) -> bytes:
    document = Document(io.BytesIO(source_bytes))
    author, initials = _comment_identity(review, comment_author)
    source_map, table_map = _source_locator_map(document)

    # All annotations are native Word comments. Exact quotations are used as
    # comment anchors where available. The source text, formatting, pagination,
    # tables, and headings remain unchanged.
    by_paragraph: Dict[int, Dict[Tuple[int, int], List[str]]] = defaultdict(lambda: defaultdict(list))
    after_paragraph: Dict[int, List[str]] = defaultdict(list)
    by_table: Dict[int, List[str]] = defaultdict(list)
    missing_by_heading: Dict[Tuple[Optional[int], Tuple[str, ...]], List[str]] = defaultdict(list)
    fallback_comments: List[str] = []

    review_rows = (
        list(review.get("academic_findings", []))
        + list(review.get("alignment_results", []))
        + list(review.get("revision_results", []))
    )
    for row in review_rows:
        if row.get("status") not in ACTIONABLE_STATUSES:
            continue
        if row.get("annotation_eligible") is False:
            continue

        comment = _comment_body(row)
        evidence = [
            item for item in (row.get("evidence") or [])
            if item.get("document_role", "current") == "current"
        ]
        evidence = _preferred_evidence(row, evidence)
        if evidence:
            best = evidence[0]
            try:
                paragraph_number = int(best.get("paragraph"))
            except (TypeError, ValueError):
                paragraph_number = 0
            locator = source_map.get(paragraph_number)
            if locator is not None:
                if locator.get("kind") in {"table_row", "table_caption"} or best.get("table_index"):
                    table_index = int(locator.get("table_index") or best.get("table_index") or 0)
                    if table_index:
                        by_table[table_index].append(comment)
                        continue
                paragraph = locator.get("paragraph")
                if paragraph is not None:
                    quote = clean_text(row.get("problematic_quote", ""))
                    exact_start = paragraph.text.find(quote) if quote else -1
                    if exact_start >= 0:
                        by_paragraph[paragraph_number][
                            (exact_start, exact_start + len(quote))
                        ].append(comment)
                    else:
                        after_paragraph[paragraph_number].append(comment)
                    continue

        headings = tuple(row.get("headings") or [row.get("section_reference") or row.get("section")])
        headings = tuple(value for value in headings if clean_text(value))
        if headings:
            chapter_number = row.get("chapter_number")
            if chapter_number is None:
                chapter_number = next(
                    (item.get("chapter_number") for item in evidence if item.get("chapter_number") is not None),
                    None,
                )
            try:
                chapter_number = int(chapter_number) if chapter_number is not None else None
            except (TypeError, ValueError):
                chapter_number = None
            missing_by_heading[(chapter_number, headings)].append(comment)
        else:
            fallback_comments.append(comment)

    for paragraph_number, span_groups in by_paragraph.items():
        locator = source_map.get(paragraph_number) or {}
        paragraph = locator.get("paragraph")
        if paragraph is None:
            continue
        merged_groups = _merge_nearby_span_groups(span_groups)
        for (start, end), comments in reversed(merged_groups):
            combined = _format_comment_group(comments)
            if not _mark_span_and_insert_comment(
                document, paragraph, start, end, combined,
                author=author, initials=initials,
            ):
                after_paragraph[paragraph_number].extend(comments)

    for paragraph_number, comments in after_paragraph.items():
        locator = source_map.get(paragraph_number) or {}
        paragraph = locator.get("paragraph")
        if paragraph is not None:
            unique = list(dict.fromkeys(comments))
            if not _comment_on_paragraph(
                document, paragraph, unique, author=author, initials=initials
            ):
                fallback_comments.extend(unique)
        else:
            fallback_comments.extend(comments)

    # Process tables in reverse order for stable comment anchoring.
    for table_index in sorted(by_table, reverse=True):
        table_info = table_map.get(table_index) or {}
        table = table_info.get("table")
        comments = list(dict.fromkeys(by_table[table_index]))
        caption = table_info.get("caption_paragraph")
        if table is not None:
            if not _comment_on_table(
                document, table, comments, caption=caption,
                author=author, initials=initials,
            ):
                fallback_comments.extend(comments)
        elif caption is not None:
            if not _comment_on_paragraph(
                document, caption, comments, author=author, initials=initials
            ):
                fallback_comments.extend(comments)
        else:
            fallback_comments.extend(comments)

    # Findings about absent or underdeveloped material are placed under the
    # exact supplied section or subsection heading.
    for (chapter_number, headings), comments in missing_by_heading.items():
        unique_comments = list(dict.fromkeys(comments))
        heading = _find_heading(document, headings, chapter_number=chapter_number)
        if heading is not None:
            if not _comment_on_paragraph(
                document, heading, unique_comments,
                author=author, initials=initials,
            ):
                fallback_comments.extend(unique_comments)
        else:
            fallback_comments.extend(unique_comments)

    _attach_document_level_comments(
        document,
        list(dict.fromkeys(fallback_comments)),
        author=author,
        initials=initials,
    )
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()
