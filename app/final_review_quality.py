from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from .comment_quality import sanitise_finding_rows
from .document_parser import clean_text, normalised
from .finding_order import chapter_number, order_and_number_rows, primary_evidence
from .student_friendly_review import make_finding_student_friendly
from .human_supervisory_editor import edit_findings_for_human_review


_LEVEL_SENTENCE_RE = re.compile(
    r"(?:^|(?<=[.!?])\s+)At\s+(?:PhD|MPhil|Professional Doctorate|professional doctorate|"
    r"Master(?:'s|s)|non-research Master(?:'s|s)|Bachelor(?:'s|s))\s+level,\s*[^.!?]+[.!?]",
    flags=re.I,
)

_EQUIVALENT_SECTIONS = {
    "definition of terms": {
        "definition of terms", "definition of key terms", "definition of key concepts",
        "operational definitions", "operational definition of terms",
    },
    "limitations of the study": {
        "limitations of the study", "limitations", "study limitations", "limitations and delimitations",
    },
    "references": {"references", "reference list", "bibliography", "works cited"},
    "organisation of the study": {"organisation of the study", "organization of the study", "organisation of the thesis", "organization of the thesis"},
    "research questions": {"research questions", "research question"},
    # A general/main objective does not replace the distinct Purpose/Aim
    # section required in the UCC Chapter One structure.
    "purpose of the study": {"purpose of the study", "aim of the study", "general aim"},
    "research objectives": {"research objectives", "objectives of the study", "general objective", "main objective", "specific objectives"},
    "research hypotheses": {"research hypotheses", "research hypothesis", "hypotheses", "hypothesis"},
    "delimitations of the study": {"delimitations of the study", "delimitation of the study", "scope and delimitations of the study", "scope and delimitation of the study", "scope of the study"},
    "chapter summary": {"chapter summary", "summary of the chapter", "chapter conclusion"},
}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _norm(value: Any) -> str:
    return normalised(_clean(value))


def _unique_sentences(*values: Any, limit: int = 5) -> str:
    output: List[str] = []
    seen = set()
    for value in values:
        text = _clean(value)
        if not text:
            continue
        parts = re.split(r"(?<=[.!?])\s+", text)
        for part in parts:
            sentence = _clean(part).strip(" ;")
            key = _norm(sentence)
            if not sentence or not key or key in seen:
                continue
            if any(SequenceMatcher(None, key, existing).ratio() >= 0.88 for existing in seen):
                continue
            seen.add(key)
            if sentence[-1:] not in ".!?":
                sentence += "."
            output.append(sentence)
            if len(output) >= limit:
                return " ".join(output)
    return " ".join(output)


def _manifest_headings(review: Dict[str, Any]) -> List[str]:
    manifest = (review.get("summary") or {}).get("supervisory_document_manifest") or {}
    headings = list(manifest.get("exact_section_and_subsection_headings") or [])
    for section in review.get("academic_section_reviews") or []:
        heading = _clean(section.get("heading") or section.get("section_name"))
        if heading:
            headings.append(heading)
    return list(dict.fromkeys(headings))


def _section_exists(label: str, headings: Sequence[str]) -> bool:
    key = _norm(label)
    equivalents = _EQUIVALENT_SECTIONS.get(key, {key})
    heading_keys = {_norm(value) for value in headings if _norm(value)}
    for equivalent in equivalents:
        eq = _norm(equivalent)
        if eq in heading_keys:
            return True
        if any(eq == heading or eq in heading or heading in eq for heading in heading_keys):
            return True
    return False


