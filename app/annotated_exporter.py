from __future__ import annotations

import io
import os
import re
from collections import defaultdict
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from docx.text.run import Run
from docx.table import Table

from .document_parser import clean_text, normalised
from .comment_quality import (
    comment_max_chars,
    public_text,
    sanitise_finding_row,
    sanitise_finding_rows,
    sentence_safe_trim,
)
from .review_rules import STATUS_MANUAL, STATUS_MISSING, STATUS_PARTIAL
from .review_enrichment import context_specific_example

ANNOTATION_EXPORT_VERSION = "1.9.9.10-one-finding-one-comment"
ACTIONABLE_STATUSES = {STATUS_PARTIAL, STATUS_MISSING, STATUS_MANUAL}
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

# Unresolved drafting placeholders inside the student's own document must always
# receive a native comment, even if the AI reviewer or the independent audit
# misses them. This is deliberately handled at export time because the exporter
# has access to the final Word paragraph/run map and can anchor the comment
# exactly on the placeholder text.
_BODY_PLACEHOLDER_RE = re.compile(
    r"\[(?:\s*(?:insert|add|specify|provide|complete|fill\s+in|replace|enter|start|end|month|year|date|x\b)[^\]\r\n]{0,120})\]",
    flags=re.I,
)

_NATURAL_LABEL_RE = re.compile(
    r"\b(?:Issue|Why this matters|Revise by|Guidance|Academic implication|Academic consequence)\s*:\s*",
    flags=re.I,
)


def _strip_visible_labels(value: str) -> str:
    return re.sub(r"\s{2,}", " ", _NATURAL_LABEL_RE.sub("", clean_text(value))).strip()




def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _export_one_comment_per_finding() -> bool:
    return _env_bool("VPROF_EXPORT_ONE_COMMENT_PER_FINDING", True)


def _split_related_concerns() -> bool:
    return _env_bool("VPROF_SPLIT_RELATED_CONCERNS_INTO_SEPARATE_COMMENTS", True)


def _prepare_comment_list(comments: Iterable[str]) -> List[str]:
    unique: List[str] = []
    seen = set()
    for value in comments:
        text = _strip_visible_labels(
            public_text(value, limit=comment_max_chars(), reject_placeholders=True, reject_incomplete=True)
        ).strip("[] ").rstrip(" ;.")
        text = re.sub(r"^Supervisor comments?\s*:\s*", "", text, flags=re.I)
        if not text:
            continue
        if _split_related_concerns() and " A related concern is that " in text:
            first, second = text.split(" A related concern is that ", 1)
            candidates = [first, second[:1].upper() + second[1:]]
        else:
            candidates = [text]
        for candidate in candidates:
            candidate = clean_text(candidate).strip(" ;.")
            key = normalised(candidate)
            if not candidate or key in seen:
                continue
            seen.add(key)
            unique.append(_shorten_comment(candidate, comment_max_chars()).rstrip(" .") + ".")
    return unique




