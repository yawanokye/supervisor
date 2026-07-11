from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from .supervisory_review_algorithm import coverage_statuses_for_review


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _pid(paragraph: Dict[str, Any]) -> str:
    role = paragraph.get("document_role", "current")
    number = int(paragraph.get("paragraph") or 0)
    if role == "previous":
        return f"C{int(paragraph.get('document_index') or 0)}P{number}"
    if role == "original":
        return f"O{number}"
    return f"P{number}"


def _section_label(paragraph: Dict[str, Any]) -> str:
    path = [_clean(value) for value in paragraph.get("section_path") or [] if _clean(value)]
    return path[-1] if path else _clean(paragraph.get("heading") or "Opening material")


def _is_substantive(paragraph: Dict[str, Any]) -> bool:
    return bool(_clean(paragraph.get("text"))) and not bool(paragraph.get("is_heading"))


def _is_table_row(paragraph: Dict[str, Any]) -> bool:
    return str(paragraph.get("source_kind") or "").lower() == "table_row" or paragraph.get("table_index") is not None


def _ordered_sections(paragraphs: Sequence[Dict[str, Any]]) -> List[Tuple[Tuple[Any, ...], List[Dict[str, Any]]]]:
    grouped: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = defaultdict(list)
    order: List[Tuple[Any, ...]] = []
    for paragraph in paragraphs:
        if not _clean(paragraph.get("text")):
            continue
        key = (
            paragraph.get("chapter_number"),
            tuple(_clean(value) for value in paragraph.get("section_path") or [] if _clean(value)),
            _section_label(paragraph),
        )
        if key not in grouped:
            order.append(key)
        grouped[key].append(paragraph)
    return [(key, grouped[key]) for key in order]


def _window_payload(
    *,
    heading: str,
    chapter_number: Any,
    section_path: Sequence[str],
    target_rows: Sequence[Dict[str, Any]],
    context_before: Sequence[Dict[str, Any]],
    context_after: Sequence[Dict[str, Any]],
    unit_kind: str,
    unit_index: int,
    total_units: int,
) -> Dict[str, Any]:
    target_ids = [_pid(row) for row in target_rows]
    context_rows = list(context_before) + list(context_after)
    context_ids = [_pid(row) for row in context_rows]
    paragraphs: List[Dict[str, Any]] = []
    seen = set()
    for row in list(context_before) + list(target_rows) + list(context_after):
        pid = _pid(row)
        if pid in seen:
            continue
        seen.add(pid)
        paragraphs.append(row)
    table_number = next((_clean(row.get("table_number")) for row in target_rows if _clean(row.get("table_number"))), "")
    table_title = next((_clean(row.get("table_title")) for row in target_rows if _clean(row.get("table_title"))), "")
    return {
        "heading": heading,
        "chapter_number": chapter_number,
        "section_path": list(section_path),
        "part": unit_index,
        "paragraphs": paragraphs,
        "target_paragraph_ids": target_ids,
        "context_paragraph_ids": context_ids,
        "coverage_unit": True,
        "coverage_unit_kind": unit_kind,
        "coverage_unit_index": unit_index,
        "coverage_unit_total": total_units,
        "table_number": table_number,
        "table_title": table_title,
    }


