from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .ai_config import HybridAIConfig
from .ai_providers import AIProviderError, OpenAIProvider
from .checkpointing import CheckpointManager, stable_hash
from .assessment_schemas import (
    ExternalAssessmentAdjudication,
    ExternalAssessmentCorrections,
    ExternalAssessmentDecision,
    ExternalAssessmentEvidence,
    ExternalAssessmentEvidenceCore,
    ExternalAssessmentFoundation,
    ExternalAssessmentIntegrity,
    ExternalAssessmentReport,
)
from .document_parser import clean_text, normalised
from .external_assessment_guard import (
    build_document_manifest,
    collect_evidence_ids,
    compact_manifest_for_prompt,
    evidence_catalog,
    filter_contradicted_rows,
    find_presence_contradictions,
    find_unsupported_numeric_claims,
    find_unsupported_reference_risk_claims,
    select_balanced_evidence,
    validate_evidence_ids,
)


EXTERNAL_ASSESSMENT_SYSTEM_PROMPT = """
You are an independent, senior external examiner of theses and dissertations.
Produce a formal, balanced and defensible external examination judgement, not a
supervisory rewrite. Apply the academic standard appropriate to the stated
degree, discipline and research approach.

Evidence hierarchy is mandatory. The document manifest and the source excerpts
identified by evidence IDs are primary evidence. Earlier automated checklist
findings are derivative aids and must be rejected whenever they conflict with
the manifest or source evidence. Do not invent institutions, participants,
statistics, findings, sources, policies or claims. Do not allege a fabricated,
phantom, future-dated, unverifiable, irrelevant or unreliable reference unless
the exact reference entry is present in cited source evidence.

Treat every statement that content is missing, absent, not supplied or not
reported as a high-risk factual claim. You may make such a claim only when the
manifest explicitly classifies the component as confirmed_absent. A status of
not_confidently_located means retrieval uncertainty, not absence. In that case,
state that the component could not be fully assessed from the supplied evidence
and do not penalise the candidate for its alleged absence.

Every assessment domain must report its coverage status. Every fully or partly
assessed domain must cite only evidence IDs supplied in the current stage. Copy
each token exactly from allowed_evidence_ids. Evidence IDs are opaque source
tokens, not page or paragraph numbers, so never construct an ID from a page,
paragraph, table or chapter number. Evidence IDs must support the actual point
being made. A technical term appearing in the thesis is not proof that the
method is adequate. Examine the reported procedures, values, diagnostics,
interpretations and limitations.

Chapter One or the equivalent foundational chapter is a critical examination
gate because it sets the intellectual direction of the thesis. Examine the
background, research problem, gap, purpose, objectives, questions or hypotheses,
significance, scope, limitations, definitions and organisation. Test the chain
from title to problem, purpose, objectives, questions, methods, findings,
conclusions, recommendations and contribution. A thesis cannot receive pass
without corrections when this foundation is materially deficient, but the gate
must be based on verified quality deficiencies rather than retrieval failure.

Do not impose a fixed five-chapter format. Assess the actual architecture by
research function, integration, originality and contribution. For quantitative,
econometric, SEM or mixed-method work, scrutinise model specification,
assumptions, diagnostics, statistical accuracy and interpretation. For
qualitative work, scrutinise philosophical coherence, sampling logic, data
adequacy, analytic transparency, trustworthiness and evidential support. For
mixed methods, scrutinise the integration of strands.

Corrections must be concrete, proportionate, prioritised and traceable to valid
evidence IDs, chapters, sections, pages, paragraphs or tables. Do not repeat a
correction merely because an earlier automated review suggested it. The
confidential comments must be suitable for the university and must not appear in
the candidate-facing report. Recommendations must follow the verified academic
defects and the institutional stage. When source coverage is limited or insufficient, no
academic recommendation may be issued. Return only the requested JSON object
matching the supplied schema.
""".strip()


class ExternalAssessmentValidationError(ValueError):
    """Raised when a generated examiner finding is not grounded in the source."""



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
    "assessment_withheld_incomplete_extraction": "Assessment Withheld: Source Extraction Requires Verification",
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



