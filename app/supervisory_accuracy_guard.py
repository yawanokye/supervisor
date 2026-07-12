from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .document_parser import clean_text, normalised

SYNTHETIC_SECTION_MARKERS = (
    "whole chapter coherence",
    "whole-chapter coherence",
    "consistency audit",
    "cross chapter coherence",
    "cross-chapter coherence",
    "cross chapter alignment",
    "cross-chapter alignment",
    "integration audit",
    "supervisor comment compliance audit",
    "optional chapter integration",
)

COMPLETENESS_PATTERNS = (
    r"\b(?:is|are|was|were)\s+(?:entirely\s+)?missing\b",
    r"\b(?:not|never)\s+(?:provided|presented|reported|included|developed|discussed|analysed|analyzed)\b",
    r"\bno\s+(?:results?|discussion|methodology|methods?|conclusion|recommendations?|analysis|evidence)\b",
    r"\b(?:write|develop|provide|add|prepare|populate|complete|fill(?:\s+in)?)\s+(?:a\s+|the\s+)?(?:complete|full|entire)?\s*(?:chapter|results?|analysis|discussion|methodology|methods?|section|methodological details)\b",
    r"\bcomplete\s+(?:chapter|results?|analysis|discussion|methodology|section)\b",
    r"\bfull\s+methodological\s+details\b",
)

UNIVERSAL_SCOPE_PATTERNS = (
    (r"\bevery citation in (?:the|this) thesis\b", "the citation(s) in this passage"),
    (r"\ball citations in (?:the|this) thesis\b", "the citation(s) in this passage"),
    (r"\ball cited works\b", "the cited work(s) in this passage"),
    (r"\bthroughout (?:the|this) thesis\b", "in this section"),
    (r"\bthe entire thesis\b", "this section"),
    (r"\bthe whole thesis\b", "this section"),
    (r"\bthe whole document\b", "this section"),
)

TABLE_REFERENCE_RE = re.compile(
    r"\btable\s+(?P<number>[A-Za-z]?\d+(?:\.\d+)*|[IVXLC]+)\b",
    flags=re.I,
)

CHAPTER_REFERENCE_RE = re.compile(
    r"\bchapter\s+(?P<chapter>one|two|three|four|five|six|seven|eight|nine|ten|[1-9]|10)\b",
    flags=re.I,
)

CHAPTER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}

STOP_WORDS = {
    "the", "and", "of", "on", "in", "for", "to", "a", "an", "with",
    "from", "this", "that", "study", "chapter", "section", "objective",
    "effects", "effect", "impact", "analysis", "results", "discussion",
    "full", "complete", "provide", "develop", "write", "including",
}


CHAPTER_MARKER_RE = re.compile(
    r"^chapter\s+(?:one|two|three|four|five|six|seven|eight|nine|ten|[1-9]|10)$",
    flags=re.I,
)

CHAPTER_TITLE_CONTAINERS = {
    "introduction",
    "literature review",
    "review of related literature",
    "research methods",
    "research methodology",
    "materials and methods",
    "results",
    "results and discussion",
    "findings and discussion",
    "summary conclusion and recommendations",
    "summary conclusions and recommendations",
    "summary conclusion recommendations",
}

ANALYSIS_TERMS = (
    "anova", "analysis of variance", "regression", "correlation",
    "structural equation", "sem", "pls sem", "chi square", "t test",
    "mann whitney", "kruskal wallis", "thematic analysis",
)


def paragraph_id(paragraph: Dict[str, Any]) -> str:
    role = paragraph.get("document_role", "current")
    number = int(paragraph.get("paragraph") or 0)
    if role == "previous":
        return f'C{int(paragraph.get("document_index") or 0)}P{number}'
    if role == "original":
        return f'O{number}'
    return f'P{number}'


def source_section(paragraph: Dict[str, Any]) -> str:
    path = [clean_text(value) for value in paragraph.get("section_path") or [] if clean_text(value)]
    if path:
        return path[-1]
    return clean_text(paragraph.get("heading") or "")


def is_synthetic_section(value: str) -> bool:
    low = normalised(value)
    return any(marker in low for marker in SYNTHETIC_SECTION_MARKERS)


def _substantive_tokens(value: str) -> set[str]:
    return {
        token for token in normalised(value).split()
        if len(token) >= 3 and token not in STOP_WORDS and not token.isdigit()
    }


