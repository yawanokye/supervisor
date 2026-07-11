from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List

from .document_parser import clean_text, normalised

_STOPWORDS = {
    "chapter", "section", "study", "research", "student", "students", "thesis", "dissertation",
    "results", "result", "method", "methods", "analysis", "discussion", "academic", "review",
    "should", "could", "would", "must", "also", "this", "that", "these", "those", "with", "from",
    "into", "within", "among", "between", "where", "which", "their", "there", "been", "were", "was",
    "have", "has", "will", "does", "than", "about", "using", "used", "based", "need", "required",
}


def _blob(row: Dict[str, Any]) -> str:
    parts: List[str] = []
    for field in (
        "item", "issue_title", "comment", "assessment", "required_action", "section",
        "section_reference", "reference_label", "category", "problematic_quote",
    ):
        parts.append(clean_text(str(row.get(field, ""))))
    for item in row.get("evidence") or []:
        if isinstance(item, dict):
            parts.append(clean_text(str(item.get("text", ""))))
    return normalised(" ".join(parts))


def _source_text(row: Dict[str, Any]) -> str:
    values = [clean_text(row.get("problematic_quote", ""))]
    for item in row.get("evidence") or []:
        if isinstance(item, dict):
            values.append(clean_text(item.get("text", "")))
    return " ".join(value for value in values if value)


def _visible_citation(source: str) -> str:
    match = re.search(r"\([^()]{1,90}(?:19|20)\d{2}[^()]{0,50}\)", source)
    return clean_text(match.group(0)) if match else ""


def _context_terms(row: Dict[str, Any], limit: int = 4) -> List[str]:
    source = _source_text(row)
    if not source:
        return []
    # Prefer repeated, current-study noun-like terms. This deliberately avoids
    # a fixed example bank, which previously leaked an unrelated banking study.
    tokens = re.findall(r"\b[A-Za-z][A-Za-z'-]{3,}\b", source)
    counts = Counter(
        token.lower() for token in tokens
        if token.lower() not in _STOPWORDS and not token.isdigit()
    )
    output: List[str] = []
    for term, _count in counts.most_common(20):
        if term in output:
            continue
        output.append(term)
        if len(output) >= limit:
            break
    return output


def _join_terms(terms: List[str]) -> str:
    if not terms:
        return "the central constructs"
    if len(terms) == 1:
        return terms[0]
    if len(terms) == 2:
        return f"{terms[0]} and {terms[1]}"
    return ", ".join(terms[:-1]) + f", and {terms[-1]}"


def context_specific_example(row: Dict[str, Any]) -> str:
    """Return a current-document example or no example.

    The function never imports named organisations, variables or settings from
    another submission. It uses only the marked passage and its evidence.
    """
    text = _blob(row)
    source = _source_text(row)
    if not text:
        return ""
    terms = _context_terms(row)
    joined = _join_terms(terms[:3])

    if any(term in text for term in ("citation", "reference list", "source attribution", "reference")):
        citation = _visible_citation(source)
        if citation:
            return f"retain {citation} only once, place it correctly in the sentence, and ensure that its full bibliographic entry appears in the reference list"
        return "place each in-text citation correctly, remove duplicate citation clusters, and match every retained citation to one complete reference-list entry"

    if any(term in text for term in ("population", "unit of analysis", "case setting", "study boundary", "scope", "delimitation")):
        return "state one consistent population, unit of analysis, institutional or geographical boundary, and time period, then use that same boundary in the title, purpose, methods, results and conclusions"

    if any(term in text for term in ("theoretical", "conceptual framework", "conceptual anchor", "construct role", "hypothesis")):
        return f"state how {joined} are expected to relate, identify the theory that explains the relationship, and show how that logic leads to the relevant objective or hypothesis"

    if any(term in text for term in ("problem statement", "research gap", "local evidence", "magnitude", "empirical evidence")):
        return "support the stated problem with a verified statistic, institutional record, policy report or peer-reviewed study from the actual study context, then explain what remains unresolved"

    if any(term in text for term in ("objective", "research question", "alignment", "purpose")):
        quote = clean_text(row.get("problematic_quote", ""))
        if quote:
            return f"revise the wording around “{quote[:120]}” so that one objective, one question or hypothesis, one analysis and one reported finding address the same relationship"
        return "map each objective to one research question or hypothesis, the data required, the analysis used, the corresponding result and the conclusion drawn"

    if any(term in text for term in ("r squared", "coefficient", "p value", "f statistic", "t statistic", "confidence interval", "statistical", "regression", "anova", "sem", "moderation", "mediation")):
        return "reproduce the coefficient or effect estimate, standard error, test statistic, degrees of freedom where applicable, p-value, confidence interval and model-fit information directly from the same original output"

    if any(term in text for term in ("qualitative", "theme", "coding", "quotation", "trustworthiness")):
        return "show how the code or category developed into the reported theme, support the interpretation with representative participant evidence, and explain any negative or divergent case"

    if any(term in text for term in ("discussion", "interpretation", "unexpected", "prior studies")):
        return f"explain what the finding about {joined} means, compare it with the theory and directly relevant prior evidence, and discuss a plausible explanation for agreement, contradiction or non-significance"

    if any(term in text for term in ("contribution", "significance", "implication", "recommendation")):
        return "separate the theoretical, empirical, methodological and practical contribution actually supported by the findings, and link each recommendation to a specific result"

    if any(term in text for term in ("definition of terms", "operational definition", "construct")):
        return f"define {joined} using the dimensions and indicators applied in the instrument, coding framework or analysis"

    if any(term in text for term in ("academic writing", "grammar", "language", "organisation of the study", "organization of the study")):
        return "replace conversational wording with a precise scholarly sentence, retain the intended meaning, and correct grammar, punctuation and citation placement without changing the evidence"

    return ""


def enrich_finding_row(row: Dict[str, Any]) -> Dict[str, Any]:
    output = dict(row)
    if not clean_text(output.get("illustrative_guidance", "")):
        output["illustrative_guidance"] = context_specific_example(output)
    return output
