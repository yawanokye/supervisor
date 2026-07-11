from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Sequence


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _clean(value).lower()).strip()


def _env_enabled(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


SUPERVISORY_SYSTEM_COMMAND = """
Act as an experienced thesis supervisor and, for complete theses, as an examiner. Review the study systematically rather than sampling a few passages. Use clear, natural language that a student can understand. Do not impose a fixed number of comments. Review every substantive paragraph, table, figure and model, but add a visible comment only when correction, clarification, source verification or re-analysis is required.

For each issue:
1. identify the exact sentence, paragraph, table or figure;
2. state plainly what is wrong or unclear;
3. explain why it matters for the study and at the actual academic level;
4. state the precise correction required;
5. add a brief example only when it will help the student, and make the example specific to the current study.

Use “the study”, “the work”, “the chapter”, or the actual section name. Never use “uploaded document”, “uploaded text”, “automated review”, “document manifest”, or checklist-style wording. Do not praise routine content. Do not invent sources, data, statistics, methods or results. Separate what can be verified from the printed study from what requires raw data or original software output.
""".strip()


SECTION_REVIEW_COMMAND = """
Review each target in relation to the complete study map. Check clarity, scholarly tone, citation support, definitions, logic, evidence, theory, variables, alignment with objectives and consistency with preceding and subsequent chapters. For every target, record one status: PASS, COMMENT, VERIFY SOURCE or RE-ANALYSE. Return no comment for PASS. A comment must be anchored to the exact target and must be written for the student, not for the software.
""".strip()


STATISTICAL_AUDIT_COMMAND = """
For every statistical table or analytical model, extract the reported N, number of predictors, coefficients, standard errors, beta values, test statistics, p-values, confidence intervals, R, R-squared, adjusted R-squared, change in R-squared, F, F-change, degrees of freedom, effect sizes and diagnostics where present. Recalculate deterministic identities, compare the method promised in the methods chapter with the statistic actually reported, check that model hierarchy is complete, and compare each interpretation with the printed statistic. Mark a result RE-ANALYSE when printed values cannot come from one model or when the analysis is inappropriate. Do not alter a coefficient without the original output. State the exact re-analysis or verification required.
""".strip()


FINAL_SYNTHESIS_COMMAND = """
Create the final supervisory or examiner report only from the completed coverage ledger and verified findings. State the scope and limitations, overall decision, strengths, critical barriers to validity, statistical consistency findings, chapter-specific correction plan, evidence the student must provide and the order of revision. Do not state that the work is ready while a critical statistical, measurement or alignment issue remains unresolved.
""".strip()


ALGORITHM_STAGES = (
    "Document ingestion and preservation",
    "Structural mapping",
    "Coverage ledger",
    "Within-section review",
    "Cross-section alignment",
    "Measurement audit",
    "Statistical audit",
    "Reference audit",
    "Comment generation",
    "Quality assurance",
)


def algorithm_contract() -> Dict[str, Any]:
    return {
        "mode": "coverage_driven_professional_supervision",
        "predetermined_comment_count": False,
        "allowed_target_statuses": ["PASS", "COMMENT", "VERIFY SOURCE", "RE-ANALYSE"],
        "stages": list(ALGORITHM_STAGES),
        "system_command": SUPERVISORY_SYSTEM_COMMAND,
        "section_review_command": SECTION_REVIEW_COMMAND,
        "statistical_audit_command": STATISTICAL_AUDIT_COMMAND,
        "final_synthesis_command": FINAL_SYNTHESIS_COMMAND,
        "comment_structure": [
            "plain statement of the specific issue",
            "why the issue matters",
            "precise correction required",
            "current-study example when useful",
        ],
    }


def issue_status(issue: Mapping[str, Any]) -> str:
    text = _norm(" ".join(_clean(issue.get(key)) for key in (
        "category", "issue_title", "item", "assessment", "comment",
        "academic_consequence", "required_action", "verification_status",
    )))
    category = _norm(issue.get("category"))
    verification = _norm(issue.get("verification_status"))
    if any(term in text for term in (
        "re run", "rerun", "re analyse", "reanalyse", "recompute", "recalculate",
        "cannot all be correct", "cannot come from the same model", "model is not valid",
        "inappropriate analysis", "wrong analysis", "full model", "original software output",
    )) or verification in {"verified inconsistency", "inappropriate analysis or interpretation"}:
        return "RE-ANALYSE"
    if bool(issue.get("source_verification_required")) or category in {
        "citations and sources", "reference integrity"
    } or any(term in text for term in (
        "verify source", "source cannot be verified", "reference list", "citation",
        "official source", "traceable source", "verify the claim",
    )):
        return "VERIFY SOURCE"
    return "COMMENT"


def status_priority(status: str) -> int:
    return {"PASS": 0, "COMMENT": 1, "VERIFY SOURCE": 2, "RE-ANALYSE": 3}.get(status, 1)


def merge_status(existing: str, incoming: str) -> str:
    return incoming if status_priority(incoming) > status_priority(existing) else existing


def coverage_statuses_for_review(review: Mapping[str, Any], target_ids: Sequence[str]) -> Dict[str, str]:
    statuses = {str(pid): "PASS" for pid in target_ids}
    for issue in review.get("issues") or []:
        status = issue_status(issue)
        for pid in issue.get("evidence_paragraph_ids") or []:
            key = str(pid)
            if key in statuses:
                statuses[key] = merge_status(statuses[key], status)
    return statuses


def _area_for_finding(row: Mapping[str, Any]) -> str:
    category = _norm(row.get("category"))
    text = _norm(" ".join(_clean(row.get(key)) for key in (
        "issue", "assessment", "required_correction", "section", "verification"
    )))
    if category in {"statistical accuracy", "analysis appropriateness", "results and interpretation"} or any(
        term in text for term in ("r squared", "f statistic", "regression", "moderation", "mediation", "coefficient", "statistical")
    ):
        return "Analysis validity"
    if category in {"measurement and scoring", "methodological rigour"} or any(
        term in text for term in ("item allocation", "scale", "response anchor", "reverse scor", "reliability", "validity", "composite")
    ):
        return "Measurement and methods"
    if category in {"reference integrity", "citations and sources"} or any(
        term in text for term in ("reference list", "citation", "verify source")
    ):
        return "Reference integrity"
    if category in {"document completeness", "chapter structure"} or any(
        term in text for term in ("missing chapter", "missing section", "chapter five", "limitations section")
    ):
        return "Completeness and structure"
    if any(term in text for term in ("causal", "influence", "effect", "association", "prediction")):
        return "Interpretation and causal language"
    if category == "cross section coherence":
        return "Cross-chapter alignment"
    return "Scholarly quality and alignment"


def _statistical_rows(review: Mapping[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for warning in (review.get("statistical_review") or {}).get("consistency_warnings") or []:
        evidence = warning.get("evidence") or {}
        location = _clean(evidence.get("table_title") or evidence.get("section_reference") or evidence.get("heading") or "Results")
        table_number = _clean(evidence.get("table_number"))
        if table_number:
            location = f"Table {table_number}" + (f": {location}" if location else "")
        rows.append({
            "check": location or "Statistical result",
            "finding": _clean(warning.get("message")),
            "status": _clean(warning.get("verification") or "reporting omission").title(),
            "action": _clean(warning.get("required_action")) or "Verify the result against the original software output and correct the table, narrative and conclusion together.",
            "reported_evidence": _clean(evidence.get("text"))[:320],
        })
    return rows


def _chapter_label(number: Any) -> str:
    names = {
        1: "Chapter One",
        2: "Chapter Two",
        3: "Chapter Three",
        4: "Chapter Four",
        5: "Chapter Five",
    }
    try:
        n = int(number)
    except (TypeError, ValueError):
        return "Whole study"
    return names.get(n, f"Chapter {n}")


def _chapter_plans(ledger: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[Any, List[Mapping[str, Any]]] = defaultdict(list)
    for row in ledger:
        grouped[row.get("chapter_number")].append(row)
    plans: List[Dict[str, Any]] = []
    for chapter in sorted(grouped, key=lambda value: (99 if value is None else int(value))):
        rows = sorted(
            grouped[chapter],
            key=lambda item: ({"critical": 0, "major": 1, "moderate": 2, "minor": 3}.get(_clean(item.get("severity")).lower(), 9), int(item.get("number") or 9999)),
        )
        corrections: List[str] = []
        for row in rows:
            action = _clean(row.get("required_correction") or row.get("assessment") or row.get("issue"))
            if action and _norm(action) not in {_norm(value) for value in corrections}:
                corrections.append(action)
            if len(corrections) >= 8:
                break
        plans.append({
            "chapter_number": chapter,
            "chapter": _chapter_label(chapter),
            "corrections": corrections,
            "finding_numbers": [int(row.get("number")) for row in rows if row.get("number")],
        })
    return plans


def build_supervisory_report_spec(review: Mapping[str, Any], professional_package: Mapping[str, Any]) -> Dict[str, Any]:
    summary = review.get("summary") or {}
    ledger = list(professional_package.get("finding_ledger") or [])
    recommendation = professional_package.get("recommendation") or {}
    strengths = [
        _clean(item.get("observation"))
        for item in review.get("academic_strengths") or []
        if _clean(item.get("observation"))
    ]
    critical_rows = [row for row in ledger if _clean(row.get("severity")).lower() in {"critical", "major"}]
    grouped: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for row in critical_rows:
        grouped[_area_for_finding(row)].append(row)
    critical_corrections: List[Dict[str, Any]] = []
    for area, rows in grouped.items():
        rows = sorted(rows, key=lambda item: ({"critical": 0, "major": 1}.get(_clean(item.get("severity")).lower(), 9), int(item.get("number") or 9999)))
        actions: List[str] = []
        for row in rows:
            action = _clean(row.get("required_correction") or row.get("assessment"))
            if action and _norm(action) not in {_norm(value) for value in actions}:
                actions.append(action)
            if len(actions) >= 3:
                break
        critical_corrections.append({
            "area": area,
            "required_correction": " ".join(actions),
            "finding_numbers": [int(row.get("number")) for row in rows if row.get("number")][:8],
        })

    chapters = sorted({row.get("chapter_number") for row in ledger if row.get("chapter_number") is not None})
    chapter_text = ", ".join(_chapter_label(value) for value in chapters) or "the submitted study"
    raw_output_available = bool(summary.get("raw_data_supplied") or summary.get("statistical_output_supplied") or summary.get("analysis_output_supplied"))
    limitation = (
        f"The review covered {chapter_text}, the reported tables and figures, cross-chapter alignment, measurement, analysis, discussion, references and presentation. "
        "The numerical audit checked internal consistency among values printed in the study. "
    )
    if raw_output_available:
        limitation += "Original analytical output was supplied for the checks identified in the report."
    else:
        limitation += "Raw data and original software output were not supplied, so the review cannot certify that the reported coefficients were generated from the underlying data. Any result marked for verification or re-analysis must be reproduced from the original data and software output."

    scope = _clean((professional_package.get("profile") or {}).get("scope"))
    role = _clean((professional_package.get("profile") or {}).get("role"))
    return {
        "report_title": "PROFESSIONAL THESIS EXAMINER’S REPORT" if scope == "full_thesis" else "SUPERVISORY REVIEW REPORT",
        "review_mode": role or "Professional academic supervisor",
        "overall_decision": _clean(recommendation.get("decision") or summary.get("readiness_label") or "Review completed"),
        "scope_and_limitation": limitation,
        "overall_assessment": _clean(review.get("overall_academic_assessment") or review.get("overall_assessment") or summary.get("readiness_meaning") or recommendation.get("meaning")),
        "strengths": strengths[:10],
        "critical_corrections": critical_corrections,
        "statistical_audit": _statistical_rows(review),
        "chapter_plans": _chapter_plans(ledger),
        "evidence_required": list((professional_package.get("methods_results_discussion_audit") or {}).get("evidence_required") or []),
        "coverage": review.get("coverage_ledger") or {},
        "finding_count": len(ledger),
        "algorithm": algorithm_contract(),
    }