def _missing_section_claim(row: Dict[str, Any]) -> str:
    # ``section_contract_label`` is also present for sections classified as
    # PRESENT_BUT_INADEQUATE. Treat it as a missing-section label only when the
    # contract explicitly says the section is missing.
    explicit = _clean(row.get("missing_section_label"))
    if explicit:
        return explicit
    if _norm(row.get("section_status")) == "missing":
        explicit = _clean(row.get("section_contract_label"))
        if explicit:
            return explicit
    text = _clean(" ".join(_clean(row.get(field)) for field in (
        "item", "issue_title", "comment", "assessment", "required_action", "section", "section_reference"
    )))
    low = _norm(text)
    if not any(term in low for term in (
        "is missing", "missing from", "not evident", "is absent", "no reference list", "references section is missing",
    )):
        return ""
    for canonical, equivalents in _EQUIVALENT_SECTIONS.items():
        if any(_norm(value) in low for value in equivalents | {canonical}):
            return canonical
    match = re.search(r"(?:expected|required)?\s*([A-Z][A-Za-z /&-]{3,60}?)\s+(?:is missing|is not evident|is absent)", text)
    return _clean(match.group(1)) if match else ""


def _is_brevity_only_false_positive(row: Dict[str, Any]) -> bool:
    section = _norm(row.get("section_reference") or row.get("section"))
    text = _norm(" ".join(_clean(row.get(field)) for field in (
        "item", "issue_title", "comment", "assessment", "required_action"
    )))
    if not any(term in section for term in ("purpose of the study", "research question", "research objectives", "hypotheses")):
        return False
    brevity = any(term in text for term in (
        "too brief to perform its purpose", "section needs further development", "expand the purpose", "expand the research questions",
    ))
    concrete = any(term in text for term in (
        "misalign", "does not match", "inconsistent", "omits", "missing objective", "duplicate", "causal", "construct", "population", "setting", "scope",
    ))
    return brevity and not concrete


def _derive_section_label(row: Dict[str, Any]) -> str:
    evidence = primary_evidence(row)
    number = _clean(evidence.get("table_number"))
    title = _clean(evidence.get("table_title"))
    if number or title:
        table_label = f"Table {number}" if number else "Table"
        if title:
            table_label += f": {title}"
        section_candidates: List[str] = []
        section_candidates.extend([
            _clean(row.get("section_reference")),
            _clean(row.get("section")),
            _clean(evidence.get("heading")),
            _clean(evidence.get("section_reference")),
        ])
        section_candidates.extend(
            _clean(value) for value in reversed(evidence.get("section_path") or [])
        )
        section = next((
            value for value in section_candidates
            if value
            and not _norm(value).startswith("table ")
            and not re.fullmatch(r"chapter\s+(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+)", _norm(value))
            and _norm(value) != _norm(table_label)
        ), "")
        return f"{section}, {table_label}" if section else table_label
    path = [_clean(value) for value in evidence.get("section_path") or [] if _clean(value)]
    if path:
        for value in reversed(path):
            if not re.fullmatch(r"chapter\s+(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+)", _norm(value)):
                return value
    return _clean(evidence.get("section_reference") or evidence.get("heading") or row.get("section_reference") or row.get("section"))


def _strip_mechanical_language(value: Any) -> str:
    text = _clean(value)
    if not text:
        return ""
    text = _LEVEL_SENTENCE_RE.sub(" ", text)
    replacements = (
        (r"\bevery conclusion should be traceable to the correct table, estimate, uncertainty measure, diagnostic evidence and decision rule\b", "each conclusion must agree with the relevant table, estimate, uncertainty measure, diagnostic evidence and decision rule"),
        (r"\bshould be traceable to\b", "should be clearly linked to"),
        (r"\bmust be traceable to\b", "must be clearly linked to"),
        (r"\bmake each one traceable\b", "show the connection for each one"),
        (r"\bclear and traceable research logic\b", "clear and coherent research logic"),
        (r"\btraceability of the research methods\b", "clarity and reproducibility of the research methods"),
        (r"\bsource traceability\b", "source support"),
        (r"\bmethodological traceability\b", "method clarity and reproducibility"),
        (r"\bresearch-method traceability\b", "method clarity and reproducibility"),
        (r"\btraceability of (?:the )?methods?\b", "clarity and reproducibility of the methods"),
        (r"\btraceability\b", "clear connection"),
        (r"\btraceable scholarly contribution\b", "clearly supported scholarly contribution"),
        (r"\btraceable\b", "clearly supported"),
        (r"\bthe reader should be able to trace the point across the chapters without having to infer the connection\b", "the link across the relevant chapters should be stated directly"),
        (r"\baudit trail from objective to analysis, result, hypothesis decision and conclusion\b", "connection from the objective to the analysis, result, hypothesis decision and conclusion"),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.I)
    text = re.sub(r"\bAt (?:PhD|MPhil|Professional Doctorate|professional doctorate|Master(?:'s|s)|Bachelor(?:'s|s)) level,\s*", "", text, flags=re.I)
    text = re.sub(r"\b(?:at|for) (?:PhD|MPhil|Professional Doctorate|professional doctorate|Master(?:'s|s)|non-research Master(?:'s|s)|Bachelor(?:'s|s)) level\b", "", text, flags=re.I)
    text = re.sub(r"\b(?:PhD|MPhil|professional doctorate|Master(?:'s|s)|Bachelor(?:'s|s))-level\b", "", text, flags=re.I)
    text = re.sub(r"\s{2,}", " ", text).strip(" ,;:")
    if text and text[-1] not in ".!?":
        text += "."
    return text


