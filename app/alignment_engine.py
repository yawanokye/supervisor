from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .document_parser import clean_text, normalised
from .review_rules import (
    STATUS_LABELS,
    STATUS_MANUAL,
    STATUS_MEETS,
    STATUS_MISSING,
    STATUS_PARTIAL,
    STATUS_SCORES,
)

STOPWORDS = {
    "about", "above", "across", "after", "again", "against", "among", "and", "another",
    "are", "around", "because", "been", "before", "being", "between", "both", "but", "can",
    "chapter", "could", "data", "does", "during", "each", "effect", "effects", "examine",
    "examines", "examined", "for", "from", "had", "has", "have", "how", "into", "investigate",
    "investigates", "investigated", "its", "may", "more", "most", "not", "objective", "objectives",
    "of", "on", "one", "only", "or", "other", "our", "question", "questions", "research",
    "relationship", "relationships", "should", "study", "such", "than", "that", "the", "their",
    "there", "these", "they", "this", "those", "through", "to", "two", "under", "using", "was",
    "were", "what", "when", "where", "whether", "which", "while", "with", "within", "would",
}

OBJECTIVE_HEADINGS = ["research objectives", "objectives of the study", "specific objectives"]
QUESTION_HEADINGS = ["research questions", "research question"]
HYPOTHESIS_HEADINGS = ["research hypotheses", "hypotheses", "hypothesis development"]
VARIABLE_HEADINGS = ["conceptual framework", "operationalisation", "operationalization", "measurement of variables"]
METHOD_HEADINGS = ["data analysis", "analysis plan", "model specification", "research design"]
RESULT_HEADINGS = ["results", "findings", "discussion of findings", "hypothesis testing"]
CONCLUSION_HEADINGS = ["summary of findings", "conclusions", "recommendations"]

ANALYSIS_TERMS = {
    "anova", "ancova", "correlation", "descriptive statistics", "factor analysis", "regression",
    "logit", "probit", "sem", "structural equation", "pls-sem", "mediation", "moderation",
    "bootstrapping", "thematic analysis", "content analysis", "narrative analysis", "panel data",
    "time series", "ardl", "var", "vecm", "cointegration", "difference in differences", "t-test",
    "chi-square", "mann-whitney", "kruskal-wallis", "nvivo", "smartpls", "spss", "stata", "r software",
}


def _heading_matches(heading: Optional[str], targets: Sequence[str]) -> bool:
    low = normalised(heading or "")
    return bool(low) and any(normalised(target) in low or low in normalised(target) for target in targets)


def _split_items(text: str) -> List[str]:
    raw = clean_text(text)
    pieces = re.split(r"(?:\n+|(?<=[.!?])\s+|\s+(?=\(?[a-z0-9ivx]+[.)]\s+))", raw, flags=re.I)
    output: List[str] = []
    for piece in pieces:
        value = re.sub(r"^\s*(?:[-•▪◦]|\(?[a-z0-9ivx]+[.)])\s*", "", piece, flags=re.I).strip()
        if 4 <= len(value.split()) <= 90:
            output.append(value)
    return output


