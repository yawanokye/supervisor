"""Conservative local copy editing and student-only native Word comments.

The original findings remain the record of the reviewed source. This separate
export records each accepted replacement and never treats an uncertain edit
as an accomplished academic correction.
"""
from __future__ import annotations

import copy
import hashlib
import io
import re
from collections import Counter
from difflib import SequenceMatcher

from docx import Document
from docx.oxml.ns import qn

from .annotation_placement import resolve_verified_location
from .annotated_exporter import (
    ACTIONABLE_STATUSES, _comment_identity, _source_locator_map,
    _mark_span_and_insert_comment,
)
from .comment_quality import public_text
from .document_parser import clean_text
from .final_review_quality import build_canonical_finding_rows
from .natural_supervisor_comment import natural_supervisor_comment

CLEAN_REVISION_VERSION = "2.12.0-clean-revision"

# These closed equivalences allow editorial changes without accepting arbitrary
# model-suggested substitutions of a construct, method or substantive claim.
_SPELLINGS = {
    "teh": "the", "recieve": "receive", "recieved": "received",
    "seperate": "separate", "seperately": "separately", "occured": "occurred",
    "occurence": "occurrence", "definately": "definitely", "relevent": "relevant",
    "behavoir": "behaviour", "behavior": "behaviour", "behaviors": "behaviours",
    "behavioral": "behavioural", "analyze": "analyse", "analyzed": "analysed",
    "analyzing": "analysing", "generalizability": "generalisability",
    "organization": "organisation", "organizations": "organisations",
    "organizational": "organisational", "characterized": "characterised",
    "utilize": "use", "utilise": "use", "utilized": "used", "utilised": "used",
}
_ARTICLES = {"a", "an", "the"}
_AGREEMENTS = [{"is", "are"}, {"was", "were"}, {"has", "have"}, {"do", "does"}, {"this", "these"}, {"that", "those"}]
_SENSITIVE = re.compile(
    r"\b(?:not|no|never|without|only|all|every|none|some|may|might|can|could|"
    r"must|should|will|would|shall|significant|insignificant|causal|causes?|"
    r"effects?|impacts?|influences?|associations?|relationships?|mediates?|"
    r"moderates?|positive|negative|higher|lower|increase[sd]?|decrease[sd]?|"
    r"proposed|planned|completed|approved|obtained|collected|conducted|validated)\b", re.I)
_VALUES = re.compile(r"\d+(?:[.,]\d+)*%?|https?://\S+|\b\w+@\w+\.\w+|\([^()]*\)|\[[^\]]*\]")
_TOKENS = re.compile(r"\b[\w'-]+\b", re.UNICODE)
_UNSAFE_XML = {qn("w:" + tag) for tag in (
    "drawing", "object", "fldChar", "fldSimple", "instrText", "hyperlink",
    "ins", "del", "sdt", "commentRangeStart", "commentRangeEnd", "tab", "br",
)}


def _deduplicate(words: list[str]) -> list[str]:
    """Collapse only immediately repeated words or phrases, never remote repeats."""
    words = list(words)
    for size in range(5, 0, -1):
        i = 0
        while i + 2 * size <= len(words):
            if words[i:i + size] == words[i + size:i + 2 * size]:
                del words[i + size:i + 2 * size]
            else:
                i += 1
        i = 0
        while i + 2 * size + 1 <= len(words):
            if words[i:i + size] == words[i + size + 1:i + 2 * size + 1] and words[i + size] == "and":
                del words[i + size:i + 2 * size + 1]
            else:
                i += 1
    return words


def permitted_replacement(original: str, replacement: str, kind: str) -> bool:
    if not original or not replacement or original == replacement:
        return False
    if len(original) > 600 or len(replacement) > 600 or "\n" in original + replacement:
        return False
    # Preserve all numbers, citations, URLs, uncertainty, negation and research
    # stage. Even a superficially plausible replacement cannot override these.
    if _VALUES.findall(original) != _VALUES.findall(replacement):
        return False
    if re.findall(r'["“”‘’]', original) != re.findall(r'["“”‘’]', replacement):
        return False
    if Counter(_SENSITIVE.findall(original.lower())) != Counter(_SENSITIVE.findall(replacement.lower())):
        return False
    before = _TOKENS.findall(original.lower())
    after = _TOKENS.findall(replacement.lower())
    if kind == "punctuation":
        # A single comma can change meaning. Only redundant spacing and
        # accidentally repeated commas are safe for deterministic repair.
        compact = lambda text: re.sub(r"\s", "", text)
        return re.sub(r",{2,}", ",", compact(original)) == compact(replacement)
    if kind == "local_repetition":
        return before != after and _deduplicate(before) == after
    if kind not in {"spelling", "grammar", "expression"}:
        return False
    if re.sub(r"[\w\s]", "", original) != re.sub(r"[\w\s]", "", replacement):
        return False
    canonical = lambda ws: [_SPELLINGS.get(w, w) for w in ws]
    left, right = canonical(before), canonical(after)
    if left == right:
        return True
    # Allow agreement/article repairs. Protect tense, pronouns, logical
    # conjunctions, prepositions, proper names and every content
    # word, including proper names and unrecognised spellings.
    for tag, a, b, c, d in SequenceMatcher(None, left, right, autojunk=False).get_opcodes():
        if tag != "equal":
            changed = left[a:b] + right[c:d]
            articles = bool(changed) and all(w in _ARTICLES for w in changed)
            agreement = b - a == d - c == 1 and any(set(changed) <= group for group in _AGREEMENTS)
            if not articles and not agreement:
                return False
    return len(before) >= 2 and len(after) >= 2


