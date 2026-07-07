from __future__ import annotations

import os
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from .document_parser import clean_text, normalised
from .review_rules import RULES, STATUS_MANUAL, STATUS_MEETS, STATUS_MISSING, STATUS_NA, STATUS_PARTIAL, is_applicable
from .supervisory_accuracy_guard import paragraph_id, source_section


def _enabled() -> bool:
    return os.getenv("VPROF_DETERMINISTIC_SUPERVISORY_CHECKLIST", "true").strip().lower() not in {"0", "false", "no", "off"}


def _contains_any(text: str, terms: Iterable[str]) -> List[str]:
    low = normalised(text)
    hits: List[str] = []
    for term in terms:
        token = normalised(str(term or ""))
        if token and token in low:
            hits.append(str(term))
    return list(dict.fromkeys(hits))


def _degree_key(level: Any) -> str:
    value = normalised(str(level or "")).replace("-", " ")
    if value == "phd" or value.startswith("doctor of philosophy"):
        return "phd"
    if "professional doctorate" in value or value.startswith("doctoral") or value.startswith("doctor of "):
        return "professional_doctorate"
    if "non research master" in value or "nonresearch master" in value:
        return "non_research_masters"
    if "research master" in value or "research masters" in value or "mphil" in value:
        return "research_masters"
    if "master" in value:
        return "non_research_masters"
    return "bachelors"


def _chapter_scope(paragraphs: Sequence[Dict[str, Any]]) -> Set[int]:
    chapters = {
        int(row.get("chapter_number"))
        for row in paragraphs
        if isinstance(row.get("chapter_number"), int)
    }
    return chapters


def _rules_for_scope(
    paragraphs: Sequence[Dict[str, Any]],
    *,
    academic_level: Any = "",
    research_approach: Any = "",
) -> List[Dict[str, Any]]:
    chapters = _chapter_scope(paragraphs)
    full_thesis = {1, 2, 3, 4, 5}.issubset(chapters)
    selected_chapter = min(chapters) if len(chapters) == 1 else None

    output: List[Dict[str, Any]] = []
    for rule in RULES:
        chapter = int(rule.get("chapter_number") or 0)
        code = str(rule.get("code") or "")
        if not is_applicable(rule, str(research_approach or "all")):
            continue
        if chapter == 0:
            # Overall coherence/final-readiness items are meaningful for a full
            # thesis. For a Chapter One upload, keep only A1 and A2 because the
            # evidence is in Chapter One; do not invent comments about Chapters
            # Four or Five when they were not uploaded.
            if full_thesis or (selected_chapter == 1 and code in {"A1", "A2"}):
                output.append(rule)
            continue
        if full_thesis or chapter in chapters:
            output.append(rule)
    return output


def _section_rows(paragraphs: Sequence[Dict[str, Any]], rule: Dict[str, Any]) -> List[Dict[str, Any]]:
    chapter = int(rule.get("chapter_number") or 0)
    headings = [normalised(h) for h in rule.get("headings") or [] if normalised(h)]
    rows = [row for row in paragraphs if row.get("document_role", "current") == "current"]
    if chapter:
        chapter_rows = [row for row in rows if row.get("chapter_number") == chapter]
        if chapter_rows:
            rows = chapter_rows

    if not headings:
        return rows

    matched = []
    for row in rows:
        section = normalised(source_section(row))
        text = normalised(clean_text(row.get("text", ""))) if row.get("is_heading") else ""
        if any(h in section or section in h or h in text or text in h for h in headings if h):
            matched.append(row)
    return matched or rows