def _is_chapter_one_background(row: Dict[str, Any]) -> bool:
    return chapter_number(row) == 1 and "background" in _norm(_derive_section_label(row))


def _rewrite_chapter_one_background_synthesis(row: Dict[str, Any]) -> Dict[str, Any]:
    if not _is_chapter_one_background(row):
        return row
    combined = _norm(" ".join(_clean(row.get(field)) for field in (
        "item", "issue_title", "comment", "assessment", "academic_consequence", "required_action"
    )))
    deep_synthesis_language = any(term in combined for term in (
        "compare evidence", "differences in method and context", "critically synthes", "deep synthesis", "study by study", "contradictory evidence",
    ))
    if not deep_synthesis_language:
        return row
    # Keep specific defects such as unsupported statistics or causal overstatement.
    if any(term in combined for term in (
        "unsupported", "causal", "bidirectional", "incorrect", "inconsistent", "unverified statistic", "source", "citation",
    )):
        return row
    output = dict(row)
    output["item"] = output["issue_title"] = "The background needs a clearer evidence-led progression"
    output["comment"] = output["assessment"] = (
        "The background contains relevant literature, but the evidence should be used selectively to introduce the main constructs, move from the wider context to Ghanaian Colleges of Education, and lead directly to the unresolved problem. Chapter One does not require the full study-by-study critical synthesis expected in Chapter Two."
    )
    output["academic_consequence"] = (
        "Without a clear progression, the chapter becomes lengthy while the reason for the study remains difficult to identify."
    )
    output["required_action"] = (
        "Retain only the theory and empirical evidence needed to establish the context, significance and gap. Reserve detailed comparison of research designs, methods, conflicting findings and limitations for Chapter Two."
    )
    terms = [value for value in output.get("study_terms") or [] if _clean(value)]
    if terms:
        output["illustrative_guidance"] = (
            f"organise the background around {_join_terms(terms[:4])}, then end with the precise issue that remains unresolved among the study population"
        )
    return output


def _join_terms(terms: Sequence[str]) -> str:
    values = [_clean(value) for value in terms if _clean(value)]
    if not values:
        return "the main constructs"
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return ", ".join(values[:-1]) + f", and {values[-1]}"


