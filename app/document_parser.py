from __future__ import annotations

import io
import re
from typing import Any, Dict, Iterable, Iterator, List, Optional

from .thesis_structure import build_chapter_role_map

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


DOCTORAL_RESEARCH_FUNCTIONS = {
    "problem_purpose_and_questions": {
        "label": "Research problem, purpose, objectives and questions",
        "terms": [
            "statement of the problem", "problem statement", "research problem",
            "research gap", "purpose of the study", "aim of the study",
            "research objective", "research objectives", "research question",
            "research questions", "research hypothesis", "research hypotheses",
        ],
    },
    "literature_theory_and_positioning": {
        "label": "Literature, theory and scholarly positioning",
        "terms": [
            "literature review", "review of literature", "theoretical framework",
            "theoretical review", "conceptual framework", "conceptual review",
            "theory", "scholarly positioning", "state of the art",
        ],
    },
    "methodology_and_research_design": {
        "label": "Methodology and research design",
        "terms": [
            "research methodology", "research methods", "methodology",
            "research design", "research approach", "data collection",
            "sampling procedure", "analytical method", "analysis method",
            "estimation technique", "research procedure",
        ],
    },
    "evidence_results_or_findings": {
        "label": "Evidence, analysis, results or findings",
        "terms": [
            "research findings", "empirical findings", "empirical results",
            "results and findings", "results", "findings", "data analysis",
            "thematic findings", "model estimates", "analysis of evidence",
        ],
    },
    "discussion_synthesis_and_interpretation": {
        "label": "Discussion, synthesis and interpretation",
        "terms": [
            "discussion of findings", "discussion of results", "discussion",
            "integrative discussion", "synthesis", "interpretation of findings",
            "interpretation of results", "alternative explanations",
        ],
    },
    "conclusions_contribution_and_implications": {
        "label": "Conclusions, contribution and implications",
        "terms": [
            "contribution to knowledge", "original contribution",
            "theoretical contribution", "professional contribution",
            "conclusion", "conclusions", "implications", "recommendations",
            "future research", "suggestions for further research",
        ],
    },
}

DOCTORAL_ESSENTIAL_FUNCTIONS = {
    "problem_purpose_and_questions",
    "methodology_and_research_design",
    "evidence_results_or_findings",
    "conclusions_contribution_and_implications",
}


PHD_PRESCRIBED_ELEMENTS = {
    "background_and_context": {
        "label": "Background, context and rationale",
        "terms": ["background to the study", "background of the study", "study context", "contextual framework", "rationale for the study"],
    },
    "problem_statement": {
        "label": "Clearly evidenced research problem",
        "terms": ["statement of the problem", "problem statement", "research problem"],
    },
    "purpose_objectives_questions": {
        "label": "Purpose, objectives and research questions or hypotheses",
        "terms": ["purpose of the study", "aim of the study", "research objectives", "specific objectives", "research questions", "research hypotheses", "hypothesis development"],
    },
    "significance_scope_and_definitions": {
        "label": "Significance, scope and key definitions",
        "terms": ["significance of the study", "scope of the study", "delimitations of the study", "definition of terms", "key concepts"],
    },
    "critical_literature_synthesis": {
        "label": "Critical literature synthesis and scholarly positioning",
        "terms": ["literature review", "empirical review", "critical synthesis", "state of the art", "research gap"],
    },
    "theory_and_conceptual_framework": {
        "label": "Theoretical and conceptual framework",
        "terms": ["theoretical framework", "theoretical review", "conceptual framework", "conceptual model"],
    },
    "originality_and_gap": {
        "label": "Defensible research gap and originality claim",
        "terms": ["research gap", "originality", "novelty", "original contribution", "contribution to knowledge"],
    },
    "methodology_design_and_philosophy": {
        "label": "Methodology, design and philosophical justification",
        "terms": ["research methodology", "methodology", "research design", "research philosophy", "research paradigm", "research approach"],
    },
    "data_sampling_measurement": {
        "label": "Data sources, sampling and measurement",
        "terms": ["population of the study", "sampling procedure", "sample size", "data sources", "data collection", "measurement of variables", "operationalisation of variables", "research instrument"],
    },
    "analysis_diagnostics_and_reproducibility": {
        "label": "Analysis strategy, diagnostics and reproducibility",
        "terms": ["data analysis", "model specification", "estimation strategy", "diagnostic tests", "assumption tests", "robustness", "software", "syntax", "code"],
    },
    "ethics_and_integrity": {
        "label": "Ethics and research integrity",
        "terms": ["ethical considerations", "research ethics", "ethics approval", "informed consent", "confidentiality", "research integrity"],
    },
    "results_and_evidence": {
        "label": "Results, findings and analytical evidence",
        "terms": ["results", "research findings", "empirical findings", "model estimates", "thematic findings", "analysis of evidence"],
    },
    "discussion_and_rival_explanations": {
        "label": "Discussion, theory integration and rival explanations",
        "terms": ["discussion of findings", "discussion of results", "integrative discussion", "alternative explanations", "rival explanations", "unexpected findings"],
    },
    "conclusions_and_contribution": {
        "label": "Conclusions and original contribution to knowledge",
        "terms": ["conclusions", "conclusion", "contribution to knowledge", "theoretical contribution", "methodological contribution", "original contribution"],
    },
    "implications_limitations_and_future_research": {
        "label": "Implications, recommendations, limitations and future research",
        "terms": ["recommendations", "policy implications", "practical implications", "limitations of the study", "future research", "directions for future research"],
    },
}

