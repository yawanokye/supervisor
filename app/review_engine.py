from __future__ import annotations

import re
import uuid
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .document_parser import clean_text, infer_primary_chapter, normalised, parse_document
from .review_rules import (
    CHAPTERS,
    RULES,
    STATUS_LABELS,
    STATUS_MANUAL,
    STATUS_MEETS,
    STATUS_MISSING,
    STATUS_NA,
    STATUS_PARTIAL,
    STATUS_SCORES,
    is_applicable,
    readiness_band,
)

JUSTIFICATION_MARKERS = {
    "because", "therefore", "appropriate", "suitable", "justified", "rationale",
    "owing to", "given that", "selected because", "was chosen", "was adopted",
}
CRITICALITY_ORDER = {"critical": 0, "major": 1, "moderate": 2, "minor": 3}

def _contains(text: str, term: str) -> bool:
    return normalised(term) in normalised(text)

def _term_hits(text: str, terms: Iterable[str]) -> List[str]:
    low = normalised(text)
    return sorted({term for term in terms if normalised(term) and normalised(term) in low})

def _heading_matches(heading: Optional[str], headings: Iterable[str]) -> bool:
    low = normalised(heading or "")
    if not low:
        return False
    return any(normalised(h) in low or low in normalised(h) for h in headings if h)

def _severity(rule: Dict[str, Any], status: str) -> str:
    if status in {STATUS_MEETS, STATUS_NA}:
        return "minor"
    if rule.get("critical"):
        return "critical"
    if status == STATUS_MISSING:
        return "major"
    if status == STATUS_MANUAL:
        return "moderate"
    return "moderate"

def _location(evidence: List[Dict[str, Any]]) -> str:
    if not evidence:
        return "No reliable location identified"
    best = evidence[0]
    page = best.get("page")
    para = best.get("paragraph")
    heading = best.get("heading")
    parts = []
    if heading:
        parts.append(str(heading))
    if page is not None:
        parts.append(f"page {page}")
    if para is not None:
        parts.append(f"paragraph {para}")
    return ", ".join(parts) or "Location available in evidence"

def _comment(rule: Dict[str, Any], status: str, evidence: List[Dict[str, Any]]) -> Tuple[str, str]:
    item = rule["item"]
    location = _location(evidence)
    if status == STATUS_MEETS:
        return (
            f"The available evidence at {location} addresses this requirement with sufficient coverage for an automated review.",
            "Retain the section and confirm that the evidence remains consistent with the rest of the thesis."
        )
    if status == STATUS_PARTIAL:
        return (
            f"Related material was found at {location}, but it does not fully demonstrate that {item.lower()}. "
            "The section may state the required element without enough explanation, justification, comparison, or linkage.",
            f"Revise the identified passage so it directly and fully demonstrates that {item.lower()}. Add a clear rationale or cross-reference where needed."
        )
    if status == STATUS_MANUAL:
        return (
            f"This requirement depends on comparison, traceability, academic judgement, or document-wide consistency. "
            f"Potential evidence was found at {location}, but automated keyword matching cannot confirm adequacy.",
            f"Manually compare the relevant sections and document whether {item.lower()}. Record the exact supporting locations."
        )
    if status == STATUS_NA:
        return (
            "This requirement is not applicable to the selected research approach or review scope.",
            "No revision is required unless the study design changes."
        )
    return (
        f"No sufficiently relevant evidence was identified to demonstrate that {item.lower()}.",
        f"Add or revise content in the expected section so the thesis clearly demonstrates that {item.lower()}."
    )

