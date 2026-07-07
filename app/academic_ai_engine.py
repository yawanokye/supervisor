from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import re
from datetime import datetime, timezone
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .ai_config import AIConfigurationError, HybridAIConfig
from .ai_prompts import (
    ACADEMIC_REVIEW_SYSTEM_PROMPT,
    ACADEMIC_VERIFY_SYSTEM_PROMPT,
    FOCUSED_SECTION_RECOVERY_SYSTEM_PROMPT,
    LIGHT_REVIEW_SYSTEM_PROMPT,
)
from .ai_providers import AIProviderError, ProviderResult
from .model_router import CostAwareAIProvider, ReviewStage, stage_for_depth
from .academic_review_guide import guide_for_heading
from .context_guard import build_context_lock, public_context, sanitise_generated_text, sanitise_issue
from .checkpointing import CheckpointManager, stable_hash
from .ai_schemas import (
    AIUsageRecord,
    AcademicIssue,
    AcademicReviewBatch,
    AcademicSectionReviewItem,
    AcademicVerificationBatch,
)
from .document_parser import clean_text, normalised
from .comment_quality import prepare_public_issues
from .deterministic_supervisory_checklist import deterministic_supervisory_checklist_issues
from .supervisory_accuracy_guard import (
    apply_accuracy_gate,
    build_factual_index,
    deterministic_expert_issues,
    guard_section_assessment,
    guard_strength,
    is_synthetic_section,
    source_section,
)

SEVERITY_ORDER = {"critical": 0, "major": 1, "moderate": 2, "minor": 3}
class ReviewOutputValidationError(RuntimeError):
    """Raised when a review would complete without usable, grounded feedback."""


ACTIONABLE_STATUS = {
    "critical": ("does_not_meet_requirement", "Critical revision"),
    "major": ("does_not_meet_requirement", "Major revision"),
    "moderate": ("partly_meets_requirement", "Revision required"),
    "minor": ("partly_meets_requirement", "Minor correction"),
}

CHAPTER_DIMENSIONS: Dict[int, List[str]] = {
    1: [
        "title accuracy and scope",
        "background progression and evidence",
        "a clear, specific, significant and researchable problem",
        "the practical or empirical condition and the defensible knowledge gap",
        "problem consequences, affected population or unit and actual study context",
        "purpose and objectives that flow directly from the problem",
        "one-to-one alignment of objectives and research questions",
        "adequate theoretically justified hypotheses where necessary",
        "significance and contribution",
        "scope, limitations, definitions and chapter organisation",
        "terminology consistency, academic writing and citations",
    ],
    2: [
        "review and clarification of all central concepts",
        "appropriate theory selection, critique and application",
        "critical empirical synthesis rather than study-by-study enumeration",
        "organisation around objectives, constructs or relationships",
        "comparison of contexts, methods, data and findings",
        "contradictions, limitations and unresolved issues in prior studies",
        "research gap, hypothesis or proposition development and conceptual framework",
        "clear implications of the literature for the study",
        "source quality, recency, citation accuracy and academic writing",
    ],
    3: [
        "research paradigm, approach, design and time-horizon fit",
        "methods and procedures aligned with every objective, question and hypothesis",
        "study setting, population, sampling frame, sample size and selection procedures",
        "instrument or data-source development and measurement",
        "validity, reliability, trustworthiness and pilot evidence",
        "data collection procedures, ethics and data protection",
        "data preparation and analysis mapped objective by objective",
        "model specification, assumptions, model-specific diagnostics, thresholds, remedies and reproducibility",
        "proposal or completed-study tense and procedural accuracy",
    ],
    4: [
        "advance organiser and actual analysed sample",
        "complete objective-by-objective or hypothesis-by-hypothesis presentation",
        "internal accuracy of narrative, tables, figures, totals and sample sizes",
        "accuracy of coefficients, signs, significance values, intervals and decisions",
        "presence and interpretation of diagnostics appropriate to the statistical model",
        "reconciliation of sample sizes, totals, percentages, tables, figures and narrative claims",
        "appropriate statistical, qualitative or mixed-method interpretation",
        "distinction between results, interpretation and discussion",
        "thorough discussion against theory and empirical literature",
        "unexpected findings, contradictions and alternative explanations",
        "theoretical, practical and policy implications",
        "consistency with Chapter Three and reporting standards",
    ],
    5: [
        "overview of purpose, questions or hypotheses and methods",
        "summary of main findings by objective without repeating the analysis",
        "conclusions drawn from findings rather than restated results",
        "unexpected findings, contribution and implications",
        "recommendations traceable to specific findings",
        "responsible actors and realistic implementation where appropriate",
        "limitations and suggestions for further research",
        "absence of new evidence and consistency with the research problem",
        "academic writing and presentation",
    ],
}

KEY_ALIGNMENT_TERMS = (
    "statement of the problem", "problem statement", "purpose of the study", "research objective",
    "objective of the study", "specific objective", "research question", "hypothesis", "theoretical",
    "conceptual framework", "methodology", "research design", "population", "sampling", "data analysis",
    "result", "finding", "conclusion", "recommendation",
)


REVIEW_LEVEL_PROFILES: Dict[str, Dict[str, Any]] = {
    "light": {
        "label": "Light Review",
        "benchmark": "Concise review at the declared degree standard",
        "focus": (
            "Review every section and subsection, but report only the most material issues. "
            "The declared academic level remains the substantive benchmark."
        ),
        "normal_issue_limit_per_section": 2,
        "quality_control_max_findings": 12,
    },
    "standard": {
        "label": "Standard Review",
        "benchmark": "Full review at the declared degree standard",
        "focus": (
            "Conduct a complete section-by-section and subsection-by-subsection review. "
            "Assess structure, evidence, theory, methods, results, alignment and contribution at the declared academic level."
        ),
        "normal_issue_limit_per_section": 4,
        "quality_control_max_findings": 24,
    },
    "advanced": {
        "label": "Advanced Review",
        "benchmark": "Intensive review and independent audit at the declared degree standard",
        "focus": (
            "Conduct a complete review with a compact independent second-pass audit. "
            "Increase scrutiny and robustness checks without imposing a degree standard above the declared programme."
        ),
        "normal_issue_limit_per_section": 5,
        "quality_control_max_findings": 32,
    },
}


DEGREE_LEVEL_PROFILES: Dict[str, Dict[str, Any]] = {
    "bachelors": {
        "label": "Bachelor’s dissertation",
        "orientation": "foundational-research",
        "benchmark": (
            "Require a clear and researchable problem, coherent use of literature, appropriate and correctly applied methods, "
            "accurate analysis, defensible conclusions and competent academic presentation. Expect a modest but explicit contribution."
        ),
    },
    "non_research_masters": {
        "label": "Non-Research Master’s project",
        "benchmark": (
            "Require a well-defined applied problem, integrated and relevant literature, justified professional or analytical methods, "
            "credible evidence, sound interpretation and practical recommendations proportionate to the design. Do not impose an MPhil-style "
            "theoretical contribution or research-intensive originality requirement unless the programme guideline expressly requires it."
        ),
        "orientation": "applied-master's",
    },
    "research_masters": {
        "label": "Research Master’s or MPhil dissertation",
        "benchmark": (
            "Require research-intensive Master’s depth: critical synthesis rather than description, defensible theoretical and conceptual grounding, "
            "a clearly evidenced research problem and gap, explicit methodological justification, construct and terminology precision, complete "
            "purpose-objective-question-hypothesis-method-result alignment, source traceability, and a clear empirical, theoretical, methodological "
            "or contextual contribution appropriate to MPhil work."
        ),
        "orientation": "research-intensive-master's",
    },
    "professional_doctorate": {
        "label": "Professional Doctorate thesis",
        "orientation": "practice-based-doctoral",
        "benchmark": (
            "Require doctoral rigour, a defensible original contribution to professional practice or policy, strong scholarly positioning, "
            "methodological robustness, critical reflexivity and evidence-based implications for the field of practice."
        ),
    },
    "phd": {
        "label": "PhD thesis",
        "orientation": "knowledge-creation-doctoral",
        "benchmark": (
            "Require an original contribution to knowledge, authoritative theoretical and empirical positioning, methodological rigour, "
            "robustness, engagement with alternative explanations and a defensible scholarly contribution."
        ),
    },
}


def _review_profile(depth: str) -> Dict[str, Any]:
    return REVIEW_LEVEL_PROFILES.get(depth, REVIEW_LEVEL_PROFILES["standard"])


def _degree_profile(academic_level: Any) -> Dict[str, str]:
    value = normalised(str(academic_level or "")).replace("-", " ")
    if value == "phd" or value.startswith("doctor of philosophy"):
        return DEGREE_LEVEL_PROFILES["phd"]
    if "professional doctorate" in value or value.startswith("doctor of ") or value.startswith("doctoral"):
        return DEGREE_LEVEL_PROFILES["professional_doctorate"]
    # Check the non-research label first because the normalised phrase
    # "non research masters" also contains "research masters".
    if "non research masters" in value or "non research master" in value:
        return DEGREE_LEVEL_PROFILES["non_research_masters"]
    if "research masters" in value or "mphil" in value or "research master" in value:
        return DEGREE_LEVEL_PROFILES["research_masters"]
    return DEGREE_LEVEL_PROFILES["bachelors"]


def _combined_benchmark(academic_level: Any, depth: str) -> Dict[str, str]:
    degree = _degree_profile(academic_level)
    intensity = _review_profile(depth)
    return {
        "degree_label": degree["label"],
        "degree_standard": degree["benchmark"],
        "review_intensity": intensity["label"],
        "review_intensity_expectation": intensity["focus"],
    }


def _degree_key(academic_level: Any) -> str:
    value = normalised(str(academic_level or "")).replace("-", " ")
    if value == "phd" or value.startswith("doctor of philosophy"):
        return "phd"
    if "professional doctorate" in value or value.startswith("doctor of ") or value.startswith("doctoral"):
        return "professional_doctorate"
    if "non research masters" in value or "non research master" in value:
        return "non_research_masters"
    if "research masters" in value or "research master" in value or "mphil" in value:
        return "research_masters"
    return "bachelors"


def _is_research_masters_level(academic_level: Any) -> bool:
    return _degree_key(academic_level) == "research_masters"


def _degree_issue_limit(academic_level: Any, depth: str) -> int:
    """Return a degree-calibrated per-section issue ceiling, never a quota."""
    base = int(_review_profile(depth)["normal_issue_limit_per_section"])
    increments = {
        "bachelors": 0,
        "non_research_masters": 1,
        "research_masters": 2,
        "professional_doctorate": 3,
        "phd": 4,
    }
    return base + increments[_degree_key(academic_level)]


def _degree_audit_max_findings(academic_level: Any, depth: str) -> int:
    base = int(_review_profile(depth)["quality_control_max_findings"])
    minimums = {
        "bachelors": {"light": 16, "standard": 32, "advanced": 44},
        "non_research_masters": {"light": 20, "standard": 42, "advanced": 54},
        "research_masters": {"light": 24, "standard": 56, "advanced": 70},
        "professional_doctorate": {"light": 28, "standard": 68, "advanced": 86},
        "phd": {"light": 32, "standard": 80, "advanced": 100},
    }
    return max(base, minimums[_degree_key(academic_level)][depth])


def _degree_comment_floor(academic_level: Any, depth: str, config: HybridAIConfig) -> int:
    """Minimum material comments to preserve for a non-trivial chapter.

    v1.9.9.3 makes the floor stronger for every academic level. The floor is
    still not a licence to invent issues; it tells the orchestrator to keep
    evidence-anchored, public-safe findings instead of over-compressing the
    review into a small number of comments.
    """
    if not config.comment_depth_floor_enabled:
        return 0
    key = _degree_key(academic_level)
    if depth == "light":
        return {
            "bachelors": 8,
            "non_research_masters": 10,
            "research_masters": 12,
            "professional_doctorate": 14,
            "phd": 16,
        }[key]
    if depth == "standard":
        return {
            "bachelors": 14,
            "non_research_masters": max(18, config.standard_non_research_min_findings),
            "research_masters": max(24, config.standard_research_masters_min_findings),
            "professional_doctorate": max(28, config.standard_professional_doctorate_min_findings),
            "phd": max(32, config.standard_phd_min_findings),
        }[key]
    return {
        "bachelors": 20,
        "non_research_masters": max(24, config.standard_non_research_min_findings + 6),
        "research_masters": max(32, config.standard_research_masters_min_findings + 8),
        "professional_doctorate": max(38, config.standard_professional_doctorate_min_findings + 10),
        "phd": max(44, config.standard_phd_min_findings + 12),
    }[key]


def _degree_required_public_categories(academic_level: Any, selected_chapter: Any, depth: str) -> Set[str]:
    """Categories that should be visibly represented in a strong review.

    These are not artificial quotas. They are a final coverage contract: if the
    document genuinely contains evidence-anchored problems in these categories,
    the public report should not silently omit them after model/audit/dedup
    filtering.
    """
    key = _degree_key(academic_level)
    try:
        chapter = int(selected_chapter or 0)
    except (TypeError, ValueError):
        chapter = 0
    base = {"academic_writing", "cross_section_coherence", "chapter_structure"}
    if chapter == 1 or chapter == 0:
        base |= {"research_gap_and_problem", "objectives_questions_hypotheses", "citations_and_sources"}
        if key in {"research_masters", "professional_doctorate", "phd"}:
            base |= {"theoretical_grounding"}
        if key in {"professional_doctorate", "phd"}:
            base |= {"critical_analysis"}
    elif chapter == 2:
        base |= {"critical_analysis", "theoretical_grounding", "citations_and_sources"}
    elif chapter == 3:
        base |= {"methodological_rigour", "ethics_and_integrity", "objectives_questions_hypotheses"}
    elif chapter == 4:
        base |= {"results_and_interpretation", "critical_analysis", "citations_and_sources"}
    elif chapter == 5:
        base |= {"conclusions_and_recommendations", "cross_section_coherence", "critical_analysis"}
    if depth == "light":
        # Light reviews should still catch critical/major issues, but we do not
        # force every category into the visible output.
        return {"cross_section_coherence", "research_gap_and_problem", "objectives_questions_hypotheses", "academic_writing"} & base
    return base


def _category_signature(issue: Dict[str, Any]) -> Tuple[str, str]:
    return (
        str(issue.get("category") or ""),
        hashlib.sha256(normalised(" ".join([
            clean_text(issue.get("section", "")),
            clean_text(issue.get("issue_title", "")),
            clean_text(issue.get("required_action", "")),
        ])).encode("utf-8")).hexdigest()[:24],
    )


