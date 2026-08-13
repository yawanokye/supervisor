from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

from .document_parser import clean_text, normalised
from .supervisory_accuracy_guard import paragraph_id

# Protect common academic abbreviations when locating sentence-level anchors.
_ABBREVIATIONS = {
    "e.g.", "i.e.", "et al.", "fig.", "table.", "no.", "vol.", "pp.",
    "dr.", "prof.", "mr.", "mrs.", "ms.", "vs.", "etc.",
}

_MISSING_REFERENCE_PATTERNS = (
    "reference list is missing",
    "references section is missing",
    "no references or bibliography section",
    "no reference list",
    "references are missing",
)

_QUOTED_RE = re.compile(r"[‘’'\"]([^‘’'\"]{2,120})[‘’'\"]")
_SUCH_AS_RE = re.compile(r"\bsuch as\s+([^.;:]{2,160})", flags=re.I)


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _norm(value: Any) -> str:
    return normalised(_clean(value))


def review_scope_is_complete(summary: Mapping[str, Any]) -> bool:
    scope = _norm(summary.get("review_scope") or summary.get("submission_scope"))
    document_label = _norm(summary.get("document_label"))
    return scope in {"full thesis", "full_thesis", "complete thesis", "complete dissertation", "complete project"} or any(
        phrase in document_label
        for phrase in ("complete thesis", "complete dissertation", "complete project", "full thesis")
    )


def sentence_spans(text: str) -> List[Tuple[int, int]]:
    """Return conservative academic sentence spans without splitting decimals or DOIs."""
    source = str(text or "")
    if not source:
        return []
    spans: List[Tuple[int, int]] = []
    start = 0
    i = 0
    while i < len(source):
        ch = source[i]
        if ch not in ".?!":
            i += 1
            continue
        # Decimal, version number or DOI segment.
        if ch == "." and i > 0 and i + 1 < len(source) and source[i - 1].isdigit() and source[i + 1].isdigit():
            i += 1
            continue
        prefix = source[max(0, i - 20): i + 1]
        if ch == ".":
            abbreviation_match = re.search(r"([A-Za-z]+(?:\s+al)?)\.$", prefix)
            if abbreviation_match:
                abbreviation = abbreviation_match.group(1).lower() + "."
                if abbreviation in _ABBREVIATIONS:
                    i += 1
                    continue
        # Initials and author abbreviations, e.g. J. K. Mensah.
        if ch == "." and i > 0 and source[i - 1].isalpha():
            token_match = re.search(r"([A-Za-z]{1,2})\.$", source[max(0, i - 5): i + 1])
            if token_match:
                token_start = i - len(token_match.group(1))
                preceding = source[token_start - 1] if token_start > 0 else " "
                # A true author initial starts at a token boundary. This avoids
                # treating the C in 1.2°C. as an initial and merging sentences.
                if preceding.isspace() or preceding in "([{'\"":
                    i += 1
                    continue
        j = i + 1
        while j < len(source) and source[j] in "\"'’”)]}":
            j += 1
        if j < len(source) and not source[j].isspace():
            i += 1
            continue
        while j < len(source) and source[j].isspace():
            j += 1
        end = j
        if _clean(source[start:end]):
            spans.append((start, end))
        start = j
        i = j
    if start < len(source) and _clean(source[start:]):
        spans.append((start, len(source)))
    return spans or [(0, len(source))]


def sentence_for_offset(text: str, start: int, end: int) -> Tuple[int, int, str]:
    for sentence_start, sentence_end in sentence_spans(text):
        if sentence_start <= start < sentence_end or (start <= sentence_start and end >= sentence_end):
            return sentence_start, sentence_end, _clean(text[sentence_start:sentence_end])
    return 0, len(text), _clean(text)


