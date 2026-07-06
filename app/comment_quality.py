from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .document_parser import clean_text, normalised

_INTERNAL_NOTICE_RE = re.compile(
    r"(?:\s*\[?Manual confirmation recommended because the independent audit request was unavailable;?"
    r"[^\]]*?(?:checks|confirmation)\.?\]?)|"
    r"(?:\s*(?:One or more|An?)\s+independent\s+(?:accuracy[- ]?)?audit(?:\s+batches?)?\s+"
    r"(?:was|were)\s+unavailable[^.!?]*(?:[.!?]|$))|"
    r"(?:\s*The displayed comments[^.!?]*manual confirmation[^.!?]*(?:[.!?]|$))|"
    r"(?:\s*A separate model response for this section remained unavailable[^.!?]*(?:[.!?]|$))|"
    r"(?:\s*The section '[^']+' is present, but its separate expert review could not be completed after focused recovery[^.!?]*(?:[.!?]|$))|"
    r"(?:\s*It has therefore not been treated as absent and no unverified finding has been added[^.!?]*(?:[.!?]|$))|"
    r"(?:\s*The section is present and remains represented in the document map and cross-chapter checks[^.!?]*(?:[.!?]|$))|"
    r"(?:\s*No unsupported criticism has been inserted[^.!?]*(?:[.!?]|$))|"
    r"(?:\s*Manual confirmation of this section is recommended[^.!?]*(?:[.!?]|$))|"
    r"(?:\s*Recovery detail:[^.!?]*(?:[.!?]|$))|"
    r"(?:\bDocument-level review note\.\s*)",
    flags=re.I,
)

_PLACEHOLDER_RE = re.compile(
    r"\[(?:"
    r"verified\s+(?:scholarly\s+)?source|verified\s+statistic|verified\s+information|"
    r"study\s+(?:country|setting|sector|context)|target\s+population|"
    r"insert\b[^\]]*|add\b[^\]]*|specify\b[^\]]*|provide\b[^\]]*|"
    r"x(?:\s*%|\b)[^\]]*|month/year|start\s+month/year|end\s+month/year"
    r")\]",
    flags=re.I,
)

_GENERIC_BRACKET_PLACEHOLDER_RE = re.compile(
    r"\[[^\]]{1,100}\]",
    flags=re.I,
)



_DANGLING_END_RE = re.compile(
    r"(?:\b(?:and|or|of|to|for|with|among|between|while|including|such as|the|a|an|this|that|these|those|its|their|on|at|by|from)"
    r"|\b(?:assessing|examining|including|manufacturing|Ghanaian|write|describe|explain|state|show|demonstrate|provide))\s*[.!?]?$",
    flags=re.I,
)


def incomplete_public_fragment(value: Any) -> bool:
    """Return True when generated guidance visibly ends mid-thought.

    This is deliberately conservative. It targets unmatched quotation marks,
    dangling connectors/determiners and unfinished list introductions that were
    observed in native Word comments after provider truncation.
    """
    text = clean_text(value)
    if not text:
        return False
    # Treat straight apostrophes as quotation marks only when they visibly
    # open a quoted example. Ordinary possessives such as "programme's" are
    # not incomplete fragments.
    if (text.startswith("'") or re.search(r":\s*'", text)) and text.count("'") % 2:
        return True
    if text.count('"') % 2 or text.count("“") != text.count("”") or text.count("‘") != text.count("’"):
        return True
    if text.count("(") != text.count(")") or text.count("[") != text.count("]"):
        return True
    if re.search(r"(?:for example|such as|including|as follows)\s*[:,-]?\s*$", text, flags=re.I):
        return True
    if _DANGLING_END_RE.search(text):
        return True
    return False


_STOP_WORDS = {
    "about", "after", "again", "against", "also", "among", "and", "are", "because",
    "been", "before", "being", "between", "both", "but", "can", "could", "does", "each",
    "either", "ensure", "for", "from", "have", "into", "its", "may", "more", "must",
    "not", "only", "other", "should", "that", "the", "their", "there", "these", "this",
    "those", "through", "under", "use", "using", "where", "which", "while", "with", "within",
    "would", "your", "section", "study", "student", "revise", "revision", "required", "action",
    "example", "comment", "statement", "research",
}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return min(maximum, max(minimum, value))


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return min(maximum, max(minimum, value))


def comment_max_chars() -> int:
    # Developmental Word comments need enough room to explain the issue, why it matters and the required correction.
    return _env_int("VPROF_COMMENT_MAX_CHARS", 980, 420, 1600)