def _candidate_paragraphs(
    paragraphs: List[Dict[str, Any]],
    rule: Dict[str, Any],
    selected_chapter: Optional[int],
    full_thesis: bool,
) -> List[Dict[str, Any]]:
    chapter_number = rule.get("chapter_number") or 0
    candidates = paragraphs

    if chapter_number and not full_thesis:
        target = selected_chapter or chapter_number
        chapter_specific = [p for p in paragraphs if p.get("chapter_number") in {None, target}]
        if chapter_specific:
            candidates = chapter_specific
    elif chapter_number:
        chapter_specific = [p for p in paragraphs if p.get("chapter_number") == chapter_number]
        if chapter_specific:
            candidates = chapter_specific

    heading_candidates = [
        p for p in candidates
        if _heading_matches(p.get("heading"), rule.get("headings", []))
        or _heading_matches(p.get("text") if p.get("is_heading") else "", rule.get("headings", []))
    ]
    return heading_candidates or candidates

def evaluate_rule(
    rule: Dict[str, Any],
    paragraphs: List[Dict[str, Any]],
    selected_chapter: Optional[int],
    research_approach: str,
    full_thesis: bool,
) -> Dict[str, Any]:
    if not is_applicable(rule, research_approach):
        status = STATUS_NA
        comment, action = _comment(rule, status, [])
        return {
            **rule, "status": status, "status_label": STATUS_LABELS[status],
            "score": None, "confidence": 1.0, "severity": "minor",
            "evidence": [], "comment": comment, "required_action": action,
        }

    candidates = _candidate_paragraphs(paragraphs, rule, selected_chapter, full_thesis)
    ranked: List[Dict[str, Any]] = []
    max_hits = 0
    max_adequacy = 0
    for p in candidates:
        hits = _term_hits(p.get("text", ""), rule.get("evidence_terms", []))
        adequacy_hits = _term_hits(
            p.get("text", ""),
            list(rule.get("adequacy_terms", [])) + list(JUSTIFICATION_MARKERS)
        )
        if hits:
            score = len(hits) * 2 + len(adequacy_hits)
            ranked.append({
                "text": clean_text(p.get("text", ""))[:850],
                "page": p.get("page"),
                "paragraph": p.get("paragraph"),
                "page_paragraph": p.get("page_paragraph"),
                "heading": p.get("heading"),
                "chapter_number": p.get("chapter_number"),
                "is_heading": bool(p.get("is_heading")),
                "matched_terms": hits,
                "adequacy_terms": adequacy_hits,
                "rank_score": score,
            })
            max_hits = max(max_hits, len(hits))
            max_adequacy = max(max_adequacy, len(adequacy_hits))

    ranked.sort(key=lambda x: x["rank_score"], reverse=True)
    evidence = ranked[:4]

    if rule.get("manual_only"):
        status = STATUS_MANUAL if evidence else STATUS_MISSING
        confidence = 0.55 if evidence else 0.15
    elif max_hits == 0:
        status = STATUS_MISSING
        confidence = 0.15
    else:
        term_target = min(3, max(1, len(set(rule.get("evidence_terms", []))) // 3))
        needs_adequacy = bool(rule.get("adequacy_terms"))
        if max_hits >= term_target and (not needs_adequacy or max_adequacy >= 1):
            status = STATUS_MEETS
            confidence = min(0.94, 0.58 + max_hits * 0.07 + max_adequacy * 0.04)
        else:
            status = STATUS_PARTIAL
            confidence = min(0.78, 0.40 + max_hits * 0.08 + max_adequacy * 0.03)

    comment, action = _comment(rule, status, evidence)
    return {
        **rule,
        "status": status,
        "status_label": STATUS_LABELS[status],
        "score": STATUS_SCORES[status],
        "confidence": round(confidence, 2),
        "severity": _severity(rule, status),
        "evidence": evidence,
        "comment": comment,
        "required_action": action,
    }

def _select_rules(selected_chapter: Optional[int], full_thesis: bool) -> List[Dict[str, Any]]:
    if full_thesis:
        return RULES
    chapter_key = next((k for k, v in CHAPTERS.items() if v["number"] == selected_chapter), None)
    if not chapter_key:
        return []
    return [r for r in RULES if r["chapter_key"] == chapter_key]

def _score_results(results: List[Dict[str, Any]]) -> Tuple[float, Dict[str, float]]:
    by_group = defaultdict(list)
    for row in results:
        value = row.get("score")
        if value is not None:
            by_group[row["chapter_key"]].append(float(value))

    chapter_scores = {}
    weighted_numerator = 0.0
    weighted_denominator = 0.0
    for key, values in by_group.items():
        score = round(sum(values) / len(values) * 100, 1) if values else 0.0
        chapter_scores[key] = score
        weight = CHAPTERS[key]["weight"]
        weighted_numerator += score * weight
        weighted_denominator += weight

    overall = round(weighted_numerator / weighted_denominator, 1) if weighted_denominator else 0.0
    return overall, chapter_scores

def _critical_gate(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    failed = [
        r for r in results
        if r.get("critical") and r.get("status") in {STATUS_MISSING, STATUS_PARTIAL, STATUS_MANUAL}
    ]
    return {
        "blocked": bool(failed),
        "failed_count": len(failed),
        "failed_rules": [{"code": r["code"], "item": r["item"], "status": r["status_label"]} for r in failed],
    }

def _priority_actions(results: List[Dict[str, Any]], limit: int = 12) -> List[Dict[str, Any]]:
    actionable = [
        r for r in results
        if r["status"] not in {STATUS_MEETS, STATUS_NA}
    ]
    actionable.sort(key=lambda r: (
        CRITICALITY_ORDER.get(r["severity"], 9),
        0 if r["status"] == STATUS_MISSING else 1,
        r["code"],
    ))
    return [{
        "code": r["code"],
        "section": r["section"],
        "severity": r["severity"],
        "status": r["status_label"],
        "action": r["required_action"],
    } for r in actionable[:limit]]

def analyse(
    file_bytes: bytes,
    filename: str,
    *,
    academic_level: str,
    research_approach: str,
    selected_chapter: Optional[int] = None,
    review_scope: str = "chapter",
) -> Dict[str, Any]:
    paragraphs = parse_document(file_bytes, filename)
    if not paragraphs:
        raise ValueError("No readable text was extracted from the document.")

    full_thesis = review_scope == "full_thesis"
    inferred = infer_primary_chapter(paragraphs)

    if not full_thesis:
        selected_chapter = selected_chapter or inferred
        if selected_chapter not in {1, 2, 3, 4, 5}:
            raise ValueError("Select the chapter being reviewed because it could not be detected reliably.")

    rules = _select_rules(selected_chapter, full_thesis)
    if not rules:
        raise ValueError("No review rules were selected.")

    results = [
        evaluate_rule(rule, paragraphs, selected_chapter, research_approach, full_thesis)
        for rule in rules
    ]
    overall_score, chapter_scores = _score_results(results)
    gates = _critical_gate(results)
    readiness = readiness_band(overall_score)

    if gates["blocked"] and overall_score >= 85:
        readiness = {
            "label": "Revision required before approval",
            "meaning": "The numerical score is high, but one or more critical requirements remain unresolved."
        }

    counts = defaultdict(int)
    for row in results:
        counts[row["status"]] += 1

    review_id = uuid.uuid4().hex
    return {
        "review_id": review_id,
        "summary": {
            "filename": filename,
            "academic_level": academic_level,
            "research_approach": research_approach,
            "review_scope": review_scope,
            "selected_chapter": selected_chapter,
            "inferred_chapter": inferred,
            "paragraphs_extracted": len(paragraphs),
            "rules_checked": len(results),
            "overall_score": overall_score,
            "readiness_label": readiness["label"],
            "readiness_meaning": readiness["meaning"],
            "critical_gate_blocked": gates["blocked"],
            "critical_failed": gates["failed_count"],
            "meets": counts[STATUS_MEETS],
            "partial": counts[STATUS_PARTIAL],
            "missing": counts[STATUS_MISSING],
            "manual": counts[STATUS_MANUAL],
            "not_applicable": counts[STATUS_NA],
        },
        "chapter_scores": chapter_scores,
        "critical_gates": gates,
        "priority_actions": _priority_actions(results),
        "results": results,
    }