def build_coverage_units(
    paragraphs: Sequence[Dict[str, Any]],
    *,
    prose_paragraphs_per_unit: int = 7,
    context_paragraphs: int = 1,
    max_chars_per_unit: int = 12000,
    table_rows_per_unit: int = 10,
) -> List[Dict[str, Any]]:
    """Create sequential, non-sampling review units covering the whole work.

    Every non-empty paragraph, heading and table row appears in exactly one target
    set. Adjacent section headings may share a unit, but every item retains its own
    heading and section metadata. Tables remain separate because they require a
    dedicated accuracy and adequacy audit. Neighbouring prose is supplied as context
    only and is never counted as a reviewed target in another unit.
    """
    prose_paragraphs_per_unit = max(1, int(prose_paragraphs_per_unit or 1))
    context_paragraphs = max(0, int(context_paragraphs or 0))
    max_chars_per_unit = max(2500, int(max_chars_per_unit or 12000))
    table_rows_per_unit = max(1, int(table_rows_per_unit or 1))

    ordered_rows = [row for row in paragraphs if _clean(row.get("text"))]
    ordered_rows.sort(key=lambda row: int(row.get("paragraph") or 0))

    # Preserve contiguous document blocks. This prevents front matter and
    # references, both of which may have chapter_number=None, from being joined
    # across the body of the thesis.
    blocks: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []
    current_chapter: Any = object()
    for row in ordered_rows:
        chapter = row.get("chapter_number")
        if current and chapter != current_chapter:
            blocks.append(current)
            current = []
        if not current:
            current_chapter = chapter
        current.append(row)
    if current:
        blocks.append(current)

    units: List[Dict[str, Any]] = []
    for block in blocks:
        chapter_number = block[0].get("chapter_number") if block else None
        prose_rows = [row for row in block if not _is_table_row(row)]
        table_groups: Dict[Any, List[Dict[str, Any]]] = defaultdict(list)
        for row in block:
            if _is_table_row(row):
                table_groups[row.get("table_index", (row.get("table_number"), int(row.get("paragraph") or 0)))].append(row)

        provisional: List[Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]] = []
        start = 0
        while start < len(prose_rows):
            target: List[Dict[str, Any]] = []
            total_chars = 0
            cursor = start
            while cursor < len(prose_rows) and len(target) < prose_paragraphs_per_unit:
                row = prose_rows[cursor]
                size = len(_clean(row.get("text"))) + 160
                if target and total_chars + size > max_chars_per_unit:
                    break
                target.append(row)
                total_chars += size
                cursor += 1
            if not target:
                target = [prose_rows[start]]
                cursor = start + 1
            before = prose_rows[max(0, start - context_paragraphs):start]
            after = prose_rows[cursor:cursor + context_paragraphs]
            provisional.append(("prose", target, before, after))
            start = cursor

        for table_rows in table_groups.values():
            table_rows.sort(key=lambda row: int(row.get("paragraph") or 0))
            for offset in range(0, len(table_rows), table_rows_per_unit):
                provisional.append(("table", table_rows[offset:offset + table_rows_per_unit], [], []))

        provisional.sort(key=lambda item: min(int(row.get("paragraph") or 0) for row in item[1]))
        total_units = len(provisional)
        for index, (kind, target, before, after) in enumerate(provisional, start=1):
            first = target[0]
            last = target[-1]
            first_label = _section_label(first)
            last_label = _section_label(last)
            heading = first_label if first_label == last_label else f"{first_label} to {last_label}"
            section_path = list(first.get("section_path") or [])
            if kind == "table":
                number = next((_clean(row.get("table_number")) for row in target if _clean(row.get("table_number"))), "")
                title = next((_clean(row.get("table_title")) for row in target if _clean(row.get("table_title"))), "")
                label = " ".join(value for value in (f"Table {number}" if number else "Table", title) if value)
                if label:
                    heading = f"{first_label} — {label}"
            units.append(_window_payload(
                heading=heading,
                chapter_number=chapter_number,
                section_path=section_path,
                target_rows=target,
                context_before=before,
                context_after=after,
                unit_kind=kind,
                unit_index=index,
                total_units=total_units,
            ))
    return units


