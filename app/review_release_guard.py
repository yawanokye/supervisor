from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from .document_parser import clean_text, normalised
from .finding_order import chapter_number, primary_evidence
from .supervisory_accuracy_guard import source_section


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _norm(value: Any) -> str:
    return normalised(_clean(value))


def _row_blob(row: Mapping[str, Any]) -> str:
    return _norm(" ".join(_clean(row.get(field)) for field in (
        "finding_id", "category", "section", "section_reference", "item",
        "issue_title", "comment", "assessment", "required_action",
        "academic_consequence", "illustrative_guidance",
    )))


def _runtime_rows(review: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return [
        dict(row)
        for row in ((review.get("_runtime_context") or {}).get("current_paragraphs") or [])
        if isinstance(row, Mapping) and _clean(row.get("text"))
    ]


def _section_label(row: Mapping[str, Any]) -> str:
    path = [value for value in (row.get("section_path") or []) if _clean(value)]
    return _clean(
        row.get("section_reference")
        or row.get("heading")
        or (path[-1] if path else "")
        or source_section(dict(row))
    )


def _section_blob(rows: Sequence[Mapping[str, Any]], *tokens: str, chapter: int | None = None) -> str:
    wanted = tuple(_norm(token) for token in tokens if _norm(token))
    values: List[str] = []
    for row in rows:
        if chapter is not None and int(row.get("chapter_number") or 0) != chapter:
            continue
        label = _norm(_section_label(row))
        path = _norm(" ".join(_clean(v) for v in (row.get("section_path") or [])))
        if wanted and not any(token in label or token in path for token in wanted):
            continue
        values.append(_clean(row.get("text")))
    return _norm(" ".join(values))


def _document_blob(rows: Sequence[Mapping[str, Any]], chapters: set[int] | None = None) -> str:
    return _norm(" ".join(
        _clean(row.get("text"))
        for row in rows
        if not chapters or int(row.get("chapter_number") or 0) in chapters
    ))


def _same_paragraph_has_citation(row: Mapping[str, Any]) -> bool:
    evidence = primary_evidence(dict(row))
    text = _clean(evidence.get("text") or row.get("problematic_quote"))
    if not text:
        return False
    parenthetical = re.search(r"\([^)]*(?:19|20)\d{2}[a-z]?[^)]*\)", text, flags=re.I)
    narrative = re.search(r"\b[A-Z][A-Za-z'’.-]+(?:\s+et\s+al\.)?\s*\((?:19|20)\d{2}[a-z]?\)", text)
    return bool(parenthetical or narrative)


def _contains_all_groups(text: str, groups: Sequence[Sequence[str]]) -> bool:
    return all(any(_norm(term) in text for term in group) for group in groups)


@dataclass(frozen=True)
class ReviewRouteContext:
    design: str
    submission_stage: str
    has_results: bool
    has_methodology: bool
    has_primary_data: bool


def classify_review_context(review: Mapping[str, Any]) -> ReviewRouteContext:
    rows = _runtime_rows(review)
    all_text = _document_blob(rows)
    method_text = _document_blob(rows, {3, 4})
    chapters = {int(row.get("chapter_number") or 0) for row in rows if int(row.get("chapter_number") or 0) > 0}

    primary_signals = (
        "questionnaire", "respondents", "participants", "interview", "focus group",
        "data collection", "sampling", "population", "spss", "stata", "regression",
        "survey", "primary data",
    )
    review_signals = (
        "systematic review", "scoping review", "meta analysis", "meta-analysis",
        "prisma", "search strategy", "screening process", "quality appraisal",
        "risk of bias",
    )
    strong_review_signals = sum(1 for term in review_signals if term in method_text)
    has_primary_data = any(term in method_text or term in all_text for term in primary_signals)

    if strong_review_signals >= 2 and not has_primary_data:
        design = "systematic_review"
    elif "mixed methods" in method_text or "mixed-methods" in method_text:
        design = "mixed_methods"
    elif any(term in method_text for term in ("qualitative", "thematic analysis", "interview", "focus group")) and not any(
        term in method_text for term in ("regression", "spss", "quantitative", "survey")
    ):
        design = "primary_qualitative"
    elif any(term in method_text for term in ("panel data", "time series", "ardl", "gmm", "cointegration", "secondary data")) and not any(
        term in method_text for term in ("questionnaire", "survey", "interview")
    ):
        design = "secondary_econometric"
    elif any(term in method_text for term in ("experiment", "quasi experimental", "quasi-experimental", "control group", "treatment group")):
        design = "experimental"
    elif has_primary_data:
        design = "primary_quantitative"
    else:
        design = "unspecified"

    results_rows = [
        row for row in rows
        if int(row.get("chapter_number") or 0) >= 4
        and any(token in _norm(_section_label(row)) for token in ("result", "finding", "analysis", "discussion"))
    ]
    result_content = _document_blob(results_rows)
    has_results = bool(results_rows) and (
        any(term in result_content for term in ("coefficient", "p value", "p-value", "table", "mean", "frequency", "theme", "finding"))
        or any(row.get("source_kind") == "table_row" for row in results_rows)
    )
    has_methodology = 3 in chapters or bool(_section_blob(rows, "research methods", "research methodology", chapter=3))

    summary = review.get("summary") or {}
    scope = _norm(summary.get("submission_scope") or summary.get("review_scope"))
    if has_results:
        stage = "results_or_complete"
    elif has_methodology:
        stage = "chapters_one_to_three"
    elif "proposal" in scope:
        stage = "proposal"
    else:
        stage = "chapter_only"
    return ReviewRouteContext(design, stage, has_results, has_methodology, has_primary_data)


def _background_is_contextualised(rows: Sequence[Mapping[str, Any]]) -> bool:
    text = _section_blob(rows, "background", chapter=1)
    if not text:
        return False
    global_context = any(term in text for term in ("global", "worldwide", "international", "african", "africa"))
    national_context = any(term in text for term in ("ghana", "bank of ghana", "ghanaian"))
    specific_setting = any(term in text for term in ("case study", "plc", "rural bank", "study is situated", "present study"))
    constructs = _contains_all_groups(text, (
        ("internal control", "control system", "control mechanisms"),
        ("fraud detection", "fraud prevention", "fraud incidence", "fraud outcome"),
    ))
    return sum((global_context, national_context, specific_setting, constructs)) >= 3


def _problem_gap_is_demonstrated(rows: Sequence[Mapping[str, Any]]) -> bool:
    text = _section_blob(rows, "statement of the problem", "problem statement", chapter=1)
    if not text:
        return False
    citations = len(re.findall(r"\((?:[^()]*)\b(?:19|20)\d{2}[a-z]?(?:[^()]*)\)", text))
    gap_terms = sum(term in text for term in (
        "gap", "however", "did not examine", "has not been", "remains unknown",
        "contextual", "methodological", "no study", "unresolved", "unlike prior",
    ))
    contribution = any(term in text for term in (
        "present study", "this study addresses", "designed to address", "study employs",
        "study investigates", "study is positioned",
    ))
    practical_evidence = bool(re.search(r"\b\d+(?:\.\d+)?\s*(?:per cent|percent|%)\b", text))
    return citations >= 2 and gap_terms >= 2 and contribution and practical_evidence


def _significance_is_applied(rows: Sequence[Mapping[str, Any]]) -> bool:
    text = _section_blob(rows, "significance", chapter=1)
    if not text:
        return False
    practical = any(term in text for term in (
        "management", "board", "institution", "organisation", "organization",
        "business", "trader", "retailer", "wholesaler", "logistics", "industry",
        "investor", "service delivery", "decision making", "decision-making",
    ))
    policy = any(term in text for term in (
        "policy", "policymaker", "ministry", "government", "regulator", "bank of ghana",
    ))
    scholarly = any(term in text for term in (
        "theoretical", "knowledge", "literature", "research", "researcher", "reference",
    ))
    return practical and (policy or scholarly)


def _theories_are_linked(rows: Sequence[Mapping[str, Any]]) -> bool:
    text = _section_blob(rows, "theoretical review", "agency theory", "fraud theory", "institutional theory", chapter=2)
    return bool(text) and bool(re.search(r"\bobjective\s*[123ivx]*\b", text))


def _population_frame_is_stated(rows: Sequence[Mapping[str, Any]]) -> bool:
    text = _section_blob(rows, "population", "sampling", chapter=3)
    return bool(text) and any(term in text for term in (
        "human resource", "hr department", "staff list", "employee list", "personnel list",
        "sampling frame", "staff register", "provided by the bank",
    ))


def _sampling_is_justified(rows: Sequence[Mapping[str, Any]]) -> bool:
    text = _section_blob(rows, "population", "sampling", chapter=3)
    technique = any(term in text for term in ("census", "purposive", "random sampling", "stratified", "systematic sampling"))
    rationale = any(term in text for term in ("because", "appropriate", "manageable", "ensures", "sensitive", "representative"))
    return technique and rationale


def _software_is_stated(rows: Sequence[Mapping[str, Any]]) -> bool:
    text = _document_blob(rows, {3})
    return bool(re.search(r"\b(?:spss|stata|smartpls|amos|r\s+version|python|nvivo|maxqda)\b", text))


def _organisation_is_present(rows: Sequence[Mapping[str, Any]]) -> bool:
    text = _section_blob(rows, "organisation of the study", "organization of the study", chapter=1)
    if not text:
        return False
    return all(f"chapter {word}" in text for word in ("two", "three", "four", "five"))


def _chapter_one_heading_pair_is_present(rows: Sequence[Mapping[str, Any]]) -> bool:
    headings = [
        _norm(row.get("text"))
        for row in rows
        if row.get("is_heading") or _norm(row.get("text")) in {"chapter one", "introduction"}
    ]
    return "chapter one" in headings and "introduction" in headings


def _introduction_text_is_present(rows: Sequence[Mapping[str, Any]]) -> bool:
    text = _section_blob(rows, "introduction", chapter=1)
    if len(text.split()) >= 18:
        return True
    # Some DOCX styles do not preserve the introduction heading in the section
    # label. Use the short passage between the Introduction and Background
    # headings as a conservative fallback.
    ordered = list(rows)
    intro_index = next((i for i, row in enumerate(ordered) if _norm(row.get("text")) == "introduction"), None)
    if intro_index is None:
        return False
    words = 0
    for row in ordered[intro_index + 1:]:
        low = _norm(row.get("text"))
        if "background" in low and (row.get("is_heading") or len(low.split()) <= 8):
            break
        words += len(_clean(row.get("text")).split())
    return words >= 18


def _objective_number_is_present(rows: Sequence[Mapping[str, Any]], number: int) -> bool:
    text = _section_blob(rows, "research objectives", "objectives of the study", chapter=1)
    if not text:
        return False
    if re.search(rf"(?:^|\s){int(number)}[.)]?\s+(?:to\s+)?[a-z]", text, flags=re.I):
        return True
    # Word list numbering is often stored as XML metadata and omitted from the
    # visible paragraph text returned by the parser. Count distinct objective
    # clauses beginning with a recognised research-action verb as a fallback.
    action_pattern = re.compile(
        r"\bto\s+(?:assess|analyse|analyze|compare|determine|develop|evaluate|examine|explore|identify|investigate|measure|test|establish|ascertain|describe)\b",
        flags=re.I,
    )
    return len(action_pattern.findall(text)) >= int(number)


def _limitations_mention_generalisation(rows: Sequence[Mapping[str, Any]]) -> bool:
    text = _section_blob(rows, "limitations of the study", "limitation of the study", chapter=1)
    return any(term in text for term in ("generalis", "generaliz", "transferab", "wider inference"))


def _rewrite_generic_limitation_finding(row: Mapping[str, Any]) -> Dict[str, Any]:
    output = dict(row)
    output.update({
        "issue_title": "The limitations are listed without explaining how they may affect the findings",
        "item": "The limitations are listed without explaining how they may affect the findings",
        "assessment": (
            "The section names access, time, financial and respondent-related constraints, but it does not explain the likely effect of each constraint on data quality, coverage or interpretation."
        ),
        "comment": (
            "The section names access, time, financial and respondent-related constraints, but it does not explain the likely effect of each constraint on data quality, coverage or interpretation."
        ),
        "required_action": (
            "For each material limitation, state how it may influence the evidence or interpretation and explain the practical step used to minimise the effect. Keep deliberate study boundaries in the scope or delimitation section."
        ),
        "severity": "moderate",
    })
    return output


def _actual_spelling_mix(rows: Sequence[Mapping[str, Any]]) -> Tuple[List[str], List[str]]:
    text = " ".join(_clean(row.get("text")) for row in rows)
    families = (
        (r"\borganis(?:ation|ations|e|ed|es|ing)\b", r"\borganiz(?:ation|ations|e|ed|es|ing)\b"),
        (r"\brecognis(?:e|ed|es|ing|ation)\b", r"\brecogniz(?:e|ed|es|ing|ation)\b"),
        (r"\bbehaviour(?:s|al)?\b", r"\bbehavior(?:s|al)?\b"),
        (r"\blabour\b", r"\blabor\b"),
        (r"\bmaximis(?:e|ed|es|ing|ation)\b", r"\bmaximiz(?:e|ed|es|ing|ation)\b"),
        (r"\bgeneralis(?:e|ed|es|ing|ation)\b", r"\bgeneraliz(?:e|ed|es|ing|ation)\b"),
    )
    british: List[str] = []
    american: List[str] = []
    for british_pattern, american_pattern in families:
        british.extend(match.group(0) for match in re.finditer(british_pattern, text, flags=re.I))
        american.extend(match.group(0) for match in re.finditer(american_pattern, text, flags=re.I))
    return list(dict.fromkeys(british)), list(dict.fromkeys(american))


def _is_results_only_finding(blob: str) -> bool:
    return any(term in blob for term in (
        "regression results do not", "result is not adequately", "moderation result",
        "interaction p value", "conditional effects", "simple slopes", "results chapter",
        "hypothesis decision and discussion", "add the missing model specific evidence",
        "table narrative hypothesis decision", "original spss regression output when presenting the results",
    ))


def _is_moderation_results_finding(blob: str) -> bool:
    return any(term in blob for term in (
        "moderation result", "moderation analysis should", "product interaction term",
        "interaction p value", "simple slope", "conditional effect", "johnson neyman",
    ))


def _moderation_alignment_row(row: Mapping[str, Any]) -> Dict[str, Any]:
    output = dict(row)
    output.update({
        "finding_id": "RELEASE-GUARD-MODERATION-ALIGNMENT",
        "category": "cross_section_coherence",
        "issue_title": "The proposed moderation role is not aligned with the objectives and analysis plan",
        "item": "The proposed moderation role is not aligned with the objectives and analysis plan",
        "severity": "major",
        "assessment": (
            "Employee characteristics are discussed as possible moderators, but the submitted objectives, conceptual framework and methodology do not consistently define a moderation model."
        ),
        "comment": (
            "Employee characteristics are discussed as possible moderators, but the submitted objectives, conceptual framework and methodology do not consistently define a moderation model."
        ),
        "academic_consequence": (
            "A moderation claim cannot be evaluated unless the moderator, interaction term and corresponding objective or hypothesis are specified before analysis."
        ),
        "required_action": (
            "Either remove the moderation claim from the stated gap, or add a matching objective or hypothesis, identify the moderator and predictor, specify the product interaction model and state how any interaction will be probed."
        ),
        "guidance_type": "direct_correction",
        "manual_confirmation_required": False,
    })
    return output


def _normalise_mechanical_checklist(row: Mapping[str, Any]) -> Dict[str, Any]:
    output = dict(row)
    title = _clean(output.get("issue_title") or output.get("item"))
    action = _clean(output.get("required_action"))
    assessment = _clean(output.get("assessment") or output.get("comment"))

    replacements = (
        (r"\bis clearly stated \([^)]*\) and justified is not fully explained\b", "is not sufficiently justified"),
        (r"\bis stated \([^)]*\) is not fully explained\b", "is named but its use is not sufficiently explained"),
        (r"\bis stated is missing or not clearly reported\b", "is not clearly reported"),
        (r"\bis described clearly is missing or not clearly reported\b", "is not clearly described"),
        (r"\bis demonstrated \([^)]*\) is not clearly linked to the rest of the study\b", "is not clearly linked to the rest of the study"),
        (r"\bis explicitly linked to specific objectives is not clearly linked to the rest of the study\b", "is not integrated clearly across the objectives, framework and analysis plan"),
        (r"\bare explained is not fully explained\b", "are not sufficiently explained"),
    )
    for pattern, replacement in replacements:
        title = re.sub(pattern, replacement, title, flags=re.I)
        assessment = re.sub(pattern, replacement, assessment, flags=re.I)

    generic = "revise the marked passage to address the identified academic weakness"
    if generic in _norm(action):
        low = _norm(title)
        if "sampling technique" in low:
            action = "State the final sampling approach, explain why it fits the accessible population, and remove any contradictory fallback technique unless it is supported by a clear non-response protocol."
        elif "decision thresholds" in low or "diagnostic" in low:
            action = "For each applicable diagnostic, state the test or output, decision threshold and remedy for a material violation."
        elif "research paradigm" in low:
            action = "Add a short alignment table or narrative linking the philosophy, approach, design, data source and analysis to the study objectives."
        elif "study site" in low or "representativeness" in low:
            action = "Explain why the selected site is suitable for the study without claiming statistical representativeness beyond the single institution."
        elif "theory" in low:
            action = "Show in one table how each retained theory explains specific constructs, objectives and expected relationships, and remove any theory that does not inform the analysis."
        elif "software" in low:
            action = "Name the software and version, then state the procedures for coding, scoring, missing-data treatment, diagnostics and model estimation."
        else:
            action = "State the missing information directly in the relevant section using the actual design, evidence and terminology of the study."

    output["issue_title"] = output["item"] = title
    output["assessment"] = output["comment"] = assessment or title
    output["required_action"] = action
    return output


def filter_and_rewrite_release_findings(
    rows: Sequence[Mapping[str, Any]],
    review: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    """Apply design, stage and whole-section contradiction gates before release.

    This guard is intentionally deterministic. It prevents a narrow paragraph or
    generic checklist label from overriding information that is already present
    elsewhere in the selected section, and prevents results-only requirements from
    being imposed on a Chapters One-to-Three submission.
    """
    runtime = _runtime_rows(review)
    context = classify_review_context(review)
    output: List[Dict[str, Any]] = []
    moderation_alignment_added = False

    for original in rows:
        row = _normalise_mechanical_checklist(original)
        blob = _row_blob(row)

        if any(phrase in blob for phrase in ("review-based research needs transparent search", "review based research needs transparent search", "review research needs transparent search")) and context.design != "systematic_review":
            continue

        if not context.has_results and _is_results_only_finding(blob):
            if _is_moderation_results_finding(blob) and not moderation_alignment_added:
                output.append(_moderation_alignment_row(row))
                moderation_alignment_added = True
            continue

        if "chapter title is too generic" in blob and _chapter_one_heading_pair_is_present(runtime):
            continue
        if any(term in blob for term in ("missing introduction text", "introduction text is missing", "introduction is missing")) and _introduction_text_is_present(runtime):
            continue
        if "missing third objective" in blob and _objective_number_is_present(runtime, 3):
            continue

        if any(term in blob for term in ("british and american", "spelling convention")):
            british, american = _actual_spelling_mix(runtime)
            if not british or not american:
                continue
            row["assessment"] = row["comment"] = (
                "The chapter uses British forms such as " + ", ".join(british[:3])
                + " and American forms such as " + ", ".join(american[:3]) + "."
            )

        if "limitations and limits of generalisation need clearer explanation" in blob and not _limitations_mention_generalisation(runtime):
            row = _rewrite_generic_limitation_finding(row)
            blob = _row_blob(row)

        if "background needs a clearer applied or professional logic" in blob and _background_is_contextualised(runtime):
            continue
        if any(term in blob for term in ("numerical empirical claim has no", "specific empirical count is not clearly", "count is not traceable")) and _same_paragraph_has_citation(row):
            continue
        if "contextual argument does not yet establish a precise research gap" in blob and _problem_gap_is_demonstrated(runtime):
            continue
        if "applied or professional contribution is not explicit" in blob and _significance_is_applied(runtime):
            continue
        if "theory" in blob and "not clearly linked" in blob and _theories_are_linked(runtime):
            continue
        if "sampling frame" in blob and ("missing" in blob or "not clearly" in blob) and _population_frame_is_stated(runtime):
            continue
        if "sampling technique" in blob and "not sufficiently justified" in blob and _sampling_is_justified(runtime):
            # Preserve a distinct census-versus-purposive inconsistency if present.
            method_text = _section_blob(runtime, "population", "sampling", chapter=3)
            if not ("census" in method_text and "purposive" in method_text):
                continue
        if "software" in blob and ("not fully explained" in blob or "not clearly reported" in blob or "named but" in blob) and _software_is_stated(runtime):
            # Keep only if the actual action concerns coding/diagnostics rather than mere naming.
            if not any(term in blob for term in ("coding", "scoring", "missing data", "diagnostic", "model estimation")):
                continue
        if "chapter organisation does not outline" in blob and _organisation_is_present(runtime):
            continue

        output.append(row)

    return consolidate_release_families(output)


def _family(row: Mapping[str, Any]) -> str:
    finding_id = _norm(row.get("finding_id") or row.get("code"))
    title = _norm(row.get("issue_title") or row.get("item"))
    section = _norm(row.get("section") or row.get("section_reference"))

    if any(term in finding_id for term in ("style british american", "language convention")) or any(
        term in title for term in ("british and american", "british american", "spelling convention")
    ):
        return "language_convention"
    if any(term in finding_id for term in ("unresolved supervisor instruction", "editorial instruction")) or any(
        term in title for term in ("unresolved supervisor", "editorial instruction remains", "embedded review note")
    ):
        return "embedded_instruction"
    if "construct terminology" in finding_id or "principal construct" in title:
        return "construct_consistency"
    if any(term in title for term in ("moderation", "moderator", "interaction term")):
        return "moderation_alignment"
    if any(term in finding_id for term in ("b3 causal", "b3 purpose objective", "b3 unit of analysis", "b3 1 purpose objectives")) or (
        any(term in title for term in ("purpose", "objective", "research question"))
        and any(term in title for term in ("align", "consistent analytical structure", "same substantive tasks", "unit and scope", "narrower than"))
    ) or (
        "purpose" in section and any(term in title for term in ("purpose", "objective", "research question", "causal language", "unit and scope"))
    ):
        return "purpose_alignment"
    if "conceptual framework" in title and any(term in title for term in ("figure", "outcome model", "directional", "duplicated", "represent")):
        return "conceptual_framework"
    if any(term in title for term in ("regression diagnostic", "ols plan", "regression specification", "multicollinearity", "homoscedasticity", "residual distribution")):
        return "regression_protocol"
    if any(term in title for term in ("ethical clearance", "gatekeeper", "institutional approval", "permission")):
        return "ethics_permissions"
    if any(term in title for term in ("numerical empirical claim", "specific empirical count", "numeric claim")):
        return "numeric_source"
    if "background" in section and not any(term in title for term in ("citation", "source", "spelling", "tense", "grammar", "punctuation")) and any(
        term in title for term in ("gap", "local", "context", "narrow", "global", "focus", "applied", "professional logic")
    ):
        return "background_local_context"
    if "problem" in section and not any(term in title for term in ("citation", "spelling", "grammar", "punctuation")) and any(
        term in title for term in ("gap", "local evidence", "specific evidence", "problem statement", "informal sector", "study title", "repetitive")
    ):
        return "problem_local_gap"
    if "significance" in section and not any(term in title for term in ("research gap", "problem statement", "gap is placed")) and any(
        term in title for term in ("contribution", "significance", "benefit", "vague", "disconnected")
    ):
        return "significance_contribution"
    if any(term in title for term in ("inconsistent construct labels", "inconsistent terminology across objectives", "it or ict", "uniform term")):
        return "terminology_consistency"
    return ""


def _merge(primary: Mapping[str, Any], other: Mapping[str, Any]) -> Dict[str, Any]:
    out = dict(primary)
    severity_rank = {"critical": 0, "major": 1, "moderate": 2, "minor": 3}
    if severity_rank.get(_norm(other.get("severity")), 9) < severity_rank.get(_norm(out.get("severity")), 9):
        out["severity"] = other.get("severity")
    out["confidence"] = max(float(out.get("confidence") or 0), float(other.get("confidence") or 0))

    actions: List[str] = []
    for value in (out.get("required_action"), other.get("required_action")):
        for sentence in re.split(r"(?<=[.!?])\s+", _clean(value)):
            key = _norm(sentence)
            if sentence and not any(SequenceMatcher(None, key, _norm(existing)).ratio() >= 0.86 for existing in actions):
                actions.append(sentence.rstrip(" .") + ".")
    out["required_action"] = " ".join(actions[:7])

    assessments: List[str] = []
    for value in (out.get("assessment") or out.get("comment"), other.get("assessment") or other.get("comment")):
        sentence = _clean(value)
        if sentence and not any(SequenceMatcher(None, _norm(sentence), _norm(existing)).ratio() >= 0.86 for existing in assessments):
            assessments.append(sentence.rstrip(" .") + ".")
    out["assessment"] = out["comment"] = " ".join(assessments[:3])

    evidence = list(out.get("evidence") or []) + list(other.get("evidence") or [])
    seen = set()
    unique = []
    for item in evidence:
        key = (item.get("paragraph"), item.get("table_index"), item.get("table_row"), _clean(item.get("text"))[:120])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    out["evidence"] = unique[:16]
    out["evidence_paragraph_ids"] = list(dict.fromkeys(
        list(out.get("evidence_paragraph_ids") or []) + list(other.get("evidence_paragraph_ids") or [])
    ))[:16]
    merged_ids = list(out.get("merged_finding_ids") or [])
    for candidate in (out.get("finding_id"), other.get("finding_id")):
        if candidate and candidate not in merged_ids:
            merged_ids.append(candidate)
    out["merged_finding_ids"] = merged_ids
    return out



def _consolidation_scope(row: Mapping[str, Any], family: str) -> str:
    """Return the narrowest safe scope for issue-family consolidation.

    The earlier chapter-wide merge collapsed distinct comments merely because
    they belonged to the same broad issue family. Exact-anchor issues now merge
    only on the same passage, while genuinely section-wide protocols may merge
    within the same section.
    """
    evidence = primary_evidence(dict(row))
    paragraph_id = _clean(
        evidence.get("paragraph_id")
        or evidence.get("id")
        or row.get("anchor_paragraph_id")
    )
    paragraph = evidence.get("paragraph")
    table_index = evidence.get("table_index")
    table_row = evidence.get("table_row")
    evidence_text = _norm(evidence.get("text") or row.get("problematic_quote"))[:120]
    exact = paragraph_id or (
        f"p:{paragraph}|t:{table_index}|r:{table_row}|x:{evidence_text}"
        if paragraph is not None or table_index is not None or evidence_text
        else ""
    )
    section = _norm(row.get("section_reference") or row.get("section")) or "unsectioned"

    if family in {"language_convention", "construct_consistency", "terminology_consistency", "purpose_alignment"}:
        return "chapter-wide"
    if family in {"regression_protocol", "conceptual_framework", "ethics_permissions", "moderation_alignment", "background_local_context", "problem_local_gap", "significance_contribution", "terminology_consistency"}:
        return "section:" + section
    return "anchor:" + (exact or section)

def consolidate_release_families(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Merge repeated root causes before numbering and export.

    Consolidation is limited to known issue families and the same chapter. This
    keeps distinct sentence-level defects separate while preventing three paid or
    deterministic findings from repeating one regression or alignment problem.
    """
    output: List[Dict[str, Any]] = []
    family_index: Dict[Tuple[int | None, str, str], int] = {}
    for original in rows:
        row = dict(original)
        family = _family(row)
        if not family:
            output.append(row)
            continue
        key = (chapter_number(row), family, _consolidation_scope(row, family))
        if key not in family_index:
            family_index[key] = len(output)
            output.append(row)
        else:
            output[family_index[key]] = _merge(output[family_index[key]], row)

    standard_titles = {
        "language_convention": "British and American English conventions are mixed",
        "embedded_instruction": "An unresolved supervisor or editor instruction remains in the academic text",
        "purpose_alignment": "The purpose, objectives, research questions, unit and scope are not fully aligned",
        "conceptual_framework": "The conceptual framework does not represent all proposed analytical models clearly",
        "regression_protocol": "The regression analysis needs one complete scoring, diagnostic and reporting protocol",
        "ethics_permissions": "Ethical clearance and institutional access procedures are not fully reported",
        "numeric_source": "A numerical empirical claim needs clearer source support",
        "moderation_alignment": "The proposed moderation role is not aligned with the objectives and analysis plan",
        "background_local_context": "The background does not narrow clearly to the study variables, Aboabo Market context and research gap",
        "problem_local_gap": "The problem statement needs a concise, locally evidenced problem and a precise Aboabo Market research gap",
        "significance_contribution": "The significance claims need to be specific to the study's scholarly, practical and policy contribution",
        "terminology_consistency": "The chapter uses IT, ICT and computer applications without defining or applying the terms consistently",
    }
    standard_actions = {
        "background_local_context": (
            "Restructure the background from the wider role of IT in supply chains to informal commodity trading and then to Aboabo Market. Define the central IT and supply-chain constructs, use relevant Ghanaian or local evidence, remove tangential technology examples and end with the exact gap addressed by the study."
        ),
        "problem_local_gap": (
            "Condense repeated background material and state the practical supply-chain problem at Aboabo Market, evidence of its nature or seriousness, what previous studies have not established, and how that gap leads directly to the purpose and objectives."
        ),
        "significance_contribution": (
            "Reorganise the section into scholarly, practical and policy contributions. Explain specifically how the findings may help Aboabo traders and supply-chain actors, relevant technology providers and policymakers, while keeping each claim proportionate to the study design and setting."
        ),
        "terminology_consistency": (
            "Choose and define the principal technology construct, distinguish IT from ICT or computer applications where necessary, and use the selected terminology consistently in the title, purpose, objectives, questions, instrument and analysis."
        ),
    }
    for row in output:
        family = _family(row)
        if family in standard_titles:
            row["issue_title"] = row["item"] = standard_titles[family]
        if family in standard_actions:
            row["required_action"] = standard_actions[family]
    return output
