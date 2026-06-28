from __future__ import annotations

import io
import re
from typing import Any, Dict, Iterable, Iterator, List, Optional

try:
    import fitz
except Exception:
    fitz = None

try:
    from docx import Document
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph
except Exception:
    Document = None
    qn = None
    Table = None
    Paragraph = None


CHAPTER_TITLE_MAP = {
    1: ["introduction"],
    2: ["literature review", "review of related literature"],
    3: ["research methods", "research methodology", "materials and methods"],
    4: ["results and discussion", "results", "research findings"],
    5: [
        "summary conclusions and recommendations",
        "summary, conclusions and recommendations",
        "conclusions and recommendations",
    ],
}

CHAPTER_DISPLAY_NAMES = {
    1: "Chapter One: Introduction",
    2: "Chapter Two: Literature Review",
    3: "Chapter Three: Research Methods",
    4: "Chapter Four: Results and Discussion",
    5: "Chapter Five: Summary, Conclusions and Recommendations",
}

STANDARD_CHAPTER_FUNCTIONS = {
    "introduction": CHAPTER_DISPLAY_NAMES[1],
    "literature_review": CHAPTER_DISPLAY_NAMES[2],
    "research_methods": CHAPTER_DISPLAY_NAMES[3],
    "results": "Chapter Four: Results",
    "discussion": "Chapter Four: Discussion",
    "summary_conclusions_recommendations": CHAPTER_DISPLAY_NAMES[5],
}

CHAPTER_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20,
    "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5,
    "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10,
    "xi": 11, "xii": 12, "xiii": 13, "xiv": 14, "xv": 15,
    "xvi": 16, "xvii": 17, "xviii": 18, "xix": 19, "xx": 20,
}

CHAPTER_EXPECTED_COMPONENTS = {
    1: [
        "background to the study",
        "statement of the problem",
        "purpose of the study",
        "research objectives",
        "research questions",
        "research hypotheses",
        "significance of the study",
        "delimitation",
        "limitations",
        "definition of terms",
        "organisation of the study",
    ],
    2: [
        "conceptual review",
        "theoretical review",
        "theoretical framework",
        "empirical review",
        "conceptual framework",
        "hypothesis development",
        "literature review summary",
    ],
    3: [
        "research philosophy",
        "research approach",
        "research design",
        "study area",
        "population",
        "sampling procedure",
        "sample size",
        "data collection instrument",
        "validity and reliability",
        "data collection procedures",
        "data processing and analysis",
        "model specification",
        "diagnostic tests",
        "ethical considerations",
    ],
    4: [
        "response rate",
        "sample characteristics",
        "descriptive statistics",
        "hypothesis testing",
        "presentation of results",
        "results",
        "discussion of findings",
        "discussion",
        "model diagnostics",
        "diagnostic tests",
    ],
    5: [
        "summary of findings",
        "conclusions",
        "recommendations",
        "contribution to knowledge",
        "implications",
        "suggestions for further research",
    ],
}

KNOWN_SECTION_TERMS = [
    "introduction", "background", "background to the study", "background of the study",
    "statement of the problem", "problem statement", "purpose of the study", "aim of the study",
    "objective of the study", "objectives of the study", "research objective", "research objectives",
    "general objective", "specific objective", "specific objectives", "research question", "research questions",
    "research hypothesis", "research hypotheses", "hypothesis", "hypotheses",
    "significance of the study", "significant of the study", "limitations of the study", "limitation of the study",
    "delimitations of the study", "delimitation of the study", "scope of the study", "definition of terms",
    "operational definition of terms", "organisation of the study", "organization of the study",
    "conceptual review", "conceptual literature", "theoretical review", "theoretical framework",
    "empirical review", "review of empirical literature", "conceptual framework", "hypothesis development",
    "hypotheses development", "chapter summary", "summary of the chapter", "research philosophy",
    "research paradigm", "research approach", "research design", "study area", "study setting",
    "population of the study", "target population", "sampling frame", "sample size", "sample size determination",
    "sampling technique", "sampling procedure", "data source", "data sources", "data collection instrument",
    "research instrument", "operationalisation of variables", "operationalization of variables",
    "measurement of variables", "pilot study", "pretesting", "validity and reliability", "trustworthiness",
    "data collection procedure", "data collection procedures", "data preparation", "data analysis",
    "model specification", "diagnostic tests", "model diagnostics", "assumption tests", "regression diagnostics",
    "measurement model assessment", "structural model assessment", "ethical considerations", "ethics",
    "response rate", "descriptive statistics", "hypothesis testing", "results", "findings",
    "presentation of results", "discussion", "discussion of findings", "summary of findings",
    "conclusion", "conclusions", "recommendation", "recommendations",
    "suggestions for future research", "future research", "references", "appendix", "appendices",
]


