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
        sentence = _sentence_form(sentence)
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

    if any(term in section for term in ("scope", "delimitation")):
        if _norm(row.get("category")) == "scope_completeness" or any(term in text for term in (
            "scope section is incomplete", "unit of analysis", "study period", "important exclusions",
        )):
            return (chapter, "scope_completeness")
        if any(term in text for term in (
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
        concrete_text = _clean(" ".join(_clean(output.get(field)) for field in (
            "item", "issue_title", "comment", "assessment", "required_action"
        )))
        if not output.get("root_cause_consolidated") and re.search(
            r"\bObjective\s+\d+\b|\bResearch Question\s+\d+\b|\bH[01]\b",
            concrete_text,
            flags=re.I,
        ):
            return output
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

    elif family == "scope_completeness":
        output["item"] = output["issue_title"] = "The scope section is incomplete"
        output["comment"] = output["assessment"] = (
            "The section identifies the general topic and setting, but it does not define all the boundaries needed to understand exactly what the study covers."
        )
        output["academic_consequence"] = (
            "The population, unit of analysis and limits of the proposed conclusions remain unclear."
        )
        output["required_action"] = (
            "State the institutional or geographical boundary, participant group or unit of analysis, main constructs, period covered and important exclusions."
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


def _safe_excerpt(value: Any, limit: int = 260) -> str:
    """Return a complete, word-safe excerpt suitable for a human comment anchor."""
    text = _clean(value)
    if len(text) <= limit:
        return text
    clipped = text[:limit]
    sentence_end = max(clipped.rfind("."), clipped.rfind("?"), clipped.rfind("!"))
    if sentence_end >= max(80, int(limit * 0.55)):
        return clipped[: sentence_end + 1].strip()
    word_end = clipped.rfind(" ")
    if word_end >= max(50, int(limit * 0.65)):
        clipped = clipped[:word_end]
    return clipped.rstrip(" ,;:-") + "…"


def _natural_term(value: Any) -> str:
    text = _clean(value)
    if not text:
        return ""
    text = re.sub(r"\bbehavioral\b", "behavioural", text, flags=re.I)
    text = re.sub(r"\brationalization\b", "rationalisation", text, flags=re.I)

    match = re.match(
        r"^(.+?)\s+(at|within)\s+(.+?(?:Bank|PLC|University|College|School|Hospital|Assembly|Company|Municipality|District|Region)(?:\s+PLC)?)$",
        text,
        flags=re.I,
    )
    if match:
        return f"{_natural_term(match.group(1))} {match.group(2).lower()} {match.group(3)}"
    if re.fullmatch(
        r"(?:the\s+)?[A-Z][A-Za-z0-9&'’. -]{2,100}?(?:Bank|PLC|University|College|School|Hospital|Assembly|Company|Municipality|District|Region)(?:\s+PLC)?",
        text,
    ):
        return text

    words: List[str] = []
    for token in text.split():
        stripped = token.strip(" ,.;:()")
        if stripped.isupper() and 1 < len(stripped) <= 8:
            words.append(token)
        else:
            words.append(token.lower())
    return " ".join(words)

def _sentence_form(value: Any) -> str:
    text = _clean(value).strip(" ;")
    if not text:
        return ""
    if re.search(r"[.!?][\"'”’)]$", text) or text[-1:] in ".!?":
        return text
    return text + "."


def _row_heading(row: Dict[str, Any]) -> str:
    path = [value for value in (row.get("section_path") or []) if _clean(value)]
    return _clean(row.get("heading") or row.get("section_reference") or (path[-1] if path else ""))


def _chapter_rows(review: Dict[str, Any], chapter: int = 1) -> List[Dict[str, Any]]:
    return [
        row for row in _current_paragraphs(review)
        if int(row.get("chapter_number") or 0) == chapter and _clean(row.get("text"))
    ]


def _section_rows(review: Dict[str, Any], *tokens: str, chapter: int = 1) -> List[Dict[str, Any]]:
    wanted = tuple(_norm(token) for token in tokens if _norm(token))
    output: List[Dict[str, Any]] = []
    for row in _chapter_rows(review, chapter):
        heading = _norm(_row_heading(row))
        path = _norm(" ".join(_clean(value) for value in (row.get("section_path") or [])))
        if any(token in heading or token in path for token in wanted):
            output.append(row)
    return output


def _first_sentence(value: Any) -> str:
    text = _clean(value)
    if not text:
        return ""
    sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0]
    return sentence.strip()


def _study_setting(review: Dict[str, Any], terms: Sequence[str]) -> str:
    setting = _setting_term(terms)
    if setting:
        return setting
    text = " ".join(_clean(row.get("text")) for row in _chapter_rows(review, 1))
    patterns = (
        r"\b((?:[A-Z][A-Za-z0-9&'’. -]+?\s+)?Rural\s+Bank(?:\s+PLC)?)\b",
        r"\b([A-Z][A-Za-z0-9&'’. -]{3,90}?(?:Bank|University|College|School|Hospital|Assembly|Company|Municipality|District|Region)(?:\s+PLC)?)\b",
    )
    candidates: List[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            candidate = _clean(match.group(1)).strip(" ,.;:")
            if candidate and not re.fullmatch(r"(?:Commercial|Rural) Banks?", candidate, flags=re.I):
                candidates.append(candidate)
    if not candidates:
        return ""
    # Prefer a named case that appears after "specifically" or "case study".
    for candidate in candidates:
        if re.search(rf"(?:specifically|case study(?: of)?|at)\s+(?:the\s+)?{re.escape(candidate)}", text, flags=re.I):
            return candidate
    return max(candidates, key=len)


def _objective_texts(review: Dict[str, Any]) -> List[str]:
    values: List[str] = []
    for row in _section_rows(review, "research objectives", "general objective", "specific objectives"):
        if row.get("is_heading"):
            continue
        text = _clean(row.get("text"))
        if not text:
            continue
        parts = re.split(r"(?=(?:^|\s)(?:[ivx]+|\d+)[.)]\s+To\s+)|(?<=[.!?])\s+", text, flags=re.I)
        for part in parts:
            part = _clean(re.sub(r"^(?:[ivx]+|\d+)[.)]\s*", "", part, flags=re.I))
            if re.search(r"\b(?:objective|aim|purpose)\b", part, flags=re.I) or re.match(r"^To\s+", part, flags=re.I):
                values.append(part)
    return list(dict.fromkeys(values))


def _question_texts(review: Dict[str, Any]) -> List[str]:
    values: List[str] = []
    for row in _section_rows(review, "research questions", "research question"):
        if row.get("is_heading"):
            continue
        text = _clean(row.get("text"))
        for part in re.split(r"(?<=[?])\s+|(?=(?:^|\s)(?:[ivx]+|\d+)[.)]\s+)", text, flags=re.I):
            part = _clean(re.sub(r"^(?:[ivx]+|\d+)[.)]\s*", "", part, flags=re.I))
            if "?" in part or re.match(r"^(?:What|How|Which|To what|Is|Are|Does|Do)\b", part, flags=re.I):
                values.append(part)
    return list(dict.fromkeys(values))


def _relation_pairs(review: Dict[str, Any]) -> List[Tuple[str, str]]:
    sources = []
    context = review.get("study_context") or {}
    sources.append(_clean(context.get("title_or_opening_focus")))
    sources.append(_clean((review.get("summary") or {}).get("study_title")))
    sources.extend(_objective_texts(review))
    pairs: List[Tuple[str, str]] = []
    for text in sources:
        if not text:
            continue
        for pattern in (
            r"(?:effect|impact|influence)\s+of\s+(.+?)\s+on\s+(.+?)(?:[.;]|$)",
            r"relationship\s+between\s+(.+?)\s+and\s+(.+?)(?:[.;]|$)",
        ):
            for match in re.finditer(pattern, text, flags=re.I):
                left = _clean(match.group(1)).strip(" ,.;:")
                right = _clean(match.group(2)).strip(" ,.;:")
                right = re.sub(r"\s+(?:at|within)\s+[A-Z].*$", "", right).strip(" ,.;:")
                if left and right:
                    pairs.append((left, right))
    return pairs


def _profile_constructs(review: Dict[str, Any], terms: Sequence[str]) -> List[str]:
    values: List[str] = []
    setting = _study_setting(review, terms)
    for value in _construct_terms(terms):
        if value and _norm(value) != _norm(setting):
            values.append(value)
    for left, right in _relation_pairs(review):
        values.extend([left, right])
    text = " ".join(_objective_texts(review))
    for match in re.finditer(r"\(([^()]{3,120})\)", text):
        for part in re.split(r",|\band\b", match.group(1), flags=re.I):
            part = _clean(part).strip(" ,.;:")
            if 2 <= len(part.split()) <= 5:
                values.append(part)
    cleaned: List[str] = []
    seen = set()
    for value in values:
        value = re.sub(r"\b(?:among|in)\s+(?:commercial|rural)?\s*banks?.*$", "", _clean(value), flags=re.I)
        value = re.sub(r"\b(?:at|within)\s+[A-Z].*$", "", value).strip(" ,.;:")
        value = re.sub(r"\bbehavioral\b", "behavioural", value, flags=re.I)
        value = re.sub(r"\brationalization\b", "rationalisation", value, flags=re.I)
        key = _norm(value)
        if not key or len(value) < 3 or key in seen or _is_setting_term(value):
            continue
        if key in {"study", "research", "banking sector", "financial system"}:
            continue
        seen.add(key)
        cleaned.append(value)
        if len(cleaned) >= 8:
            break
    return cleaned


def _purpose_example(review: Dict[str, Any], terms: Sequence[str]) -> str:
    setting = _study_setting(review, terms)
    pairs = _relation_pairs(review)
    if pairs:
        left, right = pairs[0]
        left = _natural_term(left)
        right = _natural_term(right)
        tail = f" at {setting}" if setting else " in the confirmed study setting"
        return f"write: “The purpose of the study is to examine the relationship between {left} and {right}{tail}. ”".replace(". ”", ".”")
    for text in _objective_texts(review):
        sentence = _first_sentence(text)
        if not sentence:
            continue
        if re.search(r"(?:primary|general|main) objective of (?:this|the) study is to", sentence, flags=re.I):
            sentence = re.sub(
                r"^(?:The\s+)?(?:primary|general|main) objective of (?:this|the) study is to",
                "The purpose of the study is to",
                sentence,
                flags=re.I,
            )
            if setting:
                sentence = re.sub(r"\s+among\s+(?:commercial|rural)\s+banks?.*?(?=[,.;]|$)", f" at {setting}", sentence, flags=re.I)
                sentence = re.sub(r",?\s*specifically\s+" + re.escape(setting), "", sentence, flags=re.I)
            return f"write: “{sentence.rstrip('.')}.”"
        if re.match(r"^To\s+", sentence, flags=re.I):
            return f"write: “The purpose of the study is {sentence[0].lower() + sentence[1:].rstrip('.')}.”"
    constructs = [_natural_term(value) for value in _profile_constructs(review, terms)]
    joined = _join_terms(constructs[:4])
    return f"state that the study examines {joined}" + (f" at {setting}" if setting else " using the confirmed population and setting") if joined else ""

def _hypothesis_example(review: Dict[str, Any], terms: Sequence[str]) -> str:
    inferential = [
        text for text in _objective_texts(review)
        if re.search(r"\b(effect|impact|influence|relationship|association|predict|contribut)\b", text, flags=re.I)
    ]
    source = inferential[-1] if inferential else ""
    match = re.search(r"(?:effect|impact|influence)\s+of\s+(.+?)\s+on\s+(.+?)(?:[.;]|$)", source, flags=re.I)
    if match:
        left = _clean(match.group(1)).strip(" ,.;:")
        parenthetical = re.search(r"\(([^()]+)\)", left)
        if parenthetical:
            left = parenthetical.group(1)
        left = _natural_term(left)
        right = _natural_term(_clean(match.group(2)).strip(" ,.;:"))
        return f"a matching null hypothesis could read: “H0: There is no statistically significant relationship between {left} and {right}.”"
    pairs = _relation_pairs(review)
    if pairs:
        left, right = pairs[-1]
        return f"a matching null hypothesis could read: “H0: There is no statistically significant relationship between {_natural_term(left)} and {_natural_term(right)}.”"
    constructs = [_natural_term(value) for value in _profile_constructs(review, terms)]
    return f"formulate one testable null hypothesis for each inferential relationship involving {_join_terms(constructs[:4])}" if constructs else ""

def _definition_example(review: Dict[str, Any], terms: Sequence[str]) -> str:
    constructs: List[str] = []
    for value in _profile_constructs(review, terms):
        match = re.search(r"\(([^()]+)\)", value)
        if match:
            for part in re.split(r",|\band\b", match.group(1), flags=re.I):
                part = _natural_term(part.strip(" ,.;:"))
                if part:
                    constructs.append(part)
            continue
        constructs.append(_natural_term(value))
    constructs = list(dict.fromkeys(value for value in constructs if value))
    if not constructs:
        return "define the main constructs exactly as they are measured or applied in the study"
    return f"define {_join_terms(constructs[:7])} according to how each concept will be measured or applied in the study"

def _problem_example(review: Dict[str, Any], terms: Sequence[str]) -> str:
    setting = _study_setting(review, terms) or "the study context"
    pairs = _relation_pairs(review)
    if pairs:
        left, right = pairs[0]
        return (
            f"add recent regulatory, institutional or empirical evidence showing the nature or scale of the problem at {setting}, "
            f"then explain what remains unknown about {_natural_term(left)} in relation to {_natural_term(right)}"
        )
    constructs = _profile_constructs(review, terms)
    return (
        f"add recent evidence showing the problem at {setting}, then state what remains unresolved about {_join_terms(constructs[:4])}"
        if constructs else
        f"add recent evidence showing the problem at {setting}, then state the precise unresolved issue"
    )


def _unit_options(setting: str) -> str:
    low = _norm(setting)
    if any(token in low for token in ("bank", "company", "firm", "assembly")):
        return "staff, managers, customers, transactions or institutional records"
    if any(token in low for token in ("university", "college", "school")):
        return "students, lecturers or teachers, administrators, classes or institutional records"
    if "hospital" in low:
        return "patients, clinicians, administrators or clinical records"
    return "participants, organisations, documents, transactions or records"


def _scope_example(review: Dict[str, Any], terms: Sequence[str]) -> str:
    setting = _study_setting(review, terms)
    constructs = _profile_constructs(review, terms)
    unit_text = _unit_options(setting)
    where = f" at {setting}" if setting else " in the study setting"
    return (
        f"state the institution or location, the participant group or unit of analysis, the study period, the main constructs and the exclusions; "
        f"clarify whether the evidence comes from {unit_text}{where} rather than leaving the unit unspecified"
    )


def _significance_example(review: Dict[str, Any], terms: Sequence[str]) -> str:
    setting = _study_setting(review, terms)
    pairs = _relation_pairs(review)
    focus = ""
    if pairs:
        focus = f"the relationship between {_natural_term(pairs[0][0])} and {_natural_term(pairs[0][1])}"
    else:
        constructs = _profile_constructs(review, terms)
        focus = _join_terms(constructs[:4]) or "the study findings"
    practice = f" improve practice at {setting}" if setting else " improve practice in the study setting"
    return f"state separately how evidence on {focus} may extend knowledge,{practice}, and inform relevant policy or regulation"


def _limitations_example(review: Dict[str, Any], terms: Sequence[str]) -> str:
    setting = _study_setting(review, terms)
    if setting:
        return (
            f"state that evidence from one case, {setting}, cannot automatically be generalised to all institutions, "
            "and explain the conditions under which the findings may be transferable to similar settings"
        )
    return "identify each design, sampling, measurement or access constraint and explain how it limits interpretation or generalisation"


def _objective_alignment_example(review: Dict[str, Any], terms: Sequence[str]) -> str:
    objectives = _objective_texts(review)
    questions = _question_texts(review)
    clauses: List[str] = []
    descriptive = next((text for text in objectives if re.search(r"\b(assess|describe|identify|establish the level|determine the extent)\b", text, flags=re.I) and not re.search(r"\b(effect|impact|influence|relationship)\b", text, flags=re.I)), "")
    constructs = [_natural_term(value) for value in _profile_constructs(review, terms)]
    if descriptive:
        focus = next((value for value in constructs if _norm(value) in _norm(descriptive)), "the first objective")
        clauses.append(f"treat the objective on {focus} as descriptive")
    if any(re.search(r"\b(effectiveness|rate of|successful)\b", text, flags=re.I) for text in objectives + questions):
        clauses.append("define exactly how effectiveness or a successful detection or prevention rate will be calculated")
    inferential = next((text for text in reversed(objectives) if re.search(r"\b(effect|impact|influence|relationship|predict|contribut)\b", text, flags=re.I)), "")
    if inferential:
        parenthetical = re.search(r"\(([^()]+)\)", inferential)
        if parenthetical:
            subject = _natural_term(parenthetical.group(1))
        else:
            pair = re.search(r"(?:effect|impact|influence)\s+of\s+(.+?)\s+on\s+", inferential, flags=re.I)
            subject = _natural_term(pair.group(1)) if pair else "the inferential objective"
        clauses.append(f"treat the objective involving {subject} as associational or predictive unless the design supports a causal claim")
    clauses = clauses[:3]
    if len(clauses) <= 1:
        return clauses[0] if clauses else ""
    if len(clauses) == 2:
        return f"{clauses[0]}; and {clauses[1]}"
    return f"{clauses[0]}; {clauses[1]}; and {clauses[2]}"

def _scope_completeness_finding(review: Dict[str, Any], terms: Sequence[str]) -> Dict[str, Any] | None:
    if not _env_enabled("VPROF_SCOPE_COMPLETENESS_AUDIT", True):
        return None
    rows = [row for row in _section_rows(review, "scope of the study", "delimitation of the study", "delimitations of the study") if not row.get("is_heading")]
    if not rows:
        return None
    text = " ".join(_clean(row.get("text")) for row in rows)
    low = _norm(text)
    setting = bool(_study_setting(review, terms) or re.search(r"\b(?:district|region|municipality|university|college|school|bank|company|hospital)\b", low))
    population = bool(re.search(r"\b(?:participants?|respondents?|students?|teachers?|lecturers?|employees?|staff|managers?|customers?|households?|firms?|organisations?|records?|transactions?|unit of analysis|population)\b", low))
    constructs = _profile_constructs(review, terms)
    construct_coverage = bool(constructs and any(_norm(value) in low for value in constructs if len(_norm(value)) >= 4))
    period = bool(re.search(r"\b(?:19|20)\d{2}\b|\bstudy period\b|\bacademic year\b|\bfinancial year\b|\bbetween\b.+\band\b", text, flags=re.I))
    exclusions = bool(re.search(r"\b(?:limited to|delimited to|excluding|does not include|will not cover|only|outside the scope)\b", low))
    checks = {"setting": setting, "participant group or unit of analysis": population, "constructs": construct_coverage, "study period": period, "important exclusions": exclusions}
    missing = [label for label, present in checks.items() if not present]
    if len(missing) < 2 and population:
        return None
    anchor = rows[-1]
    missing_text = _join_terms(missing)
    return {
        "finding_id": "HUMAN-SCOPE-COMPLETENESS",
        "status": "partly_meets_requirement",
        "severity": "major" if not population else "moderate",
        "confidence": 0.97,
        "chapter_number": 1,
        "section": _row_heading(anchor) or "Scope of the Study",
        "section_reference": _row_heading(anchor) or "Scope of the Study",
        "category": "scope_completeness",
        "item": "The scope section is incomplete",
        "comment": f"The section identifies part of the study focus, but it does not clearly state {missing_text}.",
        "academic_consequence": "The reader cannot determine precisely what the study covers, what it excludes or the population to which the findings relate.",
        "required_action": "State the institutional or geographical boundary, participant group or unit of analysis, constructs, period covered and important exclusions.",
        "illustrative_guidance": _scope_example(review, terms),
        "problematic_quote": _safe_excerpt(anchor.get("text")),
        "evidence": [{**anchor, "document_role": "current"}],
        "annotation_eligible": True,
        "human_deterministic_finding": True,
    }


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
    if not _env_enabled("VPROF_MICRO_LANGUAGE_CITATION_AUDIT", True):
        return None
    rows = [row for row in _current_paragraphs(review) if clean_text(row.get("text"))]
    for row in rows:
        text = _clean(row.get("text"))
        citations = re.findall(r"\([^()]{1,120}?\b(?:19|20)\d{2}[a-z]?[^()]{0,40}?\)", text)
        citation_keys = [_norm(value) for value in citations]
        duplicate = len(citation_keys) != len(set(citation_keys))
        spacing = bool(re.search(r"[A-Za-z0-9]\((?:[A-Z][A-Za-z'’-]+|[A-Z]{2,})", text))
        fragmented = bool(re.search(r"\)\s*,\s*\(", text))
        if not (duplicate or spacing or fragmented):
            continue
        unique_inner: List[str] = []
        seen = set()
        for citation in citations:
            inner = citation[1:-1].strip(" ,;")
            key = _norm(inner)
            if not key or key in seen:
                continue
            seen.add(key)
            unique_inner.append(inner)
        example = ""
        if unique_inner:
            example = f"where the sources support the same claim, present them once in a single group, such as “({'; '.join(unique_inner[:4])})”"
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
            "comment": "Some citations are repeated in the same sentence, run directly into the preceding word or are separated into unnecessary citation groups.",
            "academic_consequence": "These errors interrupt the flow of the argument and make source checking unnecessarily difficult.",
            "required_action": "Remove exact duplicate citations, insert the required space before each citation and combine sources supporting the same claim into one correctly punctuated citation group.",
            "illustrative_guidance": example,
            "problematic_quote": _safe_excerpt(text),
            "evidence": [{**row, "document_role": "current"}],
            "annotation_eligible": True,
            "human_deterministic_finding": True,
        }
    return None

def _language_editing_finding(review: Dict[str, Any]) -> Dict[str, Any] | None:
    if not _env_enabled("VPROF_MICRO_LANGUAGE_CITATION_AUDIT", True):
        return None
    rules = (
        (r"\bin other to\b", "in other to", "in order to"),
        (r"\bobjectives?\s+(?:was|is)\s+met\b", "objectives was met", "objectives were met"),
        (r"\ball transaction\b", "all transaction", "all transactions"),
        (r"\bbehavioral\b", "behavioral", "behavioural"),
        (r"\brationalization\b", "rationalization", "rationalisation"),
        (r"\bgeneralization\b", "generalization", "generalisation"),
        (r"\banalyzing\b", "analyzing", "analysing"),
        (r"\bthe regularity of fraud\b", "the regularity of fraud", "the incidence or frequency of fraud"),
    )
    rows = [row for row in _current_paragraphs(review) if clean_text(row.get("text"))]
    examples: List[Tuple[str, str]] = []
    anchor: Dict[str, Any] | None = None
    capitalisation_rows: List[Dict[str, Any]] = []
    for row in rows:
        text = _clean(row.get("text"))
        row_found = False
        for pattern, wrong, right in rules:
            if re.search(pattern, text, flags=re.I):
                if (wrong, right) not in examples:
                    examples.append((wrong, right))
                row_found = True
        if re.search(r"(?<![.!?]\s)\bRural banks\b", text):
            capitalisation_rows.append(row)
        if row_found and anchor is None:
            anchor = row
        if len(examples) >= 4:
            break
    if anchor is None:
        return None
    if capitalisation_rows and ("Rural banks", "rural banks") not in examples:
        examples.append(("Rural banks", "rural banks"))
    guidance = "; ".join(f"change “{wrong}” to “{right}”" for wrong, right in examples[:4])
    return {
        "finding_id": "HUMAN-LANGUAGE-EDITING",
        "status": "does_not_meet_requirement",
        "severity": "minor",
        "confidence": 0.97,
        "chapter_number": anchor.get("chapter_number"),
        "section": _clean(anchor.get("heading") or anchor.get("section_reference") or "Academic writing"),
        "section_reference": _clean(anchor.get("heading") or anchor.get("section_reference") or "Academic writing"),
        "category": "academic_writing",
        "item": "The chapter requires careful language editing",
        "comment": "Several sentences contain awkward expressions, agreement errors, inconsistent British spelling or imprecise wording.",
        "academic_consequence": "These language problems can obscure the intended meaning and reduce the professional quality of the work.",
        "required_action": "Edit the chapter sentence by sentence in formal British English, correcting grammar, word choice, capitalisation and punctuation without changing the intended meaning.",
        "illustrative_guidance": guidance,
        "problematic_quote": _safe_excerpt(anchor.get("text")),
        "evidence": [{**anchor, "document_role": "current"}],
        "annotation_eligible": True,
        "human_deterministic_finding": True,
    }

def add_human_judgement_findings(
    rows: Sequence[Dict[str, Any]],
    review: Dict[str, Any],
    terms: Sequence[str],
) -> List[Dict[str, Any]]:
    output = [dict(row) for row in rows]
    if not _env_enabled("VPROF_HUMAN_JUDGEMENT_PASS", True):
        return output
    additions = [
        _scope_inconsistency_finding(review),
        _scope_completeness_finding(review, terms),
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

_STATISTICAL_OUTPUT_TOKENS = (
    "coefficient", "standard error", "test statistic", "degrees of freedom", "p value",
    "confidence interval", "model diagnostic", "r squared", "f statistic", "t statistic",
    "factor loading", "reliability coefficient", "validity statistic", "anova table",
)


def _core_finding_text(row: Dict[str, Any]) -> str:
    return _norm(" ".join(_clean(row.get(field)) for field in (
        "category", "item", "issue_title", "comment", "assessment", "required_action", "academic_consequence"
    )))


def _issue_domain(row: Dict[str, Any]) -> str:
    """Classify from the actual section and issue, never from a stale example."""
    section = _section_text(row)
    category = _norm(row.get("category"))
    text = _core_finding_text(row)
    missing = _norm(_missing_label(row))
    if missing == "purpose of the study":
        return "purpose"
    if missing == "research hypotheses":
        return "objective_alignment"
    if missing == "definition of terms":
        return "definition_terms"
    if missing == "limitations of the study":
        return "limitations"
    if missing == "delimitations of the study":
        return "scope"

    if "problem statement" in section or re.search(r"\bstatement of the problem\b", section):
        return "problem_statement"
    if any(term in section for term in ("limitation",)):
        return "limitations"
    if any(term in section for term in ("scope", "delimitation")):
        return "scope"
    if "significance" in section or "contribution" in section:
        return "significance"
    if "purpose" in section or "purpose of the study" in text:
        return "purpose"
    if any(term in section for term in ("objective", "question", "hypoth")):
        return "objective_alignment"
    if "definition" in section or "definition of terms" in text:
        return "definition_terms"
    if "background" in section and chapter_number(row) == 1:
        return "background"

    statistical_section = any(term in section for term in (
        "result", "finding", "analysis", "regression", "model", "coefficient", "table"
    ))
    statistical_category = any(term in category for term in (
        "statistical", "analysis_appropriateness", "measurement", "results"
    ))
    if statistical_section or statistical_category or (
        any(term in text for term in ("regression", "anova", "r squared", "moderation", "mediation", "sem", "pls"))
        and chapter_number(row) in {3, 4, 5}
    ):
        return "statistics"
    if any(term in section for term in ("method", "sampling", "instrument", "data collection", "data analysis")):
        return "methods"
    if any(term in section for term in ("literature", "theory", "conceptual", "empirical")):
        return "literature"
    if any(term in text for term in ("citation", "reference", "source")):
        return "references"
    if any(term in text for term in ("grammar", "language", "wording", "punctuation", "capitalisation")):
        return "language"
    return "general"


def _scrub_cross_domain_contamination(row: Dict[str, Any]) -> Dict[str, Any]:
    """Remove guidance sentences imported from the wrong chapter or issue family."""
    output = dict(row)
    domain = _issue_domain(output)
    if domain == "statistics":
        return output
    for field in ("comment", "assessment", "academic_consequence", "required_action", "illustrative_guidance"):
        sentences = _sentences(output.get(field))
        kept: List[str] = []
        for sentence in sentences:
            low = _norm(sentence)
            if any(token in low for token in _STATISTICAL_OUTPUT_TOKENS):
                continue
            if domain in {"problem_statement", "scope", "significance", "limitations", "background", "purpose", "definition_terms"} and any(
                token in low for token in ("loading", "cronbach", "composite reliability", "discriminant validity", "regression diagnostic")
            ):
                continue
            kept.append(sentence)
        output[field] = " ".join(kept)
    return output


def _example_is_appropriate(row: Dict[str, Any], example: str, terms: Sequence[str]) -> bool:
    example = _clean(example)
    if not example:
        return False
    if not _env_enabled("VPROF_SEMANTIC_EXAMPLE_GATE", True):
        return True
    low = _norm(example)
    if any(re.search(pattern, low, flags=re.I) for pattern in _BAD_EXAMPLE_PATTERNS):
        return False
    domain = _issue_domain(row)
    if low.startswith("rewrite the sentence beginning") and domain not in {"general", "language", "references"}:
        return False
    if domain != "statistics" and any(token in low for token in _STATISTICAL_OUTPUT_TOKENS):
        return False
    if domain == "statistics" and not any(token in low for token in _STATISTICAL_OUTPUT_TOKENS + ("model", "interaction", "diagnostic", "assumption", "original output")):
        return False

    allowed_by_domain = {
        "problem_statement": ("evidence", "scale", "nature", "unresolved", "unknown", "problem", "regulatory", "institutional", "empirical"),
        "scope": ("setting", "institution", "location", "participant", "unit of analysis", "period", "construct", "exclusion", "single case", "records", "transactions"),
        "significance": ("knowledge", "scholarly", "practice", "policy", "regulation", "contribution"),
        "limitations": ("constraint", "generalisation", "transfer", "single case", "sampling", "access", "interpretation"),
        "purpose": ("purpose", "study is to", "examines", "assesses", "investigates"),
        "objective_alignment": ("objective", "question", "hypothesis", "descriptive", "associational", "predictive", "causal", "measured", "analysis"),
        "definition_terms": ("define", "measured", "applied", "operational"),
        "background": ("framework", "conceptual", "relationship", "briefly", "chapter two", "evidence", "organise", "context", "unresolved", "progression"),
    }
    expected = allowed_by_domain.get(domain)
    if expected and not any(token in low for token in expected):
        return False

    if terms:
        term_overlap = any(_norm(term) and _norm(term) in low for term in terms)
        procedural = any(token in low for token in (
            "research question", "objective", "hypothesis", "problem statement", "reference list",
            "single case", "study setting", "unit of analysis", "study period", "same model", "original output",
            "regulatory", "institutional", "empirical evidence", "generalisation", "transferable",
        ))
        if not (term_overlap or procedural):
            return False
    return True


def _example_is_helpful(row: Dict[str, Any], example: str, terms: Sequence[str]) -> bool:
    if not _example_is_appropriate(row, example, terms):
        return False
    domain = _issue_domain(row)
    missing = _norm(_missing_label(row))
    if missing in {"purpose of the study", "research hypotheses", "definition of terms"}:
        return True
    if domain in {"statistics", "methods", "objective_alignment", "problem_statement", "scope", "limitations"}:
        return True
    if domain == "significance" and "contribution" in _core_finding_text(row):
        return True
    if domain == "background" and any(token in _core_finding_text(row) for token in (
        "theoretical", "conceptual", "framework", "synthesis", "progression", "literature"
    )):
        return True
    # Simple moving, formatting, citation and language instructions do not need
    # a forced example in a Word comment.
    return False



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
    include_example = _example_is_helpful(row, example, terms)
    domain = _issue_domain(row)
    if _norm(row.get("severity")) == "minor" and domain not in {"statistics", "language"}:
        include_example = False

    if _missing_label(row):
        parts: List[str] = []
        if issue:
            parts.append(_sentence_form(issue))
        elif assessment:
            parts.append(_sentence_form(assessment))
        if action:
            parts.append(_sentence_form(action))
        if include_example:
            clean_example = re.sub(r"^(?:for example|example)[:,]?\s*", "", example, flags=re.I).strip(" .")
            if clean_example:
                parts.append(_sentence_form("For example, " + clean_example[0].lower() + clean_example[1:]))
        if not parts and assessment:
            parts.append(_sentence_form(assessment))
        return _trim_words(_unique_sentences(parts, limit=4), max(_comment_word_limit(row), 145))

    parts: List[str] = []
    issue_key = _norm(issue)
    assessment_key = _norm(assessment)
    if issue and (not assessment or SequenceMatcher(None, issue_key, assessment_key).ratio() < 0.70):
        parts.append(_sentence_form(issue))
    if assessment:
        # Two diagnostic sentences are enough in a Word comment. The report can
        # retain the full explanation.
        parts.extend(_sentence_form(value) for value in _sentences(assessment)[:2])

    # When a concrete example is available for a complex issue, prioritise the
    # action and example over a generic consequence sentence. This keeps the
    # guidance visible instead of trimming it off at the end.
    example_priority_domains = {
        "problem_statement", "scope", "objective_alignment", "purpose",
        "definition_terms", "limitations", "statistics", "methods", "background",
    }
    if consequence and not (include_example and domain in example_priority_domains):
        if all(SequenceMatcher(None, _norm(consequence), _norm(part)).ratio() < 0.78 for part in parts):
            parts.append(_sentence_form(consequence))
    if action:
        parts.append(_sentence_form(action))
    if include_example:
        clean_example = re.sub(r"^(?:for example|example)[:,]?\s*", "", example, flags=re.I).strip(" .")
        if clean_example:
            parts.append(_sentence_form("For example, " + clean_example[0].lower() + clean_example[1:]))

    comment = _unique_sentences(parts, limit=5)
    limit = _comment_word_limit(row)
    if include_example and domain in example_priority_domains:
        limit = max(limit, 165)
    return _trim_words(comment, limit)


def _missing_section_human_example(
    row: Dict[str, Any],
    terms: Sequence[str],
    review: Dict[str, Any],
) -> str:
    label = _norm(_missing_label(row))
    if label == "purpose of the study":
        return _purpose_example(review, terms)
    if label == "research hypotheses":
        return _hypothesis_example(review, terms)
    if label == "definition of terms":
        return _definition_example(review, terms)
    if label == "limitations of the study":
        return _limitations_example(review, terms)
    if label == "delimitations of the study":
        return _scope_example(review, terms)
    return ""


def _contextualise_finding(
    row: Dict[str, Any],
    review: Dict[str, Any],
    terms: Sequence[str],
) -> Dict[str, Any]:
    output = dict(row)
    if not _env_enabled("VPROF_CONTEXTUAL_ALIGNMENT_EXAMPLES", True):
        return output
    domain = _issue_domain(output)
    core = _core_finding_text(output)

    if domain == "problem_statement" and any(token in core for token in (
        "evidence", "research gap", "unresolved", "magnitude", "scale", "full purpose", "does not yet perform",
    )):
        output["illustrative_guidance"] = _problem_example(review, terms)

    elif domain == "objective_alignment":
        example = _objective_alignment_example(review, terms)
        if example:
            output["illustrative_guidance"] = example

    elif domain == "scope":
        if any(token in core for token in ("incomplete", "underdeveloped", "unit of analysis", "study period", "exclusion", "does not yet perform")):
            output["illustrative_guidance"] = _scope_example(review, terms)
        elif "not used consistently" in core or "alternates between" in core:
            # The action already gives the concrete correction. Repeating it as
            # an example makes the comment sound formulaic.
            output["illustrative_guidance"] = ""

    elif domain == "significance":
        if "research gap" in core or "gap is placed" in core:
            output["illustrative_guidance"] = ""
        elif any(token in core for token in ("contribution", "knowledge", "practice", "policy", "scholarly")):
            output["illustrative_guidance"] = _significance_example(review, terms)

    elif domain == "limitations":
        if any(token in core for token in ("generalisation", "generalization", "single case", "transfer", "does not yet perform", "design", "sampling", "access")):
            output["illustrative_guidance"] = _limitations_example(review, terms)

    elif domain == "background" and any(token in core for token in (
        "theoretical anchor", "conceptual anchor", "theoretical or conceptual", "framework",
    )):
        constructs = _profile_constructs(review, terms)
        pairs = _relation_pairs(review)
        if pairs:
            relationship = f"{_natural_term(pairs[0][0])} and {_natural_term(pairs[0][1])}"
        else:
            relationship = _join_terms(constructs[:3]) or "the main constructs"
        output["item"] = output["issue_title"] = "The background needs a brief conceptual link"
        output["comment"] = output["assessment"] = (
            "The main concepts are introduced, but the expected connection among them is not stated clearly. "
            "Chapter One needs only a concise conceptual orientation; the detailed theoretical discussion belongs in Chapter Two."
        )
        output["academic_consequence"] = (
            "Without this link, the background describes the topic but does not show the logic leading to the study."
        )
        output["required_action"] = (
            "Add one short paragraph explaining the expected relationship among the main constructs and identify the framework that supports that expectation."
        )
        output["illustrative_guidance"] = (
            f"briefly explain how the selected framework links {relationship}, then reserve the full theory review and critical synthesis for Chapter Two"
        )

    return output


def edit_findings_for_human_review(
    rows: Sequence[Dict[str, Any]],
    review: Dict[str, Any],
    terms: Sequence[str],
) -> List[Dict[str, Any]]:
    """Apply the final human-supervisor editorial, semantic and judgement pass.

    The pass does not create a target number of comments. It consolidates root
    causes, adds conservative study-specific checks, removes cross-chapter
    contamination, validates examples and prepares one natural comment per
    retained issue.
    """
    output = add_human_judgement_findings(rows, review, terms)
    output = consolidate_root_causes(output, terms)
    if not _env_enabled("VPROF_HUMAN_SUPERVISORY_EDITOR", True):
        return output

    edited: List[Dict[str, Any]] = []
    for row in output:
        current = dict(row)
        for field in ("item", "issue_title", "comment", "assessment", "academic_consequence", "required_action", "illustrative_guidance"):
            current[field] = _grammar_polish(current.get(field))

        current = _scrub_cross_domain_contamination(current)
        current = _contextualise_finding(current, review, terms)

        missing_example = _missing_section_human_example(current, terms, review)
        if missing_example:
            current["illustrative_guidance"] = missing_example

        # Never export an excerpt that ends in the middle of a word. Exact
        # sentence anchors are preferred, but a word-safe excerpt remains useful
        # when the original sentence is long.
        if _clean(current.get("problematic_quote")):
            current["problematic_quote"] = _safe_excerpt(current.get("problematic_quote"))
        elif current.get("evidence"):
            current["problematic_quote"] = _safe_excerpt((current.get("evidence") or [{}])[0].get("text"))

        example = _clean(current.get("illustrative_guidance"))
        if not _example_is_helpful(current, example, terms):
            current["illustrative_guidance"] = ""

        current["student_comment"] = _compose_human_comment(current, terms)
        current["human_edited"] = True
        current["semantic_example_validated"] = bool(current.get("illustrative_guidance"))
        current["human_example_included"] = bool(current.get("illustrative_guidance"))
        if current["student_comment"]:
            edited.append(current)
    return edited