def _text_nodes(paragraph):
    return list(paragraph._p.iter(qn("w:t")))


def _replace_text(paragraph, start: int, end: int, replacement: str) -> None:
    """Change text nodes only. Runs, styles, drawings and fields are not rebuilt."""
    nodes = _text_nodes(paragraph)
    cursor = 0
    affected = []
    for node in nodes:
        text = node.text or ""
        stop = cursor + len(text)
        if (start == end and cursor <= start <= stop) or (stop > start and cursor < end):
            affected.append((node, cursor, text))
            if start == end:
                break
        cursor = stop
    if not affected:
        raise ValueError("No editable text at the exact replacement span.")
    for i, (node, offset, text) in enumerate(affected):
        lo, hi = max(0, start - offset), min(len(text), end - offset)
        node.text = text[:lo] + (replacement if i == 0 else "") + text[hi:]
        node.set(qn("xml:space"), "preserve")


def _apply_local_edit(paragraph, start: int, original: str, replacement: str) -> None:
    # Edit the smallest differing spans so bold/italic wording outside the
    # actual correction retains its own runs, including cross-run spelling.
    for tag, a, b, c, d in reversed(SequenceMatcher(None, original, replacement, autojunk=False).get_opcodes()):
        if tag != "equal":
            _replace_text(paragraph, start + a, start + b, replacement[c:d])


def _rebase_text(value: str, changes: list[dict]) -> str:
    for change in changes:
        if value.count(change["original"]) == 1:
            value = value.replace(change["original"], change["replacement"], 1)
    return value


