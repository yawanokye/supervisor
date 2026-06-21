from __future__ import annotations

import asyncio
import hashlib
import json
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .ai_config import HybridAIConfig
from .ai_prompts import (
    ADJUDICATE_SYSTEM_PROMPT,
    DOCUMENT_MAP_SYSTEM_PROMPT,
    REVIEW_SYSTEM_PROMPT,
    VERIFY_SYSTEM_PROMPT,
)
from .ai_providers import AIProviderError, DeepSeekProvider, OpenAIProvider, ProviderResult
from .ai_schemas import AIDecision, AIUsageRecord, DecisionBatch, DocumentMap
from .alignment_engine import alignment_score
from .document_parser import clean_text, normalised
from .revision_engine import revision_counts, revision_score
from .review_rules import (
    CHAPTERS,
    STATUS_LABELS,
    STATUS_MANUAL,
    STATUS_MEETS,
    STATUS_MISSING,
    STATUS_NA,
    STATUS_PARTIAL,
    STATUS_SCORES,
    readiness_band,
)

ACTIONABLE = {STATUS_PARTIAL, STATUS_MISSING, STATUS_MANUAL}
STATUS_RANK = {
    STATUS_MISSING: 0,
    STATUS_MANUAL: 1,
    STATUS_PARTIAL: 2,
    STATUS_MEETS: 3,
    STATUS_NA: 4,
}
CRITICALITY_ORDER = {"critical": 0, "major": 1, "moderate": 2, "minor": 3}


def _pid(paragraph: Dict[str, Any]) -> str:
    role = paragraph.get("document_role", "current")
    number = int(paragraph.get("paragraph") or 0)
    if role == "previous":
        return f'C{int(paragraph.get("document_index") or 0)}P{number}'
    if role == "original":
        return f'O{number}'
    return f'P{number}'


def _paragraph_payload(paragraph: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": _pid(paragraph),
        "text": clean_text(paragraph.get("text", "")),
        "heading": clean_text(paragraph.get("heading", "")),
        "chapter_number": paragraph.get("chapter_number"),
        "page": paragraph.get("page"),
        "paragraph": paragraph.get("paragraph"),
        "page_paragraph": paragraph.get("page_paragraph"),
        "is_heading": bool(paragraph.get("is_heading")),
        "source_filename": paragraph.get("source_filename", ""),
        "document_role": paragraph.get("document_role", "current"),
        "document_index": paragraph.get("document_index", 0),
    }


def _evidence_from_paragraph(paragraph: Dict[str, Any]) -> Dict[str, Any]:
    payload = _paragraph_payload(paragraph)
    return {
        "text": payload["text"][:850],
        "page": payload["page"],
        "paragraph": payload["paragraph"],
        "page_paragraph": payload["page_paragraph"],
        "heading": payload["heading"],
        "chapter_number": payload["chapter_number"],
        "is_heading": payload["is_heading"],
        "source_filename": payload["source_filename"],
        "document_role": payload["document_role"],
        "document_index": payload["document_index"],
        "paragraph_id": payload["id"],
        "matched_terms": [],
        "adequacy_terms": [],
        "rank_score": 1,
    }


def _all_rows(review: Dict[str, Any]) -> List[Dict[str, Any]]:
    return (
        list(review.get("results") or [])
        + list(review.get("alignment_results") or [])
        + list(review.get("revision_results") or [])
    )


def _deterministic_sample(code: str, rate: float) -> bool:
    if rate <= 0:
        return False
    digest = hashlib.sha256(code.encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) / 0xFFFFFFFF
    return bucket < rate


def _candidate_rows(review: Dict[str, Any], mode: str, config: HybridAIConfig) -> List[Dict[str, Any]]:
    rows = []
    for row in _all_rows(review):
        if row.get("status") == STATUS_NA:
            continue
        status = row.get("status")
        confidence = float(row.get("confidence") or 0)
        should_review = (
            status in ACTIONABLE
            or bool(row.get("critical"))
            or confidence < config.confidence_threshold
            or row.get("review_type") in {"alignment", "supervisor_comment"}
            or _deterministic_sample(str(row.get("code", "")), config.verify_meets_sample_rate)
        )
        if mode == "premium" and status != STATUS_NA:
            should_review = True
        if should_review:
            rows.append(row)
    rows.sort(key=lambda r: (
        CRITICALITY_ORDER.get(r.get("severity", "minor"), 9),
        0 if r.get("status") in ACTIONABLE else 1,
        str(r.get("code", "")),
    ))
    return rows