def _study_terms(review: Dict[str, Any]) -> List[str]:
    """Return a short, clean set of constructs and the confirmed setting.

    Examples sound human only when they use stable study entities rather than
    n-grams assembled from nearby prose. Title and purpose statements therefore
    take precedence. Repeated phrases are used only when no usable study focus
    can be recovered from those sources.
    """
    context = review.get("study_context") or {}
    title = _clean(context.get("title_or_opening_focus") or (review.get("summary") or {}).get("study_title"))
    primary_candidates: List[str] = []
    fallback_candidates: List[str] = []

    patterns = (
        r"(?:effect|influence|impact|relationship)\s+of\s+(.+?)\s+on\s+(.+?)(?:\s+among|\s+in\s+|\s*:|$)",
        r"moderating\s+role\s+of\s+(.+?)(?:\s+among|\s+in\s+|\s*:|$)",
        r"relationship\s+between\s+(.+?)\s+and\s+(.+?)(?:\s+among|\s+in\s+|\s*:|$)",
        r"(?:purpose|aim)\s+of\s+(?:this|the)\s+study\s+(?:is|was)\s+to\s+(?:examine|assess|investigate|determine|explore)\s+(.+?)(?:[.;]|$)",
    )

    setting_suffix = re.compile(
        r"^(.+?)\s+(?:at|within)\s+((?:the\s+)?[A-Z][A-Za-z0-9&'’. -]{3,100}?(?:Bank|PLC|University|College|School|Hospital|Assembly|Company|Municipality|District|Region))$",
        flags=re.I,
    )

    def add_candidate(value: Any, target: List[str]) -> None:
        candidate = _clean(value).strip(" ,:-.")
        if not candidate:
            return
        match = setting_suffix.match(candidate)
        if match:
            target.append(_clean(match.group(1)))
            target.append(_clean(match.group(2)))
        else:
            target.append(candidate)

    for pattern in patterns:
        for match in re.finditer(pattern, title, flags=re.I):
            for value in match.groups():
                add_candidate(value, primary_candidates)

    # When a chapter is reviewed without its title page, recover the study focus
    # from the purpose, objectives and problem statement. Do not use research-
    # question lead-ins or other linking phrases as study entities.
    runtime_rows = ((review.get("_runtime_context") or {}).get("current_paragraphs") or [])
    focus_text = " ".join(
        _clean(row.get("text")) for row in runtime_rows
        if int(row.get("chapter_number") or 0) in {0, 1}
        and any(token in _norm(row.get("heading") or row.get("section_reference") or "") for token in (
            "title", "purpose", "objective", "background", "problem"
        ))
    )
    for pattern in patterns:
        for match in re.finditer(pattern, focus_text, flags=re.I):
            for value in match.groups():
                add_candidate(value, fallback_candidates)

    # Phrase recovery is a last resort only. It must never override clear title
    # constructs with accidental combinations such as "internal controls fraud".
    if not primary_candidates and not fallback_candidates:
        words = re.findall(r"[A-Za-z][A-Za-z'’-]{2,}", focus_text[:30000])
        stop = {
            "effect", "influence", "impact", "relationship", "among", "role", "moderating",
            "ghana", "ghanaian", "study", "teachers", "students", "pre", "service", "attempts",
            "respond", "following", "questions", "chapter", "research", "findings", "purpose",
            "objective", "objectives", "commercial", "rural", "specifically", "general",
        }
        phrase_counts: Dict[str, int] = {}
        for size in (3, 2):
            for idx in range(len(words) - size + 1):
                phrase_words = words[idx:idx + size]
                if any(word.lower() in stop for word in phrase_words):
                    continue
                phrase = " ".join(phrase_words)
                phrase_counts[phrase] = phrase_counts.get(phrase, 0) + 1
        for phrase, count in sorted(phrase_counts.items(), key=lambda item: (-item[1], -len(item[0]))):
            if count >= 2:
                fallback_candidates.append(phrase)

    # A clear title normally supplies the predictor, outcome and setting. Only
    # supplement it from Chapter One when the title did not provide enough.
    candidates = list(primary_candidates)
    if len(candidates) < 3:
        candidates.extend(fallback_candidates)
    output: List[str] = []
    seen = set()
    reject = {
        "the banking", "detection and", "fraudulent activities", "the study", "the banking sector",
        "control systems", "internal controls fraud", "banking organizations", "financial system",
    }
    for candidate in candidates:
        candidate = re.sub(r"\b(?:Ghana|Ghanaian|Colleges? of Education|pre-service teachers?)\b", "", candidate, flags=re.I)
        candidate = re.sub(r"^(?:the|a|an)\s+", "", _clean(candidate), flags=re.I).strip(" ,:-")
        words_in_candidate = candidate.lower().split()
        if not words_in_candidate or words_in_candidate[-1] in {"and", "or", "the", "of", "in", "at"}:
            continue
        key = _norm(candidate)
        if len(candidate) < 5 or not key or key in seen or key in reject:
            continue
        # Reject accidental adjacent-construct n-grams without a connector.
        if re.search(r"\binternal controls? fraud\b", key):
            continue
        replace_index = None
        skip = False
        for idx, old_value in enumerate(output):
            old_key = _norm(old_value)
            similarity = SequenceMatcher(None, key, old_key).ratio()
            if key == old_key or similarity >= 0.82:
                skip = True
                break
            if key in old_key:
                skip = True
                break
            if old_key in key:
                # Keep the longer phrase only when it remains a clean construct.
                if len(candidate.split()) <= 7:
                    replace_index = idx
                else:
                    skip = True
                break
        if skip:
            continue
        if replace_index is not None:
            output[replace_index] = candidate
        else:
            output.append(candidate)
        seen.add(key)
        if len(output) >= 4:
            break
    return output


