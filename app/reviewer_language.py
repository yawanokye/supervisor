from __future__ import annotations

import re
from typing import Any, Mapping


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def academic_level_label(value: Any) -> str:
    """Return a natural public-facing academic-level label.

    The reviewer should speak directly about the actual standard, for example
    ``At PhD level`` or ``At MPhil level``, rather than referring to a selected
    or declared level.
    """
    if isinstance(value, Mapping):
        value = value.get("academic_level") or value.get("degree_level") or value.get("level")
    text = _clean(value)
    low = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    if "phd" in low or "doctor of philosophy" in low:
        return "PhD level"
    if any(term in low for term in ("professional doctorate", "dba", "ded", "doctor of education")):
        return "professional doctorate level"
    if any(term in low for term in ("mphil", "research masters", "research master")):
        return "MPhil level"
    if any(term in low for term in ("non research masters", "non research master", "coursework masters", "coursework master")):
        return "non-research Master's level"
    if any(term in low for term in ("masters", "master")):
        return "Master's level"
    if any(term in low for term in ("bachelor", "undergraduate")):
        return "Bachelor's level"
    return f"{text} level" if text else "the applicable academic level"


def at_level_phrase(value: Any) -> str:
    label = academic_level_label(value)
    return f"At {label}" if label != "the applicable academic level" else "At the applicable academic level"


_REPLACEMENTS = (
    (r"\bthe uploaded documents\b", "the submitted work"),
    (r"\bthe uploaded document\b", "the study"),
    (r"\bthis uploaded document\b", "this work"),
    (r"\buploaded documents\b", "submitted work"),
    (r"\buploaded document\b", "study"),
)


def professionalise_reviewer_language(value: Any, academic_level: Any = None) -> str:
    """Remove app-facing language from student-facing review text."""
    text = _clean(value)
    if not text:
        return ""
    for pattern, replacement in _REPLACEMENTS:
        text = re.sub(pattern, replacement, text, flags=re.I)

    level = academic_level_label(academic_level)
    replacements = (
        r"the selected academic benchmark",
        r"selected academic benchmark",
        r"the selected benchmark",
        r"selected benchmark",
        r"the selected academic level",
        r"selected academic level",
        r"the selected level",
        r"selected level",
        r"the declared programme level",
        r"the declared degree standard",
        r"the declared level",
        r"the stated benchmark",
    )
    for pattern in replacements:
        if level != "the applicable academic level":
            text = re.sub(pattern, level, text, flags=re.I)
        else:
            text = re.sub(pattern, "the applicable academic level", text, flags=re.I)

    # Repair only awkward "against [level]" constructions. Preserve a
    # sentence-opening "At PhD level" or "At MPhil level" exactly as written.
    text = re.sub(
        r"\bagainst\s+(PhD level|MPhil level|professional doctorate level|Master's level|non-research Master's level|Bachelor's level)\b",
        r"at \1",
        text,
        flags=re.I,
    )
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


def ensure_level_expectation(value: Any, academic_level: Any, expectation: str = "") -> str:
    """Add one natural level-specific expectation when the text lacks one."""
    text = professionalise_reviewer_language(value, academic_level)
    if not text:
        return ""
    label = academic_level_label(academic_level)
    explicit_level_sentence = re.search(
        r"(?:^|[.!?]\s+)At\s+(?:PhD|MPhil|professional doctorate|Master's|non-research Master's|Bachelor's)\s+level\b",
        text,
    )
    if label == "the applicable academic level" or explicit_level_sentence:
        return text
    expectation = professionalise_reviewer_language(expectation, academic_level).strip(" .")
    if not expectation:
        expectation = "the argument, method and evidence should demonstrate the depth, precision and independent scholarly judgement expected"
    return f"{text} At {label}, {expectation}."
