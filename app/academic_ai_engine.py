from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .ai_config import AIConfigurationError, HybridAIConfig
from .ai_prompts import ACADEMIC_REVIEW_SYSTEM_PROMPT, ACADEMIC_VERIFY_SYSTEM_PROMPT
from .ai_providers import AIProviderError, DeepSeekProvider, OpenAIProvider, ProviderResult
from .ai_schemas import (
    AIUsageRecord,
    AcademicIssue,
    AcademicSectionReview,
    AcademicVerificationBatch,
)
from .document_parser import clean_text, normalised

SEVERITY_WEIGHT = {"critical": 16.0, "major": 8.0, "moderate": 3.5, "minor": 1.0}
SEVERITY_ORDER = {"critical": 0, "major": 1, "moderate": 2, "minor": 3}
ACTIONABLE_STATUS = {
    "critical": ("does_not_meet_requirement", "Critical revision"),
    "major": ("does_not_meet_requirement", "Major revision"),
    "moderate": ("partly_meets_requirement", "Revision required"),
    "minor": ("partly_meets_requirement", "Minor correction"),
}

CHAPTER_DIMENSIONS: Dict[int, List[str]] = {
    1: [
        "title accuracy and scope", "background progression and evidence", "research problem and gap",
        "purpose, objectives, questions and hypotheses", "significance and contribution", "scope and limitations",
        "definitions and chapter organisation", "terminology consistency", "academic writing and citations",
    ],
    2: [
        "conceptual definitions and construct boundaries", "theory selection and application", "critical empirical synthesis",
        "objective-driven organisation", "contradictions and limitations in prior studies", "research gap",
        "hypothesis development and conceptual framework", "source quality, recency and citation accuracy", "academic writing",
    ],
    3: [
        "research philosophy and design fit", "study setting, population and sampling", "sample-size justification",
        "instrument development and measurement", "validity, reliability or qualitative trustworthiness", "data collection",
        "data preparation and analysis mapped to objectives", "model specification and assumptions", "ethics and reproducibility",
        "academic writing and methodological consistency",
    ],
    4: [
        "data quality and preliminary analysis", "objective-by-objective presentation", "accuracy of tables and figures",
        "statistical or qualitative interpretation", "hypothesis decisions", "effect sizes and uncertainty",
        "discussion against theory and prior studies", "unexpected findings and alternative explanations",
        "consistency with Chapter Three", "academic writing and reporting standards",
    ],
    5: [
        "summary by objectives", "conclusions supported by findings", "theoretical, practical and policy implications",
        "recommendations traceable to findings", "contribution to knowledge", "limitations and future research",
        "absence of new evidence", "consistency with the research problem", "academic writing and presentation",
    ],
}

KEY_ALIGNMENT_TERMS = (
    "statement of the problem", "problem statement", "purpose of the study", "research objective",
    "objective of the study", "specific objective", "research question", "hypothesis", "theoretical",
    "conceptual framework", "methodology", "research design", "population", "sampling", "data analysis",
    "result", "finding", "conclusion", "recommendation",
)


def _pid(paragraph: Dict[str, Any]) -> str:
    role = paragraph.get("document_role", "current")
    number = int(paragraph.get("paragraph") or 0)
    if role == "previous":
        return f'C{int(paragraph.get("document_index") or 0)}P{number}'
    if role == "original":
        return f'O{number}'
    return f'P{number}'


def _payload(paragraph: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": _pid(paragraph),
        "text": clean_text(paragraph.get("text", "")),
        "heading": clean_text(paragraph.get("heading", "")),
        "chapter_number": paragraph.get("chapter_number"),
        "page": paragraph.get("page"),
        "paragraph": paragraph.get("paragraph"),
        "is_heading": bool(paragraph.get("is_heading")),
        "source_filename": paragraph.get("source_filename", ""),
        "document_role": paragraph.get("document_role", "current"),
        "document_index": paragraph.get("document_index", 0),
    }