def _sanitise_rows_for_export(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not _export_one_comment_per_finding():
        return sanitise_finding_rows(rows)
    output: List[Dict[str, Any]] = []
    seen_exact = set()
    for row in rows:
        cleaned = sanitise_finding_row(row)
        if cleaned is None:
            continue
        exact_key = (
            normalised(cleaned.get("section", "")),
            normalised(cleaned.get("item", "")),
            normalised(cleaned.get("comment", "")),
            normalised(cleaned.get("required_action", "")),
            tuple(
                str(item.get("paragraph") or item.get("paragraph_id") or "")
                for item in cleaned.get("evidence") or []
            ),
        )
        if exact_key in seen_exact:
            continue
        seen_exact.add(exact_key)
        output.append(cleaned)
    return output


def expected_native_comment_count(review: Dict[str, Any]) -> int:
    rows = _sanitise_rows_for_export(
        list(review.get("academic_findings", []))
        + list(review.get("alignment_results", []))
        + list(review.get("revision_results", []))
    )
    actionable = [
        row for row in rows
        if row.get("status") in ACTIONABLE_STATUSES and row.get("annotation_eligible") is not False
    ]
    return len(actionable)


def _set_run_colour(run_element, colour: str) -> None:
    rpr = run_element.find(qn("w:rPr"))
    if rpr is None:
        rpr = OxmlElement("w:rPr")
        run_element.insert(0, rpr)
    colour_node = rpr.find(qn("w:color"))
    if colour_node is None:
        colour_node = OxmlElement("w:color")
        rpr.append(colour_node)
    colour_node.set(qn("w:val"), colour)


def _set_italic(run_element) -> None:
    rpr = run_element.find(qn("w:rPr"))
    if rpr is None:
        rpr = OxmlElement("w:rPr")
        run_element.insert(0, rpr)
    if rpr.find(qn("w:i")) is None:
        rpr.append(OxmlElement("w:i"))


def _run_element(text: str, source_run=None, colour: Optional[str] = None, italic: bool = False):
    element = OxmlElement("w:r")
    if source_run is not None and source_run._r.rPr is not None:
        element.append(deepcopy(source_run._r.rPr))
    if colour:
        _set_run_colour(element, colour)
    if italic:
        _set_italic(element)
    node = OxmlElement("w:t")
    if text.startswith(" ") or text.endswith(" ") or "  " in text:
        node.set(XML_SPACE, "preserve")
    node.text = text
    element.append(node)
    return element


def _sentence_spans(text: str) -> List[Tuple[int, int, str]]:
    spans: List[Tuple[int, int, str]] = []
    for match in re.finditer(r"[^.!?\n]+(?:[.!?]+|$)", text or ""):
        start, end = match.span()
        if match.group(0).strip():
            spans.append((start, end, match.group(0)))
    if not spans and text:
        spans.append((0, len(text), text))
    return spans


def _best_span(text: str, matched_terms: Iterable[str], problematic_quote: str = "") -> Tuple[int, int]:
    quote = clean_text(problematic_quote)
    if quote:
        exact_start = text.find(quote)
        if exact_start >= 0:
            return exact_start, exact_start + len(quote)
        normalised_quote = normalised(quote)
        for start, end, sentence in _sentence_spans(text):
            if normalised_quote and normalised_quote in normalised(sentence):
                return start, end
    terms = [normalised(term) for term in matched_terms if normalised(term)]
    spans = _sentence_spans(text)
    if not spans:
        return (0, len(text or ""))
    ranked = []
    for start, end, sentence in spans:
        low = normalised(sentence)
        hits = sum(1 for term in terms if term in low)
        ranked.append((hits, len(sentence.strip()), start, end))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    _, _, start, end = ranked[0]
    return start, end


def _sanitise_guidance(value: str) -> str:
    text = _strip_visible_labels(value)
    patterns = [
        r"^(?:retain|keep) this finding and\s+",
        r"^require (?:the student to )?",
        r"^ask the student to\s+",
        r"^the student should\s+",
    ]
    for pattern in patterns:
        text = re.sub(pattern, "", text, flags=re.I)
    text = re.sub(r"^retain this point and\s+", "", text, flags=re.I)
    if text:
        text = text[0].upper() + text[1:]
    return text.rstrip()



def _normalise_action_start(text: str) -> str:
    """Return a natural supervisor instruction without template residue."""
    value = clean_text(text).rstrip(" .")
    if not value:
        return ""
    # Common model phrasing such as "by use" or "by undertake" must not
    # reach native Word comments. Convert it to direct supervision.
    value = re.sub(r"^revise(?: the)?(?: marked)? passage by\s+", "", value, flags=re.I)
    value = re.sub(r"^by\s+", "", value, flags=re.I)
    gerund_map = {
        "using": "use", "undertaking": "undertake", "applying": "apply",
        "providing": "provide", "linking": "link", "situating": "situate",
        "differentiating": "differentiate", "checking": "check", "clarifying": "clarify",
        "replacing": "replace", "rewriting": "rewrite", "aligning": "align",
        "expanding": "expand", "stating": "state", "defining": "define",
        "supporting": "support", "removing": "remove", "correcting": "correct",
        "ensuring": "ensure", "explaining": "explain", "adding": "add",
        "verifying": "verify", "inserting": "insert", "avoiding": "avoid",
        "developing": "develop", "formulating": "formulate", "showing": "show",
        "demonstrating": "demonstrate", "indicating": "indicate",
    }
    parts = value.split(maxsplit=1)
    if parts and parts[0].lower() in gerund_map:
        value = gerund_map[parts[0].lower()] + ((" " + parts[1]) if len(parts) > 1 else "")
    return value[0].upper() + value[1:] if value else value


def _shorten_comment(value: str, limit: Optional[int] = None) -> str:
    effective_limit = limit if limit is not None else comment_max_chars()
    return sentence_safe_trim(value, effective_limit)

def _comment_body(row: Dict[str, Any]) -> str:
    safe_row = sanitise_finding_row(row)
    if safe_row is None:
        return ""
    row = safe_row

    reference = clean_text(
        row.get("reference_label")
        or row.get("section_reference")
        or row.get("section")
    )
    if not row.get("table_reference"):
        table_evidence = next(
            (item for item in row.get("evidence") or [] if item.get("table_number")),
            None,
        )
        if table_evidence:
            number = clean_text(table_evidence.get("table_number", ""))
            title = clean_text(table_evidence.get("table_title", ""))
            table_reference = f"Table {number}" if number else "Table"
            if title:
                table_reference += f": {title}"
            reference = f"{reference}, {table_reference}" if reference else table_reference

    issue = _sanitise_guidance(row.get("item", ""))
    assessment = _sanitise_guidance(row.get("comment", ""))
    action = _sanitise_guidance(row.get("required_action", ""))
    example = _sanitise_guidance(row.get("illustrative_guidance", ""))
    if not example:
        example = _sanitise_guidance(context_specific_example(row))
    example = re.sub(r"^for example[:,]?\s*", "", example, flags=re.I)

    heading = reference or "Supervisor review"
    parts: List[str] = []

    if issue:
        parts.append(issue.rstrip(" .") + ".")
    if assessment:
        parts.append(assessment.rstrip(" .") + ".")
    if action:
        action_text = _normalise_action_start(action)
        if re.match(r"^(?:revise|rewrite|replace|align|clarify|expand|state|define|support|remove|correct|ensure|explain|add|verify|use|undertake|apply|provide|insert|avoid|check|develop|formulate|show|demonstrate|indicate|link|situate|differentiate|populate|supply|fix)\b", action_text, flags=re.I):
            parts.append(action_text + ".")
        else:
            parts.append("Revise the marked passage so that it " + action_text[0].lower() + action_text[1:] + ".")
    elif assessment:
        parts.append("Revise the marked passage so the academic point is clear, properly supported and aligned with the section purpose.")
    if example:
        example_text = _normalise_action_start(example)
        if example_text:
            parts.append("For example, " + example_text[0].lower() + example_text[1:] + ".")

    body = f"{heading}: " + " ".join(parts) if parts else f"{heading}: Revise this passage to address the identified academic weakness."
    # Manual-confirmation and provider-failure status belongs in the internal
    # audit trail, never in a student's Word comment. Student-facing comments
    # remain developmental but must read as natural supervision, not as a
    # labelled template.
    body = _strip_visible_labels(body)
    return public_text(_shorten_comment(body), reject_placeholders=True, reject_incomplete=True)


def _format_comment_group(comments: Iterable[str]) -> str:
    """Format text for the Word Review comment pane, not the document body."""
    unique: List[str] = []
    seen = set()
    for value in comments:
        text = _strip_visible_labels(
            public_text(value, limit=comment_max_chars(), reject_placeholders=True, reject_incomplete=True)
        ).strip("[] ").rstrip(" ;.")
        text = re.sub(r"^Supervisor comments?\s*:\s*", "", text, flags=re.I)
        key = normalised(text)
        if not text or not key:
            continue
        if key in seen:
            continue
        # Avoid exporting several variants of the same guidance as a bundled comment.
        if any(_comment_similarity(key, existing_key) >= 0.50 for existing_key in seen):
            continue
        seen.add(key)
        shortened = _shorten_comment(text, comment_max_chars() if not unique else 360)
        if not shortened:
            continue
        unique.append(shortened.rstrip(" .") + ".")
        if len(unique) >= 2:
            break
    if not unique:
        return ""
    if len(unique) == 1:
        return unique[0]
    combined = unique[0] + " A related concern is that " + unique[1][0].lower() + unique[1][1:]
    return _shorten_comment(combined, comment_max_chars())


def _is_synthetic_section_heading(value: str) -> bool:
    low = normalised(value)
    return any(term in low for term in (
        "whole chapter coherence",
        "whole chapter consistency",
        "cross chapter coherence",
        "cross chapter alignment",
        "supervisor comment compliance audit",
        "alignment audit",
        "revision audit",
    ))


_GENERIC_SECTION_ASSESSMENT_RE = re.compile(
    r"\b(?:reviewed against|selected academic level|no major issue|appears adequate|looks adequate|section was reviewed|this section has been reviewed|check that its purpose|should be checked|contribution to the chapter\'s argument|generally acceptable|meets the expected standard)\b",
    flags=re.I,
)


def _section_comment_template(heading: str) -> str:
    """Return a section-specific supervisory note rather than a generic coverage stamp."""
    low = normalised(heading)
    if "background" in low:
        return (
            "This part should move logically from the broad sustainability debate to the specific Ghanaian and sectoral context of the study. "
            "It should introduce the main constructs, show how they relate and prepare the reader for the problem statement rather than merely listing prior studies. "
            "Strengthen the progression, localise the evidence and ensure that every central construct in the objectives is introduced before the problem is stated."
        )
    if "statement" in low and "problem" in low:
        return (
            "This part should establish a defensible research problem, not only a general topic of interest. "
            "It should separate the practical problem, empirical gap, contextual gap and methodological gap, then show why the selected study setting requires investigation. "
            "Revise it so the gap directly leads to the purpose, objectives and questions."
        )
    if "purpose" in low:
        return (
            "The purpose statement should express the central intent of the whole study in one coherent frame. "
            "For MPhil-level work, it must cover every principal construct and outcome that later appears in the objectives and questions. "
            "Revise the statement so a reader can trace the design, analysis and conclusions back to this purpose."
        )
    if "objective" in low:
        return (
            "The objectives should be measurable, ordered and fully aligned with the title, purpose, research questions and proposed method. "
            "Avoid mixing descriptive, relational and causal intentions without explaining the analytical logic. "
            "Revise the objectives so each one can be answered by a clearly identifiable data source and analysis procedure."
        )
    if "question" in low:
        return (
            "The research questions should mirror the objectives one-to-one and use language that matches the intended design. "
            "Terms such as relationship, effect and impact imply different levels of analysis and should not be used interchangeably. "
            "Edit the questions for alignment, punctuation and methodological consistency."
        )
    if "significance" in low:
        return (
            "This part should explain the expected value of the study without reporting findings that have not yet been produced. "
            "At MPhil level, the contribution should be tied to evidence, policy, practice and scholarship in a balanced way. "
            "Rewrite stakeholder benefits prospectively and avoid claims that imply the study has already demonstrated an effect."
        )
    if "limitation" in low:
        return (
            "This part should identify unavoidable weaknesses in the design and explain how they may affect interpretation. "
            "The tense must match the stage of the work: proposed studies should not describe sampling, response or fieldwork constraints as completed events. "
            "Revise the section so the limitations are realistic, method-linked and consistently expressed."
        )
    if "delimitation" in low:
        return (
            "This part should define the deliberate boundaries of the study, including sector, location, respondents, constructs and time scope. "
            "A reader should be able to tell exactly what is included and excluded from the inquiry. "
            "Replace unresolved prompts and ensure the stated boundaries match the methodology chapter."
        )
    if "definition" in low or "terms" in low:
        return (
            "This part should define key constructs in a way that is conceptually clear and measurable. "
            "Avoid circular definitions, absolute claims and definitions that do not correspond to the proposed indicators. "
            "Revise each definition so it states the construct boundary, relevant dimensions and link to the study context."
        )
    if "organisation" in low or "organization" in low:
        return (
            "This part should provide a concise map of the remaining chapters without making claims about results not yet produced. "
            "The description should match the actual thesis structure and maintain the same proposal or completed-study tense used elsewhere. "
            "Revise it after the chapter structure is finalised to avoid inconsistency."
        )
    if "reference" in low:
        return (
            "This part should correspond exactly with the in-text citations and follow the required referencing style. "
            "Check author spelling, publication year, DOI completeness, source credibility and whether every listed item is cited in the chapter. "
            "Remove uncited or unverifiable entries and correct mismatches before submission."
        )
    return (
        "This section should be assessed for its role in the chapter, the quality of evidence used, conceptual clarity and alignment with the study purpose. "
        "Revise any wording, citation or structural element that weakens the reader's ability to trace the argument from the problem to the methodology. "
        "Keep the section focused on the selected degree level and the approved thesis format."
    )


def _is_weak_section_assessment(value: str) -> bool:
    text = clean_text(value)
    if not text:
        return True
    low = normalised(text)
    if _GENERIC_SECTION_ASSESSMENT_RE.search(text):
        return True
    # A useful section comment should contain at least one supervision cue, not merely a coverage stamp.
    cues = ("align", "evidence", "construct", "gap", "method", "purpose", "objective", "revise", "clarify", "support", "scope", "contribution", "citation")
    if any(cue in low for cue in cues):
        return False
    return len(text) < 140


def _polish_section_assessment(value: str) -> str:
    text = _strip_visible_labels(value)
    text = re.sub(r"\bDocument-level review note\.\s*", "", text, flags=re.I)
    text = re.sub(r"\bA separate model response for this section remained unavailable[^.!?]*(?:[.!?]|$)", "", text, flags=re.I)
    text = re.sub(r"\bThe section '[^']+' is present, but its separate expert review could not be completed after focused recovery[^.!?]*(?:[.!?]|$)", "", text, flags=re.I)
    text = re.sub(r"\bIt has therefore not been treated as absent and no unverified finding has been added[^.!?]*(?:[.!?]|$)", "", text, flags=re.I)
    text = re.sub(r"\bNo unsupported criticism has been inserted[^.!?]*(?:[.!?]|$)", "", text, flags=re.I)
    text = re.sub(r"\bManual confirmation of this section is recommended[^.!?]*(?:[.!?]|$)", "", text, flags=re.I)
    text = re.sub(r"\bRecovery detail:[^.!?]*(?:[.!?]|$)", "", text, flags=re.I)
    text = re.sub(r"[^.!?]*\b(?:manifest|document map|paragraph id|section packet|parser|fallback|recovery|focused recovery|model response|P\d{1,4})\b[^.!?]*(?:[.!?]|$)", "", text, flags=re.I)
    text = re.sub(r"\bThis section (?:has been|was) reviewed(?: against [^.]+)?\.?\s*", "", text, flags=re.I)
    text = re.sub(r"\bIt appears adequate\.?\s*", "", text, flags=re.I)
    text = re.sub(r"\bNo major issue(?:s)? (?:was|were) found\.?\s*", "", text, flags=re.I)
    text = re.sub(r"\bselected academic level\b", "programme level", text, flags=re.I)
    text = re.sub(r"\s{2,}", " ", text).strip(" ;,.")
    if text:
        text = text[0].upper() + text[1:]
    return text


def _section_review_comment(row: Dict[str, Any]) -> str:
    """Build a natural, section-specific comment from the stored section review.

    Section comments must not be empty coverage stamps. They should tell the
    student what the section was assessed for and what kind of revision would
    improve it, while issue comments remain attached to exact defects.
    """
    heading = clean_text(row.get("heading") or row.get("section_name") or "Section")
    if not heading or _is_synthetic_section_heading(heading):
        return ""

    raw_assessment = _polish_section_assessment(clean_text(row.get("section_assessment", "")))
    warning = _polish_section_assessment(clean_text(row.get("coverage_warning", "")))

    # Do not release false section-coverage claims such as "no terms are
    # defined" when the heading exists. Definition sections are frequently
    # multi-paragraph and can be misread by a section packet. Exact issue
    # comments still flag weak or circular definitions where evidence exists.
    if ("definition" in normalised(heading) or "terms" in normalised(heading)) and re.search(
        r"\b(?:no|not|without)\b.{0,40}\b(?:definition|definitions|terms)\b|\b(?:definition|terms)\b.{0,40}\b(?:absent|missing|not defined|no definitions)\b",
        raw_assessment,
        flags=re.I,
    ):
        raw_assessment = ""

    if _is_weak_section_assessment(raw_assessment):
        assessment = _section_comment_template(heading)
    else:
        assessment = raw_assessment
        # Add a section-specific supervisory focus when the model assessment is
        # useful but too narrow to stand alone as a section coverage comment.
        if len(assessment) < 260:
            assessment = assessment.rstrip(" .") + ". " + _section_comment_template(heading)

    assessment = public_text(
        assessment,
        limit=760,
        reject_placeholders=True,
        reject_incomplete=True,
    )
    warning = public_text(
        warning,
        limit=320,
        reject_placeholders=True,
        reject_incomplete=True,
    )

    body = assessment or _section_comment_template(heading)
    if warning and normalised(warning) not in normalised(body):
        body = (body.rstrip(" .") + ". " + warning.rstrip(" .") + ".").strip()
    body = re.sub(r"^this section\s*[:\-]\s*", "", body, flags=re.I).strip()
    body = _strip_visible_labels(body)
    return _shorten_comment(f"{heading}: {body}", max(560, min(comment_max_chars(), 980)))


def _section_review_key(row: Dict[str, Any]) -> Tuple[Optional[int], Tuple[str, ...]]:
    heading = clean_text(row.get("heading") or row.get("section_name") or "")
    chapter_number = row.get("chapter_number")
    try:
        chapter_number = int(chapter_number) if chapter_number is not None else None
    except (TypeError, ValueError):
        chapter_number = None
    path = tuple(clean_text(value) for value in row.get("section_path") or [] if clean_text(value))
    if heading and (not path or normalised(path[-1]) != normalised(heading)):
        path = path + (heading,)
    elif not path and heading:
        path = (heading,)
    return chapter_number, path


def _add_section_review_comments(
    document,
    review: Dict[str, Any],
    *,
    author: str,
    initials: str,
    fallback_comments: List[str],
) -> None:
    """Add one native Word comment for every reviewed section/subsection.

    The AI engine already returns section assessments. Earlier exports showed
    only issue comments, so sections without issues looked unreviewed. This
    pass anchors each section assessment to the exact section heading where
    possible and falls back to the first paragraph only when the heading cannot
    be uniquely located.
    """
    seen: set[Tuple[Optional[int], Tuple[str, ...]]] = set()
    for row in review.get("academic_section_reviews") or []:
        heading = clean_text(row.get("heading") or row.get("section_name") or "")
        if not heading or _is_synthetic_section_heading(heading):
            continue
        key = _section_review_key(row)
        if key in seen:
            continue
        comment = _section_review_comment(row)
        if not comment:
            continue
        seen.add(key)
        chapter_number, headings = key
        target = _find_heading(document, headings or (heading,), chapter_number=chapter_number)
        if target is not None and _comment_on_paragraph(
            document, target, [comment], author=author, initials=initials
        ):
            continue
        # If the exact heading cannot be located, keep the section assessment
        # as a whole-chapter native comment rather than silently losing it.
        # The document-level anchor deliberately avoids title-page boilerplate.
        fallback_comments.append(comment)
        continue


def _comment_similarity(left_key: str, right_key: str) -> float:
    topical_clusters = [
        ("purpose", "objectiv", "align"),
        ("purpose", "narrow", "objectiv"),
        ("significance", "result", "proposal"),
        ("definition", "construct", "circular"),
        ("limitation", "tense", "proposal"),
        ("causal", "design", "cross"),
        ("problem", "determinant", "objective"),
        ("theor", "framework", "background"),
        ("gap", "context", "problem"),
        ("citation", "punctuat", "format"),
    ]
    for cluster in topical_clusters:
        if all(token in left_key for token in cluster) and all(token in right_key for token in cluster):
            return 0.92
    left_tokens = {token for token in re.findall(r"[a-z0-9]+", left_key) if len(token) >= 4}
    right_tokens = {token for token in re.findall(r"[a-z0-9]+", right_key) if len(token) >= 4}
    token_score = (len(left_tokens & right_tokens) / len(left_tokens | right_tokens)) if left_tokens and right_tokens else 0.0
    sequence_score = __import__("difflib").SequenceMatcher(None, left_key, right_key).ratio()
    return max(token_score, sequence_score)

def _replace_run_with_parts(run, before: str, marked: str, after: str):
    """Split a plain-text run without changing its visible formatting.

    Native Word comments must anchor to run boundaries. Splitting a run gives
    the comment an exact range while preserving the original text and run
    properties. No colour, inserted note, or tracked edit is added.
    """
    parent = run._r.getparent()
    index = parent.index(run._r)
    created = []
    for value in (before, marked, after):
        if not value:
            created.append(None)
            continue
        element = _run_element(value, source_run=run)
        parent.insert(index, element)
        index += 1
        created.append(element)
    parent.remove(run._r)
    return created


def _reviewer_initials(name: str) -> str:
    words = [part for part in re.split(r"\s+", clean_text(name)) if part]
    if not words:
        return "RV"
    initials = "".join(part[0] for part in words if part[0].isalnum()).upper()
    return (initials or "RV")[:8]


def _comment_identity(
    review: Dict[str, Any], comment_author: Optional[str] = None
) -> Tuple[str, str]:
    summary = review.get("summary") or {}
    metadata = review.get("assessment_metadata") or {}
    author = clean_text(
        comment_author
        or summary.get("reviewer_name")
        or summary.get("examiner_name")
        or metadata.get("examiner_name")
        or review.get("reviewer_name")
        or "Reviewer"
    )
    return author, _reviewer_initials(author)


def _add_native_comment(
    document,
    runs: Sequence[Run],
    comment: str,
    *,
    author: str,
    initials: str,
) -> bool:
    usable = [run for run in runs if run is not None and clean_text(run.text)]
    if not usable:
        return False
    if not hasattr(document, "add_comment"):
        raise RuntimeError(
            "Native Word comments require python-docx 1.2.0 or newer."
        )
    document.add_comment(
        runs=usable,
        text=clean_text(comment),
        author=author,
        initials=initials,
    )
    return True


def _mark_span_and_insert_comment(
    document,
    paragraph: Paragraph,
    start: int,
    end: int,
    comment: str,
    *,
    author: str,
    initials: str,
) -> bool:
    """Anchor a native comment to an exact text range.

    The paragraph text and visible formatting are preserved. The selected text
    is not recoloured and no comment paragraph is inserted into the document.
    """
    if start >= end:
        return False
    runs = list(paragraph.runs)
    cursor = 0
    marked_elements = []

    for run in runs:
        text = run.text or ""
        run_start, run_end = cursor, cursor + len(text)
        cursor = run_end
        if not text or run_end <= start or run_start >= end:
            continue

        local_start = max(0, start - run_start)
        local_end = min(len(text), end - run_start)
        before = text[:local_start]
        marked = text[local_start:local_end]
        after = text[local_end:]
        created = _replace_run_with_parts(run, before, marked, after)
        if created[1] is not None:
            marked_elements.append(created[1])

    if not marked_elements:
        return False
    anchor_runs = [Run(element, paragraph) for element in marked_elements]
    return _add_native_comment(
        document, anchor_runs, comment, author=author, initials=initials
    )

def _merge_nearby_span_groups(
    span_groups: Dict[Tuple[int, int], List[str]],
    max_gap: int = 24,
) -> List[Tuple[Tuple[int, int], List[str]]]:
    ordered = sorted(span_groups.items(), key=lambda item: item[0][0])
    merged: List[Tuple[Tuple[int, int], List[str]]] = []
    for (start, end), comments in ordered:
        if not merged:
            merged.append(((start, end), list(comments)))
            continue
        (previous_start, previous_end), previous_comments = merged[-1]
        if start <= previous_end + max_gap:
            merged[-1] = ((previous_start, max(previous_end, end)), previous_comments + list(comments))
        else:
            merged.append(((start, end), list(comments)))
    return merged


_TABLE_CAPTION_RE = re.compile(
    r"^\s*table\s+(?P<number>[A-Za-z]?\d+(?:\.\d+)*|[IVXLC]+)\b\s*[:.\-–—]?\s*(?P<title>.*)$",
    flags=re.I,
)


def _docx_blocks(document):
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def _source_locator_map(document):
    output: Dict[int, Dict[str, Any]] = {}
    tables: Dict[int, Dict[str, Any]] = {}
    paragraph_no = 0
    table_index = 0
    pending_caption: Optional[Dict[str, Any]] = None

    for block in _docx_blocks(document):
        if isinstance(block, Table):
            table_index += 1
            table_info = {
                "table": block,
                "caption_paragraph": (pending_caption or {}).get("paragraph"),
                "table_number": (pending_caption or {}).get("table_number", str(table_index)),
                "table_title": (pending_caption or {}).get("table_title", ""),
            }
            tables[table_index] = table_info
            caption_number = int((pending_caption or {}).get("paragraph_number") or 0)
            if caption_number and caption_number in output:
                output[caption_number].update({
                    "kind": "table_caption",
                    "table_index": table_index,
                    "table": block,
                    **table_info,
                })
            for row_index, row in enumerate(block.rows, start=1):
                values = [clean_text(cell.text) for cell in row.cells if clean_text(cell.text)]
                if not values:
                    continue
                paragraph_no += 1
                cell_paragraphs = []
                for cell in row.cells:
                    cell_paragraphs.extend(
                        paragraph for paragraph in cell.paragraphs
                        if clean_text(paragraph.text)
                    )
                output[paragraph_no] = {
                    "kind": "table_row",
                    "table_index": table_index,
                    "table_row": row_index,
                    "table": block,
                    "cell_paragraphs": cell_paragraphs,
                    **table_info,
                }
            pending_caption = None
            continue

        text = clean_text(block.text)
        if not text:
            continue
        paragraph_no += 1
        output[paragraph_no] = {
            "kind": "paragraph",
            "paragraph": block,
        }
        match = _TABLE_CAPTION_RE.match(text)
        if match:
            pending_caption = {
                "paragraph": block,
                "paragraph_number": paragraph_no,
                "table_number": clean_text(match.group("number")),
                "table_title": clean_text(match.group("title")),
            }

    return output, tables


def _strip_heading_number(value: str) -> str:
    return re.sub(r"^\d+(?:\.\d+){0,4}\s+", "", normalised(value)).strip()


def _find_heading(
    document,
    headings: Iterable[str],
    chapter_number: Optional[int] = None,
) -> Optional[Paragraph]:
    """Find an exact heading only. Ambiguous or partial matches are rejected."""
    targets = {normalised(value) for value in headings if normalised(value)}
    stripped_targets = {_strip_heading_number(value) for value in headings if _strip_heading_number(value)}
    candidates: List[Paragraph] = []
    active_chapter: Optional[int] = None
    chapter_words = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    }
    for paragraph in document.paragraphs:
        raw = clean_text(paragraph.text)
        low = normalised(raw)
        if not low or "supervisor comment" in low:
            continue
        chapter_match = re.fullmatch(
            r"chapter\s+(one|two|three|four|five|six|seven|eight|nine|ten|[1-9]|10)",
            low,
        )
        if chapter_match:
            token = chapter_match.group(1)
            active_chapter = int(token) if token.isdigit() else chapter_words[token]
        style_name = ""
        try:
            style_name = (paragraph.style.name or "").lower()
        except Exception:
            pass
        looks_like_heading = (
            "heading" in style_name
            or "title" in style_name
            or len(raw.split()) <= 15
            or bool(re.match(r"^\d+(?:\.\d+){0,3}\s+", raw))
        )
        if not looks_like_heading:
            continue
        exact = low in targets or _strip_heading_number(raw) in stripped_targets
        if not exact:
            continue
        if chapter_number is not None and active_chapter != chapter_number:
            continue
        candidates.append(paragraph)
    return candidates[0] if len(candidates) == 1 else None


