from __future__ import annotations

import os
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .document_parser import clean_text, normalised
from .supervisory_accuracy_guard import paragraph_id, source_section
from .study_semantics import (
    contains_uncited_empirical_count,
    has_traceable_context_evidence,
    omitted_objective_focuses,
)


def enabled() -> bool:
    return os.getenv("VPROF_UCC_SECTION_COVERAGE_CONTRACT", "true").strip().lower() not in {"0", "false", "no", "off"}


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


def _degree_phrase(degree: str) -> str:
    if os.getenv("VPROF_INCLUDE_DEGREE_LABEL_IN_COMMENTS", "false").strip().lower() in {"0", "false", "no", "off"}:
        return ""
    return {
        "bachelors": "At Bachelor’s level, the section should show basic research coherence, correct academic presentation and a manageable contribution.",
        "non_research_masters": "At Non-Research Master’s level, the section should show applied problem clarity, credible evidence and defensible professional judgement.",
        "research_masters": "At MPhil level, the section should show independent research judgement, conceptual clarity, methodological defensibility and traceable scholarly contribution.",
        "professional_doctorate": "At Professional Doctorate level, the section should connect rigorous doctoral scholarship to a defensible contribution to practice, policy or professional knowledge.",
        "phd": "At PhD level, the section should support an original and defensible contribution to knowledge, with rigorous theoretical, empirical or methodological positioning.",
    }.get(degree, "At the declared academic level, the section should meet the appropriate scholarly standard.")


def _degree_label(degree: str) -> str:
    return {
        "bachelors": "Bachelor's level",
        "non_research_masters": "non-research Master's level",
        "research_masters": "MPhil level",
        "professional_doctorate": "professional doctorate level",
        "phd": "PhD level",
    }.get(degree, "the applicable academic level")


def _chapter_scope(paragraphs: Sequence[Dict[str, Any]]) -> Set[int]:
    chapters: Set[int] = set()
    for row in paragraphs:
        try:
            if row.get("chapter_number") is not None:
                chapters.add(int(row.get("chapter_number")))
        except Exception:
            continue
    return chapters


def _single_chapter(paragraphs: Sequence[Dict[str, Any]]) -> Optional[int]:
    chapters = _chapter_scope(paragraphs)
    return next(iter(chapters)) if len(chapters) == 1 else None


def _tokens(value: str) -> List[str]:
    out: List[str] = []
    for token in re.findall(r"[a-z0-9]+", normalised(value)):
        if len(token) > 5 and token.endswith("s") and token not in {"thesis", "analysis"}:
            token = token[:-1]
        out.append(token)
    return out


def _contract_label_key(value: Any) -> str:
    return re.sub(r"\s+", " ", normalised(str(value or "")).replace("/", " ")).strip()


def _contains_sequence(container: str, phrase: str) -> bool:
    left = _tokens(container)
    right = _tokens(phrase)
    if not left or not right or len(right) > len(left):
        return False
    return any(left[i:i + len(right)] == right for i in range(len(left) - len(right) + 1))


