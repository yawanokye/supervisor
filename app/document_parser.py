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

KNOWN_SECTION_TERMS = [
    "background to the study", "statement of the problem", "purpose of the study",
    "research objectives", "research questions", "research hypotheses",
    "significance of the study", "limitations of the study", "delimitations of the study",
    "organisation of the study", "organization of the study", "conceptual review",
    "theoretical review", "theoretical framework", "empirical review",
    "conceptual framework", "hypotheses development", "chapter summary",
    "research philosophy", "research approach", "research design", "study area",
    "study setting", "population of the study", "target population", "sampling frame",
    "sample size", "sampling technique", "data collection instrument",
    "operationalisation of variables", "operationalization of variables",
    "pilot study", "validity and reliability", "data collection procedure",
    "data preparation", "data analysis", "ethical considerations",
    "response rate", "descriptive statistics", "hypothesis testing",
    "discussion of findings", "summary of findings", "conclusions",
    "recommendations", "future research", "references", "appendices",
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
    if re.match(r"^(chapter\s+)?(one|two|three|four|five|1|2|3|4|5)\b", low) and len(raw.split()) <= 14:
        return True
    if re.match(r"^\d+(\.\d+){0,3}\s+\S+", raw) and len(raw.split()) <= 18:
        return True
    if raw.isupper() and len(raw.split()) <= 14:
        return True
    return any(term == low or low.startswith(term + " ") for term in KNOWN_SECTION_TERMS) and len(raw.split()) <= 18

def detect_chapter_number(text: str) -> Optional[int]:
    low = normalised(text)
    explicit = re.match(r"^chapter\s+(one|two|three|four|five|1|2|3|4|5|i|ii|iii|iv|v)\b", low)
    mapping = {"one":1,"1":1,"i":1,"two":2,"2":2,"ii":2,"three":3,"3":3,"iii":3,"four":4,"4":4,"iv":4,"five":5,"5":5,"v":5}
    if explicit:
        return mapping.get(explicit.group(1))
    numbered = re.match(r"^([1-5])(?:\.0)?\s+(.+)$", low)
    if numbered:
        candidate = int(numbered.group(1))
        title = numbered.group(2)
        if any(x in title for x in CHAPTER_TITLE_MAP[candidate]):
            return candidate
    for number, titles in CHAPTER_TITLE_MAP.items():
        if low in titles:
            return number
    return None

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
