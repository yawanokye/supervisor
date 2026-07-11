from __future__ import annotations

import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .document_parser import clean_text, normalised
from .review_rules import (
    STATUS_MANUAL,
    STATUS_MEETS,
    STATUS_MISSING,
    STATUS_PARTIAL,
    STATUS_SCORES,
)

REVISION_LABELS = {
    STATUS_MEETS: "Addressed",
    STATUS_PARTIAL: "Partly addressed",
    STATUS_MISSING: "Not addressed",
    STATUS_MANUAL: "Manual confirmation required",
}

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "because", "been", "being", "but", "by",
    "can", "chapter", "comment", "comments", "could", "do", "does", "each", "for", "from",
    "has", "have", "how", "in", "into", "is", "it", "its", "may", "more", "must", "need",
    "needs", "of", "on", "or", "please", "required", "review", "revise", "revised", "section",
    "should", "student", "study", "supervisor", "than", "that", "the", "their", "there", "these",
    "this", "to", "use", "used", "using", "was", "were", "what", "when", "where", "which", "with",
    "you", "your", "add", "include", "explain", "clarify", "justify", "correct", "change", "improve",
    "strengthen", "rewrite", "address", "ensure", "provide", "show", "state", "discuss", "link",
}

MANUAL_MARKERS = {
    "grammar", "proofread", "formatting", "font", "margin", "spacing", "pagination", "page numbering",
    "track changes", "turnitin", "plagiarism", "similarity", "reference style", "apa formatting",
    "language quality", "flow better", "readability",
}
REMOVE_MARKERS = {"remove", "delete", "omit", "take out", "exclude"}
RECENCY_MARKERS = {"recent literature", "recent studies", "current studies", "up-to-date", "latest sources", "recent references"}
CITATION_MARKERS = {"citation", "citations", "reference", "references", "source", "sources"}

SECTION_HEADINGS = {
    "background": ["background to the study", "background of the study"],
    "problem": ["statement of the problem", "problem statement"],
    "purpose": ["purpose of the study"],
    "objective": ["research objectives", "objectives of the study"],
    "question": ["research questions"],
    "hypothesis": ["research hypotheses", "hypotheses development"],
    "significance": ["significance of the study"],
    "limitation": ["limitations of the study"],
    "delimitation": ["delimitations of the study", "scope of the study"],
    "theory": ["theoretical review", "theoretical framework"],
    "empirical": ["empirical review", "review of empirical literature"],
    "conceptual framework": ["conceptual framework"],
    "research design": ["research design"],
    "population": ["population of the study", "target population"],
    "sampling": ["sampling technique", "sample size determination"],
    "instrument": ["data collection instrument"],
    "validity": ["validity and reliability"],
    "data collection": ["data collection procedure"],
    "data analysis": ["data analysis", "data analysis plan"],
    "ethical": ["ethical considerations"],
    "results": ["results", "findings"],
    "discussion": ["discussion of findings", "discussion"],
    "conclusion": ["conclusions"],
    "recommendation": ["recommendations"],
}


def _stem(token: str) -> str:
    value = token.lower().strip()
    if value.endswith("ies") and len(value) > 5:
        return value[:-3] + "y"
    if value.endswith("ied") and len(value) > 5:
        return value[:-3] + "y"
    if value.endswith("ical") and len(value) > 6:
        return value[:-2]
    if value.endswith("sses") and len(value) > 6:
        return value[:-2]
    for suffix in ("isation", "ization", "ational", "fulness", "iveness", "ments", "ment", "ingly", "edly", "ing", "ed", "es", "s"):
        if value.endswith(suffix) and len(value) - len(suffix) >= 4:
            value = value[:-len(suffix)]
            break
    return value


def _tokens(text: str) -> List[str]:
    raw = re.findall(r"[a-zA-Z][a-zA-Z0-9'-]{2,}", normalised(text))
    return [_stem(token) for token in raw if token.lower() not in STOPWORDS and len(token) > 2]


def _keywords(text: str, limit: int = 18) -> List[str]:
    values: List[str] = []
    seen = set()
    for token in _tokens(text):
        if token in seen or len(token) < 3:
            continue
        seen.add(token)
        values.append(token)
        if len(values) >= limit:
            break
    return values


def _bigrams(tokens: Sequence[str]) -> Set[Tuple[str, str]]:
    return {(tokens[i], tokens[i + 1]) for i in range(len(tokens) - 1)}


