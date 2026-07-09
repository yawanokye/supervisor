from __future__ import annotations

import re
from typing import Any, Dict

from .document_parser import clean_text, normalised


def _blob(row: Dict[str, Any]) -> str:
    parts = []
    for field in (
        "item",
        "issue_title",
        "comment",
        "assessment",
        "required_action",
        "section",
        "section_reference",
        "reference_label",
        "category",
        "problematic_quote",
    ):
        parts.append(clean_text(str(row.get(field, ""))))
    for item in row.get("evidence") or []:
        if isinstance(item, dict):
            parts.append(clean_text(str(item.get("text", ""))))
    return normalised(" ".join(parts))


def _has_case_context(text: str) -> bool:
    return any(term in text for term in ("assinman", "rural bank", "rural banks", "commercial bank", "fraud", "internal control"))


def context_specific_example(row: Dict[str, Any]) -> str:
    """Return a safe, context-aware example for student guidance.

    The examples are deliberately non-inventive. They use visible study terms
    and point the student to the type of evidence or wording needed without
    fabricating statistics, institutional facts or source details.
    """
    text = _blob(row)
    if not text:
        return ""

    # Citation and reference traceability in the sample fraud/internal-control chapter.
    if any(term in text for term in ("reference list", "visible in text citation", "source attribution", "citation spacing", "citation", "reference")):
        if _has_case_context(text):
            return (
                "clean entries such as 'government (Alnaa & Matey, 2024)' by inserting the space before the citation, removing repeated citations such as a duplicated Alnaa and Matey entry, and adding complete reference-list details for every source retained"
            )
        return "insert missing spaces before parenthetical citations, remove duplicate citation clusters, and add complete reference-list entries for every source retained"

    # Population/case boundary drift.
    if any(term in text for term in ("population", "case setting", "commercial banks", "rural banks", "unit of analysis", "population drift")):
        return (
            "state whether the study is a case study of Assinman Rural Bank PLC within Ghana's rural banking sector, then use that same boundary in the background, problem statement, objectives, questions, scope and significance"
        )

    # Fraud triangle and internal-control logic.
    if any(term in text for term in ("fraud triangle", "pressure", "opportunity", "rationalization", "rationalisation", "theoretical", "conceptual anchor", "conceptual framework")):
        return (
            "link pressure, opportunity and rationalisation to fraud incidence, then show how controls such as segregation of duties, authorisation, access controls and monitoring mainly reduce opportunity within the bank"
        )

    # Local evidence / problem evidence.
    if any(term in text for term in ("empirical or policy evidence", "local evidence", "problem statement", "research gap", "concrete evidence", "magnitude", "scale")):
        if _has_case_context(text):
            return (
                "support the problem with verifiable Ghana rural-banking evidence, such as Bank of Ghana, ARB Apex Bank, audited annual reports or documented internal-control/fraud-risk records from the institution where access is permitted"
            )
        return "support the problem with verifiable sector, institutional or policy evidence rather than relying only on broad statements that the topic is important"

    # Contribution/significance.
    if any(term in text for term in ("contribution", "significance", "theory practice policy", "beneficiaries")):
        if _has_case_context(text):
            return (
                "separate the likely theoretical contribution to fraud-triangle/internal-control literature, the practical contribution for Assinman Rural Bank PLC, and the policy relevance for rural-bank supervision or internal-control guidance"
            )
        return "separate theoretical, practical and policy contributions and state what the study adds beyond proving that the topic is useful"

    # Limitations / generalisation.
    if any(term in text for term in ("limitation", "generalisation", "generalization", "case study", "transferability")):
        return (
            "replace a broad generalisation claim with a bounded statement such as contextual or analytical transferability to similar rural banks unless the sampling and design support statistical generalisation"
        )

    # Definition of terms / constructs.
    if any(term in text for term in ("definition of terms", "core constructs", "construct labels", "construct", "terms are not evident")):
        if _has_case_context(text):
            return (
                "define internal controls, fraud detection, fraud prevention, fraud incidence, pressure, opportunity and rationalisation in measurable terms that match the questionnaire or interview guide"
            )
        return "define each core construct with its boundary, dimensions and measurable indicators so the methodology can operationalise it consistently"

    # Objectives/questions and design language.
    if any(term in text for term in ("objective", "research question", "quantitative", "impact", "effect", "causal", "explanatory", "descriptive")):
        return (
            "if the design is a cross-sectional survey, use associational wording such as 'relationship' or 'association' unless the methodology can justify causal terms such as effect or impact"
        )

    # Scope/delimitation.
    if any(term in text for term in ("scope", "delimitation", "delimitation of the study")):
        return (
            "state the sector, case organisation, respondent group, geographical boundary, time period, included constructs and exclusions so the reader can see exactly what the study covers"
        )

    # Academic writing and organisation.
    if any(term in text for term in ("academic writing", "grammar", "language", "organisation of the study", "organization of the study")):
        return (
            "edit phrases such as 'what the study is all about' into formal thesis language and correct grammatical errors such as subject-verb agreement before resubmission"
        )

    return ""


def enrich_finding_row(row: Dict[str, Any]) -> Dict[str, Any]:
    output = dict(row)
    if not clean_text(output.get("illustrative_guidance", "")):
        output["illustrative_guidance"] = context_specific_example(output)
    return output
