from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Sequence, Tuple


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", _clean(value).lower()).strip()


def chapter_number(row: Dict[str, Any]) -> int | None:
    try:
        if row.get("chapter_number") is not None:
            return int(row.get("chapter_number"))
    except (TypeError, ValueError):
        pass
    for item in row.get("evidence") or []:
        try:
            if item.get("chapter_number") is not None:
                return int(item.get("chapter_number"))
        except (TypeError, ValueError):
            continue
    text = _norm(row.get("section_reference") or row.get("section"))
    match = re.search(r"\bchapter\s+(\d+)\b", text)
    if match:
        return int(match.group(1))
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
    for word, number in words.items():
        if f"chapter {word}" in text:
            return number
    return None


def primary_evidence(row: Dict[str, Any]) -> Dict[str, Any]:
    current = [item for item in (row.get("evidence") or []) if item.get("document_role", "current") == "current"]
    evidence = current or list(row.get("evidence") or [])
    def key(item: Dict[str, Any]) -> Tuple[int, int, int]:
        try:
            paragraph = int(item.get("paragraph"))
        except (TypeError, ValueError):
            paragraph = 10**9
        try:
            table_index = int(item.get("table_index"))
        except (TypeError, ValueError):
            table_index = 10**9
        try:
            table_row = int(item.get("table_row"))
        except (TypeError, ValueError):
            table_row = 10**9
        return paragraph, table_index, table_row
    return min(evidence, key=key) if evidence else {}


def is_missing_section(row: Dict[str, Any]) -> bool:
    text = _norm(" ".join(_clean(row.get(field)) for field in (
        "item", "issue_title", "comment", "required_action", "section", "section_reference", "reference_label"
    )))
    return any(term in text for term in ("missing section", "section is not evident", "section is absent", "expected section is not evident", "reference list is missing"))


def document_order_key(row: Dict[str, Any]) -> Tuple[int, int, int, int, str]:
    chapter = chapter_number(row) or 999
    evidence = primary_evidence(row)
    try:
        paragraph = int(evidence.get("paragraph"))
    except (TypeError, ValueError):
        paragraph = 10**9
    try:
        table_index = int(evidence.get("table_index"))
    except (TypeError, ValueError):
        table_index = 10**9
    try:
        table_row = int(evidence.get("table_row"))
    except (TypeError, ValueError):
        table_row = 10**9
    # A verified missing section normally carries the paragraph after which it
    # should be inserted. Respect that insertion anchor so the correction number
    # appears in the document's natural reading order. Only genuinely unanchored
    # findings are placed at the end of their chapter.
    if not evidence:
        paragraph = 10**9
    elif is_missing_section(row) and not row.get("section_contract_verified"):
        paragraph = 10**9
    return chapter, paragraph, table_index, table_row, _norm(row.get("item") or row.get("issue_title"))


def order_and_number_rows(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ordered = list(rows)
    ordered.sort(key=document_order_key)
    for number, row in enumerate(ordered, start=1):
        row["finding_number"] = number
    return ordered