def coverage_packets(
    units: Sequence[Dict[str, Any]],
    *,
    max_units_per_request: int = 4,
    high_risk_units_per_request: int = 2,
    max_chars_per_request: int = 28000,
) -> List[List[Dict[str, Any]]]:
    """Batch adjacent units without allowing large whole-chapter sampling calls."""
    max_units_per_request = max(1, int(max_units_per_request or 1))
    high_risk_units_per_request = max(1, int(high_risk_units_per_request or 1))
    max_chars_per_request = max(5000, int(max_chars_per_request or 28000))
    packets: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []
    current_chars = 0
    current_chapter = object()

    def unit_chars(unit: Dict[str, Any]) -> int:
        return sum(len(_clean(row.get("text"))) + 160 for row in unit.get("paragraphs") or []) + 1200

    def unit_limit(unit: Dict[str, Any]) -> int:
        chapter = unit.get("chapter_number")
        heading = _clean(unit.get("heading")).lower()
        high_risk = chapter in {3, 4} or unit.get("coverage_unit_kind") == "table" or any(
            term in heading for term in ("method", "result", "analysis", "discussion", "model", "diagnostic")
        )
        return high_risk_units_per_request if high_risk else max_units_per_request

    for unit in units:
        chapter = unit.get("chapter_number")
        size = unit_chars(unit)
        limit = unit_limit(unit)
        if current and (
            chapter != current_chapter
            or len(current) >= limit
            or current_chars + size > max_chars_per_request
            or unit.get("alignment_audit")
            or unit.get("revision_audit")
        ):
            packets.append(current)
            current = []
            current_chars = 0
        if not current:
            current_chapter = chapter
        current.append(unit)
        current_chars += size
        if unit.get("alignment_audit") or unit.get("revision_audit"):
            packets.append(current)
            current = []
            current_chars = 0
            current_chapter = object()
    if current:
        packets.append(current)
    return packets


def build_coverage_ledger(
    units: Sequence[Dict[str, Any]],
    section_reviews: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    review_by_key = {str(row.get("section_key") or ""): row for row in section_reviews}
    entries: List[Dict[str, Any]] = []
    total_targets = 0
    assessed_targets = 0
    completed_units = 0
    chapter_stats: Dict[Any, Dict[str, int]] = defaultdict(lambda: {
        "units": 0, "completed_units": 0, "targets": 0, "assessed_targets": 0,
    })
    for unit in units:
        if not unit.get("coverage_unit"):
            continue
        key = str(unit.get("section_key") or "")
        targets = list(dict.fromkeys(unit.get("target_paragraph_ids") or []))
        review = review_by_key.get(key) or {}
        assessed = list(dict.fromkeys(review.get("assessed_paragraph_ids") or []))
        target_statuses = coverage_statuses_for_review(review, targets)
        assessed_set = set(assessed)
        target_set = set(targets)
        complete = bool(review) and target_set.issubset(assessed_set)
        chapter = unit.get("chapter_number")
        total_targets += len(targets)
        assessed_targets += len(target_set & assessed_set)
        completed_units += int(complete)
        stats = chapter_stats[chapter]
        stats["units"] += 1
        stats["completed_units"] += int(complete)
        stats["targets"] += len(targets)
        stats["assessed_targets"] += len(target_set & assessed_set)
        entries.append({
            "section_key": key,
            "chapter_number": chapter,
            "heading": _clean(unit.get("heading")),
            "unit_kind": unit.get("coverage_unit_kind", "prose"),
            "target_paragraph_ids": targets,
            "assessed_paragraph_ids": assessed,
            "missing_paragraph_ids": sorted(target_set - assessed_set),
            "target_statuses": target_statuses,
            "status_counts": dict(Counter(target_statuses.values())),
            "complete": complete,
            "issue_count": len(review.get("issues") or []),
            "strength_count": len(review.get("strengths") or []),
        })
    unit_count = len(entries)
    target_percent = round(100.0 * assessed_targets / max(1, total_targets), 1)
    unit_percent = round(100.0 * completed_units / max(1, unit_count), 1)
    overall_status_counts = Counter()
    for entry in entries:
        overall_status_counts.update(entry.get("status_counts") or {})
    return {
        "mode": "systematic_coverage_driven",
        "unit_count": unit_count,
        "completed_units": completed_units,
        "unit_coverage_percent": unit_percent,
        "target_count": total_targets,
        "assessed_target_count": assessed_targets,
        "target_coverage_percent": target_percent,
        "complete": bool(unit_count) and completed_units == unit_count and assessed_targets == total_targets,
        "status_counts": dict(overall_status_counts),
        "entries": entries,
        "chapters": {str(key): value for key, value in chapter_stats.items()},
    }
