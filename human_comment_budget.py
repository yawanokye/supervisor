from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Mapping, Sequence


SEVERITY_RANK = {"critical": 0, "major": 1, "moderate": 2, "minor": 3}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _budget(review: Mapping[str, Any]) -> int:
    summary = review.get("summary") or {}
    depth = _clean(summary.get("review_depth") or summary.get("requested_mode") or "standard").lower()
    if summary.get("review_scope") == "full_thesis":
        return {"light": 40, "standard": 55, "advanced": 65}.get(depth, 55)
    return {"light": 10, "standard": 14, "advanced": 18}.get(depth, 14)


def _root_signature(row: Mapping[str, Any]) -> str:
    value = _clean(
        row.get("root_cause_family")
        or row.get("issue_title")
        or row.get("item")
        or row.get("required_action")
    ).lower()
    value = re.sub(r"\b(?:table|chapter|section|paragraph)\s+[a-z0-9.:-]+\b", "", value)
    value = re.sub(r"[^a-z0-9 ]+", " ", value)
    return " ".join(value.split()[:18])


def apply_human_comment_budget(review: Dict[str, Any]) -> Dict[str, Any]:
    """Release a supervisor-sized set while retaining a grouped issue ledger."""
    rows = [
        dict(row) for row in (review.get("canonical_findings") or [])
        if row.get("status") not in {"meets_requirement", "not_applicable"}
        and row.get("annotation_eligible") is not False
    ]
    limit = _budget(review)
    rows.sort(key=lambda row: (
        SEVERITY_RANK.get(_clean(row.get("severity")).lower(), 9),
        -float(row.get("confidence") or 0),
        int(row.get("finding_number") or 99999),
    ))

    selected: List[Dict[str, Any]] = []
    deferred: List[Dict[str, Any]] = []
    root_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    for row in rows:
        severity = _clean(row.get("severity")).lower()
        root = _root_signature(row)
        category = _clean(row.get("category") or "Other")
        repeated = bool(root and root_counts[root] >= (2 if severity in {"critical", "major"} else 1))
        category_crowded = category_counts[category] >= max(3, limit // 4)
        must_keep = severity == "critical"
        if must_keep or (len(selected) < limit and not repeated and not category_crowded):
            selected.append(row)
            if root:
                root_counts[root] += 1
            category_counts[category] += 1
        else:
            deferred.append(row)

    # Fill unused capacity after the diversity and repetition pass.
    for row in list(deferred):
        if len(selected) >= limit:
            break
        selected.append(row)
        deferred.remove(row)

    selected.sort(key=lambda row: int(row.get("finding_number") or 99999))
    number_by_id: Dict[str, int] = {}
    for number, row in enumerate(selected, start=1):
        row["finding_number"] = number
        finding_id = _clean(row.get("finding_id"))
        if finding_id:
            number_by_id[finding_id] = number
    review["canonical_findings"] = selected

    for key in ("academic_findings", "alignment_results", "revision_results"):
        for row in review.get(key) or []:
            finding_id = _clean(row.get("finding_id"))
            if finding_id in number_by_id:
                row["finding_number"] = number_by_id[finding_id]
            else:
                row.pop("finding_number", None)

    grouped = Counter(_clean(row.get("category") or "Other") for row in deferred)
    review["deferred_issue_ledger"] = {
        "count": len(deferred),
        "grouped_counts": dict(grouped),
        "note": (
            "Repeated and lower-priority instances were grouped rather than inserted as separate margin comments. "
            "The student should apply each released correction consistently throughout the thesis."
        ),
    }
    summary = review.setdefault("summary", {})
    summary.update({
        "canonical_finding_count": len(selected),
        "human_comment_budget_applied": True,
        "human_comment_budget": limit,
        "deferred_repeated_or_lower_priority_findings": len(deferred),
        "final_numbering_reconciled": [row.get("finding_number") for row in selected] == list(range(1, len(selected) + 1)),
    })
    return review