def _metadata_payload(
    metadata: Dict[str, Any],
    summary: Dict[str, Any],
    manifest: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    inferred = (manifest or {}).get("inferred_metadata") or {}

    def first(*values: Any) -> str:
        for value in values:
            text = clean_text(value)
            if text:
                return text
        return ""

    return {
        "candidate_name": first(metadata.get("candidate_name"), inferred.get("candidate_name")),
        "candidate_number": first(metadata.get("candidate_number"), inferred.get("candidate_number")),
        "degree_programme": first(
            metadata.get("degree_programme"),
            inferred.get("degree_programme"),
            summary.get("academic_level"),
        ),
        "department": first(
            metadata.get("candidate_department"),
            inferred.get("department"),
        ),
        "institution": first(metadata.get("institution"), inferred.get("institution")),
        "thesis_title": first(
            metadata.get("thesis_title"),
            inferred.get("thesis_title"),
            summary.get("filename"),
        ),
        "assessment_stage": metadata.get("assessment_stage", "initial_examination"),
        "examiner_name": first(metadata.get("examiner_name"), "External Examiner"),
        "examiner_department": first(metadata.get("examiner_department")),
        "academic_level": summary.get("academic_level", ""),
        "research_approach": summary.get("research_approach", ""),
        "thesis_structure": summary.get("thesis_structure_label", ""),
        "degree_standard": _level_standard(summary.get("academic_level")),
        "metadata_source": {
            "candidate_name": "submitted_form" if clean_text(metadata.get("candidate_name")) else "document_inference",
            "candidate_number": "submitted_form" if clean_text(metadata.get("candidate_number")) else "document_inference",
            "degree_programme": "submitted_form" if clean_text(metadata.get("degree_programme")) else "document_inference",
            "department": "submitted_form" if clean_text(metadata.get("candidate_department")) else "document_inference",
            "institution": "submitted_form" if clean_text(metadata.get("institution")) else "document_inference",
            "thesis_title": "submitted_form" if clean_text(metadata.get("thesis_title")) else "document_inference",
        },
    }


def _shared_payload(
    review: Dict[str, Any],
    metadata: Dict[str, Any],
    manifest: Dict[str, Any],
) -> Dict[str, Any]:
    summary = review.get("summary") or {}
    examination_information = _metadata_payload(metadata, summary, manifest)
    overall_academic_review = _compact_text(
        review.get("overall_academic_assessment", ""),
        4200,
    )
    overall_review_contradictions = find_presence_contradictions(
        overall_academic_review,
        manifest,
        metadata=examination_information,
    )
    if overall_review_contradictions:
        overall_academic_review = (
            "The derivative overall academic review was excluded because it contained "
            "one or more source-presence contradictions. Use the document manifest, "
            "source evidence and validated domain findings instead."
        )

    academic_strengths = _compact_rows(
        review.get("academic_strengths") or [],
        fields=("category", "section", "observation", "evidence"),
        limit=20,
        text_limit=600,
    )
    priority_actions = _compact_rows(
        review.get("priority_actions") or [],
        fields=("section", "severity", "issue", "action"),
        limit=36,
        text_limit=700,
    )
    material_findings = _compact_rows(
        review.get("academic_findings") or [],
        fields=(
            "category", "section", "item", "severity", "comment",
            "required_action", "problematic_quote", "evidence",
        ),
        limit=60,
        text_limit=720,
    )
    section_reviews = _compact_rows(
        review.get("academic_section_reviews") or [],
        fields=(
            "heading", "section_score", "section_assessment",
            "coverage_warning",
        ),
        limit=65,
        text_limit=780,
    )
    alignment_findings = _compact_rows(
        review.get("alignment_results") or [],
        fields=(
            "section", "item", "status", "severity", "comment",
            "required_action",
        ),
        limit=28,
        text_limit=650,
    )

    academic_strengths, rejected_strengths = filter_contradicted_rows(
        academic_strengths, manifest, metadata=examination_information
    )
    priority_actions, rejected_actions = filter_contradicted_rows(
        priority_actions, manifest, metadata=examination_information
    )
    material_findings, rejected_findings = filter_contradicted_rows(
        material_findings, manifest, metadata=examination_information
    )
    section_reviews, rejected_sections = filter_contradicted_rows(
        section_reviews, manifest, metadata=examination_information
    )
    alignment_findings, rejected_alignment = filter_contradicted_rows(
        alignment_findings, manifest, metadata=examination_information
    )

    return {
        "examination_information": examination_information,
        "document_manifest": compact_manifest_for_prompt(manifest),
        "assessment_rules": {
            "independent_external_examination": True,
            "chapter_one_is_critical_gate": True,
            "no_pass_without_corrections_when_chapter_one_materially_deficient": True,
            "all_corrections_must_be_prioritised_and_traceable": True,
            "chapter_sequence_is_not_fixed": True,
            "confidential_comments_are_for_university_only": True,
            "do_not_invent_missing_information": True,
            "absence_claim_requires_manifest_status": "confirmed_absent",
            "not_confidently_located_is_not_absence": True,
            "source_evidence_overrides_derivative_review": True,
            "withhold_recommendation_when_coverage_is_not_sufficient": True,
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
        "overall_academic_review": overall_academic_review,
        "study_context": review.get("study_context") or {},
        "statistical_review": review.get("statistical_review") or {},
        "academic_strengths": academic_strengths,
        "priority_actions": priority_actions,
        "material_findings": material_findings,
        "section_reviews": section_reviews,
        "previous_examiner_correction_follow_up": _compact_rows(
            review.get("revision_results") or [],
            fields=(
                "section", "item", "status_label", "severity", "comment",
                "required_action", "supervisor_comment_source",
            ),
            limit=45,
            text_limit=720,
        ),
        "alignment_findings": alignment_findings,
        "discarded_derivative_findings": {
            "academic_strengths": len(rejected_strengths),
            "priority_actions": len(rejected_actions),
            "material_findings": len(rejected_findings),
            "section_reviews": len(rejected_sections),
            "alignment_findings": len(rejected_alignment),
            "overall_academic_review": len(overall_review_contradictions),
            "reason": (
                "These derivative review entries contradicted source presence signals "
                "and were excluded before external examination."
            ),
        },
    }

def _selected_evidence_for_stage(
    stage: str,
    runtime_context: Dict[str, Any],
    manifest: Dict[str, Any],
    *,
    concise_retry: bool,
    additional_evidence_ids: Sequence[str] = (),
) -> List[Dict[str, Any]]:
    """Select the exact source excerpts available to a generation stage.

    Any valid manifest IDs cited by a failed attempt are added to the next
    attempt together with their source text. This converts a recoverable
    selection mismatch into a grounded retry instead of repeatedly rejecting
    the same otherwise valid identifier.
    """

    paragraphs = runtime_context.get("current_paragraphs") or []
    if stage == "foundation":
        selected = select_balanced_evidence(
            paragraphs,
            manifest,
            target_roles=("foundation", "literature_theory", "methodology"),
            max_chars=22000 if not concise_retry else 14000,
            concise=concise_retry,
        )
    elif stage == "evidence_core":
        selected = select_balanced_evidence(
            paragraphs,
            manifest,
            target_roles=("results", "discussion", "conclusions"),
            max_chars=26000 if not concise_retry else 16000,
            concise=concise_retry,
        )
    elif stage == "integrity":
        selected = select_balanced_evidence(
            paragraphs,
            manifest,
            target_roles=(
                "foundation",
                "literature_theory",
                "methodology",
                "results",
                "discussion",
                "conclusions",
                "ethics",
                "references",
            ),
            max_chars=22000 if not concise_retry else 14000,
            concise=concise_retry,
        )
    elif stage == "evidence":
        # Backwards-compatible combined evidence selection for saved v1.8.x
        # checkpoints and direct helper tests.
        selected = select_balanced_evidence(
            paragraphs,
            manifest,
            target_roles=("results", "discussion", "conclusions", "ethics", "references"),
            max_chars=32000 if not concise_retry else 19000,
            concise=concise_retry,
        )
    else:
        return []

    valid_ids = set(manifest.get("valid_evidence_ids") or [])
    requested = [
        clean_text(value)
        for value in additional_evidence_ids
        if clean_text(value) in valid_ids
    ]
    if requested:
        extras = evidence_catalog(
            paragraphs,
            requested,
            text_limit=900 if concise_retry else 1500,
        )
        selected_ids = {item.get("id") for item in selected}
        selected.extend(item for item in extras if item.get("id") not in selected_ids)

    return selected


def _feedback_for_prompt(feedback: Sequence[str]) -> List[str]:
    """Redact unsupported tokens so a retry is not primed to repeat them."""

    output: List[str] = []
    for item in feedback:
        value = clean_text(item)
        if value.startswith("Unsupported evidence IDs were used:"):
            output.append(
                "One or more evidence IDs were outside allowed_evidence_ids. "
                "Delete them and copy only exact tokens from allowed_evidence_ids."
            )
        elif value:
            output.append(value)
    return output


def _stage_prompt(
    stage: str,
    review: Dict[str, Any],
    runtime_context: Dict[str, Any],
    metadata: Dict[str, Any],
    manifest: Dict[str, Any],
    *,
    prior_outputs: Optional[Dict[str, Any]] = None,
    concise_retry: bool = False,
    validation_feedback: Optional[List[str]] = None,
    additional_evidence_ids: Sequence[str] = (),
) -> str:
    shared = _shared_payload(review, metadata, manifest)
    paragraphs = runtime_context.get("current_paragraphs") or []

    if stage == "foundation":
        selected_evidence = _selected_evidence_for_stage(
            stage,
            runtime_context,
            manifest,
            concise_retry=concise_retry,
            additional_evidence_ids=additional_evidence_ids,
        )
        payload = {
            "examination_information": shared["examination_information"],
            "assessment_rules": shared["assessment_rules"],
            "document_manifest": shared["document_manifest"],
            "review_summary": shared["review_summary"],
            "overall_academic_review": shared["overall_academic_review"],
            "study_context": shared["study_context"],
            "alignment_findings": shared["alignment_findings"],
            "material_findings": shared["material_findings"][:32],
            "section_reviews": shared["section_reviews"][:35],
            "discarded_derivative_findings": shared["discarded_derivative_findings"],
            "selected_source_evidence": selected_evidence,
            "allowed_evidence_ids": [item["id"] for item in selected_evidence],
        }
        instruction = (
            "Prepare only the foundation, literature and methods part of the "
            "external examination. Use the functional chapter map rather than "
            "assuming that literature is Chapter Two or methods is Chapter Three. "
            "Produce a concise study summary, degree-standard judgement, the "
            "foundational critical-gate judgement, and rigorous assessments of the "
            "research problem, literature/theory and methods. Each domain must set "
            "coverage_status. Every fully or partly assessed domain must cite one or more allowed evidence_ids. Copy each "
            "ID exactly from allowed_evidence_ids and never derive it from a page or paragraph number. Each domain "
            "assessment should normally remain below 210 words and each list should "
            "contain no more than five concise items."
        )
    elif stage == "evidence_core":
        selected_evidence = _selected_evidence_for_stage(
            stage,
            runtime_context,
            manifest,
            concise_retry=concise_retry,
            additional_evidence_ids=additional_evidence_ids,
        )
        payload = {
            "examination_information": shared["examination_information"],
            "assessment_rules": shared["assessment_rules"],
            "document_manifest": shared["document_manifest"],
            "review_summary": shared["review_summary"],
            "overall_academic_review": shared["overall_academic_review"],
            "study_context": shared["study_context"],
            "statistical_review": shared["statistical_review"],
            "material_findings": shared["material_findings"][:40],
            "section_reviews": shared["section_reviews"][:40],
            "alignment_findings": shared["alignment_findings"],
            "discarded_derivative_findings": shared["discarded_derivative_findings"],
            "selected_source_evidence": selected_evidence,
            "allowed_evidence_ids": [item["id"] for item in selected_evidence],
        }
        instruction = (
            "Prepare only the results, discussion, conclusions and structural "
            "alignment part of the external examination. Apply the method-specific "
            "expert checklist in the manifest. Judge reported values, diagnostics, "
            "interpretations and alignment, not mere term presence. Each domain must "
            "set coverage_status and cite one or more exact allowed_evidence_ids. "
            "Keep each assessment below 210 words and each list to no more than five "
            "concise items."
        )
    elif stage == "integrity":
        selected_evidence = _selected_evidence_for_stage(
            stage,
            runtime_context,
            manifest,
            concise_retry=concise_retry,
            additional_evidence_ids=additional_evidence_ids,
        )
        payload = {
            "examination_information": shared["examination_information"],
            "assessment_rules": shared["assessment_rules"],
            "document_manifest": shared["document_manifest"],
            "review_summary": shared["review_summary"],
            "overall_academic_review": shared["overall_academic_review"],
            "study_context": shared["study_context"],
            "academic_strengths": shared["academic_strengths"][:16],
            "material_findings": shared["material_findings"][:30],
            "section_reviews": shared["section_reviews"][:30],
            "discarded_derivative_findings": shared["discarded_derivative_findings"],
            "selected_source_evidence": selected_evidence,
            "allowed_evidence_ids": [item["id"] for item in selected_evidence],
        }
        instruction = (
            "Prepare only the academic writing and presentation, ethics and research "
            "integrity, originality and contribution, major strengths and publication "
            "potential part of the external examination. Use exact source evidence. "
            "Do not allege citation or reference misconduct unless the exact reference "
            "entry is available in cited evidence. Each assessed domain must cite one "
            "or more exact allowed_evidence_ids. Keep each assessment below 210 words "
            "and each list to no more than five concise items."
        )
    elif stage == "evidence":
        selected_evidence = _selected_evidence_for_stage(
            stage,
            runtime_context,
            manifest,
            concise_retry=concise_retry,
            additional_evidence_ids=additional_evidence_ids,
        )
        payload = {
            "examination_information": shared["examination_information"],
            "assessment_rules": shared["assessment_rules"],
            "document_manifest": shared["document_manifest"],
            "review_summary": shared["review_summary"],
            "overall_academic_review": shared["overall_academic_review"],
            "study_context": shared["study_context"],
            "statistical_review": shared["statistical_review"],
            "academic_strengths": shared["academic_strengths"],
            "material_findings": shared["material_findings"],
            "section_reviews": shared["section_reviews"],
            "alignment_findings": shared["alignment_findings"],
            "discarded_derivative_findings": shared["discarded_derivative_findings"],
            "selected_source_evidence": selected_evidence,
            "allowed_evidence_ids": [item["id"] for item in selected_evidence],
        }
        instruction = (
            "Prepare the evidence, interpretation and contribution part of the "
            "external examination. This combined stage is retained only for backwards "
            "compatibility. Each assessed domain must cite exact allowed_evidence_ids."
        )
    elif stage == "adjudication":
        allowed_ids = collect_evidence_ids(prior_outputs or {})
        payload = {
            "examination_information": shared["examination_information"],
            "assessment_rules": shared["assessment_rules"],
            "document_manifest": shared["document_manifest"],
            "review_summary": shared["review_summary"],
            "examiner_a_intellectual_foundation": (prior_outputs or {}).get(
                "foundation", {}
            ),
            "examiner_b_evidence_and_contribution": (prior_outputs or {}).get(
                "evidence_core", {}
            ),
            "examiner_c_integrity_and_presentation": (prior_outputs or {}).get(
                "integrity", {}
            ),
            "previous_examiner_correction_follow_up": shared[
                "previous_examiner_correction_follow_up"
            ],
            "priority_actions": shared["priority_actions"][:30],
            "alignment_findings": shared["alignment_findings"],
            "allowed_evidence_ids": allowed_ids,
            "cited_source_evidence": evidence_catalog(
                paragraphs,
                allowed_ids,
                text_limit=1100 if not concise_retry else 750,
            ),
        }
        instruction = (
            "Act as the final independent adjudicator. Audit the three domain "
            "examiner reports against cited_source_evidence and produce, in one "
            "internally consistent decision, the consolidated corrections schedule, "
            "priority corrections before award, oral examination questions, overall "
            "academic judgement, final recommendation and rationale, correction-"
            "verification arrangements, viva recommendation, confidential comments "
            "to the university and examiner declaration. Consolidate duplicates, "
            "reject unsupported or misplaced concerns, and ensure correction severity "
            "is proportionate to the final recommendation. Every correction must cite "
            "one or more exact allowed_evidence_ids. Verify every factual and numerical "
            "claim against cited_source_evidence. If manifest coverage is limited or "
            "insufficient, use assessment_withheld_incomplete_extraction with low "
            "confidence. Include no more than 35 material corrections and 14 thesis-"
            "specific oral questions. Keep the candidate-facing rationale below 340 "
            "words and confidential comments below 280 words."
        )
    elif stage == "corrections":
        allowed_ids = collect_evidence_ids(prior_outputs or {})
        payload = {
            "examination_information": shared["examination_information"],
            "assessment_rules": shared["assessment_rules"],
            "document_manifest": shared["document_manifest"],
            "review_summary": shared["review_summary"],
            "foundation_assessment": (prior_outputs or {}).get("foundation", {}),
            "evidence_assessment": (prior_outputs or {}).get("evidence", {}),
            "priority_actions": shared["priority_actions"][:30],
            "material_findings": shared["material_findings"][:40],
            "previous_examiner_correction_follow_up": shared[
                "previous_examiner_correction_follow_up"
            ],
            "alignment_findings": shared["alignment_findings"],
            "allowed_evidence_ids": allowed_ids,
            "cited_source_evidence": evidence_catalog(
                paragraphs,
                allowed_ids,
                text_limit=1200 if not concise_retry else 800,
            ),
        }
        instruction = (
            "Prepare only the formal corrections schedule, priority corrections, "
            "correction-verification assessment and oral examination questions. "
            "Consolidate duplicates and discard unsupported derivative findings. "
            "Every correction must cite one or more allowed evidence_ids already "
            "used in the verified domain assessments. Verify every factual and "
            "numerical claim against cited_source_evidence. Include no more than 35 "
            "material corrections and 14 thesis-specific oral questions."
        )
    elif stage == "decision":
        payload = {
            "examination_information": shared["examination_information"],
            "assessment_rules": shared["assessment_rules"],
            "document_manifest": shared["document_manifest"],
            "review_summary": shared["review_summary"],
            "foundation_assessment": (prior_outputs or {}).get("foundation", {}),
            "evidence_assessment": (prior_outputs or {}).get("evidence", {}),
            "corrections_and_questions": (prior_outputs or {}).get(
                "corrections", {}
            ),
            "previous_examiner_correction_follow_up": shared[
                "previous_examiner_correction_follow_up"
            ],
            "cited_source_evidence": evidence_catalog(
                paragraphs,
                collect_evidence_ids(prior_outputs or {}),
                text_limit=900 if not concise_retry else 650,
            ),
        }
        instruction = (
            "Make the final independent examiner decision only. Produce the "
            "overall academic judgement, recommendation and rationale, confidential "
            "comments to the university, confidence, correction-verification "
            "authority, viva recommendation and declaration. The recommendation "
            "must be proportionate to evidence-grounded deficiencies. Independently "
            "audit the prior assessments against cited_source_evidence before deciding. If the "
            "manifest coverage_status is limited or insufficient, select "
            "assessment_withheld_incomplete_extraction. Keep the candidate-facing "
            "rationale below 340 words and confidential comments below 280 words."
        )
    else:
        raise ValueError(f"Unknown external-assessment stage: {stage}")

    retry_note = (
        " This is a concise recovery attempt. Use shorter sentences, remove "
        "repetition and stay well within the requested limits."
        if concise_retry
        else ""
    )
    feedback_note = ""
    if validation_feedback:
        safe_feedback = _feedback_for_prompt(validation_feedback)
        feedback_note = (
            " The previous draft failed mandatory evidence validation. Correct every "
            "point below and do not repeat it: "
            + " | ".join(safe_feedback[:12])
        )
    return (
        instruction
        + retry_note
        + feedback_note
        + " Use formal British English. The manifest and source excerpts outrank "
          "all derivative review summaries. Never convert not_confidently_located "
          "into missing or absent. Return the requested JSON object only.\n\n"
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )

def _renumber_corrections(report: Dict[str, Any]) -> None:
    corrections = report.get("corrections") or []
    for index, correction in enumerate(corrections, start=1):
        if isinstance(correction, dict):
            correction["number"] = index


def _enforce_recommendation_consistency(
    report: Dict[str, Any],
    manifest: Optional[Dict[str, Any]] = None,
    *,
    assessment_stage: str = "initial_examination",
) -> None:
    recommendation = report.get("final_recommendation")
    coverage_status = (manifest or {}).get("coverage_status")
    if coverage_status in {"limited", "insufficient"}:
        report["final_recommendation"] = "assessment_withheld_incomplete_extraction"
        report["recommendation_confidence"] = "low"
        report["recommendation_rationale"] = (
            "No academic recommendation has been issued because the source document "
            "did not pass the mandatory extraction and coverage checks. The thesis "
            "must be reprocessed or manually verified before an examiner judgement is "
            "released."
        )
        report["recommendation_consistency_adjusted"] = (
            recommendation != "assessment_withheld_incomplete_extraction"
        )
        report["recommendation_adjustment_reason"] = "source_coverage_not_sufficient"
        return

    if recommendation == "assessment_withheld_incomplete_extraction":
        report["recommendation_consistency_adjusted"] = False
        report["recommendation_adjustment_reason"] = "model_withheld_despite_sufficient_manifest"
        return

    gate = report.get("chapter_one_gate_status")
    corrections = [
        item for item in (report.get("corrections") or [])
        if isinstance(item, dict)
    ]
    correction_counts = {
        level: sum(1 for item in corrections if item.get("classification") == level)
        for level in ("critical", "major", "moderate", "minor")
    }
    domains = [
        report.get(field) or {}
        for field in DOMAIN_FIELDS
        if isinstance(report.get(field), dict)
    ]
    fundamental = sum(
        1 for domain in domains
        if domain.get("judgement") == "fundamentally_deficient"
    )
    major_revision_domains = sum(
        1 for domain in domains
        if domain.get("judgement") == "partly_appropriate_major_revision_required"
    )
    domain_actions = sum(
        len(domain.get("required_corrections") or []) for domain in domains
    )
    domain_concerns = sum(len(domain.get("concerns") or []) for domain in domains)

    replacement = recommendation
    reason = ""
    initial_stage = assessment_stage == "initial_examination"
    correction_verdicts = {
        "corrections_satisfactorily_completed",
        "corrections_not_satisfactorily_completed",
    }
    if initial_stage and recommendation in correction_verdicts:
        replacement = (
            "pass_subject_to_major_corrections"
            if correction_counts["critical"] or correction_counts["major"] or major_revision_domains
            else "pass_subject_to_minor_corrections"
        )
        reason = "correction_verdict_not_valid_at_initial_examination"
    elif gate == "fundamentally_deficient" and recommendation in {
        "pass_without_corrections",
        "pass_subject_to_minor_corrections",
        "pass_subject_to_major_corrections",
    }:
        replacement = "revise_and_resubmit_for_re_examination"
        reason = "foundational_gate_fundamentally_deficient"
    elif recommendation == "pass_without_corrections" and (
        correction_counts["critical"]
        or correction_counts["major"]
        or major_revision_domains
        or fundamental
        or gate == "major_concern"
    ):
        replacement = "pass_subject_to_major_corrections"
        reason = "major_verified_deficiencies_incompatible_with_unqualified_pass"
    elif recommendation == "pass_without_corrections" and (
        corrections or domain_actions or domain_concerns
    ):
        replacement = "pass_subject_to_minor_corrections"
        reason = "recorded_corrections_incompatible_with_unqualified_pass"
    elif recommendation == "pass_subject_to_minor_corrections" and (
        correction_counts["critical"]
        or correction_counts["major"]
        or major_revision_domains
        or fundamental
        or gate == "major_concern"
    ):
        replacement = "pass_subject_to_major_corrections"
        reason = "major_verified_deficiencies_incompatible_with_minor_corrections"
    elif recommendation in {"fail", "award_lower_degree_where_permitted"} and not (
        fundamental >= 2
        or (fundamental >= 1 and correction_counts["critical"] >= 1)
    ):
        replacement = (
            "revise_and_resubmit_for_re_examination"
            if fundamental or correction_counts["critical"] or major_revision_domains >= 2
            else "pass_subject_to_major_corrections"
        )
        reason = "terminal_recommendation_not_supported_by_verified_severity"

    if replacement != recommendation:
        report["final_recommendation"] = replacement
        rationale = clean_text(report.get("recommendation_rationale", ""))
        report["recommendation_rationale"] = (
            rationale
            + " The recommendation has been aligned with the evidence-grounded "
              "critical-gate, domain-judgement and correction-classification rules."
        ).strip()
        report["recommendation_consistency_adjusted"] = True
        report["recommendation_adjustment_reason"] = reason
    else:
        report["recommendation_consistency_adjusted"] = False
        report["recommendation_adjustment_reason"] = "not_required"


def _domain_fields_for_stage(stage: str) -> Sequence[str]:
    if stage == "foundation":
        return (
            "chapter_one_assessment",
            "research_problem_and_purpose",
            "literature_and_theoretical_foundation",
            "methodology_and_procedures",
        )
    if stage == "evidence_core":
        return (
            "results_or_findings",
            "discussion_and_interpretation",
            "conclusions_recommendations_and_contribution",
            "structural_coherence_and_alignment",
        )
    if stage == "integrity":
        return (
            "academic_writing_and_presentation",
            "ethics_and_research_integrity",
            "originality_and_contribution",
        )
    if stage == "evidence":
        return (
            "results_or_findings",
            "discussion_and_interpretation",
            "conclusions_recommendations_and_contribution",
            "structural_coherence_and_alignment",
            "academic_writing_and_presentation",
            "ethics_and_research_integrity",
            "originality_and_contribution",
        )
    return ()


def _allowed_ids_for_stage(
    stage: str,
    runtime_context: Dict[str, Any],
    manifest: Dict[str, Any],
    prior_outputs: Optional[Dict[str, Any]],
    *,
    concise_retry: bool,
    additional_evidence_ids: Sequence[str] = (),
) -> List[str]:
    if stage in {"foundation", "evidence_core", "integrity", "evidence"}:
        evidence = _selected_evidence_for_stage(
            stage,
            runtime_context,
            manifest,
            concise_retry=concise_retry,
            additional_evidence_ids=additional_evidence_ids,
        )
        return [item["id"] for item in evidence]
    if stage in {"adjudication", "corrections"}:
        return collect_evidence_ids(prior_outputs or {})
    return list(manifest.get("valid_evidence_ids") or [])


DOMAIN_ROLE_EXPECTATIONS: Dict[str, Sequence[str]] = {
    "chapter_one_assessment": ("foundation",),
    "research_problem_and_purpose": ("foundation",),
    "literature_and_theoretical_foundation": ("literature_theory",),
    "methodology_and_procedures": ("methodology",),
    "results_or_findings": ("results",),
    "discussion_and_interpretation": ("discussion",),
    "conclusions_recommendations_and_contribution": ("conclusions",),
    "ethics_and_research_integrity": ("ethics",),
    "originality_and_contribution": ("discussion", "conclusions"),
}


def _relevant_manifest_ids(field: str, manifest: Dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for role in DOMAIN_ROLE_EXPECTATIONS.get(field, ()):
        role_data = (manifest.get("role_presence") or {}).get(role) or {}
        ids.update(clean_text(value) for value in role_data.get("evidence_ids") or [] if clean_text(value))
    return ids


def _validate_stage_output(
    stage: str,
    data: Dict[str, Any],
    *,
    manifest: Dict[str, Any],
    metadata: Dict[str, Any],
    allowed_ids: Sequence[str],
) -> List[str]:
    feedback: List[str] = []
    unsupported = validate_evidence_ids(data, allowed_ids)
    if unsupported:
        feedback.append(
            "Unsupported evidence IDs were used: " + ", ".join(unsupported[:12])
        )

    for field in _domain_fields_for_stage(stage):
        domain = data.get(field) or {}
        evidence_ids = domain.get("evidence_ids") or []
        coverage_status = domain.get("coverage_status")
        if coverage_status in {"fully_assessed", "partly_assessed"} and not evidence_ids:
            feedback.append(f"{field} has no evidence_ids despite being assessed.")
        judgement = domain.get("judgement")
        if coverage_status == "not_assessed_due_to_retrieval_limit" and judgement != "not_applicable":
            feedback.append(
                f"{field} must use judgement=not_applicable when it was not assessed due to retrieval limits."
            )
        if coverage_status == "not_assessed_due_to_retrieval_limit":
            if domain.get("concerns") or domain.get("required_corrections"):
                feedback.append(
                    f"{field} cannot impose concerns or corrections when source retrieval prevented assessment."
                )
        expected_roles = DOMAIN_ROLE_EXPECTATIONS.get(field, ())
        role_states = [
            ((manifest.get("role_presence") or {}).get(role) or {}).get("status")
            for role in expected_roles
        ]
        if expected_roles and role_states and all(state != "present" for state in role_states):
            if coverage_status != "not_assessed_due_to_retrieval_limit":
                feedback.append(
                    f"{field} must use coverage_status=not_assessed_due_to_retrieval_limit because its research function was not confidently located."
                )
        relevant_ids = _relevant_manifest_ids(field, manifest)
        if relevant_ids and evidence_ids and not relevant_ids.intersection(evidence_ids):
            feedback.append(
                f"{field} cites evidence outside the manifest's relevant research function."
            )

    if stage in {"adjudication", "corrections"}:
        for index, item in enumerate(data.get("corrections") or [], start=1):
            if not item.get("evidence_ids"):
                feedback.append(f"Correction {index} has no evidence_ids.")

    contradictions = find_presence_contradictions(data, manifest, metadata=metadata)
    for item in contradictions[:12]:
        feedback.append(
            f"{item['path']} violates the manifest absence rule for "
            f"{item['component']} ({item.get('manifest_status')}): {item['sentence']}"
        )

    numeric_issues = find_unsupported_numeric_claims(
        data,
        manifest.get("annotated_source_rows") or [],
    )
    for item in numeric_issues[:12]:
        feedback.append(
            f"{item['path']} contains numerical claim {item['token']} that is not present in its cited evidence."
        )

    reference_risks = find_unsupported_reference_risk_claims(data, manifest)
    for item in reference_risks[:12]:
        feedback.append(
            f"{item['path']} makes a high-risk reference allegation without citing the exact reference-list evidence."
        )

    if stage in {"adjudication", "decision"}:
        recommendation = data.get("final_recommendation")
        if manifest.get("coverage_status") in {"limited", "insufficient"} and recommendation != "assessment_withheld_incomplete_extraction":
            feedback.append(
                "The manifest coverage_status is not sufficient, so the decision must be assessment_withheld_incomplete_extraction."
            )
        if manifest.get("coverage_status") in {"limited", "insufficient"} and data.get("recommendation_confidence") != "low":
            feedback.append(
                "Recommendation confidence must be low when the academic recommendation is withheld for source coverage."
            )

    return feedback


def prepare_external_assessment(
    report: Dict[str, Any],
    metadata: Dict[str, Any],
    review: Dict[str, Any],
    manifest: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    value = dict(report)
    _renumber_corrections(value)

    summary = review.get("summary") or {}
    assessment_metadata = _metadata_payload(metadata, summary, manifest)
    if manifest:
        contradictions = find_presence_contradictions(
            value,
            manifest,
            metadata=assessment_metadata,
        )
        unsupported = validate_evidence_ids(
            value,
            manifest.get("valid_evidence_ids") or [],
        )
        numeric_issues = find_unsupported_numeric_claims(
            value,
            manifest.get("annotated_source_rows") or [],
        )
        reference_risks = find_unsupported_reference_risk_claims(value, manifest)
        if contradictions or unsupported or numeric_issues or reference_risks:
            details = []
            if contradictions:
                details.append(
                    "source contradictions: "
                    + "; ".join(item["sentence"] for item in contradictions[:5])
                )
            if unsupported:
                details.append(
                    "unsupported evidence IDs: " + ", ".join(unsupported[:12])
                )
            if numeric_issues:
                details.append(
                    "unsupported numerical claims: "
                    + "; ".join(
                        f"{item['path']}={item['token']}" for item in numeric_issues[:12]
                    )
                )
            if reference_risks:
                details.append(
                    "unsupported reference allegations: "
                    + "; ".join(item["path"] for item in reference_risks[:12])
                )
            raise ExternalAssessmentValidationError(
                "The external examination draft failed the final evidence audit, "
                + " | ".join(details)
            )

    if manifest and manifest.get("coverage_status") in {"limited", "insufficient"}:
        value["recommendation_confidence"] = "low"

    _enforce_recommendation_consistency(
        value,
        manifest,
        assessment_stage=assessment_metadata.get("assessment_stage", "initial_examination"),
    )
    value["recommendation_label"] = RECOMMENDATION_LABELS.get(
        value.get("final_recommendation"),
        str(value.get("final_recommendation", "")).replace("_", " ").title(),
    )
    value["assessment_metadata"] = assessment_metadata
    value["workflow_type"] = "external_assessment"
    value["report_status"] = (
        "Assessment withheld pending source verification"
        if value.get("final_recommendation") == "assessment_withheld_incomplete_extraction"
        else "Examiner-ready draft requiring examiner review and signature"
    )
    value["domain_order"] = list(DOMAIN_FIELDS)
    value["correction_counts"] = {
        level: sum(
            1 for item in value.get("corrections") or []
            if isinstance(item, dict) and item.get("classification") == level
        )
        for level in ("critical", "major", "moderate", "minor")
    }
    if manifest:
        shared_quality = _shared_payload(review, metadata, manifest)
        discarded = shared_quality.get("discarded_derivative_findings") or {}
        report_evidence_ids = collect_evidence_ids(value)
        evidence_register = evidence_catalog(
            manifest.get("annotated_source_rows") or [],
            report_evidence_ids,
            text_limit=650,
        )
        value["source_evidence_register"] = evidence_register
        report_evidence_count = len(evidence_register)
        value["source_manifest"] = compact_manifest_for_prompt(manifest)
        value["quality_assurance"] = {
            "audit_status": (
                "passed_recommendation_withheld"
                if manifest.get("coverage_status") in {"limited", "insufficient"}
                else "passed"
            ),
            "manifest_hash": manifest.get("manifest_hash"),
            "coverage_status": manifest.get("coverage_status"),
            "coverage_score": manifest.get("coverage_score"),
            "detected_chapters": manifest.get("detected_chapters"),
            "word_count": manifest.get("word_count"),
            "table_count": manifest.get("table_count"),
            "evidence_reference_count": report_evidence_count,
            "unsupported_evidence_count": 0,
            "presence_contradiction_count": 0,
            "derivative_findings_filtered": sum(
                int(discarded.get(key) or 0)
                for key in (
                    "academic_strengths",
                    "priority_actions",
                    "material_findings",
                    "section_reviews",
                    "alignment_findings",
                    "overall_academic_review",
                )
            ),
        }
    return value

async def _complete_assessment_stage(
    provider: OpenAIProvider,
    *,
    stage: str,
    schema_model: type,
    review: Dict[str, Any],
    runtime_context: Dict[str, Any],
    metadata: Dict[str, Any],
    manifest: Dict[str, Any],
    config: HybridAIConfig,
    prior_outputs: Optional[Dict[str, Any]],
    model: str,
    max_output_tokens: int,
    reasoning_effort: str,
    checkpoint_manager: Optional[CheckpointManager] = None,
    retry_generation: int = 0,
) -> Any:
    last_error: Optional[Exception] = None
    validation_feedback: List[str] = []
    additional_evidence_ids: List[str] = []
    valid_manifest_ids = set(manifest.get("valid_evidence_ids") or [])
    attempts = (
        {"concise": False, "grounding_retry": False},
        {"concise": True, "grounding_retry": True},
    )

    for attempt_number, attempt in enumerate(attempts, start=1):
        concise_retry = bool(attempt["concise"])
        feedback = validation_feedback if attempt["grounding_retry"] else []
        user_prompt = _stage_prompt(
            stage,
            review,
            runtime_context,
            metadata,
            manifest,
            prior_outputs=prior_outputs,
            concise_retry=concise_retry,
            validation_feedback=feedback,
            additional_evidence_ids=additional_evidence_ids,
        )
        allowed_ids = _allowed_ids_for_stage(
            stage,
            runtime_context,
            manifest,
            prior_outputs,
            concise_retry=concise_retry,
            additional_evidence_ids=additional_evidence_ids,
        )
        input_hash = stable_hash({
            "pipeline": "external-assessment-v1.9.6-three-examiners-one-adjudicator",
            "retry_generation": int(retry_generation or 0),
            "stage": stage,
            "attempt_number": attempt_number,
            "concise_retry": concise_retry,
            "validation_feedback": _feedback_for_prompt(feedback),
            "additional_evidence_ids": additional_evidence_ids,
            "manifest_hash": manifest.get("manifest_hash"),
            "model": model,
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
                cached_feedback = _validate_stage_output(
                    stage,
                    cached.data,
                    manifest=manifest,
                    metadata=_metadata_payload(
                        metadata,
                        review.get("summary") or {},
                        manifest,
                    ),
                    allowed_ids=allowed_ids,
                )
                if not cached_feedback:
                    return cached
                validation_feedback = cached_feedback
                cached_unsupported = validate_evidence_ids(cached.data, allowed_ids)
                for evidence_id in cached_unsupported:
                    if (
                        evidence_id in valid_manifest_ids
                        and evidence_id not in additional_evidence_ids
                    ):
                        additional_evidence_ids.append(evidence_id)
                checkpoint_manager.mark_failed(
                    stage_key,
                    "Cached stage output failed current evidence validation.",
                )
                continue

            checkpoint_manager.mark_running(
                stage_key,
                input_hash=input_hash,
                message=f"Preparing grounded external assessment stage: {stage}",
            )
        try:
            result = await provider.complete_json(
                model=model,
                system_prompt=EXTERNAL_ASSESSMENT_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                schema_model=schema_model,
                purpose=f"external_thesis_assessment_{stage}",
                reasoning_effort=reasoning_effort,
                max_output_tokens=max_output_tokens,
                request_timeout_seconds=(
                    config.external_assessment_request_timeout_seconds
                ),
                request_max_retries=(
                    config.external_assessment_request_max_retries
                ),
            )
            stage_feedback = _validate_stage_output(
                stage,
                result.data,
                manifest=manifest,
                metadata=_metadata_payload(
                    metadata,
                    review.get("summary") or {},
                    manifest,
                ),
                allowed_ids=allowed_ids,
            )
            if stage_feedback:
                validation_feedback = stage_feedback
                unsupported_ids = validate_evidence_ids(result.data, allowed_ids)
                for evidence_id in unsupported_ids:
                    if (
                        evidence_id in valid_manifest_ids
                        and evidence_id not in additional_evidence_ids
                    ):
                        additional_evidence_ids.append(evidence_id)
                last_error = ExternalAssessmentValidationError(
                    f"External assessment stage '{stage}' failed evidence validation: "
                    + " | ".join(stage_feedback[:8])
                )
                if checkpoint_manager is not None:
                    checkpoint_manager.mark_failed(stage_key, str(last_error))
                continue

            if checkpoint_manager is not None:
                checkpoint_manager.save_provider_result(
                    stage_key,
                    result,
                    input_hash=input_hash,
                    message=f"Grounded external assessment stage completed: {stage}",
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
            if not recoverable:
                break

    if isinstance(last_error, ExternalAssessmentValidationError):
        raise last_error
    raise AIProviderError(
        f"External assessment stage '{stage}' could not be completed: "
        f"{last_error or 'provider request failed'}"
    )

def _costed_usage(result: Any, config: HybridAIConfig) -> tuple[Any, float]:
    uncached = max(
        0,
        result.usage.input_tokens - result.usage.cached_input_tokens,
    )
    input_price, cached_price, output_price = config.openai_prices_for_model(
        result.usage.model
    )
    estimated_cost = (
        uncached / 1_000_000 * input_price
        + result.usage.cached_input_tokens / 1_000_000 * cached_price
        + result.usage.output_tokens / 1_000_000 * output_price
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
    retry_generation: int = 0,
) -> Dict[str, Any]:
    if not config.openai_configured:
        raise AIProviderError(
            "OpenAI is required to prepare the external examination report."
        )

    async def progress(value: int, message: str) -> None:
        if progress_callback is None:
            return
        result = progress_callback(value, message)
        if hasattr(result, "__await__"):
            await result

    async def run_parallel(
        specs: Dict[str, Any],
        *,
        start_progress: int,
        end_progress: int,
        phase_label: str,
    ) -> Dict[str, Any]:
        """Run independent grounded stages concurrently and report each completion."""

        task_to_stage: Dict[asyncio.Task[Any], str] = {}
        for stage_name, coroutine in specs.items():
            task = asyncio.create_task(
                asyncio.wait_for(
                    coroutine,
                    timeout=config.external_assessment_stage_timeout_seconds,
                )
            )
            task_to_stage[task] = stage_name

        completed: Dict[str, Any] = {}
        total = max(1, len(task_to_stage))
        try:
            pending = set(task_to_stage)
            while pending:
                done, pending = await asyncio.wait(
                    pending,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in done:
                    stage_name = task_to_stage[task]
                    completed[stage_name] = await task
                    fraction = len(completed) / total
                    value = round(
                        start_progress
                        + (end_progress - start_progress) * fraction
                    )
                    label = stage_name.replace("_", " ").title()
                    await progress(
                        value,
                        f"{label} completed. {phase_label} continues in parallel",
                    )
        except Exception:
            for task in task_to_stage:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*task_to_stage, return_exceptions=True)
            raise
        return completed

    paragraphs = runtime_context.get("current_paragraphs") or []
    manifest = build_document_manifest(
        paragraphs,
        summary=review.get("summary") or {},
    )
    review["external_document_manifest"] = compact_manifest_for_prompt(manifest)

    required_stage_ids = {
        stage: _allowed_ids_for_stage(
            stage,
            runtime_context,
            manifest,
            None,
            concise_retry=False,
        )
        for stage in ("foundation", "evidence_core", "integrity")
    }
    missing_stages = [
        stage for stage, evidence_ids in required_stage_ids.items()
        if not evidence_ids
    ]
    if missing_stages:
        raise ExternalAssessmentValidationError(
            "The external examination was stopped because source evidence could "
            "not be distributed to these assessment stages: "
            + ", ".join(missing_stages)
            + ". Re-export the thesis as a complete text-based DOCX or PDF and "
              "submit it again."
        )

    provider = OpenAIProvider(config)
    outputs: Dict[str, Any] = {}
    results: List[Any] = []

    await progress(
        87,
        "Three independent examiners are assessing the thesis in parallel",
    )
    analysis_results = await run_parallel(
        {
            "foundation": _complete_assessment_stage(
                provider,
                stage="foundation",
                schema_model=ExternalAssessmentFoundation,
                review=review,
                runtime_context=runtime_context,
                metadata=metadata,
                manifest=manifest,
                config=config,
                prior_outputs=None,
                model=config.openai_external_domain_model,
                max_output_tokens=(
                    config.external_assessment_foundation_max_output_tokens
                ),
                reasoning_effort=(
                    config.openai_external_domain_reasoning_effort
                ),
                checkpoint_manager=checkpoint_manager,
                retry_generation=retry_generation,
            ),
            "evidence_core": _complete_assessment_stage(
                provider,
                stage="evidence_core",
                schema_model=ExternalAssessmentEvidenceCore,
                review=review,
                runtime_context=runtime_context,
                metadata=metadata,
                manifest=manifest,
                config=config,
                prior_outputs=None,
                model=config.openai_external_domain_model,
                max_output_tokens=(
                    config.external_assessment_evidence_max_output_tokens
                ),
                reasoning_effort=(
                    config.openai_external_domain_reasoning_effort
                ),
                checkpoint_manager=checkpoint_manager,
                retry_generation=retry_generation,
            ),
            "integrity": _complete_assessment_stage(
                provider,
                stage="integrity",
                schema_model=ExternalAssessmentIntegrity,
                review=review,
                runtime_context=runtime_context,
                metadata=metadata,
                manifest=manifest,
                config=config,
                prior_outputs=None,
                model=config.openai_external_domain_model,
                max_output_tokens=(
                    config.external_assessment_integrity_max_output_tokens
                ),
                reasoning_effort=(
                    config.openai_external_domain_reasoning_effort
                ),
                checkpoint_manager=checkpoint_manager,
                retry_generation=retry_generation,
            ),
        },
        start_progress=87,
        end_progress=92,
        phase_label="The remaining evidence domains",
    )

    foundation = analysis_results["foundation"]
    evidence_core = analysis_results["evidence_core"]
    integrity = analysis_results["integrity"]
    outputs["foundation"] = foundation.data
    evidence_payload = {
        **evidence_core.data,
        **integrity.data,
    }
    outputs["evidence"] = ExternalAssessmentEvidence.model_validate(
        evidence_payload
    ).model_dump()
    results.extend([foundation, evidence_core, integrity])

    await progress(
        94,
        "The final adjudicator is consolidating corrections and recommendation",
    )
    try:
        adjudication = await asyncio.wait_for(
            _complete_assessment_stage(
                provider,
                stage="adjudication",
                schema_model=ExternalAssessmentAdjudication,
                review=review,
                runtime_context=runtime_context,
                metadata=metadata,
                manifest=manifest,
                config=config,
                prior_outputs={
                    "foundation": outputs["foundation"],
                    "evidence_core": evidence_core.data,
                    "integrity": integrity.data,
                },
                model=config.openai_external_adjudicator_model,
                max_output_tokens=(
                    config.external_assessment_adjudication_max_output_tokens
                ),
                reasoning_effort=(
                    config.openai_external_adjudicator_reasoning_effort
                ),
                checkpoint_manager=checkpoint_manager,
                retry_generation=retry_generation,
            ),
            timeout=config.external_assessment_stage_timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        raise AIProviderError(
            "The final external-examination adjudication timed out safely. "
            "Resume the review to reuse the three completed examiner reports."
        ) from exc

    outputs["adjudication"] = adjudication.data
    results.append(adjudication)
    await progress(96, "The final external-examination adjudication is complete")

    merged = {
        **outputs["foundation"],
        **outputs["evidence"],
        **outputs["adjudication"],
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
        manifest,
    )

    usage_records = []
    total_cost = 0.0
    for result in results:
        usage, estimated_cost = _costed_usage(result, config)
        usage_records.append(usage.model_dump())
        total_cost += estimated_cost

    review["external_assessment"] = assessment
    review["external_assessment_usage"] = {
        "generation_mode": "three_examiners_one_adjudicator",
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
        ai_review["external_assessment_generation_mode"] = (
            "three_examiners_one_adjudicator"
        )

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
        "external_assessment_generation_mode": "three_examiners_one_adjudicator",
        "external_assessment_stage_count": 4,
        "external_assessment_manifest_hash": manifest.get("manifest_hash"),
        "external_assessment_coverage_status": manifest.get("coverage_status"),
        "external_assessment_coverage_score": manifest.get("coverage_score"),
        "external_assessment_detected_chapters": manifest.get("detected_chapters"),
        "external_assessment_evidence_audit": (
            "passed"
            if manifest.get("coverage_status") == "sufficient"
            else "passed_recommendation_withheld"
        ),
        "readiness_label": assessment["recommendation_label"],
        "readiness_meaning": assessment["recommendation_rationale"],
    })
    await progress(97, "Generating the external examination documents")
    return review