PHD_ESSENTIAL_PRESCRIBED_ELEMENTS = {
    "problem_statement",
    "purpose_objectives_questions",
    "critical_literature_synthesis",
    "theory_and_conceptual_framework",
    "methodology_design_and_philosophy",
    "data_sampling_measurement",
    "analysis_diagnostics_and_reproducibility",
    "ethics_and_integrity",
    "results_and_evidence",
    "discussion_and_rival_explanations",
    "conclusions_and_contribution",
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
        "chapter introduction or overview",
        "background to the study",
        "statement of the problem",
        "purpose of the study",
        "research objectives, including general and specific objectives where used",
        "research questions",
        "research hypotheses where inferential testing is proposed",
        "significance of the study",
        "delimitations or adequately developed scope",
        "limitations",
        "definition of terms or key concepts",
        "organisation of the study",
    ],
    2: [
        "chapter introduction",
        "theoretical review or framework where relevant",
        "conceptual review",
        "empirical review organised around the objectives or relationships",
        "critical literature synthesis and research gap",
        "conceptual framework",
        "hypothesis development where relevant",
        "chapter summary",
    ],
    3: [
        "chapter introduction",
        "research philosophy or paradigm where required",
        "research approach",
        "research design",
        "study area or setting where relevant",
        "population and unit of analysis",
        "sampling frame where probability sampling is used",
        "sampling procedure",
        "sample size and justification",
        "data sources",
        "data collection instrument or extraction protocol",
        "operationalisation and measurement",
        "pilot study or pre-testing where relevant",
        "validity, reliability or trustworthiness",
        "data collection procedures",
        "data preparation and screening",
        "data processing and analysis mapped to objectives",
        "model specification and diagnostics where relevant",
        "ethical considerations where human participants or protected data are involved",
        "chapter summary",
    ],
    4: [
        "chapter introduction",
        "response rate where relevant",
        "sample or case characteristics",
        "data quality and preliminary checks",
        "descriptive or preliminary results",
        "measurement quality where scales or latent constructs are used",
        "results presented in objective or hypothesis order",
        "assumption and diagnostic tests where relevant",
        "discussion linked to the results, theory and prior evidence",
        "chapter summary",
    ],
    5: [
        "chapter introduction",
        "summary of the study",
        "summary of findings organised by objective",
        "conclusions limited to the verified findings",
        "recommendations linked to findings and responsible actors",
        "contribution and theoretical, practical or policy implications",
        "limitations of the completed study",
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
    "suggestions for future research", "future research", "summary of the study", "contribution to knowledge",
    "theoretical implications", "practical implications", "policy implications", "references", "bibliography",
    "appendix", "appendices", "abstract", "declaration", "table of contents", "list of tables", "list of figures",
    "data screening", "missing data", "outlier treatment", "common method bias", "non-response bias",
    "sample characteristics", "demographic characteristics", "data quality", "measurement quality",
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


def is_probable_toc_entry(text: str, style_name: str = "") -> bool:
    raw = clean_text(text)
    style = (style_name or "").strip().lower()
    if style.startswith("toc") or "table of contents" in style:
        return True
    if re.search(r"\.{2,}\s*\d+\s*$", raw):
        return True
    if re.match(r"^\s*chapter\s+(?:[a-z]+|[ivxlcdm]+|\d+)", raw, flags=re.I):
        if len(raw.split()) > 2 and re.search(r"\s\d+\s*$", raw):
            return True
    if section_number_from_heading(raw) and re.search(r"\s\d+\s*$", raw) and len(raw.split()) > 2:
        return True
    return False


def is_heading(text: str, style_name: str = "") -> bool:
    raw = clean_text(text)
    low = normalised(raw)
    if not raw:
        return False
    if "heading" in (style_name or "").lower() or "title" in (style_name or "").lower():
        return True
    if explicit_chapter_marker(raw) is not None:
        # A chapter marker is a heading only when it is a short display line.
        # Sentences such as “Chapter two reviews the related literature …” in
        # an organisation-of-study paragraph must not switch the parser into a
        # new chapter. Styled headings and all-uppercase display headings have
        # already been accepted above.
        return len(raw.split()) <= 8 and not re.search(r"[.!?]\s*$", raw)
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
    required_chapters = {1, 2, 3, 4, 5}
    missing_chapter_numbers = sorted(required_chapters - detected)
    return {
        "detected_chapter_numbers": profile["detected_chapters"],
        "detected_chapter_labels": profile["detected_labels"],
        "covered_functions": [STANDARD_CHAPTER_FUNCTIONS[key] for key in STANDARD_CHAPTER_FUNCTIONS if evidence[key]],
        "function_evidence": evidence,
        "missing_function_keys": missing_keys,
        "missing_functions": [STANDARD_CHAPTER_FUNCTIONS[key] for key in missing_keys],
        "required_chapter_numbers": sorted(required_chapters),
        "missing_chapter_numbers": missing_chapter_numbers,
        "optional_chapters": [number for number in profile["detected_chapters"] if number > 5],
        "chapter_profile": profile,
        "complete": not missing_keys and not missing_chapter_numbers,
    }



def detect_doctoral_functional_coverage(
    paragraphs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Validate a flexible PhD thesis by research function, not chapter order.

    PhD theses may use article-based, essay-based, portfolio, monograph,
    practice-based or discipline-specific architectures. Chapter names, order
    and number may vary, but every prescribed doctoral research element must be
    demonstrably present and integrated in the complete thesis.
    """
    searchable_rows = [
        row for row in paragraphs
        if clean_text(row.get("text", ""))
    ]
    full_text = "\n".join(
        normalised(row.get("text", ""))
        for row in searchable_rows
    )

    evidence: Dict[str, List[Dict[str, Any]]] = {
        key: [] for key in DOCTORAL_RESEARCH_FUNCTIONS
    }

    for key, specification in DOCTORAL_RESEARCH_FUNCTIONS.items():
        matched_terms = [
            term for term in specification["terms"]
            if normalised(term) in full_text
        ]
        if not matched_terms:
            continue

        for row in searchable_rows:
            row_text = normalised(row.get("text", ""))
            row_hits = [
                term for term in matched_terms
                if normalised(term) in row_text
            ]
            if not row_hits:
                continue
            evidence[key].append({
                "heading": clean_text(
                    row.get("heading")
                    or row.get("text", "")
                )[:240],
                "paragraph": row.get("paragraph"),
                "page": row.get("page"),
                "chapter_number": row.get("chapter_number"),
                "matched_terms": row_hits[:5],
            })
            if len(evidence[key]) >= 5:
                break

    prescribed_evidence: Dict[str, List[Dict[str, Any]]] = {
        key: [] for key in PHD_PRESCRIBED_ELEMENTS
    }
    for key, specification in PHD_PRESCRIBED_ELEMENTS.items():
        for row in searchable_rows:
            row_text = normalised(row.get("text", ""))
            hits = [term for term in specification["terms"] if normalised(term) in row_text]
            if not hits:
                continue
            prescribed_evidence[key].append({
                "heading": clean_text(row.get("heading") or row.get("text", ""))[:240],
                "paragraph": row.get("paragraph"),
                "page": row.get("page"),
                "chapter_number": row.get("chapter_number"),
                "matched_terms": hits[:5],
            })
            if len(prescribed_evidence[key]) >= 5:
                break

    covered_keys = [
        key for key, rows in evidence.items() if rows
    ]
    missing_keys = [
        key for key in DOCTORAL_RESEARCH_FUNCTIONS
        if key not in covered_keys
    ]
    essential_missing = [
        key for key in DOCTORAL_ESSENTIAL_FUNCTIONS
        if key not in covered_keys
    ]

    prescribed_covered_keys = [
        key for key, rows in prescribed_evidence.items() if rows
    ]
    missing_prescribed_keys = [
        key for key in PHD_PRESCRIBED_ELEMENTS if key not in prescribed_covered_keys
    ]
    essential_prescribed_missing = [
        key for key in PHD_ESSENTIAL_PRESCRIBED_ELEMENTS
        if key not in prescribed_covered_keys
    ]

    # A PhD may use any defensible chapter architecture, but the architecture
    # must still cover every broad research function and every prescribed
    # doctoral element. Chapter variation must never become a reason to omit
    # problem, theory, methods, ethics, evidence, discussion or contribution.
    complete = (
        not essential_missing
        and len(covered_keys) == len(DOCTORAL_RESEARCH_FUNCTIONS)
        and not missing_prescribed_keys
    )

    role_map = build_chapter_role_map(paragraphs, "PhD")

    return {
        "covered_function_keys": covered_keys,
        "covered_functions": [
            DOCTORAL_RESEARCH_FUNCTIONS[key]["label"]
            for key in covered_keys
        ],
        "missing_function_keys": missing_keys,
        "missing_functions": [
            DOCTORAL_RESEARCH_FUNCTIONS[key]["label"]
            for key in missing_keys
        ],
        "essential_missing_keys": essential_missing,
        "essential_missing_functions": [
            DOCTORAL_RESEARCH_FUNCTIONS[key]["label"]
            for key in essential_missing
        ],
        "function_evidence": evidence,
        "prescribed_element_evidence": prescribed_evidence,
        "covered_prescribed_element_keys": prescribed_covered_keys,
        "covered_prescribed_elements": [PHD_PRESCRIBED_ELEMENTS[key]["label"] for key in prescribed_covered_keys],
        "missing_prescribed_element_keys": missing_prescribed_keys,
        "missing_prescribed_elements": [PHD_PRESCRIBED_ELEMENTS[key]["label"] for key in missing_prescribed_keys],
        "essential_missing_prescribed_element_keys": essential_prescribed_missing,
        "essential_missing_prescribed_elements": [PHD_PRESCRIBED_ELEMENTS[key]["label"] for key in essential_prescribed_missing],
        "chapter_role_map": role_map,
        "functions_covered_count": len(covered_keys),
        "functions_required_minimum": len(DOCTORAL_RESEARCH_FUNCTIONS),
        "fixed_chapter_sequence_required": False,
        "custom_chapter_titles_allowed": True,
        "complete": complete,
    }



_TABLE_CAPTION_RE = re.compile(
    r"^\s*table\s+(?P<number>[A-Za-z]?\d+(?:\.\d+)*|[IVXLC]+)\b\s*[:.\-–—]?\s*(?P<title>.*)$",
    flags=re.I,
)


def _table_caption(value: str) -> Optional[Dict[str, str]]:
    text = clean_text(value)
    match = _TABLE_CAPTION_RE.match(text)
    if not match:
        # Some exported SPSS tables place the caption inside the first cell,
        # after other text or line breaks. Search the cell text rather than
        # relying only on a paragraph that starts with ``Table``.
        match = re.search(
            r"(?:^|\n|\|)\s*table\s+(?P<number>[A-Za-z]?\d+(?:\.\d+)*|[IVXLC]+)\b\s*[:.\-–—]?\s*(?P<title>[^\n|]{0,180})",
            text,
            flags=re.I,
        )
    if not match:
        return None
    number = clean_text(match.group("number"))
    title = clean_text(match.group("title"))
    # Remove repeated caption text created by merged Word cells.
    title = re.split(r"\s+table\s+" + re.escape(number) + r"\b", title, maxsplit=1, flags=re.I)[0]
    return {
        "table_number": number,
        "table_title": title.strip(" :.-–—"),
        "table_caption": f"Table {number}" + (f": {title.strip(' :.-–—')}" if title.strip(" :.-–—") else ""),
    }


def _table_caption_from_cells(table: Any) -> Optional[Dict[str, str]]:
    """Return an explicit table number/title embedded in the table itself.

    Word and SPSS exports often store the visible caption in the first row
    rather than as a separate paragraph. This helper gives that explicit
    caption priority over the physical table index.
    """
    try:
        rows = list(table.rows[:2])
    except Exception:
        return None
    for row in rows:
        for cell in row.cells:
            caption = _table_caption(cell.text)
            if caption:
                return caption
    return None


def _heading_level(text: str, style_name: str = "") -> int:
    style_match = re.search(r"heading\s*(\d+)", style_name or "", flags=re.I)
    if style_match:
        return max(1, min(9, int(style_match.group(1))))
    if explicit_chapter_marker(text) is not None:
        return 1
    match = re.match(r"^\s*(\d+(?:\.\d+){0,5})\s+", text or "")
    if match:
        return min(9, match.group(1).count(".") + 1)
    return 2


BACK_MATTER_HEADINGS = {"references", "reference list", "bibliography", "appendix", "appendices"}
REFERENCE_HEADINGS = {"references", "reference list", "bibliography"}
APPENDIX_HEADINGS = {"appendix", "appendices"}


def _section_path(stack: Dict[int, str]) -> List[str]:
    return [stack[level] for level in sorted(stack) if clean_text(stack[level])]

def _iter_docx_blocks(document) -> Iterator[Any]:
    if qn is None or Paragraph is None or Table is None:
        yield from document.paragraphs
        return
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def _is_within_revision_deletion(node: Any) -> bool:
    """Return True when a WordprocessingML node belongs to deleted/moved-out text."""
    if qn is None:
        return False
    blocked = {qn("w:del"), qn("w:moveFrom")}
    parent = node.getparent() if hasattr(node, "getparent") else None
    while parent is not None:
        if parent.tag in blocked:
            return True
        parent = parent.getparent()
    return False


def docx_visible_text(block: Any) -> str:
    """Read the text Word displays, including tracked insertions.

    ``python-docx`` omits runs nested in ``w:ins`` from ``Paragraph.text``.
    Supervisor instructions and unresolved edits are often stored that way, so
    the review parser must include inserted/moved-to text while excluding
    deleted/moved-from text.
    """
    if qn is None:
        return clean_text(getattr(block, "text", ""))
    element = getattr(block, "_p", None)
    if element is None:
        element = getattr(block, "_tc", None)
    if element is None:
        element = getattr(block, "_element", None)
    if element is None:
        return clean_text(getattr(block, "text", ""))
    chunks: List[str] = []
    for node in element.iter():
        if _is_within_revision_deletion(node):
            continue
        if node.tag == qn("w:t"):
            chunks.append(node.text or "")
        elif node.tag == qn("w:tab"):
            chunks.append("	")
        elif node.tag in {qn("w:br"), qn("w:cr")}:
            chunks.append("\n")
    return clean_text("".join(chunks))


def docx_revision_metadata(block: Any) -> Dict[str, Any]:
    """Return visible revision metadata for a paragraph or table cell."""
    if qn is None:
        return {"contains_tracked_changes": False, "tracked_inserted_text": ""}
    element = getattr(block, "_p", None)
    if element is None:
        element = getattr(block, "_tc", None)
    if element is None:
        element = getattr(block, "_element", None)
    if element is None:
        return {"contains_tracked_changes": False, "tracked_inserted_text": ""}
    inserted: List[str] = []
    has_change = False
    for node in element.iter():
        if node.tag in {qn("w:ins"), qn("w:del"), qn("w:moveFrom"), qn("w:moveTo")}:
            has_change = True
        if node.tag == qn("w:t") and not _is_within_revision_deletion(node):
            parent = node.getparent()
            while parent is not None and parent is not element:
                if parent.tag in {qn("w:ins"), qn("w:moveTo")}:
                    inserted.append(node.text or "")
                    break
                parent = parent.getparent()
    return {
        "contains_tracked_changes": has_change,
        "tracked_inserted_text": clean_text("".join(inserted)),
    }


def extract_docx(data: bytes) -> List[Dict[str, Any]]:
    if Document is None:
        raise RuntimeError("python-docx is not installed.")
    doc = Document(io.BytesIO(data))
    out: List[Dict[str, Any]] = []
    current_heading = None
    current_chapter = None
    paragraph_no = 0
    table_index = 0
    academic_table_sequence = 0
    heading_stack: Dict[int, str] = {}
    pending_table_caption: Optional[Dict[str, str]] = None
    pending_caption_distance = 0
    in_references = False
    in_keywords = False
    in_appendix = False

    for block in _iter_docx_blocks(doc):
        if Table is not None and isinstance(block, Table):
            table_index += 1
            embedded_caption = _table_caption_from_cells(block)
            if current_chapter is not None:
                academic_table_sequence += 1
            fallback_number = academic_table_sequence or table_index
            usable_pending = pending_table_caption if pending_caption_distance <= 2 else None
            caption = embedded_caption or usable_pending or {
                "table_number": str(fallback_number),
                "table_title": "",
                "table_caption": f"Table {fallback_number}",
            }
            # Link a preceding caption paragraph to the physical table. This
            # lets the report and annotated document route a table finding to
            # the table even when the model cites the caption rather than a row.
            if usable_pending and out and out[-1].get("source_kind") == "table_caption":
                out[-1]["table_index"] = table_index
            current_path = _section_path(heading_stack)
            for row_index, row in enumerate(block.rows, start=1):
                values = [docx_visible_text(cell) for cell in row.cells if docx_visible_text(cell)]
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
                    "section_path": list(current_path),
                    "chapter_number": current_chapter,
                    "chapter_marker_number": None,
                    "chapter_title_number": None,
                    "section_number": None,
                    "section_number_chapter": None,
                    "chapter_detection_basis": "inherited" if current_chapter else "unassigned",
                    "is_toc_entry": False,
                    "style": "Table",
                    "source_kind": "table_row",
                    "table_index": table_index,
                    "table_row": row_index,
                    **caption,
                })
            pending_table_caption = None
            pending_caption_distance = 0
            continue

        text = docx_visible_text(block)
        if not text:
            continue
        paragraph_no += 1
        try:
            style_name = block.style.name or ""
        except Exception:
            style_name = ""
        raw_heading = is_heading(text, style_name)
        toc_entry = is_probable_toc_entry(text, style_name)
        low_text = normalised(text)
        raw_marker = explicit_chapter_marker(text) if raw_heading and not toc_entry else None
        if raw_heading and not toc_entry and low_text in REFERENCE_HEADINGS:
            in_references = True
            in_keywords = False
        elif raw_heading and not toc_entry and low_text in APPENDIX_HEADINGS:
            in_references = False
            in_keywords = False
            in_appendix = True
        elif raw_heading and not toc_entry and low_text == "keywords":
            in_keywords = True
        elif raw_marker is not None:
            in_references = False
            in_keywords = False
            in_appendix = False

        heading = raw_heading
        if in_references and low_text not in REFERENCE_HEADINGS:
            heading = False
        if in_keywords and low_text != "keywords" and raw_marker is None:
            heading = False
        marker = raw_marker if heading and not toc_entry else None
        title_chapter = (
            canonical_chapter_title_number(
                text,
                style_name=style_name,
                current_chapter=current_chapter,
            )
            if heading and not toc_entry and not in_appendix
            else None
        )
        section_number = (
            section_number_from_heading(text) if heading and not toc_entry and not in_appendix else None
        )
        section_chapter = (
            chapter_from_section_number(text) if heading and not toc_entry and not in_appendix else None
        )
        chapter = marker or title_chapter or section_chapter
        if heading and not toc_entry and low_text in BACK_MATTER_HEADINGS:
            current_chapter = None
            heading_stack = {}
        elif chapter is not None:
            current_chapter = chapter
        if heading:
            current_heading = text
            level = _heading_level(text, style_name)
            heading_stack = {k: v for k, v in heading_stack.items() if k < level}
            heading_stack[level] = text

        caption = _table_caption(text)
        if caption:
            pending_table_caption = caption
            pending_caption_distance = 0
        elif pending_table_caption is not None:
            pending_caption_distance += 1
            if pending_caption_distance > 2:
                pending_table_caption = None
                pending_caption_distance = 0

        out.append({
            "text": text,
            "page": None,
            "paragraph": paragraph_no,
            "page_paragraph": None,
            "is_heading": heading,
            "heading": current_heading,
            "section_path": _section_path(heading_stack),
            "chapter_number": current_chapter,
            "chapter_marker_number": marker,
            "chapter_title_number": title_chapter,
            "section_number": section_number,
            "section_number_chapter": section_chapter,
            "chapter_detection_basis": (
                "toc_entry" if toc_entry
                else "back_matter" if heading and low_text in BACK_MATTER_HEADINGS
                else "chapter_marker" if marker is not None
                else "chapter_title" if title_chapter is not None
                else "numbered_section" if section_chapter is not None
                else "inherited" if current_chapter is not None
                else "unassigned"
            ),
            "is_toc_entry": toc_entry,
            "style": style_name,
            "source_kind": "table_caption" if caption else "paragraph",
            "table_index": None,
            "table_row": None,
            "table_number": caption.get("table_number") if caption else None,
            "table_title": caption.get("table_title") if caption else None,
            "table_caption": caption.get("table_caption") if caption else None,
            **docx_revision_metadata(block),
        })
    return out


def extract_pdf(data: bytes) -> List[Dict[str, Any]]:
    if fitz is None:
        raise RuntimeError("PyMuPDF is not installed.")
    doc = fitz.open(stream=data, filetype="pdf")
    out: List[Dict[str, Any]] = []
    current_heading = None
    current_chapter = None
    heading_stack: Dict[int, str] = {}
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
                raw_heading = is_heading(text)
                toc_entry = is_probable_toc_entry(text)
                low_text = normalised(text)
                raw_marker = explicit_chapter_marker(text) if raw_heading and not toc_entry else None
                if raw_heading and not toc_entry and low_text in REFERENCE_HEADINGS:
                    in_references = True
                    in_keywords = False
                elif raw_heading and not toc_entry and low_text in APPENDIX_HEADINGS:
                    in_references = False
                    in_keywords = False
                    in_appendix = True
                elif raw_heading and not toc_entry and low_text == "keywords":
                    in_keywords = True
                elif raw_marker is not None:
                    in_references = False
                    in_keywords = False
                    in_appendix = False

                heading = raw_heading
                if in_references and low_text not in REFERENCE_HEADINGS:
                    heading = False
                if in_keywords and low_text != "keywords" and raw_marker is None:
                    heading = False
                marker = raw_marker if heading and not toc_entry else None
                title_chapter = (
                    canonical_chapter_title_number(
                        text,
                        current_chapter=current_chapter,
                    )
                    if heading and not toc_entry and not in_appendix
                    else None
                )
                section_number = (
                    section_number_from_heading(text) if heading and not toc_entry and not in_appendix else None
                )
                section_chapter = (
                    chapter_from_section_number(text) if heading and not toc_entry and not in_appendix else None
                )
                chapter = marker or title_chapter or section_chapter
                if heading and not toc_entry and low_text in BACK_MATTER_HEADINGS:
                    current_chapter = None
                    heading_stack = {}
                elif chapter is not None:
                    current_chapter = chapter
                if heading:
                    current_heading = text
                    level = _heading_level(text)
                    heading_stack = {k: v for k, v in heading_stack.items() if k < level}
                    heading_stack[level] = text
                caption = _table_caption(text)
                out.append({
                    "text": text,
                    "page": page_index + 1,
                    "paragraph": global_paragraph,
                    "page_paragraph": page_paragraph,
                    "is_heading": heading,
                    "heading": current_heading,
                    "section_path": _section_path(heading_stack),
                    "chapter_number": current_chapter,
                    "chapter_marker_number": marker,
                    "chapter_title_number": title_chapter,
                    "section_number": section_number,
                    "section_number_chapter": section_chapter,
                    "chapter_detection_basis": (
                        "toc_entry" if toc_entry
                        else "back_matter" if heading and low_text in BACK_MATTER_HEADINGS
                        else "chapter_marker" if marker is not None
                        else "chapter_title" if title_chapter is not None
                        else "numbered_section" if section_chapter is not None
                        else "inherited" if current_chapter is not None
                        else "unassigned"
                    ),
                    "is_toc_entry": toc_entry,
                    "style": "",
                    "source_kind": "table_caption" if caption else "pdf_block",
                    "table_index": None,
                    "table_row": None,
                    "table_number": caption.get("table_number") if caption else None,
                    "table_title": caption.get("table_title") if caption else None,
                    "table_caption": caption.get("table_caption") if caption else None,
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
