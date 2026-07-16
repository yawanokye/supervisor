from __future__ import annotations

import os
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from .document_parser import clean_text, normalised
from .review_rules import RULES, STATUS_MANUAL, STATUS_MEETS, STATUS_MISSING, STATUS_NA, STATUS_PARTIAL, is_applicable
from .supervisory_accuracy_guard import paragraph_id, source_section
from .study_semantics import (
    contains_uncited_empirical_count,
    has_traceable_context_evidence,
    omitted_objective_focuses,
)


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




def _degree_expectation_phrase(degree: str) -> str:
    if os.getenv("VPROF_INCLUDE_DEGREE_LABEL_IN_COMMENTS", "false").strip().lower() in {"0", "false", "no", "off"}:
        return ""
    return {
        "bachelors": "At Bachelor’s level, this weakness matters because the work must show basic research coherence, accurate presentation and correct application of method.",
        "non_research_masters": "At Non-Research Master’s level, this weakness matters because the work must show applied problem clarity, credible evidence and defensible professional recommendations.",
        "research_masters": "At MPhil level, this weakness matters because the work must show independent research judgement, conceptual clarity and methodological rigour.",
        "professional_doctorate": "At Professional Doctorate level, this weakness matters because the work must connect doctoral scholarship to a defensible contribution to practice or policy.",
        "phd": "At PhD level, this weakness matters because the thesis must support an original and defensible contribution to knowledge.",
    }.get(degree, "At the declared academic level, this weakness matters because the work must meet the appropriate scholarly standard.")


def _degree_theory_requirement(degree: str) -> str:
    return {
        "bachelors": "The chapter should show at least a clear conceptual understanding of the main variables or ideas.",
        "non_research_masters": "The chapter should show the applied or professional logic that connects the problem, evidence and proposed analysis.",
        "research_masters": "The chapter should prepare the reader for a defensible theoretical or conceptual framework.",
        "professional_doctorate": "The chapter should connect the professional problem to a defensible scholarly and practice-based framework.",
        "phd": "The chapter should signal the theoretical or conceptual position from which an original contribution to knowledge will be developed.",
    }.get(degree, "The chapter should explain the conceptual logic of the study.")

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
        if any(section == h or text == h or _contains_token_sequence(section, h) or _contains_token_sequence(text, h) for h in headings if h):
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
        if row.get("is_heading") and any(text == h or _contains_token_sequence(text, h) for h in headings):
            return row
    for row in rows:
        section = normalised(source_section(row))
        if any(section == h or _contains_token_sequence(section, h) for h in headings):
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
        title = f"{item} is missing or not clearly reported"
        assessment = f"The study does not clearly report {item.lower()} in {section}."
        consequence = "The reader cannot judge whether this requirement has been addressed or how it supports the study."
        action = f"Add the missing information in {section} and explain it using the actual design, evidence and terminology of the study."
    elif status == STATUS_MANUAL:
        title = f"{item} is not clearly linked to the rest of the study"
        assessment = f"The study refers to this point, but the link to the relevant objectives, methods, results or conclusions is not clear."
        consequence = "The reader should be able to trace the point across the chapters without having to infer the connection."
        action = f"State the linkage directly in {section} or add a clear cross-reference to the section where it is demonstrated."
    else:
        title = f"{item} is not fully explained"
        assessment = f"The study mentions this point in {section}, but the explanation, justification or application is incomplete."
        consequence = "The partial treatment weakens the logic of the chapter and makes the relevant decision difficult to assess."
        action = f"Develop the point in {section} and show how it relates to the study problem, objectives, method or evidence, as appropriate."

    consequence += " " + _degree_expectation_phrase(degree)
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