def _heading_match(value: str, headings: Sequence[str]) -> bool:
    low = normalised(value)
    return any(normalised(h) in low or low in normalised(h) for h in headings if normalised(h))


def _select_context_for_row(
    row: Dict[str, Any],
    paragraph_index: Dict[str, Dict[str, Any]],
    ordered_paragraphs: Sequence[Dict[str, Any]],
    max_chars: int,
) -> List[Dict[str, Any]]:
    selected_ids: List[str] = []
    ordered_ids = [_pid(p) for p in ordered_paragraphs]
    position = {pid: i for i, pid in enumerate(ordered_ids)}

    for evidence in row.get("evidence") or []:
        role = evidence.get("document_role", "current")
        paragraph_number = evidence.get("paragraph")
        document_index = evidence.get("document_index", 0)
        if paragraph_number is None:
            continue
        if role == "previous":
            pid = f"C{int(document_index or 0)}P{int(paragraph_number)}"
        elif role == "original":
            pid = f"O{int(paragraph_number)}"
        else:
            pid = f"P{int(paragraph_number)}"
        if pid in paragraph_index:
            selected_ids.append(pid)
            idx = position.get(pid)
            if idx is not None:
                selected_ids.extend(ordered_ids[max(0, idx - 1): min(len(ordered_ids), idx + 2)])

    headings = row.get("headings") or []
    if headings:
        for paragraph in ordered_paragraphs:
            if _heading_match(paragraph.get("heading", ""), headings) or (
                paragraph.get("is_heading") and _heading_match(paragraph.get("text", ""), headings)
            ):
                selected_ids.append(_pid(paragraph))
                idx = position.get(_pid(paragraph))
                if idx is not None:
                    selected_ids.extend(ordered_ids[idx: min(len(ordered_ids), idx + 5)])

    # Cross-chapter and revised-comment checks need evidence from each relevant role.
    if row.get("review_type") in {"alignment", "supervisor_comment"}:
        for role in ("previous", "original", "current"):
            for paragraph in ordered_paragraphs:
                if paragraph.get("document_role", "current") == role and not paragraph.get("is_heading"):
                    selected_ids.append(_pid(paragraph))
                    break

    # If the local engine found nothing, include a small section-aware fallback.
    if not selected_ids:
        target_chapter = row.get("chapter_number") or 0
        for paragraph in ordered_paragraphs:
            if target_chapter and paragraph.get("chapter_number") not in {None, target_chapter}:
                continue
            if paragraph.get("is_heading"):
                continue
            selected_ids.append(_pid(paragraph))
            if len(selected_ids) >= 5:
                break

    output = []
    total = 0
    for pid in dict.fromkeys(selected_ids):
        paragraph = paragraph_index.get(pid)
        if not paragraph:
            continue
        payload = _paragraph_payload(paragraph)
        size = len(payload["text"]) + len(payload["heading"]) + 100
        if output and total + size > max_chars:
            break
        output.append(payload)
        total += size
    return output


def _key_paragraphs_for_map(runtime: Dict[str, Any], max_chars: int) -> str:
    paragraphs = (
        list(runtime.get("context_paragraphs") or [])
        + list(runtime.get("current_paragraphs") or [])
        + list(runtime.get("original_paragraphs") or [])
    )
    keywords = (
        "problem", "purpose", "objective", "research question", "hypothesis", "theory",
        "conceptual framework", "variable", "population", "sample", "data analysis",
        "result", "finding", "conclusion", "recommendation",
    )
    preferred = [
        p for p in paragraphs
        if any(term in normalised((p.get("heading") or "") + " " + (p.get("text") or "")) for term in keywords)
    ]
    candidates = preferred or paragraphs
    lines = []
    total = 0
    for paragraph in candidates:
        text = clean_text(paragraph.get("text", ""))
        if not text:
            continue
        line = f'[{_pid(paragraph)} | {paragraph.get("document_role", "current")} | {clean_text(paragraph.get("heading", ""))}] {text}'
        if lines and total + len(line) > max_chars:
            break
        lines.append(line)
        total += len(line)
    return "\n".join(lines)