def _issue_family(row: Dict[str, Any]) -> str:
    text = _norm(" ".join(_clean(row.get(field)) for field in (
        "category", "item", "issue_title", "comment", "assessment", "required_action"
    )))
    if _missing_section_claim(row):
        return "missing_section"
    if any(term in text for term in ("regression", "anova", "coefficient", "r squared", "f statistic", "t statistic", "p value", "moderation", "mediation", "process", "sem", "statistical")):
        return "statistical_model"
    if any(term in text for term in ("instrument", "item allocation", "scale", "reliability", "validity", "scoring", "reverse cod", "measurement")):
        return "measurement"
    if any(term in text for term in ("objective", "research question", "hypothesis", "purpose", "alignment")):
        return "alignment"
    if any(term in text for term in ("reference", "citation", "source")):
        return "references"
    if any(term in text for term in ("literature", "theory", "conceptual", "empirical review", "synthesis")):
        return "literature"
    if any(term in text for term in ("method", "design", "sampling", "ethic", "data collection")):
        return "methods"
    if any(term in text for term in ("discussion", "interpretation", "conclusion", "recommendation")):
        return "discussion"
    if any(term in text for term in ("grammar", "language", "spelling", "punctuation", "british english")):
        return "writing"
    return _norm(row.get("category") or "other") or "other"


def _anchor_key(row: Dict[str, Any]) -> Tuple[Any, ...]:
    evidence = primary_evidence(row)
    table_number = _clean(evidence.get("table_number"))
    if table_number:
        return (chapter_number(row), "table", table_number, _issue_family(row))
    return (
        chapter_number(row),
        evidence.get("paragraph"),
        evidence.get("table_index"),
        evidence.get("table_row"),
        _issue_family(row),
    )


def _similarity(left: Dict[str, Any], right: Dict[str, Any]) -> float:
    a = _norm(" ".join(_clean(left.get(field)) for field in ("item", "issue_title", "required_action")))
    b = _norm(" ".join(_clean(right.get(field)) for field in ("item", "issue_title", "required_action")))
    return SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def _severity_rank(value: Any) -> int:
    return {"critical": 0, "major": 1, "moderate": 2, "minor": 3}.get(str(value or "minor").lower(), 9)