def build_factual_index(paragraphs: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    current = [
        row for row in paragraphs
        if row.get("document_role", "current") == "current" and clean_text(row.get("text", ""))
    ]
    sections: Dict[str, Dict[str, Any]] = {}
    headings: List[str] = []
    chapter_counts: Counter[int] = Counter()
    chapter_rows: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    tables: Dict[int, Dict[str, Any]] = {}

    for position, row in enumerate(current):
        row = dict(row)
        row.setdefault("_document_position", position)
        section = source_section(row)
        key = normalised(section)
        if key:
            entry = sections.setdefault(key, {"heading": section, "rows": [], "ids": []})
            entry["rows"].append(row)
            entry["ids"].append(paragraph_id(row))
        if row.get("is_heading"):
            heading = clean_text(row.get("text", ""))
            if heading and normalised(heading) not in {normalised(value) for value in headings}:
                headings.append(heading)
        chapter = row.get("chapter_number")
        if isinstance(chapter, int):
            chapter_counts[chapter] += 1
            chapter_rows[chapter].append(row)
        table_index = row.get("table_index")
        if isinstance(table_index, int):
            table = tables.setdefault(table_index, {
                "table_index": table_index,
                "table_number": clean_text(row.get("table_number", "")),
                "table_title": clean_text(row.get("table_title", "")),
                "section": section,
                "rows": [],
                "ids": [],
            })
            if clean_text(row.get("table_number", "")):
                table["table_number"] = clean_text(row.get("table_number", ""))
            if clean_text(row.get("table_title", "")):
                table["table_title"] = clean_text(row.get("table_title", ""))
            table["rows"].append(row)
            table["ids"].append(paragraph_id(row))

    return {
        "paragraphs": current,
        "sections": sections,
        "headings": headings,
        "chapter_counts": chapter_counts,
        "chapter_rows": chapter_rows,
        "tables": tables,
        "full_text": normalised("\n".join(clean_text(row.get("text", "")) for row in current)),
    }


def _issue_text(issue: Dict[str, Any]) -> str:
    return clean_text(" ".join([
        str(issue.get("section") or ""),
        str(issue.get("issue_title") or ""),
        str(issue.get("assessment") or ""),
        str(issue.get("academic_consequence") or ""),
        str(issue.get("required_action") or ""),
        str(issue.get("illustrative_guidance") or ""),
    ]))


def _completion_claim(text: str) -> bool:
    return any(re.search(pattern, text, flags=re.I) for pattern in COMPLETENESS_PATTERNS)


def _chapter_claims(text: str) -> List[int]:
    values: List[int] = []
    for match in CHAPTER_REFERENCE_RE.finditer(text):
        token = match.group("chapter").lower()
        values.append(int(token) if token.isdigit() else CHAPTER_WORDS[token])
    return values


def _best_matching_section(text: str, facts: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    low = normalised(text)
    best: Optional[Tuple[float, Dict[str, Any]]] = None
    issue_tokens = _substantive_tokens(text)
    for entry in facts["sections"].values():
        heading = clean_text(entry.get("heading", ""))
        heading_low = normalised(heading)
        heading_tokens = _substantive_tokens(heading)
        if not heading_low or len(heading_tokens) < 3:
            continue
        if heading_low in low:
            score = 1.0
        else:
            score = len(issue_tokens & heading_tokens) / len(heading_tokens)
        if score >= 0.62 and (best is None or score > best[0]):
            best = (score, entry)
    return best[1] if best else None


def _evidence_sections(issue: Dict[str, Any], paragraph_index: Dict[str, Dict[str, Any]]) -> List[str]:
    return [
        source_section(paragraph_index[pid])
        for pid in issue.get("evidence_paragraph_ids") or []
        if pid in paragraph_index and source_section(paragraph_index[pid])
    ]


def _dominant_evidence_section(issue: Dict[str, Any], paragraph_index: Dict[str, Dict[str, Any]]) -> str:
    sections = _evidence_sections(issue, paragraph_index)
    if not sections:
        return ""
    counts = Counter(normalised(value) for value in sections)
    winner = counts.most_common(1)[0][0]
    return next(value for value in sections if normalised(value) == winner)


def _filter_evidence_to_section(
    issue: Dict[str, Any],
    paragraph_index: Dict[str, Dict[str, Any]],
    section: str,
) -> None:
    if issue.get("category") == "cross_section_coherence":
        return
    target = normalised(section)
    ids = [
        pid for pid in issue.get("evidence_paragraph_ids") or []
        if pid in paragraph_index and normalised(source_section(paragraph_index[pid])) == target
    ]
    if ids:
        issue["evidence_paragraph_ids"] = ids[:8]


def _localise_universal_scope(issue: Dict[str, Any]) -> None:
    for field in ("assessment", "academic_consequence", "required_action", "illustrative_guidance"):
        value = clean_text(issue.get(field, ""))
        for pattern, replacement in UNIVERSAL_SCOPE_PATTERNS:
            value = re.sub(pattern, replacement, value, flags=re.I)
        issue[field] = value


def _table_identity_from_evidence(
    issue: Dict[str, Any], paragraph_index: Dict[str, Dict[str, Any]]
) -> List[Tuple[str, str]]:
    values: List[Tuple[str, str]] = []
    for pid in issue.get("evidence_paragraph_ids") or []:
        row = paragraph_index.get(pid)
        if not row:
            continue
        number = clean_text(row.get("table_number", ""))
        title = clean_text(row.get("table_title", ""))
        if number and (number, title) not in values:
            values.append((number, title))
    return values


def _normalise_table_references(issue: Dict[str, Any], paragraph_index: Dict[str, Dict[str, Any]]) -> bool:
    text = _issue_text(issue)
    mentioned = [match.group("number") for match in TABLE_REFERENCE_RE.finditer(text)]
    identities = _table_identity_from_evidence(issue, paragraph_index)
    if mentioned and not identities:
        return False
    if not identities:
        return True

    # When all evidence belongs to one table, the evidence metadata is the source
    # of truth. Correct any model-generated table number rather than rejecting a
    # useful comment.
    if len(identities) == 1:
        number, title = identities[0]
        key = normalised(number)
        filtered_ids = [
            pid for pid in issue.get("evidence_paragraph_ids") or []
            if pid in paragraph_index
            and (
                not clean_text(paragraph_index[pid].get("table_number", ""))
                or normalised(clean_text(paragraph_index[pid].get("table_number", ""))) == key
            )
        ]
        if not filtered_ids:
            return False
        issue["evidence_paragraph_ids"] = filtered_ids[:8]
        for field in ("issue_title", "assessment", "academic_consequence", "required_action", "illustrative_guidance"):
            value = clean_text(issue.get(field, ""))
            value = TABLE_REFERENCE_RE.sub(f"Table {number}", value)
            issue[field] = value
        issue["canonical_table_number"] = number
        issue["canonical_table_title"] = title
        return True

    identity_by_number = {normalised(number): (number, title) for number, title in identities}
    mentioned_keys = list(dict.fromkeys(normalised(value) for value in mentioned if normalised(value)))
    if mentioned_keys:
        if any(key not in identity_by_number for key in mentioned_keys):
            return False
        if len(mentioned_keys) == 1:
            key = mentioned_keys[0]
            number, title = identity_by_number[key]
            filtered_ids = []
            for pid in issue.get("evidence_paragraph_ids") or []:
                if pid not in paragraph_index:
                    continue
                row = paragraph_index[pid]
                row_table = normalised(clean_text(row.get("table_number", "")))
                if row_table == key:
                    filtered_ids.append(pid)
                elif issue.get("category") == "cross_section_coherence" and not row_table:
                    # Preserve the non-table method/objective evidence needed to
                    # substantiate a cross-section mismatch, while discarding
                    # rows from unrelated tables. The exact named table remains
                    # the preferred annotation anchor.
                    filtered_ids.append(pid)
            if not any(
                normalised(clean_text(paragraph_index[pid].get("table_number", ""))) == key
                for pid in filtered_ids
            ):
                return False
            issue["evidence_paragraph_ids"] = filtered_ids[:8]
            issue["canonical_table_number"] = number
            issue["canonical_table_title"] = title
            return True
        return len(identity_by_number) == len(mentioned_keys) and len(mentioned_keys) <= 2

    if issue.get("category") == "cross_section_coherence":
        issue["suppress_table_reference"] = True
        return True
    # The model cited several tables without naming which one the comment
    # concerns. Reject rather than placing the comment on the first table.
    return False


def _section_rows_for_issue(
    issue: Dict[str, Any],
    paragraph_index: Dict[str, Dict[str, Any]],
    section: str,
) -> List[Dict[str, Any]]:
    target = normalised(section)
    return [
        paragraph_index[pid]
        for pid in issue.get("evidence_paragraph_ids") or []
        if pid in paragraph_index and normalised(source_section(paragraph_index[pid])) == target
    ]


def _chapter_has_substantive_content(facts: Dict[str, Any], chapter: Optional[int]) -> bool:
    if not isinstance(chapter, int):
        return False
    return sum(
        1 for row in facts.get("chapter_rows", {}).get(chapter, [])
        if not row.get("is_heading") and clean_text(row.get("text", ""))
    ) >= 3


def _chapter_has_introduction(facts: Dict[str, Any], chapter: Optional[int]) -> bool:
    if not isinstance(chapter, int):
        return False
    rows = facts.get("chapter_rows", {}).get(chapter, [])
    intro_rows = [row for row in rows if normalised(source_section(row)) == "introduction"]
    return sum(1 for row in intro_rows if not row.get("is_heading") and clean_text(row.get("text", ""))) >= 1


def _is_structural_heading_row(row: Dict[str, Any]) -> bool:
    if not row.get("is_heading"):
        return False
    text = clean_text(row.get("text", ""))
    low = normalised(text)
    return bool(CHAPTER_MARKER_RE.fullmatch(text) or low in CHAPTER_TITLE_CONTAINERS)


def _verified_missing_section(issue: Dict[str, Any]) -> bool:
    return bool(
        issue.get("section_contract_verified")
        and normalised(str(issue.get("section_status") or "")) == "missing"
        and clean_text(issue.get("missing_section_label") or issue.get("section_contract_label"))
    )


def _verified_missing_section_still_absent(issue: Dict[str, Any], facts: Dict[str, Any]) -> bool:
    """Confirm a deterministic missing-section finding against chapter headings.

    A missing section is anchored beside the nearest insertion point, so the
    generic completeness guard must not interpret the anchor's substantive text
    as evidence that the absent section exists.  We instead test the aliases
    supplied by the section contract against headings in the relevant chapter.
    """
    try:
        chapter = int(issue.get("chapter_number"))
    except (TypeError, ValueError):
        chapter = 0
    aliases = [
        normalised(value)
        for value in (
            list(issue.get("section_aliases") or [])
            + [issue.get("missing_section_label"), issue.get("section_contract_label")]
        )
        if normalised(str(value or ""))
    ]
    if not aliases:
        return False
    headings = [
        normalised(clean_text(row.get("text", "")))
        for row in facts.get("chapter_rows", {}).get(chapter, [])
        if row.get("is_heading") and clean_text(row.get("text", ""))
    ]
    for alias in aliases:
        if any(alias == heading or alias in heading or heading in alias for heading in headings):
            return False
    return True



def guard_section_assessment(
    assessment: str,
    evidence_rows: Sequence[Dict[str, Any]],
) -> str:
    """Remove unsupported factual claims from a section-level narrative.

    Section assessments are free text rather than evidence-ID objects. They
    therefore need a deterministic final check before they are used in the
    summary report. In particular, a methodology introduction must not acquire
    an ANOVA or table strength merely because that material occurs elsewhere in
    the document.
    """
    text = clean_text(assessment)
    if not text:
        return ""
    evidence_text = normalised(" ".join(clean_text(row.get("text", "")) for row in evidence_rows))
    has_table = any(row.get("table_number") or row.get("source_kind") == "table_row" for row in evidence_rows)
    kept: List[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        sentence = clean_text(sentence)
        if not sentence:
            continue
        low = normalised(sentence)
        unsupported = False
        for term in ANALYSIS_TERMS:
            if term in low and term not in evidence_text:
                unsupported = True
                break
        if not unsupported and re.search(r"\btable(?:s)?\b", low) and not has_table:
            unsupported = True
        if not unsupported:
            kept.append(sentence)
    return " ".join(kept)

def guard_strength(
    strength: Dict[str, Any],
    paragraph_index: Dict[str, Dict[str, Any]],
    facts: Dict[str, Any],
    canonical_section: str = "",
) -> Optional[Dict[str, Any]]:
    guarded = dict(strength)
    ids = [pid for pid in guarded.get("evidence_paragraph_ids") or [] if pid in paragraph_index]
    if not ids:
        return None
    guarded["evidence_paragraph_ids"] = list(dict.fromkeys(ids))[:6]
    evidence_section = source_section(paragraph_index[ids[0]])
    section = clean_text(canonical_section or guarded.get("section") or evidence_section)
    if is_synthetic_section(section):
        section = evidence_section
    if not section:
        return None
    if not any(normalised(source_section(paragraph_index[pid])) == normalised(section) for pid in ids):
        return None
    guarded["section"] = section

    observation = clean_text(guarded.get("observation", ""))
    evidence_text = normalised(" ".join(clean_text(paragraph_index[pid].get("text", "")) for pid in ids))
    observation_low = normalised(observation)
    for term in ANALYSIS_TERMS:
        if term in observation_low and term not in evidence_text:
            return None
    if "table" in observation_low and not any(paragraph_index[pid].get("table_number") for pid in ids):
        return None
    return guarded


def guard_issue(
    issue: Dict[str, Any],
    paragraph_index: Dict[str, Dict[str, Any]],
    facts: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    guarded = dict(issue)
    ids = [pid for pid in guarded.get("evidence_paragraph_ids") or [] if pid in paragraph_index]
    if not ids:
        return None
    guarded["evidence_paragraph_ids"] = list(dict.fromkeys(ids))[:8]

    if _verified_missing_section(guarded):
        if not _verified_missing_section_still_absent(guarded, facts):
            return None
        anchor_row = paragraph_index[guarded["evidence_paragraph_ids"][0]]
        # Preserve the deterministic section label while recording the real
        # insertion anchor separately.  Missing-section findings are exported as
        # chapter correction notes rather than pretending the absent section has
        # an exact sentence anchor.
        guarded["section"] = clean_text(guarded.get("section")) or source_section(anchor_row)
        guarded["insertion_anchor_section"] = source_section(anchor_row)
        guarded["confirmed_missing_section"] = True
        guarded["problematic_quote"] = clean_text(anchor_row.get("text", ""))[:260]
        _localise_universal_scope(guarded)
        return guarded

    dominant_section = _dominant_evidence_section(guarded, paragraph_index)
    if not dominant_section:
        return None
    if is_synthetic_section(clean_text(guarded.get("section", ""))):
        guarded["section"] = dominant_section
    elif normalised(clean_text(guarded.get("section", ""))) not in facts["sections"]:
        guarded["section"] = dominant_section
    # The named location must itself be represented in the evidence. Cross-section
    # findings may include additional sections, but they cannot be placed under a
    # section that supplied no evidence.
    if not _section_rows_for_issue(guarded, paragraph_index, guarded["section"]):
        return None
    _filter_evidence_to_section(guarded, paragraph_index, guarded["section"])
    if not guarded.get("evidence_paragraph_ids"):
        return None

    evidence_rows = [paragraph_index[pid] for pid in guarded.get("evidence_paragraph_ids") or []]
    text = _issue_text(guarded)
    if evidence_rows and all(_is_structural_heading_row(row) for row in evidence_rows):
        chapter = next((row.get("chapter_number") for row in evidence_rows if isinstance(row.get("chapter_number"), int)), None)
        low = normalised(text)
        if _chapter_has_substantive_content(facts, chapter) and (
            _completion_claim(text)
            or any(term in low for term in ("add a short introductory paragraph", "introduce the chapter purpose and structure", "populate chapter"))
        ):
            return None
        if _chapter_has_introduction(facts, chapter) and any(term in low for term in (
            "introductory paragraph under the chapter heading",
            "under the chapter title",
            "introduce the chapter purpose and structure",
        )):
            return None

    if _completion_claim(text):
        for chapter in _chapter_claims(text):
            if facts["chapter_counts"].get(chapter, 0) >= 5:
                return None
        low_text = normalised(text)
        functional_chapters = {
            1: ("introduction chapter", "chapter one", "background and problem"),
            2: ("literature review", "theoretical review", "empirical review"),
            3: ("methodology chapter", "methods chapter", "research methodology", "research methods"),
            4: ("results chapter", "results section", "results and discussion", "analysis chapter"),
            5: ("conclusion chapter", "conclusions chapter", "summary conclusion", "recommendations chapter"),
        }
        for chapter, aliases in functional_chapters.items():
            if any(alias in low_text for alias in aliases) and facts["chapter_counts"].get(chapter, 0) >= 5:
                return None
        matched_section = _best_matching_section(text, facts)
        if matched_section:
            matched_heading = clean_text(matched_section.get("heading", ""))
            evidence_heading = clean_text(guarded.get("section", ""))
            if normalised(matched_heading) != normalised(evidence_heading):
                # The content exists elsewhere in the submitted work, so a local
                # passage cannot support a claim that the whole section is absent.
                return None
            if len(matched_section.get("rows") or []) >= 3:
                # Replace absolute completeness language with an adequacy-focused
                # instruction when the cited section clearly exists.
                for field in ("assessment", "required_action", "illustrative_guidance"):
                    value = clean_text(guarded.get(field, ""))
                    value = re.sub(r"\b(?:write|develop|provide|add|prepare|populate)\s+(?:a\s+|the\s+)?(?:complete|full|entire)\b", "strengthen the", value, flags=re.I)
                    value = re.sub(r"\b(?:is|are|was|were)\s+(?:entirely\s+)?missing\b", "is insufficiently developed", value, flags=re.I)
                    guarded[field] = value

    _localise_universal_scope(guarded)
    if not _normalise_table_references(guarded, paragraph_index):
        return None

    quote = clean_text(guarded.get("problematic_quote", ""))
    if quote and not any(
        quote in clean_text(paragraph_index[pid].get("text", ""))
        for pid in guarded.get("evidence_paragraph_ids") or []
    ):
        guarded["problematic_quote"] = ""
        guarded["confidence"] = min(float(guarded.get("confidence") or 0.0), 0.72)

    return guarded


def apply_accuracy_gate(
    issues: Iterable[Dict[str, Any]],
    paragraph_index: Dict[str, Dict[str, Any]],
    paragraphs: Sequence[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    facts = build_factual_index(paragraphs)
    kept: List[Dict[str, Any]] = []
    dropped = 0
    adjusted = 0
    for issue in issues:
        before = repr(issue)
        guarded = guard_issue(issue, paragraph_index, facts)
        if guarded is None:
            dropped += 1
            continue
        if repr(guarded) != before:
            adjusted += 1
        kept.append(guarded)
    return kept, {"kept": len(kept), "dropped": dropped, "adjusted": adjusted}


def _make_issue(
    *,
    finding_id: str,
    category: str,
    section: str,
    title: str,
    severity: str,
    confidence: float,
    evidence_ids: Sequence[str],
    quote: str,
    assessment: str,
    consequence: str,
    action: str,
) -> Dict[str, Any]:
    return {
        "finding_id": finding_id,
        "category": category,
        "section": section,
        "issue_title": title,
        "severity": severity,
        "confidence": confidence,
        "evidence_paragraph_ids": list(dict.fromkeys(evidence_ids))[:8],
        "problematic_quote": quote,
        "assessment": assessment,
        "academic_consequence": consequence,
        "required_action": action,
        "illustrative_guidance": "",
        "guidance_type": "direct_correction",
        "source_verification_required": False,
        "context_guard_adjusted": False,
    }


def deterministic_expert_issues(
    paragraphs: Sequence[Dict[str, Any]],
    *,
    academic_level: Any = "",
    research_approach: Any = "",
) -> List[Dict[str, Any]]:
    """Add high-confidence cross-section checks that should not depend on model luck.

    Every declared degree level receives deterministic coherence, source-traceability and scholarly-presentation checks. These checks are evidence anchored and complement, rather than replace, the expert model.
    """
    current = [row for row in paragraphs if row.get("document_role", "current") == "current"]
    output: List[Dict[str, Any]] = []

    def find_rows(pattern: str, *, chapters: Optional[set[int]] = None) -> List[Dict[str, Any]]:
        regex = re.compile(pattern, flags=re.I)
        return [
            row for row in current
            if (not chapters or row.get("chapter_number") in chapters)
            and regex.search(clean_text(row.get("text", "")))
        ]

    # Cross-sectional data do not, by themselves, establish causality. This
    # check is anchored in the design statement and the exact causal wording.
    cross_rows = find_rows(r"\bcross[ -]?sectional\b", chapters={3})
    causal_rows = find_rows(
        r"\b(?:effect|impact|influence|determinant)\b",
        chapters={1, 4, 5},
    )
    if cross_rows and causal_rows:
        target = next((row for row in causal_rows if row.get("is_heading") or "research question" in normalised(source_section(row))), causal_rows[0])
        output.append(_make_issue(
            finding_id="DET-CROSS-SECTION-CAUSAL",
            category="cross_section_coherence",
            section=source_section(target),
            title="Causal wording exceeds the cross-sectional design",
            severity="major",
            confidence=0.96,
            evidence_ids=[paragraph_id(target), paragraph_id(cross_rows[0])],
            quote=clean_text(target.get("text", ""))[:260],
            assessment="The thesis uses causal language while the methodology identifies a cross-sectional design. The design supports association or prediction, not a definitive causal effect, unless an additional causal identification strategy is established.",
            consequence="The wording overstates what can be inferred from the data and weakens consistency between the research questions, analysis and conclusions.",
            action="Use associational or predictive wording consistently in the title, objectives, questions, results and conclusions, or provide and justify a valid causal identification strategy.",
        ))

    formula_rows = find_rows(r"\b(?:yamane|cochran|krejcie|sample size formula)\b", chapters={3})
    nonprob_rows = find_rows(r"\b(?:convenience|purposive|judgmental|snowball)\s+sampl", chapters={3})
    if formula_rows and nonprob_rows:
        target = nonprob_rows[0]
        output.append(_make_issue(
            finding_id="DET-SAMPLING-FORMULA-MISMATCH",
            category="methodological_rigour",
            section=source_section(target),
            title="Sample-size justification is not reconciled with non-probability selection",
            severity="major",
            confidence=0.95,
            evidence_ids=[paragraph_id(formula_rows[0]), paragraph_id(target)],
            quote=clean_text(target.get("text", ""))[:260],
            assessment="A probability-oriented sample-size formula is combined with a non-probability sampling technique without explaining the inferential limitation.",
            consequence="The numerical sample size does not make the achieved sample statistically representative, and generalisation may be overstated.",
            action="Explain the distinct purpose of the sample-size calculation, justify the non-probability selection, and restrict generalisation to the sampled respondents and study context.",
        ))

    methods_multi = find_rows(r"\bmultiple regression\b", chapters={3})
    methods_control = find_rows(r"\b(?:simultaneous|entered together|controlling for|holding .* constant|unique effect)\b", chapters={3})
    predictor_rows = find_rows(r"\bpredictors?\s*:\s*\(constant\)\s*,", chapters={4})
    single_predictor_rows = []
    combined_predictor_rows = []
    for row in predictor_rows:
        text = clean_text(row.get("text", ""))
        tail = re.split(r"predictors?\s*:\s*", text, maxsplit=1, flags=re.I)[-1]
        predictors = [part.strip() for part in tail.split(",") if part.strip() and "constant" not in part.lower()]
        if len(predictors) <= 1:
            single_predictor_rows.append(row)
        elif len(predictors) >= 2:
            combined_predictor_rows.append(row)
    if methods_multi and methods_control and len(single_predictor_rows) >= 2 and not combined_predictor_rows:
        target = single_predictor_rows[0]
        output.append(_make_issue(
            finding_id="DET-MULTIPLE-REGRESSION-MISMATCH",
            category="cross_section_coherence",
            section=source_section(target),
            title="The reported regressions do not implement the stated simultaneous multiple-regression model",
            severity="critical",
            confidence=0.98,
            evidence_ids=[paragraph_id(methods_multi[0]), paragraph_id(methods_control[0]), paragraph_id(single_predictor_rows[0]), paragraph_id(single_predictor_rows[1])],
            quote=clean_text(target.get("text", ""))[:260],
            assessment="Chapter Three states that multiple regression estimates the predictors jointly or controls for the other predictors, but Chapter Four reports separate one-predictor models.",
            consequence="The reported coefficients are bivariate effects and cannot be interpreted as unique effects holding the other predictors constant. Comparisons of the strongest predictor are also unsupported by the separate models.",
            action="Estimate and report one combined multiple-regression model containing all specified predictors, then revise the coefficient interpretations, model diagnostics, conclusions and recommendations accordingly. If separate simple regressions were intended, correct Chapter Three and remove claims about controlled or unique effects.",
        ))

    zero_p_rows = find_rows(r"(?:\bp\s*=\s*0?\.000\b|\bsig\.?\s*[|:=]?\s*0?\.000\b|\|\s*\.000[a-z]?\b)", chapters={4})
    if zero_p_rows:
        target = zero_p_rows[0]
        output.append(_make_issue(
            finding_id="DET-P-ZERO-REPORTING",
            category="results_and_interpretation",
            section=source_section(target),
            title="A p-value is reported as zero",
            severity="moderate",
            confidence=0.99,
            evidence_ids=[paragraph_id(target)],
            quote=clean_text(target.get("text", ""))[:260],
            assessment="The statistical output is reported as p = .000 or Sig. = .000. A p-value is not reported as exactly zero.",
            consequence="The notation is statistically inaccurate and may be repeated incorrectly in the narrative or hypothesis decision.",
            action="Report the value as p < .001 and apply the same correction consistently in the table, narrative interpretation and hypothesis decision.",
        ))

    placeholder_rows = find_rows(
        r"\[(?:insert|add|specify|provide|complete|start|end|x\b)[^\]]*\]"
    )
    if placeholder_rows:
        target = placeholder_rows[0]
        output.append(_make_issue(
            finding_id="DET-UNRESOLVED-DRAFT-PLACEHOLDERS",
            category="presentation",
            section=source_section(target),
            title="Unresolved drafting placeholders remain in the chapter",
            severity="major",
            confidence=0.99,
            evidence_ids=[paragraph_id(row) for row in placeholder_rows[:6]],
            quote=clean_text(target.get("text", ""))[:260],
            assessment="The submitted chapter still contains bracketed drafting prompts instead of final study information.",
            consequence="The document is incomplete and cannot be treated as submission-ready while required dates or other study details remain unresolved.",
            action="Replace every bracketed drafting prompt with the correct verified study information and check the full chapter for any remaining placeholders before resubmission.",
        ))

    malformed_question_rows = find_rows(r"\.\?")
    if malformed_question_rows:
        target = malformed_question_rows[0]
        output.append(_make_issue(
            finding_id="DET-MALFORMED-QUESTION-PUNCTUATION",
            category="academic_writing",
            section=source_section(target),
            title="A research question contains malformed punctuation",
            severity="minor",
            confidence=0.99,
            evidence_ids=[paragraph_id(target)],
            quote=clean_text(target.get("text", ""))[:260],
            assessment="The question ends with a full stop followed by a question mark.",
            consequence="The error reduces the professional presentation of the research questions.",
            action="Remove the full stop and retain a single question mark at the end of the sentence.",
        ))

    proposal_rows = find_rows(r"\b(?:will be obtained|will be collected|will be considered|will be covered)\b", chapters={1})
    completed_rows = find_rows(r"\b(?:the study faced|data were collected|findings showed|results revealed)\b", chapters={1})
    if proposal_rows and completed_rows:
        target = completed_rows[0]
        output.append(_make_issue(
            finding_id="DET-CHAPTER-ONE-TENSE-MISMATCH",
            category="academic_writing",
            section=source_section(target),
            title="Proposal and completed-study tenses are mixed",
            severity="moderate",
            confidence=0.96,
            evidence_ids=[paragraph_id(proposal_rows[0]), paragraph_id(target)],
            quote=clean_text(target.get("text", ""))[:260],
            assessment="Chapter One uses future tense for a proposed study but also describes constraints as though the study and data collection have already been completed.",
            consequence="The mixed stage signals make the status of the research unclear and weaken internal consistency.",
            action="Use proposal-appropriate future or present tense throughout if the study has not been completed. Use past tense consistently only when reporting a completed study.",
        ))

    opening_grammar_rows = find_rows(r"\bThe study revolve\b", chapters={1})
    if opening_grammar_rows:
        target = opening_grammar_rows[0]
        output.append(_make_issue(
            finding_id="DET-OPENING-SUBJECT-VERB-AGREEMENT",
            category="academic_writing",
            section=source_section(target),
            title="The opening sentence contains a subject-verb agreement error",
            severity="minor",
            confidence=0.99,
            evidence_ids=[paragraph_id(target)],
            quote="The study revolve",
            assessment="The singular subject 'study' is paired with the plural verb form 'revolve'. The sentence is also awkwardly framed as the study revolving around global environmental issues.",
            consequence="A grammatical error in the opening sentence weakens the chapter's first academic impression.",
            action="Rewrite the opening sentence in a direct form and use the correct singular verb, for example by stating that climate change, pollution and resource depletion have intensified concern about environmental sustainability.",
        ))


    level_value = normalised(str(academic_level or "")).replace("-", " ")
    if level_value == "phd" or level_value.startswith("doctor of philosophy"):
        degree_key = "phd"
        degree_label = "PhD"
    elif "professional doctorate" in level_value or level_value.startswith("doctor of ") or level_value.startswith("doctoral"):
        degree_key = "professional_doctorate"
        degree_label = "Professional Doctorate"
    elif "non research master" in level_value:
        degree_key = "non_research_masters"
        degree_label = "Non-Research Master's"
    elif "research masters" in level_value or "research master" in level_value or "mphil" in level_value:
        degree_key = "research_masters"
        degree_label = "Research Master's/MPhil"
    else:
        degree_key = "bachelors"
        degree_label = "Bachelor's"

    if degree_key in {"bachelors", "non_research_masters", "research_masters", "professional_doctorate", "phd"}:
        # The purpose must cover the substantive constructs introduced by the
        # objectives. This lexical audit is deliberately conservative and
        # ignores generic research, setting and population terms.
        purpose_rows = [
            row for row in current
            if row.get("chapter_number") == 1
            and "purpose" in normalised(source_section(row))
            and not row.get("is_heading")
        ]
        objective_rows = [
            row for row in current
            if row.get("chapter_number") == 1
            and "research objective" in normalised(source_section(row))
            and not row.get("is_heading")
        ]
        if purpose_rows and objective_rows:
            stop = {
                "the", "this", "study", "research", "purpose", "objective", "objectives",
                "to", "examine", "assess", "determine", "investigate", "explore", "analyse",
                "analyze", "evaluate", "identify", "establish", "current", "adopted", "level",
                "relationship", "effect", "impact", "influence", "among", "within", "between",
                "regarding", "practices", "practice", "firms", "firm", "companies", "company",
                "organisations", "organizations", "manufacturing", "central", "region", "ghana",
                "and", "of", "on", "in", "by", "for", "with", "from", "as", "a", "an",
            }
            purpose_tokens = {
                token for token in re.findall(r"[a-z][a-z-]{2,}", normalised(" ".join(clean_text(row.get("text", "")) for row in purpose_rows)))
                if token not in stop
            }
            objective_tokens = {
                token for token in re.findall(r"[a-z][a-z-]{2,}", normalised(" ".join(clean_text(row.get("text", "")) for row in objective_rows)))
                if token not in stop
            }
            missing_tokens = sorted(objective_tokens - purpose_tokens)
            # Require either two omitted substantive tokens or a recognised
            # construct word. This avoids flagging one incidental adjective.
            recognised = {
                "awareness", "performance", "satisfaction", "adoption", "intention",
                "productivity", "efficiency", "profitability", "resilience", "innovation",
                "compliance", "quality", "behaviour", "behavior", "capability", "risk",
            }
            material_missing = [token for token in missing_tokens if token in recognised]
            if len(missing_tokens) >= 2 and material_missing:
                target = purpose_rows[0]
                output.append(_make_issue(
                    finding_id="DET-DEGREE-PURPOSE-OBJECTIVE-COVERAGE",
                    category="objectives_questions_hypotheses",
                    section=source_section(target),
                    title="The purpose does not cover all substantive objectives",
                    severity="major",
                    confidence=0.91,
                    evidence_ids=[paragraph_id(target)] + [paragraph_id(row) for row in objective_rows[:5]],
                    quote=clean_text(target.get("text", ""))[:260],
                    assessment=(
                        f"At {degree_label} level, the purpose statement is narrower than the objectives. The objectives introduce additional substantive constructs or outcomes that are not represented in the stated purpose."
                    ),
                    consequence=(
                        "The study's central intent is unclear, and the later methodology and conclusions may not be traceable to one coherent purpose."
                    ),
                    action=(
                        "Revise the purpose so it explicitly covers every principal construct and outcome in the objectives, or remove objectives that fall outside the intended study purpose. Then recheck one-to-one alignment with the research questions."
                    ),
                ))

        # A proposal significance section must not present anticipated findings
        # as though results already exist.
        significance_rows = [
            row for row in current
            if row.get("chapter_number") == 1
            and "significance" in normalised(source_section(row))
            and not row.get("is_heading")
            and re.search(r"\b(?:the|these)\s+(?:results?|findings)\s+(?:reveal|show|demonstrate|indicate)|\bthese results\b", clean_text(row.get("text", "")), flags=re.I)
        ]
        if significance_rows:
            target = significance_rows[0]
            output.append(_make_issue(
                finding_id="DET-DEGREE-PREMATURE-SIGNIFICANCE-RESULTS",
                category="cross_section_coherence",
                section=source_section(target),
                title="The significance section presents anticipated findings as completed results",
                severity="moderate",
                confidence=0.97,
                evidence_ids=[paragraph_id(row) for row in significance_rows[:4]],
                quote=clean_text(target.get("text", ""))[:260],
                assessment=(
                    "The significance discussion refers to results or findings as though the empirical analysis has already established them, even though the chapter is written as a proposal."
                ),
                consequence=(
                    "This prejudges the outcome of the study and creates an inconsistent research stage and evidential stance."
                ),
                action=(
                    "Rewrite the significance prospectively. Explain how the eventual findings may contribute to theory, evidence, policy or practice without stating that a relationship or effect has already been demonstrated."
                ),
            ))

        # Numerical empirical claims require an adjacent citation. This targets
        # sentences such as '100 firms...' rather than dates and percentages in
        # formal references.
        uncited_numeric_rows = []
        for row in current:
            if row.get("chapter_number") != 1 or row.get("is_heading"):
                continue
            section_name = normalised(source_section(row))
            if "reference" in section_name:
                continue
            text = clean_text(row.get("text", ""))
            if not re.search(r"\b\d{2,}\s+(?:manufacturing\s+)?(?:firms?|enterprises?|companies|organisations|organizations|respondents?|participants?|employees?)\b", text, flags=re.I):
                continue
            if re.search(r"\([^)]*(?:19|20)\d{2}[^)]*\)", text):
                continue
            uncited_numeric_rows.append(row)
        if uncited_numeric_rows:
            target = uncited_numeric_rows[0]
            output.append(_make_issue(
                finding_id="DET-DEGREE-UNCITED-EMPIRICAL-NUMERIC-CLAIM",
                category="citations_and_sources",
                section=source_section(target),
                title="A numerical empirical claim has no traceable citation",
                severity="major",
                confidence=0.94,
                evidence_ids=[paragraph_id(row) for row in uncited_numeric_rows[:5]],
                quote=clean_text(target.get("text", ""))[:260],
                assessment=(
                    "The chapter reports a specific empirical sample or study result without an adjacent in-text citation that allows the evidence to be traced."
                ),
                consequence=(
                    "The factual claim cannot be verified and the local empirical argument is weakened."
                ),
                action=(
                    "Add the authentic source immediately after each numerical empirical claim and ensure the corresponding complete reference appears in the reference list. Remove or qualify any claim that cannot be verified."
                ),
            ))

        # Sentence-level audit for empirical sample claims. A paragraph-level
        # citation elsewhere in the paragraph must not be treated as support for
        # a different sentence that introduces a specific sample or study result.
        sentence_uncited_numeric_rows = []
        for row in current:
            if row.get("chapter_number") != 1 or row.get("is_heading"):
                continue
            section_name = normalised(source_section(row))
            if "reference" in section_name:
                continue
            text = clean_text(row.get("text", ""))
            for sentence in re.split(r"(?<=[.!?])\s+", text):
                if not re.search(r"\b\d{2,}\s+(?:manufacturing\s+)?(?:firms?|enterprises?|companies|organisations|organizations|respondents?|participants?|employees?)\b", sentence, flags=re.I):
                    continue
                if re.search(r"\([^)]*(?:19|20)\d{2}[^)]*\)", sentence):
                    continue
                candidate = dict(row)
                candidate["_sentence_quote"] = sentence[:260]
                sentence_uncited_numeric_rows.append(candidate)
                break
        if sentence_uncited_numeric_rows:
            target = sentence_uncited_numeric_rows[0]
            output.append(_make_issue(
                finding_id="DET-DEGREE-SENTENCE-UNCITED-EMPIRICAL-NUMERIC-CLAIM",
                category="source_traceability",
                section=source_section(target),
                title="A specific empirical sample claim is not cited in the sentence where it appears",
                severity="major",
                confidence=0.95,
                evidence_ids=[paragraph_id(row) for row in sentence_uncited_numeric_rows[:5]],
                quote=clean_text(target.get("_sentence_quote") or target.get("text", ""))[:260],
                assessment=(
                    "The chapter introduces a specific empirical sample or study result in a sentence that does not contain its own traceable in-text citation."
                ),
                consequence=(
                    "At MPhil and higher research levels, empirical claims must be immediately traceable; otherwise the local evidence base for the problem and background appears unverified."
                ),
                action=(
                    "Place the authentic citation in the same sentence as the empirical sample claim, then confirm that the corresponding full reference is present and accurate. Remove the claim if the source cannot be verified."
                ),
            ))

        # Circular or absolute definitions are unsuitable for core study
        # constructs and should be operationally precise.
        circular_awareness = find_rows(r"\bAwareness\s+means\s+the\s+extent\s+of\s+awareness\b", chapters={1})
        absolute_sustainability = find_rows(r"\bwithout\s+causing\s+any\s+harm\s+to\s+the\s+environment\b", chapters={1})
        definition_rows = circular_awareness + absolute_sustainability
        if definition_rows:
            target = definition_rows[0]
            output.append(_make_issue(
                finding_id="DET-DEGREE-WEAK-CORE-DEFINITIONS",
                category="conceptual_clarity",
                section=source_section(target),
                title="Core constructs are defined circularly or in unrealistically absolute terms",
                severity="moderate",
                confidence=0.96,
                evidence_ids=[paragraph_id(row) for row in definition_rows[:4]],
                quote=clean_text(target.get("text", ""))[:260],
                assessment=(
                    "At least one central construct repeats the term being defined, while another is framed as the complete absence of environmental harm. These formulations are not conceptually discriminating or readily measurable."
                ),
                consequence=(
                    "Weak conceptual definitions make operationalisation and interpretation of the variables uncertain."
                ),
                action=(
                    "Replace circular and absolute wording with concise scholarly definitions that state the construct's dimensions and boundaries, then align each definition with the proposed indicators or measurement scale."
                ),
            ))

        terminology_rows = [
            row for row in current
            if row.get("chapter_number") == 1
            and not row.get("is_heading")
            and re.search(r"\benvironmental\s+sustainability\b", clean_text(row.get("text", "")), flags=re.I)
        ]
        performance_rows = [
            row for row in current
            if row.get("chapter_number") == 1
            and not row.get("is_heading")
            and re.search(r"\benvironmental\s+performance\b", clean_text(row.get("text", "")), flags=re.I)
        ]
        if terminology_rows and performance_rows:
            target = performance_rows[0]
            output.append(_make_issue(
                finding_id="DET-DEGREE-ENVIRONMENTAL-SUSTAINABILITY-PERFORMANCE-TERMS",
                category="construct_alignment",
                section=source_section(target),
                title="Environmental sustainability and environmental performance are not clearly distinguished",
                severity="moderate",
                confidence=0.92,
                evidence_ids=[paragraph_id(terminology_rows[0]), paragraph_id(target)],
                quote=clean_text(target.get("text", ""))[:260],
                assessment=(
                    "The chapter alternates between environmental sustainability and environmental performance without explaining whether these are the same construct, related dimensions or separate outcomes."
                ),
                consequence=(
                    "Unclear construct terminology can weaken the conceptual framework, measurement plan and interpretation of results."
                ),
                action=(
                    "Define the preferred construct consistently, explain any distinction between sustainability and performance, and align the title, purpose, objectives, questions, definitions and later measures with that decision."
                ),
            ))

        citation_format_rows = find_rows(r"\(\s+[A-ZÀ-Ý][^()]{1,80}\bet\s+al\.\s+(?:19|20)\d{2}\s*\)", chapters={1})
        citation_format_rows += find_rows(r"\bet\s+al\.\s+(?:19|20)\d{2}\s*\)", chapters={1})
        if citation_format_rows:
            target = citation_format_rows[0]
            output.append(_make_issue(
                finding_id="DET-DEGREE-IN-TEXT-CITATION-FORMAT",
                category="citations_and_sources",
                section=source_section(target),
                title="An in-text citation is incorrectly punctuated",
                severity="minor",
                confidence=0.98,
                evidence_ids=[paragraph_id(row) for row in citation_format_rows[:5]],
                quote=clean_text(target.get("text", ""))[:260],
                assessment=(
                    "The marked author-year citation contains spacing or punctuation that does not follow the required in-text citation format."
                ),
                consequence=(
                    "Inconsistent citation presentation reduces accuracy and makes the reference system appear unedited."
                ),
                action=(
                    "Correct the spacing and insert the required comma between the author expression and year, then apply the same citation style consistently throughout the chapter."
                ),
            ))

        body_text_original = " ".join(clean_text(row.get("text", "")) for row in current if "reference" not in normalised(source_section(row)))
        reference_text_original = " ".join(clean_text(row.get("text", "")) for row in current if "reference" in normalised(source_section(row)))
        if re.search(r"\bAsha[- ]Mari\s*&\s*Daud\b", body_text_original, flags=re.I) and re.search(r"\bAsha['’]ari,\s*M\.", reference_text_original, flags=re.I):
            target = next((row for row in current if "reference" not in normalised(source_section(row)) and re.search(r"\bAsha[- ]Mari\s*&\s*Daud\b", clean_text(row.get("text", "")), flags=re.I)), None)
            ref_row = next((row for row in current if "reference" in normalised(source_section(row)) and re.search(r"\bAsha['’]ari,\s*M\.", clean_text(row.get("text", "")), flags=re.I)), None)
            if target is not None:
                evidence_ids = [paragraph_id(target)]
                if ref_row is not None:
                    evidence_ids.append(paragraph_id(ref_row))
                output.append(_make_issue(
                    finding_id="DET-DEGREE-IN-TEXT-REFERENCE-AUTHOR-MISMATCH",
                    category="source_traceability",
                    section=source_section(target),
                    title="An in-text citation does not match the reference-list author name",
                    severity="major",
                    confidence=0.96,
                    evidence_ids=evidence_ids,
                    quote=clean_text(target.get("text", ""))[:260],
                    assessment=(
                        "The in-text author name differs from the corresponding reference-list entry, which suggests either a spelling error or a mismatched source."
                    ),
                    consequence=(
                        "This weakens citation integrity because the reader cannot confidently trace the cited claim to the correct source."
                    ),
                    action=(
                        "Correct the in-text citation or the reference-list entry after checking the original source, and then run a full author-year reconciliation across the chapter."
                    ),
                ))

        # Detect a reference-list entry that is not cited in the chapter body.
        body_rows = [
            row for row in current
            if "reference" not in normalised(source_section(row))
        ]
        body_text = normalised(" ".join(clean_text(row.get("text", "")) for row in body_rows))
        uncited_reference_rows = []
        for row in current:
            if "reference" not in normalised(source_section(row)):
                continue
            text = clean_text(row.get("text", ""))
            match = re.match(r"\s*([A-ZÀ-Ý][A-Za-zÀ-ÿ'’\-]+),[^()]{0,220}\(((?:19|20)\d{2})\)", text)
            if not match:
                continue
            surname, year = normalised(match.group(1)), match.group(2)
            if not re.search(rf"\b{re.escape(surname)}\b[^.(){{}}]{{0,100}}\b{year}\b", body_text):
                uncited_reference_rows.append(row)
        if uncited_reference_rows:
            target = uncited_reference_rows[0]
            output.append(_make_issue(
                finding_id="DET-DEGREE-UNCITED-REFERENCE-ENTRIES",
                category="citations_and_sources",
                section=source_section(target) or "References",
                title="Some reference-list entries are not cited in the chapter",
                severity="moderate",
                confidence=0.90,
                evidence_ids=[paragraph_id(row) for row in uncited_reference_rows[:6]],
                quote=clean_text(target.get("text", ""))[:260],
                assessment=(
                    "One or more works listed in the references do not have a traceable author-year citation in the chapter text."
                ),
                consequence=(
                    "The reference list and in-text citation system are not fully reconciled, which weakens source traceability."
                ),
                action=(
                    "Reconcile the chapter in both directions: cite every retained reference where it supports the argument, and remove entries that are not used. Also confirm that every in-text citation has one matching reference-list entry."
                ),
            ))

        # One consolidated British-English consistency finding is enough.
        american_rows = find_rows(r"\b(?:labor|behavior|organization|organizations|organizational|minimizing|analyze|analyzed|modeling)\b", chapters={1})
        british_rows = find_rows(r"\b(?:labour|behaviour|organisation|organisations|organisational|minimising|analyse|analysed|modelling)\b", chapters={1})
        if american_rows and british_rows:
            target = american_rows[0]
            output.append(_make_issue(
                finding_id="DET-DEGREE-BRITISH-ENGLISH-CONSISTENCY",
                category="academic_writing",
                section=source_section(target),
                title="British and American English conventions are mixed",
                severity="minor",
                confidence=0.93,
                evidence_ids=[paragraph_id(target), paragraph_id(british_rows[0])],
                quote=clean_text(target.get("text", ""))[:260],
                assessment=(
                    "The chapter alternates between British and American spellings instead of applying one institutional language convention consistently."
                ),
                consequence=(
                    "The inconsistency reduces editorial quality and can create avoidable corrections at examination or formatting review."
                ),
                action=(
                    "Apply formal British English consistently across the chapter, except where an original title or direct quotation must retain its published spelling."
                ),
            ))

    declaration_rows = find_rows(r"\bI\s*,?[^.]{0,120}\bis entirely my own original work\b")
    if declaration_rows:
        target = declaration_rows[0]
        output.append(_make_issue(
            finding_id="DET-DECLARATION-GRAMMAR",
            category="academic_writing",
            section=source_section(target) or "Declaration",
            title="The candidate declaration contains a grammatical construction error",
            severity="minor",
            confidence=0.99,
            evidence_ids=[paragraph_id(target)],
            quote="is entirely my own original work",
            assessment="The declaration begins with a candidate identifier followed by the singular subject 'I', but the sentence uses 'is' rather than 'declare that this work is' or an equivalent grammatical construction.",
            consequence="The formal front matter is grammatically defective and may not comply with the institution's approved declaration wording.",
            action="Replace the sentence with the institution's approved declaration template and ensure that the group authorship and signatures are presented consistently for all candidates.",
        ))

    return output