def _batch(values: Sequence[Any], size: int) -> List[List[Any]]:
    return [list(values[index:index + size]) for index in range(0, len(values), size)]


def _row_packet(
    row: Dict[str, Any],
    paragraph_index: Dict[str, Dict[str, Any]],
    ordered_paragraphs: Sequence[Dict[str, Any]],
    config: HybridAIConfig,
) -> Dict[str, Any]:
    return {
        "code": row.get("code", ""),
        "official_criterion": row.get("item", ""),
        "section": row.get("section", ""),
        "critical": bool(row.get("critical")),
        "local_screening": {
            "status": row.get("status", STATUS_MANUAL),
            "confidence": row.get("confidence", 0),
            "assessment": row.get("comment", ""),
        },
        "evidence_paragraphs": _select_context_for_row(
            row,
            paragraph_index,
            ordered_paragraphs,
            config.max_context_chars_per_rule,
        ),
    }


def _review_prompt(
    *,
    review: Dict[str, Any],
    rows: Sequence[Dict[str, Any]],
    paragraph_index: Dict[str, Dict[str, Any]],
    ordered_paragraphs: Sequence[Dict[str, Any]],
    config: HybridAIConfig,
    document_map: Optional[Dict[str, Any]],
) -> str:
    summary = review.get("summary", {})
    packet = {
        "academic_level": summary.get("academic_level"),
        "research_approach": summary.get("research_approach"),
        "document_label": summary.get("document_label"),
        "submission_stage": summary.get("submission_stage"),
        "document_map": document_map or {},
        "criteria": [
            _row_packet(row, paragraph_index, ordered_paragraphs, config)
            for row in rows
        ],
    }
    return json.dumps(packet, ensure_ascii=False)


def _verification_prompt(
    *,
    review: Dict[str, Any],
    rows: Sequence[Dict[str, Any]],
    decisions: Dict[str, Dict[str, Any]],
    paragraph_index: Dict[str, Dict[str, Any]],
    ordered_paragraphs: Sequence[Dict[str, Any]],
    config: HybridAIConfig,
    document_map: Optional[Dict[str, Any]],
) -> str:
    base = json.loads(_review_prompt(
        review=review,
        rows=rows,
        paragraph_index=paragraph_index,
        ordered_paragraphs=ordered_paragraphs,
        config=config,
        document_map=document_map,
    ))
    for criterion in base["criteria"]:
        criterion["proposed_decision"] = decisions.get(criterion["code"], {})
    return json.dumps(base, ensure_ascii=False)


def _adjudication_prompt(
    *,
    review: Dict[str, Any],
    row: Dict[str, Any],
    deepseek_decision: Dict[str, Any],
    openai_decision: Dict[str, Any],
    paragraph_index: Dict[str, Dict[str, Any]],
    ordered_paragraphs: Sequence[Dict[str, Any]],
    config: HybridAIConfig,
) -> str:
    packet = _row_packet(row, paragraph_index, ordered_paragraphs, config)
    packet["deepseek_decision"] = deepseek_decision
    packet["openai_verification"] = openai_decision
    packet["academic_level"] = review.get("summary", {}).get("academic_level")
    packet["research_approach"] = review.get("summary", {}).get("research_approach")
    return json.dumps({"criteria": [packet]}, ensure_ascii=False)