def _comment_on_paragraph(
    document,
    paragraph: Paragraph,
    comments: List[str],
    *,
    author: str,
    initials: str,
) -> bool:
    runs = [run for run in paragraph.runs if clean_text(run.text)]
    if not runs:
        return False
    if _export_one_comment_per_finding():
        added = False
        for comment in _prepare_comment_list(comments):
            if _add_native_comment(document, runs, comment, author=author, initials=initials):
                added = True
        return added
    grouped = _format_comment_group(comments)
    return bool(
        grouped
        and _add_native_comment(
            document, runs, grouped, author=author, initials=initials
        )
    )


def _comment_on_table(
    document,
    table: Table,
    comments: List[str],
    caption: Optional[Paragraph] = None,
    *,
    author: str,
    initials: str,
) -> bool:
    prepared = _prepare_comment_list(comments) if _export_one_comment_per_finding() else [_format_comment_group(comments)]
    prepared = [comment for comment in prepared if comment]
    if not prepared:
        return False
    if caption is not None:
        runs = [run for run in caption.runs if clean_text(run.text)]
        if runs:
            added = False
            for comment in prepared:
                if _add_native_comment(document, runs, comment, author=author, initials=initials):
                    added = True
            if added:
                return True
    for row in table.rows:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                runs = [run for run in paragraph.runs if clean_text(run.text)]
                if not runs:
                    continue
                added = False
                for comment in prepared:
                    if _add_native_comment(
                        document,
                        runs,
                        comment,
                        author=author,
                        initials=initials,
                    ):
                        added = True
                if added:
                    return True
    return False