def _anchor_row(paragraphs: Sequence[Dict[str, Any]], rule: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    chapter = int(rule.get("chapter_number") or 0)
    headings = [normalised(h) for h in rule.get("headings") or [] if normalised(h)]
    rows = [row for row in paragraphs if row.get("document_role", "current") == "current"]
    if chapter:
        chapter_rows = [row for row in rows if row.get("chapter_number") == chapter]
        if chapter_rows:
            rows = chapter_rows

    # Prefer a real heading. Never fall back to title-page material when the
    # required section cannot be found.
    for row in rows:
        text = normalised(clean_text(row.get("text", "")))
        if row.get("is_heading") and any(h in text or text in h for h in headings):
            return row
    for row in rows:
        section = normalised(source_section(row))
        if any(h in section or section in h for h in headings):
            return row
    if chapter and rows:
        # Use the first substantive row inside the relevant chapter only.
        for row in rows:
            if len(clean_text(row.get("text", "")).split()) >= 4:
                return row
    return None


def _status_for_rule(rows: Sequence[Dict[str, Any]], rule: Dict[str, Any]) -> Dict[str, Any]:
    evidence_terms = list(rule.get("evidence_terms") or [])
    adequacy_terms = list(rule.get("adequacy_terms") or [])
    justification_terms = ["because", "therefore", "justified", "appropriate", "rationale", "selected because", "was chosen", "was adopted"]
    scored: List[Dict[str, Any]] = []
    max_hits = 0
    max_adequacy = 0

    for row in rows:
        text = clean_text(row.get("text", ""))
        hits = _contains_any(text, evidence_terms)
        if not hits:
            continue
        adequacy = _contains_any(text, adequacy_terms + justification_terms)
        score = len(hits) * 2 + len(adequacy)
        scored.append({"row": row, "hits": hits, "adequacy": adequacy, "score": score})
        max_hits = max(max_hits, len(hits))
        max_adequacy = max(max_adequacy, len(adequacy))

    scored.sort(key=lambda item: item["score"], reverse=True)
    evidence_rows = [item["row"] for item in scored[:4]]

    if rule.get("manual_only"):
        status = STATUS_MANUAL if evidence_rows else STATUS_MISSING
    elif max_hits == 0:
        status = STATUS_MISSING
    else:
        target = min(3, max(1, len(set(evidence_terms)) // 3))
        needs_adequacy = bool(adequacy_terms)
        if max_hits >= target and (not needs_adequacy or max_adequacy >= 1):
            status = STATUS_MEETS
        else:
            status = STATUS_PARTIAL
    return {"status": status, "evidence_rows": evidence_rows, "max_hits": max_hits, "max_adequacy": max_adequacy}


def _category_for_code(code: str) -> str:
    if code.startswith("A"):
        return "cross_section_coherence"
    if code.startswith("B1"):
        return "research_gap_and_problem"
    if code.startswith("B2"):
        return "research_gap_and_problem"
    if code.startswith("B3"):
        return "objectives_questions_hypotheses"
    if code.startswith("B4"):
        return "chapter_structure"
    if code.startswith("C1"):
        return "theoretical_grounding"
    if code.startswith("C2"):
        return "critical_analysis"
    if code.startswith("D12"):
        return "ethics_and_integrity"
    if code.startswith("D"):
        return "methodological_rigour"
    if code.startswith("E"):
        return "results_and_interpretation"
    if code.startswith("F"):
        return "conclusions_and_recommendations"
    if code.startswith("G2"):
        return "citations_and_sources"
    if code.startswith("G"):
        return "chapter_structure"
    if code.startswith("GUIDE-CH2"):
        return "critical_analysis"
    if code.startswith("GUIDE-CH3"):
        return "methodological_rigour"
    if code.startswith("GUIDE-CH4"):
        return "results_and_interpretation"
    if code.startswith("GUIDE-CH5"):
        return "conclusions_and_recommendations"
    return "other"


def _severity(rule: Dict[str, Any], status: str, degree: str) -> str:
    if status in {STATUS_MEETS, STATUS_NA}:
        return "minor"
    critical = bool(rule.get("critical")) or str(rule.get("code", "")).startswith(("A", "B2", "B3", "D1", "D2", "D4", "D6", "D10", "D11", "D12"))
    if critical and status == STATUS_MISSING:
        return "critical" if degree in {"research_masters", "professional_doctorate", "phd"} else "major"
    if critical:
        return "major"
    if status == STATUS_MISSING:
        return "major"
    return "moderate"


def _section_label(rule: Dict[str, Any], anchor: Optional[Dict[str, Any]]) -> str:
    if anchor is not None and source_section(anchor):
        return source_section(anchor)
    section = clean_text(rule.get("section", ""))
    return section or clean_text(rule.get("chapter_title", "")) or "Document section"


def _quote(anchor: Optional[Dict[str, Any]], status: str) -> str:
    if anchor is None:
        return ""
    text = clean_text(anchor.get("text", ""))
    if status == STATUS_MISSING and anchor.get("is_heading"):
        return text[:220]
    return text[:260]


def _issue_text(rule: Dict[str, Any], status: str, section: str, degree: str) -> Dict[str, str]:
    item = clean_text(rule.get("item", ""))
    if status == STATUS_MISSING:
        title = f"Required thesis element is not evident: {item}"
        assessment = f"The uploaded text does not provide sufficient evidence that {item.lower()}."
        consequence = "This creates a supervisory risk because the thesis may appear complete in form while a required academic element remains absent or unverified."
        action = f"Add a clear, evidence-backed treatment of this requirement in {section}, and make the location traceable by page and paragraph before resubmission."
    elif status == STATUS_MANUAL:
        title = f"Required thesis element needs explicit traceability: {item}"
        assessment = f"Related wording appears in the uploaded text, but the automated review cannot confirm that {item.lower()} without cross-checking other sections."
        consequence = "The thesis may contain the required content, but its traceability across chapters is not yet defensible enough for a supervisor or examiner to verify quickly."
        action = f"Make the linkage explicit in {section}, or add a cross-reference showing exactly where the supporting evidence appears."
    else:
        title = f"Required thesis element is only partly demonstrated: {item}"
        assessment = f"The uploaded text touches on this requirement, but it does not fully demonstrate that {item.lower()}."
        consequence = "A partial treatment may pass a surface checklist but still leave the argument, method or chapter logic underdeveloped at the declared level."
        action = f"Revise {section} so the requirement is not merely mentioned but explained, justified and linked to the study problem, objectives or methods as appropriate."

    if degree == "research_masters":
        consequence += " At MPhil level, this weakness is material because the work is expected to show independent research judgement, conceptual clarity and methodological rigour."
    elif degree == "phd":
        consequence += " At PhD level, this weakness is material because the thesis must support an original and defensible contribution to knowledge."
    elif degree == "professional_doctorate":
        consequence += " At professional doctorate level, this weakness is material because the study must connect doctoral scholarship to a defensible contribution to practice or policy."
    return {"title": title, "assessment": assessment, "consequence": consequence, "action": action}


def _make_issue_from_rule(rule: Dict[str, Any], status: str, evidence_rows: List[Dict[str, Any]], anchor: Optional[Dict[str, Any]], degree: str) -> Optional[Dict[str, Any]]:
    if status in {STATUS_MEETS, STATUS_NA}:
        return None
    evidence = evidence_rows[:] or ([anchor] if anchor is not None else [])
    evidence_ids = [paragraph_id(row) for row in evidence if row is not None]
    if not evidence_ids:
        return None
    section = _section_label(rule, anchor or evidence[0])
    text = _issue_text(rule, status, section, degree)
    return {
        "finding_id": f"DSC-{rule.get('code')}",
        "category": _category_for_code(str(rule.get("code") or "")),
        "section": section,
        "issue_title": text["title"],
        "severity": _severity(rule, status, degree),
        "confidence": 0.94 if status == STATUS_MISSING else (0.82 if status == STATUS_PARTIAL else 0.74),
        "evidence_paragraph_ids": list(dict.fromkeys(evidence_ids))[:8],
        "problematic_quote": _quote(anchor or evidence[0], status),
        "assessment": text["assessment"],
        "academic_consequence": text["consequence"],
        "required_action": text["action"],
        "illustrative_guidance": "",
        "guidance_type": "structural_guidance",
        "source_verification_required": False,
        "context_guard_adjusted": False,
        "checklist_code": rule.get("code"),
        "checklist_item": rule.get("item"),
        "verification_status": "deterministic_supervisory_checklist",
    }


# High-level expectations from the dissertation/thesis guideline. They are not a
# substitute for the official checklist; they cover requirements that the
# checklist compresses but the guideline states explicitly.
GUIDELINE_EXPECTATIONS: List[Dict[str, Any]] = [
    {
        "code": "GUIDE-THESIS-FRAMEWORK",
        "chapter_number": 2,
        "section": "Theoretical/Conceptual Framework",
        "item": "The thesis declares a theoretical or conceptual framework and uses the literature review to address its elements",
        "headings": ["theoretical framework", "conceptual framework", "conceptual base"],
        "evidence_terms": ["theoretical framework", "conceptual framework", "model", "theory", "variable", "relationship"],
        "adequacy_terms": ["objective", "hypothesis", "framework", "relationship", "link"],
        "critical": True,
        "applicability": ["research_masters", "professional_doctorate", "phd", "quantitative", "mixed", "sem", "econometrics"],
    },
    {
        "code": "GUIDE-CH2-CRITIQUE-NOT-REPORT",
        "chapter_number": 2,
        "section": "Literature Review",
        "item": "The literature review critiques and synthesises the literature rather than merely reporting studies",
        "headings": ["literature review", "empirical review", "theoretical review"],
        "evidence_terms": ["however", "whereas", "contrary", "in contrast", "limitation", "weakness", "gap", "synthesis", "inconsistent", "contradict"],
        "adequacy_terms": ["gap", "limitation", "synthesis", "contradict", "inconsistent"],
        "critical": True,
        "applicability": ["research_masters", "professional_doctorate", "phd"],
    },
    {
        "code": "GUIDE-CH3-DESIGN-ALTERNATIVES",
        "chapter_number": 3,
        "section": "Research Design",
        "item": "The research design is justified against alternatives and linked to the objectives, questions or hypotheses",
        "headings": ["research design", "research methodology", "research methods"],
        "evidence_terms": ["research design", "alternative", "quantitative", "qualitative", "mixed", "justified", "objective", "research question", "hypothesis"],
        "adequacy_terms": ["justified", "appropriate", "alternative", "objective", "hypothesis"],
        "critical": True,
        "applicability": ["all"],
    },
    {
        "code": "GUIDE-CH3-ANALYSIS-BY-QUESTION",
        "chapter_number": 3,
        "section": "Data Processing and Analysis",
        "item": "Data analysis is explained for each research question or hypothesis and the statistical tools are justified",
        "headings": ["data analysis", "data processing and analysis", "method of data analysis"],
        "evidence_terms": ["research question", "hypothesis", "objective", "regression", "correlation", "anova", "thematic", "statistical", "analysis"],
        "adequacy_terms": ["justified", "appropriate", "objective", "hypothesis", "research question"],
        "critical": True,
        "applicability": ["all"],
    },
    {
        "code": "GUIDE-CH4-THEORY-DISCUSSION",
        "chapter_number": 4,
        "section": "Results and Discussion",
        "item": "Findings are interpreted in relation to theory, previous studies and practical implications",
        "headings": ["results and discussion", "discussion of findings", "discussion"],
        "evidence_terms": ["theory", "theoretical", "previous studies", "consistent with", "contrary to", "implication", "finding"],
        "adequacy_terms": ["theory", "previous", "implication", "contrary", "consistent"],
        "critical": True,
        "applicability": ["all"],
    },
    {
        "code": "GUIDE-CH5-RECOMMENDATIONS-FINDINGS",
        "chapter_number": 5,
        "section": "Recommendations",
        "item": "Recommendations are specific and logically derived from the study findings, not from common sense alone",
        "headings": ["recommendations", "summary conclusions and recommendations", "conclusions and recommendations"],
        "evidence_terms": ["finding", "based on", "recommend", "should", "policy", "manager", "stakeholder"],
        "adequacy_terms": ["finding", "based on", "specific", "stakeholder"],
        "critical": True,
        "applicability": ["all"],
    },
]


def guideline_rules_for_scope(paragraphs: Sequence[Dict[str, Any]], degree: str, research_approach: str) -> List[Dict[str, Any]]:
    chapters = _chapter_scope(paragraphs)
    full_thesis = {1, 2, 3, 4, 5}.issubset(chapters)
    output: List[Dict[str, Any]] = []
    for rule in GUIDELINE_EXPECTATIONS:
        chapter = int(rule.get("chapter_number") or 0)
        allowed = [normalised(x) for x in rule.get("applicability", ["all"])]
        if "all" not in allowed and normalised(degree) not in allowed and normalised(research_approach) not in allowed:
            continue
        if full_thesis or chapter in chapters:
            output.append(rule)
    return output


def deterministic_supervisory_checklist_issues(
    paragraphs: Sequence[Dict[str, Any]],
    *,
    academic_level: Any = "",
    research_approach: Any = "",
    max_issues: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Build evidence-anchored issues from the attached supervisory checklist.

    This is intentionally deterministic. It does not write content and does not
    depend on model judgement. It simply checks whether the uploaded section or
    thesis visibly demonstrates each required supervisory item, then creates a
    concise issue for missing/partial/manual items. These issues are later passed
    through the same factual, public-quality and DOCX anchoring gates as model
    findings.
    """
    if not _enabled():
        return []
    current = [row for row in paragraphs if row.get("document_role", "current") == "current"]
    if not current:
        return []
    degree = _degree_key(academic_level)
    approach = normalised(str(research_approach or "all")) or "all"
    rules = _rules_for_scope(current, academic_level=academic_level, research_approach=approach)
    rules.extend(guideline_rules_for_scope(current, degree, approach))

    issues: List[Dict[str, Any]] = []
    for rule in rules:
        rows = _section_rows(current, rule)
        status_data = _status_for_rule(rows, rule)
        status = status_data["status"]
        if status == STATUS_MEETS or status == STATUS_NA:
            continue
        # Do not flood short chapter uploads with low-priority generic final
        # readiness items. Let the model and section assessments handle those.
        code = str(rule.get("code") or "")
        if code.startswith("G") and len(_chapter_scope(current)) < 5:
            continue
        anchor = _anchor_row(current, rule)
        issue = _make_issue_from_rule(rule, status, status_data["evidence_rows"], anchor, degree)
        if issue:
            issues.append(issue)

    severity_rank = {"critical": 0, "major": 1, "moderate": 2, "minor": 3}
    issues.sort(key=lambda row: (severity_rank.get(row.get("severity", "minor"), 9), str(row.get("finding_id", ""))))
    if max_issues is None:
        if degree in {"research_masters", "professional_doctorate", "phd"}:
            max_issues = int(os.getenv("VPROF_DETERMINISTIC_CHECKLIST_MAX_ISSUES", "36"))
        else:
            max_issues = int(os.getenv("VPROF_DETERMINISTIC_CHECKLIST_MAX_ISSUES", "24"))
    return issues[: max(0, int(max_issues))]