def similarity_threshold() -> float:
    return _env_float("VPROF_COMMENT_SIMILARITY_THRESHOLD", 0.62, 0.45, 0.90)


def reject_placeholder_comments() -> bool:
    return _env_bool("VPROF_REJECT_PLACEHOLDER_COMMENTS", True)


def suppress_internal_notices() -> bool:
    return _env_bool("VPROF_SUPPRESS_INTERNAL_AUDIT_NOTICES", True)


def contains_placeholder(value: Any) -> bool:
    text = clean_text(value)
    if not text:
        return False
    if _PLACEHOLDER_RE.search(text):
        return True
    # Generated comments should not expose unresolved square-bracket prompts.
    return bool(_GENERIC_BRACKET_PLACEHOLDER_RE.search(text))


def strip_internal_notices(value: Any) -> str:
    text = clean_text(value)
    if suppress_internal_notices():
        text = _INTERNAL_NOTICE_RE.sub("", text)
    return re.sub(r"\s{2,}", " ", text).strip(" ,;:")


def sentence_safe_trim(value: Any, limit: Optional[int] = None) -> str:
    text = strip_internal_notices(value)
    if not text:
        return ""
    if limit is None or len(text) <= limit:
        return text

    window = text[: limit + 1]
    sentence_ends = [m.end() for m in re.finditer(r"[.!?](?=\s|$)", window)]
    viable = [end for end in sentence_ends if end >= int(limit * 0.52)]
    if viable:
        return window[: viable[-1]].strip()

    clause_ends = [m.start() for m in re.finditer(r"[;:](?=\s|$)", window)]
    viable_clause = [end for end in clause_ends if end >= int(limit * 0.62)]
    if viable_clause:
        return window[: viable_clause[-1]].rstrip(" ,;:") + "."

    # Do not release a visibly cut fragment. Keep the first complete sentence
    # when it exists, otherwise return an empty value so the caller can omit it.
    first = re.match(r"^(.+?[.!?])(?:\s|$)", text)
    if first and len(first.group(1)) <= limit:
        return first.group(1).strip()
    return ""


def public_text(
    value: Any,
    *,
    limit: Optional[int] = None,
    reject_placeholders: bool = True,
    reject_incomplete: bool = False,
) -> str:
    text = strip_internal_notices(value)
    if reject_placeholders and reject_placeholder_comments() and contains_placeholder(text):
        return ""
    text = re.sub(r"\bExample\s*:\s*Example\s*:\s*", "Example: ", text, flags=re.I)
    text = re.sub(r"\s{2,}", " ", text).strip()
    if reject_incomplete and incomplete_public_fragment(text):
        return ""
    output = sentence_safe_trim(text, limit)
    if reject_incomplete and incomplete_public_fragment(output):
        return ""
    return output


def _conditionalise_hypothesis_advice(value: str) -> str:
    text = clean_text(value)
    low = normalised(text)
    if "hypoth" not in low:
        return text
    if any(marker in low for marker in ("where required", "if required", "where the programme", "if the programme")):
        return text
    if re.search(r"\b(?:develop|formulate|state|add|include)\b.{0,45}\bhypoth", text, flags=re.I):
        text = re.sub(
            r"^(?:Develop|Formulate|State|Add|Include)\b",
            "Where required by the programme's thesis format and supported by the research design, formulate",
            text,
            count=1,
            flags=re.I,
        )
    return text


def _future_date_only_issue(issue: Dict[str, Any], current_year: int) -> bool:
    combined = " ".join(
        clean_text(issue.get(field, ""))
        for field in ("issue_title", "assessment", "academic_consequence", "required_action", "illustrative_guidance")
    )
    if not re.search(r"future[- ]dated", combined, flags=re.I):
        return False
    years = [int(value) for value in re.findall(r"\b(?:19|20)\d{2}\b", combined)]
    for evidence in issue.get("evidence") or []:
        years.extend(int(value) for value in re.findall(r"\b(?:19|20)\d{2}\b", clean_text(evidence.get("text", ""))))
    return not any(year > current_year for year in years)


def _fallback_action(category: str) -> str:
    category = str(category or "other")
    if category in {"citations_and_sources", "ethics_and_integrity"}:
        return "Verify the relevant claim against an authentic source and provide complete, accurate bibliographic details for every retained citation."
    if category in {"academic_writing", "presentation"}:
        return "Rewrite the marked passage in clear formal British English and correct the recurring grammar, punctuation and sentence-structure problems."
    if category in {"cross_section_coherence", "objectives_questions_hypotheses"}:
        return "Revise the affected sections together so the problem, purpose, objectives, research questions and stated study scope are fully aligned."
    return "Revise the marked passage to address the identified academic weakness using only verified information from the study and authentic sources."


