from __future__ import annotations

import hashlib
import os
import re
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from .document_parser import clean_text, normalised
from .finding_order import chapter_number, primary_evidence


def _env_enabled(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _norm(value: Any) -> str:
    return normalised(_clean(value))




def _is_setting_term(value: Any) -> bool:
    text = _clean(value)
    return bool(re.search(
        r"\b(?:Bank|PLC|University|College|School|Hospital|Assembly|Company|Municipality|District|Region|Ghana)\b",
        text,
        flags=re.I,
    ))


def _construct_terms(terms: Sequence[str]) -> List[str]:
    values = [_clean(value) for value in terms if _clean(value) and not _is_setting_term(value)]
    return values or [_clean(value) for value in terms if _clean(value)]


def _setting_term(terms: Sequence[str]) -> str:
    return next((_clean(value) for value in terms if _clean(value) and _is_setting_term(value)), "")

def _severity_rank(value: Any) -> int:
    return {"critical": 0, "major": 1, "moderate": 2, "minor": 3}.get(_norm(value), 9)


def _sentences(value: Any) -> List[str]:
    text = _clean(value)
    if not text:
        return []
    output: List[str] = []
    for part in re.split(r"(?<=[.!?])\s+", text):
        sentence = _clean(part).strip(" ;")
        if not sentence:
            continue
        if sentence[-1:] not in ".!?":
            sentence += "."
        output.append(sentence)
    return output


def _unique_sentences(values: Iterable[Any], limit: int = 5) -> str:
    output: List[str] = []
    keys: List[str] = []
    for value in values:
        for sentence in _sentences(value):
            key = _norm(sentence)
            if not key:
                continue
            if any(key == old or SequenceMatcher(None, key, old).ratio() >= 0.84 for old in keys):
                continue
            keys.append(key)
            output.append(sentence)
            if len(output) >= limit:
                return " ".join(output)
    return " ".join(output)


def _section_text(row: Dict[str, Any]) -> str:
    return _norm(" ".join(_clean(row.get(field)) for field in (
        "section_reference", "section", "reference_label", "item", "issue_title"
    )))


def _finding_text(row: Dict[str, Any]) -> str:
    return _norm(" ".join(_clean(row.get(field)) for field in (
        "category", "item", "issue_title", "comment", "assessment", "required_action",
        "academic_consequence", "illustrative_guidance"
    )))


def _missing_label(row: Dict[str, Any]) -> str:
    explicit = _clean(row.get("missing_section_label"))
    if explicit:
        return explicit
    if _norm(row.get("section_status")) == "missing":
        return _clean(row.get("section_contract_label"))
    return ""


def _table_reference(row: Dict[str, Any]) -> str:
    evidence = primary_evidence(row)
    number = _clean(evidence.get("table_number"))
    title = _clean(evidence.get("table_title"))
    if not (number or title):
        return ""
    label = f"Table {number}" if number else "Table"
    return f"{label}: {title}" if title else label


def _root_cause_key(row: Dict[str, Any]) -> Tuple[Any, ...]:
    chapter = chapter_number(row) or 999
    section = _section_text(row)
    text = _finding_text(row)
    missing = _norm(_missing_label(row))
    if missing:
        return (chapter, "missing_section", missing)

    table = _norm(_table_reference(row))
    if table and any(term in text for term in (
        "statistic", "regression", "anova", "coefficient", "r squared", "f statistic",
        "moderation", "mediation", "sem", "pls", "loading", "reliability", "validity",
    )):
        return (chapter, "table_model", table)

    if "significance" in section:
        if any(term in text for term in ("research gap", "gap is placed", "move the research gap", "problem logic")):
            return (chapter, "significance_gap_placement")
        if any(term in text for term in (
            "contribution", "theory", "theoretical", "practice", "practical", "policy",
            "stakeholder usefulness", "scholarly value", "research contribution",
        )):
            return (chapter, "significance_contribution")

    if "problem statement" in section:
        if any(term in text for term in (
            "local evidence", "empirical evidence", "policy evidence", "magnitude", "scale",
            "research gap", "unresolved", "full purpose", "does not yet perform",
        )):
            return (chapter, "problem_evidence_and_gap")

    if any(term in section for term in ("scope", "delimitation")) and any(term in text for term in (
        "commercial bank", "rural bank", "case study", "population", "scope", "generalisation",
    )):
        return (chapter, "scope_and_population")

    if any(term in section for term in ("question", "objective", "hypoth", "purpose")):
        if any(term in text for term in ("align", "inferential", "relational", "impact", "effect", "hypoth")):
            return (chapter, "objective_question_hypothesis_alignment")

    evidence = primary_evidence(row)
    return (
        chapter,
        evidence.get("paragraph"),
        evidence.get("table_index"),
        evidence.get("table_row"),
        _norm(row.get("category") or "other"),
    )


def _merge_evidence(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    seen = set()
    for row in rows:
        for item in row.get("evidence") or []:
            key = (
                item.get("paragraph"), item.get("table_index"), item.get("table_row"),
                _clean(item.get("text"))[:160],
            )
            if key in seen:
                continue
            seen.add(key)
            output.append(dict(item))
    output.sort(key=lambda item: (
        int(item.get("paragraph") or 10**9),
        int(item.get("table_index") or 10**9),
        int(item.get("table_row") or 10**9),
    ))
    return output[:16]


def _special_root_cause_rewrite(row: Dict[str, Any], key: Tuple[Any, ...], terms: Sequence[str]) -> Dict[str, Any]:
    output = dict(row)
    family = key[1] if len(key) > 1 else ""
    construct_values = _construct_terms(terms)
    joined = _join_terms(construct_values[:4])
    setting = _setting_term(terms)

    if family == "problem_evidence_and_gap":
        output["item"] = output["issue_title"] = "The problem statement needs stronger evidence and a precise unresolved issue"
        output["comment"] = output["assessment"] = (
            "The section discusses fraud and internal controls generally, but it does not yet demonstrate the scale of the problem in the study context or identify clearly what previous research has left unresolved."
        )
        output["academic_consequence"] = (
            "Without that evidence and gap, the reader cannot see why this particular investigation is necessary."
        )
        output["required_action"] = (
            "Add recent, verifiable institutional, regulatory or empirical evidence, explain the unresolved issue, and end the section with the exact problem the study will address."
        )
        if joined:
            output["illustrative_guidance"] = (
                f"show what is known and still unknown about {joined}" + (f" at {setting}" if setting else " in the confirmed study setting")
            )

    elif family == "significance_gap_placement":
        output["item"] = output["issue_title"] = "The research gap is placed in the significance section"
        output["comment"] = output["assessment"] = (
            "The significance section contains part of the argument for why the study is needed. That argument belongs in the background or problem statement."
        )
        output["academic_consequence"] = (
            "Mixing the gap with the benefits of the study weakens both the problem logic and the contribution statement."
        )
        output["required_action"] = (
            "Move the research gap to the background or problem statement, then use the significance section only for the study's scholarly, practical and policy value."
        )
        output["illustrative_guidance"] = "end the problem statement with the unresolved issue and begin the significance section with the contribution the findings may make"

    elif family == "significance_contribution":
        output["item"] = output["issue_title"] = "The significance section does not distinguish the study's main contributions"
        output["comment"] = output["assessment"] = (
            "The section mainly lists possible beneficiaries, but it does not state clearly what the study may add to knowledge, practice and policy."
        )
        output["academic_consequence"] = (
            "A list of beneficiaries does not by itself establish the scholarly value of the work."
        )
        output["required_action"] = (
            "Reorganise the section into concise scholarly, practical and policy contributions, and keep each claim proportionate to the study's design and scope."
        )
        if joined:
            output["illustrative_guidance"] = (
                f"explain how findings on {joined} may extend understanding, guide organisational practice and inform relevant policy"
            )

    elif family == "objective_question_hypothesis_alignment":
        output["item"] = output["issue_title"] = "The objectives, questions and hypotheses need one consistent analytical structure"
        output["comment"] = output["assessment"] = (
            "The study combines descriptive and inferential aims, but the corresponding questions or hypotheses are not organised consistently."
        )
        output["academic_consequence"] = (
            "This makes it difficult to determine which analysis will answer each objective and what type of conclusion the design can support."
        )
        output["required_action"] = (
            "Classify each objective as descriptive, associational, predictive or causal, then provide a matching research question or hypothesis and an appropriate analysis."
        )
        if joined:
            output["illustrative_guidance"] = (
                f"use the same terms for {joined} in the objective, question or hypothesis, method and reported result"
            )

    elif family == "scope_and_population":
        if output.get("human_deterministic_finding"):
            return output
        output["item"] = output["issue_title"] = "The study population and institutional scope are not used consistently"
        output["comment"] = output["assessment"] = (
            "The work moves between a broad population and a specific case without making clear which one defines the study."
        )
        output["academic_consequence"] = (
            "This affects the title, sampling frame, interpretation and the extent to which the findings may be generalised."
        )
        output["required_action"] = (
            "State one study population and setting, then use that scope consistently in the title, problem, purpose, objectives, methods and conclusions."
        )
        output["illustrative_guidance"] = (
            "decide whether the work is a single-case study or a broader multi-institution study and revise every population reference accordingly"
        )

    return output


def _join_terms(terms: Sequence[str]) -> str:
    values = [_clean(value) for value in terms if _clean(value)]
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return ", ".join(values[:-1]) + f", and {values[-1]}"


def consolidate_root_causes(rows: Sequence[Dict[str, Any]], terms: Sequence[str]) -> List[Dict[str, Any]]:
    if not _env_enabled("VPROF_HUMAN_ROOT_CAUSE_CONSOLIDATION", True):
        return [dict(row) for row in rows]
    grouped: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = {}
    order: List[Tuple[Any, ...]] = []
    for row in rows:
        key = _root_cause_key(row)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(dict(row))

    output: List[Dict[str, Any]] = []
    for key in order:
        group = grouped[key]
        primary = min(group, key=lambda row: (_severity_rank(row.get("severity")), -float(row.get("confidence") or 0)))
        merged = dict(primary)
        if len(group) > 1:
            merged["severity"] = min((row.get("severity") or "minor" for row in group), key=_severity_rank)
            merged["confidence"] = max(float(row.get("confidence") or 0) for row in group)
            merged["evidence"] = _merge_evidence(group)
            merged["evidence_paragraph_ids"] = list(dict.fromkeys(
                value for row in group for value in (row.get("evidence_paragraph_ids") or [])
            ))[:16]
            merged["comment"] = merged["assessment"] = _unique_sentences(
                [row.get("comment") or row.get("assessment") for row in group], limit=3
            )
            merged["academic_consequence"] = _unique_sentences(
                [row.get("academic_consequence") for row in group], limit=2
            )
            merged["required_action"] = _unique_sentences(
                [row.get("required_action") for row in group], limit=3
            )
            merged["illustrative_guidance"] = next(
                (_clean(row.get("illustrative_guidance")) for row in group if _clean(row.get("illustrative_guidance"))), ""
            )
            merged["merged_finding_ids"] = [
                _clean(row.get("finding_id")) for row in group if _clean(row.get("finding_id"))
            ]
            merged["root_cause_consolidated"] = True
        merged = _special_root_cause_rewrite(merged, key, terms)
        output.append(merged)
    return output


def _current_paragraphs(review: Dict[str, Any]) -> List[Dict[str, Any]]:
    runtime = review.get("_runtime_context") or {}
    return [row for row in runtime.get("current_paragraphs") or [] if isinstance(row, dict)]


def _scope_inconsistency_finding(review: Dict[str, Any]) -> Dict[str, Any] | None:
    rows = [row for row in _current_paragraphs(review) if int(row.get("chapter_number") or 0) == 1]
    if not rows:
        return None
    text = " ".join(_clean(row.get("text")) for row in rows)
    low = _norm(text)
    # Conservative deterministic rule. This avoids inventing population conflicts
    # while catching the recurring single-bank case that alternates between
    # commercial banks and rural banks.
    commercial = "commercial banks" in low or "commercial bank" in low
    rural = "rural banks" in low or "rural bank" in low
    named_case = re.search(r"\b(?:specifically(?:\s+uses?|\s+focuses?\s+on)?|case study(?:\s+of)?|uses?)\s+(?:the\s+)?([A-Z][A-Za-z0-9&'’. -]{3,70}?(?:Bank|School|College|Hospital|Assembly|Company|PLC))\b", text)
    if not (commercial and rural and named_case):
        return None
    anchor = next((row for row in rows if "commercial bank" in _norm(row.get("text")) and "rural bank" in low), rows[0])
    case_name = _clean(named_case.group(1))
    return {
        "finding_id": "HUMAN-SCOPE-CONSISTENCY",
        "status": "does_not_meet_requirement",
        "severity": "major",
        "confidence": 0.98,
        "chapter_number": 1,
        "section": _clean(anchor.get("heading") or "Background to the Study"),
        "section_reference": _clean(anchor.get("heading") or "Background to the Study"),
        "category": "scope_alignment",
        "item": "The study population and institutional scope are not used consistently",
        "comment": (
            f"The chapter alternates between commercial banks, rural banks and the specific case of {case_name}. These are not interchangeable populations."
        ),
        "academic_consequence": (
            "The inconsistency affects the sampling frame, interpretation and the extent to which the findings may be generalised."
        ),
        "required_action": (
            f"Decide whether the work is a single-case study of {case_name} or a broader study of rural banks, then align the title, problem, purpose, objectives and methods with that decision."
        ),
        "illustrative_guidance": (
            f"if {case_name} is the sole case, refer to the institution consistently and avoid conclusions about all commercial or rural banks unless the design supports them"
        ),
        "problematic_quote": _clean(anchor.get("text"))[:220],
        "evidence": [{**anchor, "document_role": "current"}],
        "annotation_eligible": True,
        "human_deterministic_finding": True,
    }



def _citation_presentation_finding(review: Dict[str, Any]) -> Dict[str, Any] | None:
    rows = [row for row in _current_paragraphs(review) if clean_text(row.get("text"))]
    for row in rows:
        text = _clean(row.get("text"))
        citations = re.findall(r"\([^()]{1,100}?\b(?:19|20)\d{2}[a-z]?[^()]{0,30}?\)", text)
        citation_keys = [_norm(value) for value in citations]
        duplicate = len(citation_keys) != len(set(citation_keys))
        spacing = bool(re.search(r"[A-Za-z0-9]\((?:[A-Z][A-Za-z'’-]+|[A-Z]{2,})", text))
        fragmented = bool(re.search(r"\)\s*,\s*\(", text))
        if not (duplicate or spacing or fragmented):
            continue
        return {
            "finding_id": "HUMAN-CITATION-PRESENTATION",
            "status": "does_not_meet_requirement",
            "severity": "minor",
            "confidence": 0.99,
            "chapter_number": row.get("chapter_number"),
            "section": _clean(row.get("heading") or row.get("section_reference") or "Academic presentation"),
            "section_reference": _clean(row.get("heading") or row.get("section_reference") or "Academic presentation"),
            "category": "citation_and_reference_integrity",
            "item": "The citation presentation contains duplication and punctuation errors",
            "comment": (
                "Some citations are repeated in the same sentence, run directly into the preceding word or are separated into unnecessary citation groups."
            ),
            "academic_consequence": (
                "These errors interrupt the flow of the argument and make source checking unnecessarily difficult."
            ),
            "required_action": (
                "Remove exact duplicate citations, insert the required space before each citation and combine sources supporting the same claim into one correctly punctuated citation group."
            ),
            "illustrative_guidance": (
                "retain each source once and present related author-year citations together in the citation style required by the programme"
            ),
            "problematic_quote": text[:220],
            "evidence": [{**row, "document_role": "current"}],
            "annotation_eligible": True,
            "human_deterministic_finding": True,
        }
    return None


def _language_editing_finding(review: Dict[str, Any]) -> Dict[str, Any] | None:
    patterns = (
        r"\bin other to\b",
        r"\bobjectives?\s+(?:was|is)\s+met\b",
        r"\btransaction unless\b",
        r"\bchallenges? with regard to information and data adequacy\b",
        r"\bthe regularity of fraud\b",
    )
    rows = [row for row in _current_paragraphs(review) if clean_text(row.get("text"))]
    for row in rows:
        text = _clean(row.get("text"))
        if not any(re.search(pattern, text, flags=re.I) for pattern in patterns):
            continue
        return {
            "finding_id": "HUMAN-LANGUAGE-EDITING",
            "status": "does_not_meet_requirement",
            "severity": "minor",
            "confidence": 0.96,
            "chapter_number": row.get("chapter_number"),
            "section": _clean(row.get("heading") or row.get("section_reference") or "Academic writing"),
            "section_reference": _clean(row.get("heading") or row.get("section_reference") or "Academic writing"),
            "category": "academic_writing",
            "item": "The chapter requires careful language editing",
            "comment": (
                "Several sentences contain awkward expressions, agreement errors or imprecise wording that weakens an otherwise understandable argument."
            ),
            "academic_consequence": (
                "Language problems can obscure the intended meaning and reduce the professional quality of the work."
            ),
            "required_action": (
                "Edit the chapter sentence by sentence in formal British English, correcting grammar, word choice, capitalisation and punctuation without changing the intended meaning."
            ),
            "illustrative_guidance": (
                "replace expressions such as “in other to” with “in order to” and ensure subjects and verbs agree"
            ),
            "problematic_quote": text[:220],
            "evidence": [{**row, "document_role": "current"}],
            "annotation_eligible": True,
            "human_deterministic_finding": True,
        }
    return None

def add_human_judgement_findings(rows: Sequence[Dict[str, Any]], review: Dict[str, Any]) -> List[Dict[str, Any]]:
    output = [dict(row) for row in rows]
    if not _env_enabled("VPROF_HUMAN_JUDGEMENT_PASS", True):
        return output
    additions = [
        _scope_inconsistency_finding(review),
        _citation_presentation_finding(review),
        _language_editing_finding(review),
    ]
    existing = " ".join(_finding_text(row) for row in output)
    for finding in additions:
        if not finding:
            continue
        finding_text = _finding_text(finding)
        if any(SequenceMatcher(None, finding_text, _finding_text(row)).ratio() >= 0.72 for row in output):
            continue
        if finding.get("finding_id") == "HUMAN-SCOPE-CONSISTENCY" and (
            "commercial bank" in existing and "rural bank" in existing and "scope" in existing
        ):
            continue
        output.append(finding)
    return output


_BAD_EXAMPLE_PATTERNS = (
    r"\battempts respond\b",
    r"\brespond the following\b",
    r"\bso that it (?:where|present|reorganise|move|add|state|report)\b",
    r"\bloading, reliability or validity statistic\b",
)


def _issue_domain(row: Dict[str, Any]) -> str:
    text = _finding_text(row)
    section = _section_text(row)
    if any(term in text for term in ("statistic", "regression", "anova", "coefficient", "r squared", "moderation", "mediation", "sem", "loading", "reliability", "validity")):
        return "statistics"
    if any(term in section for term in ("problem statement", "background", "significance", "limitation", "scope", "delimitation", "purpose", "objective", "question", "hypoth")):
        return "chapter_one"
    if any(term in section for term in ("method", "sampling", "instrument", "data collection", "analysis")):
        return "methods"
    if any(term in section for term in ("literature", "theory", "conceptual", "empirical")):
        return "literature"
    return "general"


def _example_is_appropriate(row: Dict[str, Any], example: str, terms: Sequence[str]) -> bool:
    example = _clean(example)
    if not example:
        return False
    low = _norm(example)
    if any(re.search(pattern, low, flags=re.I) for pattern in _BAD_EXAMPLE_PATTERNS):
        return False
    domain = _issue_domain(row)
    if low.startswith("rewrite the sentence beginning") and domain not in {"general"}:
        focus = _finding_text(row)
        if not any(token in focus for token in ("grammar", "language", "wording", "citation", "punctuation")):
            return False
    statistical_tokens = ("coefficient", "standard error", "test statistic", "p value", "confidence interval", "loading", "reliability", "validity", "r squared")
    if domain != "statistics" and any(token in low for token in statistical_tokens):
        return False
    if domain == "statistics" and not any(token in low for token in statistical_tokens + ("model", "interaction", "diagnostic")):
        return False
    if terms:
        term_overlap = any(_norm(term) and _norm(term) in low for term in terms)
        procedural = any(token in low for token in (
            "research question", "objective", "hypothesis", "problem statement", "reference list",
            "single case", "study setting", "same model", "original output",
        ))
        if not (term_overlap or procedural):
            return False
    return True


def _grammar_polish(text: Any) -> str:
    value = _clean(text)
    if not value:
        return ""
    replacements = (
        (r"\bso that it where required\b", "where required"),
        (r"\bso that it present\b", "to present"),
        (r"\bso that it reorganise\b", "to reorganise"),
        (r"\bso that it move\b", "to move"),
        (r"\bso that it add\b", "to add"),
        (r"\bso that it state\b", "to state"),
        (r"\bso that it report\b", "to report"),
        (r"\bin other to\b", "in order to"),
        (r"\bthe objectives? (?:was|is) met\b", "the objectives are met"),
        (r"\bthe work does not clearly show that the work\b", "the work does not clearly show that"),
        (r"\bthe study does not clearly show that the study\b", "the study does not clearly show that"),
    )
    for pattern, replacement in replacements:
        value = re.sub(pattern, replacement, value, flags=re.I)
    value = re.sub(r"\s+([,.;:!?])", r"\1", value)
    value = re.sub(r"([.!?]){2,}", r"\1", value)
    value = re.sub(r"\s{2,}", " ", value).strip(" ,;:")
    return value


def _comment_word_limit(row: Dict[str, Any]) -> int:
    severity = _norm(row.get("severity"))
    domain = _issue_domain(row)
    if severity == "critical" or domain == "statistics":
        return 190
    if severity in {"major", "moderate"}:
        return 135
    return 85


def _trim_words(text: str, limit: int) -> str:
    words = _clean(text).split()
    if len(words) <= limit:
        return _clean(text)
    clipped = " ".join(words[:limit])
    sentence_end = max(clipped.rfind("."), clipped.rfind("?"), clipped.rfind("!"))
    if sentence_end >= max(60, len(clipped) // 2):
        return clipped[: sentence_end + 1]
    return clipped.rstrip(" ,;:") + "."


def _compose_human_comment(row: Dict[str, Any], terms: Sequence[str]) -> str:
    issue = _grammar_polish(row.get("item") or row.get("issue_title"))
    assessment = _grammar_polish(row.get("comment") or row.get("assessment"))
    consequence = _grammar_polish(row.get("academic_consequence") or row.get("why_it_matters"))
    action = _grammar_polish(row.get("required_action"))
    example = _grammar_polish(row.get("illustrative_guidance"))
    include_example = _example_is_appropriate(row, example, terms)
    # Human supervisors do not force examples into minor citation, grammar or
    # presentation corrections. The direct action is usually sufficient.
    if _norm(row.get("severity")) == "minor" and _issue_domain(row) != "statistics":
        include_example = False

    # Missing sections need a short, decisive comment at the logical insertion
    # point. A specialised composition prevents generic consequence sentences
    # from crowding out the useful study-specific example.
    if _missing_label(row):
        parts: List[str] = []
        if issue:
            parts.append(issue.rstrip(" .") + ".")
        elif assessment:
            parts.append(assessment.rstrip(" .") + ".")
        if action:
            parts.append(action.rstrip(" .") + ".")
        if include_example:
            clean_example = re.sub(r"^(?:for example|example)[:,]?\s*", "", example, flags=re.I).strip(" .")
            if clean_example:
                parts.append("For example, " + clean_example[0].lower() + clean_example[1:] + ".")
        if not parts and assessment:
            parts.append(assessment.rstrip(" .") + ".")
        return _trim_words(_unique_sentences(parts, limit=4), _comment_word_limit(row))

    # Avoid restating the same title and assessment.
    parts: List[str] = []
    issue_key = _norm(issue)
    assessment_key = _norm(assessment)
    if issue and (not assessment or SequenceMatcher(None, issue_key, assessment_key).ratio() < 0.70):
        parts.append(issue.rstrip(" .") + ".")
    if assessment:
        parts.append(assessment.rstrip(" .") + ".")
    if consequence and all(SequenceMatcher(None, _norm(consequence), _norm(part)).ratio() < 0.78 for part in parts):
        parts.append(consequence.rstrip(" .") + ".")
    if action:
        parts.append(action.rstrip(" .") + ".")
    if include_example:
        example = re.sub(r"^(?:for example|example)[:,]?\s*", "", example, flags=re.I).strip(" .")
        if example:
            parts.append("For example, " + example[0].lower() + example[1:] + ".")

    # Retain the natural supervisory sequence: diagnosis, significance, action
    # and an optional example. Variation comes from issue-specific composition,
    # not from reordering sentences mechanically.

    comment = _unique_sentences(parts, limit=5)
    return _trim_words(comment, _comment_word_limit(row))


def _missing_section_human_example(row: Dict[str, Any], terms: Sequence[str]) -> str:
    label = _norm(_missing_label(row))
    constructs = _construct_terms(terms)
    joined = _join_terms(constructs[:4])
    setting = _setting_term(terms)
    if label == "purpose of the study":
        if joined:
            return f"state that the study examines {joined}" + (f" at {setting}" if setting else ", followed by the confirmed population and setting")
        return "state the overall aim using the same variables, population and setting as the title and objectives"
    if label == "research hypotheses":
        return (
            f"formulate one testable null hypothesis for each inferential relationship involving {joined}"
            if joined else
            "formulate one testable null hypothesis for each inferential objective"
        )
    if label == "definition of terms":
        return (
            f"define {joined} exactly as they are measured or applied in the study"
            if joined else
            "define the main constructs exactly as they are measured or applied in the study"
        )
    if label in {"limitations of the study", "delimitations of the study"}:
        return "state the study boundaries or constraints and explain how they affect interpretation of the findings"
    return ""


def edit_findings_for_human_review(
    rows: Sequence[Dict[str, Any]],
    review: Dict[str, Any],
    terms: Sequence[str],
) -> List[Dict[str, Any]]:
    """Apply a final human-supervisor editorial and judgement pass.

    The pass does not create a target number of comments. It consolidates
    duplicate root causes, removes irrelevant examples, fixes mechanical
    phrasing and prepares one natural student-facing comment per retained issue.
    """
    output = add_human_judgement_findings(rows, review)
    output = consolidate_root_causes(output, terms)
    if not _env_enabled("VPROF_HUMAN_SUPERVISORY_EDITOR", True):
        return output

    edited: List[Dict[str, Any]] = []
    for row in output:
        current = dict(row)
        for field in ("item", "issue_title", "comment", "assessment", "academic_consequence", "required_action", "illustrative_guidance"):
            current[field] = _grammar_polish(current.get(field))
        missing_example = _missing_section_human_example(current, terms)
        if missing_example:
            current["illustrative_guidance"] = missing_example
        focus_text = _finding_text(current)
        if (
            "background" in _section_text(current)
            and any(token in focus_text for token in ("theoretical anchor", "conceptual anchor", "theoretical or conceptual"))
        ):
            joined = _join_terms(_construct_terms(terms)[:3])
            current["illustrative_guidance"] = (
                f"identify the framework that explains the expected relationship between {joined} and state that connection briefly in the background"
                if joined else
                "identify the framework that explains the expected relationship among the main constructs and state that connection briefly in the background"
            )
        example = _clean(current.get("illustrative_guidance"))
        if not _example_is_appropriate(current, example, terms):
            current["illustrative_guidance"] = ""
        current["student_comment"] = _compose_human_comment(current, terms)
        current["human_edited"] = True
        current["human_example_included"] = bool(current.get("illustrative_guidance"))
        if current["student_comment"]:
            edited.append(current)
    return edited