def _rank_paragraphs(comment: str, paragraphs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    keywords = _keywords(comment)
    keyword_set = set(keywords)
    comment_bigrams = _bigrams(keywords)
    ranked: List[Dict[str, Any]] = []
    for paragraph in paragraphs:
        if paragraph.get("is_heading"):
            continue
        text = clean_text(paragraph.get("text", ""))
        if len(text) < 20:
            continue
        paragraph_tokens = _tokens(text + " " + clean_text(paragraph.get("heading", "")))
        paragraph_set = set(paragraph_tokens)
        overlap = keyword_set & paragraph_set
        coverage = len(overlap) / max(1, len(keyword_set))
        paragraph_bigrams = _bigrams(paragraph_tokens)
        bigram_hits = len(comment_bigrams & paragraph_bigrams)
        phrase_bonus = min(0.18, bigram_hits * 0.06)
        score = min(1.0, coverage * 0.82 + phrase_bonus)
        if overlap or phrase_bonus:
            ranked.append({
                "text": text[:1000],
                "page": paragraph.get("page"),
                "paragraph": paragraph.get("paragraph"),
                "page_paragraph": paragraph.get("page_paragraph"),
                "heading": paragraph.get("heading"),
                "chapter_number": paragraph.get("chapter_number"),
                "is_heading": False,
                "source_filename": paragraph.get("source_filename"),
                "document_role": paragraph.get("document_role", "current"),
                "matched_terms": sorted(overlap),
                "rank_score": round(score, 4),
            })
    ranked.sort(key=lambda row: (row["rank_score"], len(row["matched_terms"])), reverse=True)
    return ranked


def _infer_headings(comment: str) -> List[str]:
    low = normalised(comment)
    headings: List[str] = []
    for marker, values in SECTION_HEADINGS.items():
        if marker in low:
            headings.extend(values)
    return list(dict.fromkeys(headings))


def _severity(comment: str) -> str:
    low = normalised(comment)
    if any(value in low for value in ("critical", "fundamental", "must be corrected", "major revision", "not acceptable")):
        return "critical"
    if any(value in low for value in ("major", "substantial", "missing", "not addressed", "inconsistent", "unsupported")):
        return "major"
    return "moderate"


def _has_recent_citations(paragraphs: List[Dict[str, Any]]) -> bool:
    threshold = datetime.utcnow().year - 5
    for paragraph in paragraphs:
        for year in re.findall(r"\b(19\d{2}|20\d{2})\b", paragraph.get("text", "")):
            if int(year) >= threshold:
                return True
    return False


def _has_citations(paragraphs: List[Dict[str, Any]]) -> bool:
    patterns = [r"\([A-Z][A-Za-z' -]+,\s*(?:19|20)\d{2}\)", r"\b[A-Z][A-Za-z' -]+\s+et\s+al\.?,?\s*\((?:19|20)\d{2}\)"]
    return any(re.search(pattern, paragraph.get("text", "")) for paragraph in paragraphs for pattern in patterns)


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, normalised(a), normalised(b)).ratio()


def _manual_required(comment: str) -> bool:
    low = normalised(comment)
    return any(marker in low for marker in MANUAL_MARKERS)


def _is_remove_request(comment: str) -> bool:
    low = normalised(comment)
    return any(marker in low for marker in REMOVE_MARKERS)


def _special_status(comment: str, current_paragraphs: List[Dict[str, Any]]) -> Optional[Tuple[str, float, str]]:
    low = normalised(comment)
    if any(marker in low for marker in RECENCY_MARKERS):
        if _has_recent_citations(current_paragraphs):
            return STATUS_PARTIAL, 0.68, "Recent citation years were found, but relevance and adequacy still require confirmation."
        return STATUS_MISSING, 0.78, "No clearly recent citation years were found in the revised chapter."
    if any(marker in low for marker in CITATION_MARKERS) and any(value in low for value in ("add", "include", "support", "cite")):
        if _has_citations(current_paragraphs):
            return STATUS_PARTIAL, 0.65, "Citation patterns were found, but the exact claim-to-source match requires confirmation."
        return STATUS_MISSING, 0.8, "No clear in-text citation pattern was found in the revised chapter."
    return None