def finalise_public_issue(issue: Dict[str, Any], *, current_year: Optional[int] = None) -> Optional[Dict[str, Any]]:
    output = dict(issue)
    current_year = current_year or datetime.now(timezone.utc).year
    if _future_date_only_issue(output, current_year):
        return None

    for field in ("section", "issue_title", "assessment", "academic_consequence", "required_action", "illustrative_guidance"):
        raw = strip_internal_notices(output.get(field, ""))
        if field in {"required_action", "illustrative_guidance"}:
            raw = _conditionalise_hypothesis_advice(raw)
        if contains_placeholder(raw):
            if field == "required_action":
                raw = _fallback_action(str(output.get("category") or "other"))
            elif field == "illustrative_guidance":
                raw = ""
            elif field in {"assessment", "academic_consequence"}:
                raw = re.sub(_GENERIC_BRACKET_PLACEHOLDER_RE, "verified information", raw)
            else:
                return None
        output[field] = public_text(
            raw,
            reject_placeholders=True,
            reject_incomplete=field in {"required_action", "illustrative_guidance"},
        )

    if not output.get("issue_title"):
        return None
    if not output.get("required_action"):
        output["required_action"] = _fallback_action(str(output.get("category") or "other"))
    if not output.get("assessment"):
        output["assessment"] = "The marked passage requires revision because it does not yet meet the expected academic standard."

    output["manual_confirmation_required"] = bool(output.get("manual_confirmation_required"))
    return output


def _topic_tokens(issue: Dict[str, Any]) -> set[str]:
    text = " ".join(
        clean_text(issue.get(field, ""))
        for field in ("issue_title", "assessment", "required_action")
    )
    return {
        token for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) >= 4 and token not in _STOP_WORDS and not token.isdigit()
    }


def _similarity(left: Dict[str, Any], right: Dict[str, Any]) -> float:
    left_tokens = _topic_tokens(left)
    right_tokens = _topic_tokens(right)
    jaccard = (
        len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
        if left_tokens and right_tokens else 0.0
    )
    left_text = normalised(" ".join([left.get("issue_title", ""), left.get("required_action", "")]))
    right_text = normalised(" ".join([right.get("issue_title", ""), right.get("required_action", "")]))
    sequence = SequenceMatcher(None, left_text, right_text).ratio() if left_text and right_text else 0.0

    shared = left_tokens & right_tokens
    intent_bonus = 0.0
    duplicate_intents = (
        {"hypotheses", "objectives"},
        {"purpose", "operational", "performance"},
        {"environmental", "sustainability", "performance"},
        {"citation", "source", "verify"},
    )
    if any(len(shared & intent) >= 2 for intent in duplicate_intents):
        intent_bonus = 0.08
    return min(1.0, max(jaccard, sequence) + intent_bonus)


def _merge_issue(primary: Dict[str, Any], duplicate: Dict[str, Any]) -> Dict[str, Any]:
    output = dict(primary)
    evidence_ids = list(output.get("evidence_paragraph_ids") or [])
    evidence_ids.extend(duplicate.get("evidence_paragraph_ids") or [])
    output["evidence_paragraph_ids"] = list(dict.fromkeys(evidence_ids))[:8]

    # Keep the more complete but still concise public wording.
    for field in ("assessment", "academic_consequence", "required_action", "illustrative_guidance"):
        left = clean_text(output.get(field, ""))
        right = clean_text(duplicate.get(field, ""))
        if len(right) > len(left) and not contains_placeholder(right):
            output[field] = right
    output["confidence"] = max(float(output.get("confidence") or 0.0), float(duplicate.get("confidence") or 0.0))
    output["manual_confirmation_required"] = bool(
        output.get("manual_confirmation_required") or duplicate.get("manual_confirmation_required")
    )
    return output


def deduplicate_public_issues(issues: Sequence[Dict[str, Any]], *, threshold: Optional[float] = None) -> List[Dict[str, Any]]:
    threshold = similarity_threshold() if threshold is None else threshold
    severity_rank = {"critical": 0, "major": 1, "moderate": 2, "minor": 3}
    ordered = sorted(
        (dict(issue) for issue in issues),
        key=lambda row: (severity_rank.get(str(row.get("severity") or "minor"), 9), -float(row.get("confidence") or 0.0)),
    )
    kept: List[Dict[str, Any]] = []
    for issue in ordered:
        merged = False
        for index, existing in enumerate(kept):
            same_category = str(issue.get("category") or "") == str(existing.get("category") or "")
            flexible_category = {
                str(issue.get("category") or ""), str(existing.get("category") or "")
            } <= {"cross_section_coherence", "objectives_questions_hypotheses", "conceptual_clarity", "other"}
            if not (same_category or flexible_category):
                continue
            if _similarity(issue, existing) >= threshold:
                kept[index] = _merge_issue(existing, issue)
                merged = True
                break
        if not merged:
            kept.append(issue)
    return kept


