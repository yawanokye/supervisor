from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .ai_config import AIConfigurationError, HybridAIConfig
from .ai_prompts import ACADEMIC_REVIEW_SYSTEM_PROMPT, ACADEMIC_VERIFY_SYSTEM_PROMPT, LIGHT_REVIEW_SYSTEM_PROMPT
from .ai_providers import AIProviderError, DeepSeekProvider, OpenAIProvider, ProviderResult
from .academic_review_guide import guide_for_heading
from .context_guard import build_context_lock, public_context, sanitise_generated_text, sanitise_issue
from .checkpointing import CheckpointManager, stable_hash
from .ai_schemas import (
    AIUsageRecord,
    AcademicIssue,
    AcademicReviewBatch,
    AcademicVerificationBatch,
)
from .document_parser import clean_text, normalised

SEVERITY_ORDER = {"critical": 0, "major": 1, "moderate": 2, "minor": 3}
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
        "benchmark": "Bachelor’s dissertation or non-research Master’s project",
        "focus": (
            "Complete section-by-section and subsection-by-subsection review at a foundational academic standard. "
            "Emphasise correct structure, basic coherence, clear concepts, credible evidence, alignment, essential methodology, "
            "defensible interpretation, research-integrity checks and readable scholarly presentation."
        ),
        "normal_issue_limit_per_section": 2,
    },
    "standard": {
        "label": "Standard Review",
        "benchmark": "Research Master’s or MPhil dissertation",
        "focus": (
            "Complete section-by-section and subsection-by-subsection review at a research Master’s standard. "
            "Require critical synthesis, defensible theoretical grounding, explicit methodological justification, "
            "objective-method-result alignment and a clear contribution appropriate to MPhil-level research."
        ),
        "normal_issue_limit_per_section": 4,
    },
    "advanced": {
        "label": "Advanced Review",
        "benchmark": "Professional Doctorate or PhD thesis",
        "focus": (
            "Complete section-by-section and subsection-by-subsection review at doctoral standard. "
            "Apply rigorous scrutiny to originality, theoretical and methodological contribution, assumptions, robustness, "
            "alternative explanations, scholarly positioning and contribution to knowledge."
        ),
        "normal_issue_limit_per_section": 5,
    },
}


def _review_profile(depth: str) -> Dict[str, Any]:
    return REVIEW_LEVEL_PROFILES.get(depth, REVIEW_LEVEL_PROFILES["standard"])


def _is_doctoral_level(academic_level: Any) -> bool:
    value = normalised(str(academic_level or ""))
    return (
        value == "phd"
        or "professional doctorate" in value
        or value.startswith("doctor of ")
        or value.startswith("doctoral")
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
        "source_kind": paragraph.get("source_kind", "paragraph"),
        "table_index": paragraph.get("table_index"),
        "table_row": paragraph.get("table_row"),
        "matched_terms": [], "adequacy_terms": [], "rank_score": 1,
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
            current = current[-1:]
            total = sum(len(clean_text(p.get("text", ""))) + 120 for p in current)
        current.append(paragraph)
        total += size
    if current:
        chunks.append({"heading": group["heading"], "part": part, "paragraphs": current})
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
    sections = []
    for section in batch:
        sections.append({
            "section_key": section["section_key"],
            "heading": clean_text(section.get("heading", "Untitled section")),
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
            "review_benchmark": profile["benchmark"],
            "depth_expectation": profile["focus"],
        },
        "study_context_lock": {
            key: value for key, value in context_lock.items()
            if key != "source_text_normalised"
        },
        "chapter_review_dimensions": _chapter_dimensions(review),
        "coverage_contract": {
            "review_every_section_and_subsection": True,
            "return_exactly_one_review_for_each_section_key": True,
            "section_assessment_required_even_when_no_issue_is_found": True,
            "strengths_should_be_reported_where_deserved": True,
            "normal_issue_limit_per_section": profile["normal_issue_limit_per_section"],
        },
        "accuracy_contract": {
            "do_not_introduce_external_countries_or_locations": True,
            "do_not_invent_citations_statistics_or_organisations": True,
            "use_placeholders_for_unknown_context": True,
            "distinguish_missing_from_weak_content": True,
            "make_method_advice_conditional_when_design_is_unknown": True,
            "do_not_review_context_only_chapters_as_the_selected_chapter": True,
            "when_combined_chapters_are_selected_review_every_chapter_in_the_range": True,
            "verify_alignment_sequentially_from_chapter_one_to_the_last_selected_chapter": True,
            "verify_objective_question_hypothesis_method_result_conclusion_alignment": True,
            "verify_model_specific_diagnostics_in_methods_and_results": True,
            "verify_statistical_values_against_tables_and_interpretations": True,
            "treat_local_statistical_flags_as_items_to_verify_not_automatic_conclusions": True,
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
            "Give examples only from the confirmed study context, or use neutral placeholders when a contextual detail is not supplied."
        ),
        "sections": sections,
    }
    return json.dumps(packet, ensure_ascii=False)


def _verification_prompt(
    review: Dict[str, Any],
    batch: Sequence[Dict[str, Any]],
    depth: str,
    context_lock: Dict[str, Any],
) -> str:
    summary = review.get("summary") or {}
    profile = _review_profile(depth)
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
            "declared_academic_level": summary.get("academic_level"),
            "research_approach": summary.get("research_approach"),
            "review_depth": depth,
            "review_benchmark": profile["benchmark"],
            "depth_expectation": profile["focus"],
        },
        "study_context_lock": {
            key: value for key, value in context_lock.items()
            if key != "source_text_normalised"
        },
        "source_paragraphs": list(paragraphs.values()),
        "proposed_reviews": proposals,
        "instruction": (
            "Independently verify the proposed issues at the stated benchmark. Remove unsupported, repetitive or misplaced findings; "
            "correct severity and evidence; add important missed issues; and confirm that all sections received a substantive assessment. "
            "Reject any example, citation, statistic, country, location, organisation, population or design assumption not found in the source. "
            "For Advanced Review, apply doctoral expectations to originality, theoretical contribution, methodological defensibility, "
            "robustness, alternative explanations and contribution to knowledge."
        ),
    }
    return json.dumps(packet, ensure_ascii=False)