def _usage_cost(usage: AIUsageRecord, config: HybridAIConfig) -> AIUsageRecord:
    uncached = max(0, usage.input_tokens - usage.cached_input_tokens)
    model = usage.model
    if usage.provider == "deepseek" and model == config.deepseek_extract_model:
        input_price = config.deepseek_flash_input_price
        cached_price = config.deepseek_flash_cached_input_price
        output_price = config.deepseek_flash_output_price
    elif usage.provider == "deepseek":
        input_price = config.deepseek_pro_input_price
        cached_price = config.deepseek_pro_cached_input_price
        output_price = config.deepseek_pro_output_price
    elif model == config.openai_premium_model:
        input_price = config.openai_premium_input_price
        cached_price = config.openai_premium_cached_input_price
        output_price = config.openai_premium_output_price
    else:
        input_price = config.openai_verify_input_price
        cached_price = config.openai_verify_cached_input_price
        output_price = config.openai_verify_output_price
    cost = (
        uncached / 1_000_000 * input_price
        + usage.cached_input_tokens / 1_000_000 * cached_price
        + usage.output_tokens / 1_000_000 * output_price
    )
    return usage.model_copy(update={"estimated_cost_usd": round(cost, 6)})


def _validate_decision(
    decision: Dict[str, Any],
    allowed_codes: set[str],
    paragraph_index: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    try:
        parsed = AIDecision.model_validate(decision).model_dump()
    except Exception:
        return None
    if parsed["code"] not in allowed_codes:
        return None
    parsed["evidence_paragraph_ids"] = [
        pid for pid in parsed.get("evidence_paragraph_ids", []) if pid in paragraph_index
    ]
    quote = clean_text(parsed.get("problematic_quote", ""))
    if quote and not any(quote in clean_text(paragraph_index[pid].get("text", "")) for pid in parsed["evidence_paragraph_ids"]):
        parsed["problematic_quote"] = ""
    if parsed["status"] == STATUS_MEETS and not parsed["evidence_paragraph_ids"]:
        parsed["status"] = STATUS_MANUAL
        parsed["confidence"] = min(parsed["confidence"], 0.55)
        parsed["expert_assessment"] = (
            "The model proposed that the criterion was met but did not identify a valid source paragraph. "
            "Manual confirmation is required."
        )
        parsed["required_action"] = "Confirm the criterion against the source document and record the exact evidence paragraph."
    return parsed


def _apply_decision(
    row: Dict[str, Any],
    decision: Dict[str, Any],
    paragraph_index: Dict[str, Dict[str, Any]],
    *,
    provider: str,
    model: str,
    verified: bool = False,
    verification_provider: str = "",
    verification_model: str = "",
    disagreement: bool = False,
) -> None:
    if "local_status" not in row:
        row["local_status"] = row.get("status")
        row["local_status_label"] = row.get("status_label")
        row["local_confidence"] = row.get("confidence")
        row["local_comment"] = row.get("comment")
        row["local_required_action"] = row.get("required_action")

    evidence = [
        _evidence_from_paragraph(paragraph_index[pid])
        for pid in decision.get("evidence_paragraph_ids", [])
        if pid in paragraph_index
    ]
    row["status"] = decision["status"]
    row["status_label"] = STATUS_LABELS[decision["status"]]
    row["score"] = STATUS_SCORES[decision["status"]]
    row["severity"] = decision["severity"]
    row["confidence"] = round(float(decision["confidence"]), 2)
    row["comment"] = clean_text(decision["expert_assessment"])
    row["required_action"] = clean_text(decision["required_action"])
    if evidence:
        row["evidence"] = evidence
    row["ai_reviewed"] = True
    row["ai_primary_provider"] = provider
    row["ai_primary_model"] = model
    row["ai_verified"] = verified
    row["ai_verification_provider"] = verification_provider
    row["ai_verification_model"] = verification_model
    row["ai_disagreement"] = disagreement
    row["ai_problematic_quote"] = clean_text(decision.get("problematic_quote", ""))
    row["ai_verification_reason"] = clean_text(decision.get("verification_reason", ""))


def _needs_openai(
    row: Dict[str, Any],
    decision: Dict[str, Any],
    config: HybridAIConfig,
    mode: str,
) -> Tuple[bool, str]:
    reasons = []
    if mode == "premium":
        reasons.append("premium dual review")
    if decision.get("needs_openai_verification"):
        reasons.append(decision.get("verification_reason") or "primary reviewer requested verification")
    if float(decision.get("confidence") or 0) < config.confidence_threshold:
        reasons.append("confidence below threshold")
    if config.verify_critical and row.get("critical"):
        reasons.append("critical checklist criterion")
    if config.verify_manual and decision.get("status") == STATUS_MANUAL:
        reasons.append("manual-review decision")
    local_status = row.get("local_status", row.get("status"))
    if config.verify_disagreement and local_status != decision.get("status"):
        reasons.append("AI and local screening disagree")
    return bool(reasons), "; ".join(dict.fromkeys(reasons))


def _score_checklist(results: Sequence[Dict[str, Any]]) -> Tuple[float, Dict[str, float]]:
    by_group: Dict[str, List[float]] = defaultdict(list)
    for row in results:
        value = row.get("score")
        if value is not None:
            by_group[row["chapter_key"]].append(float(value))
    chapter_scores: Dict[str, float] = {}
    numerator = 0.0
    denominator = 0.0
    for key, values in by_group.items():
        score = round(sum(values) / len(values) * 100, 1) if values else 0.0
        chapter_scores[key] = score
        weight = CHAPTERS[key]["weight"]
        numerator += score * weight
        denominator += weight
    return (round(numerator / denominator, 1) if denominator else 0.0), chapter_scores


def _critical_gate(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    failed = [
        row for row in rows
        if row.get("critical") and row.get("status") in ACTIONABLE
    ]
    return {
        "blocked": bool(failed),
        "failed_count": len(failed),
        "failed_rules": [
            {"code": r.get("code"), "item": r.get("item"), "status": r.get("status_label")}
            for r in failed
        ],
    }


def _priority_actions(rows: Sequence[Dict[str, Any]], limit: int = 12) -> List[Dict[str, Any]]:
    actionable = [row for row in rows if row.get("status") in ACTIONABLE]
    actionable.sort(key=lambda row: (
        CRITICALITY_ORDER.get(row.get("severity", "minor"), 9),
        0 if row.get("status") == STATUS_MISSING else 1,
        str(row.get("code", "")),
    ))
    return [
        {
            "code": row.get("code", ""),
            "section": row.get("section", ""),
            "severity": row.get("severity", "moderate"),
            "status": row.get("status_label", ""),
            "action": row.get("required_action", ""),
        }
        for row in actionable[:limit]
    ]


def _recompute(review: Dict[str, Any]) -> None:
    summary = review["summary"]
    checklist_value, chapter_scores = _score_checklist(review.get("results") or [])
    align_value = alignment_score(review.get("alignment_results") or [])
    revision_value = revision_score(review.get("revision_results") or []) if review.get("revision_results") else None

    if summary.get("revised_mode") and revision_value is not None and align_value is not None:
        overall = round(checklist_value * 0.65 + align_value * 0.15 + revision_value * 0.20, 1)
    elif summary.get("revised_mode") and revision_value is not None:
        overall = round(checklist_value * 0.80 + revision_value * 0.20, 1)
    elif align_value is not None:
        overall = round(checklist_value * 0.80 + align_value * 0.20, 1)
    else:
        overall = checklist_value

    rows = _all_rows(review)
    gates = _critical_gate(rows)
    revision_gate_blocked = any(row.get("status") == STATUS_MISSING for row in review.get("revision_results") or [])
    revision_manual_pending = any(row.get("status") == STATUS_MANUAL for row in review.get("revision_results") or [])
    readiness = readiness_band(overall)
    if revision_gate_blocked:
        readiness = {
            "label": "Further revision required",
            "meaning": "One or more supervisor comments have not been addressed in the revised chapter.",
        }
    elif summary.get("revised_mode") and revision_manual_pending and overall >= 70:
        readiness = {
            "label": "Supervisor confirmation required",
            "meaning": "The revision is broadly developed, but one or more supervisor comments require manual confirmation.",
        }
    elif gates["blocked"] and overall >= 85:
        readiness = {
            "label": "Revision required before approval",
            "meaning": "The numerical score is high, but one or more critical requirements remain unresolved.",
        }

    counts: Dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row.get("status")] += 1
    revision_summary = revision_counts(review.get("revision_results") or [])
    summary.update({
        "checklist_score": checklist_value,
        "alignment_score": align_value,
        "revision_score": revision_value,
        "overall_score": overall,
        "readiness_label": readiness["label"],
        "readiness_meaning": readiness["meaning"],
        "critical_gate_blocked": gates["blocked"],
        "critical_failed": gates["failed_count"],
        "revision_gate_blocked": revision_gate_blocked,
        "revision_manual_pending": revision_manual_pending,
        "meets": counts[STATUS_MEETS],
        "partial": counts[STATUS_PARTIAL],
        "missing": counts[STATUS_MISSING],
        "manual": counts[STATUS_MANUAL],
        "not_applicable": counts[STATUS_NA],
        "revision_addressed": revision_summary["addressed"],
        "revision_partly_addressed": revision_summary["partly_addressed"],
        "revision_not_addressed": revision_summary["not_addressed"],
        "revision_manual": revision_summary["manual"],
    })
    review["chapter_scores"] = chapter_scores
    review["critical_gates"] = gates
    review["priority_actions"] = _priority_actions(rows)


async def _run_limited(coroutines: Sequence[Any], limit: int) -> List[Any]:
    semaphore = asyncio.Semaphore(max(1, limit))

    async def runner(coro):
        async with semaphore:
            return await coro

    return await asyncio.gather(*(runner(coro) for coro in coroutines), return_exceptions=True)


async def enrich_review_with_hybrid_ai(
    review: Dict[str, Any],
    runtime: Dict[str, Any],
    *,
    requested_mode: str,
    config: Optional[HybridAIConfig] = None,
) -> Dict[str, Any]:
    config = config or HybridAIConfig.from_env()
    resolved_mode = config.resolve_mode(requested_mode)
    summary = review["summary"]

    ai_summary: Dict[str, Any] = {
        "requested_mode": requested_mode,
        "resolved_mode": resolved_mode,
        "enabled": resolved_mode != "local",
        "deepseek_configured": config.deepseek_configured,
        "openai_configured": config.openai_configured,
        "primary_reviewed_count": 0,
        "openai_verified_count": 0,
        "premium_adjudicated_count": 0,
        "disagreement_count": 0,
        "calls": 0,
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "estimated_cost_usd": 0.0,
        "models_used": [],
        "warnings": [],
    }
    review["ai_review"] = ai_summary
    summary["ai_review_mode"] = resolved_mode

    if resolved_mode == "local":
        if requested_mode == "auto" and config.enabled:
            ai_summary["warnings"].append("No provider API keys were configured. The local checklist engine was used.")
        return review

    ordered_paragraphs = (
        list(runtime.get("context_paragraphs") or [])
        + list(runtime.get("current_paragraphs") or [])
        + list(runtime.get("original_paragraphs") or [])
    )
    paragraph_index = {_pid(p): p for p in ordered_paragraphs if p.get("paragraph")}
    rows_by_code = {str(row.get("code")): row for row in _all_rows(review)}
    candidates = _candidate_rows(review, resolved_mode, config)
    if not candidates:
        ai_summary["warnings"].append("No checklist item required AI escalation after local screening.")
        return review

    usage_records: List[AIUsageRecord] = []
    deepseek = DeepSeekProvider(config) if config.deepseek_configured else None
    openai = OpenAIProvider(config) if config.openai_configured else None
    document_map: Optional[Dict[str, Any]] = None

    if deepseek and config.use_flash_document_map:
        map_text = _key_paragraphs_for_map(runtime, config.max_map_input_chars)
        if map_text:
            try:
                result = await deepseek.complete_json(
                    model=config.deepseek_extract_model,
                    system_prompt=DOCUMENT_MAP_SYSTEM_PROMPT,
                    user_prompt=map_text,
                    schema_model=DocumentMap,
                    purpose="document_map",
                    thinking=False,
                )
                document_map = result.data
                usage_records.append(_usage_cost(result.usage, config))
                review["ai_document_map"] = document_map
            except Exception as exc:
                ai_summary["warnings"].append(f"DeepSeek Flash document mapping failed: {exc}")
                if config.strict_failure:
                    raise

    primary_decisions: Dict[str, Dict[str, Any]] = {}
    candidate_batches = _batch(candidates, config.max_rules_per_batch)

    if resolved_mode in {"deepseek_only", "hybrid", "premium"}:
        if not deepseek:
            raise ValueError("DeepSeek is required for the selected review mode.")
        calls = [
            deepseek.complete_json(
                model=config.deepseek_review_model,
                system_prompt=REVIEW_SYSTEM_PROMPT,
                user_prompt=_review_prompt(
                    review=review,
                    rows=batch,
                    paragraph_index=paragraph_index,
                    ordered_paragraphs=ordered_paragraphs,
                    config=config,
                    document_map=document_map,
                ),
                schema_model=DecisionBatch,
                purpose="primary_review",
                thinking=True,
            )
            for batch in candidate_batches
        ]
        responses = await _run_limited(calls, config.max_parallel_calls)
        for batch, response in zip(candidate_batches, responses):
            allowed = {str(row.get("code")) for row in batch}
            if isinstance(response, Exception):
                ai_summary["warnings"].append(f"DeepSeek review batch failed: {response}")
                if config.strict_failure:
                    raise response
                continue
            usage_records.append(_usage_cost(response.usage, config))
            for raw in response.data.get("decisions", []):
                parsed = _validate_decision(raw, allowed, paragraph_index)
                if parsed:
                    primary_decisions[parsed["code"]] = parsed
                    row = rows_by_code.get(parsed["code"])
                    if row:
                        _apply_decision(
                            row,
                            parsed,
                            paragraph_index,
                            provider="deepseek",
                            model=config.deepseek_review_model,
                        )
    elif resolved_mode == "openai_only":
        if not openai:
            raise ValueError("OpenAI is required for the selected review mode.")
        calls = [
            openai.complete_json(
                model=config.openai_verify_model,
                system_prompt=REVIEW_SYSTEM_PROMPT,
                user_prompt=_review_prompt(
                    review=review,
                    rows=batch,
                    paragraph_index=paragraph_index,
                    ordered_paragraphs=ordered_paragraphs,
                    config=config,
                    document_map=document_map,
                ),
                schema_model=DecisionBatch,
                purpose="primary_review",
            )
            for batch in candidate_batches
        ]
        responses = await _run_limited(calls, config.max_parallel_calls)
        for batch, response in zip(candidate_batches, responses):
            allowed = {str(row.get("code")) for row in batch}
            if isinstance(response, Exception):
                ai_summary["warnings"].append(f"OpenAI review batch failed: {response}")
                if config.strict_failure:
                    raise response
                continue
            usage_records.append(_usage_cost(response.usage, config))
            for raw in response.data.get("decisions", []):
                parsed = _validate_decision(raw, allowed, paragraph_index)
                if parsed:
                    primary_decisions[parsed["code"]] = parsed
                    row = rows_by_code.get(parsed["code"])
                    if row:
                        _apply_decision(
                            row,
                            parsed,
                            paragraph_index,
                            provider="openai",
                            model=config.openai_verify_model,
                            verified=True,
                            verification_provider="openai",
                            verification_model=config.openai_verify_model,
                        )

    ai_summary["primary_reviewed_count"] = len(primary_decisions)

    verification_candidates: List[Tuple[Dict[str, Any], Dict[str, Any], str]] = []
    if resolved_mode in {"hybrid", "premium"} and openai:
        for code, decision in primary_decisions.items():
            row = rows_by_code.get(code)
            if not row:
                continue
            needs, reason = _needs_openai(row, decision, config, resolved_mode)
            if needs:
                verification_candidates.append((row, decision, reason))

    verification_decisions: Dict[str, Dict[str, Any]] = {}
    if verification_candidates:
        verify_batches = _batch(verification_candidates, config.max_rules_per_batch)
        calls = []
        for batch in verify_batches:
            rows = [item[0] for item in batch]
            decisions = {item[1]["code"]: {**item[1], "routing_reason": item[2]} for item in batch}
            calls.append(openai.complete_json(
                model=config.openai_verify_model,
                system_prompt=VERIFY_SYSTEM_PROMPT,
                user_prompt=_verification_prompt(
                    review=review,
                    rows=rows,
                    decisions=decisions,
                    paragraph_index=paragraph_index,
                    ordered_paragraphs=ordered_paragraphs,
                    config=config,
                    document_map=document_map,
                ),
                schema_model=DecisionBatch,
                purpose="verification",
            ))
        responses = await _run_limited(calls, config.max_parallel_calls)
        for batch, response in zip(verify_batches, responses):
            allowed = {item[1]["code"] for item in batch}
            if isinstance(response, Exception):
                ai_summary["warnings"].append(f"OpenAI verification batch failed: {response}")
                if config.strict_failure:
                    raise response
                continue
            usage_records.append(_usage_cost(response.usage, config))
            for raw in response.data.get("decisions", []):
                parsed = _validate_decision(raw, allowed, paragraph_index)
                if not parsed:
                    continue
                verification_decisions[parsed["code"]] = parsed
                row = rows_by_code.get(parsed["code"])
                primary = primary_decisions.get(parsed["code"], {})
                disagreement = parsed.get("status") != primary.get("status")
                if disagreement:
                    ai_summary["disagreement_count"] += 1
                if row:
                    _apply_decision(
                        row,
                        parsed,
                        paragraph_index,
                        provider="deepseek",
                        model=config.deepseek_review_model,
                        verified=True,
                        verification_provider="openai",
                        verification_model=config.openai_verify_model,
                        disagreement=disagreement,
                    )
        ai_summary["openai_verified_count"] = len(verification_decisions)

    if resolved_mode == "premium" and openai and config.openai_premium_model:
        disputed = [
            code for code, verified in verification_decisions.items()
            if verified.get("status") != primary_decisions.get(code, {}).get("status")
            or float(verified.get("confidence") or 0) < config.confidence_threshold
        ]
        for code in disputed:
            row = rows_by_code.get(code)
            if not row:
                continue
            try:
                result = await openai.complete_json(
                    model=config.openai_premium_model,
                    system_prompt=ADJUDICATE_SYSTEM_PROMPT,
                    user_prompt=_adjudication_prompt(
                        review=review,
                        row=row,
                        deepseek_decision=primary_decisions[code],
                        openai_decision=verification_decisions[code],
                        paragraph_index=paragraph_index,
                        ordered_paragraphs=ordered_paragraphs,
                        config=config,
                    ),
                    schema_model=DecisionBatch,
                    purpose="premium_adjudication",
                    reasoning_effort="high",
                )
                usage_records.append(_usage_cost(result.usage, config))
                parsed_rows = result.data.get("decisions", [])
                if parsed_rows:
                    parsed = _validate_decision(parsed_rows[0], {code}, paragraph_index)
                    if parsed:
                        _apply_decision(
                            row,
                            parsed,
                            paragraph_index,
                            provider="deepseek",
                            model=config.deepseek_review_model,
                            verified=True,
                            verification_provider="openai",
                            verification_model=config.openai_premium_model,
                            disagreement=True,
                        )
                        ai_summary["premium_adjudicated_count"] += 1
            except Exception as exc:
                ai_summary["warnings"].append(f"Premium adjudication failed for {code}: {exc}")
                if config.strict_failure:
                    raise

    _recompute(review)

    ai_summary["calls"] = len(usage_records)
    ai_summary["input_tokens"] = sum(item.input_tokens for item in usage_records)
    ai_summary["cached_input_tokens"] = sum(item.cached_input_tokens for item in usage_records)
    ai_summary["output_tokens"] = sum(item.output_tokens for item in usage_records)
    ai_summary["estimated_cost_usd"] = round(sum(item.estimated_cost_usd for item in usage_records), 6)
    ai_summary["models_used"] = list(dict.fromkeys(item.model for item in usage_records))
    ai_summary["usage"] = [item.model_dump() for item in usage_records]
    summary["ai_reviewed_count"] = ai_summary["primary_reviewed_count"]
    summary["ai_verified_count"] = ai_summary["openai_verified_count"]
    summary["ai_estimated_cost_usd"] = ai_summary["estimated_cost_usd"]
    return review
