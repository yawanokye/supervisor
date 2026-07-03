from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .ai_config import HybridAIConfig
from .ai_providers import AIProviderError, DeepSeekProvider
from .checkpointing import CheckpointManager, stable_hash
from .assessment_schemas import (
    ExternalAssessmentCorrections,
    ExternalAssessmentDecision,
    ExternalAssessmentEvidence,
    ExternalAssessmentFoundation,
    ExternalAssessmentReport,
)
from .document_parser import clean_text, normalised


EXTERNAL_ASSESSMENT_SYSTEM_PROMPT = """
You are an independent, senior external examiner of theses and dissertations.
Produce a formal, balanced and defensible external examination judgement, not a
supervisory rewrite. Apply the academic standard appropriate to the stated
degree and research approach. Treat the submitted thesis as the sole evidential
basis. Do not invent institutions, participants, statistics, findings, sources,
policies or claims that are not established in the supplied evidence.

Chapter One or the equivalent foundational chapter is a critical examination
gate because it sets the intellectual direction of the thesis. Examine the
background, research problem, gap, purpose, objectives, questions or hypotheses,
significance, scope, limitations, definitions and organisation. Test the chain
from title to problem, purpose, objectives, questions, methods, findings,
conclusions, recommendations and contribution. A thesis cannot receive pass
without corrections when this foundation is materially deficient.

For Professional Doctorate and PhD work, do not impose a fixed five-chapter
format. Assess the actual architecture by research function, integration,
originality and contribution. For quantitative, econometric, SEM or mixed-method
work, scrutinise model specification, assumptions, diagnostics, statistical
accuracy and interpretation. For qualitative work, scrutinise philosophical
coherence, sampling logic, data adequacy, analytic transparency, trustworthiness
and evidential support. For mixed methods, scrutinise the integration of strands.

Corrections must be concrete, prioritised and traceable to a chapter, section,
page, paragraph or table where the evidence permits. The confidential comments
must be suitable for the university and must not appear in the candidate-facing
report. Recommendations must be proportionate to the academic defects and the
institutional stage. Return the requested external-assessment stage matching the supplied schema.
""".strip()


LEVEL_STANDARDS: Dict[str, str] = {
    "bachelors": (
        "Competent application of established knowledge, a clearly framed and "
        "manageable inquiry, appropriate methods, accurate analysis and sound "
        "interpretation at undergraduate level."
    ),
    "non research masters": (
        "Advanced professional or taught-Master's application of knowledge, "
        "critical engagement, methodological competence and practical relevance."
    ),
    "research masters mphil": (
        "Independent research capability, critical synthesis, defensible theory "
        "and methodology, rigorous analysis and a meaningful empirical, "
        "theoretical, methodological or contextual contribution."
    ),
    "professional doctorate": (
        "Original and advanced professional inquiry that integrates scholarship "
        "with practice and makes a defensible contribution to professional "
        "knowledge, policy, organisation or practice."
    ),
    "phd": (
        "Original, substantial and defensible contribution to knowledge, command "
        "of the field, methodological and theoretical sophistication, and the "
        "capacity for independent scholarship of publishable quality."
    ),
}


RECOMMENDATION_LABELS = {
    "pass_without_corrections": "Pass Without Corrections",
    "pass_subject_to_minor_corrections": "Pass Subject to Minor Corrections",
    "pass_subject_to_major_corrections": "Pass Subject to Major Corrections",
    "revise_and_resubmit_for_re_examination": "Revise and Resubmit for Re-examination",
    "award_lower_degree_where_permitted": "Award a Lower Degree Where Permitted",
    "fail": "Fail",
    "corrections_satisfactorily_completed": "Corrections Satisfactorily Completed",
    "corrections_not_satisfactorily_completed": "Corrections Not Satisfactorily Completed",
}


