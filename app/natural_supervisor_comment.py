from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Mapping

from .document_parser import clean_text, normalised

_LABEL_RE = re.compile(
    r"(?:^|(?<=[.!?])\s+|\s+)"
    r"(?:Issue|Problem identified|Action required|Required correction|Required revision|"
    r"Why this matters|Academic consequence|Academic implication|Verification|"
    r"How to verify completion|Illustrative guidance|Guidance|Example)\s*:\s*",
    flags=re.I,
)

_GENERIC_VERIFICATION = (
    "confirm that the revised sentence or paragraph now performs the stated academic function "
    "and remains aligned with the relevant objective method and evidence"
)

_GENERIC_ACTIONS = (
    "revise the marked passage to address the identified academic weakness",
    "state the missing information directly in the relevant section",
    "using the actual design evidence and terminology of the study",
)


def _clean(value: Any) -> str:
    text = clean_text(str(value or ""))
    text = _LABEL_RE.sub(" ", text)
    return re.sub(r"\s{2,}", " ", text).strip(" .;:")


def _norm(value: Any) -> str:
    return normalised(_clean(value))


def _sentence(value: Any) -> str:
    text = _clean(value)
    if not text:
        return ""
    text = text[0].upper() + text[1:]
    return text if text.endswith((".", "?", "!")) else text + "."


def _direct_action(value: Any) -> str:
    text = _clean(value)
    if not text or any(phrase in _norm(text) for phrase in _GENERIC_ACTIONS):
        return ""
    text = re.sub(r"^(?:the student should|you should|please)\s+", "", text, flags=re.I)
    text = re.sub(r"^revise(?: the)?(?: marked)? passage by\s+", "", text, flags=re.I)
    text = re.sub(r"^by\s+", "", text, flags=re.I)
    gerunds = {
        "adding": "Add", "aligning": "Align", "applying": "Apply", "checking": "Check",
        "clarifying": "Clarify", "correcting": "Correct", "defining": "Define",
        "developing": "Develop", "ensuring": "Ensure", "explaining": "Explain",
        "identifying": "Identify", "inserting": "Insert", "linking": "Link",
        "providing": "Provide", "removing": "Remove", "reorganising": "Reorganise",
        "reorganizing": "Reorganise", "replacing": "Replace", "reporting": "Report",
        "rewriting": "Rewrite", "stating": "State", "using": "Use", "verifying": "Verify",
    }
    first, *rest = text.split(maxsplit=1)
    if first.lower() in gerunds:
        text = gerunds[first.lower()] + ((" " + rest[0]) if rest else "")
    else:
        text = text[0].upper() + text[1:]
    return text if text.endswith((".", "?", "!")) else text + "."


def _is_generic_verification(value: str) -> bool:
    low = _norm(value)
    return not low or SequenceMatcher(None, low, _GENERIC_VERIFICATION).ratio() >= 0.74


def _unique_sentences(values: Iterable[str], limit: int = 7) -> List[str]:
    output: List[str] = []
    keys: List[str] = []
    for value in values:
        sentence = _sentence(value)
        key = _norm(sentence)
        if not sentence or not key:
            continue
        if any(key == old or SequenceMatcher(None, key, old).ratio() >= 0.86 for old in keys):
            continue
        keys.append(key)
        output.append(sentence)
        if len(output) >= limit:
            break
    return output


def natural_supervisor_comment(
    row: Mapping[str, Any],
    *,
    compact: bool = False,
    include_reason: bool = True,
    include_verification: bool = False,
    include_example: bool = False,
) -> str:
    """Render one finding as natural supervisory prose without field labels.

    The canonical finding record remains structured internally. Only the student-
    facing rendering is flattened into fluent prose. This prevents Word comments
    from reading like database fields while preserving the corrective action.
    """
    issue = _clean(row.get("item") or row.get("issue_title"))
    assessment = _clean(row.get("assessment") or row.get("comment"))
    action = _direct_action(row.get("required_action"))
    reason = _clean(row.get("academic_consequence") or row.get("why_it_matters"))
    verification = _clean(row.get("verification_test") or row.get("verification"))
    example = _clean(row.get("illustrative_guidance"))

    opening = assessment or issue
    if issue and assessment and SequenceMatcher(None, _norm(issue), _norm(assessment)).ratio() < 0.70:
        opening = f"{issue.rstrip(' .')}. {assessment}"

    sentences: List[str] = []
    sentences.extend(_unique_sentences([opening], limit=2))
    if action:
        sentences.extend(_unique_sentences([action], limit=1))

    if not compact and include_reason and reason:
        # Consequences often arrive as complete sentences. Keep them direct rather
        # than adding another visible label such as "Why this matters".
        sentences.extend(_unique_sentences([reason], limit=1))

    if not compact and include_verification and verification and not _is_generic_verification(verification):
        verification = re.sub(r"^(?:verify|confirm|check)\s+", "", verification, flags=re.I)
        verification = re.sub(r"^that\s+", "", verification, flags=re.I)
        if re.match(r"^(?:add|align|apply|check|clarify|correct|define|explain|identify|insert|link|provide|remove|report|revise|rewrite|state|use|verify)\b", verification, flags=re.I):
            verification_sentence = "Confirm completion by checking that the revision follows this instruction: " + verification
        else:
            verification_sentence = "Confirm that " + verification
        sentences.extend(_unique_sentences([verification_sentence], limit=1))

    if not compact and include_example and example:
        example = re.sub(r"^for example[:,]?\s*", "", example, flags=re.I)
        if example:
            sentences.extend(_unique_sentences(["For example, " + example], limit=1))

    return " ".join(_unique_sentences(sentences, limit=4))


def natural_group_item(value: Any) -> str:
    """Normalise legacy labelled comments before exact-anchor grouping."""
    text = _clean(value)
    text = re.sub(r"^Supervisor comments?\s*:\s*", "", text, flags=re.I)
    return _sentence(text)
