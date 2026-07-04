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
    r"\b(?:write|develop|provide|add|prepare)\s+(?:a\s+|the\s+)?(?:complete|full|entire)\b",
    r"\bcomplete\s+(?:chapter|results?|analysis|discussion|methodology|section)\b",
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
    tables: Dict[int, Dict[str, Any]] = {}

    for row in current:
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
    if len(identities) > 1:
        allowed = {normalised(number) for number, _ in identities}
        if mentioned and any(normalised(value) not in allowed for value in mentioned):
            return False
        return True
    if not identities:
        return True
    number, title = identities[0]
    for field in ("issue_title", "assessment", "academic_consequence", "required_action", "illustrative_guidance"):
        value = clean_text(issue.get(field, ""))
        value = TABLE_REFERENCE_RE.sub(f"Table {number}", value)
        issue[field] = value
    issue["canonical_table_number"] = number
    issue["canonical_table_title"] = title
    return True


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

    dominant_section = _dominant_evidence_section(guarded, paragraph_index)
    if not dominant_section:
        return None
    if is_synthetic_section(clean_text(guarded.get("section", ""))):
        guarded["section"] = dominant_section
    elif normalised(clean_text(guarded.get("section", ""))) not in facts["sections"]:
        guarded["section"] = dominant_section
    _filter_evidence_to_section(guarded, paragraph_index, guarded["section"])
    if not guarded.get("evidence_paragraph_ids"):
        return None

    text = _issue_text(guarded)
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
                    value = re.sub(r"\b(?:write|develop|provide|add|prepare)\s+(?:a\s+|the\s+)?(?:complete|full|entire)\b", "strengthen the", value, flags=re.I)
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


def deterministic_expert_issues(paragraphs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Add high-confidence cross-section checks that should not depend on depth."""
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