def _group_by_section(paragraphs: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in paragraphs:
        if row.get("document_role", "current") != "current":
            continue
        section = normalised(source_section(row) or row.get("heading") or "")
        if not section:
            continue
        grouped.setdefault(section, []).append(row)
    return grouped


def _section_tokens(value: str) -> List[str]:
    tokens = re.findall(r"[a-z0-9]+", normalised(value))
    # Light stemming prevents singular/plural heading mismatches, but keeps
    # "limitation" and "delimitation" distinct.
    return [token[:-1] if len(token) > 5 and token.endswith("s") else token for token in tokens]


def _contains_token_sequence(container: str, phrase: str) -> bool:
    c_tokens = _section_tokens(container)
    p_tokens = _section_tokens(phrase)
    if not c_tokens or not p_tokens or len(p_tokens) > len(c_tokens):
        return False
    return any(c_tokens[i:i + len(p_tokens)] == p_tokens for i in range(len(c_tokens) - len(p_tokens) + 1))


def _find_section_rows(grouped: Dict[str, List[Dict[str, Any]]], *terms: str) -> List[Dict[str, Any]]:
    wanted = [normalised(term) for term in terms if normalised(term)]
    # Exact match first.
    for term in wanted:
        for section, rows in grouped.items():
            if section == term:
                return rows
    # Token-sequence match next. This avoids matching "limitations" as
    # "delimitations", which caused placeholder checks to inspect the wrong
    # section.
    for term in wanted:
        for section, rows in grouped.items():
            if _contains_token_sequence(section, term):
                return rows
    return []


def _section_plain(rows: Sequence[Dict[str, Any]]) -> str:
    return "\n".join(clean_text(row.get("text", "")) for row in rows if clean_text(row.get("text", "")))


def _first_substantive(rows: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for row in rows:
        if not row.get("is_heading") and len(clean_text(row.get("text", "")).split()) >= 4:
            return row
    for row in rows:
        if len(clean_text(row.get("text", "")).split()) >= 1:
            return row
    return None


def _issue(
    *,
    code: str,
    section: str,
    title: str,
    assessment: str,
    consequence: str,
    action: str,
    anchor: Optional[Dict[str, Any]],
    category: str,
    severity: str = "major",
    confidence: float = 0.96,
    quote: str = "",
) -> Optional[Dict[str, Any]]:
    if anchor is None:
        return None
    pid = paragraph_id(anchor)
    if not pid:
        return None
    return {
        "finding_id": f"DSC-HARD-{code}",
        "category": category,
        "section": section,
        "issue_title": clean_text(title),
        "severity": severity,
        "confidence": confidence,
        "evidence_paragraph_ids": [pid],
        "problematic_quote": clean_text(quote or anchor.get("text", ""))[:260],
        "assessment": clean_text(assessment),
        "academic_consequence": clean_text(consequence),
        "required_action": clean_text(action),
        "illustrative_guidance": "",
        "guidance_type": "deterministic_supervisory_checklist",
        "source_verification_required": False,
        "context_guard_adjusted": False,
        "checklist_code": code,
        "checklist_item": title,
        "verification_status": "hard_deterministic_supervisory_checklist",
    }


def _citation_tokens(text: str) -> Set[str]:
    tokens: Set[str] = set()
    for match in re.finditer(r"\(([A-Z][A-Za-z'’\-]+(?:\s+et\s+al\.)?|[A-Z][A-Za-z'’\-]+\s*&\s*[A-Z][A-Za-z'’\-]+)[^)]*?,\s*(?:19|20)\d{2}\)", text):
        first = re.split(r"\s*&\s*|\s+et\s+al\.", match.group(1))[0]
        tokens.add(normalised(first))
    return tokens


def _reference_author_tokens(text: str) -> Set[str]:
    refs_started = False
    tokens: Set[str] = set()
    for line in text.splitlines():
        low = normalised(line)
        if low == "references":
            refs_started = True
            continue
        if refs_started:
            m = re.match(r"\s*([A-Z][A-Za-z'’\-]+),", line)
            if m:
                tokens.add(normalised(m.group(1)))
    return tokens




def hard_chapter_one_supervisory_issues(
    paragraphs: Sequence[Dict[str, Any]],
    *,
    academic_level: Any = "",
) -> List[Dict[str, Any]]:
    """Evidence-anchored Chapter One checks that must not depend on model recall.

    These checks implement the most examinable Chapter One requirements from the
    attached self-evaluation checklist and thesis guideline. They are intentionally
    conservative, but they catch objective/purpose drift, proposal-stage tense,
    missing time delimitations, definition weaknesses, citation mismatches and
    MPhil-level theory/gap expectations.
    """
    current = [row for row in paragraphs if row.get("document_role", "current") == "current"]
    chapters = _chapter_scope(current)
    if 1 not in chapters:
        return []
    degree = _degree_key(academic_level)
    grouped = _group_by_section(current)
    background = _find_section_rows(grouped, "background to the study", "background of the study")
    problem = _find_section_rows(grouped, "statement of the problem", "problem statement")
    purpose = _find_section_rows(grouped, "purpose of the study", "aim of the study", "general objective", "general objectives", "general aim", "primary objective")
    objectives = _find_section_rows(grouped, "research objectives", "objectives of the study")
    questions = _find_section_rows(grouped, "research questions", "research question")
    significance = _find_section_rows(grouped, "significance of the study")
    limitations = _find_section_rows(grouped, "limitations of the study", "limitation of the study")
    delimitations = _find_section_rows(grouped, "delimitation of the study", "delimitations of the study", "scope of the study")
    definitions = _find_section_rows(grouped, "definition of terms", "operational definition of terms")
    organisation = _find_section_rows(grouped, "organisation of the study", "organization of the study")
    references = _find_section_rows(grouped, "references")
    first_chapter_paragraph = min((int(row.get("paragraph")) for row in current if row.get("chapter_number") == 1 and row.get("paragraph")), default=10**9)
    title_rows = [
        row for row in current
        if not row.get("chapter_number")
        and int(row.get("paragraph") or 0) < first_chapter_paragraph
        and len(clean_text(row.get("text", "")).split()) >= 4
        and not re.search(
            r"^(?:university|college|school|faculty|department)\b|^(?:by|candidate|supervisor|co-supervisor)\b",
            normalised(clean_text(row.get("text", ""))),
            flags=re.I,
        )
    ]

    bg_text = _section_plain(background)
    problem_text = _section_plain(problem)
    purpose_text = _section_plain(purpose)
    objectives_text = _section_plain(objectives)
    questions_text = _section_plain(questions)
    sig_text = _section_plain(significance)
    limits_text = _section_plain(limitations)
    delim_text = _section_plain(delimitations)
    defs_text = _section_plain(definitions)
    org_text = _section_plain(organisation)
    refs_text = _section_plain(references)
    full_text = _section_plain(current)
    issues: List[Dict[str, Any]] = []

    title_text = _section_plain(title_rows)

    if background:
        low_bg = normalised(bg_text)
        has_named_theory = bool(re.search(r"\b(?:theor(?:y|ies|etical)|conceptual|framework)\b", low_bg))
        if not has_named_theory:
            if degree == "bachelors":
                title = "The background needs a clearer conceptual anchor for the key variables"
                action = "Add a short explanation of how the main variables and context of the study relate conceptually, without imposing a full postgraduate theoretical framework."
                severity = "moderate"
            elif degree == "non_research_masters":
                title = "The background needs a clearer applied or professional logic"
                action = "Add a concise applied framework showing how the professional problem, the main independent variables, outcomes and setting connect in the study context."
                severity = "major"
            else:
                title = "The background does not establish an explicit theoretical or conceptual anchor"
                action = "Add a concise theoretical or conceptual anchor and show how it explains the expected relationship among the main variables and contextual factors in the study."
                severity = "major"
            issues.append(_issue(
                code="B1.2-LEVEL-CONCEPTUAL-ANCHOR",
                section="Background to the Study",
                title=title,
                assessment="The background introduces several central constructs, but it does not clearly identify the level-appropriate logic that binds these constructs together.",
                consequence=_degree_theory_requirement(degree),
                action=action,
                anchor=_first_substantive(background),
                category="theoretical_grounding",
                severity=severity,
                quote=_first_substantive(background).get("text", "") if _first_substantive(background) else "",
            ))
        # A context is not justified merely by naming it. Release this finding
        # only when the background makes a contextual problem claim but provides
        # no traceable empirical, policy or institutional evidence.
        context_claim = bool(re.search(
            r"\b(?:in|within|among|at)\s+(?:the\s+)?[A-Z][A-Za-z0-9&'’., -]{3,80}\b",
            bg_text,
        ))
        if context_claim and len(bg_text.split()) >= 80 and not has_traceable_context_evidence(bg_text):
            issues.append(_issue(
                code="B1.3-LOCAL-EVIDENCE",
                section="Background to the Study",
                title="The study context is named but not sufficiently evidenced",
                assessment="The background identifies a specific study context but does not provide traceable empirical, policy or institutional evidence showing why that setting requires investigation.",
                consequence="Naming a setting does not establish the scale, seriousness or distinctiveness of the problem in that setting.",
                action="Add recent, verifiable evidence from the confirmed study setting, such as official data, regulatory or policy documents, institutional records or relevant empirical studies, and connect it directly to the research problem.",
                anchor=_first_substantive(background),
                category="research_gap_and_problem",
            ))

        uncited_count_anchor = next(
            (row for row in background if any(contains_uncited_empirical_count(sentence) for sentence in re.split(r"(?<=[.!?])\s+", clean_text(row.get("text", ""))))),
            None,
        )
        if uncited_count_anchor:
            issues.append(_issue(
                code="B1.3-UNSUPPORTED-SAMPLE-CLAIM",
                section="Background to the Study",
                title="A specific empirical count is not traceable to a source",
                assessment="The background reports a numerical sample, population or empirical count without an adjacent citation supporting that exact claim.",
                consequence="Specific numerical claims must be immediately traceable to authentic evidence.",
                action="Add the authentic citation in the same sentence as the numerical claim and verify the full reference, or remove or qualify the claim if it cannot be confirmed.",
                anchor=uncited_count_anchor,
                category="citations_and_sources",
                severity="major",
            ))

        if "the study revolve" in low_bg:
            issues.append(_issue(
                code="LANG-STUDY-REVOLVE",
                section="Background to the Study",
                title="The opening sentence contains a basic subject-verb agreement error",
                assessment="The chapter opens with 'The study revolve', which is grammatically incorrect and awkwardly frames the study as revolving around broad global issues.",
                consequence="Mechanical errors in the opening paragraph weaken confidence in the student's control of academic writing before the substantive argument begins.",
                action="Correct the sentence and review the whole background for similar language problems before supervision or examination.",
                anchor=_first_substantive(background),
                category="academic_writing",
                severity="moderate",
            ))

    if problem:
        low_prob = normalised(problem_text)
        problem_words = len(problem_text.split())
        if problem_words < 45:
            issues.append(_issue(
                code="B2.1-PROBLEM-DEVELOPMENT",
                section="Statement of the Problem",
                title="The problem statement does not yet establish the central research problem",
                assessment="The section is too brief to demonstrate the practical or scholarly problem, its seriousness, the unresolved gap and the exact issue the study will address.",
                consequence="A topic statement or broad motivation is not enough to establish a researchable problem or justify the objectives.",
                action="Develop the section using traceable evidence of the problem, explain what earlier work has not resolved, identify why the confirmed context matters and end with the precise research problem.",
                anchor=_first_substantive(problem),
                category="research_gap_and_problem",
                severity="critical" if degree in {"research_masters", "professional_doctorate", "phd"} else "major",
            ))
        elif not has_traceable_context_evidence(problem_text):
            issues.append(_issue(
                code="B2.2-EVIDENCE",
                section="Statement of the Problem",
                title="The problem statement is not supported by concrete empirical, institutional or policy evidence",
                assessment="The section discusses the topic generally but does not provide traceable evidence showing the existence, scale or consequences of the problem in the confirmed study context.",
                consequence="Without direct evidence of the problem, the section reads as topic justification rather than a researchable problem.",
                action="Add specific, cited evidence showing the nature, magnitude or consequences of the problem in the confirmed study setting, then explain the precise issue that remains unresolved.",
                anchor=_first_substantive(problem),
                category="research_gap_and_problem",
            ))
        if re.search(r"\b(?:cannot|may not|should not)\s+be\s+(?:extrapolated|generalised|generalized|transferred|applied)\b", problem_text, flags=re.I):
            issues.append(_issue(
                code="B2.3-GAP-LOGIC",
                section="Statement of the Problem",
                title="The contextual argument does not yet establish a precise research gap",
                assessment="The section argues that findings from another context cannot simply be transferred to the present setting, but it does not clearly separate the practical problem, empirical gap, contextual gap and methodological gap.",
                consequence="A difference in setting alone does not establish what is unknown or why the present study is necessary.",
                action="Rewrite the problem statement in connected moves: identify the practical problem, provide evidence of its seriousness, show what earlier studies have not resolved, explain why the confirmed context matters and state the exact research focus.",
                anchor=_first_substantive(problem),
                category="research_gap_and_problem",
            ))

    if purpose and objectives:
        missing_constructs = omitted_objective_focuses(purpose_text, objectives_text)
        if missing_constructs:
            issues.append(_issue(
                code="B3.1-PURPOSE-OBJECTIVES",
                section="Purpose of the study",
                title="The purpose statement is narrower than the objectives",
                assessment=f"The purpose does not fully cover all substantive constructs introduced in the objectives, including {', '.join(missing_constructs)}.",
                consequence="This breaks the traceability required from problem to purpose, objectives, questions, methodology and conclusions.",
                action="Either broaden the purpose to include all principal constructs and outcomes or remove the objectives that fall outside the stated purpose.",
                anchor=_first_substantive(purpose),
                category="objectives_questions_hypotheses",
                severity="critical" if degree in {"research_masters", "professional_doctorate", "phd"} else "major",
            ))
    if objectives and not questions:
        issues.append(_issue(
            code="B3.3-MISSING-QUESTIONS",
            section="Research Objectives",
            title="Research questions are missing although research objectives are stated",
            assessment="The chapter states research objectives but does not provide corresponding research questions or explain why the study is hypothesis-only.",
            consequence="The reader cannot see how each objective will be answered and how the later analysis should be organised.",
            action="Add one clear research question for each descriptive objective and align inferential objectives with the relevant hypotheses. Where the design is intentionally hypothesis-only, explain that structure explicitly.",
            anchor=_first_substantive(objectives),
            category="objectives_questions_hypotheses",
            severity="major",
        ))

    if objectives and questions:
        combined = normalised(objectives_text + "\n" + questions_text)
        has_relational = any(term in combined for term in ("relationship", "impact", "effect", "influence", "predict"))
        has_hypothesis_heading = any("hypothes" in normalised(row.get("text", "")) and row.get("is_heading") for row in current)
        if has_relational and not has_hypothesis_heading and degree in {"research_masters", "professional_doctorate", "phd"}:
            issues.append(_issue(
                code="B3.5-HYPOTHESES",
                section="Research Questions",
                title="Relational and impact objectives are stated without corresponding hypotheses or justification",
                assessment="The objectives and questions use relationship, effect and impact language, but the chapter does not provide corresponding hypotheses or explain why research questions alone are sufficient.",
                consequence="For a quantitative research-intensive or doctoral study, inferential objectives normally require clear hypotheses or an explicit methodological justification for their absence.",
                action="Add hypotheses aligned to the relational objectives, or revise the design language so the study is framed as descriptive/associational rather than impact-testing.",
                anchor=_first_substantive(questions) or _first_substantive(objectives),
                category="objectives_questions_hypotheses",
            ))
        if ".?" in questions_text:
            issues.append(_issue(
                code="RQ-PUNCTUATION",
                section="Research Questions",
                title="A research question contains malformed punctuation",
                assessment="One research question ends with a full stop followed by a question mark.",
                consequence="This is a visible presentation error in a core section and should not survive proofreading.",
                action="Remove the full stop and retain a single question mark at the end of the sentence.",
                anchor=next((row for row in questions if ".?" in clean_text(row.get("text", ""))), _first_substantive(questions)),
                category="academic_writing",
                severity="moderate",
            ))

    if significance:
        low_sig = normalised(sig_text)
        if any(term in low_sig for term in ("results reveal", "the results reveal", "findings obtained", "study evaluates the impact of these results")):
            issues.append(_issue(
                code="B4.1-PROSPECTIVE-SIGNIFICANCE",
                section="Significance of the Study",
                title="The significance section reports anticipated findings as if results already exist",
                assessment="The significance section uses phrases such as results reveal and findings obtained even though Chapter One is written as a proposal.",
                consequence="This blurs the research stage and may imply that the analysis has already been conducted.",
                action="Rewrite stakeholder benefits prospectively, using language such as 'the study may show' or 'the findings may inform', and avoid asserting outcomes before data analysis.",
                anchor=_first_substantive(significance),
                category="chapter_structure",
            ))
        if not all(term in low_sig for term in ("theory", "practice", "policy")):
            issues.append(_issue(
                code="B4.1-THEORY-PRACTICE-POLICY",
                section="Significance of the Study",
                title="The significance does not clearly balance theory, practice and policy contribution",
                assessment="The section lists stakeholders, but it does not clearly separate the expected theoretical, practical and policy contributions required in a thesis-level significance discussion.",
                consequence="The contribution may appear applied only, with insufficient indication of how the study adds to scholarship or policy debate.",
                action="Reorganise the section around theory, practice and policy, then explain the specific way each group may benefit from the eventual findings.",
                anchor=_first_substantive(significance),
                category="chapter_structure",
                severity="moderate",
            ))

        if any(term in normalised(sig_text) for term in ("meta analysis", "correlation coefficients", "liu et al", "onukwulu")):
            issues.append(_issue(
                code="B4.1-LITERATURE-IN-SIGNIFICANCE",
                section="Significance of the Study",
                title="The significance section carries too much literature-review material",
                assessment="The significance section includes detailed empirical discussion and citations that read more like literature review than a concise explanation of expected beneficiaries and contributions.",
                consequence="This blurs the function of Chapter One and can make the significance section appear argumentative rather than focused on theory, practice and policy relevance.",
                action="Condense the literature-heavy passages and rewrite the section around specific stakeholder benefits and expected scholarly, practical and policy contributions.",
                anchor=_first_substantive(significance),
                category="chapter_structure",
                severity="moderate",
            ))

        contribution_terms = ("contribution to knowledge", "original contribution", "contribution to practice", "contribution to policy", "applied contribution", "professional contribution")
        if not any(term in low_sig for term in contribution_terms):
            if degree == "bachelors":
                title = "The expected contribution is not stated plainly"
                assessment = "The significance section lists beneficiaries, but it does not clearly state the modest empirical, contextual or practical contribution expected from the study."
                action = "Add one concise sentence stating the expected contribution of the study in a way that is proportionate to undergraduate research."
                severity = "moderate"
            elif degree == "non_research_masters":
                title = "The applied or professional contribution is not explicit"
                assessment = "The significance section lists stakeholders, but it does not clearly state the professional, managerial, policy or applied decision-making contribution expected from the study."
                action = "State the expected applied contribution and link it to a concrete professional, policy or organisational decision problem."
                severity = "major"
            elif degree == "research_masters":
                title = "The research contribution expected from the MPhil study is not explicit"
                assessment = "The significance section mentions beneficiaries, but it does not clearly state the expected empirical, theoretical, methodological or contextual contribution to scholarship."
                action = "Add a concise research contribution statement that explains what the study is expected to add beyond confirming that the topic matters."
                severity = "major"
            elif degree == "professional_doctorate":
                title = "The original contribution to professional practice or policy is not explicit"
                assessment = "The significance section does not clearly state the doctoral-level contribution to practice, policy, organisational capability or professional knowledge."
                action = "State the expected original contribution to professional practice or policy and identify who can use it, how and under what conditions."
                severity = "critical"
            else:
                title = "The original contribution to knowledge is not explicit"
                assessment = "The significance section does not clearly state what original contribution to knowledge the thesis is expected to make."
                action = "State the expected theoretical, empirical or methodological contribution to knowledge and explain why it matters to the field."
                severity = "critical"
            issues.append(_issue(
                code="B4.1-LEVEL-CONTRIBUTION",
                section="Significance of the Study",
                title=title,
                assessment=assessment,
                consequence=_degree_expectation_phrase(degree),
                action=action,
                anchor=_first_substantive(significance),
                category="critical_analysis" if degree in {"professional_doctorate", "phd"} else "chapter_structure",
                severity=severity,
            ))

    if limitations:
        low_lim = normalised(limits_text)
        if any(term in low_lim for term in ("faced practical constraints", "could be achieved", "did not participate", "skewing the results")):
            issues.append(_issue(
                code="B4.2-PROPOSAL-TENSE",
                section="Limitations of the Study",
                title="The limitations section mixes proposal-stage and completed-study language",
                assessment="The section states that data will be obtained but also reports constraints as though the fieldwork has already occurred.",
                consequence="Inconsistent tense makes it unclear whether the document is a proposal or a completed study.",
                action="Use proposal-appropriate tense throughout if data collection has not occurred, or convert the whole chapter consistently to completed-study reporting if the study is finished.",
                anchor=_first_substantive(limitations),
                category="chapter_structure",
            ))

    if delimitations:
        if re.search(r"\[[^\]]*(insert|provide|complete|specify)[^\]]*\]", delim_text, flags=re.I):
            issues.append(_issue(
                code="B4.3-PLACEHOLDER",
                section="Delimitation of the Study",
                title="The delimitation contains an unresolved drafting placeholder",
                assessment="The time scope still contains bracketed template text instead of the verified start and end month/year.",
                consequence="A delimitation without a completed time boundary leaves the study scope incomplete and not reproducible.",
                action="Replace the bracketed prompt with the actual data-collection period and ensure the same period appears consistently in the methodology chapter.",
                anchor=next((row for row in delimitations if "[" in clean_text(row.get("text", ""))), _first_substantive(delimitations)),
                category="chapter_structure",
                severity="critical" if degree in {"research_masters", "professional_doctorate", "phd"} else "major",
            ))

    if definitions:
        low_defs = normalised(defs_text)
        circular_match = re.search(r"\b([a-z][a-z -]{2,40})\s+(?:means|refers to|is defined as)\s+(?:the\s+)?(?:extent|degree|level|state)\s+of\s+\1\b", low_defs, flags=re.I)
        absolute_match = re.search(r"\b(?:without|with no)\s+(?:causing|creating|producing)\s+(?:any|all)\s+(?:harm|damage|risk)\b|\bcompletely eliminates?\b", low_defs, flags=re.I)
        if circular_match or absolute_match:
            matched_phrase = circular_match.group(0) if circular_match else absolute_match.group(0)
            issues.append(_issue(
                code="DEF-CIRCULAR-ABSOLUTE",
                section="Definition of Terms",
                title="A core term is defined circularly or in unrealistically absolute language",
                assessment=f"The wording ‘{matched_phrase}’ does not establish a measurable conceptual boundary.",
                consequence="Circular and absolute definitions are difficult to operationalise and may not align with measurable indicators in the methodology chapter.",
                action="Revise the definition to state the construct's dimensions, scope and observable or measurable indicators in the confirmed study context.",
                anchor=next((row for row in definitions if matched_phrase.lower() in normalised(clean_text(row.get("text", "")))), _first_substantive(definitions)),
                category="objectives_questions_hypotheses",
            ))

    if any(word in full_text for word in ("behavior", "organization", "labor")) and any(word in full_text for word in ("behaviour", "organisation", "labour")):
        anchor = next((row for row in current if any(w in clean_text(row.get("text", "")) for w in ("behavior", "organization", "labor"))), _first_substantive(background))
        issues.append(_issue(
            code="STYLE-BRITISH-AMERICAN",
            section=source_section(anchor) if anchor else "Chapter One",
            title="British and American spelling are mixed in the chapter",
            assessment="The chapter uses British spellings such as behaviour/organisations and American spellings such as behavior/organization/labor.",
            consequence="Mixed spelling conventions reduce editorial consistency and do not meet a polished thesis presentation standard.",
            action="Choose the required institutional convention and apply it consistently across the chapter, including quoted or adapted text where appropriate.",
            anchor=anchor,
            category="academic_writing",
            severity="minor",
        ))

    if references:
        cited = _citation_tokens(full_text)
        ref_authors = _reference_author_tokens(full_text)
        # If the reference list is much longer than in-text citation set, ask for a cited/uncited audit.
        if len(ref_authors) >= max(10, len(cited) + 8):
            issues.append(_issue(
                code="REF-CITED-UNCITED-AUDIT",
                section="References",
                title="The reference list requires a cited-versus-uncited consistency audit",
                assessment="The reference list is substantial for a short Chapter One, and several entries may not be clearly traceable to in-text citations in the chapter.",
                consequence="Uncited references or mismatched references weaken scholarly accuracy and may attract examiner queries.",
                action="Cross-check every in-text citation against the reference list and remove or correct any source that is not cited, not traceable or incorrectly formatted.",
                anchor=next((row for row in references if not row.get("is_heading")), _first_substantive(references)),
                category="citations_and_sources",
                severity="moderate",
                confidence=0.82,
            ))


    # Topic-safe citation/reference and scope checks for any Chapter One topic.
    full_low = normalised(full_text)
    if not references and len(re.findall(r"\([^)]*(?:19|20)\d{2}[^)]*\)", full_text)) >= 5:
        cite_anchor = next((row for row in current if re.search(r"\([^)]*(?:19|20)\d{2}[^)]*\)", clean_text(row.get("text", "")))), _first_substantive(background) or _first_substantive(problem))
        issues.append(_issue(
            code="REF-MISSING-LIST",
            section="References",
            title="The reference list is missing despite visible in-text citations",
            assessment="The chapter contains several in-text citations, but no References or Bibliography section is evident in the work.",
            consequence="A thesis chapter with citations but no reference list fails the basic traceability requirement for scholarly sources.",
            action="Add a complete reference list in the required style and verify that every in-text citation has a matching reference-list entry.",
            anchor=cite_anchor,
            category="citations_and_sources",
            severity="critical" if degree in {"research_masters", "professional_doctorate", "phd"} else "major",
        ))

    if re.search(r"\w\(", full_text) or re.search(r"\)\s*,\s*\(", full_text):
        cite_anchor = next((row for row in current if re.search(r"\w\(", clean_text(row.get("text", ""))) or re.search(r"\)\s*,\s*\(", clean_text(row.get("text", "")))), _first_substantive(background) or _first_substantive(problem))
        issues.append(_issue(
            code="CITATION-SPACING-DUPLICATION",
            section=source_section(cite_anchor) if cite_anchor else "Chapter One",
            title="Citation spacing and grouping need editorial correction",
            assessment="Several citations are attached to preceding words without a space or are placed as repeated separate parenthetical citations instead of being cleanly grouped.",
            consequence="Citation formatting errors reduce readability and make the source system look unedited.",
            action="Insert required spaces before citations, remove duplicate citations and group multiple sources according to the selected referencing style.",
            anchor=cite_anchor,
            category="citations_and_sources",
            severity="moderate",
        ))

    # Remove Nones and duplicate hard codes.
    out: List[Dict[str, Any]] = []
    seen_codes: Set[str] = set()
    for issue in issues:
        if not issue:
            continue
        code = str(issue.get("finding_id") or "")
        if code in seen_codes:
            continue
        seen_codes.add(code)
        out.append(issue)
    return out

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
    # v1.9.9.1: hard deterministic Chapter One contract. These are added
    # before generic rules so obvious MPhil issues cannot disappear simply
    # because the model, evidence-term scoring or public deduplication missed them.
    hard_issues = hard_chapter_one_supervisory_issues(current, academic_level=academic_level)
    issues.extend(hard_issues)
    hard_chapters = {1} if hard_issues else set()

    for rule in rules:
        code = str(rule.get("code") or "")
        if hard_issues and code in {"A1", "A2"}:
            continue
        if int(rule.get("chapter_number") or 0) in hard_chapters:
            # The hard Chapter One contract produces more specific, better
            # anchored comments than the generic evidence-term rules. Suppress
            # generic Chapter One checklist text to avoid bland comments such as
            # "required thesis element is not evident" when a supervisor-quality
            # comment already exists for the same chapter.
            continue
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