def _compact_advanced_audit_prompt(
    review: Dict[str, Any],
    section_reviews: Sequence[Dict[str, Any]],
    context_lock: Dict[str, Any],
    paragraph_index: Dict[str, Dict[str, Any]],
    audit_paragraphs: Sequence[Dict[str, Any]],
    max_findings: int,
    max_source_chars: int,
) -> str:
    """Build one compact doctoral audit instead of re-reviewing every batch.

    The audit receives all section assessments, only the highest-priority
    findings, and a focused evidence packet. This keeps doctoral quality
    control while avoiding another full set of section-by-section API calls.
    """
    summary = review.get("summary") or {}

    all_issues = [
        issue
        for section_review in section_reviews
        for issue in section_review.get("issues") or []
    ]
    all_issues.sort(
        key=lambda item: (
            SEVERITY_ORDER.get(item.get("severity", "minor"), 9),
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
            "declared_academic_level": summary.get("academic_level"),
            "research_approach": summary.get("research_approach"),
            "review_depth": "advanced",
            "review_benchmark": REVIEW_LEVEL_PROFILES["advanced"]["benchmark"],
        },
        "study_context_lock": {
            key: value for key, value in context_lock.items()
            if key != "source_text_normalised"
        },
        "section_assessments": proposals,
        "focused_source_paragraphs": source_rows,
        "instruction": (
            "Conduct one compact doctoral quality audit. Verify the supplied "
            "priority findings, remove unsupported or repetitive findings, "
            "correct severity and evidence, and add only genuinely critical or "
            "major issues missed by the primary review. Do not re-review every "
            "minor wording point. Check originality, theory, methodological "
            "defensibility, coherence, robustness, alternative explanations and "
            "contribution to knowledge. Use only the confirmed study context."
        ),
    }
    return json.dumps(packet, ensure_ascii=False)