def build_clean_revised_docx(source_bytes: bytes, review: dict, comment_author: str | None = None) -> bytes:
    document = Document(io.BytesIO(source_bytes))
    source_map, _ = _source_locator_map(document)
    # Freeze the old visible evidence before its paragraph objects are edited.
    for locator in source_map.values():
        if locator.get("paragraph") is not None:
            locator["text"] = clean_text(locator["paragraph"].text)
    rows = copy.deepcopy(build_canonical_finding_rows(review))
    rows = [r for r in rows if r.get("status") in ACTIONABLE_STATUSES]
    audit = {"version": CLEAN_REVISION_VERSION, "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
             "applied_edits": [], "rejected_edits": [], "resolved_finding_numbers": [],
             "commented_finding_numbers": [], "manual_location_finding_numbers": []}
    changes_by_location: dict[int, list[dict]] = {}
    occupied: dict[int, list[tuple[int, int]]] = {}
    plans = []
    for row in rows:
        proposals = row.get("direct_edits") or []
        if not proposals:
            continue
        location = resolve_verified_location(row, source_map)
        locator = source_map.get(location, {})
        paragraph = locator.get("paragraph")
        text = paragraph.text if paragraph is not None else ""
        accepted = []
        reason = ""
        if (row.get("source_verification_required") or row.get("manual_confirmation_required")
                or row.get("annotation_eligible") is False or row.get("confidence", 0) < .9):
            reason = "Student verification is required."
        elif paragraph is None or locator.get("kind") != "paragraph":
            reason = "A unique editable prose paragraph was not verified."
        elif any(node.tag in _UNSAFE_XML for node in paragraph._p.iter()):
            reason = "The passage contains a protected field, object, revision or comment."
        elif (str(paragraph.style.name).lower() in {"quote", "intense quote", "block text"}
              or re.search(r'''[“"].+?[”"]|(?<!\w)‘.+?’|(?<!\w)'[^'\n]+'(?!\w)''', text)
              or re.search(r'\b(?:references|bibliography)\b', str(locator.get("heading") or ""), re.I)):
            reason = "Source quotations and reference entries require student review."
        else:
            for edit in proposals:
                original, replacement = str(edit.get("original") or ""), str(edit.get("replacement") or "")
                if text.count(original) != 1 or not permitted_replacement(original, replacement, edit.get("kind", "")):
                    reason = "The proposed change did not pass exact-text and meaning-preservation checks."
                    break
                start = text.index(original)
                end = start + len(original)
                if any(start < b and end > a for a, b in occupied.get(location, []) + [(e[0], e[1]) for e in accepted]):
                    reason = "Overlapping replacements require student review."
                    break
                accepted.append((start, end, original, replacement, edit.get("kind")))
        if reason:
            audit["rejected_edits"].append({"finding_number": row.get("finding_number"), "reason": reason})
            continue
        for start, end, original, replacement, kind in accepted:
            occupied.setdefault(location, []).append((start, end))
            plans.append((location, start, original, replacement, kind, row))
        if (row.get("edit_resolves_finding") is True and accepted
                and row.get("category") == "academic_writing"
                and row.get("severity") in {"minor", "moderate"}
                and row.get("guidance_type") != "language_pattern"
                and not re.search(r'\b(?:throughout|every|each|across|consistently)\b', str(row.get("required_action") or ""), re.I)
                and len(row.get("evidence") or []) == 1
                and not row.get("merged_finding_ids")):
            audit["resolved_finding_numbers"].append(row.get("finding_number"))

    for location, start, original, replacement, kind, row in sorted(plans, key=lambda x: (x[0], -x[1])):
        paragraph = source_map[location]["paragraph"]
        _apply_local_edit(paragraph, start, original, replacement)
        change = {"finding_number": row.get("finding_number"), "paragraph": location,
                  "original": original, "replacement": replacement, "kind": kind}
        changes_by_location.setdefault(location, []).append(change)
        audit["applied_edits"].append(change)

    revised_map, _ = _source_locator_map(document)
    author, initials = _comment_identity(review, comment_author)
    for row in rows:
        number = row.get("finding_number")
        if number in audit["resolved_finding_numbers"]:
            continue
        original_location = resolve_verified_location(row, source_map)
        changes = changes_by_location.get(original_location, [])
        for key in ("problematic_quote", "exact_source_text"):
            row[key] = _rebase_text(str(row.get(key) or ""), changes)
        row.pop("exact_source_start", None)
        row.pop("exact_source_end", None)
        for evidence in row.get("evidence") or []:
            if evidence.get("document_role", "current") == "current":
                # Only rebase evidence from the paragraph actually edited.
                old = clean_text(evidence.get("text"))
                original_text = clean_text(source_map.get(original_location, {}).get("text"))
                if old and old == original_text:
                    evidence["text"] = _rebase_text(old, changes)
        location = resolve_verified_location(row, revised_map)
        comment = public_text(natural_supervisor_comment(row), limit=1800,
                              reject_placeholders=True, reject_incomplete=True)
        locator = revised_map.get(location, {})
        paragraph = locator.get("paragraph")
        quote = str(row.get("exact_source_text") or row.get("problematic_quote") or "")
        if locator.get("kind") == "table_row":
            # A row's numeric cell or prose cell must be uniquely identifiable.
            candidates = [p for p in locator.get("cell_paragraphs", []) if quote and p.text.count(quote) == 1]
            paragraph = candidates[0] if len(candidates) == 1 else None
        elif paragraph is not None and not quote:
            quote = paragraph.text
        text = paragraph.text if paragraph is not None else ""
        if (not location or paragraph is None or not comment or not quote or text.count(quote) != 1
                or row.get("annotation_eligible") is False):
            audit["manual_location_finding_numbers"].append(number)
            continue
        start = text.index(quote)
        # Use native Word comments directly, with no body markers, colours,
        # repeated explanations or appended correction register.
        placed = _mark_span_and_insert_comment(document, paragraph, start, start + len(quote),
            comment, author=author, initials=initials, include_markers=False)
        audit["commented_finding_numbers" if placed else "manual_location_finding_numbers"].append(number)

    all_numbers = {r.get("finding_number") for r in rows}
    represented = set(audit["resolved_finding_numbers"] + audit["commented_finding_numbers"] + audit["manual_location_finding_numbers"])
    if represented != all_numbers:
        raise ValueError("Every clean-revision finding must be corrected, commented or retained for location checking.")
    audit["passed"] = True
    review["clean_revision"] = audit
    review.setdefault("summary", {}).update({
        "clean_revised_document_available": True, "clean_revision_version": CLEAN_REVISION_VERSION,
        "direct_edit_count": len(audit["applied_edits"]),
        "student_action_comment_count": len(audit["commented_finding_numbers"]),
        "clean_revision_manual_location_count": len(audit["manual_location_finding_numbers"]),
    })
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()