def _chapter_review_checks(chapter: int) -> List[str]:
    checks = {
        1: [
            "Check whether the background moves logically from the broad problem to the study context and the precise unresolved issue.",
            "Check whether the problem statement is evidenced, identifies what is not known or not working, explains why the gap matters, and leads directly to the purpose.",
            "Check one-to-one alignment among the title, problem, purpose, objectives, questions and hypotheses where applicable.",
            "Check whether causal, predictive, relational and descriptive verbs are compatible with the intended research design.",
            "Check whether significance is prospective and whether delimitations, limitations, definitions, proposal stage and terminology are internally consistent.",
            "Audit in-text citations, unsupported empirical claims, reference-list correspondence, unresolved prompts and language consistency.",
        ],
        2: [
            "Assess whether the literature is critically synthesised by themes, debates, methods and findings rather than presented as a catalogue of studies.",
            "Check the relevance, currency, authority and traceability of sources and whether contrary evidence is represented fairly.",
            "Check whether theoretical and conceptual choices are explained, integrated and linked to the study variables or phenomena.",
            "Check whether the empirical review establishes a defensible gap and avoids claiming novelty merely because a setting differs.",
        ],
        3: [
            "Check alignment of the approach, design, population, sampling, data sources, instruments, procedures and analysis with every objective and question.",
            "Check operational definitions, measurement validity, reliability or trustworthiness, ethics, bias controls and reproducibility.",
            "Check statistical or qualitative assumptions, model specification, diagnostic procedures and limits of inference.",
        ],
        4: [
            "Check that every objective and hypothesis is answered with the correct analysis and that tables, figures and narratives agree.",
            "Check statistical, qualitative or mixed-method interpretation, assumptions, uncertainty, effect size and avoidance of causal overstatement.",
            "Check whether the discussion explains findings through theory and prior evidence, including contradictions and plausible alternatives.",
        ],
        5: [
            "Check that conclusions are direct answers to the objectives and contain no new evidence or unsupported generalisation.",
            "Check that recommendations arise from specific findings, identify responsible actors and remain feasible within the study evidence.",
            "Check the stated contribution, limitations and future research against what the design and results can genuinely support.",
        ],
    }
    return list(checks.get(chapter, []))


def _degree_specific_review_contract(
    academic_level: Any,
    selected_chapter: Any,
    depth: str,
) -> Dict[str, Any]:
    """Operational review contract for every supported degree level."""
    key = _degree_key(academic_level)
    try:
        chapter = int(selected_chapter or 0)
    except (TypeError, ValueError):
        chapter = 0

    common = [
        "Evaluate every detected section and subsection using direct evidence from the uploaded document.",
        "Distinguish a missing element from a present but weakly developed element.",
        "Consolidate recurring proofreading defects, but do not merge distinct conceptual, alignment, citation or methodological problems.",
        "Check factual support, source traceability, internal consistency and the limits of inference at the declared programme level.",
    ]

    if key == "bachelors":
        required = [
            "a clear, manageable and researchable problem",
            "coherent use of relevant literature and basic conceptual understanding",
            "alignment of the purpose, objectives, questions, methods, results and conclusions",
            "appropriate and correctly applied methods and analysis",
            "accurate interpretation, competent academic writing and a modest explicit contribution",
        ]
        contribution = "Expect a modest but explicit empirical, contextual or practical contribution appropriate to undergraduate research."
        overlay = [
            "Do not impose postgraduate theoretical originality, but require the student to explain rather than merely reproduce sources.",
            "Prioritise fundamental research coherence, correct method application and evidence-based conclusions.",
        ]
    elif key == "non_research_masters":
        required = [
            "clarity, professional relevance and practical importance of the applied problem",
            "coherence of the purpose, objectives, questions, methods, findings and recommendations",
            "integrated and relevant literature that frames the professional problem",
            "fitness and justification of the analytical or professional method",
            "credible interpretation and feasible practice, management or policy recommendations",
            "a defensible applied contribution without imposing research-intensive originality",
        ]
        contribution = "Expect a defensible applied or professional contribution. Do not require an MPhil-level theoretical contribution unless the programme guideline does."
        overlay = [
            "Assess whether the work converts evidence into a credible solution, decision framework, intervention or professional recommendation.",
            "Require scholarly support and methodological justification, while keeping the benchmark focused on advanced application rather than original theory creation.",
        ]
    elif key == "research_masters":
        required = [
            "critical synthesis and scholarly positioning rather than study-by-study description",
            "explicit theoretical or conceptual grounding and precise roles for every central construct",
            "a significant, current and contextually evidenced research problem with a defensible empirical, theoretical, methodological or contextual gap",
            "one-to-one alignment among the title, problem, purpose, objectives, questions, hypotheses where applicable, methods, results, conclusions and recommendations",
            "compatibility between the research design and words such as effect, impact, influence, determinant, relationship and association",
            "methodological defensibility, operationalisation, measurement validity, reproducibility, assumptions and limitations appropriate to the stated approach",
            "citation-reference correspondence, source traceability, unsupported empirical claims, author-year consistency and source quality",
            "a clear research contribution appropriate to a research Master's dissertation, without imposing doctoral originality",
        ]
        contribution = "Require a clear research contribution and critical scholarly judgement appropriate to MPhil work, but do not impose a PhD-level original contribution to knowledge."
        overlay = [
            "Test whether the argument moves beyond description to critical comparison, synthesis and defensible scholarly judgement.",
            "Require the study gap, framework, methods and contribution to form one coherent research logic.",
        ]
    elif key == "professional_doctorate":
        required = [
            "doctoral-level critical synthesis and authoritative positioning in both scholarship and the field of practice",
            "a complex and consequential professional, organisational, policy or practice problem supported by credible contextual evidence",
            "a defensible theoretical or conceptual lens that informs professional inquiry rather than being appended decoratively",
            "methodological robustness, practitioner reflexivity, ethics, stakeholder implications and limits of transferability",
            "integration of evidence, professional knowledge and alternative explanations",
            "a clearly articulated original contribution to professional practice, policy, organisational capability or applied knowledge",
            "credible pathways from findings to implementation, evaluation or professional change",
        ]
        contribution = "Require an original and defensible doctoral contribution to professional practice, policy or applied knowledge, supported by rigorous scholarship and evidence."
        overlay = [
            "Assess whether the work produces doctoral-level improvement, innovation or insight in practice rather than merely a managerial recommendation.",
            "Require critical reflexivity about the researcher's professional position, implementation context and stakeholder consequences where relevant.",
        ]
    else:  # PhD
        required = [
            "authoritative and critical command of the international and context-specific scholarly field",
            "a precise unresolved problem and gap whose significance to knowledge is demonstrated rather than asserted",
            "theoretical or conceptual advancement, challenge, integration or genuinely novel application",
            "methodological rigour, transparency, robustness, assumptions, sensitivity and reproducibility appropriate to the discipline",
            "engagement with rival explanations, contradictory evidence, boundary conditions and limitations",
            "complete cross-chapter alignment and a sustained argument leading to an original contribution to knowledge",
            "clear separation of what is confirmed, inferred, proposed and newly contributed by the thesis",
        ]
        contribution = "Require a substantial, original and defensible contribution to knowledge, with clear theoretical, empirical or methodological significance to the field."
        overlay = [
            "Interrogate every originality claim and require the thesis to specify exactly what is new, how it was established and why it matters to the discipline.",
            "Require doctoral robustness, engagement with alternatives and a contribution that extends beyond a new setting or sample.",
        ]

    chapter_checks = _chapter_review_checks(chapter) + overlay

    return {
        "degree_key": key,
        "orientation": DEGREE_LEVEL_PROFILES[key].get("orientation", key),
        "review_depth": depth,
        "per_section_issue_ceiling_not_quota": _degree_issue_limit(academic_level, depth),
        "independent_audit_material_finding_capacity": _degree_audit_max_findings(academic_level, depth),
        "mandatory_dimensions": common + required,
        "chapter_specific_mandatory_checks": chapter_checks,
        "contribution_standard": contribution,
        "coverage_rule": (
            "Explicitly assess every mandatory dimension relevant to the supplied chapter. A dimension may be marked adequate, but it must not be silently skipped. "
            "The finding capacity is not a quota: never invent a weakness, yet do not suppress distinct material defects merely to keep the report short."
        ),
    }

def _is_doctoral_level(academic_level: Any) -> bool:
    value = normalised(str(academic_level or ""))
    return (
        value == "phd"
        or "professional doctorate" in value
        or value.startswith("doctor of ")
        or value.startswith("doctoral")
    )


def _is_research_intensive_level(academic_level: Any) -> bool:
    value = normalised(str(academic_level or "")).replace("-", " ")
    if "non research master" in value:
        return False
    return (
        _is_doctoral_level(academic_level)
        or "research masters" in value
        or "research master" in value
        or "mphil" in value
    )


def _use_research_intensive_route(
    academic_level: Any, config: HybridAIConfig
) -> bool:
    return bool(
        _is_doctoral_level(academic_level)
        or (
            _is_research_masters_level(academic_level)
            and config.research_masters_deep_review
        )
    )


def _degree_primary_output_tokens(academic_level: Any, depth: str, config: HybridAIConfig) -> int:
    if depth == "light":
        return config.light_max_output_tokens
    if depth == "advanced":
        return config.advanced_max_output_tokens
    if not config.all_levels_degree_calibrated:
        return (
            config.research_masters_max_output_tokens
            if _is_research_masters_level(academic_level) and config.research_masters_deep_review
            else config.standard_max_output_tokens
        )
    key = _degree_key(academic_level)
    return {
        "bachelors": config.standard_max_output_tokens,
        "non_research_masters": config.non_research_masters_max_output_tokens,
        "research_masters": config.research_masters_max_output_tokens,
        "professional_doctorate": config.professional_doctorate_max_output_tokens,
        "phd": config.phd_max_output_tokens,
    }[key]


def _degree_audit_settings(academic_level: Any, depth: str, config: HybridAIConfig) -> Tuple[str, str, int, ReviewStage]:
    key = _degree_key(academic_level)
    research_stage = (
        ReviewStage.RESEARCH_INTENSIVE_AUDIT
        if _use_research_intensive_route(academic_level, config)
        else ReviewStage.FINAL_AUDIT
    )
    if depth == "advanced":
        return (
            config.openai_final_audit_model,
            config.openai_final_audit_reasoning_effort,
            max(config.advanced_audit_max_output_tokens, min(config.advanced_max_output_tokens, 8000)),
            research_stage,
        )
    if not config.all_levels_degree_calibrated:
        if depth == "light":
            return config.openai_chapter_model, "low", config.light_audit_max_output_tokens, research_stage
        if key == "research_masters" and config.research_masters_deep_review:
            return config.openai_expert_model, config.research_masters_audit_reasoning_effort, max(config.standard_audit_max_output_tokens, config.research_masters_audit_max_output_tokens), research_stage
        return config.openai_chapter_model, "medium", config.standard_audit_max_output_tokens, research_stage

    if depth == "light":
        settings = {
            "bachelors": (config.openai_chapter_model, "low", config.light_audit_max_output_tokens),
            "non_research_masters": (config.openai_chapter_model, "medium", max(config.light_audit_max_output_tokens, 3200)),
            "research_masters": (config.openai_expert_model, "medium", max(config.light_audit_max_output_tokens, 4200)),
            "professional_doctorate": (config.openai_expert_model, "high", max(config.light_audit_max_output_tokens, 5000)),
            "phd": (config.openai_expert_model, "high", max(config.light_audit_max_output_tokens, 5500)),
        }
    else:
        settings = {
            "bachelors": (config.openai_chapter_model, "medium", config.standard_audit_max_output_tokens),
            "non_research_masters": (config.openai_chapter_model, config.non_research_masters_audit_reasoning_effort, max(config.standard_audit_max_output_tokens, config.non_research_masters_audit_max_output_tokens)),
            "research_masters": (config.openai_expert_model, config.research_masters_audit_reasoning_effort, max(config.standard_audit_max_output_tokens, config.research_masters_audit_max_output_tokens)),
            "professional_doctorate": (config.openai_expert_model, config.professional_doctorate_audit_reasoning_effort, max(config.standard_audit_max_output_tokens, config.professional_doctorate_audit_max_output_tokens)),
            "phd": (config.openai_expert_model, config.phd_audit_reasoning_effort, max(config.standard_audit_max_output_tokens, config.phd_audit_max_output_tokens)),
        }
    model, effort, tokens = settings[key]
    return model, effort, tokens, research_stage


_EXPERT_SECTION_TERMS = (
    "problem statement", "statement of the problem", "research problem",
    "purpose of the study", "research objective", "research question",
    "hypothesis", "significance", "originality", "contribution",
    "literature review", "theoretical review", "theoretical framework",
    "conceptual review", "conceptual framework", "empirical review",
    "research gap", "research method", "methodology", "research approach",
    "research design", "population", "sampling", "sample size", "instrument",
    "measurement", "validity", "reliability", "trustworthiness",
    "data collection", "data analysis", "model specification", "diagnostic",
    "assumption", "result", "finding", "analysis", "regression", "anova",
    "correlation", "structural equation", "sem", "pls", "econometric",
    "discussion", "conclusion", "recommendation", "alignment", "coherence",
    "whole chapter", "cross chapter", "external examination",
)


def _section_requires_expert_model(
    section: Dict[str, Any], academic_level: Any
) -> bool:
    """Use GPT-5.4 for high-risk academic reasoning at research levels.

    Bachelor's and non-research master's chapter drafting remains on the faster
    GPT-5.4 mini model. Research master's and doctoral reviews escalate methods,
    results, discussion, contribution and cross-chapter synthesis to GPT-5.4.
    """
    if not _is_research_intensive_level(academic_level):
        return False
    # Doctoral work is high-stakes throughout, so every substantive section is
    # reviewed by GPT-5.4. Research master's work escalates the academically
    # decisive sections while routine descriptive material remains on the mini
    # model for speed.
    if _is_doctoral_level(academic_level):
        return True
    parts = [
        clean_text(section.get("heading", "")),
        " ".join(clean_text(value) for value in section.get("section_path") or []),
        " ".join(
            clean_text(paragraph.get("text", ""))[:1200]
            for paragraph in section.get("paragraphs") or []
        ),
    ]
    haystack = normalised(" ".join(parts))
    return any(term in haystack for term in _EXPERT_SECTION_TERMS)