def _section_items(paragraphs: Sequence[Dict[str, Any]], headings: Sequence[str]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    for paragraph in paragraphs:
        if paragraph.get("is_heading"):
            continue
        if not _heading_matches(paragraph.get("heading"), headings):
            continue
        for item in _split_items(paragraph.get("text", "")):
            output.append({"text": item, "paragraph": paragraph})
    return output


def _concept_tokens(text: str, limit: int = 10) -> List[str]:
    words = re.findall(r"[a-z][a-z0-9-]{2,}", normalised(text))
    counts = Counter(word for word in words if word not in STOPWORDS and len(word) > 3)
    return [word for word, _ in counts.most_common(limit)]


def _best_current_evidence(
    current_paragraphs: Sequence[Dict[str, Any]],
    tokens: Sequence[str],
    preferred_headings: Sequence[str],
) -> Tuple[Optional[Dict[str, Any]], int]:
    best = None
    best_score = 0
    for paragraph in current_paragraphs:
        if paragraph.get("is_heading"):
            continue
        low = normalised(paragraph.get("text", ""))
        hits = [token for token in tokens if token in low]
        score = len(hits) * 2
        if preferred_headings and _heading_matches(paragraph.get("heading"), preferred_headings):
            score += 2
        if score > best_score:
            best = paragraph
            best_score = score
    return best, best_score


def _evidence_payload(paragraph: Optional[Dict[str, Any]], matched_terms: Sequence[str]) -> List[Dict[str, Any]]:
    if paragraph is None:
        return []
    return [{
        "text": clean_text(paragraph.get("text", ""))[:850],
        "page": paragraph.get("page"),
        "paragraph": paragraph.get("paragraph"),
        "page_paragraph": paragraph.get("page_paragraph"),
        "heading": paragraph.get("heading"),
        "chapter_number": paragraph.get("chapter_number"),
        "is_heading": bool(paragraph.get("is_heading")),
        "source_filename": paragraph.get("source_filename"),
        "document_role": paragraph.get("document_role", "current"),
        "matched_terms": list(matched_terms),
        "adequacy_terms": [],
        "rank_score": len(matched_terms),
    }]


def _status_from_ratio(ratio: float) -> str:
    if ratio >= 0.8:
        return STATUS_MEETS
    if ratio >= 0.4:
        return STATUS_PARTIAL
    return STATUS_MISSING


def _severity(status: str, critical: bool = True) -> str:
    if status == STATUS_MEETS:
        return "minor"
    if critical:
        return "critical" if status == STATUS_MISSING else "major"
    return "major" if status == STATUS_MISSING else "moderate"


def _result(
    *,
    code: str,
    selected_chapter: int,
    item: str,
    status: str,
    comment: str,
    action: str,
    evidence: Optional[List[Dict[str, Any]]] = None,
    headings: Optional[List[str]] = None,
    confidence: float = 0.7,
    critical: bool = True,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "code": code,
        "chapter_key": "ALIGN",
        "chapter_number": selected_chapter,
        "chapter_title": "Cross-Chapter Alignment",
        "section": "Cross-Chapter Alignment",
        "item": item,
        "headings": headings or [],
        "evidence_terms": [],
        "adequacy_terms": [],
        "critical": critical,
        "applicability": ["all"],
        "manual_only": status == STATUS_MANUAL,
        "status": status,
        "status_label": STATUS_LABELS[status],
        "score": STATUS_SCORES[status],
        "confidence": round(confidence, 2),
        "severity": _severity(status, critical),
        "evidence": evidence or [],
        "comment": comment,
        "required_action": action,
        "alignment_details": details or {},
    }


def detected_chapters(paragraphs: Sequence[Dict[str, Any]], filename: str = "") -> Set[int]:
    found = {
        int(paragraph["chapter_number"])
        for paragraph in paragraphs
        if isinstance(paragraph.get("chapter_number"), int)
        and 1 <= int(paragraph["chapter_number"]) <= 20
    }
    low = normalised(filename)
    for match in re.finditer(
        r"(?:chapter|chap|ch)\s*[-_ ]?([1-9]|1[0-9]|20)\b",
        low,
    ):
        found.add(int(match.group(1)))
    return found


def context_coverage_result(
    selected_chapter: int,
    context_documents: Sequence[Dict[str, Any]],
    context_paragraphs: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    expected = set(range(1, selected_chapter))
    detected: Set[int] = set()
    for document in context_documents:
        detected.update(document.get("detected_chapters", []))
    missing = sorted(expected - detected)

    if not context_documents:
        return _result(
            code="AL0",
            selected_chapter=selected_chapter,
            item="All required previous chapters are supplied for alignment review",
            status=STATUS_MISSING,
            comment="No previous chapter was supplied, so cross-chapter consistency cannot be assessed.",
            action=f"Upload Chapters 1 to {selected_chapter - 1} as one composite DOCX/PDF or as separate files.",
            confidence=1.0,
            details={"expected_chapters": sorted(expected), "detected_chapters": [], "missing_chapters": sorted(expected)},
        )

    if not missing:
        status = STATUS_MEETS
        comment = f"The uploaded context includes the expected previous chapters: {', '.join(map(str, sorted(expected)))}."
        action = "Retain the uploaded context files when running the final alignment review."
        confidence = 0.95
    elif detected:
        status = STATUS_PARTIAL
        comment = (
            f"Previous chapter files were supplied, but Chapters {', '.join(map(str, missing))} were not detected. "
            "The alignment review may therefore be incomplete."
        )
        action = f"Add the missing chapter(s): {', '.join(map(str, missing))}, either within the composite file or as separate uploads."
        confidence = 0.78
    else:
        status = STATUS_MANUAL
        comment = (
            "Previous files were supplied, but chapter labels could not be detected reliably. "
            "This can occur when standalone files omit their chapter title."
        )
        action = (
            f"Confirm that the files contain Chapters 1 to {selected_chapter - 1}. Add clear chapter headings or use filenames such as Chapter_1.docx."
        )
        confidence = 0.52

    evidence = []
    if context_paragraphs:
        paragraph = next((p for p in context_paragraphs if p.get("is_heading") and p.get("chapter_number")), context_paragraphs[0])
        evidence = _evidence_payload(paragraph, [])

    return _result(
        code="AL0",
        selected_chapter=selected_chapter,
        item="All required previous chapters are supplied for alignment review",
        status=status,
        comment=comment,
        action=action,
        evidence=evidence,
        confidence=confidence,
        details={
            "expected_chapters": sorted(expected),
            "detected_chapters": sorted(detected),
            "missing_chapters": missing,
            "uploaded_files": [document.get("filename") for document in context_documents],
        },
    )


def _anchor_alignment(
    *,
    code: str,
    selected_chapter: int,
    item: str,
    anchors: Sequence[Dict[str, Any]],
    current_paragraphs: Sequence[Dict[str, Any]],
    preferred_headings: Sequence[str],
    action_prefix: str,
) -> Dict[str, Any]:
    if not anchors:
        return _result(
            code=code,
            selected_chapter=selected_chapter,
            item=item,
            status=STATUS_MANUAL,
            comment="The previous chapters were uploaded, but no clear objectives, questions, or hypotheses could be extracted for comparison.",
            action="Use clear headings for the research objectives, questions and hypotheses. Numbering may be used but is not required. Then rerun the alignment review.",
            headings=list(preferred_headings),
            confidence=0.48,
            details={"anchors_found": 0, "matched": [], "unmatched": []},
        )

    matched: List[str] = []
    unmatched: List[str] = []
    best_evidence = None
    best_terms: List[str] = []
    best_score = -1

    for anchor in anchors:
        text = anchor["text"]
        tokens = _concept_tokens(text)
        evidence, score = _best_current_evidence(current_paragraphs, tokens, preferred_headings)
        minimum = max(1, min(3, round(len(tokens) * 0.35)))
        hits = []
        if evidence is not None:
            low = normalised(evidence.get("text", ""))
            hits = [token for token in tokens if token in low]
        if len(hits) >= minimum:
            matched.append(text)
        else:
            unmatched.append(text)
        if score > best_score:
            best_evidence = evidence
            best_terms = hits or tokens[:3]
            best_score = score

    ratio = len(matched) / len(anchors) if anchors else 0.0
    status = _status_from_ratio(ratio)
    if status == STATUS_MEETS:
        comment = f"The current chapter reflects {len(matched)} of {len(anchors)} extracted objectives, questions, or hypotheses from the previous chapters."
        action = "Retain the alignment and verify that the terminology remains consistent across the final thesis."
    elif status == STATUS_PARTIAL:
        comment = f"The current chapter reflects only {len(matched)} of {len(anchors)} extracted objectives, questions, or hypotheses. Some earlier study commitments are not clearly carried forward."
        action = f"{action_prefix} Review the unmatched items listed in the alignment details and make each one traceable in the current chapter."
    else:
        comment = f"Little or no clear correspondence was found between the current chapter and the {len(anchors)} extracted objectives, questions, or hypotheses."
        action = f"{action_prefix} Reorganise the current chapter so every earlier objective, question, or hypothesis is explicitly addressed."

    return _result(
        code=code,
        selected_chapter=selected_chapter,
        item=item,
        status=status,
        comment=comment,
        action=action,
        evidence=_evidence_payload(best_evidence, best_terms),
        headings=list(preferred_headings),
        confidence=min(0.92, 0.60 + len(anchors) * 0.02),
        details={
            "anchors_found": len(anchors),
            "matched_count": len(matched),
            "unmatched_count": len(unmatched),
            "matched": matched[:12],
            "unmatched": unmatched[:12],
        },
    )


def _analysis_consistency(
    selected_chapter: int,
    context_paragraphs: Sequence[Dict[str, Any]],
    current_paragraphs: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    planned_text = " ".join(
        p.get("text", "") for p in context_paragraphs
        if p.get("chapter_number") == 3 and _heading_matches(p.get("heading"), METHOD_HEADINGS)
    )
    current_text = " ".join(p.get("text", "") for p in current_paragraphs)
    planned = sorted(term for term in ANALYSIS_TERMS if normalised(term) in normalised(planned_text))
    reported = sorted(term for term in planned if normalised(term) in normalised(current_text))

    if not planned:
        status = STATUS_MANUAL
        comment = "No clear analysis techniques were extracted from the uploaded Chapter Three for comparison with Chapter Four."
        action = "State the analysis plan clearly in Chapter Three and verify manually that Chapter Four uses the same techniques."
        confidence = 0.5
    else:
        ratio = len(reported) / len(planned)
        status = _status_from_ratio(ratio)
        missing = sorted(set(planned) - set(reported))
        comment = f"Chapter Four reflects {len(reported)} of {len(planned)} analysis techniques detected in Chapter Three."
        action = (
            "Explain or correct any change in analytical technique. Missing techniques: " + ", ".join(missing)
            if missing else "Retain the consistent analysis terminology and reporting."
        )
        confidence = 0.84

    evidence_paragraph = None
    for paragraph in current_paragraphs:
        low = normalised(paragraph.get("text", ""))
        if any(normalised(term) in low for term in reported or planned):
            evidence_paragraph = paragraph
            break

    return _result(
        code="AL4.2",
        selected_chapter=selected_chapter,
        item="The analyses reported in Chapter Four are consistent with the Chapter Three analysis plan",
        status=status,
        comment=comment,
        action=action,
        evidence=_evidence_payload(evidence_paragraph, reported or planned[:3]),
        headings=RESULT_HEADINGS,
        confidence=confidence,
        details={"planned_analyses": planned, "reported_analyses": reported},
    )


def evaluate_alignment(
    *,
    selected_chapter: int,
    current_paragraphs: Sequence[Dict[str, Any]],
    context_paragraphs: Sequence[Dict[str, Any]],
    context_documents: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if selected_chapter <= 1:
        return []

    results: List[Dict[str, Any]] = [
        context_coverage_result(selected_chapter, context_documents, context_paragraphs)
    ]

    objectives = _section_items(context_paragraphs, OBJECTIVE_HEADINGS)
    questions = _section_items(context_paragraphs, QUESTION_HEADINGS)
    hypotheses = _section_items(context_paragraphs, HYPOTHESIS_HEADINGS)
    anchors = objectives or questions or hypotheses
    if objectives:
        # Add questions and hypotheses only where they contain distinct wording.
        seen = {normalised(item["text"]) for item in objectives}
        anchors = list(objectives)
        for item in list(questions) + list(hypotheses):
            key = normalised(item["text"])
            if key and key not in seen:
                anchors.append(item)
                seen.add(key)

    if selected_chapter == 2:
        results.append(_anchor_alignment(
            code="AL2.1",
            selected_chapter=2,
            item="Chapter Two is organised around the objectives, questions, and hypotheses established in Chapter One",
            anchors=anchors,
            current_paragraphs=current_paragraphs,
            preferred_headings=["empirical review", "theoretical review", "literature review"],
            action_prefix="Create objective-driven literature subsections.",
        ))
        concept_anchors = _section_items(context_paragraphs, VARIABLE_HEADINGS) or anchors
        results.append(_anchor_alignment(
            code="AL2.2",
            selected_chapter=2,
            item="The concepts, variables, and relationships introduced in Chapter One are adequately reviewed in Chapter Two",
            anchors=concept_anchors,
            current_paragraphs=current_paragraphs,
            preferred_headings=["conceptual review", "theoretical review", "empirical review"],
            action_prefix="Add the missing concepts or explain why they are outside the literature review.",
        ))

    elif selected_chapter == 3:
        results.append(_anchor_alignment(
            code="AL3.1",
            selected_chapter=3,
            item="The methodology and analysis plan address every earlier objective, question, and hypothesis",
            anchors=anchors,
            current_paragraphs=current_paragraphs,
            preferred_headings=["research design", "data analysis", "analysis plan", "methodology"],
            action_prefix="Map each objective or hypothesis to its design, data source, measurement, and analysis technique.",
        ))
        concept_anchors = _section_items(context_paragraphs, VARIABLE_HEADINGS) or anchors
        results.append(_anchor_alignment(
            code="AL3.2",
            selected_chapter=3,
            item="Variables and constructs from earlier chapters are operationalised consistently in Chapter Three",
            anchors=concept_anchors,
            current_paragraphs=current_paragraphs,
            preferred_headings=["operationalisation", "operationalization", "measurement of variables", "data collection instrument"],
            action_prefix="Use the same construct names and specify dimensions, indicators, scales, and sources.",
        ))

    elif selected_chapter == 4:
        results.append(_anchor_alignment(
            code="AL4.1",
            selected_chapter=4,
            item="Chapter Four presents findings for every earlier objective, question, and hypothesis",
            anchors=anchors,
            current_paragraphs=current_paragraphs,
            preferred_headings=RESULT_HEADINGS,
            action_prefix="Present the results objective by objective and state each hypothesis decision explicitly.",
        ))
        results.append(_analysis_consistency(4, context_paragraphs, current_paragraphs))

    elif selected_chapter == 5:
        results.append(_anchor_alignment(
            code="AL5.1",
            selected_chapter=5,
            item="The Chapter Five summary and conclusions address every earlier objective, question, and hypothesis",
            anchors=anchors,
            current_paragraphs=current_paragraphs,
            preferred_headings=CONCLUSION_HEADINGS,
            action_prefix="Structure the summary and conclusions objective by objective.",
        ))
        chapter_four = [p for p in context_paragraphs if p.get("chapter_number") == 4]
        findings = _section_items(chapter_four, RESULT_HEADINGS)
        recommendations = _section_items(current_paragraphs, ["recommendations"])
        if findings and recommendations:
            status = STATUS_MANUAL
            comment = (
                f"The uploaded context contains {len(findings)} finding passages and Chapter Five contains "
                f"{len(recommendations)} recommendation passages. Direct traceability requires a finding-by-recommendation comparison."
            )
            action = "Add a recommendation traceability table showing the specific Chapter Four finding supporting each recommendation."
            evidence = _evidence_payload(recommendations[0]["paragraph"], _concept_tokens(recommendations[0]["text"], 4))
            confidence = 0.66
        else:
            status = STATUS_MISSING
            comment = "Clear Chapter Four findings or Chapter Five recommendations were not detected for traceability testing."
            action = "Use clear Findings and Recommendations headings, then link each recommendation to a specific finding."
            evidence = []
            confidence = 0.42
        results.append(_result(
            code="AL5.2",
            selected_chapter=5,
            item="Every recommendation in Chapter Five is traceable to a finding in Chapter Four",
            status=status,
            comment=comment,
            action=action,
            evidence=evidence,
            headings=["recommendations"],
            confidence=confidence,
            details={"finding_passages": len(findings), "recommendation_passages": len(recommendations)},
        ))

    return results


def alignment_score(results: Sequence[Dict[str, Any]]) -> Optional[float]:
    values = [float(row["score"]) for row in results if row.get("score") is not None]
    if not values:
        return None
    return round(sum(values) / len(values) * 100, 1)