def _current_rows(paragraphs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [row for row in paragraphs if row.get("document_role", "current") == "current"]


def _group_by_heading(paragraphs: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group rows under both their immediate heading and every parent heading.

    Earlier builds grouped a paragraph only under its immediate subsection.  A
    parent such as ``Research Objectives`` therefore appeared almost empty when
    the actual content sat under ``General Objective`` and ``Specific
    Objectives``.  The coverage contract now aggregates child subsections while
    preserving chapter metadata on every row.  ``_find_rows`` performs the
    chapter filter so repeated headings such as ``Introduction`` do not leak
    across chapters.
    """
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in _current_rows(paragraphs):
        labels: List[str] = []
        labels.extend(clean_text(value) for value in row.get("section_path") or [] if clean_text(value))
        labels.extend([
            clean_text(row.get("heading") or ""),
            clean_text(row.get("text") or "") if row.get("is_heading") else "",
            clean_text(source_section(row) or ""),
        ])
        seen: Set[str] = set()
        for label in labels:
            key = normalised(label)
            if not key or key in seen or re.fullmatch(r"chapter\s+(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+)", key):
                continue
            seen.add(key)
            bucket = grouped.setdefault(key, [])
            marker = (row.get("document_role", "current"), row.get("document_index"), row.get("paragraph"), row.get("table_index"), row.get("table_row"))
            if not any(
                (item.get("document_role", "current"), item.get("document_index"), item.get("paragraph"), item.get("table_index"), item.get("table_row")) == marker
                for item in bucket
            ):
                bucket.append(row)
    return grouped


def _find_rows(
    grouped: Dict[str, List[Dict[str, Any]]],
    names: Iterable[str],
    chapter: Optional[int] = None,
) -> List[Dict[str, Any]]:
    wanted = [normalised(name) for name in names if normalised(name)]
    collected: List[Dict[str, Any]] = []
    seen_markers: Set[Tuple[Any, ...]] = set()

    def add_rows(rows: Sequence[Dict[str, Any]]) -> None:
        for row in rows:
            if chapter is not None and row.get("chapter_number") != chapter:
                continue
            marker = (
                row.get("document_role", "current"), row.get("document_index"),
                row.get("paragraph"), row.get("table_index"), row.get("table_row"),
            )
            if marker in seen_markers:
                continue
            seen_markers.add(marker)
            collected.append(row)

    for name in wanted:
        for key, rows in grouped.items():
            if key == name:
                add_rows(rows)
    for name in wanted:
        for key, rows in grouped.items():
            if _contains_sequence(key, name):
                add_rows(rows)
    collected.sort(key=lambda row: (
        int(row.get("paragraph") or 0), int(row.get("table_index") or -1), int(row.get("table_row") or -1)
    ))
    return collected


def _find_content_rows(
    paragraphs: Sequence[Dict[str, Any]],
    names: Iterable[str],
    chapter: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Recognise a required element even when it is not formatted as a heading.

    This is conservative: one-word aliases are ignored and multi-word labels
    must appear in the paragraph or table title. It prevents false missing-section
    comments where, for example, sample size or demographic characteristics are
    clearly reported inside a broader methods/results section.
    """
    wanted = [normalised(name) for name in names if len(normalised(name).split()) >= 2]
    for row in _current_rows(paragraphs):
        if chapter is not None and row.get("chapter_number") != chapter:
            continue
        haystack = normalised(
            clean_text(row.get("table_title", "")) + " " + clean_text(row.get("text", ""))
        )
        if any(name in haystack for name in wanted):
            return [row]
    return []


def _plain(rows: Sequence[Dict[str, Any]]) -> str:
    return "\n".join(clean_text(row.get("text", "")) for row in rows if clean_text(row.get("text", "")))


def _first_substantive(rows: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for row in rows:
        if not row.get("is_heading") and len(clean_text(row.get("text", "")).split()) >= 4:
            return row
    for row in rows:
        if len(clean_text(row.get("text", "")).split()) >= 1:
            return row
    return None


def _first_chapter_anchor(paragraphs: Sequence[Dict[str, Any]], chapter: Optional[int] = None) -> Optional[Dict[str, Any]]:
    for row in _current_rows(paragraphs):
        if chapter and row.get("chapter_number") != chapter:
            continue
        if row.get("is_heading") and len(clean_text(row.get("text", "")).split()) >= 1:
            return row
    for row in _current_rows(paragraphs):
        if chapter and row.get("chapter_number") != chapter:
            continue
        if len(clean_text(row.get("text", "")).split()) >= 4:
            return row
    return None


def _title_anchor(paragraphs: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    current = _current_rows(paragraphs)
    first_chapter_para = min((int(r.get("paragraph")) for r in current if r.get("chapter_number") and r.get("paragraph")), default=10**9)
    title_rows = [r for r in current if not r.get("chapter_number") and int(r.get("paragraph") or 0) < first_chapter_para and len(clean_text(r.get("text", "")).split()) >= 5]
    if not title_rows:
        return None
    return max(title_rows, key=lambda r: len(clean_text(r.get("text", "")).split()))


def _issue(
    *,
    code: str,
    section: str,
    title: str,
    assessment: str,
    action: str,
    anchor: Optional[Dict[str, Any]],
    category: str,
    degree: str,
    severity: str = "major",
    confidence: float = 0.94,
    quote: str = "",
    example: str = "",
    study_terms: Optional[Sequence[str]] = None,
    missing_section_label: str = "",
    chapter_number: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    if anchor is None:
        return None
    pid = paragraph_id(anchor)
    if not pid:
        return None
    return {
        "finding_id": f"UCC-{code}",
        "category": category,
        "section": clean_text(section) or source_section(anchor) or "Document section",
        "issue_title": clean_text(title),
        "severity": severity,
        "confidence": confidence,
        "evidence_paragraph_ids": [pid],
        "problematic_quote": clean_text(quote or anchor.get("text", ""))[:260],
        "assessment": clean_text(assessment),
        "academic_consequence": _degree_phrase(degree),
        "required_action": clean_text(action),
        "illustrative_guidance": clean_text(example),
        "study_terms": [clean_text(value) for value in (study_terms or []) if clean_text(value)],
        "missing_section_label": clean_text(missing_section_label),
        "chapter_number": chapter_number if chapter_number is not None else anchor.get("chapter_number"),
        "guidance_type": "structural_guidance",
        "source_verification_required": category == "citations_and_sources",
        "context_guard_adjusted": False,
        "checklist_code": f"UCC-{code}",
        "checklist_item": clean_text(title),
        "verification_status": "ucc_section_contract",
    }


UCC_EXPECTED: Dict[int, List[Tuple[str, List[str], str, str]]] = {
    1: [
        ("Introduction / Overview", ["introduction", "overview", "chapter introduction"], "chapter_structure", "moderate"),
        ("Background to the Study", ["background to the study", "background of the study"], "research_gap_and_problem", "critical"),
        ("Statement of the Problem", ["statement of the problem", "problem statement"], "research_gap_and_problem", "critical"),
        # Purpose is intentionally distinct from a general/main objective.  UCC
        # chapters may contain both, and accepting the latter as a purpose caused
        # genuine omissions to pass silently in MPhil and lower-level reviews.
        ("Purpose of the Study", ["purpose of the study", "aim of the study", "general aim"], "objectives_questions_hypotheses", "critical"),
        ("Research Objectives", ["research objectives", "objectives of the study", "general objective", "main objective", "specific objectives", "specific objective"], "objectives_questions_hypotheses", "critical"),
        ("Research Questions", ["research questions", "research question"], "objectives_questions_hypotheses", "critical"),
        ("Research Hypotheses", ["research hypotheses", "research hypothesis", "hypotheses", "hypothesis"], "objectives_questions_hypotheses", "major"),
        ("Significance of the Study", ["significance of the study"], "critical_analysis", "major"),
        ("Limitations of the Study", ["limitations of the study", "limitation of the study"], "chapter_structure", "major"),
        ("Delimitations of the Study", ["delimitation of the study", "delimitations of the study", "scope and delimitation of the study", "scope and delimitations of the study", "scope of the study", "scope"], "chapter_structure", "major"),
        ("Definition of Terms", ["definition of terms", "definition of key terms", "definition of key concepts", "definition of concepts", "operational definition of terms", "operational definitions"], "objectives_questions_hypotheses", "major"),
        ("Organisation of the Study", ["organisation of the study", "organization of the study"], "chapter_structure", "moderate"),
    ],
    2: [
        ("Introduction", ["introduction"], "chapter_structure", "moderate"),
        ("Theoretical Review", ["theoretical review", "theoretical framework"], "theoretical_grounding", "critical"),
        ("Conceptual Review", ["conceptual review", "conceptual literature", "conceptual definitions"], "theoretical_grounding", "major"),
        ("Empirical Review", ["empirical review", "review of empirical literature"], "critical_analysis", "critical"),
        ("Literature Gap / Synthesis", ["literature gap", "research gap", "summary of empirical review", "synthesis of literature", "literature synthesis"], "critical_analysis", "major"),
        ("Conceptual Framework", ["conceptual framework"], "theoretical_grounding", "critical"),
        ("Hypothesis Development", ["hypothesis development", "hypotheses development"], "objectives_questions_hypotheses", "major"),
        ("Chapter Summary", ["chapter summary", "summary of the chapter"], "chapter_structure", "moderate"),
    ],
    3: [
        ("Introduction", ["introduction"], "chapter_structure", "moderate"),
        ("Research Philosophy / Paradigm", ["research philosophy", "research paradigm", "philosophical orientation"], "methodological_rigour", "major"),
        ("Research Approach", ["research approach", "methodological approach"], "methodological_rigour", "major"),
        ("Research Design", ["research design"], "methodological_rigour", "critical"),
        ("Study Area", ["study area", "study setting"], "methodological_rigour", "major"),
        ("Population", ["population", "target population"], "methodological_rigour", "major"),
        ("Sampling Frame", ["sampling frame", "sample frame"], "methodological_rigour", "major"),
        ("Sampling Procedure", ["sampling procedure", "sampling technique", "sampling frame"], "methodological_rigour", "critical"),
        ("Sample Size", ["sample size", "sample size determination"], "methodological_rigour", "critical"),
        ("Data Sources", ["data source", "data sources", "source of data", "sources of data"], "methodological_rigour", "major"),
        ("Data Collection Instrument", ["data collection instrument", "research instrument", "instrument"], "methodological_rigour", "critical"),
        ("Operationalisation and Measurement", ["operationalisation of variables", "operationalization of variables", "measurement of variables", "variable measurement", "operational definitions"], "measurement_and_scoring", "critical"),
        ("Pilot Study / Pre-testing", ["pilot study", "pilot testing", "pretest", "pre-test", "pretesting", "pre-testing"], "methodological_rigour", "major"),
        ("Validity and Reliability", ["validity and reliability", "validity", "reliability", "trustworthiness"], "methodological_rigour", "critical"),
        ("Data Collection Procedures", ["data collection procedure", "data collection procedures"], "methodological_rigour", "major"),
        ("Data Preparation and Screening", ["data preparation", "data screening", "preliminary analysis", "missing data", "outlier treatment"], "methodological_rigour", "major"),
        ("Data Processing and Analysis", ["data processing and analysis", "data analysis", "method of data analysis"], "methodological_rigour", "critical"),
        ("Model Specification", ["model specification", "analytical model", "econometric model", "regression model"], "analysis_appropriateness", "major"),
        ("Assumptions and Diagnostic Tests", ["diagnostic tests", "model diagnostics", "assumption tests", "regression diagnostics"], "analysis_appropriateness", "major"),
        ("Ethical Considerations", ["ethical considerations", "ethics"], "ethics_and_integrity", "critical"),
        ("Chapter Summary", ["chapter summary", "summary of the chapter"], "chapter_structure", "moderate"),
    ],
    4: [
        ("Introduction", ["introduction"], "chapter_structure", "moderate"),
        ("Response Rate", ["response rate"], "results_and_interpretation", "major"),
        ("Sample Characteristics", ["sample characteristics", "demographic characteristics", "demographic characteristics of respondents", "background characteristics"], "results_and_interpretation", "major"),
        ("Data Quality and Preliminary Checks", ["data quality", "data screening", "missing data", "outlier", "normality", "common method bias", "non-response bias"], "results_and_interpretation", "major"),
        ("Descriptive Results", ["descriptive statistics", "descriptive results", "level of", "extent of"], "results_and_interpretation", "major"),
        ("Measurement Quality", ["reliability", "validity", "measurement model", "outer loadings", "composite reliability", "discriminant validity"], "measurement_and_scoring", "critical"),
        ("Results by Objective", ["results", "findings", "presentation of results", "hypothesis testing"], "results_and_interpretation", "critical"),
        ("Diagnostic Tests", ["diagnostic tests", "model diagnostics", "assumption tests"], "results_and_interpretation", "major"),
        ("Discussion of Findings", ["discussion of findings", "discussion"], "discussion_and_integration", "critical"),
        ("Chapter Summary", ["chapter summary", "summary of the chapter"], "chapter_structure", "moderate"),
    ],
    5: [
        ("Introduction", ["introduction"], "chapter_structure", "moderate"),
        ("Summary of the Study", ["summary of the study"], "conclusions_and_recommendations", "major"),
        ("Summary of Findings", ["summary of findings"], "conclusions_and_recommendations", "critical"),
        ("Conclusions", ["conclusion", "conclusions"], "conclusions_and_recommendations", "critical"),
        ("Recommendations", ["recommendation", "recommendations"], "conclusions_and_recommendations", "critical"),
        ("Contribution and Implications", ["contribution to knowledge", "contribution to practice", "theoretical implications", "practical implications", "policy implications", "implications", "contribution"], "critical_analysis", "major"),
        ("Limitations of the Study", ["limitations of the study", "study limitations", "limitations"], "chapter_structure", "major"),
        ("Suggestions for Further Research", ["suggestions for further research", "future research"], "conclusions_and_recommendations", "major"),
    ],
}


# Whole-document components are assessed only for complete thesis, dissertation
# or project-work submissions. They are deliberately excluded from a single
# chapter or proposal review so the app does not demand front matter from a
# chapter-only file.
DOCUMENT_EXPECTED: List[Tuple[str, List[str], str, str, str]] = [
    ("Title Page", ["title page"], "document_completeness", "major", "always"),
    ("Declaration", ["declaration", "candidate declaration", "student declaration"], "ethics_and_integrity", "major", "always"),
    ("Abstract", ["abstract"], "document_completeness", "critical", "always"),
    ("Table of Contents", ["table of contents", "contents"], "document_completeness", "major", "always"),
    ("List of Tables", ["list of tables"], "document_completeness", "moderate", "tables"),
    ("List of Figures", ["list of figures"], "document_completeness", "moderate", "figures"),
    ("References", ["references", "reference list", "bibliography"], "reference_integrity", "critical", "always"),
    ("Appendices / Supporting Instruments", ["appendix", "appendices", "questionnaire", "interview guide", "data extraction form"], "document_completeness", "major", "supporting_material"),
]


SECTION_STATUS_PRESENT = "PRESENT"
SECTION_STATUS_EQUIVALENT = "EQUIVALENT_HEADING"
SECTION_STATUS_INADEQUATE = "PRESENT_BUT_INADEQUATE"
SECTION_STATUS_MISSING = "MISSING"
SECTION_STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"

_RESEARCH_INTENSIVE_LEVELS = {"research_masters", "professional_doctorate", "phd"}

# These components may legitimately be reported within a broader methods or
# results section. Core chapter sections such as Purpose, Limitations and
# Definition of Terms must be identified by a heading rather than by a passing
# mention elsewhere in the work.
_INLINE_EQUIVALENT_SECTIONS = {
    "sampling frame", "sample size", "data sources",
    "operationalisation and measurement", "data preparation and screening",
    "model specification", "assumptions and diagnostic tests",
    "response rate", "sample characteristics", "data quality and preliminary checks",
    "descriptive results", "measurement quality", "diagnostic tests",
    "contribution and implications",
}


def _route_flags(paragraphs: Sequence[Dict[str, Any]]) -> Dict[str, bool]:
    current = _current_rows(paragraphs)
    full_text = normalised(_plain(current))
    method_rows = [row for row in current if row.get("chapter_number") == 3]
    route_rows = method_rows or current
    route_text = normalised(_plain(route_rows))

    qualitative = any(term in route_text for term in (
        "qualitative", "thematic analysis", "content analysis", "phenomenological",
        "grounded theory", "focus group", "interview guide", "case study design",
    ))
    quantitative = any(term in route_text for term in (
        "quantitative", "questionnaire", "regression", "correlation", "anova",
        "hypothesis", "structural equation", "smartpls", "spss", "stata", "process macro",
    ))
    mixed = bool(re.search(
        r"\b(?:adopted|used|employed|followed|applied)\s+(?:an?\s+)?(?:mixed[ -]?methods?|convergent|explanatory sequential|exploratory sequential)",
        route_text,
    ))
    survey = any(term in route_text for term in ("survey", "questionnaire", "respondent", "response rate"))

    objective_rows = [
        row for row in current
        if any("objective" in normalised(part) for part in (row.get("section_path") or []))
        or "objective" in normalised(row.get("heading", ""))
    ]
    objective_text = normalised(_plain(objective_rows))
    inferential_text = objective_text or full_text
    inferential = any(term in inferential_text for term in (
        "effect of", "impact of", "influence of", "relationship between", "association between",
        "predict", "determinant", "moderating", "mediating", "significant difference",
    )) or any(term in route_text for term in ("regression", "correlation", "anova", "hypothesis"))
    model_based = any(term in route_text for term in (
        "regression", "structural equation", "sem", "pls sem", "smartpls", "process macro",
        "econometric", "panel data", "time series", "logit", "probit", "moderation", "mediation",
    ))
    probability_sampling = any(term in route_text for term in (
        "simple random", "stratified random", "systematic sampling", "cluster sampling",
        "multistage sampling", "probability sampling", "sampling frame",
    ))
    human_participants = any(term in route_text for term in (
        "respondent", "participant", "student", "teacher", "employee", "manager", "household",
        "interviewee", "pre service", "pre-service", "staff",
    ))
    scale_measurement = survey or any(term in route_text for term in (
        "likert", "scale", "construct", "reliability", "cronbach", "composite reliability",
        "outer loading", "validity", "questionnaire item",
    ))
    secondary_data = any(term in route_text for term in (
        "secondary data", "annual report", "panel data", "time series", "database", "archival data",
    ))
    has_tables = any(row.get("table_index") is not None or row.get("table_number") for row in current)
    has_figures = bool(re.search(r"\bfigure\s+(?:[1-9]|[1-9]\d)(?:[.: -]|$)", full_text))
    has_citations = bool(re.search(r"\((?:[^()]{1,80}),?\s*(?:19|20)\d{2}[a-z]?\)", _plain(current)))
    descriptive_objectives = any(term in objective_text for term in (
        "assess the level", "determine the level", "examine the level",
        "assess the extent", "determine the extent", "describe", "identify", "explore",
        "what is the level", "what is the extent",
    ))
    has_question_heading = any(row.get("is_heading") and "research question" in normalised(row.get("text", "")) for row in current)
    has_hypothesis_heading = any(row.get("is_heading") and "hypoth" in normalised(row.get("text", "")) for row in current)
    return {
        "qualitative": qualitative and not quantitative and not mixed,
        "quantitative": quantitative or (inferential and not qualitative),
        "mixed": mixed,
        "survey": survey,
        "inferential": inferential and not (qualitative and not quantitative and not mixed),
        "model_based": model_based,
        "probability_sampling": probability_sampling,
        "human_participants": human_participants,
        "scale_measurement": scale_measurement,
        "secondary_data": secondary_data,
        "has_tables": has_tables,
        "has_figures": has_figures,
        "has_citations": has_citations,
        "descriptive_objectives": descriptive_objectives,
        "has_question_heading": has_question_heading,
        "has_hypothesis_heading": has_hypothesis_heading,
    }


def _section_applicable(label: str, degree: str, flags: Dict[str, bool]) -> bool:
    key = _contract_label_key(label)
    empirical = bool(
        flags.get("quantitative") or flags.get("qualitative") or flags.get("mixed")
        or flags.get("survey") or flags.get("secondary_data") or flags.get("human_participants")
    )
    field_based = bool(flags.get("human_participants") or flags.get("survey") or flags.get("qualitative"))

    if key == "research questions":
        return bool(flags.get("descriptive_objectives") or not flags.get("inferential") or flags.get("has_question_heading"))
    if key == "research hypotheses":
        return bool(flags.get("inferential"))
    if key == "hypothesis development":
        return bool(flags.get("inferential")) and degree in _RESEARCH_INTENSIVE_LEVELS
    if key == "research philosophy paradigm":
        return degree in _RESEARCH_INTENSIVE_LEVELS or bool(flags.get("mixed"))
    if key == "study area":
        return field_based and not (flags.get("secondary_data") and not flags.get("human_participants"))
    if key == "population":
        return empirical
    if key == "sampling frame":
        return bool(flags.get("probability_sampling"))
    if key in {"sampling procedure", "sample size"}:
        return empirical
    if key == "data sources":
        return empirical
    if key == "data collection instrument":
        return bool(field_based or flags.get("scale_measurement"))
    if key == "operationalisation and measurement":
        return bool(flags.get("quantitative") or flags.get("mixed") or flags.get("scale_measurement") or flags.get("secondary_data"))
    if key == "pilot study pre testing":
        return bool(flags.get("survey") or flags.get("scale_measurement"))
    if key == "validity and reliability":
        return bool(flags.get("scale_measurement") or flags.get("qualitative") or flags.get("mixed"))
    if key == "data collection procedures":
        return empirical
    if key == "data preparation and screening":
        return bool(flags.get("quantitative") or flags.get("mixed") or flags.get("secondary_data"))
    if key == "data processing and analysis":
        return empirical
    if key == "model specification":
        return bool(flags.get("model_based"))
    if key in {"assumptions and diagnostic tests", "diagnostic tests"}:
        return bool(flags.get("model_based"))
    if key == "ethical considerations":
        return bool(flags.get("human_participants") or flags.get("qualitative") or flags.get("survey"))
    if key == "response rate":
        return bool(flags.get("survey"))
    if key == "sample characteristics":
        return bool(flags.get("human_participants"))
    if key == "measurement quality":
        return bool(flags.get("scale_measurement"))
    if key == "data quality and preliminary checks":
        return bool(flags.get("quantitative") or flags.get("mixed") or flags.get("secondary_data"))
    if key == "theoretical review":
        return degree in _RESEARCH_INTENSIVE_LEVELS or bool(flags.get("inferential"))
    if key == "conceptual framework":
        return degree in _RESEARCH_INTENSIVE_LEVELS or bool(flags.get("inferential"))
    if key == "literature gap synthesis":
        return degree in _RESEARCH_INTENSIVE_LEVELS
    if key == "contribution and implications":
        return True
    return True


def _submission_target_chapters(
    paragraphs: Sequence[Dict[str, Any]],
    submission_scope: Any = "",
) -> Set[int]:
    chapters = _chapter_scope(paragraphs)
    scope = normalised(str(submission_scope or ""))
    if any(term in scope for term in ("full thesis", "complete thesis", "full dissertation", "complete dissertation", "full project")):
        return {1, 2, 3, 4, 5}
    # Chapters One to Four almost always represent an incomplete full study,
    # whereas Chapters One to Three may legitimately be a proposal.
    if {1, 2, 3, 4}.issubset(chapters):
        return {1, 2, 3, 4, 5}
    return set(chapters)


def _is_full_submission(paragraphs: Sequence[Dict[str, Any]], submission_scope: Any = "") -> bool:
    chapters = _chapter_scope(paragraphs)
    scope = normalised(str(submission_scope or ""))
    if any(term in scope for term in (
        "full thesis", "complete thesis", "full dissertation", "complete dissertation",
        "full project", "complete project", "entire thesis", "entire dissertation",
    )):
        return True
    return {1, 2, 3, 4}.issubset(chapters) or {1, 2, 3, 4, 5}.issubset(chapters)


def _document_component_applicable(mode: str, flags: Dict[str, bool]) -> bool:
    if mode == "tables":
        return bool(flags.get("has_tables"))
    if mode == "figures":
        return bool(flags.get("has_figures"))
    if mode == "supporting_material":
        return bool(flags.get("survey") or flags.get("scale_measurement") or flags.get("qualitative") or flags.get("human_participants"))
    return True


def _pre_chapter_rows(paragraphs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    current = _current_rows(paragraphs)
    first_chapter = min(
        (int(row.get("paragraph") or 10**9) for row in current if row.get("chapter_number") is not None),
        default=10**9,
    )
    return [row for row in current if row.get("chapter_number") is None and int(row.get("paragraph") or 0) < first_chapter]


def _document_component_rows(
    paragraphs: Sequence[Dict[str, Any]],
    grouped: Dict[str, List[Dict[str, Any]]],
    label: str,
    aliases: Sequence[str],
) -> Tuple[List[Dict[str, Any]], str, bool]:
    key = _contract_label_key(label)
    current = _current_rows(paragraphs)
    if key == "title page":
        rows = _pre_chapter_rows(current)
        title_like = [
            row for row in rows
            if len(clean_text(row.get("text", "")).split()) >= 5
            and not row.get("is_toc_entry")
            and normalised(row.get("text", "")) not in {"abstract", "declaration", "table of contents", "contents"}
        ]
        has_university = any("university" in normalised(row.get("text", "")) for row in rows)
        selected = rows if title_like and (has_university or len(title_like) >= 2) else []
        return selected, "Title Page" if selected else "", bool(selected)
    if key == "table of contents":
        rows = [row for row in current if row.get("is_toc_entry")]
        heading = next((clean_text(row.get("text", "")) for row in current if normalised(row.get("text", "")) == "table of contents"), "")
        return rows, heading, bool(heading)
    if key in {"list of tables", "list of figures"}:
        target = key
        rows = [
            row for row in current
            if not row.get("is_toc_entry")
            and any(_contains_sequence(clean_text(part), target) for part in (row.get("section_path") or []))
        ]
        heading = next((clean_text(row.get("text", "")) for row in rows if normalised(row.get("text", "")) == target), "")
        if rows:
            return rows, heading or label, bool(heading)
    if key == "appendices supporting instruments":
        first = next((
            int(row.get("paragraph") or 0) for row in current
            if not row.get("is_toc_entry") and re.match(r"^appendi(?:x|ces)\b", normalised(row.get("text", "")))
        ), None)
        if first is not None:
            rows = [row for row in current if int(row.get("paragraph") or 0) >= first]
            return rows, clean_text(rows[0].get("text", "")) if rows else "", True
    rows = _find_rows(grouped, aliases)
    heading = next((clean_text(row.get("text", "")) for row in rows if row.get("is_heading")), "")
    if not rows and key == "appendices supporting instruments":
        rows = [
            row for row in current
            if any(term in normalised(row.get("text", "")) for term in ("questionnaire", "interview guide", "data extraction form"))
            and (row.get("is_heading") or len(clean_text(row.get("text", "")).split()) >= 5)
        ]
        heading = clean_text(rows[0].get("text", "")) if rows else ""
    return rows, heading, bool(heading)


def _document_component_adequacy(label: str, rows: Sequence[Dict[str, Any]]) -> Tuple[bool, str, str]:
    body_text = _plain([row for row in rows if not row.get("is_heading")])
    all_text = _plain(rows)
    key = _contract_label_key(label)
    text = all_text if key in {"title page", "declaration", "table of contents", "list of tables", "list of figures"} else (body_text or all_text)
    low = normalised(text)
    words = len(clean_text(text).split())
    if key == "title page":
        enough = words >= 8 and any(term in low for term in ("university", "college", "in partial fulfilment", "by"))
        return enough, "The title page does not clearly identify the study and its institutional submission details.", "Show the approved study title, candidate name, programme or award, institution and submission year using the required institutional format."
    if key == "declaration":
        enough = words >= 20 and any(term in low for term in ("original", "declare", "declaration"))
        return enough, "The declaration is present but does not clearly state originality and the required candidate or supervisor confirmation.", "Use the approved declaration wording and include the candidate and supervisor confirmation fields required by the institution."
    if key == "abstract":
        dimensions = sum(any(term in low for term in group) for group in (
            ("purpose", "aim", "examined", "investigated"),
            ("design", "approach", "sample", "data were collected", "method"),
            ("finding", "result", "showed", "revealed"),
            ("conclusion", "concluded", "recommend"),
        ))
        return words >= 120 and dimensions >= 3, "The abstract does not yet provide a complete account of the purpose, method, principal findings and conclusion.", "Rewrite the abstract as a self-contained summary of the problem or purpose, design, population and sample, instrument or data source, analysis, principal numerical or thematic findings, conclusion and main recommendation."
    if key == "table of contents":
        mentions = len(re.findall(r"\bchapter\s+(?:one|two|three|four|five|1|2|3|4|5)\b", low))
        return mentions >= 3 or len(rows) >= 12, "The table of contents is present but does not provide a complete navigational outline of the work.", "Regenerate the table of contents from the final heading structure and confirm that headings and page numbers agree with the work."
    if key in {"list of tables", "list of figures"}:
        noun = "table" if "tables" in key else "figure"
        count = len(re.findall(rf"\b{noun}\s+\d+", low))
        substantive_rows = sum(1 for row in rows if clean_text(row.get("text", "")) and normalised(row.get("text", "")) not in {key, f"{noun} page"})
        return count >= 1 or substantive_rows >= 2, f"The {label.lower()} is present but does not list the numbered items used in the work.", f"Regenerate the {label.lower()} so every numbered {noun} and its page number matches the final document."
    if key == "references":
        years = len(re.findall(r"\b(?:19|20)\d{2}[a-z]?\b", text))
        return words >= 30 and years >= 2, "The reference section is present but is too incomplete to support the citations used in the study.", "Provide a complete, consistently formatted reference entry for every retained in-text citation and remove entries that are not cited."
    if key == "appendices supporting instruments":
        enough = words >= 20 or any(term in low for term in ("appendix", "questionnaire", "interview guide", "data extraction", "consent form"))
        return enough, "The supporting appendices do not contain enough material to verify the instrument or data-collection procedure.", "Attach the final questionnaire, interview guide, observation schedule or data-extraction form, together with other supporting documents required to verify the study."
    return words >= 10, f"The {label} component is present but incomplete.", f"Complete the {label} using the approved institutional format."


def _canonical_alias(label: str, matched_heading: str) -> bool:
    canonical = normalised(label).replace(" / ", " ")
    matched = normalised(matched_heading)
    return canonical == matched or canonical in matched or matched in canonical


def _section_content_dimensions(label: str, text: str, degree: str = "") -> Tuple[bool, str, str]:
    """Return adequacy, reason and action for structurally present sections.

    The checks are purpose-based rather than a universal word-count rule.  A
    concise purpose or research question can be perfectly adequate, while a
    lengthy delimitation that never identifies the population or location is
    not.
    """
    low = normalised(text)
    words = len(clean_text(text).split())
    key = _contract_label_key(label)

    if key in {"purpose of the study", "research questions", "research hypotheses", "research objectives"}:
        return (words >= 5, "The section does not contain a substantive statement.", f"State the {label.lower()} clearly using the study's constructs, population and setting.")
    if key == "introduction overview" or key == "introduction":
        return (words >= 18, "The introduction does not yet explain the chapter's purpose and organisation.", "Add a short paragraph stating what the chapter covers and how its sections are arranged.")
    if key == "delimitations of the study":
        dimensions = 0
        dimensions += int(any(term in low for term in (
            "country", "region", "district", "municipality", "institution", "organisation", "organization", "study area", "location"
        )))
        dimensions += int(any(term in low for term in (
            "participant", "respondent", "employee", "student", "teacher", "population", "sample", "unit of analysis"
        )))
        dimensions += int(any(term in low for term in (
            "variable", "construct", "theme", "phenomenon", "outcome", "scope", "focus"
        )))
        dimensions += int(
            any(term in low for term in ("academic year", "study period", "data collection period", "time period", "financial year"))
            or bool(re.search(r"\b(?:19|20)\d{2}\b", text))
        )
        dimensions += int(any(term in low for term in (
            "exclude", "excluded", "limited to", "delimited", "boundary", "case study"
        )))
        # A credible scope/delimitation must identify more than the topic and
        # location. The same structural minimum applies at every level; degree
        # level changes the depth of justification, not whether boundaries are
        # stated.
        threshold = 4
        return (
            dimensions >= threshold,
            "The section is present, but it does not state enough of the study's boundaries.",
            "State the study location, population or unit of analysis, variables or themes, period covered and the main exclusions that define the scope.",
        )
    if key == "limitations of the study":
        has_constraint = any(term in low for term in ("limitation", "constraint", "bias", "access", "non response", "sample", "measurement", "data", "generalisation", "generalization"))
        has_consequence = any(term in low for term in ("may", "could", "restrict", "limit", "affect", "reduce", "therefore", "interpret"))
        return (has_constraint and has_consequence and words >= 25, "The limitations are not explained as concrete constraints and consequences for interpretation.", "Identify the main design, sampling, measurement or data-collection limitations and explain how each one affects interpretation or generalisation.")
    if key == "definition of terms":
        definition_markers = len(re.findall(r"(?:^|[.;])\s*[A-Z][A-Za-z -]{2,40}\s*(?::|means|refers to|is defined as)", text))
        return (definition_markers >= 2 or (words >= 35 and any(term in low for term in ("means", "refers to", "defined as"))), "The section does not operationally define enough of the study's central terms.", "Define each principal construct as it is used and measured in the study, and distinguish closely related concepts.")
    if key == "significance of the study":
        dimensions = sum(any(term in low for term in group) for group in (
            ("theory", "knowledge", "literature", "empirical"),
            ("practice", "management", "professional", "institution"),
            ("policy", "regulator", "government", "guideline"),
            ("stakeholder", "student", "teacher", "bank", "community", "researcher"),
        ))
        return (dimensions >= 2 and words >= 70, "The section identifies beneficiaries but does not explain the distinct scholarly and practical value of the study.", "Explain the study's likely scholarly, practical and policy value in separate, specific terms rather than listing beneficiaries only.")
    if key == "organisation of the study":
        chapter_mentions = len(re.findall(r"\bchapter\s+(?:one|two|three|four|five|1|2|3|4|5)\b", low))
        return (chapter_mentions >= 3, "The organisation section does not adequately guide the reader through the chapters.", "State the purpose and main content of each chapter in one concise sequence.")
    if key == "statement of the problem":
        has_evidence = bool(re.search(r"\b(?:19|20)\d{2}\b", text)) and any(term in low for term in ("report", "study", "data", "statistics", "evidence", "found", "reported"))
        has_gap = any(term in low for term in ("gap", "limited", "few studies", "not known", "unclear", "however", "despite"))
        return (words >= 120 and has_evidence and has_gap, "The problem statement does not yet combine evidence of the practical problem with a precise unresolved research gap.", "Present evidence of the problem, show what earlier studies have not resolved, explain the consequence of that gap and end with the exact focus of the study.")
    if key == "background to the study":
        broad_to_specific = any(term in low for term in ("ghana", "region", "district", "institution", "sector", "context")) and any(term in low for term in ("gap", "however", "despite", "limited"))
        return (words >= 220 and broad_to_specific, "The background does not yet move clearly from the wider context to the specific study problem and gap.", "Use focused evidence to introduce the constructs, narrow to the study setting and lead directly to the problem. Reserve exhaustive study-by-study comparison for Chapter Two.")
    if key in {"chapter summary", "summary of the chapter"}:
        return (words >= 35, "The chapter summary does not yet capture the main content and transition to the next chapter.", "Summarise the chapter's main argument or methodological decisions and state how the next chapter follows.")
    if key == "data processing and analysis":
        has_mapping = any(term in low for term in ("objective", "research question", "hypothesis")) and any(term in low for term in ("analysis", "statistic", "thematic", "regression", "descriptive"))
        return (words >= 90 and has_mapping, "The analysis section does not clearly show how each objective, question or hypothesis will be answered.", "Map every objective or hypothesis to the relevant variables or themes, data preparation steps and analysis technique.")
    if key == "ethical considerations":
        dimensions = sum(any(term in low for term in group) for group in (
            ("approval", "ethics committee", "review board"),
            ("consent", "voluntary"),
            ("confidential", "anonymous", "privacy"),
            ("data storage", "security", "access"),
            ("risk", "harm", "withdraw"),
        ))
        return (dimensions >= 3, "The ethics section does not cover the main protections required for the study.", "State the approval process, informed consent, voluntary participation, confidentiality or anonymity, data protection and participant risk arrangements as applicable.")
    if key == "theoretical review":
        has_theory = any(term in low for term in ("theory", "framework", "model"))
        has_application = any(term in low for term in ("study", "variable", "construct", "explain", "predict", "relationship"))
        return (words >= 90 and has_theory and has_application, "The theoretical review does not yet explain clearly how the selected theory or theories apply to the study variables and relationships.", "Present the main propositions of each theory, justify its selection, map it to the study variables or themes and identify what it explains that the other theories do not.")
    if key == "conceptual review":
        has_definition = any(term in low for term in ("defined as", "refers to", "conceptualised", "conceptualized"))
        return (words >= 100 and has_definition, "The conceptual review does not yet define and distinguish the study's main constructs adequately.", "Define each central construct from relevant scholarship, compare alternative meanings, state the dimensions adopted and keep the conceptual meaning consistent with the instrument or analytical definition.")
    if key == "empirical review":
        citation_years = len(re.findall(r"\b(?:19|20)\d{2}[a-z]?\b", text))
        synthesis = sum(term in low for term in ("however", "in contrast", "similarly", "whereas", "although", "difference", "consistent", "contradict"))
        return (words >= 180 and citation_years >= 3 and synthesis >= 2, "The empirical review is present but remains largely descriptive and does not compare the evidence deeply enough.", "Organise the evidence around the objectives or relationships and compare studies by context, design, sample, measurement, findings, contradictions and limitations before stating the unresolved gap.")
    if key == "literature gap synthesis":
        has_gap = any(term in low for term in ("gap", "limited", "unresolved", "not examined", "few studies", "inconsistent", "unknown"))
        return (words >= 45 and has_gap, "The literature synthesis does not state a precise, evidence-based gap that leads to the present study.", "Summarise what is established, where the evidence is inconsistent or incomplete, and the exact contextual, theoretical, methodological or relational gap the study addresses.")
    if key == "conceptual framework":
        relation = any(term in low for term in ("relationship", "influence", "effect", "predict", "moderate", "mediate", "independent variable", "dependent variable"))
        return (words >= 55 and relation, "The conceptual framework is present but its variables, directions and expected relationships are not explained clearly enough.", "Identify every variable or theme, show the expected directions and interaction or mediation paths where relevant, and explain how the framework follows from the theory, evidence and objectives.")
    if key == "hypothesis development":
        relation = any(term in low for term in ("hypothesis", "h0", "expected", "relationship", "influence", "effect"))
        return (words >= 50 and relation, "The hypothesis-development section does not yet derive the testable propositions from theory and empirical evidence.", "For each inferential objective, synthesise the relevant theoretical and empirical argument and end with one clearly numbered, testable hypothesis using the same constructs and population as the study.")
    if key == "research philosophy paradigm":
        rationale = any(term in low for term in ("because", "appropriate", "suitable", "assumption", "ontology", "epistemology"))
        return (words >= 55 and rationale, "The research philosophy or paradigm is named but not justified in relation to the study's questions, evidence and design.", "State the philosophical assumptions adopted and explain how they support the research approach, type of evidence and interpretation used in the study.")
    if key == "research approach":
        identified = any(term in low for term in ("quantitative", "qualitative", "mixed method", "deductive", "inductive", "abductive"))
        return (words >= 40 and identified, "The research approach is not identified and justified clearly enough.", "Name the approach and explain why it is suitable for the objectives, type of data, analytical strategy and claims the study can make.")
    if key == "research design":
        identified = any(term in low for term in ("survey", "case study", "cross sectional", "cross-sectional", "experimental", "correlational", "explanatory", "descriptive", "phenomenological"))
        rationale = any(term in low for term in ("appropriate", "suitable", "because", "allows", "enabled"))
        return (words >= 65 and identified and rationale, "The research design is not described and justified sufficiently for the study.", "Name the design, explain what it permits the researcher to examine, state its time dimension and unit of analysis, and acknowledge the limits it places on causal or generalisable claims.")
    if key == "study area":
        relevance = any(term in low for term in ("located", "region", "district", "municipality", "institution", "selected because", "relevant"))
        return (words >= 45 and relevance, "The study area is described without showing why it is relevant to the research problem and population.", "Describe only the characteristics needed to understand the setting, justify its selection and connect those characteristics to the research problem and accessible population.")
    if key == "population":
        units = any(term in low for term in ("population", "participant", "respondent", "firm", "institution", "employee", "student", "teacher", "record"))
        number = bool(re.search(r"\b\d{2,}\b", text))
        return (words >= 35 and units and number, "The population section does not identify the target and accessible population precisely enough.", "Define the target and accessible populations, give their verified sizes and sources, specify the unit of analysis and state the inclusion and exclusion criteria.")
    if key == "sampling frame":
        source = any(term in low for term in ("register", "list", "database", "sampling frame", "records", "roster"))
        return (words >= 30 and source, "The sampling frame is not described sufficiently to show who had a chance of selection.", "Identify the source and date of the sampling frame, explain how it was checked for completeness and show how it connects to the accessible population and sampling procedure.")
    if key == "sampling procedure":
        steps = sum(term in low for term in ("random", "stratified", "purposive", "systematic", "cluster", "stage", "selected", "proportion"))
        return (words >= 65 and steps >= 2, "The sampling procedure is not described as a reproducible sequence of selection steps.", "State each sampling stage, the sampling technique used, how units were selected, numbers selected from each group and how replacement or non-response was handled.")
    if key == "sample size":
        basis = any(term in low for term in ("formula", "power", "effect size", "confidence level", "margin of error", "census", "sample size table"))
        number = bool(re.search(r"\b\d{2,}\b", text))
        return (words >= 35 and basis and number, "The sample size is stated without a sufficiently clear and defensible justification.", "Show the population value and the formula, power analysis, census decision or other basis used, state the assumptions and explain any allowance for non-response or subgroup analysis.")
    if key == "data sources":
        source = any(term in low for term in ("primary data", "secondary data", "questionnaire", "interview", "annual report", "database", "records"))
        return (words >= 25 and source, "The sources of data are not identified precisely enough for verification.", "State each data source, the period covered, the unit represented, who produced or supplied it and why it is suitable for the study objectives.")
    if key == "data collection instrument":
        details = sum(term in low for term in ("questionnaire", "interview guide", "section", "item", "scale", "source", "adapted", "developed"))
        return (words >= 75 and details >= 3, "The instrument section does not explain the structure, source and measurement content sufficiently.", "Describe each instrument section, item source, adaptation, response format, scoring direction and the construct or objective measured. Attach the final instrument in the appendix.")
    if key == "operationalisation and measurement":
        details = sum(term in low for term in ("variable", "construct", "item", "indicator", "scale", "score", "coding", "measurement", "dimension"))
        return (words >= 80 and details >= 4, "The operationalisation section does not show clearly how the study concepts become measurable variables or analysable themes.", "Provide a variable or construct register showing the conceptual definition, operational definition, dimensions, items or indicators, response anchors, coding, composite construction, expected direction and source.")
    if key == "pilot study pre testing":
        details = sum(term in low for term in ("pilot", "pretest", "pre-test", "participants", "reliability", "revision", "feedback", "excluded"))
        return (words >= 50 and details >= 3, "The pilot or pre-test is mentioned without enough information to judge what was tested and changed.", "State where and with whom the pilot was conducted, why they were comparable but excluded from the main sample, what was assessed and the revisions or coefficients that resulted.")
    if key == "validity and reliability":
        details = sum(term in low for term in ("content validity", "construct validity", "criterion", "reliability", "cronbach", "composite reliability", "trustworthiness", "triangulation", "member checking"))
        return (words >= 70 and details >= 2, "The quality assurance for the instrument or qualitative evidence is not documented sufficiently.", "Report the specific validity, reliability or trustworthiness procedures, the evidence or coefficients obtained, decision thresholds and any item or coding changes made.")
    if key == "data collection procedures":
        steps = sum(term in low for term in ("permission", "consent", "administer", "distributed", "collected", "interviewed", "trained", "duration", "response"))
        return (words >= 60 and steps >= 3, "The data-collection procedure is not described as a clear chronological process.", "State how access was obtained, who collected the data, how participants were approached, the period and setting, quality controls, follow-up and the number of usable responses or records obtained.")
    if key == "data preparation and screening":
        details = sum(term in low for term in ("missing", "outlier", "normality", "coding", "reverse", "data entry", "screen", "common method", "non response"))
        return (words >= 55 and details >= 2, "The data-preparation and screening steps are not reported sufficiently to support the later analysis.", "Explain data entry and coding, missing-data treatment, reverse scoring, outlier checks, distribution or assumption checks and any common-method or non-response assessment relevant to the design.")
    if key == "model specification":
        details = sum(term in low for term in ("equation", "dependent variable", "independent variable", "interaction", "control variable", "error term", "beta", "model"))
        return (words >= 55 and details >= 3, "The analytical model is not specified clearly enough to reproduce or interpret it.", "Present the equation or model structure, define every term, show the expected signs, include all required lower-order terms for interactions and link each model to the relevant objective or hypothesis.")
    if key in {"assumptions and diagnostic tests", "diagnostic tests"}:
        details = sum(term in low for term in ("normality", "linearity", "homoscedastic", "multicollinearity", "independence", "vif", "residual", "model fit", "diagnostic"))
        return (words >= 55 and details >= 2, "The required analytical assumptions and diagnostic decision rules are not reported adequately.", "State the diagnostics required by the selected method, the thresholds or decision rules, the corrective action for violations and where the verified results are reported.")
    if key == "response rate":
        numbers = len(re.findall(r"\b\d+(?:\.\d+)?%?\b", text))
        return (words >= 25 and numbers >= 2, "The response rate is not reported with enough information to verify the achieved sample.", "Report the number approached or distributed, returned, excluded and analysed, calculate the response rate correctly and discuss possible non-response where relevant.")
    if key == "sample characteristics":
        return (words >= 35, "The characteristics of the analysed sample are not described sufficiently to establish who contributed the evidence.", "Present the relevant participant, case or organisational characteristics with frequencies or appropriate summaries and reconcile all totals with the analysed sample.")
    if key == "data quality and preliminary checks":
        details = sum(term in low for term in ("missing", "outlier", "normality", "bias", "linearity", "descriptive", "screen", "assumption"))
        return (words >= 45 and details >= 2, "The preliminary checks needed before the main analysis are not reported adequately.", "Report the data-quality and preliminary checks relevant to the selected method, give the results and decision rules, and explain any exclusions, transformations or remedial action.")
    if key == "descriptive results":
        numeric = bool(re.search(r"\b(?:mean|standard deviation|frequency|percentage|median|range)\b", low))
        return (words >= 35 and numeric, "The descriptive results do not yet provide a clear numerical or thematic account of the relevant variables or questions.", "Present the descriptive evidence in the same order as the objectives, define any category rules, reconcile totals and interpret the values without making inferential or causal claims.")
    if key == "measurement quality":
        details = sum(term in low for term in ("reliability", "validity", "loading", "alpha", "composite reliability", "ave", "htmt", "factor", "item"))
        return (words >= 55 and details >= 2, "The measurement-quality evidence is incomplete for the constructs used in the analysis.", "Report the appropriate reliability and validity evidence, identify any deleted or reversed items, apply declared thresholds consistently and explain how the final composite scores or latent variables were formed.")
    if key == "results by objective":
        evidence = any(term in low for term in ("table", "coefficient", "theme", "finding", "result", "hypothesis", "research question"))
        return (words >= 80 and evidence, "The results are not presented clearly enough in the order of the objectives, questions or hypotheses.", "Organise the chapter by objective or hypothesis, present the complete table or qualitative evidence, state the decision using the reported statistic or theme and avoid interpretation that is not supported by the result.")
    if key == "discussion of findings":
        integration = sum(term in low for term in ("theory", "consistent", "contrary", "study", "because", "context", "explain", "implication"))
        return (words >= 120 and integration >= 3, "The discussion does not yet explain and evaluate the findings in relation to theory, prior evidence and the study context.", "Discuss each verified finding by stating what was found, explaining why, comparing it with relevant studies, relating it to the theoretical framework, considering alternative explanations and identifying its implication without overstating causality.")
    if key == "summary of the study":
        details = sum(term in low for term in ("purpose", "objective", "design", "population", "sample", "instrument", "analysis"))
        return (words >= 70 and details >= 3, "The summary of the study does not capture the purpose and main methodological decisions sufficiently.", "Summarise the problem or purpose, objectives, design, population and sample, data source or instrument and analytical approach without introducing new evidence.")
    if key == "summary of findings":
        return (words >= 70, "The summary of findings is not organised clearly around the research objectives or questions.", "State one concise, evidence-based finding for each objective or question, preserving the direction, significance and limits of the verified results without adding new analysis.")
    if key == "conclusions":
        return (words >= 55, "The conclusions do not yet answer the objectives directly or remain sufficiently limited to the verified findings.", "Draw one conclusion for each objective from the corrected findings, explain its meaning and avoid new evidence, causal claims or generalisation beyond the design and population.")
    if key == "recommendations":
        details = sum(term in low for term in ("should", "recommend", "institution", "management", "policy", "practitioner", "implement", "responsible"))
        return (words >= 55 and details >= 2, "The recommendations are not sufficiently specific, evidence-based and assigned to responsible actors.", "Link each recommendation to a verified finding and state who should act, what should be done, how it may be implemented and the problem it is expected to address.")
    if key == "contribution and implications":
        dimensions = sum(any(term in low for term in group) for group in (("theory", "theoretical"), ("method", "methodological"), ("practice", "practical", "professional"), ("policy", "regulation")))
        return (words >= 65 and dimensions >= 2, "The study's contribution and implications are not distinguished or supported clearly enough.", "State separately what the verified findings add to theory or knowledge, method where applicable, professional practice and policy, and explain how each claim follows from the study rather than from the topic alone.")
    if key == "suggestions for further research":
        basis = any(term in low for term in ("limitation", "future", "further", "different context", "longitudinal", "method"))
        return (words >= 35 and basis, "The suggestions for further research are too general or are not derived from the study's limitations and unresolved questions.", "Propose specific future studies linked to the limitations, unanswered mechanisms, populations, contexts, measures or designs that the present study could not address.")

    # Sections not listed above are assessed by the systematic model reviewer and
    # specialist method/results audits.  They pass the structural ledger when a
    # substantive heading and content are present.
    return (words >= 18, "The section is present but contains too little substantive content to perform its stated function.", f"Develop the {label} section with the specific evidence, decisions and explanations required by the study.")


def build_section_coverage_ledger(
    paragraphs: Sequence[Dict[str, Any]],
    *,
    academic_level: Any = "",
    depth: str = "standard",
    submission_scope: Any = "",
) -> Dict[str, Any]:
    current = _current_rows(paragraphs)
    degree = _degree_key(academic_level)
    flags = _route_flags(current)
    grouped = _group_by_heading(current)
    target_chapters = _submission_target_chapters(current, submission_scope)
    entries: List[Dict[str, Any]] = []

    if (
        os.getenv("VPROF_FULL_DOCUMENT_COMPONENT_AUDIT", "true").strip().lower() not in {"0", "false", "no", "off"}
        and _is_full_submission(current, submission_scope)
    ):
        for label, aliases, category, severity, mode in DOCUMENT_EXPECTED:
            applicable = _document_component_applicable(mode, flags)
            entry: Dict[str, Any] = {
                "chapter_number": 0,
                "document_level": True,
                "label": label,
                "aliases": list(aliases),
                "category": category,
                "severity": severity,
                "applicable": applicable,
                "status": SECTION_STATUS_NOT_APPLICABLE if not applicable else SECTION_STATUS_MISSING,
                "matched_heading": "",
                "paragraph_ids": [],
                "reason": "",
                "required_action": "",
            }
            if not applicable:
                entries.append(entry)
                continue
            rows, matched_heading, found_as_heading = _document_component_rows(current, grouped, label, aliases)
            if rows:
                adequate, reason, action = _document_component_adequacy(label, rows)
                entry["matched_heading"] = matched_heading
                entry["paragraph_ids"] = [paragraph_id(row) for row in rows if paragraph_id(row)]
                entry["reason"] = "" if adequate else reason
                entry["required_action"] = "" if adequate else action
                if not adequate:
                    entry["status"] = SECTION_STATUS_INADEQUATE
                elif found_as_heading or label == "Title Page":
                    entry["status"] = SECTION_STATUS_PRESENT
                else:
                    entry["status"] = SECTION_STATUS_EQUIVALENT
            entries.append(entry)

    for chapter in sorted(target_chapters):
        for label, aliases, category, severity in UCC_EXPECTED.get(chapter, []):
            applicable = _section_applicable(label, degree, flags)
            entry: Dict[str, Any] = {
                "chapter_number": chapter,
                "label": label,
                "aliases": list(aliases),
                "category": category,
                "severity": severity,
                "applicable": applicable,
                "status": SECTION_STATUS_NOT_APPLICABLE if not applicable else SECTION_STATUS_MISSING,
                "matched_heading": "",
                "paragraph_ids": [],
                "reason": "",
                "required_action": "",
            }
            if not applicable:
                entries.append(entry)
                continue

            rows = _find_rows(grouped, aliases, chapter=chapter)
            heading_rows = [row for row in rows if row.get("is_heading") and any(_contains_sequence(clean_text(row.get("text", "")), alias) for alias in aliases)]
            matched_heading = clean_text(heading_rows[0].get("text", "")) if heading_rows else ""
            found_as_heading = bool(heading_rows)
            if not rows and _contract_label_key(label) in _INLINE_EQUIVALENT_SECTIONS:
                rows = _find_content_rows(current, aliases, chapter=chapter)
            if rows:
                content = _plain([row for row in rows if not row.get("is_heading")])
                adequate, reason, action = _section_content_dimensions(label, content, degree)
                entry["matched_heading"] = matched_heading or clean_text(source_section(rows[0]))
                entry["paragraph_ids"] = [paragraph_id(row) for row in rows if paragraph_id(row)]
                entry["reason"] = "" if adequate else reason
                entry["required_action"] = "" if adequate else action
                if not adequate:
                    entry["status"] = SECTION_STATUS_INADEQUATE
                elif found_as_heading and _canonical_alias(label, matched_heading):
                    entry["status"] = SECTION_STATUS_PRESENT
                else:
                    entry["status"] = SECTION_STATUS_EQUIVALENT
            entries.append(entry)

    applicable_entries = [entry for entry in entries if entry["status"] != SECTION_STATUS_NOT_APPLICABLE]
    assessed = len(applicable_entries)
    complete = all(entry["status"] in {SECTION_STATUS_PRESENT, SECTION_STATUS_EQUIVALENT, SECTION_STATUS_INADEQUATE, SECTION_STATUS_MISSING} for entry in applicable_entries)
    counts: Dict[str, int] = {}
    for entry in entries:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    return {
        "mode": "deterministic_required_section_contract",
        "academic_level": degree,
        "route_flags": flags,
        "target_chapters": sorted(target_chapters),
        "full_submission": _is_full_submission(current, submission_scope),
        "entries": entries,
        "counts": counts,
        "applicable_section_count": assessed,
        "complete": complete,
    }


def expected_sections_for_scope(paragraphs: Sequence[Dict[str, Any]]) -> List[Tuple[int, str, List[str], str, str]]:
    chapters = _chapter_scope(paragraphs)
    if not chapters:
        return []
    full_thesis = {1, 2, 3, 4, 5}.issubset(chapters)
    target_chapters = sorted(chapters if not full_thesis else {1, 2, 3, 4, 5})
    out: List[Tuple[int, str, List[str], str, str]] = []
    for chapter in target_chapters:
        for label, names, category, severity in UCC_EXPECTED.get(chapter, []):
            out.append((chapter, label, names, category, severity))
    return out


def present_relevant_sections(paragraphs: Sequence[Dict[str, Any]]) -> Set[str]:
    grouped = _group_by_heading(paragraphs)
    labels: Set[str] = set()
    if _title_anchor(paragraphs):
        labels.add("Title")
    for _chapter, label, names, _category, _severity in expected_sections_for_scope(paragraphs):
        if _find_rows(grouped, names):
            labels.add(label)
    if _find_rows(grouped, ["references"]):
        labels.add("References")
    return labels


def ucc_comment_floor(paragraphs: Sequence[Dict[str, Any]], academic_level: Any, depth: str) -> int:
    """No predetermined UCC comment floor.

    The UCC structure remains a coverage guide, but it cannot force a minimum
    number of findings. Only evidence-backed issues are released.
    """
    return 0


def _study_terms_for_chapter(paragraphs: Sequence[Dict[str, Any]], chapter: int, limit: int = 6) -> List[str]:
    text = " ".join(
        clean_text(row.get("text", ""))
        for row in _current_rows(paragraphs)
        if row.get("chapter_number") in {None, chapter}
    )
    candidates: List[str] = []
    # Prefer recognisable constructs explicitly present in the current study.
    for phrase in re.findall(
        r"\b(?:classroom incivility|academic entitlement|academic engagement|academic achievement|academic performance|perceived academic support|perceived value|teacher self-efficacy|instructional practices|organisational performance|erratic power supply|internally generated funds|social studies)\b",
        text,
        flags=re.I,
    ):
        candidates.append(clean_text(phrase))
    # Fall back to title/purpose patterns only after explicit construct phrases.
    for pattern in (
        r"(?:effect|influence|impact|relationship)\s+of\s+(.+?)\s+on\s+(.+?)(?:\s+among|\s+in\s+|[.:]|$)",
        r"moderating\s+role\s+of\s+(.+?)(?:\s+among|\s+in\s+|[.:]|$)",
    ):
        match = re.search(pattern, text, flags=re.I)
        if match:
            candidates.extend(clean_text(value) for value in match.groups() if clean_text(value))
    output: List[str] = []
    for value in candidates:
        value = re.sub(r"\s+", " ", value).strip(" ,;:-")
        if re.match(r"^(?:these|those|this|their|the)\b", value, flags=re.I) and len(value.split()) > 4:
            continue
        if value and normalised(value) not in {normalised(item) for item in output}:
            output.append(value)
        if len(output) >= limit:
            break
    return output


def _missing_section_example(label: str, terms: Sequence[str]) -> str:
    key = _contract_label_key(label)
    joined = ", ".join(terms[:3])
    if key == "title page":
        return "Use the approved institutional format to show the study title, candidate name, programme, institution and submission year."
    if key == "declaration":
        return "Insert the approved candidate and supervisor declaration statements with the required names, signatures and dates."
    if key == "abstract":
        return "Summarise the purpose, design, population and sample, instrument or data source, analysis, principal findings, conclusion and main recommendation in one self-contained abstract."
    if key == "table of contents":
        return "Generate the contents from the final heading styles and confirm that every chapter, section and page number agrees with the work."
    if key == "list of tables":
        return "List every numbered table with its exact title and final page number."
    if key == "list of figures":
        return "List every numbered figure with its exact title and final page number."
    if key == "references":
        return "Provide one complete reference entry for every in-text citation and remove entries that are not cited in the study."
    if key == "appendices supporting instruments":
        return "Attach the final questionnaire, interview guide, observation schedule or data-extraction form and label each appendix clearly."
    if key == "definition of terms":
        return (
            f"Define {joined} as they are used and measured in the study."
            if joined else
            "Define each main construct as it is used and measured in the study, rather than copying a general dictionary definition."
        )
    if key == "limitations of the study":
        return "State the limitations arising from the design, sample, measurement and data collection, and explain how each one restricts interpretation or generalisation."
    if key in {"scope delimitation of the study", "delimitations of the study", "delimitation of the study"}:
        return "State the population, location, variables or themes, period covered and the boundaries deliberately excluded from the study."
    if key == "purpose of the study":
        return (
            f"State in one sentence that the study examines {joined}, followed by the confirmed population and setting."
            if joined else
            "State the overall aim in one clear sentence using the same constructs, population and setting as the title and objectives."
        )
    if key == "research hypotheses":
        return (
            f"Formulate testable null hypotheses for the inferential relationships involving {joined}, using the same direction and population as the objectives."
            if joined else
            "Formulate one testable null hypothesis for each inferential objective, or explain why the approved format uses research questions only."
        )
    if key == "statement of the problem":
        return (
            f"Use verified evidence to show the problem involving {joined}, identify what previous studies have not resolved and end with the exact focus of the study."
            if joined else
            "Use verified evidence to show the practical problem, identify the unresolved research gap and end with the exact focus of the study."
        )
    if key == "significance of the study":
        return (
            f"Explain separately how findings on {joined} may add to knowledge, improve professional practice and inform policy in the study setting."
            if joined else
            "Explain separately what the study may add to knowledge, professional practice and policy."
        )
    if key == "research objectives":
        return (
            f"Use measurable verbs and state one objective for each aspect of {joined} that the proposed data and analysis can answer."
            if joined else
            "Use measurable verbs and ensure that every objective can be answered by the proposed data source and analysis."
        )
    if key == "research questions":
        return (
            f"Write one clear question for each descriptive objective involving {joined}, using the same population and setting."
            if joined else
            "Write one clear research question for each descriptive objective using the same constructs, population and setting."
        )
    if key == "background to the study":
        return "Develop the discussion from the wider context to the specific study setting, then lead clearly to the problem being investigated."
    if key == "research questions":
        return "Write one clear research question for each objective and retain the same constructs, population and setting in both sections."
    if key == "organisation of the study" or key == "organization of the study":
        return "Give one concise sentence explaining the purpose and main content of each chapter."
    return "Add the section under a clear heading and ensure that its content performs the academic purpose expected in that chapter."


def _insertion_anchor_for_missing(
    paragraphs: Sequence[Dict[str, Any]],
    chapter: int,
    label: str,
) -> Optional[Dict[str, Any]]:
    if chapter == 0:
        current = _current_rows(paragraphs)
        if _contract_label_key(label) in {"title page", "declaration", "abstract", "table of contents", "list of tables", "list of figures"}:
            return (current[0] if current else None)
        return (current[-1] if current else None)
    order = [spec[0] for spec in UCC_EXPECTED.get(chapter, [])]
    try:
        target_index = order.index(label)
    except ValueError:
        return _first_chapter_anchor(paragraphs, chapter)
    grouped = _group_by_heading(paragraphs)
    # Prefer the last substantive row of the closest preceding section, so the
    # comment indicates where the missing section should be inserted.
    for previous in reversed(UCC_EXPECTED.get(chapter, [])[:target_index]):
        rows = _find_rows(grouped, previous[1], chapter=chapter)
        substantive = [row for row in rows if not row.get("is_heading") and clean_text(row.get("text", ""))]
        if substantive:
            return substantive[-1]
    # Otherwise use the heading of the next available section.
    for following in UCC_EXPECTED.get(chapter, [])[target_index + 1:]:
        rows = _find_rows(grouped, following[1], chapter=chapter)
        heading = next((row for row in rows if row.get("is_heading")), None)
        if heading:
            return heading
    return _first_chapter_anchor(paragraphs, chapter)


def _missing_section_issue(
    paragraphs: Sequence[Dict[str, Any]],
    chapter: int,
    label: str,
    category: str,
    severity: str,
    degree: str,
    aliases: Optional[Sequence[str]] = None,
) -> Optional[Dict[str, Any]]:
    anchor = _insertion_anchor_for_missing(paragraphs, chapter, label)
    sev = severity if degree in {"research_masters", "professional_doctorate", "phd"} else ("major" if severity == "critical" else severity)
    chapter_words = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five"}
    chapter_label = "the complete work" if chapter == 0 else f"Chapter {chapter_words.get(chapter, chapter)}"
    purposes = {
        "Title Page": "It identifies the approved study, candidate, programme, institution and submission details.",
        "Declaration": "It records the candidate's originality statement and the required supervisory confirmation.",
        "Abstract": "It gives a self-contained summary of the purpose, method, main findings and conclusion.",
        "Table of Contents": "It provides the navigational structure of the complete work.",
        "List of Tables": "It helps the reader locate and verify every numbered table.",
        "List of Figures": "It helps the reader locate and verify every numbered figure.",
        "References": "It provides the full bibliographic details needed to verify every source used in the study.",
        "Appendices / Supporting Instruments": "It supplies the instrument and supporting evidence needed to assess how the data were collected and analysed.",
        "Definition of Terms": "It helps the reader understand the exact meaning and measurement of the main concepts used in the study.",
        "Limitations of the Study": "It shows the constraints that affect the interpretation, transferability or generalisation of the findings.",
        "Delimitations of the Study": "It states the boundaries of the study so the reader knows what was included and excluded.",
        "Background to the Study": "It provides the context and evidence needed to lead the reader to the research problem.",
        "Research Questions": "It translates the objectives into answerable questions and guides the analysis.",
        "Research Hypotheses": "It states the propositions tested by inferential analyses and keeps the objectives, analysis and decisions aligned.",
        "Purpose of the Study": "It states the overall aim and connects the title, problem, objectives and methods.",
        "Organisation of the Study": "It gives the reader a clear guide to the remaining chapters.",
    }
    terms = _study_terms_for_chapter(paragraphs, chapter)
    issue = _issue(
        code=f"CH{chapter}-MISSING-{normalised(label).replace(' ', '-').upper()}",
        section=chapter_label,
        title=f"{label} is missing from {chapter_label}",
        assessment=f"{label} is missing from {chapter_label}. This component is required in a complete UCC research work. {purposes.get(label, 'It is needed to complete the academic structure of the work.')}",
        action=f"Add a clearly labelled {label} in the appropriate position and develop it using the actual focus and evidence of the study.",
        example=_missing_section_example(label, terms),
        study_terms=terms,
        missing_section_label=label,
        chapter_number=chapter,
        anchor=anchor,
        category=category,
        degree=degree,
        severity=sev,
        confidence=0.91,
    )
    if issue:
        issue["section_contract_verified"] = True
        issue["section_status"] = SECTION_STATUS_MISSING
        issue["section_contract_label"] = label
        issue["section_aliases"] = list(aliases or [])
        issue["suggested_insertion_after"] = clean_text(source_section(anchor)) if anchor else ""
    return issue


def _inadequate_section_issue(
    paragraphs: Sequence[Dict[str, Any]],
    entry: Dict[str, Any],
    degree: str,
) -> Optional[Dict[str, Any]]:
    chapter = int(entry.get("chapter_number") or 0)
    ids = set(entry.get("paragraph_ids") or [])
    rows = [row for row in _current_rows(paragraphs) if paragraph_id(row) in ids]
    anchor = _first_substantive(rows) or next((row for row in rows if row.get("is_heading")), None) or _first_chapter_anchor(paragraphs, chapter)
    label = clean_text(entry.get("label"))
    issue = _issue(
        code=f"CH{chapter}-INADEQUATE-{normalised(label).replace(' ', '-').upper()}",
        section=clean_text(entry.get("matched_heading")) or label,
        title=f"The {label} section is present but does not yet perform its full purpose",
        assessment=clean_text(entry.get("reason")) or f"The {label} section is present but is not sufficiently developed for this study.",
        action=clean_text(entry.get("required_action")) or f"Strengthen the {label} section using the study's actual evidence and design.",
        example=_missing_section_example(label, _study_terms_for_chapter(paragraphs, chapter)),
        study_terms=_study_terms_for_chapter(paragraphs, chapter),
        chapter_number=chapter,
        anchor=anchor,
        category=clean_text(entry.get("category")) or "chapter_structure",
        degree=degree,
        severity="major" if clean_text(entry.get("severity")) == "critical" else clean_text(entry.get("severity")) or "major",
        confidence=0.90,
    )
    if issue:
        issue["section_contract_verified"] = True
        issue["section_status"] = SECTION_STATUS_INADEQUATE
        issue["section_contract_label"] = label
        issue["section_aliases"] = list(entry.get("aliases") or [])
    return issue


def _thin_section_issue(label: str, rows: Sequence[Dict[str, Any]], category: str, severity: str, degree: str) -> Optional[Dict[str, Any]]:
    text = _plain([row for row in rows if not row.get("is_heading")])
    if len(text.split()) >= 45:
        return None
    anchor = _first_substantive(rows)
    return _issue(
        code=f"THIN-{normalised(label).replace(' ', '-').upper()}",
        section=label,
        title=f"The {label} section needs further development",
        assessment=f"The {label} section is present, but it is too brief to perform its purpose adequately at {_degree_label(degree)}.",
        action=f"Expand the {label} section with the specific evidence, explanation and links needed for this study.",
        anchor=anchor,
        category=category,
        degree=degree,
        severity="major" if severity == "critical" else severity,
        confidence=0.80,
    )


def _citation_tokens(text: str) -> Set[str]:
    hits: Set[str] = set()
    for match in re.finditer(r"\(([A-Z][A-Za-z'’\-]+(?:\s+et\s+al\.)?|[A-Z][A-Za-z'’\-]+\s*&\s*[A-Z][A-Za-z'’\-]+)[^)]*?,\s*(?:19|20)\d{2}\)", text):
        first = re.split(r"\s*&\s*|\s+et\s+al\.", match.group(1))[0]
        hits.add(normalised(first))
    return hits


def _reference_author_tokens(text: str) -> Set[str]:
    refs = False
    tokens: Set[str] = set()
    for line in text.splitlines():
        if normalised(line) == "references":
            refs = True
            continue
        if refs:
            match = re.match(r"\s*([A-Z][A-Za-z'’\-]+),", line)
            if match:
                tokens.add(normalised(match.group(1)))
    return tokens


def _first_citation_anchor(paragraphs: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    pattern = re.compile(r"\([^)]*(?:19|20)\d{2}[^)]*\)")
    for row in _current_rows(paragraphs):
        if pattern.search(clean_text(row.get("text", ""))):
            return row
    return _first_chapter_anchor(paragraphs, 1)


def _has_references_heading(grouped: Dict[str, List[Dict[str, Any]]]) -> bool:
    return bool(_find_rows(grouped, ["references", "reference list", "bibliography"]))


def _citation_count(text: str) -> int:
    return len(re.findall(r"\([^)]*(?:19|20)\d{2}[^)]*\)", text))


def _duplicated_parenthetical_citations(text: str) -> List[str]:
    raw = re.findall(r"\(([^)]*(?:19|20)\d{2}[^)]*)\)", text)
    counts: Dict[str, int] = {}
    for item in raw:
        key = normalised(item)
        if key:
            counts[key] = counts.get(key, 0) + 1
    return [k for k, v in counts.items() if v > 1]


def _chapter_one_specific(paragraphs: Sequence[Dict[str, Any]], grouped: Dict[str, List[Dict[str, Any]]], degree: str) -> List[Dict[str, Any]]:
    issues: List[Optional[Dict[str, Any]]] = []
    background = _find_rows(grouped, ["background to the study", "background of the study"], chapter=1)
    problem = _find_rows(grouped, ["statement of the problem", "problem statement"], chapter=1)
    purpose = _find_rows(grouped, ["purpose of the study", "aim of the study", "general aim"], chapter=1)
    objectives = _find_rows(grouped, ["research objectives", "objectives of the study", "general objective", "main objective", "specific objectives", "specific objective"], chapter=1)
    questions = _find_rows(grouped, ["research questions", "research question"], chapter=1)
    significance = _find_rows(grouped, ["significance of the study"], chapter=1)
    limitations = _find_rows(grouped, ["limitations of the study", "limitation of the study"], chapter=1)
    delimitation = _find_rows(grouped, ["delimitation of the study", "delimitations of the study", "scope and delimitation of the study", "scope of the study"], chapter=1)
    definitions = _find_rows(grouped, ["definition of terms", "definition of key terms", "definition of key concepts", "definition of concepts", "operational definition of terms", "operational definitions"], chapter=1)
    references = _find_rows(grouped, ["references"])
    full_text = _plain(_current_rows(paragraphs))
    bg = _plain(background)
    prob = _plain(problem)
    purp = _plain(purpose)
    obj = _plain(objectives)
    qs = _plain(questions)
    sig = _plain(significance)
    lim = _plain(limitations)
    delim = _plain(delimitation)
    defs = _plain(definitions)
    refs = _plain(references)


    if background:
        low_bg = normalised(bg)
        has_theory_or_framework = bool(re.search(r"\b(?:theor(?:y|ies|etical)|conceptual|framework)\b", low_bg))
        if degree in {"research_masters", "professional_doctorate", "phd"} and not has_theory_or_framework:
            issues.append(_issue(
                code="CH1-BACKGROUND-THEORY",
                section="Background to the Study",
                title="The background does not establish a clear theoretical or conceptual anchor",
                assessment="The background introduces several central constructs but does not make the theoretical or conceptual logic binding them explicit.",
                action="Add a concise theoretical or conceptual anchor and show how it explains the expected relationship among the main independent variables, outcome variables and contextual factors in the study.",
                anchor=_first_substantive(background),
                category="theoretical_grounding",
                degree=degree,
                severity="major",
            ))
        context_claim = bool(re.search(
            r"\b(?:in|within|among|at)\s+(?:the\s+)?[A-Z][A-Za-z0-9&'’., -]{3,80}\b",
            bg,
        ))
        if context_claim and len(bg.split()) >= 80 and not has_traceable_context_evidence(bg):
            issues.append(_issue(
                code="CH1-BACKGROUND-LOCAL-EVIDENCE",
                section="Background to the Study",
                title="The study context is named but not adequately evidenced",
                assessment="The section identifies a specific context but does not provide traceable local empirical, institutional or policy evidence showing why that context requires investigation.",
                action="Add recent evidence from the confirmed study setting, such as official data, policy or regulatory documents, institutional records or relevant empirical studies, and connect it directly to the problem.",
                anchor=_first_substantive(background),
                category="research_gap_and_problem",
                degree=degree,
                severity="major",
            ))
        uncited_count_anchor = next(
            (row for row in background if any(contains_uncited_empirical_count(sentence) for sentence in re.split(r"(?<=[.!?])\s+", clean_text(row.get("text", ""))))),
            None,
        )
        if uncited_count_anchor:
            issues.append(_issue(
                code="CH1-BACKGROUND-SAMPLE-CLAIM",
                section="Background to the Study",
                title="A specific empirical count is not clearly sourced",
                assessment="The section reports a numerical sample, population or empirical count without an adjacent citation supporting that exact claim.",
                action="Attach the authentic source in the same sentence as the numerical claim and verify the full reference, or remove or qualify the claim if it cannot be confirmed.",
                anchor=uncited_count_anchor,
                category="citations_and_sources",
                degree=degree,
                severity="major",
            ))
        if "the study revolve" in low_bg:
            issues.append(_issue(
                code="CH1-BACKGROUND-GRAMMAR",
                section="Background to the Study",
                title="The opening sentence contains a basic grammatical error",
                assessment="The opening sentence uses 'The study revolve', which is incorrect and weakens the academic presentation of the chapter.",
                action="Correct the opening sentence and carry out a line-by-line language edit of the chapter before resubmission.",
                anchor=_first_substantive(background),
                category="academic_writing",
                degree=degree,
                severity="moderate",
            ))

    if problem:
        low_prob = normalised(prob)
        if len(prob.split()) >= 45 and not has_traceable_context_evidence(prob):
            issues.append(_issue(
                code="CH1-PROBLEM-EVIDENCE",
                section="Statement of the Problem",
                title="The problem statement lacks concrete empirical, institutional or policy evidence",
                assessment="The problem is argued mainly through broad statements rather than traceable evidence showing its existence, scale or consequences in the confirmed study context.",
                action="Insert credible evidence from the confirmed setting, explain what remains unresolved and connect that gap directly to the study constructs and purpose.",
                anchor=_first_substantive(problem),
                category="research_gap_and_problem",
                degree=degree,
                severity="major",
            ))
        if re.search(r"\b(?:cannot|may not|should not)\s+be\s+(?:extrapolated|generalised|generalized|transferred|applied)\b", prob, flags=re.I):
            issues.append(_issue(
                code="CH1-PROBLEM-GAP-LOGIC",
                section="Statement of the Problem",
                title="The practical problem, empirical gap and contextual gap are not clearly separated",
                assessment="The section argues that evidence from another context cannot simply be transferred, but it does not clearly separate the practical problem from the empirical, contextual and methodological gaps.",
                action="Rewrite the section in connected moves: practical problem, evidence of seriousness, unresolved issue in earlier studies, relevance of the confirmed context and exact research focus.",
                anchor=_first_substantive(problem),
                category="research_gap_and_problem",
                degree=degree,
                severity="major",
            ))

    if purpose and objectives:
        missing_focuses = omitted_objective_focuses(purp, obj)
        if missing_focuses:
            issues.append(_issue(
                code="CH1-PURPOSE-OBJECTIVE-COVERAGE",
                section="Purpose of the study",
                title="The purpose statement is narrower than the objectives",
                assessment=f"The purpose does not represent all substantive focuses introduced in the objectives, including {', '.join(missing_focuses)}.",
                action="Broaden the purpose to cover every principal construct and outcome, or remove objectives that fall outside the intended study purpose. Then recheck alignment with the questions, hypotheses and methods.",
                anchor=_first_substantive(purpose),
                category="objectives_questions_hypotheses",
                degree=degree,
                severity="critical" if degree in {"research_masters", "professional_doctorate", "phd"} else "major",
            ))

    if objectives:
        low_obj = normalised(obj)
        if any(t in low_obj for t in ("relationship", "impact", "effect", "influence")) and any(t in low_obj for t in ("examine", "assess")):
            issues.append(_issue(
                code="CH1-OBJECTIVES-MIXED-INFERENCE",
                section="Research Objectives",
                title="The objectives mix descriptive, relational and impact claims without clarifying the intended level of inference",
                assessment="The objective set moves from describing current practices to assessing relationships and examining impact, but the chapter does not yet clarify how the design will support each type of inference.",
                action="Revise the objectives and methods together so each objective has a clear analytical status: descriptive, associational, predictive or causal, with wording that the design can support.",
                anchor=_first_substantive(objectives),
                category="objectives_questions_hypotheses",
                degree=degree,
                severity="major" if degree in {"research_masters", "professional_doctorate", "phd"} else "moderate",
            ))

        if purpose and "cross sectional" in normalised(full_text) and any(t in normalised(purp) for t in ("effect", "impact", "influence")):
            issues.append(_issue(
                code="CH1-PURPOSE-CAUSAL-LANGUAGE",
                section="Purpose of the study",
                title="Causal or impact language may exceed the implied design",
                assessment="The purpose uses effect language, while the chapter later recognises limits to causal inference from a cross-sectional design.",
                action="Use neutral associational language unless the methodology can justify causal inference, or explain clearly how the design supports effect or impact claims.",
                anchor=_first_substantive(purpose),
                category="methodological_rigour",
                degree=degree,
                severity="major",
                confidence=0.88,
            ))

    if questions:
        combined = normalised(obj + "\n" + qs)
        has_rel = any(t in combined for t in ("relationship", "impact", "effect", "influence", "determinant"))
        has_hyp = any("hypothes" in normalised(row.get("text", "")) for row in _current_rows(paragraphs))
        if has_rel and not has_hyp and degree in {"research_masters", "professional_doctorate", "phd"}:
            issues.append(_issue(
                code="CH1-HYPOTHESES-MISSING",
                section="Research Questions",
                title="Relational and impact objectives are not supported by hypotheses or justification",
                assessment="The objectives and questions imply relationship or impact testing, but no hypotheses or justification for their absence is provided.",
                action="Where required by the programme format and supported by the research design, formulate hypotheses for the relational objectives; otherwise explain why research questions alone are appropriate.",
                anchor=_first_substantive(questions),
                category="objectives_questions_hypotheses",
                degree=degree,
                severity="major",
            ))
        if ".?" in qs:
            issues.append(_issue(
                code="CH1-RQ-PUNCTUATION",
                section="Research Questions",
                title="A research question contains malformed punctuation",
                assessment="One research question ends with a full stop followed by a question mark.",
                action="Remove the full stop and retain only the question mark.",
                anchor=next((row for row in questions if ".?" in clean_text(row.get("text", ""))), _first_substantive(questions)),
                category="academic_writing",
                degree=degree,
                severity="moderate",
            ))

    if significance:
        low_sig = normalised(sig)
        if any(t in low_sig for t in ("results reveal", "findings obtained", "study evaluates the impact of these results")):
            issues.append(_issue(
                code="CH1-SIGNIFICANCE-PROSPECTIVE",
                section="Significance of the Study",
                title="The significance section presents anticipated findings as completed results",
                assessment="The section uses results/findings language even though Chapter One is written as a proposal.",
                action="Rewrite the significance prospectively, explaining what the eventual findings may contribute without stating that relationships have already been found.",
                anchor=_first_substantive(significance),
                category="chapter_structure",
                degree=degree,
                severity="major",
            ))
        if not all(t in low_sig for t in ("theory", "practice", "policy")):
            issues.append(_issue(
                code="CH1-SIGNIFICANCE-THEORY-PRACTICE-POLICY",
                section="Significance of the Study",
                title="The significance section does not adequately separate theory, practice and policy contribution",
                assessment="The section lists stakeholders but does not clearly organise the expected contribution across theory, practice and policy.",
                action="Reorganise the section around the scholarly, practical and policy value that is genuinely supported by the study's scope.",
                anchor=_first_substantive(significance),
                category="critical_analysis",
                degree=degree,
                severity="moderate",
            ))
        if any(t in low_sig for t in ("meta analysis", "correlation coefficients", "liu et al", "onukwulu")):
            issues.append(_issue(
                code="CH1-SIGNIFICANCE-LIT-OVERLOAD",
                section="Significance of the Study",
                title="The significance section contains literature-review material",
                assessment="Detailed empirical discussion and source comparison are placed in the significance section, where the emphasis should be expected contribution and beneficiaries.",
                action="Move detailed literature discussion to Chapter Two and keep the significance focused on the likely scholarly, practical and policy value of the study.",
                anchor=_first_substantive(significance),
                category="chapter_structure",
                degree=degree,
                severity="moderate",
            ))
        contribution_terms = ("contribution to knowledge", "original contribution", "applied contribution", "professional contribution", "contribution to practice", "contribution to policy")
        if not any(t in low_sig for t in contribution_terms):
            title = {
                "bachelors": "The expected contribution is not stated plainly",
                "non_research_masters": "The applied or professional contribution is not explicit",
                "research_masters": "The expected scholarly contribution is not explicit",
                "professional_doctorate": "The original contribution to practice or policy is not explicit",
                "phd": "The original contribution to knowledge is not explicit",
            }[degree]
            issues.append(_issue(
                code="CH1-SIGNIFICANCE-CONTRIBUTION",
                section="Significance of the Study",
                title=title,
                assessment="The section names beneficiaries but does not state clearly what the study is expected to add to knowledge, practice or policy.",
                action="Add a concise contribution statement that matches the study's design and scope, and distinguish that contribution from ordinary stakeholder usefulness.",
                anchor=_first_substantive(significance),
                category="critical_analysis",
                degree=degree,
                severity="critical" if degree in {"professional_doctorate", "phd"} else "major",
            ))

    if limitations and any(t in normalised(lim) for t in ("faced practical constraints", "could be achieved", "did not participate", "skewing the results")):
        issues.append(_issue(
            code="CH1-LIMITATIONS-TENSE",
            section="Limitations of the Study",
            title="The limitations section mixes proposal-stage and completed-study language",
            assessment="The section shifts between planned data collection and constraints that appear to have already occurred.",
            action="Use proposal-stage language throughout if the study has not been completed, or convert the whole section to completed-study reporting if fieldwork has already occurred.",
            anchor=_first_substantive(limitations),
            category="chapter_structure",
            degree=degree,
            severity="major",
        ))

    if delimitation and re.search(r"\[[^\]]*(insert|provide|specify|start month/year|end month/year)[^\]]*\]", delim, flags=re.I):
        issues.append(_issue(
            code="CH1-DELIMITATION-PLACEHOLDER",
            section="Delimitation of the Study",
            title="The delimitation contains an unresolved drafting placeholder",
            assessment="The time scope still contains bracketed template text instead of a verified data-collection period.",
            action="Replace the placeholder with the confirmed start and end month/year and ensure the same time boundary appears consistently in the methodology chapter.",
            anchor=next((row for row in delimitation if "[" in clean_text(row.get("text", ""))), _first_substantive(delimitation)),
            category="chapter_structure",
            degree=degree,
            severity="critical" if degree in {"research_masters", "professional_doctorate", "phd"} else "major",
        ))

    if definitions:
        low_defs = normalised(defs)
        circular_match = re.search(r"\b([a-z][a-z -]{2,40})\s+(?:means|refers to|is defined as)\s+(?:the\s+)?(?:extent|degree|level|state)\s+of\s+\1\b", low_defs, flags=re.I)
        absolute_match = re.search(r"\b(?:without|with no)\s+(?:causing|creating|producing)\s+(?:any|all)\s+(?:harm|damage|risk)\b|\bcompletely eliminates?\b", low_defs, flags=re.I)
        if circular_match or absolute_match:
            matched_phrase = circular_match.group(0) if circular_match else absolute_match.group(0)
            issues.append(_issue(
                code="CH1-DEFINITIONS-CIRCULAR",
                section="Definition of Terms",
                title="A core term is defined circularly or in unrealistically absolute language",
                assessment=f"The wording ‘{matched_phrase}’ does not establish a measurable conceptual boundary.",
                action="Replace circular or absolute wording with a definition that states the construct's dimensions, boundaries and measurable indicators.",
                anchor=next((row for row in definitions if matched_phrase.lower() in normalised(clean_text(row.get("text", "")))), _first_substantive(definitions)),
                category="objectives_questions_hypotheses",
                degree=degree,
                severity="major",
            ))

    if any(w in full_text for w in ("behavior", "organization", "labor")) and any(w in full_text for w in ("behaviour", "organisation", "labour")):
        anchor = next((row for row in _current_rows(paragraphs) if any(w in clean_text(row.get("text", "")) for w in ("behavior", "organization", "labor"))), _first_substantive(background))
        issues.append(_issue(
            code="CH1-SPELLING-CONVENTION",
            section=source_section(anchor) or "Chapter One",
            title="British and American spelling conventions are mixed",
            assessment="The chapter combines spellings such as behaviour/organisations with behavior/organization/labor.",
            action="Apply the required institutional spelling convention consistently across the chapter.",
            anchor=anchor,
            category="academic_writing",
            degree=degree,
            severity="minor",
        ))

    if references:
        cited = _citation_tokens(full_text)
        ref_authors = _reference_author_tokens(full_text)
        if len(ref_authors) >= max(10, len(cited) + 8):
            issues.append(_issue(
                code="CH1-REFERENCE-AUDIT",
                section="References",
                title="The reference list requires a cited-versus-uncited audit",
                assessment="The reference list is large relative to the number of visible in-text citations in Chapter One, so uncited or mismatched sources may remain.",
                action="Cross-check each in-text citation against the reference list and remove, add or correct entries so every source is traceable.",
                anchor=next((row for row in references if not row.get("is_heading")), _first_substantive(references)),
                category="citations_and_sources",
                degree=degree,
                severity="moderate",
                confidence=0.82,
            ))


    # Topic-safe generic Chapter One checks. These must not depend on a previous
    # sample thesis topic. They protect UCC section coverage across disciplines.
    full_low = normalised(full_text)
    if not _has_references_heading(grouped) and _citation_count(full_text) >= 5:
        issues.append(_issue(
            code="CH1-MISSING-REFERENCES",
            section="References",
            title="The reference list is missing despite visible in-text citations",
            assessment="The chapter contains several in-text citations, but no References or Bibliography section is evident in the work.",
            action="Add a complete reference list in the required style and verify that every in-text citation has a matching reference-list entry.",
            anchor=_first_citation_anchor(paragraphs),
            category="citations_and_sources",
            degree=degree,
            severity="critical" if degree in {"research_masters", "professional_doctorate", "phd"} else "major",
        ))

    if re.search(r"\w\(", full_text) or re.search(r"\)\s*,\s*\(", full_text):
        issues.append(_issue(
            code="CH1-CITATION-SPACING-DUPLICATION",
            section="Chapter One",
            title="Citation spacing and grouping need editorial correction",
            assessment="Several citations are attached to preceding words without a space or are placed as repeated separate parenthetical citations instead of being cleanly grouped.",
            action="Insert required spaces before citations, remove duplicate citations and group multiple sources according to the selected referencing style.",
            anchor=_first_citation_anchor(paragraphs),
            category="citations_and_sources",
            degree=degree,
            severity="moderate",
        ))

    if significance and "research gap" in normalised(sig):
        issues.append(_issue(
            code="CH1-GAP-MISPLACED-IN-SIGNIFICANCE",
            section="Significance of the Study",
            title="The research gap is placed inside the significance section rather than being fully developed in the problem logic",
            assessment="The significance section names a research gap, but the gap should be established earlier through the background and problem statement before the study's beneficiaries are discussed.",
            action="Move or restate the research gap in the background/problem sequence, then reserve the significance section for theoretical, empirical, policy and practical contributions.",
            anchor=_first_substantive(significance),
            category="research_gap_and_problem",
            degree=degree,
            severity="major",
        ))

    if limitations and any(term in normalised(lim) for term in ("generalization", "generalisation")) and "case study" in full_low:
        issues.append(_issue(
            code="CH1-LIMITATION-GENERALISATION",
            section="Limitations of the Study",
            title="The limitations section overstates generalisation from a case study",
            assessment="The chapter suggests that findings will be sufficient for generalisation even though the scope is confined to a single case setting.",
            action="Qualify the claim as analytical or contextual transferability unless the sampling design supports statistical generalisation beyond the case.",
            anchor=_first_substantive(limitations),
            category="methodological_rigour",
            degree=degree,
            severity="major",
        ))

    out: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for item in issues:
        if not item:
            continue
        key = str(item.get("finding_id"))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _generic_chapter_specific(paragraphs: Sequence[Dict[str, Any]], grouped: Dict[str, List[Dict[str, Any]]], degree: str, chapter: int) -> List[Dict[str, Any]]:
    issues: List[Optional[Dict[str, Any]]] = []
    if chapter == 2:
        lit_rows: List[Dict[str, Any]] = []
        for _label, names, _cat, _sev in UCC_EXPECTED[2]:
            lit_rows.extend(_find_rows(grouped, names, chapter=2))
        text = normalised(_plain(lit_rows))
        anchor = _first_substantive(lit_rows) or _first_chapter_anchor(paragraphs, 2)
        if degree in {"research_masters", "professional_doctorate", "phd"} and not any(t in text for t in ("however", "in contrast", "gap", "limitation", "contradict", "synthesis")):
            issues.append(_issue(code="CH2-CRITICAL-SYNTHESIS", section="Chapter Two: Literature Review", title="The literature review needs stronger critical synthesis", assessment="The chapter does not show enough explicit comparison, contradiction, limitation or synthesis across studies.", action="Organise the review around constructs, debates and relationships; compare methods and findings, then show how the synthesis leads to the study gap and framework.", anchor=anchor, category="critical_analysis", degree=degree, severity="major"))
        if degree in {"research_masters", "professional_doctorate", "phd"} and not any(t in text for t in ("theoretical framework", "conceptual framework", "theory")):
            issues.append(_issue(code="CH2-FRAMEWORK", section="Chapter Two: Literature Review", title="The literature review does not make the theoretical or conceptual framework evident", assessment="A research-intensive or doctoral thesis needs a clear framework rather than only a thematic literature review.", action="Add a theoretical or conceptual framework section and explicitly link its constructs to the objectives, hypotheses or propositions.", anchor=anchor, category="theoretical_grounding", degree=degree, severity="critical"))
    elif chapter == 3:
        method_rows: List[Dict[str, Any]] = []
        for _label, names, _cat, _sev in UCC_EXPECTED[3]:
            method_rows.extend(_find_rows(grouped, names, chapter=3))
        text = normalised(_plain(method_rows))
        anchor = _first_substantive(method_rows) or _first_chapter_anchor(paragraphs, 3)
        if not all(t in text for t in ("objective", "analysis")):
            issues.append(_issue(code="CH3-ANALYSIS-MAPPING", section="Chapter Three: Research Methods", title="The methods chapter does not clearly map analysis to each objective", assessment="The chapter should make the analytical route for every objective, research question or hypothesis explicit.", action="Add a table or narrative mapping each objective/question/hypothesis to data, variables, measurement and analysis technique.", anchor=anchor, category="methodological_rigour", degree=degree, severity="critical"))
        if "ethic" not in text:
            issues.append(_issue(code="CH3-ETHICS", section="Chapter Three: Research Methods", title="Ethical considerations are not evident", assessment="The chapter does not visibly address ethical approval, informed consent, confidentiality or data protection.", action="Add an ethics section covering approval, consent, confidentiality, data storage and participant risk as applicable.", anchor=anchor, category="ethics_and_integrity", degree=degree, severity="critical"))
    elif chapter == 4:
        rows: List[Dict[str, Any]] = []
        for _label, names, _cat, _sev in UCC_EXPECTED[4]:
            rows.extend(_find_rows(grouped, names, chapter=4))
        text = normalised(_plain(rows))
        anchor = _first_substantive(rows) or _first_chapter_anchor(paragraphs, 4)
        if not any(t in text for t in ("objective", "research question", "hypothesis")):
            issues.append(_issue(code="CH4-OBJECTIVE-ORDER", section="Chapter Four: Results and Discussion", title="Results are not clearly organised by objective, question or hypothesis", assessment="The chapter should make it easy to trace each result to the corresponding objective or hypothesis.", action="Present the results in the order of the objectives/questions/hypotheses and explicitly state which objective each table, figure or theme addresses.", anchor=anchor, category="results_and_interpretation", degree=degree, severity="critical"))
        if degree in {"research_masters", "professional_doctorate", "phd"} and not any(t in text for t in ("theory", "previous studies", "consistent with", "contrary to")):
            issues.append(_issue(code="CH4-DISCUSSION-INTEGRATION", section="Chapter Four: Results and Discussion", title="The discussion is not sufficiently integrated with theory and prior studies", assessment="Advanced thesis discussion must interpret findings through theory and prior empirical evidence, including contradictions and alternatives.", action="For each major finding, explain its meaning, compare it with theory and previous studies, and discuss contradictions or alternative explanations.", anchor=anchor, category="discussion_and_integration", degree=degree, severity="major"))
    elif chapter == 5:
        rows: List[Dict[str, Any]] = []
        for _label, names, _cat, _sev in UCC_EXPECTED[5]:
            rows.extend(_find_rows(grouped, names, chapter=5))
        text = normalised(_plain(rows))
        anchor = _first_substantive(rows) or _first_chapter_anchor(paragraphs, 5)
        if not any(t in text for t in ("based on the findings", "finding", "objective")):
            issues.append(_issue(code="CH5-FINDINGS-TRACE", section="Chapter Five: Summary, Conclusions and Recommendations", title="Conclusions and recommendations are not clearly traceable to findings", assessment="The final chapter should not introduce broad recommendations without showing which findings support them.", action="Summarise findings by objective, draw conclusions from those findings and link each recommendation to a specific finding and responsible stakeholder.", anchor=anchor, category="conclusions_and_recommendations", degree=degree, severity="critical"))
        if degree in {"professional_doctorate", "phd"} and not any(t in text for t in ("original contribution", "contribution to knowledge", "contribution to practice", "theoretical contribution")):
            issues.append(_issue(code="CH5-CONTRIBUTION", section="Chapter Five: Summary, Conclusions and Recommendations", title="The final chapter does not state the study's contribution clearly", assessment="The contribution should identify what the study adds and show how the verified findings support that claim.", action="Add a contribution section explaining what is original or practically valuable, how the study established it and why it matters to knowledge, policy or practice.", anchor=anchor, category="critical_analysis", degree=degree, severity="critical"))
    return [x for x in issues if x]


def ucc_section_contract_issues(
    paragraphs: Sequence[Dict[str, Any]],
    *,
    academic_level: Any = "",
    depth: str = "standard",
    max_issues: Optional[int] = None,
    submission_scope: Any = "",
) -> List[Dict[str, Any]]:
    """Return UCC-format, degree-calibrated, evidence-anchored issues.

    This layer is intentionally deterministic and conservative. It does not
    replace the model review; it prevents relevant UCC thesis sections from
    being silently omitted after filtering and de-duplication.
    """
    if not enabled():
        return []
    current = _current_rows(paragraphs)
    if not current:
        return []
    degree = _degree_key(academic_level)
    grouped = _group_by_heading(current)
    issues: List[Optional[Dict[str, Any]]] = []

    section_ledger = build_section_coverage_ledger(
        current,
        academic_level=academic_level,
        depth=depth,
        submission_scope=submission_scope,
    )
    for entry in section_ledger.get("entries") or []:
        status = clean_text(entry.get("status"))
        if status == SECTION_STATUS_MISSING:
            issues.append(_missing_section_issue(
                current,
                int(entry.get("chapter_number") or 0),
                clean_text(entry.get("label")),
                clean_text(entry.get("category")),
                clean_text(entry.get("severity")),
                degree,
                aliases=entry.get("aliases") or [],
            ))
        elif status == SECTION_STATUS_INADEQUATE:
            issues.append(_inadequate_section_issue(current, entry, degree))

    chapters = set(section_ledger.get("target_chapters") or _chapter_scope(current))
    if 1 in chapters:
        issues.extend(_chapter_one_specific(current, grouped, degree))
    for chapter in sorted(chapters - {1}):
        issues.extend(_generic_chapter_specific(current, grouped, degree, chapter))


    out: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for item in issues:
        if not item:
            continue
        if item.get("severity") == "minor" and normalised(depth) == "light":
            continue
        key = str(item.get("finding_id"))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    severity_rank = {"critical": 0, "major": 1, "moderate": 2, "minor": 3}
    out.sort(key=lambda row: (severity_rank.get(str(row.get("severity") or "minor"), 9), normalised(row.get("section", "")), normalised(row.get("issue_title", ""))))
    if max_issues is None:
        max_issues = int(os.getenv("VPROF_UCC_SECTION_CONTRACT_MAX_ISSUES", "500"))
    return out[: max(0, int(max_issues))]


def section_contract_key(chapter_number: Any, label: Any) -> str:
    try:
        chapter = int(chapter_number or 0)
    except (TypeError, ValueError):
        chapter = 0
    return f"{chapter}::{normalised(clean_text(label))}"


def missing_section_labels_in_output(
    paragraphs: Sequence[Dict[str, Any]],
    issues: Sequence[Dict[str, Any]],
    *,
    academic_level: Any = "",
    depth: str = "standard",
    submission_scope: Any = "",
) -> Set[str]:
    """Return chapter-specific structural findings lost from public output.

    Keys include the chapter number because labels such as ``Introduction`` or
    ``Chapter Summary`` can be missing from more than one chapter. Earlier
    builds used the label alone, so one comment could incorrectly satisfy all
    chapters that shared the same section name.
    """
    ledger = build_section_coverage_ledger(
        paragraphs,
        academic_level=academic_level,
        depth=depth,
        submission_scope=submission_scope,
    )
    covered: Set[str] = set()
    for issue in issues:
        chapter = issue.get("chapter_number")
        for value in (
            issue.get("section_contract_label"),
            issue.get("missing_section_label"),
            issue.get("section"),
            issue.get("section_reference"),
            issue.get("reference_label"),
        ):
            if clean_text(value):
                covered.add(section_contract_key(chapter, value))
    needed: Set[str] = set()
    for entry in ledger.get("entries") or []:
        if entry.get("status") not in {SECTION_STATUS_MISSING, SECTION_STATUS_INADEQUATE}:
            continue
        chapter = entry.get("chapter_number")
        label = clean_text(entry.get("label"))
        matched = clean_text(entry.get("matched_heading"))
        aliases = [clean_text(value) for value in entry.get("aliases") or [] if clean_text(value)]
        keys = {section_contract_key(chapter, value) for value in [label, matched, *aliases] if clean_text(value)}
        if not keys.intersection(covered):
            needed.add(section_contract_key(chapter, label))
    return needed