def _first_native_anchor(document) -> Optional[Paragraph]:
    """Return a stable existing paragraph for document-level comments."""
    for paragraph in document.paragraphs:
        if clean_text(paragraph.text):
            return paragraph
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    if clean_text(paragraph.text):
                        return paragraph
    return None


def _first_academic_anchor(document):
    """Return a safe academic-body anchor, never title-page boilerplate."""
    preferred = (
        "chapter one", "chapter two", "chapter three", "chapter four", "chapter five",
        "introduction", "background to the study", "statement of the problem",
    )
    for paragraph in document.paragraphs:
        text = clean_text(paragraph.text)
        low = normalised(text)
        if not text:
            continue
        if low in preferred or re.match(r"^chapter\s+(one|two|three|four|five|six|[1-9])\b", low):
            return paragraph
    title_page_terms = (
        "university of cape coast", "college of", "school of", "by", "june", "july",
        "august", "september", "emmanuel", "candidate", "supervisor"
    )
    for paragraph in document.paragraphs:
        text = clean_text(paragraph.text)
        low = normalised(text)
        if len(text.split()) < 4:
            continue
        if any(term == low or low.startswith(term) for term in title_page_terms):
            continue
        return paragraph
    return None


def _attach_document_level_comments(
    document, comments: List[str], *, author: str, initials: str
) -> None:
    """Keep unplaced findings in the Review pane without changing body text.

    Public comments must not expose provider recovery, fallback, retry or
    manual-confirmation messages. Unplaced comments are therefore exported as
    polished whole-chapter guidance without the mechanical "Document-level
    review note" prefix.
    """
    cleaned: List[str] = []
    for value in comments:
        text = public_text(
            value,
            limit=comment_max_chars(),
            reject_placeholders=True,
            reject_incomplete=True,
        )
        text = re.sub(r"^Document-level review note\.\s*", "", text, flags=re.I).strip()
        low = normalised(text)
        if not text:
            continue
        if any(token in low for token in (
            "should be checked for its contribution",
            "focused recovery",
            "separate expert review",
            "separate model response",
            "manual confirmation",
            "provider fallback",
            "independent audit",
            "recovery detail",
        )):
            continue
        cleaned.append(text)
    unique = list(dict.fromkeys(cleaned))
    if not unique:
        return
    anchor = _first_academic_anchor(document)
    if anchor is None:
        raise RuntimeError(
            "The source document has no text that can anchor native Word comments."
        )
    batches = [[comment] for comment in unique] if _export_one_comment_per_finding() else [unique[start:start + 4] for start in range(0, len(unique), 4)]
    for batch in batches:
        if not _comment_on_paragraph(
            document, anchor, batch, author=author, initials=initials
        ):
            raise RuntimeError("A native Word comment could not be anchored.")


