from __future__ import annotations

import json
import uuid
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping, Sequence


def guided_chapter_units(paragraphs: Sequence[Mapping[str, Any]]) -> List[int]:
    """Return genuine detected chapter numbers in document order.

    TOC rows are explicitly excluded. The parser already distinguishes them,
    but the second guard prevents a malformed manual TOC from becoming a
    guided review unit.
    """
    output: List[int] = []
    for row in paragraphs:
        number = row.get("chapter_number")
        if not isinstance(number, int) or number < 1:
            continue
        if row.get("is_toc_entry") or row.get("document_zone") in {
            "table_of_contents", "list_of_tables", "list_of_figures"
        }:
            continue
        if number not in output:
            output.append(number)
    return output


def should_use_guided_review(
    *, workflow_type: str, review_scope: str, units: Sequence[int]
) -> bool:
    return (
        workflow_type == "supervisory_review"
        and review_scope == "full_thesis"
        and len(units) > 1
    )


def parse_json_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return list(value)
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def parse_review_id_map(value: Any) -> Dict[str, str]:
    if isinstance(value, dict):
        return {str(key): str(item) for key, item in value.items() if item}
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(key): str(item) for key, item in parsed.items() if item}


def scoped_guided_payload(
    payload: Mapping[str, Any], *, units: Sequence[int], current_index: int
) -> Dict[str, Any]:
    """Build the single-chapter payload used for one guided review turn."""
    if not units:
        return dict(payload)
    index = max(0, min(int(current_index or 0), len(units) - 1))
    chapter = int(units[index])
    output = dict(payload)
    output.update({
        "guided_mode": True,
        "guided_units": [int(value) for value in units],
        "guided_current_index": index,
        "guided_current_chapter": chapter,
        "guided_is_last": index == len(units) - 1,
        "original_review_scope": payload.get("original_review_scope") or payload.get("review_scope"),
        "review_scope": "chapter",
        "selected_chapter": chapter,
        "combined_chapter_end": 0,
        "document_type": "chapter_one" if chapter == 1 else "chapter",
        "section_scope_mode": "whole_chapter",
        "selected_sections": [],
    })
    return output


def remember_chapter_review(
    mapping: Mapping[str, str], *, chapter: int, review_id: str
) -> Dict[str, str]:
    output = dict(mapping)
    output[str(int(chapter))] = str(review_id)
    return output


def review_id_is_guided_child(value: Any, review_id: str) -> bool:
    return str(review_id) in set(parse_review_id_map(value).values())


def _signature(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("finding_id") or "").strip().lower(),
        str(row.get("issue_title") or row.get("item") or "").strip().lower(),
        str(row.get("exact_source_text") or row.get("problematic_quote") or "").strip().lower()[:220],
    )


def _merge_rows(reviews: Iterable[Mapping[str, Any]], key: str) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    seen = set()
    for review in reviews:
        for row in review.get(key) or []:
            signature = _signature(row)
            if signature in seen:
                continue
            seen.add(signature)
            item = deepcopy(dict(row))
            item.pop("finding_number", None)
            output.append(item)
    return output


def merge_guided_reviews(
    reviews: Sequence[Mapping[str, Any]], *, filename: str = ""
) -> Dict[str, Any]:
    """Assemble the released whole-thesis result from completed chapter turns.

    Each chapter has already been reviewed with all earlier chapters and the
    shared reference index available as context. This final assembly preserves
    those grounded findings, removes cross-turn duplicates and creates a new
    review identity for the complete-thesis report.
    """
    if not reviews:
        raise ValueError("At least one chapter review is required.")
    merged = deepcopy(dict(reviews[-1]))
    merged["review_id"] = uuid.uuid4().hex
    for key in (
        "academic_findings", "canonical_findings", "alignment_results",
        "revision_results", "results", "priority_actions",
    ):
        merged[key] = _merge_rows(reviews, key)

    statistical_warnings: List[Dict[str, Any]] = []
    warning_seen = set()
    for review in reviews:
        for warning in (review.get("statistical_review") or {}).get("consistency_warnings") or []:
            signature = (
                str(warning.get("kind") or ""),
                str(warning.get("message") or ""),
                str((warning.get("evidence") or {}).get("paragraph") or ""),
            )
            if signature in warning_seen:
                continue
            warning_seen.add(signature)
            statistical_warnings.append(deepcopy(dict(warning)))
    stats = deepcopy(dict(merged.get("statistical_review") or {}))
    stats["consistency_warnings"] = statistical_warnings
    stats["warning_count"] = len(statistical_warnings)
    stats["verified_inconsistency_count"] = sum(
        1 for row in statistical_warnings
        if row.get("verification") == "verified inconsistency"
    )
    merged["statistical_review"] = stats

    summary = merged.setdefault("summary", {})
    scores = [float((item.get("summary") or {}).get("overall_score") or 0) for item in reviews]
    summary.update({
        "filename": filename or summary.get("filename"),
        "review_scope": "full_thesis",
        "document_type": "full_thesis",
        "document_label": "Complete thesis",
        "selected_chapter": None,
        "guided_review": True,
        "guided_final_consistency_audit": True,
        "guided_chapters_completed": [
            (item.get("summary") or {}).get("selected_chapter") for item in reviews
        ],
        "guided_chapter_report_count": len(reviews),
        "overall_score": round(sum(scores) / len(scores), 1) if scores else 0,
        "partial_report_generated": False,
    })
    return merged
