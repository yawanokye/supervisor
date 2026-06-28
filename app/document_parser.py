from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Optional

try:
    import fitz
except Exception:
    fitz = None

try:
    from docx import Document
except Exception:
    Document = None

CHAPTER_TITLE_MAP = {
    1: ["introduction", "background to the study"],
    2: ["literature review", "review of related literature"],
    3: ["research methods", "research methodology", "methodology"],
    4: ["results and discussion", "results", "findings"],
    5: ["summary conclusions and recommendations", "conclusions and recommendations", "conclusion and recommendations"],
}


STANDARD_CHAPTER_FUNCTIONS = {
    "introduction": "Chapter One: Introduction",
    "literature_review": "Chapter Two: Literature Review",
    "research_methods": "Chapter Three: Research Methods",
    "results": "Chapter Four: Results",
    "discussion": "Chapter Four: Discussion",
    "summary_conclusions_recommendations": (
        "Chapter Five: Summary, Conclusions and Recommendations"
    ),
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
    "model specification", "ethical considerations", "ethics", "response rate", "descriptive statistics",
    "hypothesis testing", "results", "findings", "presentation of results", "discussion", "discussion of findings",
    "summary of findings", "conclusion", "conclusions", "recommendation", "recommendations",
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

def is_heading(text: str, style_name: str = "") -> bool:
    raw = clean_text(text)
    low = normalised(raw)
    if not raw:
        return False
    if "heading" in (style_name or "").lower() or "title" in (style_name or "").lower():
        return True
    if detect_chapter_number(raw) is not None and len(raw.split()) <= 14:
        return True
    if re.match(r"^\d+(\.\d+){0,3}\s+\S+", raw) and len(raw.split()) <= 18:
        return True
    if raw.isupper() and len(raw.split()) <= 14:
        return True
    if any(term == low or low.startswith(term + " ") for term in KNOWN_SECTION_TERMS) and len(raw.split()) <= 18:
        return True
    # Student chapters often contain unnumbered and imperfectly worded headings.
    heading_tokens = {"introduction", "background", "problem", "purpose", "objective", "objectives", "question", "questions",
                      "hypothesis", "hypotheses", "significance", "significant", "limitation", "limitations", "delimitation",
                      "delimitations", "definition", "literature", "theory", "theoretical", "empirical", "methodology", "methods",
                      "design", "population", "sampling", "instrument", "validity", "reliability", "analysis", "ethics", "results",
                      "findings", "discussion", "conclusion", "recommendations", "references", "appendix"}
    words = set(low.split())
    # Avoid treating short declarative sentences as headings merely because they contain words
    # such as objective, significance, result or conclusion.
    if low.startswith(("the ", "this ", "these ", "those ", "it ", "they ", "we ", "our ")):
        return False
    sentence_verbs = {"is", "are", "was", "were", "will", "would", "should", "requires", "require", "includes", "include", "comprises", "comprise", "deals", "aims", "seeks"}
    if words & sentence_verbs:
        return False
    return len(raw.split()) <= 10 and bool(words & heading_tokens) and not raw.endswith((".", ",", ";", ":"))

def detect_chapter_number(text: str) -> Optional[int]:
    low = normalised(text)
    explicit = re.match(
        r"^chapter\s+("
        r"one|two|three|four|five|six|seven|eight|nine|ten|"
        r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|"
        r"seventeen|eighteen|nineteen|twenty|"
        r"xx|xix|xviii|xvii|xvi|xv|xiv|xiii|xii|xi|x|ix|viii|vii|vi|v|iv|iii|ii|i|"
        r"[1-9]|1[0-9]|20"
        r")\b",
        low,
    )
    if explicit:
        token = explicit.group(1)
        number = int(token) if token.isdigit() else CHAPTER_WORD_NUMBERS.get(token)
        if number is None or not 1 <= number <= 20:
            return None

        remainder = low[explicit.end():].strip(" .:-–—")
        if not remainder:
            return number

        if remainder.startswith(
            (
                "is ", "deals ", "being ", "will ", "comprises ",
                "is devoted ", "is concerned ", "is mainly ",
            )
        ):
            return None

        if number in CHAPTER_TITLE_MAP and any(
            title in remainder for title in CHAPTER_TITLE_MAP[number]
        ):
            return number

        if clean_text(text).isupper() or len(remainder.split()) <= 14:
            return number
        return None

    numbered = re.match(r"^([1-9]|1[0-9]|20)(?:\.0)?\s+(.+)$", low)
    if numbered:
        candidate = int(numbered.group(1))
        title = numbered.group(2)
        if candidate in CHAPTER_TITLE_MAP and any(
            value in title for value in CHAPTER_TITLE_MAP[candidate]
        ):
            return candidate

    for number, titles in CHAPTER_TITLE_MAP.items():
        if low in titles:
            return number
    return None


def detect_standard_chapter_coverage(
    paragraphs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Detect the required functions of the default five-chapter structure.

    Results and Discussion may be combined or separated. Additional chapters
    are permitted, but the standard research functions must still be present.
    """
    detected_numbers = sorted(
        {
            int(paragraph["chapter_number"])
            for paragraph in paragraphs
            if isinstance(paragraph.get("chapter_number"), int)
            and 1 <= int(paragraph["chapter_number"]) <= 20
        }
    )

    headings = [
        normalised(paragraph.get("text", ""))
        for paragraph in paragraphs
        if paragraph.get("is_heading")
    ]
    heading_text = "\n".join(headings)

    coverage = set()

    if 1 in detected_numbers or any(
        value in heading_text
        for value in ("chapter one introduction", "background to the study")
    ):
        coverage.add("introduction")

    if 2 in detected_numbers or any(
        value in heading_text
        for value in ("literature review", "review of related literature")
    ):
        coverage.add("literature_review")

    if 3 in detected_numbers or any(
        value in heading_text
        for value in (
            "research methods", "research methodology",
            "materials and methods", "methodology",
        )
    ):
        coverage.add("research_methods")

    if 4 in detected_numbers or any(
        value in heading_text
        for value in (
            "results and discussion", "presentation of results",
            "research findings", "results", "findings",
        )
    ):
        coverage.add("results")

    if any(
        value in heading_text
        for value in (
            "results and discussion", "discussion of findings",
            "discussion of results", "discussion",
        )
    ):
        coverage.add("discussion")

    has_summary = any(
        value in heading_text
        for value in ("summary of findings", "summary conclusions", "chapter summary")
    )
    has_conclusion = "conclusion" in heading_text
    has_recommendation = "recommendation" in heading_text
    standard_five_title = any(
        value in heading_text
        for value in (
            "summary conclusions and recommendations",
            "summary conclusions recommendations",
            "conclusions and recommendations",
        )
    )
    if standard_five_title or (
        has_summary and has_conclusion and has_recommendation
    ):
        coverage.add("summary_conclusions_recommendations")
    elif 5 in detected_numbers:
        chapter_five_headings = [
            normalised(paragraph.get("text", ""))
            for paragraph in paragraphs
            if paragraph.get("is_heading")
            and paragraph.get("chapter_number") == 5
        ]
        if any(
            "conclusion" in value or "recommendation" in value
            for value in chapter_five_headings
        ):
            coverage.add("summary_conclusions_recommendations")

    missing_keys = [
        key for key in STANDARD_CHAPTER_FUNCTIONS
        if key not in coverage
    ]
    optional_numbers = [
        number for number in detected_numbers if number > 5
    ]

    return {
        "detected_chapter_numbers": detected_numbers,
        "covered_functions": [
            STANDARD_CHAPTER_FUNCTIONS[key]
            for key in STANDARD_CHAPTER_FUNCTIONS
            if key in coverage
        ],
        "missing_function_keys": missing_keys,
        "missing_functions": [
            STANDARD_CHAPTER_FUNCTIONS[key] for key in missing_keys
        ],
        "optional_chapters": optional_numbers,
        "complete": not missing_keys,
    }


def extract_docx(data: bytes) -> List[Dict[str, Any]]:
    if Document is None:
        raise RuntimeError("python-docx is not installed.")
    doc = Document(io.BytesIO(data))
    out: List[Dict[str, Any]] = []
    current_heading = None
    current_chapter = None
    paragraph_no = 0
    for p in doc.paragraphs:
        text = clean_text(p.text)
        if not text:
            continue
        paragraph_no += 1
        style_name = ""
        try:
            style_name = p.style.name or ""
        except Exception:
            pass
        heading = is_heading(text, style_name)
        chapter = detect_chapter_number(text) if heading else None
        if chapter:
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
            "style": style_name,
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
        blocks = sorted(page.get_text("blocks"), key=lambda b: (round(b[1], 1), round(b[0], 1)))
        page_paragraph = 0
        for block in blocks:
            raw = clean_text(block[4] if len(block) > 4 else "")
            if not raw:
                continue
            pieces = [clean_text(x) for x in re.split(r"\n\s*\n", raw) if clean_text(x)]
            for text in pieces:
                if len(text) < 2:
                    continue
                global_paragraph += 1
                page_paragraph += 1
                heading = is_heading(text)
                chapter = detect_chapter_number(text) if heading else None
                if chapter:
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
                    "style": "",
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
    counts = {}
    for p in paragraphs:
        number = p.get("chapter_number")
        if number:
            counts[number] = counts.get(number, 0) + 1
    if counts:
        return max(counts, key=counts.get)

    first_headings = [normalised(p["text"]) for p in paragraphs[:40] if p.get("is_heading")]
    for number, titles in CHAPTER_TITLE_MAP.items():
        if any(any(title in heading for title in titles) for heading in first_headings):
            return number
    return None