def _preferred_evidence(row: Dict[str, Any], evidence: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Order evidence so the annotation lands on the exact claimed location."""
    target_section = normalised(row.get("section_reference") or row.get("section") or "")
    table_reference = clean_text(row.get("table_reference", ""))
    table_match = re.search(r"\bTable\s+([A-Za-z]?\d+(?:\.\d+)*)\b", table_reference, flags=re.I)
    target_table = normalised(table_match.group(1)) if table_match else ""
    quote = clean_text(row.get("problematic_quote", ""))

    def rank(item: Dict[str, Any]):
        item_section = normalised(item.get("section_reference") or item.get("heading") or "")
        item_table = normalised(item.get("table_number", ""))
        text = clean_text(item.get("text", ""))
        return (
            0 if target_table and item_table == target_table else 1,
            0 if quote and quote in text else 1,
            0 if target_section and item_section == target_section else 1,
            0 if item.get("is_heading") else 1,
            int(item.get("paragraph") or 0),
        )
    return sorted(evidence, key=rank)


def _existing_placeholder_comment(review_rows: Sequence[Dict[str, Any]], paragraph_number: int, placeholder: str) -> bool:
    """Return True when the review already contains a usable placeholder comment.

    This prevents the exporter fallback from creating a second native comment on
    the same unresolved bracketed prompt.
    """
    placeholder_key = normalised(placeholder)
    for row in review_rows:
        if row.get("status") not in ACTIONABLE_STATUSES:
            continue
        text_blob = normalised(" ".join(
            clean_text(str(row.get(field, "")))
            for field in ("item", "comment", "required_action", "illustrative_guidance", "problematic_quote")
        ))
        if not ("placeholder" in text_blob or "bracketed" in text_blob or placeholder_key in text_blob):
            continue
        evidence_paragraphs = {
            int(item.get("paragraph"))
            for item in row.get("evidence") or []
            if str(item.get("paragraph") or "").isdigit()
        }
        if paragraph_number in evidence_paragraphs or placeholder_key in text_blob:
            return True
    return False


def _placeholder_finding_rows(source_map: Dict[int, Dict[str, Any]], existing_rows: Sequence[Dict[str, Any]] = ()) -> List[Dict[str, Any]]:
    """Create deterministic review rows for unresolved bracketed prompts.

    The main review engine also checks for placeholders, but export-time
    detection prevents a missed or filtered finding from leaving obvious
    author placeholders uncommented in the final DOCX. Existing placeholder
    comments are respected so the same issue is not exported twice.
    """
    rows: List[Dict[str, Any]] = []
    seen: set[Tuple[int, str]] = set()
    for paragraph_number, locator in sorted(source_map.items()):
        text = ""
        if locator.get("kind") == "paragraph" and locator.get("paragraph") is not None:
            text = clean_text(locator["paragraph"].text)
        elif locator.get("kind") == "table_row":
            text = clean_text(" ".join(clean_text(p.text) for p in locator.get("cell_paragraphs") or []))
        if not text:
            continue
        for match in _BODY_PLACEHOLDER_RE.finditer(text):
            placeholder = clean_text(match.group(0))
            key = (paragraph_number, normalised(placeholder))
            if not placeholder or key in seen:
                continue
            if _existing_placeholder_comment(existing_rows, paragraph_number, placeholder):
                continue
            seen.add(key)
            rows.append({
                "status": STATUS_MISSING,
                "annotation_eligible": True,
                "category": "presentation",
                "severity": "major",
                "confidence": 0.99,
                "reference_label": "Delimitation of the Study" if "date" in normalised(text) or "time scope" in normalised(text) else "Drafting placeholder",
                "item": "Unresolved drafting placeholder remains in the chapter",
                "comment": "The marked bracketed text is still a drafting prompt rather than final study information. This leaves the chapter incomplete and weakens the professional readiness of the submission.",
                "required_action": "Replace the placeholder with the correct verified study detail and check the full document for any remaining bracketed prompts before resubmission.",
                "illustrative_guidance": "state the actual data-collection period once it has been confirmed, instead of leaving a prompt in the text",
                "problematic_quote": placeholder,
                "evidence": [{
                    "document_role": "current",
                    "paragraph": paragraph_number,
                    "text": text,
                }],
            })
    return rows

def native_comment_count(docx_bytes: bytes) -> int:
    """Return the number of native Word comments in an exported DOCX."""
    try:
        document = Document(io.BytesIO(docx_bytes))
        return len(list(document.comments))
    except Exception:
        return 0


def build_annotated_docx(
    source_bytes: bytes,
    review: Dict[str, Any],
    comment_author: Optional[str] = None,
) -> bytes:
    document = Document(io.BytesIO(source_bytes))
    author, initials = _comment_identity(review, comment_author)
    source_map, table_map = _source_locator_map(document)

    # All annotations are native Word comments. Exact quotations are used as
    # comment anchors where available. The source text, formatting, pagination,
    # tables, and headings remain unchanged.
    by_paragraph: Dict[int, Dict[Tuple[int, int], List[str]]] = defaultdict(lambda: defaultdict(list))
    after_paragraph: Dict[int, List[str]] = defaultdict(list)
    by_table: Dict[int, List[str]] = defaultdict(list)
    missing_by_heading: Dict[Tuple[Optional[int], Tuple[str, ...]], List[str]] = defaultdict(list)
    fallback_comments: List[str] = []

    supplied_rows = (
        list(review.get("academic_findings", []))
        + list(review.get("alignment_results", []))
        + list(review.get("revision_results", []))
    )
    review_rows = _sanitise_rows_for_export(
        supplied_rows + _placeholder_finding_rows(source_map, supplied_rows)
    )
    for row in review_rows:
        if row.get("status") not in ACTIONABLE_STATUSES:
            continue
        if row.get("annotation_eligible") is False:
            continue

        comment = _comment_body(row)
        if not comment:
            continue
        evidence = [
            item for item in (row.get("evidence") or [])
            if item.get("document_role", "current") == "current"
        ]
        evidence = _preferred_evidence(row, evidence)
        if evidence:
            best = evidence[0]
            try:
                paragraph_number = int(best.get("paragraph"))
            except (TypeError, ValueError):
                paragraph_number = 0
            locator = source_map.get(paragraph_number)
            if locator is not None:
                if locator.get("kind") in {"table_row", "table_caption"} or best.get("table_index"):
                    table_index = int(locator.get("table_index") or best.get("table_index") or 0)
                    if table_index:
                        by_table[table_index].append(comment)
                        continue
                paragraph = locator.get("paragraph")
                if paragraph is not None:
                    quote = clean_text(row.get("problematic_quote", ""))
                    exact_start = paragraph.text.find(quote) if quote else -1
                    if exact_start >= 0:
                        by_paragraph[paragraph_number][
                            (exact_start, exact_start + len(quote))
                        ].append(comment)
                    else:
                        after_paragraph[paragraph_number].append(comment)
                    continue

        headings = tuple(row.get("headings") or [row.get("section_reference") or row.get("section")])
        headings = tuple(value for value in headings if clean_text(value))
        if headings:
            chapter_number = row.get("chapter_number")
            if chapter_number is None:
                chapter_number = next(
                    (item.get("chapter_number") for item in evidence if item.get("chapter_number") is not None),
                    None,
                )
            try:
                chapter_number = int(chapter_number) if chapter_number is not None else None
            except (TypeError, ValueError):
                chapter_number = None
            missing_by_heading[(chapter_number, headings)].append(comment)
        else:
            fallback_comments.append(comment)

    for paragraph_number, span_groups in by_paragraph.items():
        locator = source_map.get(paragraph_number) or {}
        paragraph = locator.get("paragraph")
        if paragraph is None:
            continue
        merged_groups = _merge_nearby_span_groups(span_groups)
        for (start, end), comments in reversed(merged_groups):
            if _export_one_comment_per_finding():
                placed_any = False
                for comment in _prepare_comment_list(comments):
                    if _mark_span_and_insert_comment(
                        document, paragraph, start, end, comment,
                        author=author, initials=initials,
                    ):
                        placed_any = True
                    else:
                        after_paragraph[paragraph_number].append(comment)
                if not placed_any and comments:
                    after_paragraph[paragraph_number].extend(comments)
                continue
            combined = _format_comment_group(comments)
            if not _mark_span_and_insert_comment(
                document, paragraph, start, end, combined,
                author=author, initials=initials,
            ):
                after_paragraph[paragraph_number].extend(comments)

    for paragraph_number, comments in after_paragraph.items():
        locator = source_map.get(paragraph_number) or {}
        paragraph = locator.get("paragraph")
        if paragraph is not None:
            unique = list(dict.fromkeys(comments))
            if not _comment_on_paragraph(
                document, paragraph, unique, author=author, initials=initials
            ):
                fallback_comments.extend(unique)
        else:
            fallback_comments.extend(comments)

    # Process tables in reverse order for stable comment anchoring.
    for table_index in sorted(by_table, reverse=True):
        table_info = table_map.get(table_index) or {}
        table = table_info.get("table")
        comments = list(dict.fromkeys(by_table[table_index]))
        caption = table_info.get("caption_paragraph")
        if table is not None:
            if not _comment_on_table(
                document, table, comments, caption=caption,
                author=author, initials=initials,
            ):
                fallback_comments.extend(comments)
        elif caption is not None:
            if not _comment_on_paragraph(
                document, caption, comments, author=author, initials=initials
            ):
                fallback_comments.extend(comments)
        else:
            fallback_comments.extend(comments)

    # Findings about absent or underdeveloped material are placed under the
    # exact supplied section or subsection heading.
    for (chapter_number, headings), comments in missing_by_heading.items():
        unique_comments = list(dict.fromkeys(comments))
        heading = _find_heading(document, headings, chapter_number=chapter_number)
        if heading is not None:
            if not _comment_on_paragraph(
                document, heading, unique_comments,
                author=author, initials=initials,
            ):
                fallback_comments.extend(unique_comments)
        else:
            fallback_comments.extend(unique_comments)

    # Add a section-level review note for every reviewed section or subsection.
    # These comments are separate from issue findings and make coverage visible
    # in the native Word Review pane. They are added after issue comments so
    # exact issue anchors remain the primary feedback.
    _add_section_review_comments(
        document,
        review,
        author=author,
        initials=initials,
        fallback_comments=fallback_comments,
    )

    _attach_document_level_comments(
        document,
        list(dict.fromkeys(fallback_comments)),
        author=author,
        initials=initials,
    )
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()