def _merge_rows(primary: Dict[str, Any], duplicate: Dict[str, Any]) -> Dict[str, Any]:
    output = dict(primary)
    if _severity_rank(duplicate.get("severity")) < _severity_rank(output.get("severity")):
        output["severity"] = duplicate.get("severity")
    output["confidence"] = max(float(output.get("confidence") or 0), float(duplicate.get("confidence") or 0))
    evidence = list(output.get("evidence") or []) + list(duplicate.get("evidence") or [])
    seen_evidence = set()
    unique_evidence = []
    for item in evidence:
        key = (item.get("paragraph"), item.get("table_index"), item.get("table_row"), _clean(item.get("text"))[:120])
        if key in seen_evidence:
            continue
        seen_evidence.add(key)
        unique_evidence.append(item)
    output["evidence"] = unique_evidence[:12]
    output["evidence_paragraph_ids"] = list(dict.fromkeys(
        list(output.get("evidence_paragraph_ids") or []) + list(duplicate.get("evidence_paragraph_ids") or [])
    ))[:12]
    family = _issue_family(output)
    if family == "statistical_model":
        table_label = _derive_section_label(output)
        output["item"] = output["issue_title"] = f"{table_label} requires correction and complete reporting"
    output["comment"] = output["assessment"] = _unique_sentences(
        output.get("comment") or output.get("assessment"),
        duplicate.get("comment") or duplicate.get("assessment"),
        limit=4,
    )
    output["academic_consequence"] = _unique_sentences(
        output.get("academic_consequence"), duplicate.get("academic_consequence"), limit=2
    )
    output["required_action"] = _unique_sentences(
        output.get("required_action"), duplicate.get("required_action"), limit=4
    )
    if not _clean(output.get("illustrative_guidance")):
        output["illustrative_guidance"] = _clean(duplicate.get("illustrative_guidance"))
    output["requires_original_output"] = bool(output.get("requires_original_output") or duplicate.get("requires_original_output"))
    return output