def clean_text(text: str) -> str:
    text = (text or "").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalised(text: str) -> str:
    text = clean_text(text).lower()
    text = re.sub(r"[^a-z0-9\s./&()-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def section_number_from_heading(text: str) -> Optional[str]:
    match = re.match(
        r"^\s*([1-9]|1[0-9]|20)\.(\d+)(?:\.(\d+))?(?:\.(\d+))?\b",
        clean_text(text),
    )
    if not match:
        return None
    return ".".join(part for part in match.groups() if part is not None)


def chapter_from_section_number(text: str) -> Optional[int]:
    section_number = section_number_from_heading(text)
    if not section_number:
        return None
    try:
        chapter = int(section_number.split(".", 1)[0])
    except (TypeError, ValueError):
        return None
    return chapter if 1 <= chapter <= 20 else None


def explicit_chapter_marker(text: str) -> Optional[int]:
    low = normalised(text)
    match = re.match(
        r"^chapter\s+("
        r"one|two|three|four|five|six|seven|eight|nine|ten|"
        r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|"
        r"seventeen|eighteen|nineteen|twenty|"
        r"xx|xix|xviii|xvii|xvi|xv|xiv|xiii|xii|xi|x|ix|viii|vii|vi|v|iv|iii|ii|i|"
        r"[1-9]|1[0-9]|20"
        r")\b",
        low,
    )
    if not match:
        return None
    token = match.group(1)
    chapter = int(token) if token.isdigit() else CHAPTER_WORD_NUMBERS.get(token)
    return chapter if chapter and 1 <= chapter <= 20 else None


def _heading_without_number(text: str) -> str:
    value = clean_text(text)
    value = re.sub(
        r"^\s*(?:chapter\s+(?:[a-z]+|\d+)|\d+(?:\.\d+){1,3})\s*[:.\-–—]*\s*",
        "",
        value,
        flags=re.I,
    )
    return normalised(value)



def canonical_chapter_title_number(
    text: str,
    *,
    style_name: str = "",
    current_chapter: Optional[int] = None,
) -> Optional[int]:
    """Identify an unnumbered chapter from its canonical title.

    UCC theses commonly use unnumbered chapter and section headings. A chapter
    title is therefore accepted without a numeric prefix when its text and
    formatting indicate a top-level heading. Numbering is only a supporting
    signal and is not required.
    """
    raw = clean_text(text)
    value = _heading_without_number(raw)
    if not value:
        return None

    matched = None
    for number, titles in CHAPTER_TITLE_MAP.items():
        if value in {normalised(title) for title in titles}:
            matched = number
            break
    if matched is None:
        return None

    style = (style_name or "").strip().lower()
    is_top_style = (
        "heading 1" in style
        or style in {"title", "chapter title"}
        or style.startswith("chapter")
    )
    is_display_heading = raw.isupper() and len(raw.split()) <= 14
    is_long_canonical_title = value in {
        "literature review",
        "review of related literature",
        "research methods",
        "research methodology",
        "materials and methods",
        "results and discussion",
        "research findings",
        "summary conclusions and recommendations",
        "conclusions and recommendations",
    }

    # "Introduction" and "Results" can also be subsection headings. They start
    # a chapter only where top-level formatting or document position supports it.
    if matched == 1 and value == "introduction":
        if current_chapter is not None:
            return None
        return matched if is_top_style or is_display_heading else None

    if matched == 4 and value == "results":
        if current_chapter not in {None, 4}:
            return matched if is_top_style or is_display_heading else None
        return matched if is_top_style or is_display_heading else None

    if is_top_style or is_display_heading or (
        current_chapter is None and is_long_canonical_title
    ):
        return matched
    return None


def _component_score(headings: Iterable[str], chapter_number: int) -> int:
    expected = CHAPTER_EXPECTED_COMPONENTS.get(chapter_number, [])
    matched = set()
    for heading in headings:
        value = _heading_without_number(heading)
        if not value:
            continue
        for component in expected:
            target = normalised(component)
            if target == value or target in value or value in target:
                matched.add(target)
    return len(matched)


def detect_chapter_number(text: str) -> Optional[int]:
    explicit = explicit_chapter_marker(text)
    if explicit is not None:
        return explicit

    title_chapter = canonical_chapter_title_number(
        text,
        current_chapter=None,
    )
    if title_chapter is not None:
        return title_chapter

    numbered = chapter_from_section_number(text)
    if numbered is not None:
        return numbered
    return None


def is_heading(text: str, style_name: str = "") -> bool:
    raw = clean_text(text)
    low = normalised(raw)
    if not raw:
        return False
    if "heading" in (style_name or "").lower() or "title" in (style_name or "").lower():
        return True
    if explicit_chapter_marker(raw) is not None:
        return True
    if section_number_from_heading(raw) is not None and len(raw.split()) <= 20:
        return True
    if raw.isupper() and len(raw.split()) <= 14:
        return True
    if any(term == low or low.startswith(term + " ") for term in KNOWN_SECTION_TERMS) and len(raw.split()) <= 18:
        return True

    heading_tokens = {
        "introduction", "background", "problem", "purpose", "objective", "objectives",
        "question", "questions", "hypothesis", "hypotheses", "significance", "limitation",
        "limitations", "delimitation", "delimitations", "definition", "literature", "theory",
        "theoretical", "empirical", "methodology", "methods", "design", "population", "sampling",
        "instrument", "validity", "reliability", "analysis", "diagnostic", "diagnostics", "ethics",
        "results", "findings", "discussion", "conclusion", "recommendations", "references", "appendix",
    }
    words = set(low.split())
    if low.startswith(("the ", "this ", "these ", "those ", "it ", "they ", "we ", "our ")):
        return False
    sentence_verbs = {
        "is", "are", "was", "were", "will", "would", "should", "requires", "require",
        "includes", "include", "comprises", "comprise", "deals", "aims", "seeks",
    }
    if words & sentence_verbs:
        return False
    return len(raw.split()) <= 10 and bool(words & heading_tokens) and not raw.endswith((".", ",", ";", ":"))


def detect_document_chapter_profile(paragraphs: List[Dict[str, Any]]) -> Dict[str, Any]:
    explicit = sorted({
        int(row["chapter_marker_number"])
        for row in paragraphs
        if isinstance(row.get("chapter_marker_number"), int)
    })
    title_based = sorted({
        int(row["chapter_title_number"])
        for row in paragraphs
        if isinstance(row.get("chapter_title_number"), int)
    })
    numbered = sorted({
        int(row["section_number_chapter"])
        for row in paragraphs
        if isinstance(row.get("section_number_chapter"), int)
    })
    assigned = sorted({
        int(row["chapter_number"])
        for row in paragraphs
        if isinstance(row.get("chapter_number"), int)
    })
    headings = [
        clean_text(row.get("text", ""))
        for row in paragraphs
        if row.get("is_heading")
    ]
    scores = {
        number: _component_score(headings, number)
        for number in range(1, 6)
    }

    detected = sorted(
        set(explicit)
        | set(title_based)
        | set(numbered)
        | set(assigned)
    )
    inferred = None
    confidence = "none"
    if not detected:
        ranked = sorted(
            scores.items(),
            key=lambda item: item[1],
            reverse=True,
        )
        if ranked and ranked[0][1] >= 3:
            best_number, best_score = ranked[0]
            second_score = ranked[1][1] if len(ranked) > 1 else 0
            if best_score >= second_score + 2:
                inferred = best_number
                confidence = "strong"
                detected = [best_number]

    if explicit or title_based:
        primary_basis = "chapter_title"
    elif numbered:
        primary_basis = "section_numbering"
    elif inferred is not None:
        primary_basis = "expected_components"
    else:
        primary_basis = "unconfirmed"

    return {
        "explicit_chapters": explicit,
        "title_based_chapters": title_based,
        "numbered_section_chapters": numbered,
        "assigned_chapters": assigned,
        "detected_chapters": detected,
        "detected_labels": [
            CHAPTER_DISPLAY_NAMES.get(number, f"Chapter {number}")
            for number in detected
        ],
        "component_scores": scores,
        "inferred_chapter": inferred,
        "inference_confidence": confidence,
        "numbering_used": bool(numbered),
        "primary_detection_basis": primary_basis,
    }


def detect_standard_chapter_coverage(paragraphs: List[Dict[str, Any]]) -> Dict[str, Any]:
    profile = detect_document_chapter_profile(paragraphs)
    detected = set(profile["detected_chapters"])
    headings_by_chapter: Dict[int, List[str]] = {}
    for row in paragraphs:
        if row.get("is_heading") and isinstance(row.get("chapter_number"), int):
            headings_by_chapter.setdefault(int(row["chapter_number"]), []).append(clean_text(row.get("text", "")))

    evidence = {key: [] for key in STANDARD_CHAPTER_FUNCTIONS}

    def record(key: str, value: str) -> None:
        if value and value not in evidence[key]:
            evidence[key].append(value)

    if 1 in detected:
        record("introduction", CHAPTER_DISPLAY_NAMES[1])
    if 2 in detected:
        record("literature_review", CHAPTER_DISPLAY_NAMES[2])
    if 3 in detected:
        record("research_methods", CHAPTER_DISPLAY_NAMES[3])

    for number in detected:
        headings = headings_by_chapter.get(number, [])
        title_text = " ".join(_heading_without_number(value) for value in headings)
        if number == 4 or any(term in title_text for term in (
            "results and discussion", "research findings", "presentation of results", "results",
        )):
            record("results", f"Chapter {number}")
        if any(term in title_text for term in (
            "results and discussion", "discussion of findings", "discussion of results", "discussion",
        )):
            record("discussion", f"Chapter {number}")
        if any(term in title_text for term in (
            "summary conclusions and recommendations",
            "summary, conclusions and recommendations",
            "conclusions and recommendations",
        )) or _component_score(headings, 5) >= 2:
            record("summary_conclusions_recommendations", f"Chapter {number}")

    if (
        not profile["explicit_chapters"]
        and not profile["title_based_chapters"]
        and not profile["numbered_section_chapters"]
    ):
        inferred = profile.get("inferred_chapter")
        if inferred == 1:
            record("introduction", "Strong Chapter One component profile")
        elif inferred == 2:
            record("literature_review", "Strong Chapter Two component profile")
        elif inferred == 3:
            record("research_methods", "Strong Chapter Three component profile")
        elif inferred == 4:
            record("results", "Strong Chapter Four component profile")
            if profile["component_scores"].get(4, 0) >= 3:
                record("discussion", "Strong Chapter Four component profile")
        elif inferred == 5:
            record("summary_conclusions_recommendations", "Strong Chapter Five component profile")

    missing_keys = [key for key in STANDARD_CHAPTER_FUNCTIONS if not evidence[key]]
    return {
        "detected_chapter_numbers": profile["detected_chapters"],
        "detected_chapter_labels": profile["detected_labels"],
        "covered_functions": [STANDARD_CHAPTER_FUNCTIONS[key] for key in STANDARD_CHAPTER_FUNCTIONS if evidence[key]],
        "function_evidence": evidence,
        "missing_function_keys": missing_keys,
        "missing_functions": [STANDARD_CHAPTER_FUNCTIONS[key] for key in missing_keys],
        "optional_chapters": [number for number in profile["detected_chapters"] if number > 5],
        "chapter_profile": profile,
        "complete": not missing_keys,
    }


def _iter_docx_blocks(document) -> Iterator[Any]:
    if qn is None or Paragraph is None or Table is None:
        yield from document.paragraphs
        return
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def extract_docx(data: bytes) -> List[Dict[str, Any]]:
    if Document is None:
        raise RuntimeError("python-docx is not installed.")
    doc = Document(io.BytesIO(data))
    out: List[Dict[str, Any]] = []
    current_heading = None
    current_chapter = None
    paragraph_no = 0
    table_index = 0

    for block in _iter_docx_blocks(doc):
        if Table is not None and isinstance(block, Table):
            table_index += 1
            for row_index, row in enumerate(block.rows, start=1):
                values = [clean_text(cell.text) for cell in row.cells if clean_text(cell.text)]
                if not values:
                    continue
                paragraph_no += 1
                out.append({
                    "text": " | ".join(values),
                    "page": None,
                    "paragraph": paragraph_no,
                    "page_paragraph": None,
                    "is_heading": False,
                    "heading": current_heading,
                    "chapter_number": current_chapter,
                    "chapter_marker_number": None,
                    "chapter_title_number": None,
                    "section_number": None,
                    "section_number_chapter": None,
                    "chapter_detection_basis": "inherited" if current_chapter else "unassigned",
                    "style": "Table",
                    "source_kind": "table_row",
                    "table_index": table_index,
                    "table_row": row_index,
                })
            continue

        text = clean_text(block.text)
        if not text:
            continue
        paragraph_no += 1
        try:
            style_name = block.style.name or ""
        except Exception:
            style_name = ""
        heading = is_heading(text, style_name)
        marker = explicit_chapter_marker(text) if heading else None
        title_chapter = (
            canonical_chapter_title_number(
                text,
                style_name=style_name,
                current_chapter=current_chapter,
            )
            if heading
            else None
        )
        section_number = (
            section_number_from_heading(text) if heading else None
        )
        section_chapter = (
            chapter_from_section_number(text) if heading else None
        )
        chapter = marker or title_chapter or section_chapter
        if chapter is not None:
            current_chapter = chapter
        if heading:
            current_heading = text
        out.append({
            "text": text,
            "page": None,
            "paragraph": paragraph_no,
            "page_paragraph": None,
            "is_heading": heading,
            "heading": current_heading,
            "chapter_number": current_chapter,
            "chapter_marker_number": marker,
            "chapter_title_number": title_chapter,
            "section_number": section_number,
            "section_number_chapter": section_chapter,
            "chapter_detection_basis": (
                "chapter_marker" if marker is not None
                else "chapter_title" if title_chapter is not None
                else "numbered_section" if section_chapter is not None
                else "inherited" if current_chapter is not None
                else "unassigned"
            ),
            "style": style_name,
            "source_kind": "paragraph",
            "table_index": None,
            "table_row": None,
        })
    return out


def extract_pdf(data: bytes) -> List[Dict[str, Any]]:
    if fitz is None:
        raise RuntimeError("PyMuPDF is not installed.")
    doc = fitz.open(stream=data, filetype="pdf")
    out: List[Dict[str, Any]] = []
    current_heading = None
    current_chapter = None
    global_paragraph = 0
    for page_index in range(len(doc)):
        page = doc[page_index]
        blocks = sorted(page.get_text("blocks"), key=lambda block: (round(block[1], 1), round(block[0], 1)))
        page_paragraph = 0
        for block in blocks:
            raw = clean_text(block[4] if len(block) > 4 else "")
            if not raw:
                continue
            pieces = [clean_text(value) for value in re.split(r"\n\s*\n", raw) if clean_text(value)]
            for text in pieces:
                if len(text) < 2:
                    continue
                global_paragraph += 1
                page_paragraph += 1
                heading = is_heading(text)
                marker = explicit_chapter_marker(text) if heading else None
                title_chapter = (
                    canonical_chapter_title_number(
                        text,
                        current_chapter=current_chapter,
                    )
                    if heading
                    else None
                )
                section_number = (
                    section_number_from_heading(text) if heading else None
                )
                section_chapter = (
                    chapter_from_section_number(text) if heading else None
                )
                chapter = marker or title_chapter or section_chapter
                if chapter is not None:
                    current_chapter = chapter
                if heading:
                    current_heading = text
                out.append({
                    "text": text,
                    "page": page_index + 1,
                    "paragraph": global_paragraph,
                    "page_paragraph": page_paragraph,
                    "is_heading": heading,
                    "heading": current_heading,
                    "chapter_number": current_chapter,
                    "chapter_marker_number": marker,
                    "chapter_title_number": title_chapter,
                    "section_number": section_number,
                    "section_number_chapter": section_chapter,
                    "chapter_detection_basis": (
                        "chapter_marker" if marker is not None
                        else "chapter_title" if title_chapter is not None
                        else "numbered_section" if section_chapter is not None
                        else "inherited" if current_chapter is not None
                        else "unassigned"
                    ),
                    "style": "",
                    "source_kind": "pdf_block",
                    "table_index": None,
                    "table_row": None,
                })
    doc.close()
    return out


def parse_document(data: bytes, filename: str) -> List[Dict[str, Any]]:
    low = (filename or "").lower()
    if low.endswith(".docx"):
        return extract_docx(data)
    if low.endswith(".pdf"):
        return extract_pdf(data)
    raise ValueError("Unsupported file type. Upload a DOCX or text-based PDF.")


def infer_primary_chapter(paragraphs: List[Dict[str, Any]]) -> Optional[int]:
    profile = detect_document_chapter_profile(paragraphs)
    detected = profile["detected_chapters"]
    if len(detected) == 1:
        return detected[0]
    counts: Dict[int, int] = {}
    for row in paragraphs:
        number = row.get("chapter_number")
        if isinstance(number, int):
            counts[number] = counts.get(number, 0) + 1
    if counts:
        return max(counts, key=counts.get)
    return profile.get("inferred_chapter")