def _batch_model_route(
    batch: Sequence[Dict[str, Any]],
    academic_level: Any,
    config: HybridAIConfig,
) -> Tuple[str, str]:
    if any(
        _section_requires_expert_model(section, academic_level)
        for section in batch
    ):
        return (
            config.openai_expert_model,
            config.openai_expert_reasoning_effort,
        )
    return (
        config.openai_chapter_model,
        config.openai_chapter_reasoning_effort,
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
    section_path = [clean_text(value) for value in paragraph.get("section_path") or [] if clean_text(value)]
    return {
        "id": _pid(paragraph),
        "text": clean_text(paragraph.get("text", "")),
        "heading": clean_text(paragraph.get("heading", "")),
        "section_path": section_path,
        "section_reference": section_path[-1] if section_path else clean_text(paragraph.get("heading", "")),
        "chapter_number": paragraph.get("chapter_number"),
        "page": paragraph.get("page"),
        "paragraph": paragraph.get("paragraph"),
        "is_heading": bool(paragraph.get("is_heading")),
        "source_filename": paragraph.get("source_filename", ""),
        "document_role": paragraph.get("document_role", "current"),
        "source_kind": paragraph.get("source_kind", "paragraph"),
        "table_index": paragraph.get("table_index"),
        "table_row": paragraph.get("table_row"),
        "table_number": clean_text(paragraph.get("table_number", "")),
        "table_title": clean_text(paragraph.get("table_title", "")),
        "table_caption": clean_text(paragraph.get("table_caption", "")),
    }


def _evidence(paragraph: Dict[str, Any]) -> Dict[str, Any]:
    value = _payload(paragraph)
    return {
        "text": value["text"][:1200], "page": value["page"], "paragraph": value["paragraph"],
        "page_paragraph": paragraph.get("page_paragraph"), "heading": value["heading"],
        "chapter_number": value["chapter_number"], "is_heading": value["is_heading"],
        "source_filename": value["source_filename"], "document_role": value["document_role"],
        "document_index": paragraph.get("document_index", 0), "paragraph_id": value["id"],
        "section_number": paragraph.get("section_number"),
        "section_path": value.get("section_path") or [],
        "section_reference": value.get("section_reference", ""),
        "source_kind": paragraph.get("source_kind", "paragraph"),
        "table_index": paragraph.get("table_index"),
        "table_row": paragraph.get("table_row"),
        "table_number": value.get("table_number", ""),
        "table_title": value.get("table_title", ""),
        "table_caption": value.get("table_caption", ""),
        "matched_terms": [], "adequacy_terms": [], "rank_score": 1,
    }


def _normalise_heading(value: str) -> str:
    low = normalised(value)
    low = re.sub(r"^\d+(?:\.\d+){0,3}\s+", "", low)
    return low or "Untitled section"


CHAPTER_MARKER_RE = re.compile(
    r"^chapter\s+(?:one|two|three|four|five|six|seven|eight|nine|ten|[1-9]|10)$",
    flags=re.I,
)

CHAPTER_TITLE_CONTAINERS = {
    "introduction",
    "literature review",
    "review of related literature",
    "research methods",
    "research methodology",
    "materials and methods",
    "results",
    "results and discussion",
    "findings and discussion",
    "summary conclusion and recommendations",
    "summary conclusions and recommendations",
    "summary conclusion recommendations",
    "questionnaire",
    "interview guide",
    "survey instrument",
}


def _section_group_metadata(group: Dict[str, Any]) -> Dict[str, Any]:
    rows = list(group.get("paragraphs") or [])
    first = rows[0] if rows else {}
    chapter_number = next(
        (row.get("chapter_number") for row in rows if isinstance(row.get("chapter_number"), int)),
        None,
    )
    section_path = next(
        ([clean_text(value) for value in row.get("section_path") or [] if clean_text(value)]
         for row in rows if row.get("section_path")),
        [],
    )
    substantive = [row for row in rows if not row.get("is_heading") and clean_text(row.get("text", ""))]
    return {
        "chapter_number": chapter_number,
        "section_path": section_path,
        "heading_only": not substantive,
        "first_is_heading": bool(first.get("is_heading")),
    }


def _is_structural_container_group(
    group: Dict[str, Any],
    next_group: Optional[Dict[str, Any]] = None,
) -> bool:
    """Return True for bare chapter markers and chapter-title containers.

    The institutional chapter structure is a chapter-level guide. A bare
    ``CHAPTER THREE`` or ``RESEARCH METHODS`` heading must never be reviewed as
    though it should contain the complete methodology. The substantive
    Introduction and later subsections are reviewed instead.
    """
    meta = _section_group_metadata(group)
    if not meta["heading_only"] or not meta["first_is_heading"]:
        return False
    heading = clean_text(group.get("heading", ""))
    low = normalised(heading)
    if CHAPTER_MARKER_RE.fullmatch(heading):
        return True
    if next_group is None:
        return False
    next_meta = _section_group_metadata(next_group)
    next_path = [normalised(value) for value in next_meta.get("section_path") or []]

    # Any heading-only parent whose exact heading is retained in the next
    # section path is an organisational container, not a missing-content
    # section. This covers headings such as "Reliability and Validity" and
    # objective labels above their substantive analysis subsections.
    if low and low in next_path[:-1]:
        return True
    if low not in CHAPTER_TITLE_CONTAINERS:
        return False

    # Canonical chapter or instrument titles are structural when followed by
    # another unit in the same chapter/back-matter block. This retains genuine
    # Introduction subsections that contain prose.
    return meta.get("chapter_number") == next_meta.get("chapter_number")


def _section_groups(paragraphs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    raw_groups: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    for paragraph in paragraphs:
        text = clean_text(paragraph.get("text", ""))
        if not text:
            continue
        if current is None or paragraph.get("is_heading"):
            heading = text if paragraph.get("is_heading") else (paragraph.get("heading") or "Opening material")
            current = {"heading": heading, "paragraphs": []}
            raw_groups.append(current)
        current["paragraphs"].append(paragraph)

    groups: List[Dict[str, Any]] = []
    for index, group in enumerate(raw_groups):
        next_group = raw_groups[index + 1] if index + 1 < len(raw_groups) else None
        if _is_structural_container_group(group, next_group):
            continue
        group.update(_section_group_metadata(group))
        groups.append(group)
    return groups


def _split_group(group: Dict[str, Any], max_chars: int) -> List[Dict[str, Any]]:
    paragraphs = group["paragraphs"]
    chunks: List[Dict[str, Any]] = []
    current: List[Dict[str, Any]] = []
    total = 0
    part = 1
    metadata = {
        "chapter_number": group.get("chapter_number"),
        "section_path": list(group.get("section_path") or []),
    }
    for paragraph in paragraphs:
        size = len(clean_text(paragraph.get("text", ""))) + 120
        if current and total + size > max_chars:
            chunks.append({"heading": group["heading"], "part": part, "paragraphs": current, **metadata})
            part += 1
            current = current[-1:]
            total = sum(len(clean_text(p.get("text", ""))) + 120 for p in current)
        current.append(paragraph)
        total += size
    if current:
        chunks.append({"heading": group["heading"], "part": part, "paragraphs": current, **metadata})
    return chunks


def _guide_expectations(review: Dict[str, Any], heading: str) -> List[str]:
    """Return broad internal academic expectations without exposing checklist wording."""
    return guide_for_heading(heading, limit=10)


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


def _selected_audit_paragraphs(paragraphs: Sequence[Dict[str, Any]], limit_chars: int) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    total = 0
    for index, paragraph in enumerate(paragraphs):
        combined = normalised((paragraph.get("heading") or "") + " " + (paragraph.get("text") or ""))
        include = index < 4 or bool(paragraph.get("is_heading")) or any(term in combined for term in KEY_ALIGNMENT_TERMS)
        if not include:
            continue
        size = len(clean_text(paragraph.get("text", ""))) + 120
        if selected and total + size > limit_chars:
            break
        selected.append(paragraph)
        total += size
    return selected


def _batch(values: Sequence[Any], size: int) -> List[List[Any]]:
    return [list(values[i:i + max(1, size)]) for i in range(0, len(values), max(1, size))]


def _chapter_review_packets(
    sections: Sequence[Dict[str, Any]],
    max_chars: int,
) -> List[List[Dict[str, Any]]]:
    """Build stable chapter-level review packets.

    A chapter is reviewed in one request whenever it fits the configured context
    budget. Long chapters are split only at section boundaries. Synthetic
    cross-chapter audit units remain separate. This reduces API round trips and
    prevents a later recovery pass from repeatedly rediscovering the same
    chapter structure.
    """
    packets: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []
    current_key: Any = object()
    current_chars = 0

    def section_chars(section: Dict[str, Any]) -> int:
        return sum(
            len(clean_text(paragraph.get("text", ""))) + 120
            for paragraph in section.get("paragraphs") or []
        ) + 900

    def packet_key(section: Dict[str, Any]) -> Tuple[str, Any]:
        if section.get("alignment_audit") or section.get("revision_audit"):
            return ("synthetic", section.get("section_key"))
        chapter = section.get("chapter_number")
        if isinstance(chapter, int):
            return ("chapter", chapter)
        path = tuple(normalised(value) for value in section.get("section_path") or [])
        return ("back_matter", path[0] if path else "unassigned")

    for section in sections:
        key = packet_key(section)
        size = section_chars(section)
        must_flush = bool(
            current
            and (key != current_key or current_chars + size > max_chars)
        )
        if must_flush:
            packets.append(current)
            current = []
            current_chars = 0
        if not current:
            current_key = key
        current.append(section)
        current_chars += size
    if current:
        packets.append(current)
    return packets


def _section_key(section: Dict[str, Any], index: int) -> str:
    """Return a short, stable identifier that models can reproduce exactly.

    The earlier key embedded the full heading. Long thesis titles were sometimes
    shortened, capitalised differently, or paraphrased by the model, causing a
    valid title review to be rejected as an omitted section.
    """
    return f"S{index + 1:03d}P{int(section.get('part') or 1):02d}"


def _batch_prompt(
    review: Dict[str, Any],
    batch: Sequence[Dict[str, Any]],
    supervisor_comments: Sequence[Dict[str, Any]],
    context_lock: Dict[str, Any],
    depth: str = "standard",
) -> str:
    summary = review.get("summary") or {}
    profile = _review_profile(depth)
    benchmark = _combined_benchmark(summary.get("academic_level"), depth)
    degree_contract = _degree_specific_review_contract(
        summary.get("academic_level"), summary.get("selected_chapter"), depth
    )
    sections = []
    for section in batch:
        sections.append({
            "section_key": section["section_key"],
            "heading": clean_text(section.get("heading", "Untitled section")),
            "chapter_number": section.get("chapter_number"),
            "section_path": list(section.get("section_path") or []),
            "part": section.get("part", 1),
            "cross_chapter_audit": bool(section.get("alignment_audit")),
            "revision_audit": bool(section.get("revision_audit")),
            "internal_academic_guide_adapt_to_relevance_do_not_name_or_number": _guide_expectations(review, section.get("heading", "")),
            "paragraphs": [_payload(p) for p in section.get("paragraphs") or []],
            "extra_context": section.get("extra_context") or {},
        })
    doctoral_structure = bool(
        summary.get("thesis_structure_mode")
        == "flexible_doctoral"
        or _is_doctoral_level(summary.get("academic_level"))
    )

    if doctoral_structure:
        structure_contract = {
            "structure_mode": "flexible_doctoral",
            "fixed_five_chapter_sequence_required": False,
            "custom_chapter_numbers_order_and_titles_allowed": True,
            "acceptable_architectures": [
                "monograph",
                "article-based thesis",
                "essay-based thesis",
                "portfolio or practice-based thesis",
                "discipline-specific doctoral structure",
            ],
            "required_research_functions": [
                "research problem, purpose, objectives and questions",
                "literature, theory and scholarly positioning",
                "methodology and research design",
                "evidence, analysis, results or findings",
                "discussion, synthesis and interpretation",
                "conclusions, original contribution and implications",
            ],
            "review_requirement": (
                "Assess functional completeness, scholarly logic, integration "
                "and contribution across the actual submitted architecture. "
                "Do not criticise the thesis merely for departing from a "
                "five-chapter sequence."
            ),
        }
        complete_structure_instruction = (
            "For this Professional Doctorate or PhD thesis, accept the actual "
            "chapter architecture and titles. Review every chapter and section "
            "as submitted, then test whether the core research functions are "
            "complete, logically ordered, mutually consistent and integrated "
            "into a defensible doctoral contribution. "
        )
    else:
        structure_contract = {
            "structure_mode": "standard_five_chapter",
            "fixed_five_chapter_sequence_required": True,
            "default_complete_thesis_structure": [
                "Chapter One: Introduction",
                "Chapter Two: Literature Review",
                "Chapter Three: Research Methods",
                "Chapter Four: Results and Discussion",
                "Chapter Five: Summary, Conclusions and Recommendations",
            ],
            "discipline_specific_additional_chapters_are_allowed": True,
            "additional_chapters_must_align_with_the_problem_objectives_methods_results_and_conclusions": True,
        }
        complete_structure_instruction = (
            "For a complete non-doctoral thesis, examine all standard research "
            "chapters and any approved additional chapters. "
        )

    packet = {
        "review_context": {
            "current_date_utc": datetime.now(timezone.utc).date().isoformat(),
            "declared_academic_level": summary.get("academic_level"),
            "research_approach": summary.get("research_approach"),
            "document_label": summary.get("document_label"),
            "chapter_under_review": summary.get("selected_chapter"),
            "review_stage": summary.get("submission_stage"),
            "review_depth": depth,
            "review_scope": summary.get("review_scope"),
            "combined_chapters": summary.get("combined_chapters", []),
            "reviewed_chapter_range": summary.get("reviewed_chapter_range"),
            "uploaded_chapters_detected": summary.get("uploaded_chapters_detected", []),
            "reviewed_chapters": summary.get("current_chapters_detected", []),
            "selected_chapter_isolated_from_composite": summary.get(
                "reviewed_only_selected_chapter", False
            ),
            "complete_thesis_structure_validated": summary.get(
                "complete_thesis_structure_validated", False
            ),
            "optional_chapters_detected": summary.get(
                "optional_chapters_detected", []
            ),
            "review_level_label": profile["label"],
            "declared_degree_label": benchmark["degree_label"],
            "review_benchmark": benchmark["degree_standard"],
            "depth_expectation": benchmark["review_intensity_expectation"],
            "review_intensity": benchmark["review_intensity"],
            "degree_specific_review_contract": degree_contract,
        },
        "study_context_lock": {
            key: value for key, value in context_lock.items()
            if key != "source_text_normalised"
        },
        "document_manifest_for_factual_checks": summary.get("supervisory_document_manifest") or {},
        "chapter_review_dimensions": _chapter_dimensions(review),
        "coverage_contract": {
            "review_every_section_and_subsection": True,
            "return_exactly_one_review_for_each_section_key": True,
            "section_assessment_required_even_when_no_issue_is_found": True,
            "strengths_should_be_reported_where_deserved": True,
            "normal_issue_limit_per_section": _degree_issue_limit(
                summary.get("academic_level"), depth
            ),
            "independent_audit_material_finding_capacity": _degree_audit_max_findings(
                summary.get("academic_level"), depth
            ),
            "degree_standard_must_not_change_with_depth": True,
            "degree_specific_dimensions_must_be_explicitly_assessed": True,
        },
        "accuracy_contract": {
            "do_not_introduce_external_countries_or_locations": True,
            "do_not_invent_citations_statistics_or_organisations": True,
            "use_placeholders_for_unknown_context": False,
            "omit_illustrative_guidance_when_verified_details_are_unavailable": True,
            "distinguish_missing_from_weak_content": True,
            "make_method_advice_conditional_when_design_is_unknown": True,
            "do_not_review_context_only_chapters_as_the_selected_chapter": True,
            "when_combined_chapters_are_selected_review_every_chapter_in_the_range": True,
            "verify_alignment_sequentially_from_chapter_one_to_the_last_selected_chapter": True,
            "verify_objective_question_hypothesis_method_result_conclusion_alignment": True,
            "verify_model_specific_diagnostics_in_methods_and_results": True,
            "verify_statistical_values_against_tables_and_interpretations": True,
            "treat_local_statistical_flags_as_items_to_verify_not_automatic_conclusions": True,
            "every_issue_must_use_evidence_from_its_own_section": True,
            "every_issue_must_name_the_exact_section_or_subsection_heading": True,
            "table_findings_must_name_the_supplied_table_number_and_title": True,
            "generic_or_portable_comments_are_not_allowed": True,
            "absence_claims_must_be_checked_against_the_document_manifest": True,
            "synthetic_audit_labels_are_not_document_locations": True,
            "whole_thesis_instructions_require_whole_thesis_evidence": True,
            "chapter_structure_is_a_whole_chapter_guide_not_a_heading_requirement": True,
            "chapter_introduction_outlines_purpose_and_contents": True,
            "bare_chapter_headings_and_titles_are_not_substantive_sections": True,
            "analysis_claims_require_direct_statistical_or_table_evidence": True,
            "factual_accuracy_threshold_is_identical_for_all_depths": True,
        },
        "statistical_review_audit": review.get("statistical_review") or {},
        "institutional_structure_contract": {
            **structure_contract,
            "the_guideline_strengthens_but_does_not_replace_the_existing_academic_review": True,
        },
        "instruction": (
            "Review every supplied section and subsection at the stated benchmark. Return exactly one review for every section_key. "
            "Use the internal academic guide flexibly rather than mechanically. Do not omit short or apparently adequate sections. "
            "A section may have zero issues only after a substantive assessment. "
            "When one chapter is selected from a composite document, review only the supplied current sections and use the other chapters solely for alignment. "
            + complete_structure_instruction
            + "For Chapters Three and Four, determine which diagnostics are required by the actual statistical model, verify their presence and interpretation, and check numerical and inferential consistency across text, tables and figures. "
            "Treat deterministic statistical warnings as evidence requiring verification rather than as automatic proof of error. "
            "Give examples only from the confirmed study context. When a verified contextual detail, source or statistic is unavailable, omit the example and give a direct verification instruction without any placeholder token. "
            "Treat the institutional structure only as a whole-chapter coverage guide. Do not ask a bare chapter heading or chapter title to contain the chapter's methods, results or conclusions. The chapter Introduction should outline the chapter purpose and contents. "
            "Every issue must be directly relevant to the cited passage, use the exact section or subsection heading, and, when applicable, name the supplied table number and title. "
            "Apply the degree_specific_review_contract operationally. Do not stop after proofreading and broad structural comments. For each material issue, write enough detail to explain the defect, its academic consequence and the exact revision action. For Research Master’s/MPhil and doctoral work, assess theoretical and conceptual grounding, problem-gap evidence, construct roles, one-to-one alignment, design-language compatibility, source traceability and contribution wherever relevant."
        ),
        "sections": sections,
    }
    return json.dumps(packet, ensure_ascii=False)


def _focused_section_recovery_prompt(
    review: Dict[str, Any],
    section: Dict[str, Any],
    context_lock: Dict[str, Any],
    depth: str,
) -> str:
    summary = review.get("summary") or {}
    packet = {
        "review_context": {
            "current_date_utc": datetime.now(timezone.utc).date().isoformat(),
            "declared_academic_level": summary.get("academic_level"),
            "research_approach": summary.get("research_approach"),
            "review_depth": depth,
            "review_scope": summary.get("review_scope"),
            "degree_specific_review_contract": _degree_specific_review_contract(
                summary.get("academic_level"), summary.get("selected_chapter"), depth
            ),
        },
        "study_context_lock": {
            key: value for key, value in context_lock.items()
            if key != "source_text_normalised"
        },
        "document_manifest_for_factual_checks": (
            summary.get("supervisory_document_manifest") or {}
        ),
        "section": {
            "section_key": section["section_key"],
            "heading": clean_text(section.get("heading", "Untitled section")),
            "chapter_number": section.get("chapter_number"),
            "section_path": list(section.get("section_path") or []),
            "part": section.get("part", 1),
            "paragraphs": [
                _payload(paragraph)
                for paragraph in section.get("paragraphs") or []
            ],
            "internal_academic_guide_adapt_to_relevance_do_not_name_or_number": (
                _guide_expectations(review, section.get("heading", ""))
            ),
        },
        "instruction": (
            "Return exactly one compact but substantive review for the supplied "
            "section_key. The section exists. Assess its quality, identify only "
            "supported strengths and issues, and preserve the section_key exactly."
        ),
    }
    return json.dumps(packet, ensure_ascii=False)


def _unresolved_section_fallback(
    section: Dict[str, Any],
    reason: str = "",
) -> Dict[str, Any]:
    heading = clean_text(section.get("heading", "Untitled section"))
    # Student-facing exports must never expose provider, retry, recovery or
    # manual-confirmation status. When a focused section response is unavailable,
    # keep the section represented with a neutral expert-review requirement and
    # allow deterministic cross-section checks to supply any supported issues.
    return {
        "section_key": section["section_key"],
        "heading": heading,
        "chapter_number": section.get("chapter_number"),
        "section_path": list(section.get("section_path") or []),
        "part": section.get("part", 1),
        "paragraph_count": len(section.get("paragraphs") or []),
        "section_score": 50.0,
        # Keep unavailable model responses out of student-facing comments. The
        # exporter will use its own section-specific template if a coverage note
        # is needed, and deterministic checklist findings will add exact issues.
        "section_assessment": "",
        "coverage_warning": "",
        "strengths": [],
        "issues": [],
        "source_section": section,
    }


def _verification_prompt(
    review: Dict[str, Any],
    batch: Sequence[Dict[str, Any]],
    depth: str,
    context_lock: Dict[str, Any],
) -> str:
    summary = review.get("summary") or {}
    profile = _review_profile(depth)
    benchmark = _combined_benchmark(summary.get("academic_level"), depth)
    degree_contract = _degree_specific_review_contract(
        summary.get("academic_level"), summary.get("selected_chapter"), depth
    )
    proposals = []
    paragraphs: Dict[str, Dict[str, Any]] = {}
    for section_review in batch:
        proposals.append({
            "section_key": section_review["section_key"],
            "section_name": section_review["heading"],
            "section_score": section_review["section_score"],
            "section_assessment": section_review["section_assessment"],
            "issues": section_review["issues"],
        })
        for paragraph in section_review["source_section"].get("paragraphs") or []:
            paragraphs[_pid(paragraph)] = _payload(paragraph)
    packet = {
        "review_context": {
            "current_date_utc": datetime.now(timezone.utc).date().isoformat(),
            "declared_academic_level": summary.get("academic_level"),
            "research_approach": summary.get("research_approach"),
            "review_depth": depth,
            "declared_degree_label": benchmark["degree_label"],
            "review_benchmark": benchmark["degree_standard"],
            "depth_expectation": benchmark["review_intensity_expectation"],
            "degree_specific_review_contract": degree_contract,
        },
        "study_context_lock": {
            key: value for key, value in context_lock.items()
            if key != "source_text_normalised"
        },
        "document_manifest_for_factual_checks": summary.get("supervisory_document_manifest") or {},
        "source_paragraphs": list(paragraphs.values()),
        "proposed_reviews": proposals,
        "instruction": (
            "Independently verify the proposed issues at the stated benchmark. Remove unsupported, repetitive or misplaced findings; "
            "correct severity and evidence; add important missed issues; and confirm that all sections received a substantive assessment. "
            "Reject any example, citation, statistic, country, location, organisation, population or design assumption not found in the source. "
            "Apply the declared degree standard to originality, theoretical contribution, methodological defensibility, "
            "robustness, alternative explanations and contribution. Advanced Review increases scrutiny but not the degree level. "
            "Use the degree_specific_review_contract as a mandatory coverage map. Independently test every relevant dimension at the declared level and add material missed issues even when the primary review did not propose them. Keep the issue ordering by academic level and review depth, so a Standard Research Master’s/MPhil review should normally retain more material, research-intensive findings than a Standard Non-Research Master’s review of the same weak chapter. In Chapter One this includes problem-gap evidence, "
            "critical background synthesis, construct roles, title-purpose-objective-question alignment, causal-language compatibility, prospective significance, "
            "definition quality, citation-reference correspondence, uncited empirical claims and source traceability. "
            "Reject generic comments, misplaced evidence, incorrect section headings and incorrect or missing table references. "
            "Do not invent issues to reach a number, but do not compress distinct material defects into a single vague comment."
        ),
    }
    return json.dumps(packet, ensure_ascii=False)


def _compact_quality_audit_prompt(
    review: Dict[str, Any],
    section_reviews: Sequence[Dict[str, Any]],
    context_lock: Dict[str, Any],
    paragraph_index: Dict[str, Dict[str, Any]],
    audit_paragraphs: Sequence[Dict[str, Any]],
    max_findings: int,
    max_source_chars: int,
    depth: str,
) -> str:
    """Build one compact evidence audit instead of re-reviewing every batch."""
    summary = review.get("summary") or {}
    benchmark = _combined_benchmark(summary.get("academic_level"), depth)

    all_issues = [
        issue
        for section_review in section_reviews
        for issue in section_review.get("issues") or []
    ]
    all_issues.sort(
        key=lambda item: (
            SEVERITY_ORDER.get(item.get("severity", "minor"), 9),
            0 if any(
                paragraph_index.get(pid, {}).get("source_kind") == "table_row"
                for pid in item.get("evidence_paragraph_ids") or []
            ) else 1,
            0 if item.get("source_verification_required") else 1,
            float(item.get("confidence") or 0.0),
        )
    )
    selected_issues = all_issues[:max(1, max_findings)]
    selected_ids = {
        pid
        for issue in selected_issues
        for pid in issue.get("evidence_paragraph_ids") or []
        if pid in paragraph_index
    }

    source_rows: List[Dict[str, Any]] = []
    seen_ids = set()
    total_chars = 0

    def add_paragraph(paragraph: Dict[str, Any]) -> None:
        nonlocal total_chars
        pid = _pid(paragraph)
        if pid in seen_ids:
            return
        payload = _payload(paragraph)
        size = len(payload.get("text", "")) + 120
        if source_rows and total_chars + size > max_source_chars:
            return
        source_rows.append(payload)
        seen_ids.add(pid)
        total_chars += size

    for pid in selected_ids:
        paragraph = paragraph_index.get(pid)
        if paragraph:
            add_paragraph(paragraph)

    for paragraph in audit_paragraphs:
        add_paragraph(paragraph)

    selected_findings_by_section: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for issue in selected_issues:
        selected_findings_by_section[normalised(issue.get("section", ""))].append(issue)

    proposals = []
    for section_review in section_reviews:
        proposals.append({
            "section_key": section_review["section_key"],
            "section_name": section_review["heading"],
            "section_score": section_review["section_score"],
            "section_assessment": section_review["section_assessment"],
            "priority_issues": selected_findings_by_section.get(
                normalised(section_review["heading"]), []
            ),
        })

    packet = {
        "review_context": {
            "current_date_utc": datetime.now(timezone.utc).date().isoformat(),
            "declared_academic_level": summary.get("academic_level"),
            "research_approach": summary.get("research_approach"),
            "review_depth": depth,
            "declared_degree_label": benchmark["degree_label"],
            "review_benchmark": benchmark["degree_standard"],
            "review_intensity": benchmark["review_intensity"],
            "degree_specific_review_contract": _degree_specific_review_contract(
                summary.get("academic_level"), summary.get("selected_chapter"), depth
            ),
        },
        "study_context_lock": {
            key: value for key, value in context_lock.items()
            if key != "source_text_normalised"
        },
        "section_assessments": proposals,
        "focused_source_paragraphs": source_rows,
        "instruction": (
            "Conduct one compact evidence-grounded quality audit at the declared degree standard. "
            "Verify the supplied priority findings, remove unsupported, generic, misplaced or repetitive findings, "
            "correct severity and evidence, and add only genuinely material issues missed by the primary review. "
            "Confirm the exact section or subsection heading for every finding. For table findings, confirm the supplied "
            "table number, title and relevant row. Do not re-review every minor wording point. Use only the confirmed study context."
        ),
    }
    return json.dumps(packet, ensure_ascii=False)


def _valid_issue(
    issue: Dict[str, Any],
    paragraph_index: Dict[str, Dict[str, Any]],
    context_lock: Dict[str, Any],
    *,
    allowed_ids: Optional[set[str]] = None,
    canonical_section: str = "",
) -> Optional[Dict[str, Any]]:
    try:
        parsed = AcademicIssue.model_validate(issue).model_dump()
    except Exception:
        return None
    parsed = sanitise_issue(parsed, context_lock)
    evidence_ids = [
        pid for pid in parsed["evidence_paragraph_ids"]
        if pid in paragraph_index and (allowed_ids is None or pid in allowed_ids)
    ]
    parsed["evidence_paragraph_ids"] = list(dict.fromkeys(evidence_ids))[:8]

    # Unsupported comments are the main source of irrelevant annotations. Every
    # academic finding must be anchored in the supplied section, including a
    # claim that required content is absent or underdeveloped.
    if not parsed["evidence_paragraph_ids"]:
        return None

    first = paragraph_index[parsed["evidence_paragraph_ids"][0]]
    evidence_section = source_section(first)
    evidence_sections = {
        normalised(source_section(paragraph_index[pid]))
        for pid in parsed["evidence_paragraph_ids"]
        if pid in paragraph_index and source_section(paragraph_index[pid])
    }
    requested_section = clean_text(parsed.get("section", ""))
    # Synthetic audit packets are not real document locations. Re-anchor their
    # findings to the exact section or subsection that supplied the evidence.
    if canonical_section and not is_synthetic_section(canonical_section):
        parsed["section"] = clean_text(canonical_section)
    elif (
        requested_section
        and not is_synthetic_section(requested_section)
        and normalised(requested_section) in evidence_sections
    ):
        parsed["section"] = requested_section
    elif evidence_section:
        parsed["section"] = evidence_section

    quote = clean_text(parsed.get("problematic_quote", ""))
    if quote and not any(
        quote in clean_text(paragraph_index[pid].get("text", ""))
        for pid in parsed["evidence_paragraph_ids"]
    ):
        parsed["problematic_quote"] = ""
        parsed["confidence"] = min(float(parsed["confidence"]), 0.72)

    combined = normalised(
        " ".join([
            parsed.get("issue_title", ""),
            parsed.get("assessment", ""),
            parsed.get("required_action", ""),
        ])
    )
    generic_phrases = {
        "revise this section",
        "improve the clarity",
        "provide more detail",
        "strengthen this section",
        "improve academic writing",
        "review this section",
    }
    if any(combined == phrase or combined.endswith(phrase) for phrase in generic_phrases):
        return None

    return parsed


def _issue_signature(issue: Dict[str, Any]) -> str:
    base = "|".join([normalised(issue.get("category", "")), normalised(issue.get("section", "")), normalised(issue.get("problematic_quote", ""))[:180], normalised(issue.get("issue_title", ""))])
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _deduplicate_issues(issues: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    output: Dict[str, Dict[str, Any]] = {}
    for issue in issues:
        key = _issue_signature(issue)
        existing = output.get(key)
        if not existing or SEVERITY_ORDER.get(issue.get("severity", "minor"), 9) < SEVERITY_ORDER.get(existing.get("severity", "minor"), 9):
            output[key] = issue
    return sorted(output.values(), key=lambda x: (SEVERITY_ORDER.get(x.get("severity", "minor"), 9), normalised(x.get("section", "")), normalised(x.get("issue_title", ""))))


def _consolidate_repetitive_issues(issues: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge repetitive language, citation and terminology comments within a section."""
    merge_categories = {"academic_writing", "citations_and_sources", "conceptual_clarity"}
    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    untouched: List[Dict[str, Any]] = []
    for issue in issues:
        category = str(issue.get("category") or "other")
        if category in merge_categories:
            grouped[(normalised(issue.get("section", "")), category)].append(issue)
        else:
            untouched.append(issue)

    merged: List[Dict[str, Any]] = list(untouched)
    for (_, category), values in grouped.items():
        values = sorted(values, key=lambda item: (SEVERITY_ORDER.get(item.get("severity", "minor"), 9), -float(item.get("confidence") or 0)))
        primary = dict(values[0])
        evidence: List[str] = []
        for value in values:
            evidence.extend(value.get("evidence_paragraph_ids") or [])
        primary["evidence_paragraph_ids"] = list(dict.fromkeys(evidence))[:6]
        if len(values) > 1:
            if category == "academic_writing":
                primary["issue_title"] = "Recurring academic writing and language problems"
                primary["required_action"] = (
                    "Undertake a systematic line-by-line language edit of this section, correcting the recurring patterns identified in the marked examples rather than treating each sentence as an isolated error."
                )
                primary["guidance_type"] = "language_pattern"
            elif category == "citations_and_sources":
                primary["issue_title"] = "Source attribution and verification require systematic correction"
                primary["required_action"] = (
                    "Verify each marked claim or citation against the original source, remove unsupported details, and ensure every retained in-text citation has a complete and accurate reference-list entry."
                )
                primary["source_verification_required"] = True
                primary["guidance_type"] = "source_verification"
            elif category == "conceptual_clarity":
                primary["issue_title"] = "Key terminology is used inconsistently"
        merged.append(primary)
    return sorted(merged, key=lambda x: (SEVERITY_ORDER.get(x.get("severity", "minor"), 9), normalised(x.get("section", "")), normalised(x.get("issue_title", ""))))


def _finding_row(issue: Dict[str, Any], paragraph_index: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    severity = issue.get("severity", "moderate")
    status, label = ACTIONABLE_STATUS[severity]
    evidence = [
        _evidence(paragraph_index[pid])
        for pid in issue.get("evidence_paragraph_ids", [])
        if pid in paragraph_index
    ]
    target_section = normalised(issue.get("section", ""))
    evidence.sort(
        key=lambda item: (
            0 if normalised(item.get("section_reference", "")) == target_section else 1,
            0 if item.get("problematic_quote") else 1,
            int(item.get("paragraph") or 0),
        )
    )
    assessment = clean_text(issue.get("assessment", ""))
    consequence = clean_text(issue.get("academic_consequence", ""))
    comment = assessment + (f" Academic implication: {consequence}" if consequence else "")
    section = clean_text(issue.get("section", "")) or "Chapter-wide review"

    table_evidence = None if issue.get("suppress_table_reference") else next(
        (item for item in evidence if item.get("table_number")),
        None,
    )
    table_reference = ""
    number = clean_text(issue.get("canonical_table_number", ""))
    title = clean_text(issue.get("canonical_table_title", ""))
    if not number and table_evidence:
        number = clean_text(table_evidence.get("table_number", ""))
        title = clean_text(table_evidence.get("table_title", ""))
    if number:
        table_reference = f"Table {number}"
        if title:
            table_reference += f": {title}"

    section_path = []
    for item in evidence:
        path = [clean_text(value) for value in item.get("section_path") or [] if clean_text(value)]
        if path:
            section_path = path
            break

    chapter_number = next(
        (item.get("chapter_number") for item in evidence if item.get("chapter_number") is not None),
        None,
    )

    reference_label = section
    if table_reference:
        reference_label = f"{section}, {table_reference}"

    return {
        "review_type": "academic_finding",
        "finding_id": issue.get("finding_id", ""),
        "category": issue.get("category", "other"),
        "section": section,
        "section_reference": section,
        "section_path": section_path,
        "chapter_number": chapter_number,
        "table_reference": table_reference,
        "reference_label": reference_label,
        "item": clean_text(issue.get("issue_title", "Academic issue")),
        "status": status,
        "status_label": label,
        "severity": severity,
        "confidence": round(float(issue.get("confidence") or 0), 2),
        "evidence": evidence,
        "comment": comment,
        "required_action": clean_text(issue.get("required_action", "")),
        "illustrative_guidance": clean_text(issue.get("illustrative_guidance", "")),
        "guidance_type": issue.get("guidance_type", "direct_correction"),
        "source_verification_required": bool(issue.get("source_verification_required")),
        "context_guard_adjusted": bool(issue.get("context_guard_adjusted")),
        "problematic_quote": clean_text(issue.get("problematic_quote", "")),
        "headings": [section],
        "annotation_eligible": bool(evidence),
        "verification_status": issue.get("verification_status", "deterministic_or_primary"),
        "manual_confirmation_required": bool(issue.get("manual_confirmation_required")),
    }



def _limit_light_issues(issues: Sequence[Dict[str, Any]], max_findings: int) -> List[Dict[str, Any]]:
    """Keep a light review concise and non-forensic."""
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for raw in issues:
        issue = dict(raw)
        if issue.get("severity") == "critical":
            issue["severity"] = "major"
        grouped[normalised(issue.get("section", "Chapter-wide review"))].append(issue)

    selected: List[Dict[str, Any]] = []
    for values in grouped.values():
        values.sort(key=lambda item: (SEVERITY_ORDER.get(item.get("severity", "minor"), 9), -float(item.get("confidence") or 0)))
        selected.extend(values[:2])
    selected.sort(key=lambda item: (SEVERITY_ORDER.get(item.get("severity", "minor"), 9), -float(item.get("confidence") or 0)))
    return selected[:max(1, max_findings)]


def _light_readiness(
    score: float,
    issues: Sequence[Dict[str, Any]],
    academic_level: Any = "",
) -> Tuple[str, str]:
    critical = sum(1 for issue in issues if issue.get("severity") == "critical")
    major = sum(1 for issue in issues if issue.get("severity") == "major")
    moderate = sum(1 for issue in issues if issue.get("severity") == "moderate")
    if critical or major >= 3 or score < 60:
        label = "Material revision required"
    elif major or moderate:
        label = "Targeted revision required"
    else:
        label = "Meets the declared degree standard with minor refinement"
    degree = _degree_profile(academic_level)
    meaning = (
        f"Every detected section and subsection was reviewed concisely against the standard expected of a {degree['label']}. "
        "The review reports the most material issues while preserving the academic benchmark of the declared programme."
    )
    return label, meaning



def _usage_cost(usage: AIUsageRecord, config: HybridAIConfig) -> AIUsageRecord:
    uncached = max(0, usage.input_tokens - usage.cached_input_tokens)
    if usage.estimated_cost_usd > 0:
        return usage
    p_in, p_cache, p_out = config.prices_for_model(
        usage.provider, usage.model
    )

    cost = (
        uncached / 1_000_000 * p_in
        + usage.cached_input_tokens / 1_000_000 * p_cache
        + usage.output_tokens / 1_000_000 * p_out
    )
    return usage.model_copy(
        update={"estimated_cost_usd": round(cost, 6)}
    )


async def _run_limited(coroutines: Sequence[Any], limit: int) -> List[Any]:
    semaphore = asyncio.Semaphore(max(1, limit))
    async def runner(coro):
        async with semaphore:
            return await coro
    return await asyncio.gather(*(runner(coro) for coro in coroutines), return_exceptions=True)


async def _notify(callback: Any, progress: int, message: str) -> None:
    if callback is None:
        return
    result = callback(progress, message)
    if inspect.isawaitable(result):
        await result


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
            "severity": value.get("severity", source.get("severity")), "confidence": value.get("confidence", source.get("confidence")),
            "evidence_paragraph_ids": value.get("evidence_paragraph_ids", source.get("evidence_paragraph_ids")),
            "problematic_quote": value.get("problematic_quote", source.get("problematic_quote")),
            "assessment": value.get("assessment", source.get("assessment")),
            "academic_consequence": value.get("academic_consequence", source.get("academic_consequence")),
            "required_action": value.get("required_action", source.get("required_action")),
            "illustrative_guidance": value.get("illustrative_guidance", source.get("illustrative_guidance", "")),
            "guidance_type": value.get("guidance_type", source.get("guidance_type", "direct_correction")),
            "source_verification_required": value.get("source_verification_required", source.get("source_verification_required", False)),
            "context_guard_adjusted": value.get("context_guard_adjusted", source.get("context_guard_adjusted", False)),
        })
    values = list(by_id.values())
    values.extend(verification.get("missed_issues") or [])
    return values


def _academic_score(section_reviews: Sequence[Dict[str, Any]], issues: Sequence[Dict[str, Any]]) -> float:
    weighted_total = sum(float(section.get("section_score") or 0) * max(1, int(section.get("paragraph_count") or 1)) for section in section_reviews)
    weight_sum = sum(max(1, int(section.get("paragraph_count") or 1)) for section in section_reviews)
    score = weighted_total / weight_sum if weight_sum else 0.0
    counts = defaultdict(int)
    for issue in issues:
        counts[issue.get("severity", "minor")] += 1
    if counts["critical"]: score = min(score, 54.0)
    elif counts["major"] >= 5: score = min(score, 60.0)
    elif counts["major"] >= 3: score = min(score, 68.0)
    elif counts["major"]: score = min(score, 78.0)
    elif counts["moderate"] >= 6: score = min(score, 82.0)
    return round(max(0.0, score), 1)


def _readiness(score: float, issues: Sequence[Dict[str, Any]], incomplete: bool) -> Tuple[str, str]:
    critical = sum(1 for issue in issues if issue.get("severity") == "critical")
    major = sum(1 for issue in issues if issue.get("severity") == "major")
    if incomplete:
        return "Review requires regeneration", "A required verification stage did not complete. Regenerate the review before treating the report or comments as final."
    if critical: return "Substantial revision required", f"The chapter contains {critical} critical academic issue(s) that must be resolved before supervisor approval."
    if score >= 85 and major == 0: return "Ready after minor refinement", "The chapter is academically sound overall, with targeted refinements still required."
    if score >= 70 and major <= 2: return "Revision required", "The chapter has a workable foundation but requires focused academic revision before approval."
    if score >= 55: return "Major revision required", "Several important weaknesses affect the chapter's academic adequacy, coherence, or defensibility."
    return "Substantial redevelopment required", "The chapter requires extensive academic redevelopment before it is ready for supervisor approval."


def _overall_assessment(
    score: float,
    issues: Sequence[Dict[str, Any]],
    strengths: Sequence[Dict[str, Any]],
    section_reviews: Sequence[Dict[str, Any]],
) -> str:
    counts = defaultdict(int)
    for issue in issues:
        counts[issue.get("severity", "minor")] += 1

    contextual = ""
    for section in section_reviews:
        heading = normalised(section.get("heading", ""))
        if "whole chapter coherence" in heading or "whole chapter" in heading:
            contextual = clean_text(section.get("section_assessment", ""))
            if contextual:
                break
    if not contextual:
        candidates = [
            clean_text(section.get("section_assessment", ""))
            for section in section_reviews
            if clean_text(section.get("section_assessment", ""))
            and "audit" not in normalised(section.get("heading", ""))
        ]
        contextual = " ".join(candidates[:2])

    judgement = "The chapter is academically coherent overall and requires mainly targeted refinement."
    if counts["critical"]:
        judgement = "Critical weaknesses currently prevent approval and should be addressed before attention shifts to language and formatting."
    elif counts["major"]:
        judgement = "The chapter has a workable foundation, but major revisions are needed before it reaches a defensible academic standard."
    elif counts["moderate"]:
        judgement = "The chapter is broadly developed, but clearer justification, evidence and scholarly refinement are still required."

    parts = [contextual, judgement]
    if strengths:
        parts.append(f"The review also identifies {len(strengths)} strength(s) that should be retained during revision.")
    return " ".join(part for part in parts if part).strip()


async def enrich_review_with_academic_ai(
    review: Dict[str, Any], runtime: Dict[str, Any], *, requested_mode: str = "standard",
    config: Optional[HybridAIConfig] = None, progress_callback: Any = None,
    checkpoint_manager: Optional[CheckpointManager] = None,
    retry_generation: int = 0,
) -> Dict[str, Any]:
    config = config or HybridAIConfig.from_env()
    academic_level = str((review.get("summary") or {}).get("academic_level") or "")
    depth = config.resolve_mode(requested_mode, academic_level)
    router = CostAwareAIProvider(config)

    current = list(runtime.get("current_paragraphs") or [])
    context = list(runtime.get("context_paragraphs") or [])
    original = list(runtime.get("original_paragraphs") or [])
    supervisor_comments = list(runtime.get("supervisor_comments") or [])
    all_paragraphs = current + context + original
    paragraph_index = {_pid(p): p for p in all_paragraphs}
    context_lock = build_context_lock(all_paragraphs, review.get("summary") or {})
    factual_index = build_factual_index(current)

    groups = _section_groups(current)
    max_section_chars = (
        max(12000, min(22000, config.max_context_chars_per_rule * 2))
        if depth == "light" else
        max(8000, min(18000, config.max_context_chars_per_rule * 2))
    )
    sections: List[Dict[str, Any]] = []
    for group in groups:
        sections.extend(_split_group(group, max_section_chars))

    whole_audit = _selected_audit_paragraphs(current, max(config.max_map_input_chars, 28000))
    if whole_audit:
        sections.append({"heading": "Whole-chapter coherence and consistency audit", "chapter_number": None, "section_path": [], "part": 1, "paragraphs": whole_audit})

    optional_chapters = list(
        (review.get("summary") or {}).get("optional_chapters_detected") or []
    )
    if optional_chapters:
        optional_paragraphs = [
            paragraph for paragraph in current
            if paragraph.get("chapter_number") in optional_chapters
        ]
        standard_alignment = _selected_audit_paragraphs(
            [
                paragraph for paragraph in current
                if paragraph.get("chapter_number") in {1, 2, 3, 4, 5}
            ],
            max(12000, config.max_map_input_chars // 2),
        )
        optional_packet = _selected_audit_paragraphs(
            optional_paragraphs,
            max(12000, config.max_map_input_chars // 2),
        )
        combined_optional = standard_alignment + [
            paragraph for paragraph in optional_packet
            if paragraph not in standard_alignment
        ]
        if combined_optional:
            sections.append({
                "heading": "Optional chapter integration and cross-thesis alignment audit",
                "chapter_number": None,
                "section_path": [],
                "part": 1,
                "paragraphs": combined_optional,
                "alignment_audit": True,
                "extra_context": {
                    "optional_chapters": optional_chapters,
                    "instruction": (
                        "Determine whether every optional chapter has a clear "
                        "disciplinary purpose and remains consistent with the "
                        "problem, objectives, literature, methods, results, "
                        "conclusions and recommendations."
                    ),
                },
            })

    if context:
        combined = _selected_audit_paragraphs(context + current, max(config.max_map_input_chars, 30000))
        if combined:
            sections.append({"heading": "Cross-chapter coherence and alignment", "chapter_number": None, "section_path": [], "part": 1, "paragraphs": combined, "alignment_audit": True})
    if supervisor_comments:
        revision_paragraphs = _selected_audit_paragraphs(original + current, max(config.max_map_input_chars, 30000))
        if revision_paragraphs:
            sections.append({
                "heading": "Supervisor comment compliance audit", "chapter_number": None, "section_path": [], "part": 1, "paragraphs": revision_paragraphs,
                "revision_audit": True,
                "extra_context": {"supervisor_comments": supervisor_comments},
            })

    for index, section in enumerate(sections):
        section["section_key"] = _section_key(section, index)

    provider = router
    primary_tokens = _degree_primary_output_tokens(academic_level, depth, config)
    if depth == "light":
        primary_system_prompt = LIGHT_REVIEW_SYSTEM_PROMPT
        batch_size = config.light_section_batch_size
    elif depth == "standard":
        primary_system_prompt = ACADEMIC_REVIEW_SYSTEM_PROMPT
        batch_size = config.section_batch_size
    else:
        primary_system_prompt = ACADEMIC_REVIEW_SYSTEM_PROMPT
        batch_size = config.advanced_section_batch_size

    if provider is None:
        raise AIProviderError(
            "The selected review service is not configured on the server."
        )

    # Review complete chapters in parallel. A long chapter is split only at
    # section boundaries when it exceeds the configured packet budget.
    section_batches = _chapter_review_packets(
        sections, config.chapter_packet_max_chars
    )

    await _notify(progress_callback, 35, "Reviewing chapters in parallel")

    completed_primary_batches = 0
    progress_lock = asyncio.Lock()

    async def primary_call(
        batch: Sequence[Dict[str, Any]],
        model: str,
        effort: str,
        purpose: str,
        tokens: int,
        *,
        track_primary_progress: bool = False,
        route_stage: Optional[ReviewStage] = None,
    ) -> ProviderResult:
        nonlocal completed_primary_batches
        user_prompt = _batch_prompt(
            review, batch, supervisor_comments, context_lock, depth
        )
        section_keys = [str(item.get("section_key") or "") for item in batch]
        input_hash = stable_hash({
            "pipeline": "academic-review-v1.9.9.0-deterministic-supervisory-checklist",
            "retry_generation": int(retry_generation or 0),
            "model": model,
            "effort": effort,
            "routing": provider.route_signature(
                stage=route_stage or stage_for_depth(depth),
                review_depth=depth,
                requested_model=model,
                requested_effort=effort,
            ),
            "purpose": purpose,
            "tokens": tokens,
            "system_prompt": primary_system_prompt,
            "user_prompt": user_prompt,
            "section_keys": section_keys,
        })
        stage_key = f"academic-primary-{input_hash[:20]}"
        result: Optional[ProviderResult] = None
        if checkpoint_manager is not None:
            result = checkpoint_manager.load_provider_result(
                stage_key,
                expected_input_hash=input_hash,
            )

        if result is None:
            if checkpoint_manager is not None:
                checkpoint_manager.mark_running(
                    stage_key,
                    input_hash=input_hash,
                    progress=35,
                    message=f"Reviewing chapter packet containing {len(batch)} section(s)",
                )
            result = await provider.complete_json(
                model=model,
                system_prompt=primary_system_prompt,
                user_prompt=user_prompt,
                schema_model=AcademicReviewBatch,
                purpose=purpose,
                reasoning_effort=effort,
                max_output_tokens=tokens,
                request_timeout_seconds=(
                    config.fast_request_timeout_seconds
                    if depth in {"light", "standard"}
                    else None
                ),
                request_max_retries=(
                    config.fast_request_max_retries
                    if depth in {"light", "standard"}
                    else None
                ),
                stage=route_stage or stage_for_depth(depth),
                review_depth=depth,
                # Light and Standard already receive a dedicated independent
                # accuracy audit. Escalating the entire first pass here caused
                # duplicate OpenAI work and unpredictable cost.
                allow_escalation=(depth == "advanced"),
            )
            if checkpoint_manager is not None:
                checkpoint_manager.save_provider_result(
                    stage_key,
                    result,
                    input_hash=input_hash,
                    progress=53,
                    message="Academic chapter packet completed",
                )

        if track_primary_progress:
            async with progress_lock:
                completed_primary_batches += 1
                progress = 35 + int(
                    18 * completed_primary_batches / max(1, len(section_batches))
                )
                await _notify(
                    progress_callback,
                    min(progress, 53),
                    f"Reviewed chapter packet {completed_primary_batches} of {len(section_batches)}",
                )
        return result

    primary_results = await _run_limited(
        [
            primary_call(
                batch,
                *_batch_model_route(batch, academic_level, config),
                "batched_academic_review",
                primary_tokens,
                track_primary_progress=True,
                route_stage=(
                    ReviewStage.RESEARCH_INTENSIVE_REVIEW
                    if _use_research_intensive_route(academic_level, config)
                    else None
                ),
            )
            for batch in section_batches
        ],
        min(config.chapter_review_concurrency, max(1, len(section_batches))),
    )
    await _notify(
        progress_callback,
        58,
        "Checking chapter coverage",
    )

    usage_records: List[AIUsageRecord] = []
    section_reviews: List[Dict[str, Any]] = []
    failed_batches: List[int] = []

    def consume_batch(batch: Sequence[Dict[str, Any]], result: ProviderResult) -> None:
        usage_records.append(_usage_cost(result.usage, config))
        returned = [
            item for item in (result.data.get("reviews") or [])
            if isinstance(item, dict)
        ]

        def compact_key(value: Any) -> str:
            return re.sub(r"[^a-z0-9]", "", str(value or "").lower())

        by_key = {
            str(item.get("section_key") or "").strip(): item
            for item in returned
            if str(item.get("section_key") or "").strip()
        }
        by_compact_key = {
            compact_key(item.get("section_key")): item
            for item in returned
            if compact_key(item.get("section_key"))
        }

        used_ids: set[int] = set()

        for section in batch:
            data = by_key.get(section["section_key"])
            if data is None:
                data = by_compact_key.get(compact_key(section["section_key"]))

            # Recover a valid response when the provider preserved the section
            # name but changed or omitted the opaque key.
            if data is None:
                target_heading = _normalise_heading(
                    clean_text(section.get("heading", "Untitled section"))
                )
                target_part = int(section.get("part") or 1)
                heading_matches = []
                for item in returned:
                    if id(item) in used_ids:
                        continue
                    returned_heading = _normalise_heading(
                        clean_text(
                            item.get("section_name")
                            or item.get("heading")
                            or ""
                        )
                    )
                    returned_part = int(item.get("part") or target_part)
                    if (
                        returned_heading
                        and returned_heading != "Untitled section"
                        and (
                            returned_heading == target_heading
                            or returned_heading in target_heading
                            or target_heading in returned_heading
                        )
                        and returned_part == target_part
                    ):
                        heading_matches.append(item)
                if len(heading_matches) == 1:
                    data = heading_matches[0]

            # A single-section retry has no ambiguity. Accept the single valid
            # review even if the provider altered the section key.
            if data is None and len(batch) == 1:
                unused = [item for item in returned if id(item) not in used_ids]
                if len(unused) == 1:
                    data = unused[0]

            if not data:
                continue

            used_ids.add(id(data))
            allowed_ids = {_pid(paragraph) for paragraph in section.get("paragraphs") or []}
            canonical_section = clean_text(section.get("heading", "Untitled section"))
            valid_issues = [
                valid
                for item in data.get("issues") or []
                if (valid := _valid_issue(
                    item,
                    paragraph_index,
                    context_lock,
                    allowed_ids=allowed_ids,
                    canonical_section=canonical_section,
                ))
            ]
            valid_strengths = []
            for strength in data.get("strengths") or []:
                ids = [
                    pid for pid in strength.get("evidence_paragraph_ids", [])
                    if pid in paragraph_index and pid in allowed_ids
                ]
                if not ids:
                    continue
                row = dict(strength)
                row["evidence_paragraph_ids"] = list(dict.fromkeys(ids))[:6]
                row["observation"], _ = sanitise_generated_text(row.get("observation", ""), context_lock)
                row["section"] = canonical_section
                guarded_strength = guard_strength(
                    row, paragraph_index, factual_index, canonical_section=canonical_section
                )
                if guarded_strength:
                    valid_strengths.append(guarded_strength)
            section_assessment, _ = sanitise_generated_text(data.get("section_assessment", ""), context_lock)
            section_assessment = guard_section_assessment(
                section_assessment,
                section.get("paragraphs") or [],
            )
            coverage_warning, _ = sanitise_generated_text(data.get("coverage_warning", ""), context_lock)
            section_reviews.append({
                "section_key": section["section_key"], "heading": clean_text(section.get("heading", "Untitled section")),
                "chapter_number": section.get("chapter_number"),
                "section_path": list(section.get("section_path") or []),
                "part": section.get("part", 1), "paragraph_count": len(section.get("paragraphs") or []),
                "section_score": float(data.get("section_score") or 0),
                "section_assessment": section_assessment,
                "coverage_warning": coverage_warning,
                "strengths": valid_strengths, "issues": valid_issues, "source_section": section,
            })

    for idx, (batch, result) in enumerate(zip(section_batches, primary_results)):
        if isinstance(result, Exception):
            failed_batches.append(idx)
        else:
            consume_batch(batch, result)

    # Recover omissions once at chapter-packet level. The previous pipeline
    # attempted grouped, single-section and focused recovery in sequence, which
    # could loop at 64 percent. One compact chapter retry preserves quality while
    # bounding latency and API calls.
    reviewed_keys = {row["section_key"] for row in section_reviews}
    missing_sections = [
        section for section in sections
        if section["section_key"] not in reviewed_keys
    ]
    recovery_errors: Dict[str, str] = {}
    verification_failed = False

    if (
        missing_sections
        and failed_batches
        and not section_reviews
        and depth in {"light", "standard"}
    ):
        raise AIProviderError(
            "The fast review providers did not complete the first chapter pass. "
            "The job was stopped before starting another full paid pass. Check "
            "the DeepSeek key, model access and provider logs, then retry once."
        )

    if missing_sections:
        recovery_packets = _chapter_review_packets(
            missing_sections,
            max(24000, config.chapter_packet_max_chars // 2),
        )
        recovery_tokens = min(
            primary_tokens, config.chapter_recovery_max_output_tokens
        )
        completed_recovery_packets = 0
        recovery_progress_lock = asyncio.Lock()

        async def recover_chapter_packet(
            packet: Sequence[Dict[str, Any]],
        ) -> ProviderResult:
            nonlocal completed_recovery_packets
            result = await primary_call(
                packet,
                *_batch_model_route(packet, academic_level, config),
                "chapter_packet_coverage_recovery",
                recovery_tokens,
            )
            async with recovery_progress_lock:
                completed_recovery_packets += 1
                progress = 58 + int(6 * completed_recovery_packets / max(1, len(recovery_packets)))
                await _notify(
                    progress_callback,
                    min(64, progress),
                    f"Recovered chapter packet {completed_recovery_packets} of {len(recovery_packets)}",
                )
            return result

        recovery_results = await _run_limited(
            [recover_chapter_packet(packet) for packet in recovery_packets],
            min(
                config.chapter_recovery_concurrency,
                max(1, len(recovery_packets)),
            ),
        )
        for packet, result in zip(recovery_packets, recovery_results):
            if isinstance(result, Exception):
                for section in packet:
                    recovery_errors[section["section_key"]] = str(result)
                continue
            consume_batch(packet, result)

    reviewed_keys = {row["section_key"] for row in section_reviews}
    still_missing = [
        section for section in sections
        if section["section_key"] not in reviewed_keys
    ]
    if still_missing:
        verification_failed = True
        for section in still_missing:
            section_reviews.append(
                _unresolved_section_fallback(
                    section, recovery_errors.get(section["section_key"], "")
                )
            )
        await _notify(
            progress_callback,
            64,
            (
                f"Preserved {len(still_missing)} unresolved section"
                f"{'s' if len(still_missing) != 1 else ''} without unsupported comments"
            ),
        )

    verification_failed = locals().get("verification_failed", False)
    await _notify(
        progress_callback,
        68,
        "Checking the relevance and accuracy of review comments",
    )

    all_primary = [
        issue
        for section_review in section_reviews
        for issue in section_review["issues"]
    ]

    # Accuracy is mandatory at every review depth. Light, Standard and
    # Advanced differ in the amount of feedback shown, not in factual
    # verification. Proposed findings are audited in small batches. A failed
    # batch is split once into focused sub-batches before a deterministic,
    # evidence-grounded fallback is used. This prevents an otherwise useful
    # review from being exported with an empty report and no Word comments.
    if all_primary:
        audit_model, audit_effort, audit_tokens, audit_stage = _degree_audit_settings(
            academic_level, depth, config
        )

        verification_batches: List[List[Dict[str, Any]]] = []
        pending: List[Dict[str, Any]] = []
        pending_issues = 0
        batch_limit = (
            max(4, config.fast_audit_batch_issue_limit)
            if depth in {"light", "standard"}
            else max(4, config.verification_batch_size)
        )
        for section_review in section_reviews:
            count = max(1, len(section_review.get("issues") or []))
            if pending and pending_issues + count > batch_limit:
                verification_batches.append(pending)
                pending = []
                pending_issues = 0
            pending.append(section_review)
            pending_issues += count
        if pending:
            verification_batches.append(pending)

        # A normal chapter review should make at most one OpenAI audit request.
        # If a very large chapter exceeds the limit, remaining findings still
        # pass through the deterministic evidence/placement gate instead of
        # triggering an unbounded series of paid requests.
        deferred_audit_sections: List[Dict[str, Any]] = []
        if depth in {"light", "standard"} and len(verification_batches) > config.fast_audit_max_batches:
            deferred = verification_batches[config.fast_audit_max_batches:]
            verification_batches = verification_batches[:config.fast_audit_max_batches]
            deferred_audit_sections = [row for batch in deferred for row in batch]

        def split_failed_batch(
            batch: Sequence[Dict[str, Any]], max_issues: int = 4
        ) -> List[List[Dict[str, Any]]]:
            pieces: List[Dict[str, Any]] = []
            for section_review in batch:
                issues = list(section_review.get("issues") or [])
                if not issues:
                    continue
                for offset in range(0, len(issues), max_issues):
                    copy = dict(section_review)
                    copy["issues"] = issues[offset:offset + max_issues]
                    pieces.append(copy)
            return [[piece] for piece in pieces]

        async def verify_batch(
            batch_label: str,
            batch: Sequence[Dict[str, Any]],
            *,
            retry: bool = False,
        ) -> ProviderResult:
            prompt = _verification_prompt(review, batch, depth, context_lock)
            audit_hash = stable_hash({
                "pipeline": "academic-comment-audit-v1.9.8.6-final-mphil-depth",
                "retry_generation": int(retry_generation or 0),
                "batch": batch_label,
                "retry": retry,
                "depth": depth,
                "academic_level": academic_level,
                "model": audit_model,
                "effort": audit_effort,
                "routing": provider.route_signature(
                    stage=audit_stage,
                    review_depth=depth,
                    requested_model=audit_model,
                    requested_effort=audit_effort,
                ),
                "tokens": audit_tokens,
                "system_prompt": ACADEMIC_VERIFY_SYSTEM_PROMPT,
                "user_prompt": prompt,
            })
            stage_key = f"academic-comment-audit-{audit_hash[:20]}"
            result = (
                checkpoint_manager.load_provider_result(
                    stage_key, expected_input_hash=audit_hash
                )
                if checkpoint_manager is not None else None
            )
            if result is None:
                if checkpoint_manager is not None:
                    checkpoint_manager.mark_running(
                        stage_key,
                        input_hash=audit_hash,
                        progress=68,
                        message=(
                            "Retrying a focused comment audit"
                            if retry else "Verifying review comments"
                        ),
                    )
                result = await provider.complete_json(
                    model=audit_model,
                    system_prompt=ACADEMIC_VERIFY_SYSTEM_PROMPT,
                    user_prompt=prompt,
                    schema_model=AcademicVerificationBatch,
                    purpose=(
                        f"{depth}_focused_comment_accuracy_retry"
                        if retry else f"{depth}_universal_comment_accuracy_audit"
                    ),
                    reasoning_effort=audit_effort,
                    max_output_tokens=audit_tokens,
                    request_timeout_seconds=(
                        config.fast_request_timeout_seconds
                        if depth in {"light", "standard"}
                        else None
                    ),
                    request_max_retries=(
                        config.fast_request_max_retries
                        if depth in {"light", "standard"}
                        else None
                    ),
                    stage=audit_stage,
                    review_depth=depth,
                    allow_escalation=(depth == "advanced"),
                )
                if checkpoint_manager is not None:
                    checkpoint_manager.save_provider_result(
                        stage_key,
                        result,
                        input_hash=audit_hash,
                        progress=76,
                        message="Comment accuracy audit batch completed",
                    )
            return result

        initial_results = await _run_limited(
            [
                verify_batch(str(index), batch)
                for index, batch in enumerate(verification_batches)
            ],
            min(config.max_parallel_calls, max(1, len(verification_batches))),
        )

        audit_units: List[Tuple[List[Dict[str, Any]], Any, bool]] = []
        retry_specs: List[Tuple[str, List[Dict[str, Any]]]] = []
        for batch_index, (batch, result) in enumerate(
            zip(verification_batches, initial_results)
        ):
            if isinstance(result, Exception):
                if depth == "advanced":
                    for retry_index, retry_batch in enumerate(split_failed_batch(batch)):
                        retry_specs.append((f"{batch_index}-retry-{retry_index}", retry_batch))
                else:
                    # No second paid request for Light/Standard. The normal
                    # fallback path below keeps only evidence-grounded,
                    # sufficiently confident findings.
                    audit_units.append((list(batch), result, False))
            else:
                audit_units.append((list(batch), result, False))

        if retry_specs and depth == "advanced":
            retry_results = await _run_limited(
                [
                    verify_batch(label, retry_batch, retry=True)
                    for label, retry_batch in retry_specs
                ],
                min(2, config.max_parallel_calls, max(1, len(retry_specs))),
            )
            for (_, retry_batch), result in zip(retry_specs, retry_results):
                audit_units.append((retry_batch, result, True))

        verified_by_section: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        # Preserve findings that were intentionally not sent to a second paid
        # model. They have already passed exact paragraph, quote and placement
        # checks and remain clearly identified in the internal audit trail.
        for section_review in deferred_audit_sections:
            for item in section_review.get("issues") or []:
                row = dict(item)
                row["verification_status"] = "deterministic_cost_guard"
                row["manual_confirmation_required"] = False
                verified_by_section[normalised(row.get("section", ""))].append(row)
        successful_audits = 0
        fallback_audits = 0
        for batch, result, was_retry in audit_units:
            batch_primary = [
                issue for section_review in batch
                for issue in section_review.get("issues") or []
            ]
            allowed_ids = {
                _pid(paragraph)
                for section_review in batch
                for paragraph in section_review.get("source_section", {}).get("paragraphs") or []
            }
            fallback_mode = isinstance(result, Exception)
            if fallback_mode:
                verification_failed = True
                fallback_audits += 1
                merged = list(batch_primary)
            else:
                successful_audits += 1
                usage_records.append(_usage_cost(result.usage, config))
                merged = _apply_verification(batch_primary, result.data)

            valid_rows: List[Dict[str, Any]] = []
            for item in merged:
                if fallback_mode:
                    severity = str(item.get("severity") or "minor").lower()
                    confidence = float(item.get("confidence") or 0.0)
                    if severity == "minor" or confidence < 0.60:
                        continue
                valid = _valid_issue(
                    item, paragraph_index, context_lock, allowed_ids=allowed_ids
                )
                if valid:
                    valid_rows.append(valid)
            gated_rows, _ = apply_accuracy_gate(
                valid_rows, paragraph_index, current
            )
            for valid in gated_rows:
                if fallback_mode:
                    valid["verification_status"] = "deterministic_fallback"
                    valid["manual_confirmation_required"] = True
                    valid["confidence"] = min(
                        float(valid.get("confidence") or 0.0), 0.72
                    )
                else:
                    valid["verification_status"] = (
                        "focused_ai_audit" if was_retry else "independent_ai_audit"
                    )
                    valid["manual_confirmation_required"] = False
                verified_by_section[normalised(valid.get("section", ""))].append(valid)

        for section_review in section_reviews:
            section_review["issues"] = verified_by_section.pop(
                normalised(section_review["heading"]), []
            )

        # Findings from synthetic whole-document audits are re-anchored by the
        # deterministic gate to their actual source section. Attach them only
        # where the exact heading exists, never to an unrelated opening page.
        if verified_by_section:
            by_heading = {normalised(row["heading"]): row for row in section_reviews}
            for section_key, values in list(verified_by_section.items()):
                target = by_heading.get(section_key)
                if target is not None:
                    target["issues"].extend(values)

        if fallback_audits:
            # Keep provider/audit failure details in internal metadata only.
            # Student-facing reports must not expose technical fallback notices.
            verification_failed = True


    raw_issues = [
        issue for section_review in section_reviews
        for issue in section_review["issues"]
    ]
    for deterministic in deterministic_expert_issues(
        current,
        academic_level=academic_level,
        research_approach=(review.get("summary") or {}).get("research_approach"),
    ):
        valid = _valid_issue(deterministic, paragraph_index, context_lock)
        if valid:
            raw_issues.append(valid)

    # v1.9.9.0: add evidence-backed deterministic supervisory checklist findings
    # before the accuracy/public-output gates. This makes the native DOCX review
    # depend on the attached supervisory checklist and thesis guidelines, not only
    # on model-generated findings. Findings still need an exact paragraph anchor
    # and pass through the same placement and public-comment quality gates.
    for checklist_issue in deterministic_supervisory_checklist_issues(
        current,
        academic_level=academic_level,
        research_approach=(review.get("summary") or {}).get("research_approach"),
    ):
        valid = _valid_issue(checklist_issue, paragraph_index, context_lock)
        if valid:
            raw_issues.append(valid)

    raw_issues, accuracy_gate_stats = apply_accuracy_gate(
        raw_issues, paragraph_index, current
    )
    all_issues = _consolidate_repetitive_issues(
        _deduplicate_issues(raw_issues)
    )
    if not all_issues:
        if depth in {"light", "standard"}:
            severity_rank = {
                "critical": 0,
                "major": 1,
                "moderate": 2,
                "minor": 3,
            }
            deterministic_rescue: List[Dict[str, Any]] = []
            for item in all_primary:
                severity = str(item.get("severity") or "minor").lower()
                confidence = float(item.get("confidence") or 0.0)
                if severity == "minor" or confidence < 0.68:
                    continue
                row = dict(item)
                row["verification_status"] = "deterministic_fast_rescue"
                row["manual_confirmation_required"] = True
                deterministic_rescue.append(row)
            deterministic_rescue.sort(
                key=lambda row: (
                    severity_rank.get(str(row.get("severity") or "minor"), 9),
                    -float(row.get("confidence") or 0.0),
                )
            )
            deterministic_rescue, _ = apply_accuracy_gate(
                deterministic_rescue[:16], paragraph_index, current
            )
            all_issues = _consolidate_repetitive_issues(
                _deduplicate_issues(deterministic_rescue)
            )

        low_scoring_sections = [
            section for section in section_reviews
            if float(section.get("section_score") or 0.0) < 75.0
        ]
        if low_scoring_sections and depth == "advanced":
            # Last-mile expert rescue. This mirrors a direct expert ChatGPT review:
            # one strong request receives the complete affected chapter packets and
            # must return only evidence-anchored comments. It is used only when the
            # independent audit removed every proposed issue. The deterministic
            # accuracy gate still controls what reaches the report and native DOCX.
            rescue_sources = [
                section.get("source_section") or {}
                for section in low_scoring_sections
                if (section.get("source_section") or {}).get("paragraphs")
            ]
            rescue_sources = rescue_sources[:8]
            if rescue_sources:
                rescue_result = await primary_call(
                    rescue_sources,
                    config.openai_final_audit_model,
                    config.openai_final_audit_reasoning_effort,
                    "direct_grounded_comment_rescue",
                    max(config.advanced_audit_max_output_tokens, 7000),
                    route_stage=ReviewStage.FINAL_AUDIT,
                )
                usage_records.append(_usage_cost(rescue_result.usage, config))
                source_by_key = {
                    str(section.get("section_key") or ""): section
                    for section in rescue_sources
                }
                rescue_rows: List[Dict[str, Any]] = []
                for item in rescue_result.data.get("reviews") or []:
                    source = source_by_key.get(str(item.get("section_key") or ""))
                    if not source:
                        continue
                    allowed_ids = {
                        _pid(paragraph)
                        for paragraph in source.get("paragraphs") or []
                    }
                    for issue in item.get("issues") or []:
                        candidate = dict(issue)
                        candidate["section"] = clean_text(source.get("heading") or candidate.get("section"))
                        valid = _valid_issue(
                            candidate, paragraph_index, context_lock, allowed_ids=allowed_ids
                        )
                        if valid:
                            valid["verification_status"] = "direct_expert_rescue"
                            valid["manual_confirmation_required"] = False
                            rescue_rows.append(valid)
                rescue_rows, _ = apply_accuracy_gate(
                    rescue_rows, paragraph_index, current
                )
                all_issues = _consolidate_repetitive_issues(
                    _deduplicate_issues(rescue_rows)
                )

        if low_scoring_sections and not all_issues:
            raise ReviewOutputValidationError(
                "The expert review completed, but no factual, correctly placed "
                "comments survived the evidence checks. A fresh automatic expert "
                "pass is required before any report or annotated document is released."
            )
    strengths = []
    seen = set()
    for section_review in section_reviews:
        for strength in section_review["strengths"]:
            key = hashlib.sha256(normalised(strength.get("observation", "")).encode("utf-8")).hexdigest()
            if key in seen: continue
            seen.add(key)
            evidence = [_evidence(paragraph_index[pid]) for pid in strength.get("evidence_paragraph_ids", []) if pid in paragraph_index]
            strengths.append({"category": strength.get("category", "other"), "section": clean_text(strength.get("section", "")), "observation": clean_text(strength.get("observation", "")), "evidence": evidence})

    if depth == "light":
        strengths = strengths[:6]

    # If a non-trivial chapter has many evidence-anchored first-pass issues but
    # the audit leaves a shallow report, retain additional supported findings up
    # to the degree/depth floor. This protects the expected ordering: Light <
    # Standard Non-Research Master's < Standard MPhil/doctorate for the same
    # weak document, without inventing comments or making extra paid calls.
    floor = _degree_comment_floor(academic_level, depth, config)
    if floor and len(all_issues) < floor and len(current) >= 12:
        existing_signatures = {_issue_signature(issue) for issue in all_issues}
        severity_rank = {"critical": 0, "major": 1, "moderate": 2, "minor": 3}
        candidates = []
        for item in all_primary:
            severity = str(item.get("severity") or "minor").lower()
            confidence = float(item.get("confidence") or 0.0)
            if severity == "minor" and depth != "advanced":
                continue
            if confidence < (0.70 if depth == "light" else 0.64):
                continue
            valid = _valid_issue(dict(item), paragraph_index, context_lock)
            if not valid:
                continue
            signature = _issue_signature(valid)
            if signature in existing_signatures:
                continue
            valid["verification_status"] = "depth_floor_evidence_retention"
            valid["manual_confirmation_required"] = True
            candidates.append(valid)
        candidates.sort(
            key=lambda row: (
                severity_rank.get(str(row.get("severity") or "minor"), 9),
                -float(row.get("confidence") or 0.0),
            )
        )
        candidates, _ = apply_accuracy_gate(candidates, paragraph_index, current)
        for candidate in candidates:
            signature = _issue_signature(candidate)
            if signature in existing_signatures:
                continue
            all_issues.append(candidate)
            existing_signatures.add(signature)
            if len(all_issues) >= floor:
                break
        all_issues = _consolidate_repetitive_issues(_deduplicate_issues(all_issues))

    # Final public-output quality gate. Internal provider/audit metadata remains
    # available in the job record, but student-facing findings cannot contain
    # placeholders, false future-date claims, duplicate advice or unfinished
    # generated wording.
    all_issues, public_quality_stats = prepare_public_issues(all_issues)

    # v1.9.8.6 applies the depth floor after public deduplication too. Earlier
    # versions could meet the MPhil floor before cleaning but fall below it after
    # duplicate and placeholder-safe filtering. Refill only with already generated
    # evidence-anchored findings that survive the same accuracy and public gates.
    if floor and len(all_issues) < floor and len(current) >= 12:
        severity_rank = {"critical": 0, "major": 1, "moderate": 2, "minor": 3}
        existing_signatures = {_issue_signature(issue) for issue in all_issues}
        refill_pool: List[Dict[str, Any]] = []
        for item in list(raw_issues) + list(all_primary):
            severity = str(item.get("severity") or "minor").lower()
            confidence = float(item.get("confidence") or 0.0)
            if severity == "minor" and depth != "advanced":
                continue
            if confidence < (0.66 if depth == "light" else 0.58):
                continue
            valid = _valid_issue(dict(item), paragraph_index, context_lock)
            if not valid:
                continue
            signature = _issue_signature(valid)
            if signature in existing_signatures:
                continue
            valid["verification_status"] = "post_public_depth_refill"
            valid["manual_confirmation_required"] = True
            refill_pool.append(valid)
            existing_signatures.add(signature)

        refill_pool.sort(
            key=lambda row: (
                severity_rank.get(str(row.get("severity") or "minor"), 9),
                -float(row.get("confidence") or 0.0),
            )
        )
        refill_pool, _ = apply_accuracy_gate(
            refill_pool[:max(16, floor * 3)], paragraph_index, current
        )
        working = list(all_issues)
        for candidate in refill_pool:
            trial, _trial_stats = prepare_public_issues(working + [candidate])
            if len(trial) > len(working):
                working = trial
            if len(working) >= floor:
                break
        if len(working) > len(all_issues):
            public_quality_stats["post_public_refill_added"] = len(working) - len(all_issues)
            public_quality_stats["kept"] = len(working)
            all_issues = working


    # v1.9.9.6: ensure a safe summary object exists before the final degree
    # contract rescue runs. In the combined OpenAI pipeline the provider can
    # return successfully before the later summary assembly block executes;
    # the coverage rescue must therefore not reference an uninitialised local.
    summary = review.get("summary") or {}
    if not isinstance(summary, dict):
        summary = {}

    # v1.9.9.3: final level-wide coverage rescue. Deterministic checklist
    # findings are re-tested after public cleaning so that all supported degree
    # levels visibly cover their mandatory supervisory categories. This prevents
    # Bachelor's, Non-Research Master's, MPhil, Professional Doctorate and PhD
    # reviews from collapsing into a small proofreading-style comment set.
    required_categories = _degree_required_public_categories(
        academic_level, summary.get("selected_chapter"), depth
    )
    present_categories = {str(issue.get("category") or "") for issue in all_issues}
    if required_categories - present_categories or (floor and len(all_issues) < floor):
        coverage_pool: List[Dict[str, Any]] = []
        for item in deterministic_supervisory_checklist_issues(
            current,
            academic_level=academic_level,
            research_approach=(review.get("summary") or {}).get("research_approach"),
            max_issues=max(48, floor * 3 if floor else 48),
        ):
            valid = _valid_issue(dict(item), paragraph_index, context_lock)
            if valid:
                valid["verification_status"] = "final_degree_contract_rescue"
                valid["manual_confirmation_required"] = False
                coverage_pool.append(valid)
        coverage_pool, _coverage_accuracy = apply_accuracy_gate(coverage_pool, paragraph_index, current)
        coverage_public, _coverage_public_stats = prepare_public_issues(coverage_pool)
        existing_signatures = {_issue_signature(issue) for issue in all_issues}
        existing_category_sigs = {_category_signature(issue) for issue in all_issues}
        additions: List[Dict[str, Any]] = []
        # First add missing mandatory categories.
        for candidate in coverage_public:
            cat = str(candidate.get("category") or "")
            if cat not in required_categories or cat in present_categories:
                continue
            sig = _issue_signature(candidate)
            cat_sig = _category_signature(candidate)
            if sig in existing_signatures or cat_sig in existing_category_sigs:
                continue
            additions.append(candidate)
            existing_signatures.add(sig)
            existing_category_sigs.add(cat_sig)
            present_categories.add(cat)
        # Then fill the strengthened level/depth floor with the strongest
        # remaining deterministic findings.
        if floor and len(all_issues) + len(additions) < floor:
            for candidate in coverage_public:
                sig = _issue_signature(candidate)
                cat_sig = _category_signature(candidate)
                if sig in existing_signatures or cat_sig in existing_category_sigs:
                    continue
                if str(candidate.get("severity") or "minor").lower() == "minor" and depth != "advanced":
                    continue
                additions.append(candidate)
                existing_signatures.add(sig)
                existing_category_sigs.add(cat_sig)
                if len(all_issues) + len(additions) >= floor:
                    break
        if additions:
            working, _working_stats = prepare_public_issues(list(all_issues) + additions)
            if len(working) > len(all_issues):
                public_quality_stats["final_degree_contract_added"] = len(working) - len(all_issues)
                public_quality_stats["kept"] = len(working)
                all_issues = working

    finding_rows = [_finding_row(issue, paragraph_index) for issue in all_issues]
    incomplete = verification_failed or len(section_reviews) < len(sections)
    score = _academic_score(section_reviews, all_issues)
    readiness_label, readiness_meaning = (
        _light_readiness(score, all_issues, academic_level)
        if depth == "light"
        else _readiness(score, all_issues, incomplete)
    )

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
    for issue in all_issues: counts[issue.get("severity", "minor")] += 1
    priority_candidates = [
        {"section": row.get("section", ""), "severity": row.get("severity", "moderate"),
         "status": row.get("status_label", "Revision required"), "action": row.get("required_action", ""),
         "issue": row.get("item", "")}
        for row in finding_rows
    ]
    for row in review.get("revision_results") or []:
        if row.get("status") in {"partly_meets_requirement", "does_not_meet_requirement", "manual_review_required"}:
            priority_candidates.append({"section": row.get("section", "Supervisor comment follow-up"), "severity": row.get("severity", "major"), "status": row.get("status_label", "Revision required"), "action": row.get("required_action", ""), "issue": "Earlier supervisor comment"})
    priority_candidates = sorted(priority_candidates, key=lambda x: SEVERITY_ORDER.get(x.get("severity", "minor"), 9))
    priority = []
    seen_priority = set()
    for item in priority_candidates:
        signature = (normalised(item.get("section", "")), normalised(item.get("action", ""))[:180])
        if not signature[1] or signature in seen_priority:
            continue
        seen_priority.add(signature)
        priority.append(item)
        priority_limit = 8 if depth == "light" else (10 if depth == "standard" else 12)
        if len(priority) >= priority_limit:
            break

    profile = _review_profile(depth)
    benchmark = _combined_benchmark(academic_level, depth)
    actual_section_names = {
        normalised(section.get("heading", ""))
        for section in section_reviews
        if normalised(section.get("heading", ""))
        and not any(term in normalised(section.get("heading", "")) for term in (
            "whole chapter coherence", "cross chapter coherence", "cross chapter alignment", "supervisor comment compliance audit"
        ))
    }
    summary.update({
        "review_depth": depth,
        "review_benchmark": benchmark["degree_standard"],
        "declared_degree_standard": benchmark["degree_label"],
        "review_intensity": benchmark["review_intensity"],
        "degree_specific_review_contract": _degree_specific_review_contract(
            academic_level, summary.get("selected_chapter"), depth
        ),
        "degree_calibrated_issue_ceiling": _degree_issue_limit(academic_level, depth),
        "degree_calibrated_audit_capacity": _degree_audit_max_findings(academic_level, depth),
        "academic_review_score": score, "overall_score": overall,
        "readiness_label": readiness_label, "readiness_meaning": readiness_meaning,
        "academic_review_complete": not incomplete,
        "academic_sections_reviewed": len(actual_section_names),
        "academic_review_units_completed": len(section_reviews),
        "critical_issues": counts["critical"], "major_issues": counts["major"],
        "moderate_issues": counts["moderate"], "minor_issues": counts["minor"],
        "strengths_identified": len(strengths),
        "accuracy_gate_kept": accuracy_gate_stats.get("kept", 0),
        "accuracy_gate_dropped": accuracy_gate_stats.get("dropped", 0),
        "accuracy_gate_adjusted": accuracy_gate_stats.get("adjusted", 0),
        "public_comment_quality_kept": public_quality_stats.get("kept", 0),
        "public_comment_quality_dropped": public_quality_stats.get("dropped", 0),
        "public_comment_quality_adjusted": public_quality_stats.get("adjusted", 0),
        "universal_accuracy_audit_applied": True,
        "verified_finding_count": sum(
            1 for issue in all_issues
            if issue.get("verification_status") in {"independent_ai_audit", "focused_ai_audit"}
        ),
        "manual_confirmation_finding_count": sum(
            1 for issue in all_issues if issue.get("manual_confirmation_required")
        ),
        "review_rebuild_recommended": bool(incomplete and not finding_rows),
    })
    review["study_context"] = public_context(context_lock)
    review["academic_findings"] = finding_rows
    review["academic_strengths"] = strengths
    review["academic_section_reviews"] = [{k: v for k, v in section.items() if k not in {"source_section", "issues", "strengths"}} for section in section_reviews]
    review["overall_academic_assessment"] = _overall_assessment(score, all_issues, strengths, section_reviews)
    if depth == "light":
        contextual_parts = [
            clean_text(section.get("section_assessment", ""))
            for section in section_reviews
            if clean_text(section.get("section_assessment", ""))
            and "audit" not in normalised(section.get("heading", ""))
        ]
        contextual_summary = " ".join(contextual_parts[:2])
        review["overall_academic_assessment"] = (
            (contextual_summary + " " if contextual_summary else "")
            + f"Every detected section and subsection was assessed concisely against the standard expected of a {benchmark['degree_label']}. "
            + "The review reports the most material issues and provides context-aware guidance where revision is required."
        ).strip()
    review["priority_actions"] = priority
    review["ai_review"] = {
        "review_depth": depth,
        "review_benchmark": benchmark["degree_standard"],
        "declared_degree_standard": benchmark["degree_label"],
        "review_intensity": benchmark["review_intensity"],
        "usage": [record.model_dump() for record in usage_records],
        "estimated_cost_usd": round(sum(record.estimated_cost_usd for record in usage_records), 6),
        "academic_review_complete": not incomplete,
        "active_provider": "cost_aware_router",
        "comment_accuracy_second_pass": bool(all_primary),
        "comment_accuracy_audit_mode": "single_compact_evidence_audit" if all_primary else "not_required",
        "advanced_second_pass": bool(depth == "advanced" and all_primary),
        "advanced_audit_mode": "single_compact_evidence_audit" if depth == "advanced" and all_primary else "not_applicable",
        "api_call_count": len(usage_records),
        "primary_batch_count": len(section_batches),
        "primary_packet_mode": "chapter_level_parallel",
        "chapter_packet_max_chars": config.chapter_packet_max_chars,
        "coverage_recovery_mode": "single_chapter_packet_retry",
        "verification_batch_size": config.verification_batch_size,
        "context_guard_enabled": True,
    }
    await _notify(progress_callback, 86, "Preparing the annotated review")
    return review