def prepare_public_issues(issues: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    cleaned: List[Dict[str, Any]] = []
    dropped = 0
    adjusted = 0
    for issue in issues:
        before = repr(issue)
        final = finalise_public_issue(issue)
        if final is None:
            dropped += 1
            continue
        if repr(final) != before:
            adjusted += 1
        cleaned.append(final)
    deduplicated = deduplicate_public_issues(cleaned)
    return deduplicated, {
        "input": len(issues),
        "kept": len(deduplicated),
        "dropped": dropped + max(0, len(cleaned) - len(deduplicated)),
        "adjusted": adjusted,
    }


def sanitise_finding_row(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    output = dict(row)
    for field in ("item", "comment", "required_action", "illustrative_guidance", "reference_label", "section_reference", "section"):
        value = output.get(field, "")
        if field == "required_action":
            value = _conditionalise_hypothesis_advice(clean_text(value))
        cleaned = public_text(
            value,
            reject_placeholders=True,
            reject_incomplete=field in {"required_action", "illustrative_guidance"},
        )
        if field == "illustrative_guidance" and not cleaned:
            output[field] = ""
        elif field == "required_action" and not cleaned:
            output[field] = _fallback_action(str(output.get("category") or "other"))
        else:
            output[field] = cleaned
    if not output.get("item"):
        output["item"] = public_text(
            output.get("comment")
            or output.get("section_reference")
            or output.get("section")
            or "Academic revision required",
            limit=180,
            reject_placeholders=True,
        ) or "Academic revision required"
    if not output.get("required_action"):
        return None
    return output


def _finding_row_projection(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "category": row.get("category") or "other",
        "issue_title": row.get("item") or row.get("issue_title") or "",
        "assessment": row.get("comment") or row.get("assessment") or "",
        "required_action": row.get("required_action") or "",
        "confidence": row.get("confidence") or 0.0,
        "severity": row.get("severity") or "minor",
    }


def sanitise_finding_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    for row in rows:
        cleaned = sanitise_finding_row(row)
        if cleaned is None:
            continue
        duplicate_index: Optional[int] = None
        candidate = _finding_row_projection(cleaned)
        for index, existing in enumerate(output):
            same_category = str(cleaned.get("category") or "") == str(existing.get("category") or "")
            flexible_category = {
                str(cleaned.get("category") or ""), str(existing.get("category") or "")
            } <= {"cross_section_coherence", "objectives_questions_hypotheses", "conceptual_clarity", "other"}
            if not (same_category or flexible_category):
                continue

            cleaned_evidence = {
                str(item.get("paragraph") or item.get("paragraph_id") or "")
                for item in cleaned.get("evidence") or []
                if str(item.get("paragraph") or item.get("paragraph_id") or "")
            }
            existing_evidence = {
                str(item.get("paragraph") or item.get("paragraph_id") or "")
                for item in existing.get("evidence") or []
                if str(item.get("paragraph") or item.get("paragraph_id") or "")
            }
            cleaned_quote = normalised(cleaned.get("problematic_quote", ""))
            existing_quote = normalised(existing.get("problematic_quote", ""))
            same_anchor = bool(cleaned_evidence & existing_evidence) or (
                bool(cleaned_quote) and cleaned_quote == existing_quote
            )
            if not same_anchor:
                continue
            if _similarity(candidate, _finding_row_projection(existing)) >= similarity_threshold():
                duplicate_index = index
                break
        if duplicate_index is None:
            output.append(cleaned)
            continue
        existing = output[duplicate_index]
        if _severity_rank_value(cleaned.get("severity")) < _severity_rank_value(existing.get("severity")):
            output[duplicate_index] = cleaned
        elif len(clean_text(cleaned.get("required_action", ""))) > len(clean_text(existing.get("required_action", ""))):
            output[duplicate_index] = cleaned
    return output


def _severity_rank_value(value: Any) -> int:
    return {"critical": 0, "major": 1, "moderate": 2, "minor": 3}.get(str(value or "minor").lower(), 9)