def _consolidate(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    kept: List[Dict[str, Any]] = []
    positions: Dict[Tuple[Any, ...], List[int]] = {}
    for row in rows:
        key = _anchor_key(row)
        candidates = positions.setdefault(key, [])
        merged = False
        for index in candidates:
            existing = kept[index]
            same_table_stats = key[1:2] == ("table",) and _issue_family(row) == "statistical_model"
            if same_table_stats or _similarity(existing, row) >= 0.48:
                kept[index] = _merge_rows(existing, row)
                merged = True
                break
        if not merged:
            candidates.append(len(kept))
            kept.append(row)
    return kept


def _attach_runtime_evidence(row: Dict[str, Any], review: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve deterministic section-contract paragraph IDs to full evidence.

    AI-generated findings normally arrive with an evidence list. Deterministic
    section-contract findings may carry only IDs such as ``P24``. Resolving them
    here keeps missing and inadequate-section comments anchored and actionable
    even when the AI stage does not enrich them first.
    """
    output = dict(row)
    if not _clean(output.get("status")):
        if output.get("section_contract_verified"):
            status = _norm(output.get("section_status"))
            output["status"] = "does_not_meet_requirement" if status == "missing" else "partly_meets_requirement"
        elif any(_clean(output.get(field)) for field in ("item", "issue_title", "comment", "assessment", "required_action")):
            output["status"] = (
                "does_not_meet_requirement"
                if _norm(output.get("severity")) in {"critical", "major"}
                else "partly_meets_requirement"
            )
        output.setdefault("annotation_eligible", True)
    if output.get("evidence"):
        return output
    ids = {_clean(value) for value in output.get("evidence_paragraph_ids") or [] if _clean(value)}
    if not ids:
        return output
    runtime_rows = ((review.get("_runtime_context") or {}).get("current_paragraphs") or [])
    evidence = []
    for source in runtime_rows:
        paragraph = source.get("paragraph")
        source_ids = {
            _clean(source.get("paragraph_id")),
            _clean(source.get("id")),
            f"P{paragraph}" if paragraph is not None else "",
        }
        if ids.intersection(source_ids):
            evidence.append({**source, "document_role": "current"})
    if evidence:
        output["evidence"] = evidence[:12]
        output.setdefault("problematic_quote", _clean(evidence[0].get("text"))[:280])
    return output


def _polish_row(row: Dict[str, Any], review: Dict[str, Any], terms: Sequence[str]) -> Dict[str, Any] | None:
    output = dict(row)
    output["study_terms"] = list(terms)
    missing = _missing_section_claim(output)
    headings = _manifest_headings(review)
    verified_missing = bool(
        output.get("section_contract_verified")
        and _norm(output.get("section_status")) == "missing"
    )
    if missing and not verified_missing and _section_exists(missing, headings):
        return None
    if _is_brevity_only_false_positive(output):
        return None

    output = _rewrite_chapter_one_background_synthesis(output)
    label = _derive_section_label(output)
    if label:
        output["section"] = label
        output["section_reference"] = label
        output["reference_label"] = label
    evidence = primary_evidence(output)
    if evidence.get("table_number") or evidence.get("table_title"):
        number = _clean(evidence.get("table_number"))
        title = _clean(evidence.get("table_title"))
        table_reference = f"Table {number}" if number else "Table"
        if title:
            table_reference += f": {title}"
        output["table_reference"] = table_reference

    for field in (
        "comment", "assessment", "academic_consequence", "required_action", "illustrative_guidance",
    ):
        output[field] = _strip_mechanical_language(output.get(field))
    for field in ("item", "issue_title", "section", "section_reference", "reference_label"):
        output[field] = _strip_mechanical_language(output.get(field)).rstrip(" .:;,-")

    # A context-specific example is useful only when it contains a current-study
    # construct or a concrete, safe procedural correction.
    example = _clean(output.get("illustrative_guidance"))
    if example and terms:
        ex_norm = _norm(example)
        if not any(_norm(term) in ex_norm for term in terms) and not any(term in ex_norm for term in (
            "coefficient", "standard error", "confidence interval", "objective", "research question", "reference list", "original output",
        )):
            output["illustrative_guidance"] = ""
    return output


def _raw_rows(review: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for source_key in ("academic_findings", "alignment_results", "revision_results"):
        for source in review.get(source_key) or []:
            status = str(source.get("status") or "").strip().lower()
            if status in {"meets_requirement", "not_applicable", "addressed"}:
                continue
            if not any(_clean(source.get(field)) for field in (
                "item", "issue_title", "comment", "assessment", "required_action"
            )):
                continue
            row = dict(source)
            row.setdefault("finding_source", source_key)
            rows.append(row)
    return rows


def build_canonical_finding_rows(review: Dict[str, Any], *, force: bool = False) -> List[Dict[str, Any]]:
    if not force and review.get("canonical_findings"):
        return [dict(row) for row in review.get("canonical_findings") or []]
    level = (review.get("summary") or {}).get("academic_level")
    terms = _study_terms(review)
    polished: List[Dict[str, Any]] = []
    for row in _raw_rows(review):
        row = _attach_runtime_evidence(row, review)
        row = make_finding_student_friendly(row, level)
        row = _polish_row(row, review, terms)
        if row is not None:
            polished.append(row)
    polished = sanitise_finding_rows(polished)
    polished = _consolidate(polished)
    # A final human-supervisor editorial pass consolidates repeated root causes,
    # removes irrelevant examples, adds conservative context checks and prepares
    # one natural student-facing comment for each retained issue.
    polished = edit_findings_for_human_review(polished, review, terms)
    # Re-sanitise after every consolidation and editorial transformation, then
    # assign numbers only once, after all filters and merges have completed.
    polished = sanitise_finding_rows(polished)
    numbered = order_and_number_rows(polished)
    for row in numbered:
        row["canonical_finding"] = True
    review["canonical_findings"] = [dict(row) for row in numbered]
    # Reconcile the source rows for dashboards and any legacy consumers. The
    # canonical ledger remains the source of truth, but matching source records
    # receive the final number so no old model-generated numbers survive.
    by_id = {}
    for row in numbered:
        number = int(row.get("finding_number"))
        identifiers = [_clean(row.get("finding_id"))] + [
            _clean(value) for value in (row.get("merged_finding_ids") or [])
        ]
        for identifier in identifiers:
            if identifier:
                by_id[identifier] = number
    for source_key in ("academic_findings", "alignment_results", "revision_results"):
        for source in review.get(source_key) or []:
            key = _clean(source.get("finding_id"))
            if key and key in by_id:
                source["finding_number"] = by_id[key]
            else:
                source.pop("finding_number", None)
    summary = review.setdefault("summary", {})
    summary["canonical_finding_count"] = len(numbered)
    summary["final_numbering_reconciled"] = [row.get("finding_number") for row in numbered] == list(range(1, len(numbered) + 1))
    return [dict(row) for row in numbered]


def attach_canonical_findings(review: Dict[str, Any]) -> Dict[str, Any]:
    build_canonical_finding_rows(review, force=True)
    return review