def _valid_issue(
    issue: Dict[str, Any],
    paragraph_index: Dict[str, Dict[str, Any]],
    context_lock: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    try:
        parsed = AcademicIssue.model_validate(issue).model_dump()
    except Exception:
        return None
    parsed = sanitise_issue(parsed, context_lock)
    parsed["evidence_paragraph_ids"] = [
        pid for pid in parsed["evidence_paragraph_ids"] if pid in paragraph_index
    ]
    quote = clean_text(parsed.get("problematic_quote", ""))
    if quote and not any(
        quote in clean_text(paragraph_index[pid].get("text", ""))
        for pid in parsed["evidence_paragraph_ids"]
    ):
        parsed["problematic_quote"] = ""
    if not parsed["evidence_paragraph_ids"]:
        parsed["confidence"] = min(float(parsed["confidence"]), 0.55)
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
    evidence = [_evidence(paragraph_index[pid]) for pid in issue.get("evidence_paragraph_ids", []) if pid in paragraph_index]
    assessment = clean_text(issue.get("assessment", ""))
    consequence = clean_text(issue.get("academic_consequence", ""))
    comment = assessment + (f" Academic implication: {consequence}" if consequence else "")
    section = clean_text(issue.get("section", "")) or "Chapter-wide review"
    return {
        "review_type": "academic_finding", "finding_id": issue.get("finding_id", ""),
        "category": issue.get("category", "other"), "section": section,
        "item": clean_text(issue.get("issue_title", "Academic issue")), "status": status,
        "status_label": label, "severity": severity, "confidence": round(float(issue.get("confidence") or 0), 2),
        "evidence": evidence, "comment": comment, "required_action": clean_text(issue.get("required_action", "")),
        "illustrative_guidance": clean_text(issue.get("illustrative_guidance", "")),
        "guidance_type": issue.get("guidance_type", "direct_correction"),
        "source_verification_required": bool(issue.get("source_verification_required")),
        "context_guard_adjusted": bool(issue.get("context_guard_adjusted")),
        "problematic_quote": clean_text(issue.get("problematic_quote", "")), "headings": [section],
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


def _light_readiness(score: float, issues: Sequence[Dict[str, Any]]) -> Tuple[str, str]:
    critical = sum(1 for issue in issues if issue.get("severity") == "critical")
    major = sum(1 for issue in issues if issue.get("severity") == "major")
    moderate = sum(1 for issue in issues if issue.get("severity") == "moderate")
    if critical or major >= 3 or score < 60:
        label = "Foundational revision required"
    elif major or moderate:
        label = "Targeted revision required"
    else:
        label = "Meets the foundational review standard with minor refinement"
    meaning = (
        "Every detected section and subsection was reviewed against the standard expected of a Bachelor’s dissertation or non-research Master’s project. "
        "The guidance addresses structure, coherence, evidence, alignment, essential methodology, interpretation, research-integrity warning signs and academic presentation at that level."
    )
    return label, meaning


def _usage_cost(usage: AIUsageRecord, config: HybridAIConfig) -> AIUsageRecord:
    uncached = max(0, usage.input_tokens - usage.cached_input_tokens)
    if usage.provider == "deepseek":
        p_in = config.deepseek_pro_input_price
        p_cache = config.deepseek_pro_cached_input_price
        p_out = config.deepseek_pro_output_price
    else:
        p_in = config.openai_review_input_price
        p_cache = config.openai_review_cached_input_price
        p_out = config.openai_review_output_price

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
        return "Review completed with a limitation", "Most sections were reviewed, but one review batch could not be independently verified. The available findings remain usable, while the affected section should receive manual confirmation."
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
) -> Dict[str, Any]:
    config = config or HybridAIConfig.from_env()
    academic_level = str((review.get("summary") or {}).get("academic_level") or "")
    depth = config.resolve_mode(requested_mode, academic_level)
    deepseek = DeepSeekProvider(config) if config.deepseek_configured else None
    openai = OpenAIProvider(config) if config.openai_configured else None  # optional legacy fallback only

    current = list(runtime.get("current_paragraphs") or [])
    context = list(runtime.get("context_paragraphs") or [])
    original = list(runtime.get("original_paragraphs") or [])
    supervisor_comments = list(runtime.get("supervisor_comments") or [])
    all_paragraphs = current + context + original
    paragraph_index = {_pid(p): p for p in all_paragraphs}
    context_lock = build_context_lock(all_paragraphs, review.get("summary") or {})

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
        sections.append({"heading": "Whole-chapter coherence and consistency audit", "part": 1, "paragraphs": whole_audit})

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
            sections.append({"heading": "Cross-chapter coherence and alignment", "part": 1, "paragraphs": combined, "alignment_audit": True})
    if supervisor_comments:
        revision_paragraphs = _selected_audit_paragraphs(original + current, max(config.max_map_input_chars, 30000))
        if revision_paragraphs:
            sections.append({
                "heading": "Supervisor comment compliance audit", "part": 1, "paragraphs": revision_paragraphs,
                "revision_audit": True,
                "extra_context": {"supervisor_comments": supervisor_comments},
            })

    for index, section in enumerate(sections):
        section["section_key"] = _section_key(section, index)

    if depth == "light":
        provider = deepseek
        primary_model = config.deepseek_review_model
        primary_effort = config.deepseek_reasoning_effort
        primary_tokens = config.light_max_output_tokens
        primary_system_prompt = LIGHT_REVIEW_SYSTEM_PROMPT
        batch_size = config.light_section_batch_size
    elif depth == "standard":
        provider = deepseek
        primary_model = config.deepseek_review_model
        primary_effort = config.deepseek_reasoning_effort
        primary_tokens = config.standard_max_output_tokens
        primary_system_prompt = ACADEMIC_REVIEW_SYSTEM_PROMPT
        batch_size = config.section_batch_size
    else:
        provider = deepseek
        primary_model = config.deepseek_advanced_model
        primary_effort = config.deepseek_advanced_primary_reasoning_effort
        primary_tokens = config.advanced_max_output_tokens
        primary_system_prompt = ACADEMIC_REVIEW_SYSTEM_PROMPT
        batch_size = config.advanced_section_batch_size

    if provider is None:
        raise AIProviderError(
            "The selected review service is not configured on the server."
        )

    section_batches = _batch(sections, batch_size)

    await _notify(progress_callback, 35, "Reviewing chapter sections")

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
    ) -> ProviderResult:
        nonlocal completed_primary_batches
        user_prompt = _batch_prompt(
            review, batch, supervisor_comments, context_lock, depth
        )
        section_keys = [str(item.get("section_key") or "") for item in batch]
        input_hash = stable_hash({
            "pipeline": "academic-review-v1.7.0",
            "model": model,
            "effort": effort,
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
                    message=f"Reviewing section group containing {len(batch)} unit(s)",
                )
            result = await provider.complete_json(
                model=model,
                system_prompt=primary_system_prompt,
                user_prompt=user_prompt,
                schema_model=AcademicReviewBatch,
                purpose=purpose,
                reasoning_effort=effort,
                max_output_tokens=tokens,
            )
            if checkpoint_manager is not None:
                checkpoint_manager.save_provider_result(
                    stage_key,
                    result,
                    input_hash=input_hash,
                    progress=53,
                    message="Academic section group completed",
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
                    f"Reviewed section group {completed_primary_batches} of {len(section_batches)}",
                )
        return result

    primary_results = await _run_limited(
        [
            primary_call(
                batch,
                primary_model,
                primary_effort,
                "batched_academic_review",
                primary_tokens,
                track_primary_progress=True,
            )
            for batch in section_batches
        ],
        config.max_parallel_calls,
    )
    await _notify(
        progress_callback,
        54,
        "Completing section coverage and checking omitted sections",
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
            valid_issues = [valid for item in data.get("issues") or [] if (valid := _valid_issue(item, paragraph_index, context_lock))]
            valid_strengths = []
            for strength in data.get("strengths") or []:
                ids = [pid for pid in strength.get("evidence_paragraph_ids", []) if pid in paragraph_index]
                if ids:
                    row = dict(strength)
                    row["evidence_paragraph_ids"] = ids
                    row["observation"], _ = sanitise_generated_text(row.get("observation", ""), context_lock)
                    row["section"], _ = sanitise_generated_text(row.get("section", ""), context_lock)
                    valid_strengths.append(row)
            section_assessment, _ = sanitise_generated_text(data.get("section_assessment", ""), context_lock)
            coverage_warning, _ = sanitise_generated_text(data.get("coverage_warning", ""), context_lock)
            section_reviews.append({
                "section_key": section["section_key"], "heading": clean_text(section.get("heading", "Untitled section")),
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

    # Retry omitted sections in grouped recovery batches. This prevents one
    # additional API call for every omitted subsection.
    reviewed_keys = {row["section_key"] for row in section_reviews}
    retry_sections = [
        section for section in sections
        if section["section_key"] not in reviewed_keys
    ]
    if retry_sections:
        if depth in {"light", "standard"}:
            recovery_model = config.deepseek_review_model
            recovery_effort = config.deepseek_reasoning_effort
            recovery_tokens = (
                config.light_max_output_tokens
                if depth == "light"
                else config.standard_max_output_tokens
            )
        else:
            recovery_model = config.deepseek_advanced_model
            recovery_effort = config.deepseek_advanced_primary_reasoning_effort
            recovery_tokens = config.advanced_max_output_tokens

        recovery_batches = _batch(
            retry_sections,
            config.recovery_batch_size,
        )[: config.max_recovery_batches]

        retry_results = await _run_limited(
            [
                primary_call(
                    batch,
                    recovery_model,
                    recovery_effort,
                    "section_review_recovery",
                    recovery_tokens,
                )
                for batch in recovery_batches
            ],
            min(config.max_parallel_calls, len(recovery_batches) or 1),
        )
        for batch, result in zip(recovery_batches, retry_results):
            if not isinstance(result, Exception):
                consume_batch(batch, result)

        await _notify(
            progress_callback,
            62,
            "Completing coverage checks",
        )

    reviewed_keys = {row["section_key"] for row in section_reviews}
    retry_sections = [section for section in sections if section["section_key"] not in reviewed_keys]
    if retry_sections:
        if depth in {"light", "standard"}:
            recovery_model = config.deepseek_review_model
            recovery_effort = config.deepseek_reasoning_effort
            recovery_tokens = (
                config.light_max_output_tokens
                if depth == "light"
                else config.standard_max_output_tokens
            )
        else:
            recovery_model = config.deepseek_advanced_model
            recovery_effort = config.deepseek_advanced_reasoning_effort
            recovery_tokens = config.advanced_max_output_tokens
        retry_results = await _run_limited(
            [primary_call([section], recovery_model, recovery_effort, "section_review_recovery", recovery_tokens) for section in retry_sections],
            config.max_parallel_calls,
        )
        for section, result in zip(retry_sections, retry_results):
            if not isinstance(result, Exception):
                consume_batch([section], result)
        await _notify(
            progress_callback,
            64,
            "Finalising coverage of every section and subsection",
        )

    reviewed_keys = {row["section_key"] for row in section_reviews}
    still_missing = [
        section for section in sections
        if section["section_key"] not in reviewed_keys
    ]
    short_missing = [
        section for section in still_missing
        if len(section.get("paragraphs") or []) <= 2
        and sum(
            len(clean_text(paragraph.get("text", "")))
            for paragraph in section.get("paragraphs") or []
        ) <= 1200
    ]

    if (
        still_missing
        and len(still_missing) <= config.max_short_section_fallbacks
        and len(short_missing) == len(still_missing)
    ):
        verification_failed = True
        for section in still_missing:
            section_reviews.append({
                "section_key": section["section_key"],
                "heading": clean_text(
                    section.get("heading", "Untitled section")
                ),
                "part": section.get("part", 1),
                "paragraph_count": len(section.get("paragraphs") or []),
                "section_score": 50.0,
                "section_assessment": (
                    "This short section was included in the chapter-wide context, "
                    "but the provider did not return a separate section assessment. "
                    "Manual confirmation is recommended."
                ),
                "coverage_warning": (
                    "Separate model output was unavailable for this short section."
                ),
                "strengths": [],
                "issues": [],
                "source_section": section,
            })
        still_missing = []

    if still_missing:
        names = ", ".join(
            clean_text(section.get("heading", "Untitled section"))
            for section in still_missing[:5]
        )
        raise AIProviderError(
            "The expert review could not complete the following substantive "
            f"section(s) after grouped recovery: {names}. Please retry the review."
        )

    verification_failed = locals().get("verification_failed", False)
    if depth in {"light", "standard"}:
        await _notify(
            progress_callback,
            68,
            "Consolidating the academic review and guidance",
        )
    elif config.advanced_quality_control:
        await _notify(
            progress_callback,
            68,
            "Conducting one compact doctoral quality audit",
        )

        all_primary = [
            issue
            for section_review in section_reviews
            for issue in section_review["issues"]
        ]

        audit_prompt = _compact_advanced_audit_prompt(
            review=review,
            section_reviews=section_reviews,
            context_lock=context_lock,
            paragraph_index=paragraph_index,
            audit_paragraphs=whole_audit,
            max_findings=config.advanced_audit_max_findings,
            max_source_chars=max(config.max_map_input_chars, 30000),
        )

        try:
            audit_hash = stable_hash({
                "pipeline": "academic-audit-v1.7.0",
                "model": config.deepseek_advanced_model,
                "effort": config.deepseek_advanced_reasoning_effort,
                "tokens": config.advanced_audit_max_output_tokens,
                "system_prompt": ACADEMIC_VERIFY_SYSTEM_PROMPT,
                "user_prompt": audit_prompt,
            })
            audit_stage_key = f"academic-audit-{audit_hash[:20]}"
            result = (
                checkpoint_manager.load_provider_result(
                    audit_stage_key,
                    expected_input_hash=audit_hash,
                )
                if checkpoint_manager is not None
                else None
            )
            if result is None:
                if checkpoint_manager is not None:
                    checkpoint_manager.mark_running(
                        audit_stage_key,
                        input_hash=audit_hash,
                        progress=68,
                        message="Conducting the doctoral quality audit",
                    )
                result = await deepseek.complete_json(
                    model=config.deepseek_advanced_model,
                    system_prompt=ACADEMIC_VERIFY_SYSTEM_PROMPT,
                    user_prompt=audit_prompt,
                    schema_model=AcademicVerificationBatch,
                    purpose="advanced_compact_doctoral_audit",
                    reasoning_effort=config.deepseek_advanced_reasoning_effort,
                    max_output_tokens=config.advanced_audit_max_output_tokens,
                )
                if checkpoint_manager is not None:
                    checkpoint_manager.save_provider_result(
                        audit_stage_key,
                        result,
                        input_hash=audit_hash,
                        progress=76,
                        message="Doctoral quality audit completed",
                    )
            usage_records.append(_usage_cost(result.usage, config))
            merged = _apply_verification(all_primary, result.data)

            merged_by_section: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            for item in merged:
                valid = _valid_issue(item, paragraph_index, context_lock)
                if valid:
                    merged_by_section[
                        normalised(valid.get("section", ""))
                    ].append(valid)

            for section_review in section_reviews:
                key = normalised(section_review["heading"])
                section_review["issues"] = merged_by_section.pop(
                    key,
                    section_review["issues"],
                )

            leftovers = [
                item
                for values in merged_by_section.values()
                for item in values
            ]
            if leftovers and section_reviews:
                section_reviews[0]["issues"].extend(leftovers)

        except Exception:
            verification_failed = True
            for section_review in section_reviews:
                section_review["coverage_warning"] = (
                    section_review.get("coverage_warning", "")
                    + " The compact doctoral audit was unavailable; the primary "
                      "advanced review remains available."
                ).strip()

    all_issues = _consolidate_repetitive_issues(
        _deduplicate_issues(issue for section_review in section_reviews for issue in section_review["issues"])
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
    finding_rows = [_finding_row(issue, paragraph_index) for issue in all_issues]
    incomplete = verification_failed or len(section_reviews) < len(sections)
    score = _academic_score(section_reviews, all_issues)
    readiness_label, readiness_meaning = (
        _light_readiness(score, all_issues) if depth == "light" else _readiness(score, all_issues, incomplete)
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
    actual_section_names = {
        normalised(section.get("heading", ""))
        for section in section_reviews
        if normalised(section.get("heading", ""))
        and not any(term in normalised(section.get("heading", "")) for term in (
            "whole chapter coherence", "cross chapter coherence", "cross chapter alignment", "supervisor comment compliance audit"
        ))
    }
    summary.update({
        "review_depth": depth, "review_benchmark": profile["benchmark"],
        "academic_review_score": score, "overall_score": overall,
        "readiness_label": readiness_label, "readiness_meaning": readiness_meaning,
        "academic_review_complete": not incomplete,
        "academic_sections_reviewed": len(actual_section_names),
        "academic_review_units_completed": len(section_reviews),
        "critical_issues": counts["critical"], "major_issues": counts["major"],
        "moderate_issues": counts["moderate"], "minor_issues": counts["minor"],
        "strengths_identified": len(strengths),
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
            + "Every detected section and subsection was assessed at the foundational standard expected of a Bachelor’s dissertation or non-research Master’s project. "
            + "The review provides context-aware guidance and examples where these are needed to support revision."
        ).strip()
    review["priority_actions"] = priority
    review["ai_review"] = {
        "review_depth": depth, "review_benchmark": profile["benchmark"],
        "usage": [record.model_dump() for record in usage_records],
        "estimated_cost_usd": round(sum(record.estimated_cost_usd for record in usage_records), 6),
        "academic_review_complete": not incomplete,
        "active_provider": "deepseek",
        "advanced_second_pass": bool(depth == "advanced" and config.advanced_quality_control),
        "advanced_audit_mode": "single_compact_audit" if depth == "advanced" else "not_applicable",
        "api_call_count": len(usage_records),
        "primary_batch_count": len(section_batches),
        "context_guard_enabled": True,
    }
    await _notify(progress_callback, 86, "Preparing the annotated review")
    return review
