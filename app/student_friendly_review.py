from __future__ import annotations

import os
import re
from typing import Any, Dict, Iterable, List, Sequence

from .document_parser import clean_text, normalised
from .reviewer_language import academic_level_label, professionalise_reviewer_language


def _env_enabled(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


_APP_LANGUAGE_REPLACEMENTS = (
    (r"\bthe uploaded documents\b", "the study materials"),
    (r"\bthe uploaded document\b", "the study"),
    (r"\bthe uploaded chapter\b", "the chapter"),
    (r"\bthe uploaded text\b", "the study"),
    (r"\bthe uploaded work\b", "the work"),
    (r"\buploaded documents\b", "study materials"),
    (r"\buploaded document\b", "study"),
    (r"\buploaded chapter\b", "chapter"),
    (r"\buploaded text\b", "study"),
    (r"\bthe submitted document\b", "the study"),
    (r"\bthe supplied document\b", "the study"),
    (r"\bthe supplied text\b", "the study"),
    (r"\bthe selected academic level\b", "the applicable academic level"),
    (r"\bthe selected level\b", "the applicable academic level"),
)

_GENERIC_SYSTEM_PHRASES = (
    r"\bthe automated review cannot confirm that\b",
    r"\bthe automated review cannot confirm\b",
    r"\bthe review cannot confirm that\b",
    r"\bthe review cannot confirm\b",
    r"\bthe document manifest does not confirm that\b",
)

_STOPWORDS = {
    "about", "above", "across", "after", "again", "against", "among", "and", "another",
    "because", "before", "being", "between", "chapter", "could", "data", "document", "during",
    "each", "evidence", "from", "have", "into", "level", "method", "methods", "more", "must",
    "only", "other", "result", "results", "review", "section", "should", "study", "their", "there",
    "these", "thesis", "this", "through", "using", "where", "which", "with", "work", "would",
}

_SECTION_PURPOSE = {
    "background to the study": "It should introduce the study context, explain the main constructs and lead logically to the research problem.",
    "statement of the problem": "It should show the practical or scholarly problem, provide evidence that the problem exists and identify what remains unresolved.",
    "purpose of the study": "It should state the overall aim of the study in one clear sentence and cover the main constructs, population and setting.",
    "research objectives": "They should break the purpose into measurable tasks that can each be answered by the methods and analysis.",
    "research questions": "They should correspond directly to the objectives and use the same constructs, population and scope.",
    "research hypotheses": "They should state the propositions tested by the inferential analysis and use the same constructs and direction as the objectives.",
    "significance of the study": "It should explain what the study may add to knowledge, practice and policy, rather than only listing beneficiaries.",
    "limitations of the study": "It should explain the main design, measurement, sampling or data constraints and how they limit interpretation of the findings.",
    "delimitations of the study": "It should state the population, setting, variables or themes, time period and boundaries deliberately covered by the study.",
    "definition of terms": "It should define the key concepts as they are used and measured in the study.",
    "organisation of the study": "It should give a brief and accurate account of what each chapter contains.",
    "organization of the study": "It should give a brief and accurate account of what each chapter contains.",
    "empirical review": "It should compare and synthesise relevant studies, identify agreements and differences, and show the evidence supporting the research gap.",
    "conceptual framework": "It should show the proposed relationships among the study constructs and explain why those relationships are expected.",
    "data processing and analysis": "It should state the analysis used for each objective or hypothesis and explain the assumptions, diagnostics and decision rules.",
    "diagnostic tests": "It should report the assumptions and model checks needed to judge whether the analysis is valid.",
    "sample size": "It should state the final sample, explain how it was determined and show that it is appropriate for the design and analysis.",
    "response rate": "It should show the number of instruments distributed, returned and retained for analysis, including the treatment of incomplete responses.",
    "sample characteristics": "It should describe the relevant characteristics of the respondents or units analysed so the reader can interpret the findings in context.",
    "discussion of findings": "It should explain what each finding means, compare it with theory and previous evidence, and acknowledge the limits of interpretation.",
}

_SECTION_PLACEMENT = {
    "background to the study": "Place it after the brief chapter introduction or overview.",
    "statement of the problem": "Place it after the background to the study.",
    "purpose of the study": "Place it after the statement of the problem.",
    "research objectives": "Place it immediately after the purpose of the study.",
    "research questions": "Place it after the research objectives.",
    "research hypotheses": "Place it after the research questions, or immediately after the objectives where the approved format does not use research questions for inferential objectives.",
    "significance of the study": "Place it after the research questions or hypotheses.",
    "delimitations of the study": "Place it after the significance of the study.",
    "limitations of the study": "Place it after the scope or delimitations section.",
    "definition of terms": "Place it near the end of Chapter One, before the organisation of the study.",
    "organisation of the study": "Place it at the end of Chapter One.",
    "sample size": "Place it in Chapter Three after the population and sampling discussion.",
    "response rate": "Place it near the beginning of Chapter Four before the substantive results.",
    "sample characteristics": "Place it near the beginning of Chapter Four before the analyses addressing the research questions or hypotheses.",
    "organization of the study": "Place it at the end of Chapter One.",
}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def remove_app_language(value: Any, academic_level: Any = None) -> str:
    """Turn app-facing review language into natural supervisor language."""
    text = professionalise_reviewer_language(_clean(value), academic_level)
    if not text:
        return ""
    for pattern, replacement in _APP_LANGUAGE_REPLACEMENTS:
        text = re.sub(pattern, replacement, text, flags=re.I)
    for pattern in _GENERIC_SYSTEM_PHRASES:
        text = re.sub(pattern, "the study does not clearly show that", text, flags=re.I)
    text = re.sub(
        r"\bThis creates a supervisory risk because the thesis may appear complete in form while a required academic element remains absent or unverified\.?",
        "This makes it difficult for the reader to judge whether the requirement has been met.",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"\bmake the location traceable by page and paragraph before resubmission\b",
        "state it clearly in the relevant section",
        text,
        flags=re.I,
    )
    text = re.sub(r"\bthe applicable academic level level\b", "the applicable academic level", text, flags=re.I)
    text = re.sub(r"\s{2,}", " ", text).strip(" ,;:")
    return text


def _all_evidence_text(issue: Dict[str, Any]) -> str:
    values: List[str] = [
        _clean(issue.get("problematic_quote")),
        _clean(issue.get("title_or_opening_focus")),
    ]
    for row in issue.get("evidence") or []:
        if isinstance(row, dict):
            values.append(_clean(row.get("text")))
            values.append(_clean(row.get("table_title")))
            values.extend(_clean(v) for v in row.get("section_path") or [])
    return " ".join(value for value in values if value)


def _technical_terms(text: str, limit: int = 5) -> List[str]:
    """Extract useful study terms without inventing content.

    Preference is given to repeated multi-word phrases and capitalised construct
    names. The function is intentionally conservative because an omitted example
    is better than an example from another study.
    """
    text = _clean(text)
    if not text:
        return []
    candidates: List[str] = []

    # Phrases commonly used in thesis titles and research purposes.
    title_like = re.sub(r"\s+", " ", text)
    for pattern in (
        r"(?:effect|influence|impact|relationship)\s+of\s+(.+?)\s+on\s+(.+?)(?:\s+among|\s+in\s+|\s*:|\.|$)",
        r"moderating\s+role\s+of\s+(.+?)(?:\s+among|\s+in\s+|\s*:|\.|$)",
        r"relationship\s+between\s+(.+?)\s+and\s+(.+?)(?:\s+among|\s+in\s+|\s*:|\.|$)",
    ):
        match = re.search(pattern, title_like, flags=re.I)
        if match:
            candidates.extend(_clean(group) for group in match.groups() if _clean(group))

    # Capitalised or repeated noun-like bigrams/trigrams.
    words = re.findall(r"[A-Za-z][A-Za-z'’-]{2,}", text)
    lowered = [word.lower() for word in words]
    counts: Dict[str, int] = {}
    for size in (3, 2):
        for idx in range(0, len(lowered) - size + 1):
            phrase_words = lowered[idx:idx + size]
            if any(word in _STOPWORDS for word in phrase_words):
                continue
            phrase = " ".join(phrase_words)
            counts[phrase] = counts.get(phrase, 0) + 1
    for phrase, count in sorted(counts.items(), key=lambda item: (-item[1], -len(item[0]))):
        if count < 2 and candidates:
            continue
        candidates.append(phrase)

    output: List[str] = []
    for candidate in candidates:
        candidate = re.sub(r"\b(?:ghana|ghanaian|chapter|college|university|students?|teachers?|study)\b", "", candidate, flags=re.I)
        candidate = re.sub(r"\s+", " ", candidate).strip(" ,;:-")
        if len(candidate.split()) < 1 or len(candidate) < 4:
            continue
        if normalised(candidate) in {normalised(value) for value in output}:
            continue
        if any(normalised(candidate) in normalised(value) or normalised(value) in normalised(candidate) for value in output):
            continue
        output.append(candidate)
        if len(output) >= limit:
            break
    return output


def _join_terms(terms: Sequence[str]) -> str:
    terms = [term for term in terms if _clean(term)]
    if not terms:
        return ""
    if len(terms) == 1:
        return terms[0]
    if len(terms) == 2:
        return f"{terms[0]} and {terms[1]}"
    return ", ".join(terms[:-1]) + f", and {terms[-1]}"


def _missing_label(issue: Dict[str, Any]) -> str:
    explicit = _clean(issue.get("missing_section_label"))
    if explicit:
        return explicit
    for field in ("issue_title", "item"):
        value = _clean(issue.get(field))
        match = re.match(r"Expected UCC thesis section is not evident:\s*(.+?)\s*$", value, flags=re.I)
        if match:
            return _clean(match.group(1))
        match = re.match(r"(.+?)\s+is missing from Chapter(?:\s+(?:One|Two|Three|Four|Five|\d+))?\s*$", value, flags=re.I)
        if match:
            return _clean(match.group(1))
    for field in ("assessment", "comment"):
        value = _clean(issue.get(field))
        match = re.search(r"The\s+(.+?)\s+section\s+is missing from Chapter", value, flags=re.I)
        if match:
            return _clean(match.group(1))
    return ""


def _chapter_label(issue: Dict[str, Any]) -> str:
    for value in (
        issue.get("chapter_number"),
        next((row.get("chapter_number") for row in issue.get("evidence") or [] if isinstance(row, dict) and row.get("chapter_number") is not None), None),
    ):
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        words = {1: "Chapter One", 2: "Chapter Two", 3: "Chapter Three", 4: "Chapter Four", 5: "Chapter Five"}
        return words.get(number, f"Chapter {number}")
    section = _clean(issue.get("section") or issue.get("section_reference"))
    match = re.search(r"chapter\s+(one|two|three|four|five|\d+)", section, flags=re.I)
    if match:
        token = match.group(1)
        return f"Chapter {token.title()}" if not token.isdigit() else f"Chapter {token}"
    return "the chapter"


def _normalise_label(label: str) -> str:
    low = normalised(label)
    aliases = {
        "definition of key concepts": "definition of terms",
        "definition of concepts": "definition of terms",
        "operational definition of terms": "definition of terms",
        "delimitation of the study": "delimitations of the study",
        "scope / delimitation of the study": "delimitations of the study",
        "scope of the study": "delimitations of the study",
        "organization of the study": "organisation of the study",
    }
    return aliases.get(low, low)


def _missing_section_example(label: str, issue: Dict[str, Any]) -> str:
    key = _normalise_label(label)
    evidence_text = _all_evidence_text(issue)
    supplied_terms = issue.get("study_terms") or []
    terms = [str(value) for value in supplied_terms if _clean(value)] or _technical_terms(evidence_text, limit=4)
    joined = _join_terms(terms[:4])
    if key == "definition of terms":
        if joined:
            return f"define {joined} in the same way they are operationalised in the instrument and analysis"
        return "define the main constructs, abbreviations and study-specific terms in the same way they are used in the instrument and analysis"
    if key == "limitations of the study":
        return "explain how the design, sampling coverage, self-reported measures, data availability or study period limit the interpretation and generalisation of the findings, where applicable"
    if key == "delimitations of the study":
        return "state the population, study setting, variables or themes, time period and aspects deliberately excluded from the work"
    if key == "purpose of the study":
        if joined:
            return f"state in one sentence that the study examines {joined}, followed by the confirmed population and setting"
        return "state the overall aim in one clear sentence using the same constructs, population and setting as the title and objectives"
    if key == "research hypotheses":
        if joined:
            return f"formulate testable null hypotheses for the inferential relationships involving {joined}, using the same population and direction as the objectives"
        return "formulate one testable null hypothesis for each inferential objective, or explain why the approved format uses research questions only"
    if key == "research questions":
        return "write one clear question for each objective and retain the same construct names, population and setting"
    if key == "sample size":
        return "state the target and achieved sample, the method or power basis used to determine it, and whether the final sample was adequate for the planned analysis"
    if key == "response rate":
        return "report the number of questionnaires distributed, returned, excluded and retained for analysis, then calculate the response rate from those figures"
    if key == "sample characteristics":
        return "summarise the characteristics relevant to the study, such as institution, programme, sex, age or experience, and ensure the totals reconcile with the analytical sample"
    if key == "research objectives":
        return "use measurable verbs and ensure that each objective can be answered by a clearly stated data source and analysis"
    if key == "significance of the study":
        if joined:
            return f"explain how findings on {joined} may add to knowledge, improve practice and inform policy in the study setting"
        return "separate the study's expected contribution to knowledge, practice and policy"
    if key == "statement of the problem":
        return "present verified evidence of the problem in the study setting, identify what previous studies have not resolved and show how the study addresses that gap"
    if key == "background to the study":
        return "move from the broad context to the specific study setting, introduce the main constructs and end with the gap that leads to the problem statement"
    if key in {"organisation of the study", "organization of the study"}:
        return "state briefly and accurately what each chapter covers"
    return "add the section with content that is directly linked to the purpose, objectives, methods and evidence of the study"


def _missing_section_rewrite(issue: Dict[str, Any], academic_level: Any = None) -> Dict[str, Any]:
    output = dict(issue)
    label = _missing_label(output)
    if not label:
        return output
    chapter = _chapter_label(output)
    key = _normalise_label(label)
    display_label = "Definition of Terms" if key == "definition of terms" else label
    purpose = _SECTION_PURPOSE.get(key, "It is needed to complete the academic structure and make the study easier to follow.")
    placement = _SECTION_PLACEMENT.get(key, f"Add it under a clear {display_label} heading in the appropriate part of {chapter}.")
    output["issue_title"] = f"{display_label} is missing from {chapter}"
    output["item"] = output["issue_title"]
    output["assessment"] = f"{display_label} is missing from {chapter}. This section is required under UCC thesis guidelines. {purpose}"
    output["comment"] = output["assessment"]
    output["academic_consequence"] = "Without this section, the reader cannot fully assess the structure, boundaries or interpretation of the study."
    output["required_action"] = f"Add a clearly labelled {display_label} section. {placement}"
    example = _missing_section_example(display_label, output)
    if example:
        example = example[0].upper() + example[1:]
        if example[-1] not in ".!?":
            example += "."
    output["illustrative_guidance"] = example
    output["missing_section_label"] = display_label
    return output


def _specific_level_expectation(issue: Dict[str, Any], academic_level: Any) -> str:
    """Return a natural quality expectation without repeating the degree label.

    The academic benchmark is applied by the review prompts and report. Native
    comments should normally explain the concrete defect rather than repeat
    "At PhD level" or "At MPhil level" after every finding.
    """
    section_text = normalised(" ".join(_clean(issue.get(field)) for field in (
        "section", "issue_title", "item", "assessment", "comment"
    )))
    category = normalised(_clean(issue.get("category")))
    if any(term in section_text for term in ("significance", "contribution", "implication")):
        return "The claimed contribution must be explicit and proportionate to the evidence and design."
    if any(term in section_text for term in ("discussion", "interpretation")):
        return "The discussion should explain the result, integrate relevant theory and evidence, and respect the limits of the design."
    if any(term in section_text for term in ("statistic", "result", "regression", "anova", "sem", "moderation", "mediation", "table", "coefficient")) or category in {"statistical accuracy", "analysis appropriateness", "results and interpretation"}:
        return "Each conclusion must agree with the relevant table, estimate, uncertainty measure, diagnostic evidence and decision rule."
    if any(term in section_text for term in ("method", "design", "sampling", "instrument", "validity", "reliability", "ethic")) or category == "methodological rigour":
        return "The method should be justified and documented well enough for another researcher to understand and reproduce the procedure."
    if any(term in section_text for term in ("literature", "empirical review", "theory", "conceptual", "gap")) or category in {"theoretical grounding", "critical analysis"}:
        return "The literature should be used at the depth required by the chapter and should support the study's argument, gap and framework."
    if any(term in section_text for term in ("objective", "question", "hypoth", "purpose", "problem")):
        return "The problem, purpose, objectives, questions and hypotheses should form one coherent research logic."
    if any(term in section_text for term in ("grammar", "language", "spelling", "punctuation", "citation", "reference")):
        return "The presentation should be accurate and consistent so that language does not obscure the academic argument."
    return "The point should be stated precisely and supported sufficiently for the reader to follow the study's reasoning."


def _remove_generic_level_boilerplate(text: str) -> str:
    patterns = (
        r"At MPhil level, the correction should demonstrate clear scholarly judgement, methodological or analytical defensibility, and traceable support from the study evidence\.?",
        r"At MPhil level, the section should show independent research judgement, conceptual clarity, methodological defensibility and traceable scholarly contribution\.?",
        r"At PhD level, this weakness matters because the thesis must support an original and defensible contribution to knowledge\.?",
        r"At PhD level, the section should support an original and defensible contribution to knowledge, with rigorous theoretical, empirical or methodological positioning\.?",
        r"At Professional Doctorate level, the section should connect rigorous doctoral scholarship to a defensible contribution to practice, policy or professional knowledge\.?",
    )
    for pattern in patterns:
        text = re.sub(pattern, "", text, flags=re.I)
    text = re.sub(
        r"(?:^|(?<=[.!?])\s+)At\s+(?:PhD|MPhil|Professional Doctorate|professional doctorate|Master(?:'s|s)|non-research Master(?:'s|s)|Bachelor(?:'s|s))\s+level,\s*[^.!?]+[.!?]",
        " ", text, flags=re.I,
    )
    text = re.sub(r"\b(?:at|for) (?:PhD|MPhil|Professional Doctorate|professional doctorate|Master(?:'s|s)|non-research Master(?:'s|s)|Bachelor(?:'s|s)) level\b", "", text, flags=re.I)
    text = re.sub(r"\bshould be traceable to\b", "should be clearly linked to", text, flags=re.I)
    text = re.sub(r"\bclear and traceable research logic\b", "clear and coherent research logic", text, flags=re.I)
    text = re.sub(r"\bmethodological traceability\b", "method clarity and reproducibility", text, flags=re.I)
    text = re.sub(r"\btraceability of (?:the )?methods?\b", "clarity and reproducibility of the methods", text, flags=re.I)
    text = re.sub(r"\btraceability\b", "clear connection", text, flags=re.I)
    text = re.sub(r"\btraceable\b", "clearly supported", text, flags=re.I)
    return re.sub(r"\s{2,}", " ", text).strip(" ,;:")


def _example_relevant(example: str, issue: Dict[str, Any]) -> bool:
    example = _clean(example)
    if not example:
        return False
    context = " ".join(
        _clean(issue.get(field))
        for field in ("section", "section_reference", "issue_title", "item", "assessment", "comment", "required_action", "problematic_quote")
    ) + " " + _all_evidence_text(issue)
    context_norm = normalised(context)
    example_norm = normalised(example)

    # Block recurring stale examples and any domain-specific phrase that is not
    # present in the current evidence or finding context.
    high_risk_phrases = (
        "assinman rural bank", "rural banking sector", "fraud incidence", "fraud triangle",
        "pressure opportunity and rationalisation", "segregation of duties", "access controls",
        "internal controls within the bank", "commercial banks in ghana",
    )
    for phrase in high_risk_phrases:
        if phrase in example_norm and phrase not in context_norm:
            return False

    # Examples about citations are only relevant to citation findings.
    if any(term in example_norm for term in ("citation cluster", "reference list entry", "parenthetical citation")):
        issue_focus = normalised(" ".join(_clean(issue.get(field)) for field in ("category", "issue_title", "item", "required_action")))
        if not any(term in issue_focus for term in ("citation", "reference", "source attribution")):
            return False

    example_tokens = {
        token for token in re.findall(r"[a-z][a-z0-9'-]{3,}", example_norm)
        if token not in _STOPWORDS
    }
    context_tokens = {
        token for token in re.findall(r"[a-z][a-z0-9'-]{3,}", context_norm)
        if token not in _STOPWORDS
    }
    if not example_tokens:
        return False
    overlap = example_tokens & context_tokens
    generic_allowed = any(term in example_norm for term in (
        "one objective", "one research question", "theoretical practical and policy",
        "estimate standard error", "design sampling", "same construct names",
    ))
    return bool(overlap) or generic_allowed


def _generated_example(issue: Dict[str, Any]) -> str:
    text = normalised(" ".join(_clean(issue.get(field)) for field in (
        "category", "section", "issue_title", "item", "assessment", "comment", "required_action"
    )))
    terms = _technical_terms(_all_evidence_text(issue) + " " + _clean(issue.get("problematic_quote")), limit=4)
    joined = _join_terms(terms[:4])
    quote = _clean(issue.get("problematic_quote"))

    if any(term in text for term in ("definition of terms", "definition of key concepts", "operational definition")):
        return f"define {joined} exactly as they are measured or analysed in the study" if joined else "define the main constructs exactly as they are measured or analysed in the study"
    if any(term in text for term in ("outer loading", "factor loading", "composite reliability", "cronbach", "rho a", "average variance extracted", "ave", "htmt", "fornell", "measurement model", "construct reliability", "construct validity")):
        return "report the relevant loading, reliability or validity statistic, state the decision threshold used, and explain whether the construct meets that criterion using values from the same measurement-model output"
    if any(term in text for term in ("result", "statistic", "regression", "anova", "sem", "moderation", "mediation", "coefficient", "p value", "r squared")):
        if "interpret" in text or "explain the coefficient" in text:
            return "state the direction and size of the coefficient, report its uncertainty and significance from the same model output, and explain what the result means for the relevant objective"
        return "report the estimate, standard error, test statistic, degrees of freedom where applicable, p-value, confidence interval and relevant model diagnostic from the same analysis output"
    if any(term in text for term in ("objective", "research question", "hypoth", "purpose", "alignment")):
        if quote:
            return f"revise the wording beginning “{quote[:120]}” and use the same constructs in the matching objective, question or hypothesis, analysis and reported result"
        if joined:
            return f"use the same main construct names across the purpose, objectives, questions, hypotheses, methods and results, including {joined}"
        return "map each objective to one question or hypothesis, the data required, the analysis used and the result reported"
    if any(term in text for term in ("problem statement", "research gap", "local evidence")):
        return "state the documented problem in the study setting, cite verified evidence of its scale, identify what remains unknown and show how the study addresses that gap"
    if any(term in text for term in ("significance", "contribution", "implication")):
        supplied = [str(value) for value in (issue.get("study_terms") or []) if _clean(value)]
        if supplied:
            return f"explain separately how findings on {_join_terms(supplied[:4])} may add to knowledge, improve practice and inform policy"
        if quote:
            return f"after the paragraph beginning “{quote[:100]}”, add separate statements of the theoretical, empirical, practical and policy contribution supported by the study"
        return "separate the theoretical, empirical, practical and policy contribution supported by the study"
    if any(term in text for term in ("discussion", "interpretation")):
        return f"explain what the finding about {joined} means, compare it with the relevant theory and prior evidence, and state the limit of the conclusion" if joined else "explain what the finding means, compare it with theory and prior evidence, and state the limit of the conclusion"
    if any(term in text for term in ("citation", "reference", "source attribution")):
        return "place the citation correctly, remove any duplicate citation and ensure that one complete reference-list entry matches it"
    if any(term in text for term in ("grammar", "language", "spelling", "british", "american english", "punctuation", "academic writing")):
        return f"rewrite the sentence beginning “{quote[:120]}” in clear formal British English while preserving its meaning" if quote else "apply formal British English consistently and correct grammar, punctuation and sentence structure throughout the affected passage"
    if quote:
        return f"rewrite the sentence beginning “{quote[:120]}” so that the point is precise, supported and consistent with the study's terminology"
    return ""


def make_issue_student_friendly(issue: Dict[str, Any], academic_level: Any = None) -> Dict[str, Any]:
    """Polish an issue for clear student-facing supervision.

    The function preserves the academic finding but removes app language,
    replaces repetitive level boilerplate with an issue-specific expectation,
    and keeps only examples that fit the current study.
    """
    output = dict(issue)
    # The final human-supervisor editor has already resolved structure, wording
    # and examples. Do not rebuild those fields during the final sanitation
    # pass, because that can reintroduce generic examples or mechanical text.
    if _missing_label(output) and not output.get("human_edited"):
        output = _missing_section_rewrite(output, academic_level)

    fields = (
        "section", "section_reference", "reference_label", "issue_title", "item",
        "assessment", "comment", "academic_consequence", "required_action", "illustrative_guidance",
    )
    for field in fields:
        output[field] = remove_app_language(output.get(field, ""), academic_level)

    if not _env_enabled("VPROF_STUDENT_FRIENDLY_COMMENTS", True):
        return output

    for field in ("assessment", "comment", "academic_consequence"):
        output[field] = _remove_generic_level_boilerplate(output.get(field, ""))

    # The degree standard is applied silently. Add a quality expectation only
    # when explicitly requested and only where the existing assessment is too
    # short to explain why the issue matters.
    if _env_enabled("VPROF_ADD_QUALITY_EXPECTATION_TO_COMMENTS", False):
        expectation = _specific_level_expectation(output, academic_level)
        assessment_field = "comment" if _clean(output.get("comment")) else "assessment"
        current = _clean(output.get(assessment_field))
        if expectation and len(current.split()) < 24:
            output[assessment_field] = (current.rstrip(" .") + ". " + expectation).strip() if current else expectation

    example = _clean(output.get("illustrative_guidance"))
    if not output.get("human_edited") and not _example_relevant(example, output):
        example = _generated_example(output) if _env_enabled("VPROF_CONTEXT_SPECIFIC_EXAMPLES", True) else ""
    output["illustrative_guidance"] = remove_app_language(example, academic_level)

    # Prefer direct sentences over checklist wording.
    title = _clean(output.get("issue_title") or output.get("item"))
    title = re.sub(r"^Required thesis element is not evident:\s*", "", title, flags=re.I)
    title = re.sub(r"^Required thesis element is only partly demonstrated:\s*", "", title, flags=re.I)
    title = re.sub(r"^Required thesis element needs explicit traceability:\s*", "", title, flags=re.I)
    if title and not re.search(r"\b(?:missing|unclear|incomplete|inconsistent|not fully|needs|does not|is not|lacks|weak)\b", title, flags=re.I):
        original = _clean(output.get("issue_title") or output.get("item"))
        if "only partly demonstrated" in original.lower():
            title = f"{title} is not fully explained"
        elif "needs explicit traceability" in original.lower():
            title = f"{title} is not clearly linked to the rest of the study"
        elif "not evident" in original.lower():
            title = f"{title} is not clearly reported"
    output["issue_title"] = title or _clean(output.get("issue_title"))
    output["item"] = output["issue_title"] or _clean(output.get("item"))

    return output


def make_finding_student_friendly(row: Dict[str, Any], academic_level: Any = None) -> Dict[str, Any]:
    """Apply the same language rules to exporter-ready finding rows."""
    adapted = {
        **row,
        "issue_title": row.get("item") or row.get("issue_title"),
        "assessment": row.get("comment") or row.get("assessment"),
    }
    adapted = make_issue_student_friendly(adapted, academic_level)
    output = dict(row)
    output["item"] = adapted.get("issue_title") or adapted.get("item") or output.get("item")
    output["comment"] = adapted.get("assessment") or adapted.get("comment") or output.get("comment")
    output["academic_consequence"] = adapted.get("academic_consequence") or output.get("academic_consequence")
    output["required_action"] = adapted.get("required_action") or output.get("required_action")
    output["illustrative_guidance"] = adapted.get("illustrative_guidance") or ""
    output["section"] = adapted.get("section") or output.get("section")
    output["section_reference"] = adapted.get("section_reference") or output.get("section_reference")
    output["reference_label"] = adapted.get("reference_label") or output.get("reference_label")
    return output