def _paragraph_index(paragraphs: Sequence[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    output: Dict[str, Dict[str, Any]] = {}
    for row in paragraphs:
        if row.get("document_role", "current") != "current":
            continue
        pid = paragraph_id(dict(row))
        if pid:
            output[pid] = dict(row)
    return output


def _source_blob(paragraphs: Sequence[Mapping[str, Any]]) -> str:
    return "\n".join(_clean(row.get("text")) for row in paragraphs if row.get("document_role", "current") == "current")


def _drop_scope_false_positive(row: Mapping[str, Any], summary: Mapping[str, Any]) -> bool:
    if review_scope_is_complete(summary):
        return False
    text = _norm(" ".join(_clean(row.get(field)) for field in (
        "issue_title", "item", "assessment", "comment", "required_action", "section", "section_reference"
    )))
    return any(pattern in text for pattern in _MISSING_REFERENCE_PATTERNS)


def _best_evidence_row(row: Mapping[str, Any], index: Mapping[str, Dict[str, Any]]) -> Dict[str, Any] | None:
    ids = [str(value) for value in (row.get("evidence_paragraph_ids") or [])]
    # AI and alignment findings sometimes carry only evidence objects. Resolve
    # those paragraph references before rejecting the finding as ungrounded.
    for evidence in row.get("evidence") or []:
        if not isinstance(evidence, Mapping):
            continue
        for value in (evidence.get("paragraph_id"), evidence.get("paragraph"), evidence.get("id")):
            if value in (None, ""):
                continue
            raw = str(value)
            for candidate in (raw, f"P{raw}", f"p{raw}"):
                if candidate in index and candidate not in ids:
                    ids.append(candidate)
    quote = _clean(row.get("problematic_quote"))
    candidates = [index[pid] for pid in ids if pid in index]
    if quote:
        exact = next((item for item in candidates if quote in _clean(item.get("text"))), None)
        if exact:
            return exact
    return candidates[0] if candidates else None


def _keyword_tokens(row: Mapping[str, Any]) -> List[str]:
    text = _norm(" ".join(_clean(row.get(field)) for field in (
        "issue_title", "item", "assessment", "required_action", "section"
    )))
    stop = {
        "the", "and", "for", "this", "that", "with", "from", "study", "section", "chapter",
        "should", "needs", "need", "required", "action", "student", "work", "research",
    }
    return [token for token in text.split() if len(token) >= 4 and token not in stop][:24]


def _best_grounded_sentence(text: str, row: Mapping[str, Any]) -> Tuple[int, int, str]:
    tokens = set(_keyword_tokens(row))
    best: Tuple[int, int, int, str] | None = None
    for start, end in sentence_spans(text):
        sentence = _clean(text[start:end])
        overlap = len(tokens & set(_norm(sentence).split()))
        score = overlap * 10 + min(len(sentence), 250)
        if best is None or score > best[0]:
            best = (score, start, end, sentence)
    if best:
        return best[1], best[2], best[3]
    return 0, len(text), _clean(text)


_SAFE_NAMED_ENTITIES = {
    "british english", "american english", "chapter one", "chapter two", "chapter three",
    "chapter four", "chapter five", "research question", "research questions",
    "problem statement", "statement of the problem", "system gmm", "difference gmm",
    "ordinary least squares", "structural equation modelling", "structural equation modeling",
    "anova", "sem", "ols", "apa", "word", "excel", "stata", "spss", "r",
    "british", "american",
}


def _contains_ungrounded_named_entity(sentence: str, source_norm: str) -> bool:
    # A comment may use normal academic labels, but it may not introduce a
    # named institution, organisation, country, dataset or case that is absent
    # from the current work. This is the positive grounding rule that prevents
    # previous-study contamination.
    candidates = re.findall(
        r"\b(?:[A-Z][A-Za-z&'’.-]{2,}|[A-Z]{2,})(?:\s+(?:[A-Z][A-Za-z&'’.-]{2,}|[A-Z]{2,})){0,4}\b",
        sentence,
    )
    for candidate in candidates:
        candidate_norm = _norm(candidate)
        if not candidate_norm or candidate_norm in _SAFE_NAMED_ENTITIES:
            continue
        # Ignore the first ordinary word of a sentence. Multiword or all-caps
        # sequences remain subject to the evidence check.
        if sentence.startswith(candidate) and len(candidate.split()) == 1 and not candidate.isupper():
            continue
        if candidate_norm not in source_norm:
            return True
    return False


def _near_source_rewrite(value: str, source_text: str) -> bool:
    candidate = _norm(value)
    if not candidate:
        return False
    for start, end in sentence_spans(source_text):
        source_sentence = _norm(source_text[start:end])
        if not source_sentence:
            continue
        if SequenceMatcher(None, candidate, source_sentence).ratio() >= 0.72:
            return True
        candidate_tokens = set(re.findall(r"[a-z0-9]+", candidate))
        source_tokens = set(re.findall(r"[a-z0-9]+", source_sentence))
        if candidate_tokens and len(candidate_tokens & source_tokens) / len(candidate_tokens) >= 0.78:
            return True
    return False


def _strip_ungrounded_example_sentences(
    value: Any, source_text: str, *, allow_procedural_examples: bool = False,
    allow_corrective_rewrites: bool = False,
) -> str:
    text = _clean(value)
    if not text:
        return ""
    source_norm = _norm(source_text)
    kept: List[str] = []
    for start, end in sentence_spans(text):
        sentence = _clean(text[start:end])
        grounded = True
        for quoted in _QUOTED_RE.findall(sentence):
            # Academic labels and generic category names are not source quotations.
            quoted_norm = _norm(quoted)
            if len(quoted_norm.split()) <= 2 and quoted_norm in {
                "major", "moderate", "minor", "critical", "research questions", "problem statement"
            }:
                continue
            if quoted_norm and quoted_norm not in source_norm:
                if allow_corrective_rewrites and _near_source_rewrite(quoted, source_text):
                    continue
                grounded = False
                break
        if grounded and _contains_ungrounded_named_entity(sentence, source_norm):
            grounded = False
        if grounded:
            match = _SUCH_AS_RE.search(sentence)
            if match and not allow_procedural_examples:
                examples = [
                    _norm(part.strip(" ‘\"'’”"))
                    for part in re.split(r"[/,]|\band\b|\bor\b", match.group(1), flags=re.I)
                    if _norm(part)
                ]
                lexical = [example for example in examples if 1 <= len(example.split()) <= 5]
                if lexical and not all(example in source_norm for example in lexical):
                    grounded = False
        if grounded:
            kept.append(sentence)
    return _clean(" ".join(kept))


def _priority(severity: Any) -> str:
    value = _norm(severity)
    if value in {"critical", "major"}:
        return "Essential before approval"
    if value == "moderate":
        return "Strongly recommended"
    return "Optional refinement"


def _verification(row: Mapping[str, Any]) -> str:
    existing = _clean(row.get("verification_test") or row.get("verification"))
    if existing:
        return existing
    category = _norm(row.get("category"))
    issue = _norm(" ".join(_clean(row.get(field)) for field in ("issue_title", "item", "required_action")))
    if "supervisor" in issue or "editor instruction" in issue or "tracked" in issue:
        return "Open the document with tracked changes visible and confirm that the instruction has been accepted, rejected or removed and that no unresolved editing notes remain in the selected scope."
    if category in {"statistical accuracy", "analysis appropriateness", "measurement and scoring", "results and interpretation"} or any(term in issue for term in ("coefficient", "p value", "regression", "anova", "statistical", "model estimate")):
        return "Re-run or inspect the original analysis, then confirm that the corrected table, statistics, decision rule and narrative interpretation agree exactly."
    if category in {"citations and sources", "reference integrity"} or row.get("source_verification_required") or any(term in issue for term in ("citation", "reference", "source attribution", "bibliographic")):
        if "incomplete" in issue or "unfinished" in issue:
            return "Confirm that the sentence and citation are complete, the year and closing punctuation are present, and the source has a matching reference-list entry."
        return "Check the citation against the original source and the required referencing style, then confirm that the in-text citation and reference-list entry match."
    if category in {"academic writing", "writing", "language"} or any(term in issue for term in ("spelling", "grammar", "subject verb", "punctuation", "british english")):
        return "Search the full selected scope for the same language pattern and confirm that the corrected form is used consistently without altering direct quotations or publication titles."
    if any(term in issue for term in ("causal language", "causal effect", "impact must be justified", "causal wording")):
        return "Confirm that causal terms are retained only where the research design, identification strategy and analysis can support causal inference; otherwise replace them with descriptive or associational wording."
    if category in {"scope", "scope and context"} or any(term in issue for term in ("one firm", "several firms", "unit and scope", "population", "sampling frame", "study setting is not identified")):
        return "Confirm that the same unit of analysis, population and study setting appear consistently in the title, purpose, objectives, questions, scope, limitations and methodology."
    if "limitation" in issue or "delimitation" in issue:
        return "Confirm that the scope or delimitation states the investigator's chosen boundaries, while each limitation is an unavoidable design, data, measurement, sampling or access constraint with a stated implication."
    if category in {"research gap and problem", "problem statement"} or any(term in issue for term in ("research gap", "problem context", "problem statement", "study context")):
        return "Confirm that the revised problem statement presents verified evidence of the practical problem, synthesises the closest studies, states the precise unresolved gap and leads directly to the study purpose."
    if category in {"cross section coherence", "alignment"} or any(term in issue for term in ("purpose", "objective", "research question", "hypothesis", "align")):
        return "Use an alignment table to confirm a one-to-one match among the purpose, each objective, its question or hypothesis, the required data, the analysis and the expected result."
    if category in {"conceptual clarity", "theoretical grounding"} or any(term in issue for term in ("construct", "conceptual", "theoretical", "framework")):
        return "Confirm that each principal construct has one clear definition and is used consistently in the title, background, purpose, objectives, questions and methodology."
    if "significance" in issue or "contribution" in issue:
        return "Confirm that the section states distinct, realistic scholarly, practical and policy contributions that follow from the study's purpose, design and intended evidence."
    return "Confirm that the marked passage directly performs the stated purpose of its section and that the required correction is visible in the revised text."


def evidence_ledger_rows(
    rows: Sequence[Mapping[str, Any]],
    paragraphs: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    """Ground, scope-check and enrich findings before any student-facing export."""
    # Runtime paragraph maps are preferred. Legacy and direct exporter calls
    # may carry the current-document rows only inside each finding's evidence
    # list, so fold those rows into the same evidence index rather than
    # discarding otherwise valid anchored findings.
    effective_paragraphs: List[Mapping[str, Any]] = list(paragraphs)
    known = {paragraph_id(dict(item)) for item in effective_paragraphs if paragraph_id(dict(item))}
    for source_row in rows:
        for evidence in source_row.get("evidence") or []:
            if not isinstance(evidence, Mapping):
                continue
            if evidence.get("document_role", "current") != "current" or not _clean(evidence.get("text")):
                continue
            pid = paragraph_id(dict(evidence))
            if pid and pid not in known:
                effective_paragraphs.append(dict(evidence))
                known.add(pid)
    index = _paragraph_index(effective_paragraphs)
    source_text = _source_blob(effective_paragraphs)
    # The declared study title is valid grounding context even when a direct
    # exporter test or section-only review supplies only one body paragraph.
    # This allows context-specific procedural guidance without importing a
    # named case from another study.
    study_title = _clean(summary.get("study_title") or summary.get("title"))
    if study_title:
        source_text = study_title + "\n" + source_text
    output: List[Dict[str, Any]] = []
    for source_row in rows:
        row: Dict[str, Any] = dict(source_row)
        if _drop_scope_false_positive(row, summary):
            continue
        evidence_row = _best_evidence_row(row, index)
        if evidence_row is None:
            # Verified structural omissions can remain report-only. Other claims
            # without current-document evidence are unsafe for annotation.
            if row.get("section_contract_verified") and _norm(row.get("section_status")) == "missing":
                row["annotation_eligible"] = False
                row["report_only"] = True
                row["action_priority"] = _priority(row.get("severity"))
                row["verification_test"] = _verification(row)
                output.append(row)
            continue

        paragraph_text = _clean(evidence_row.get("text"))
        quote = _clean(row.get("problematic_quote"))
        if quote and quote in paragraph_text:
            start = paragraph_text.find(quote)
            end = start + len(quote)
        else:
            start, end, quote = _best_grounded_sentence(paragraph_text, row)
            row["problematic_quote"] = quote
        sentence_start, sentence_end, exact_sentence = sentence_for_offset(paragraph_text, start, end)
        row["exact_source_text"] = exact_sentence
        row["exact_anchor_paragraph_id"] = paragraph_id(evidence_row)
        row["exact_anchor_paragraph"] = evidence_row.get("paragraph")
        row["exact_anchor_start"] = sentence_start
        row["exact_anchor_end"] = sentence_end
        row["anchor_key"] = f"{row['exact_anchor_paragraph_id']}:{sentence_start}:{sentence_end}"
        row["problematic_quote"] = exact_sentence
        row["evidence_paragraph_ids"] = [row["exact_anchor_paragraph_id"]]
        row["action_priority"] = _priority(row.get("severity"))
        row["verification_test"] = _verification(row)
        row["annotation_eligible"] = True
        row["evidence_grounded"] = True

        for field in ("issue_title", "assessment", "academic_consequence", "required_action", "illustrative_guidance", "comment"):
            if field in row:
                cleaned = _strip_ungrounded_example_sentences(
                    row.get(field), source_text,
                    allow_procedural_examples=(field == "illustrative_guidance"),
                    allow_corrective_rewrites=(field == "required_action"),
                )
                if cleaned:
                    row[field] = cleaned
                else:
                    # Never retain the original value when its examples or
                    # quotations failed the evidence gate. A later formatter
                    # may supply neutral connective wording, but it may not
                    # preserve invented examples.
                    row[field] = ""
        output.append(row)
    return output


def group_count_by_anchor(rows: Iterable[Mapping[str, Any]]) -> Dict[str, int]:
    return dict(Counter(_clean(row.get("anchor_key")) for row in rows if _clean(row.get("anchor_key"))))