def evaluate_revision_comments(
    comments: List[Dict[str, Any]],
    current_paragraphs: List[Dict[str, Any]],
    original_paragraphs: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    original_paragraphs = original_paragraphs or []

    for index, source in enumerate(comments, start=1):
        comment_text = clean_text(source.get("text", ""))
        code = f"REV{index}"
        keywords = _keywords(comment_text)
        current_ranked = _rank_paragraphs(comment_text, current_paragraphs)
        original_ranked = _rank_paragraphs(comment_text, original_paragraphs) if original_paragraphs else []
        current_best = current_ranked[0] if current_ranked else None
        original_best = original_ranked[0] if original_ranked else None
        current_score = float(current_best.get("rank_score", 0)) if current_best else 0.0
        original_score = float(original_best.get("rank_score", 0)) if original_best else 0.0
        changed = None
        similarity = None

        special = _special_status(comment_text, current_paragraphs)
        if _manual_required(comment_text):
            status = STATUS_MANUAL
            confidence = 0.55
            rationale = "This comment concerns presentation or language quality that requires direct human confirmation."
        elif _is_remove_request(comment_text) and original_paragraphs:
            if original_score >= 0.30 and current_score < 0.18:
                status = STATUS_MEETS
                confidence = 0.82
                rationale = "The material associated with the removal request appears in the original version but is not clearly present in the revision."
            elif current_score >= 0.30:
                status = STATUS_MISSING
                confidence = 0.75
                rationale = "Material associated with the removal request still appears in the revised chapter."
            else:
                status = STATUS_MANUAL
                confidence = 0.48
                rationale = "The target of the removal request could not be identified reliably."
        elif special is not None:
            status, confidence, rationale = special
        elif len(keywords) < 2:
            status = STATUS_MANUAL
            confidence = 0.42
            rationale = "The comment is too general for reliable automated matching."
        else:
            if current_score >= 0.45 and len(current_best.get("matched_terms", [])) >= 3:
                status = STATUS_MEETS
                confidence = min(0.93, 0.68 + current_score * 0.25)
                rationale = "The revised chapter contains strong topic coverage corresponding to the supervisor comment."
            elif current_score >= 0.20 and len(current_best.get("matched_terms", [])) >= 2:
                status = STATUS_PARTIAL
                confidence = min(0.82, 0.50 + current_score * 0.35)
                rationale = "Related revision evidence was found, but the comment is not fully demonstrated."
            else:
                status = STATUS_MISSING
                confidence = min(0.86, 0.58 + (0.25 - min(current_score, 0.25)))
                rationale = "No sufficiently strong revision evidence was found for this supervisor comment."

        if original_best and current_best:
            similarity = round(_similarity(original_best.get("text", ""), current_best.get("text", "")), 3)
            changed = similarity < 0.92
            if similarity >= 0.95 and current_score <= original_score + 0.05:
                if status == STATUS_MEETS:
                    status = STATUS_PARTIAL
                    rationale = "Relevant text was found, but it remains almost unchanged from the original version."
                elif status == STATUS_PARTIAL:
                    status = STATUS_MISSING
                    rationale = "The relevant passage remains almost unchanged from the original version."
                confidence = max(confidence, 0.72)
            elif current_score >= original_score + 0.18 and status == STATUS_PARTIAL:
                status = STATUS_MEETS
                rationale = "The revised version shows a clear improvement in coverage compared with the original chapter."
                confidence = max(confidence, 0.78)

        if status == STATUS_MEETS:
            required_action = "No further action is indicated automatically. Confirm that the revision fully satisfies the supervisor's intended meaning."
        elif status == STATUS_PARTIAL:
            required_action = f"Strengthen the revised passage so it fully addresses this supervisor comment: {comment_text}"
        elif status == STATUS_MANUAL:
            required_action = f"Manually compare the revised chapter with this supervisor comment and record the final decision: {comment_text}"
        else:
            required_action = f"Revise the chapter to address this outstanding supervisor comment: {comment_text}"

        evidence = current_ranked[:3]
        location = "No reliable revision location identified"
        if current_best:
            parts = [current_best.get("heading")]
            if current_best.get("page") is not None:
                parts.append(f"page {current_best['page']}")
            if current_best.get("paragraph") is not None:
                parts.append(f"paragraph {current_best['paragraph']}")
            location = ", ".join(str(value) for value in parts if value)

        assessment = f"{rationale}"
        if current_best:
            assessment += f" Best matching revised evidence: {location}."
        if original_best and similarity is not None:
            assessment += f" Original-to-revised passage similarity: {similarity:.0%}."

        results.append({
            "code": code,
            "chapter_key": "REV",
            "chapter_number": 0,
            "chapter_title": "Supervisor Comment Compliance",
            "section": "Supervisor Comment Compliance",
            "item": comment_text,
            "headings": _infer_headings(comment_text),
            "evidence_terms": keywords,
            "critical": _severity(comment_text) == "critical",
            "manual_only": False,
            "review_type": "supervisor_comment",
            "status": status,
            "status_label": REVISION_LABELS[status],
            "score": STATUS_SCORES[status],
            "confidence": round(float(confidence), 2),
            "severity": _severity(comment_text),
            "evidence": evidence,
            "comment": assessment,
            "required_action": required_action,
            "supervisor_comment_source": source.get("source_filename", "Supervisor comments"),
            "supervisor_comment_source_type": source.get("source_type", "document"),
            "supervisor_comment_author": source.get("author", ""),
            "revision_details": {
                "keyword_count": len(keywords),
                "current_match_score": round(current_score, 3),
                "original_match_score": round(original_score, 3) if original_paragraphs else None,
                "passage_changed": changed,
                "passage_similarity": similarity,
            },
        })
    return results


def revision_score(results: List[Dict[str, Any]]) -> Optional[float]:
    values = [float(row["score"]) for row in results if row.get("score") is not None]
    if not values:
        return None
    return round(sum(values) / len(values) * 100, 1)


def revision_counts(results: List[Dict[str, Any]]) -> Dict[str, int]:
    output = {"addressed": 0, "partly_addressed": 0, "not_addressed": 0, "manual": 0}
    for row in results:
        if row.get("status") == STATUS_MEETS:
            output["addressed"] += 1
        elif row.get("status") == STATUS_PARTIAL:
            output["partly_addressed"] += 1
        elif row.get("status") == STATUS_MISSING:
            output["not_addressed"] += 1
        elif row.get("status") == STATUS_MANUAL:
            output["manual"] += 1
    return output