def _evidence(paragraph: Dict[str, Any]) -> Dict[str, Any]:
    p = _payload(paragraph)
    return {
        "text": p["text"][:1200],
        "page": p["page"],
        "paragraph": p["paragraph"],
        "page_paragraph": paragraph.get("page_paragraph"),
        "heading": p["heading"],
        "chapter_number": p["chapter_number"],
        "is_heading": p["is_heading"],
        "source_filename": p["source_filename"],
        "document_role": p["document_role"],
        "document_index": p["document_index"],
        "paragraph_id": p["id"],
        "matched_terms": [],
        "adequacy_terms": [],
        "rank_score": 1,
    }


def _normalise_heading(value: str) -> str:
    low = normalised(value)
    low = re.sub(r"^\d+(?:\.\d+){0,3}\s+", "", low)
    return low or "Untitled section"


def _section_groups(paragraphs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    for paragraph in paragraphs:
        text = clean_text(paragraph.get("text", ""))
        if not text:
            continue
        if current is None or paragraph.get("is_heading"):
            heading = text if paragraph.get("is_heading") else (paragraph.get("heading") or "Opening material")
            current = {"heading": heading, "paragraphs": []}
            groups.append(current)
        current["paragraphs"].append(paragraph)
    return groups


def _split_group(group: Dict[str, Any], max_chars: int) -> List[Dict[str, Any]]:
    paragraphs = group["paragraphs"]
    chunks: List[Dict[str, Any]] = []
    current: List[Dict[str, Any]] = []
    total = 0
    part = 1
    for paragraph in paragraphs:
        size = len(clean_text(paragraph.get("text", ""))) + 120
        if current and total + size > max_chars:
            chunks.append({"heading": group["heading"], "part": part, "paragraphs": current})
            part += 1
            # One-paragraph overlap preserves local continuity.
            current = current[-1:]
            total = sum(len(clean_text(p.get("text", ""))) + 120 for p in current)
        current.append(paragraph)
        total += size
    if current:
        chunks.append({"heading": group["heading"], "part": part, "paragraphs": current})
    return chunks


def _guide_expectations(review: Dict[str, Any], heading: str) -> List[str]:
    target = _normalise_heading(heading)
    selected: List[str] = []
    for row in review.get("results") or []:
        row_headings = [_normalise_heading(v) for v in row.get("headings") or []]
        row_section = _normalise_heading(row.get("section", ""))
        if any(h in target or target in h for h in row_headings if h != "Untitled section") or (
            row_section != "Untitled section" and (row_section in target or target in row_section)
        ):
            selected.append(clean_text(row.get("item", "")))
    return list(dict.fromkeys(x for x in selected if x))[:16]


def _chapter_dimensions(review: Dict[str, Any]) -> List[str]:
    summary = review.get("summary") or {}
    selected = int(summary.get("selected_chapter") or 0)
    if summary.get("proposal_mode"):
        return list(dict.fromkeys(CHAPTER_DIMENSIONS[1] + CHAPTER_DIMENSIONS[2] + CHAPTER_DIMENSIONS[3]))
    if summary.get("review_scope") == "full_thesis":
        values: List[str] = []
        for number in range(1, 6):
            values.extend(CHAPTER_DIMENSIONS[number])
        return list(dict.fromkeys(values))
    return CHAPTER_DIMENSIONS.get(selected, ["academic coherence", "evidence", "critical analysis", "academic writing"])


def _alignment_audit_paragraphs(runtime: Dict[str, Any], limit_chars: int) -> List[Dict[str, Any]]:
    paragraphs = list(runtime.get("context_paragraphs") or []) + list(runtime.get("current_paragraphs") or [])
    selected: List[Dict[str, Any]] = []
    total = 0
    for paragraph in paragraphs:
        combined = normalised((paragraph.get("heading") or "") + " " + (paragraph.get("text") or ""))
        if not any(term in combined for term in KEY_ALIGNMENT_TERMS):
            continue
        size = len(clean_text(paragraph.get("text", ""))) + 120
        if selected and total + size > limit_chars:
            break
        selected.append(paragraph)
        total += size
    return selected


def _whole_chapter_audit_paragraphs(paragraphs: Sequence[Dict[str, Any]], limit_chars: int) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    total = 0
    for index, paragraph in enumerate(paragraphs):
        combined = normalised((paragraph.get("heading") or "") + " " + (paragraph.get("text") or ""))
        include = (
            index < 4
            or bool(paragraph.get("is_heading"))
            or any(term in combined for term in KEY_ALIGNMENT_TERMS)
        )
        if not include:
            continue
        size = len(clean_text(paragraph.get("text", ""))) + 120
        if selected and total + size > limit_chars:
            break
        selected.append(paragraph)
        total += size
    return selected


def _section_prompt(
    review: Dict[str, Any],
    section: Dict[str, Any],
    document_map: Dict[str, Any],
    *,
    is_alignment_audit: bool = False,
) -> str:
    summary = review.get("summary") or {}
    heading = clean_text(section.get("heading", "Untitled section"))
    packet = {
        "review_context": {
            "academic_level": summary.get("academic_level"),
            "research_approach": summary.get("research_approach"),
            "document_label": summary.get("document_label"),
            "chapter_under_review": summary.get("selected_chapter"),
            "review_stage": summary.get("submission_stage"),
            "section": heading,
            "section_part": section.get("part", 1),
            "cross_chapter_audit": is_alignment_audit,
        },
        "document_map": document_map or {},
        "chapter_review_dimensions": _chapter_dimensions(review),
        "internal_guidance_only_do_not_name_or_number": _guide_expectations(review, heading),
        "paragraphs": [_payload(p) for p in section.get("paragraphs") or []],
    }
    return json.dumps(packet, ensure_ascii=False)


def _valid_issue(issue: Dict[str, Any], paragraph_index: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    try:
        parsed = AcademicIssue.model_validate(issue).model_dump()
    except Exception:
        return None
    parsed["evidence_paragraph_ids"] = [pid for pid in parsed["evidence_paragraph_ids"] if pid in paragraph_index]
    quote = clean_text(parsed.get("problematic_quote", ""))
    if quote:
        matching_ids = [
            pid for pid in parsed["evidence_paragraph_ids"]
            if quote in clean_text(paragraph_index[pid].get("text", ""))
        ]
        if not matching_ids:
            # Preserve the issue, but avoid colouring unrelated text.
            parsed["problematic_quote"] = ""
    if not parsed["evidence_paragraph_ids"]:
        parsed["confidence"] = min(float(parsed["confidence"]), 0.55)
    return parsed


def _issue_signature(issue: Dict[str, Any]) -> str:
    base = "|".join([
        normalised(issue.get("category", "")),
        normalised(issue.get("section", "")),
        normalised(issue.get("problematic_quote", ""))[:180],
        normalised(issue.get("issue_title", "")),
    ])
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _deduplicate_issues(issues: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    output: Dict[str, Dict[str, Any]] = {}
    for issue in issues:
        key = _issue_signature(issue)
        existing = output.get(key)
        if not existing or SEVERITY_ORDER.get(issue.get("severity", "minor"), 9) < SEVERITY_ORDER.get(existing.get("severity", "minor"), 9):
            output[key] = issue
    return sorted(output.values(), key=lambda x: (
        SEVERITY_ORDER.get(x.get("severity", "minor"), 9),
        normalised(x.get("section", "")),
        normalised(x.get("issue_title", "")),
    ))


def _finding_row(issue: Dict[str, Any], paragraph_index: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    severity = issue.get("severity", "moderate")
    status, label = ACTIONABLE_STATUS[severity]
    evidence = [_evidence(paragraph_index[pid]) for pid in issue.get("evidence_paragraph_ids", []) if pid in paragraph_index]
    assessment = clean_text(issue.get("assessment", ""))
    consequence = clean_text(issue.get("academic_consequence", ""))
    comment = assessment
    if consequence:
        comment = f"{assessment} Academic implication: {consequence}"
    section = clean_text(issue.get("section", "")) or "Chapter-wide review"
    return {
        "review_type": "academic_finding",
        "finding_id": issue.get("finding_id", ""),
        "category": issue.get("category", "other"),
        "section": section,
        "item": clean_text(issue.get("issue_title", "Academic issue")),
        "status": status,
        "status_label": label,
        "severity": severity,
        "confidence": round(float(issue.get("confidence") or 0), 2),
        "evidence": evidence,
        "comment": comment,
        "required_action": clean_text(issue.get("required_action", "")),
        "problematic_quote": clean_text(issue.get("problematic_quote", "")),
        "headings": [section],
    }


def _usage_cost(usage: AIUsageRecord, config: HybridAIConfig) -> AIUsageRecord:
    uncached = max(0, usage.input_tokens - usage.cached_input_tokens)
    if usage.provider == "deepseek" and usage.model == config.deepseek_extract_model:
        p_in, p_cache, p_out = config.deepseek_flash_input_price, config.deepseek_flash_cached_input_price, config.deepseek_flash_output_price
    elif usage.provider == "deepseek":
        p_in, p_cache, p_out = config.deepseek_pro_input_price, config.deepseek_pro_cached_input_price, config.deepseek_pro_output_price
    elif usage.model == config.openai_premium_model:
        p_in, p_cache, p_out = config.openai_premium_input_price, config.openai_premium_cached_input_price, config.openai_premium_output_price
    else:
        p_in, p_cache, p_out = config.openai_verify_input_price, config.openai_verify_cached_input_price, config.openai_verify_output_price
    cost = uncached / 1_000_000 * p_in + usage.cached_input_tokens / 1_000_000 * p_cache + usage.output_tokens / 1_000_000 * p_out
    return usage.model_copy(update={"estimated_cost_usd": round(cost, 6)})


async def _run_limited(coroutines: Sequence[Any], limit: int) -> List[Any]:
    semaphore = asyncio.Semaphore(max(1, limit))

    async def runner(coro):
        async with semaphore:
            return await coro

    return await asyncio.gather(*(runner(coro) for coro in coroutines), return_exceptions=True)


def _verification_prompt(
    review: Dict[str, Any],
    section: Dict[str, Any],
    primary: Dict[str, Any],
    document_map: Dict[str, Any],
) -> str:
    packet = json.loads(_section_prompt(review, section, document_map, is_alignment_audit=bool(section.get("alignment_audit"))))
    packet["proposed_section_review"] = primary
    packet["verification_instruction"] = (
        "Verify every proposed issue. Return one verification for each finding_id. "
        "Also return any high-impact issue missed by the primary reviewer."
    )
    return json.dumps(packet, ensure_ascii=False)


def _apply_verification(primary_issues: List[Dict[str, Any]], verification: Dict[str, Any]) -> List[Dict[str, Any]]:
    by_id = {str(item.get("finding_id")): item for item in primary_issues}
    for value in verification.get("verifications") or []:
        finding_id = str(value.get("finding_id", ""))
        if finding_id not in by_id:
            continue
        if not value.get("keep", True):
            by_id.pop(finding_id, None)
            continue
        source = by_id[finding_id]
        source.update({
            "severity": value.get("severity", source.get("severity")),
            "confidence": value.get("confidence", source.get("confidence")),
            "evidence_paragraph_ids": value.get("evidence_paragraph_ids", source.get("evidence_paragraph_ids")),
            "problematic_quote": value.get("problematic_quote", source.get("problematic_quote")),
            "assessment": value.get("assessment", source.get("assessment")),
            "academic_consequence": value.get("academic_consequence", source.get("academic_consequence")),
            "required_action": value.get("required_action", source.get("required_action")),
        })
    values = list(by_id.values())
    values.extend(verification.get("missed_issues") or [])
    return values


def _academic_score(section_reviews: Sequence[Dict[str, Any]], issues: Sequence[Dict[str, Any]]) -> float:
    weighted_total = 0.0
    weight_sum = 0.0
    for section in section_reviews:
        weight = max(1, int(section.get("paragraph_count") or 1))
        weighted_total += float(section.get("section_score") or 0) * weight
        weight_sum += weight
    score = weighted_total / weight_sum if weight_sum else 0.0
    counts = defaultdict(int)
    for issue in issues:
        counts[issue.get("severity", "minor")] += 1
    # Severity acts as a defensibility gate rather than an unlimited arithmetic penalty.
    if counts["critical"]:
        score = min(score, 54.0)
    elif counts["major"] >= 5:
        score = min(score, 60.0)
    elif counts["major"] >= 3:
        score = min(score, 68.0)
    elif counts["major"]:
        score = min(score, 78.0)
    elif counts["moderate"] >= 6:
        score = min(score, 82.0)
    return round(max(0.0, score), 1)


def _readiness(score: float, issues: Sequence[Dict[str, Any]], incomplete: bool) -> Tuple[str, str]:
    critical = sum(1 for issue in issues if issue.get("severity") == "critical")
    major = sum(1 for issue in issues if issue.get("severity") == "major")
    if incomplete:
        return "Review incomplete", "One or more sections could not be reviewed completely. Do not treat this output as a final academic assessment."
    if critical:
        return "Substantial revision required", f"The chapter contains {critical} critical academic issue(s) that must be resolved before supervisor approval."
    if score >= 85 and major == 0:
        return "Ready after minor refinement", "The chapter is academically sound overall, with targeted refinements still required."
    if score >= 70 and major <= 2:
        return "Revision required", "The chapter has a workable foundation but requires focused academic revision before approval."
    if score >= 55:
        return "Major revision required", "Several important weaknesses affect the chapter's academic adequacy, coherence, or defensibility."
    return "Substantial redevelopment required", "The chapter requires extensive academic redevelopment before it is ready for supervisor approval."


def _overall_assessment(score: float, issues: Sequence[Dict[str, Any]], strengths: Sequence[Dict[str, Any]]) -> str:
    counts = defaultdict(int)
    for issue in issues:
        counts[issue.get("severity", "minor")] += 1
    if counts["critical"]:
        opening = "The chapter has a recognisable study focus, but critical academic weaknesses currently prevent approval."
    elif counts["major"]:
        opening = "The chapter provides a useful foundation, but major revisions are needed to achieve a defensible academic standard."
    elif counts["moderate"]:
        opening = "The chapter is broadly developed, with several areas requiring clearer justification, evidence, and scholarly refinement."
    else:
        opening = "The chapter is academically coherent overall and requires mainly targeted refinement."
    return (
        f"{opening} The review identified {counts['critical']} critical, {counts['major']} major, "
        f"{counts['moderate']} moderate, and {counts['minor']} minor issue(s), alongside {len(strengths)} documented strength(s). "
        f"The academic review score is {score}%."
    )


async def enrich_review_with_academic_ai(
    review: Dict[str, Any],
    runtime: Dict[str, Any],
    *,
    requested_mode: str = "auto",
    config: Optional[HybridAIConfig] = None,
) -> Dict[str, Any]:
    config = config or HybridAIConfig.from_env()
    mode = config.resolve_mode(requested_mode)
    if mode == "local":
        raise AIConfigurationError(
            "The complete academic review requires an AI review provider. Configure the server API keys and redeploy."
        )

    deepseek = DeepSeekProvider(config) if config.deepseek_configured else None
    openai = OpenAIProvider(config) if config.openai_configured else None
    primary_provider = "deepseek" if deepseek is not None else "openai"

    current = list(runtime.get("current_paragraphs") or [])
    context = list(runtime.get("context_paragraphs") or [])
    original = list(runtime.get("original_paragraphs") or [])
    all_paragraphs = current + context + original
    paragraph_index = {_pid(p): p for p in all_paragraphs}

    document_map = review.get("ai_document_map") or (review.get("ai_review") or {}).get("document_map") or {}
    usage_records: List[AIUsageRecord] = []
    existing_usage = (review.get("ai_review") or {}).get("usage") or []

    groups = _section_groups(current)
    max_section_chars = max(9000, min(22000, config.max_context_chars_per_rule * 2))
    sections: List[Dict[str, Any]] = []
    for group in groups:
        sections.extend(_split_group(group, max_section_chars))

    whole_audit = _whole_chapter_audit_paragraphs(current, max(config.max_map_input_chars, 30000))
    if whole_audit:
        sections.append({
            "heading": "Whole-chapter coherence and consistency audit",
            "part": 1,
            "paragraphs": whole_audit,
            "alignment_audit": False,
        })

    if context:
        audit_paragraphs = _alignment_audit_paragraphs(runtime, max(config.max_map_input_chars, 30000))
        if audit_paragraphs:
            sections.append({
                "heading": "Cross-chapter coherence and alignment",
                "part": 1,
                "paragraphs": audit_paragraphs,
                "alignment_audit": True,
            })

    async def primary_call(section: Dict[str, Any]) -> ProviderResult:
        prompt = _section_prompt(
            review,
            section,
            document_map,
            is_alignment_audit=bool(section.get("alignment_audit")),
        )
        if primary_provider == "deepseek":
            return await deepseek.complete_json(
                model=config.deepseek_review_model,
                system_prompt=ACADEMIC_REVIEW_SYSTEM_PROMPT,
                user_prompt=prompt,
                schema_model=AcademicSectionReview,
                purpose="complete_academic_section_review",
                thinking=True,
            )
        return await openai.complete_json(
            model=config.openai_verify_model,
            system_prompt=ACADEMIC_REVIEW_SYSTEM_PROMPT,
            user_prompt=prompt,
            schema_model=AcademicSectionReview,
            purpose="complete_academic_section_review",
            reasoning_effort=config.openai_reasoning_effort,
        )

    primary_results = await _run_limited([primary_call(section) for section in sections], config.max_parallel_calls)
    section_reviews: List[Dict[str, Any]] = []
    failed_sections: List[str] = []

    for section, result in zip(sections, primary_results):
        if isinstance(result, Exception):
            failed_sections.append(clean_text(section.get("heading", "Untitled section")))
            continue
        usage_records.append(_usage_cost(result.usage, config))
        data = result.data
        valid_issues = []
        for issue in data.get("issues") or []:
            valid = _valid_issue(issue, paragraph_index)
            if valid:
                valid_issues.append(valid)
        valid_strengths = []
        for strength in data.get("strengths") or []:
            ids = [pid for pid in strength.get("evidence_paragraph_ids", []) if pid in paragraph_index]
            if ids:
                strength = dict(strength)
                strength["evidence_paragraph_ids"] = ids
                valid_strengths.append(strength)
        section_reviews.append({
            "section_key": f'{clean_text(section.get("heading", ""))}::{section.get("part", 1)}',
            "heading": clean_text(section.get("heading", "Untitled section")),
            "part": section.get("part", 1),
            "paragraph_count": len(section.get("paragraphs") or []),
            "section_score": float(data.get("section_score") or 0),
            "section_assessment": clean_text(data.get("section_assessment", "")),
            "coverage_warning": clean_text(data.get("coverage_warning", "")),
            "strengths": valid_strengths,
            "issues": valid_issues,
            "source_section": section,
        })

    if failed_sections and config.strict_failure:
        raise AIProviderError(
            "The expert review could not complete every section. Failed section(s): " + ", ".join(failed_sections)
        )
    if not section_reviews:
        raise AIProviderError("The expert review service returned no valid section reviews.")

    # OpenAI verifies high-impact or uncertain DeepSeek findings, without repeating every low-risk section.
    if primary_provider == "deepseek" and openai is not None:
        verify_targets = []
        for section_review in section_reviews:
            issues = section_review["issues"]
            should_verify = mode == "premium" or any(
                issue.get("severity") in {"critical", "major"}
                or float(issue.get("confidence") or 0) < config.confidence_threshold
                for issue in issues
            )
            if should_verify and issues:
                verify_targets.append(section_review)

        async def verify_call(section_review: Dict[str, Any]) -> ProviderResult:
            prompt = _verification_prompt(
                review,
                section_review["source_section"],
                {
                    "section_name": section_review["heading"],
                    "section_score": section_review["section_score"],
                    "section_assessment": section_review["section_assessment"],
                    "strengths": section_review["strengths"],
                    "issues": section_review["issues"],
                    "coverage_warning": section_review["coverage_warning"],
                },
                document_map,
            )
            model = config.openai_premium_model if mode == "premium" else config.openai_verify_model
            return await openai.complete_json(
                model=model,
                system_prompt=ACADEMIC_VERIFY_SYSTEM_PROMPT,
                user_prompt=prompt,
                schema_model=AcademicVerificationBatch,
                purpose="academic_finding_verification",
                reasoning_effort="high" if mode == "premium" else config.openai_reasoning_effort,
            )

        verified_results = await _run_limited(
            [verify_call(section_review) for section_review in verify_targets],
            config.max_parallel_calls,
        )
        for section_review, result in zip(verify_targets, verified_results):
            if isinstance(result, Exception):
                if config.strict_failure:
                    raise AIProviderError(f'Quality-control review failed for {section_review["heading"]}: {result}')
                section_review["coverage_warning"] = (
                    section_review.get("coverage_warning", "") + " Independent verification was unavailable."
                ).strip()
                continue
            usage_records.append(_usage_cost(result.usage, config))
            merged = _apply_verification(section_review["issues"], result.data)
            section_review["issues"] = [
                valid for item in merged if (valid := _valid_issue(item, paragraph_index))
            ]

    all_issues = _deduplicate_issues(
        issue for section_review in section_reviews for issue in section_review["issues"]
    )
    strengths = []
    seen_strengths = set()
    for section_review in section_reviews:
        for strength in section_review["strengths"]:
            key = hashlib.sha256(normalised(strength.get("observation", "")).encode("utf-8")).hexdigest()
            if key in seen_strengths:
                continue
            seen_strengths.add(key)
            evidence = [_evidence(paragraph_index[pid]) for pid in strength.get("evidence_paragraph_ids", []) if pid in paragraph_index]
            strengths.append({
                "category": strength.get("category", "other"),
                "section": clean_text(strength.get("section", "")),
                "observation": clean_text(strength.get("observation", "")),
                "evidence": evidence,
            })

    finding_rows = [_finding_row(issue, paragraph_index) for issue in all_issues]
    score = _academic_score(section_reviews, all_issues)
    incomplete = bool(failed_sections) or any(bool(section.get("coverage_warning")) for section in section_reviews)
    readiness_label, readiness_meaning = _readiness(score, all_issues, incomplete)

    # Retain alignment and revision as distinct dimensions, but make the academic review the dominant score.
    summary = review.get("summary") or {}
    alignment_value = summary.get("alignment_score")
    revision_value = summary.get("revision_score")
    if summary.get("revised_mode") and revision_value is not None and alignment_value is not None:
        overall = round(score * 0.70 + float(alignment_value) * 0.10 + float(revision_value) * 0.20, 1)
    elif summary.get("revised_mode") and revision_value is not None:
        overall = round(score * 0.80 + float(revision_value) * 0.20, 1)
    elif alignment_value is not None:
        overall = round(score * 0.85 + float(alignment_value) * 0.15, 1)
    else:
        overall = score

    counts = defaultdict(int)
    for issue in all_issues:
        counts[issue.get("severity", "minor")] += 1

    priority = [
        {
            "section": row.get("section", ""),
            "severity": row.get("severity", "moderate"),
            "status": row.get("status_label", "Revision required"),
            "action": row.get("required_action", ""),
            "issue": row.get("item", ""),
        }
        for row in finding_rows[:15]
    ]
    # Add unresolved supervisor comments after academic issues.
    for row in review.get("revision_results") or []:
        if row.get("status") in {"partly_meets_requirement", "does_not_meet_requirement", "manual_review_required"}:
            priority.append({
                "section": row.get("section", "Supervisor comment follow-up"),
                "severity": row.get("severity", "major"),
                "status": row.get("status_label", "Revision required"),
                "action": row.get("required_action", ""),
                "issue": "Earlier supervisor comment",
            })
    priority = sorted(priority, key=lambda x: SEVERITY_ORDER.get(x.get("severity", "minor"), 9))[:15]

    summary.update({
        "academic_review_score": score,
        "overall_score": overall,
        "readiness_label": readiness_label,
        "readiness_meaning": readiness_meaning,
        "academic_review_complete": not incomplete,
        "academic_sections_reviewed": len(section_reviews),
        "critical_issues": counts["critical"],
        "major_issues": counts["major"],
        "moderate_issues": counts["moderate"],
        "minor_issues": counts["minor"],
        "strengths_identified": len(strengths),
    })
    review["academic_findings"] = finding_rows
    review["academic_strengths"] = strengths
    review["academic_section_reviews"] = [
        {k: v for k, v in section.items() if k not in {"source_section", "issues", "strengths"}}
        for section in section_reviews
    ]
    review["overall_academic_assessment"] = _overall_assessment(score, all_issues, strengths)
    review["priority_actions"] = priority

    ai_review = review.setdefault("ai_review", {})
    all_usage = list(existing_usage)
    all_usage.extend(record.model_dump() for record in usage_records)
    ai_review.update({
        "academic_review_enabled": True,
        "academic_review_complete": not incomplete,
        "failed_sections": failed_sections,
        "usage": all_usage,
        "estimated_cost_usd": round(sum(float(x.get("estimated_cost_usd", 0)) for x in all_usage), 6),
    })
    return review