DOMAIN_FIELDS = (
    "chapter_one_assessment",
    "research_problem_and_purpose",
    "literature_and_theoretical_foundation",
    "methodology_and_procedures",
    "results_or_findings",
    "discussion_and_interpretation",
    "conclusions_recommendations_and_contribution",
    "structural_coherence_and_alignment",
    "academic_writing_and_presentation",
    "ethics_and_research_integrity",
    "originality_and_contribution",
)


def _level_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _level_standard(value: Any) -> str:
    key = _level_key(value)
    for label, standard in LEVEL_STANDARDS.items():
        if label in key or key in label:
            return standard
    return LEVEL_STANDARDS["research masters mphil"]


def _compact_text(value: Any, limit: int = 1200) -> str:
    text = clean_text(str(value or ""))
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _compact_rows(
    rows: Iterable[Dict[str, Any]],
    *,
    fields: Sequence[str],
    limit: int,
    text_limit: int = 900,
) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        compact: Dict[str, Any] = {}
        for field in fields:
            value = row.get(field)
            if isinstance(value, str):
                value = _compact_text(value, text_limit)
            compact[field] = value
        output.append(compact)
        if len(output) >= limit:
            break
    return output


def _source_extract(
    paragraphs: Sequence[Dict[str, Any]],
    *,
    max_chars: int = 42000,
    chapter_numbers: Optional[set[Optional[int]]] = None,
) -> List[Dict[str, Any]]:
    """Select balanced examination evidence with a protected Chapter One budget."""
    key_terms = (
        "statement of the problem", "research problem", "purpose of the study",
        "research objective", "research question", "hypothesis", "theoretical",
        "conceptual framework", "research design", "methodology", "sampling",
        "data analysis", "diagnostic", "result", "finding", "discussion",
        "conclusion", "recommendation", "contribution", "limitation", "ethic",
    )

    def item_for(paragraph: Dict[str, Any], index: int) -> Dict[str, Any]:
        return {
            "id": f"P{paragraph.get('paragraph') or index + 1}",
            "chapter_number": paragraph.get("chapter_number"),
            "heading": _compact_text(paragraph.get("heading", ""), 220),
            "page": paragraph.get("page"),
            "paragraph": paragraph.get("paragraph"),
            "source_kind": paragraph.get("source_kind", "paragraph"),
            "table_index": paragraph.get("table_index"),
            "table_row": paragraph.get("table_row"),
            "text": _compact_text(paragraph.get("text", ""), 1200),
        }

    selected: List[Dict[str, Any]] = []
    selected_ids = set()
    total = 0

    def add_candidates(candidates: Iterable[tuple[int, Dict[str, Any]]], budget: int) -> None:
        nonlocal total
        start_total = total
        for index, paragraph in candidates:
            text = clean_text(paragraph.get("text", ""))
            if not text:
                continue
            identity = (paragraph.get("paragraph"), paragraph.get("page"), text[:120])
            if identity in selected_ids:
                continue
            item = item_for(paragraph, index)
            size = len(json.dumps(item, ensure_ascii=False))
            if selected and total + size > max_chars:
                return
            if total - start_total + size > budget:
                return
            selected.append(item)
            selected_ids.add(identity)
            total += size

    chapter_one_candidates = []
    other_candidates = []
    for index, paragraph in enumerate(paragraphs):
        chapter_number = paragraph.get("chapter_number")
        if chapter_numbers is not None and chapter_number not in chapter_numbers:
            continue
        text = clean_text(paragraph.get("text", ""))
        if not text:
            continue
        combined = normalised(f"{paragraph.get('heading', '')} {text}")
        important = (
            bool(paragraph.get("is_heading"))
            or index < 8
            or any(term in combined for term in key_terms)
        )
        if paragraph.get("chapter_number") == 1:
            if important or len(chapter_one_candidates) < 30:
                chapter_one_candidates.append((index, paragraph))
        elif important:
            other_candidates.append((index, paragraph))

    add_candidates(chapter_one_candidates, min(16000, max_chars // 2))
    add_candidates(other_candidates, max_chars - total)
    return selected


def _metadata_payload(metadata: Dict[str, Any], summary: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "candidate_name": clean_text(metadata.get("candidate_name", "")) or "Not supplied",
        "candidate_number": clean_text(metadata.get("candidate_number", "")) or "Not supplied",
        "degree_programme": clean_text(metadata.get("degree_programme", "")) or summary.get("academic_level", ""),
        "department": clean_text(metadata.get("candidate_department", "")) or "Not supplied",
        "institution": clean_text(metadata.get("institution", "")) or "Not supplied",
        "thesis_title": clean_text(metadata.get("thesis_title", "")) or summary.get("filename", ""),
        "assessment_stage": metadata.get("assessment_stage", "initial_examination"),
        "examiner_name": clean_text(metadata.get("examiner_name", "")) or "External Examiner",
        "examiner_department": clean_text(metadata.get("examiner_department", "")) or "Not supplied",
        "academic_level": summary.get("academic_level", ""),
        "research_approach": summary.get("research_approach", ""),
        "thesis_structure": summary.get("thesis_structure_label", ""),
        "degree_standard": _level_standard(summary.get("academic_level")),
    }


def _shared_payload(
    review: Dict[str, Any],
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    summary = review.get("summary") or {}
    return {
        "examination_information": _metadata_payload(metadata, summary),
        "assessment_rules": {
            "independent_external_examination": True,
            "chapter_one_is_critical_gate": True,
            "no_pass_without_corrections_when_chapter_one_materially_deficient": True,
            "all_corrections_must_be_prioritised_and_traceable": True,
            "doctoral_structure_may_deviate_from_five_chapters": True,
            "confidential_comments_are_for_university_only": True,
            "do_not_invent_missing_information": True,
        },
        "review_summary": {
            key: summary.get(key)
            for key in (
                "filename", "academic_level", "research_approach", "review_scope",
                "thesis_structure_mode", "thesis_structure_label",
                "uploaded_chapter_labels", "academic_review_score", "overall_score",
                "readiness_label", "critical_issues", "major_issues",
                "moderate_issues", "minor_issues", "alignment_score",
                "doctoral_functional_coverage", "missing_doctoral_functional_coverage",
                "standard_chapter_coverage", "missing_standard_chapter_coverage",
            )
        },
        "overall_academic_review": _compact_text(
            review.get("overall_academic_assessment", ""),
            4200,
        ),
        "study_context": review.get("study_context") or {},
        "statistical_review": review.get("statistical_review") or {},
        "academic_strengths": _compact_rows(
            review.get("academic_strengths") or [],
            fields=("category", "section", "observation", "evidence"),
            limit=20,
            text_limit=600,
        ),
        "priority_actions": _compact_rows(
            review.get("priority_actions") or [],
            fields=("section", "severity", "issue", "action"),
            limit=36,
            text_limit=700,
        ),
        "material_findings": _compact_rows(
            review.get("academic_findings") or [],
            fields=(
                "category", "section", "item", "severity", "comment",
                "required_action", "problematic_quote", "evidence",
            ),
            limit=60,
            text_limit=720,
        ),
        "section_reviews": _compact_rows(
            review.get("academic_section_reviews") or [],
            fields=(
                "heading", "section_score", "section_assessment",
                "coverage_warning",
            ),
            limit=65,
            text_limit=780,
        ),
        "previous_examiner_correction_follow_up": _compact_rows(
            review.get("revision_results") or [],
            fields=(
                "section", "item", "status_label", "severity", "comment",
                "required_action", "supervisor_comment_source",
            ),
            limit=45,
            text_limit=720,
        ),
        "alignment_findings": _compact_rows(
            review.get("alignment_results") or [],
            fields=(
                "section", "item", "status", "severity", "comment",
                "required_action",
            ),
            limit=28,
            text_limit=650,
        ),
    }


def _stage_prompt(
    stage: str,
    review: Dict[str, Any],
    runtime_context: Dict[str, Any],
    metadata: Dict[str, Any],
    *,
    prior_outputs: Optional[Dict[str, Any]] = None,
    concise_retry: bool = False,
) -> str:
    shared = _shared_payload(review, metadata)
    paragraphs = runtime_context.get("current_paragraphs") or []

    if stage == "foundation":
        payload = {
            "examination_information": shared["examination_information"],
            "assessment_rules": shared["assessment_rules"],
            "review_summary": shared["review_summary"],
            "overall_academic_review": shared["overall_academic_review"],
            "study_context": shared["study_context"],
            "alignment_findings": shared["alignment_findings"],
            "material_findings": shared["material_findings"][:32],
            "section_reviews": shared["section_reviews"][:35],
            "selected_source_evidence": _source_extract(
                paragraphs,
                max_chars=26000 if not concise_retry else 15000,
                chapter_numbers={None, 1, 2, 3},
            ),
        }
        instruction = (
            "Prepare only the foundation and methods part of the external "
            "examination. Produce a concise study summary, degree-standard "
            "judgement, the Chapter One critical-gate judgement, and rigorous "
            "assessments of the research problem, literature/theory and methods. "
            "Each domain assessment should normally remain below 220 words and "
            "each strengths, concerns and corrections list should contain no more "
            "than six concise items."
        )
    elif stage == "evidence":
        payload = {
            "examination_information": shared["examination_information"],
            "assessment_rules": shared["assessment_rules"],
            "review_summary": shared["review_summary"],
            "overall_academic_review": shared["overall_academic_review"],
            "study_context": shared["study_context"],
            "statistical_review": shared["statistical_review"],
            "academic_strengths": shared["academic_strengths"],
            "material_findings": shared["material_findings"],
            "section_reviews": shared["section_reviews"],
            "alignment_findings": shared["alignment_findings"],
            "selected_source_evidence": _source_extract(
                paragraphs,
                max_chars=28000 if not concise_retry else 16000,
                chapter_numbers=None,
            ),
        }
        instruction = (
            "Prepare only the evidence, interpretation and contribution part of "
            "the external examination. Assess results/findings, discussion, "
            "conclusions, structural coherence, writing, ethics, originality and "
            "publication potential. Scrutinise statistical accuracy and model "
            "diagnostics where relevant. Each domain assessment should normally "
            "remain below 220 words and lists should contain no more than six "
            "concise items."
        )
    elif stage == "corrections":
        payload = {
            "examination_information": shared["examination_information"],
            "review_summary": shared["review_summary"],
            "foundation_assessment": (prior_outputs or {}).get("foundation", {}),
            "evidence_assessment": (prior_outputs or {}).get("evidence", {}),
            "priority_actions": shared["priority_actions"],
            "material_findings": shared["material_findings"],
            "previous_examiner_correction_follow_up": shared[
                "previous_examiner_correction_follow_up"
            ],
            "alignment_findings": shared["alignment_findings"],
        }
        instruction = (
            "Prepare only the formal corrections schedule, priority corrections, "
            "correction-verification assessment and oral examination questions. "
            "Consolidate duplicates. Include no more than 35 material corrections "
            "and 18 thesis-specific oral questions. Make every correction concise, "
            "traceable, classified and suitable for institutional verification."
        )
    elif stage == "decision":
        payload = {
            "examination_information": shared["examination_information"],
            "assessment_rules": shared["assessment_rules"],
            "review_summary": shared["review_summary"],
            "foundation_assessment": (prior_outputs or {}).get("foundation", {}),
            "evidence_assessment": (prior_outputs or {}).get("evidence", {}),
            "corrections_and_questions": (prior_outputs or {}).get(
                "corrections", {}
            ),
            "previous_examiner_correction_follow_up": shared[
                "previous_examiner_correction_follow_up"
            ],
        }
        instruction = (
            "Make the final independent examiner decision only. Produce the "
            "overall academic judgement, recommendation and rationale, confidential "
            "comments to the university, confidence, correction-verification "
            "authority, viva recommendation and declaration. The recommendation "
            "must follow the Chapter One gate and correction severity. Keep the "
            "candidate-facing rationale below 320 words and confidential comments "
            "below 260 words."
        )
    else:
        raise ValueError(f"Unknown external-assessment stage: {stage}")

    retry_note = (
        " This is a concise recovery attempt. Use shorter sentences, remove "
        "repetition and stay well within the requested limits."
        if concise_retry
        else ""
    )
    return (
        instruction
        + retry_note
        + " Use formal British English. Treat only the supplied evidence as "
          "authoritative. Return the requested JSON object only.\n\n"
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )


def _renumber_corrections(report: Dict[str, Any]) -> None:
    corrections = report.get("corrections") or []
    for index, correction in enumerate(corrections, start=1):
        if isinstance(correction, dict):
            correction["number"] = index


def _enforce_recommendation_consistency(report: Dict[str, Any]) -> None:
    recommendation = report.get("final_recommendation")
    gate = report.get("chapter_one_gate_status")
    corrections = report.get("corrections") or []
    critical = sum(
        1 for item in corrections
        if isinstance(item, dict) and item.get("classification") == "critical"
    )
    major = sum(
        1 for item in corrections
        if isinstance(item, dict) and item.get("classification") == "major"
    )

    inconsistent = False
    replacement = recommendation
    if gate == "fundamentally_deficient" and recommendation in {
        "pass_without_corrections",
        "pass_subject_to_minor_corrections",
    }:
        replacement = "revise_and_resubmit_for_re_examination"
        inconsistent = True
    elif critical and recommendation == "pass_without_corrections":
        replacement = "pass_subject_to_major_corrections"
        inconsistent = True
    elif major and recommendation == "pass_without_corrections":
        replacement = "pass_subject_to_major_corrections"
        inconsistent = True

    if inconsistent:
        report["final_recommendation"] = replacement
        rationale = clean_text(report.get("recommendation_rationale", ""))
        report["recommendation_rationale"] = (
            rationale
            + " The recommendation has been aligned with the critical-gate and "
              "correction classification rules because the reported deficiencies "
              "are incompatible with an unqualified pass."
        ).strip()
        report["recommendation_consistency_adjusted"] = True
    else:
        report["recommendation_consistency_adjusted"] = False


def prepare_external_assessment(
    report: Dict[str, Any],
    metadata: Dict[str, Any],
    review: Dict[str, Any],
) -> Dict[str, Any]:
    value = dict(report)
    _renumber_corrections(value)
    _enforce_recommendation_consistency(value)
    summary = review.get("summary") or {}
    value["recommendation_label"] = RECOMMENDATION_LABELS.get(
        value.get("final_recommendation"),
        str(value.get("final_recommendation", "")).replace("_", " ").title(),
    )
    value["assessment_metadata"] = _metadata_payload(metadata, summary)
    value["workflow_type"] = "external_assessment"
    value["report_status"] = "Examiner-ready draft requiring examiner review and signature"
    value["domain_order"] = list(DOMAIN_FIELDS)
    value["correction_counts"] = {
        level: sum(
            1 for item in value.get("corrections") or []
            if isinstance(item, dict) and item.get("classification") == level
        )
        for level in ("critical", "major", "moderate", "minor")
    }
    return value


async def _complete_assessment_stage(
    provider: DeepSeekProvider,
    *,
    stage: str,
    schema_model: type,
    review: Dict[str, Any],
    runtime_context: Dict[str, Any],
    metadata: Dict[str, Any],
    config: HybridAIConfig,
    prior_outputs: Optional[Dict[str, Any]],
    max_output_tokens: int,
    reasoning_effort: str,
    checkpoint_manager: Optional[CheckpointManager] = None,
) -> Any:
    last_error: Optional[Exception] = None
    for concise_retry in (False, True):
        user_prompt = _stage_prompt(
            stage,
            review,
            runtime_context,
            metadata,
            prior_outputs=prior_outputs,
            concise_retry=concise_retry,
        )
        input_hash = stable_hash({
            "pipeline": "external-assessment-v1.7.0",
            "stage": stage,
            "concise_retry": concise_retry,
            "model": config.deepseek_advanced_model,
            "reasoning_effort": reasoning_effort,
            "max_output_tokens": max_output_tokens,
            "system_prompt": EXTERNAL_ASSESSMENT_SYSTEM_PROMPT,
            "user_prompt": user_prompt,
            "schema": schema_model.__name__,
        })
        stage_key = f"external-{stage}-{input_hash[:20]}"
        if checkpoint_manager is not None:
            cached = checkpoint_manager.load_provider_result(
                stage_key,
                expected_input_hash=input_hash,
            )
            if cached is not None:
                return cached
            checkpoint_manager.mark_running(
                stage_key,
                input_hash=input_hash,
                message=f"Preparing external assessment stage: {stage}",
            )
        try:
            result = await provider.complete_json(
                model=config.deepseek_advanced_model,
                system_prompt=EXTERNAL_ASSESSMENT_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                schema_model=schema_model,
                purpose=f"external_thesis_assessment_{stage}",
                reasoning_effort=reasoning_effort,
                max_output_tokens=max_output_tokens,
            )
            if checkpoint_manager is not None:
                checkpoint_manager.save_provider_result(
                    stage_key,
                    result,
                    input_hash=input_hash,
                    message=f"External assessment stage completed: {stage}",
                )
            return result
        except AIProviderError as exc:
            last_error = exc
            message = normalised(str(exc))
            recoverable = any(
                phrase in message
                for phrase in (
                    "output token",
                    "truncated",
                    "timeout",
                    "timed out",
                    "empty json",
                    "schema validation",
                    "invalid json",
                )
            )
            if not recoverable or concise_retry:
                break
    raise AIProviderError(
        f"External assessment stage '{stage}' could not be completed: "
        f"{last_error or 'provider request failed'}"
    )


def _costed_usage(result: Any, config: HybridAIConfig) -> tuple[Any, float]:
    uncached = max(
        0,
        result.usage.input_tokens - result.usage.cached_input_tokens,
    )
    estimated_cost = (
        uncached / 1_000_000 * config.deepseek_pro_input_price
        + result.usage.cached_input_tokens
        / 1_000_000
        * config.deepseek_pro_cached_input_price
        + result.usage.output_tokens
        / 1_000_000
        * config.deepseek_pro_output_price
    )
    usage = result.usage.model_copy(
        update={"estimated_cost_usd": round(estimated_cost, 6)}
    )
    return usage, estimated_cost


async def enrich_with_external_assessment(
    review: Dict[str, Any],
    runtime_context: Dict[str, Any],
    *,
    metadata: Dict[str, Any],
    config: HybridAIConfig,
    progress_callback: Optional[Any] = None,
    checkpoint_manager: Optional[CheckpointManager] = None,
) -> Dict[str, Any]:
    if not config.deepseek_configured:
        raise AIProviderError(
            "DeepSeek is required to prepare the external examination report."
        )

    async def progress(value: int, message: str) -> None:
        if progress_callback is None:
            return
        result = progress_callback(value, message)
        if hasattr(result, "__await__"):
            await result

    provider = DeepSeekProvider(config)
    outputs: Dict[str, Any] = {}
    results: List[Any] = []

    await progress(
        87,
        "Assessing the thesis foundation, methods, findings and contribution in parallel",
    )
    foundation_task = _complete_assessment_stage(
        provider,
        stage="foundation",
        schema_model=ExternalAssessmentFoundation,
        review=review,
        runtime_context=runtime_context,
        metadata=metadata,
        config=config,
        prior_outputs=None,
        max_output_tokens=config.external_assessment_foundation_max_output_tokens,
        reasoning_effort=config.deepseek_advanced_primary_reasoning_effort,
        checkpoint_manager=checkpoint_manager,
    )
    evidence_task = _complete_assessment_stage(
        provider,
        stage="evidence",
        schema_model=ExternalAssessmentEvidence,
        review=review,
        runtime_context=runtime_context,
        metadata=metadata,
        config=config,
        prior_outputs=None,
        max_output_tokens=config.external_assessment_evidence_max_output_tokens,
        reasoning_effort=config.deepseek_advanced_primary_reasoning_effort,
        checkpoint_manager=checkpoint_manager,
    )
    foundation, evidence = await asyncio.gather(
        foundation_task,
        evidence_task,
    )
    outputs["foundation"] = foundation.data
    outputs["evidence"] = evidence.data
    results.extend([foundation, evidence])
    await progress(91, "Foundation and evidence assessment completed")

    await progress(93, "Preparing corrections and oral examination questions")
    corrections = await _complete_assessment_stage(
        provider,
        stage="corrections",
        schema_model=ExternalAssessmentCorrections,
        review=review,
        runtime_context=runtime_context,
        metadata=metadata,
        config=config,
        prior_outputs=outputs,
        max_output_tokens=config.external_assessment_corrections_max_output_tokens,
        reasoning_effort=config.deepseek_advanced_primary_reasoning_effort,
        checkpoint_manager=checkpoint_manager,
    )
    outputs["corrections"] = corrections.data
    results.append(corrections)

    await progress(95, "Finalising the independent examiner recommendation")
    decision = await _complete_assessment_stage(
        provider,
        stage="decision",
        schema_model=ExternalAssessmentDecision,
        review=review,
        runtime_context=runtime_context,
        metadata=metadata,
        config=config,
        prior_outputs=outputs,
        max_output_tokens=config.external_assessment_decision_max_output_tokens,
        reasoning_effort=config.deepseek_advanced_reasoning_effort,
        checkpoint_manager=checkpoint_manager,
    )
    outputs["decision"] = decision.data
    results.append(decision)

    merged = {
        **outputs["foundation"],
        **outputs["evidence"],
        **outputs["corrections"],
        **outputs["decision"],
    }
    try:
        validated = ExternalAssessmentReport.model_validate(merged)
    except Exception as exc:
        raise AIProviderError(
            f"The staged external assessment could not be assembled: {exc}"
        ) from exc

    assessment = prepare_external_assessment(
        validated.model_dump(),
        metadata,
        review,
    )

    usage_records = []
    total_cost = 0.0
    for result in results:
        usage, estimated_cost = _costed_usage(result, config)
        usage_records.append(usage.model_dump())
        total_cost += estimated_cost

    review["external_assessment"] = assessment
    review["external_assessment_usage"] = {
        "generation_mode": "staged",
        "api_call_count": len(usage_records),
        "estimated_cost_usd": round(total_cost, 6),
        "calls": usage_records,
    }
    ai_review = review.get("ai_review") or {}
    if ai_review:
        ai_review.setdefault("usage", []).extend(usage_records)
        ai_review["estimated_cost_usd"] = round(
            float(ai_review.get("estimated_cost_usd") or 0) + total_cost,
            6,
        )
        ai_review["api_call_count"] = (
            int(ai_review.get("api_call_count") or 0)
            + len(usage_records)
        )
        ai_review["external_assessment_call"] = True
        ai_review["external_assessment_generation_mode"] = "staged"

    summary = review.setdefault("summary", {})
    summary.update({
        "workflow_type": "external_assessment",
        "workflow_label": "External Assessment",
        "assessment_stage": metadata.get(
            "assessment_stage", "initial_examination"
        ),
        "external_recommendation": assessment["final_recommendation"],
        "external_recommendation_label": assessment["recommendation_label"],
        "chapter_one_gate_status": assessment["chapter_one_gate_status"],
        "external_assessment_available": True,
        "external_assessment_generation_mode": "staged",
        "external_assessment_stage_count": 4,
        "readiness_label": assessment["recommendation_label"],
        "readiness_meaning": assessment["recommendation_rationale"],
    })
    await progress(97, "Generating the external examination documents")
    return review

