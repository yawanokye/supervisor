from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping

from .comment_quality import public_text, sentence_safe_trim


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _trim(value: Any, limit: int = 520) -> str:
    return sentence_safe_trim(public_text(_clean(value), reject_placeholders=True), limit)


def _location(row: Mapping[str, Any]) -> str:
    evidence = row.get("evidence") or []
    if evidence:
        item = evidence[0]
        bits: List[str] = []
        section = _clean(item.get("section_reference") or item.get("heading") or row.get("section"))
        if section:
            bits.append(section)
        if item.get("table_number"):
            bits.append(f"Table {item.get('table_number')}" + (f", row {item.get('table_row')}" if item.get("table_row") else ""))
        elif item.get("paragraph") is not None:
            bits.append(f"paragraph {item.get('paragraph')}")
        if item.get("page") is not None:
            bits.append(f"page {item.get('page')}")
        if bits:
            return ", ".join(bits)
    return _clean(row.get("section_reference") or row.get("section") or "Selected review scope")


def _priority(severity: str) -> str:
    value = _clean(severity).lower()
    if value in {"critical", "major"}:
        return "Essential before approval"
    if value == "moderate":
        return "Strongly recommended"
    return "Optional refinement"


def _verification(row: Mapping[str, Any]) -> str:
    category = _clean(row.get("category")).lower()
    if category in {"statistical_accuracy", "analysis_appropriateness", "measurement_and_scoring"}:
        return "Verify against the original dataset, statistical output, syntax or model report and update the table and interpretation together."
    if row.get("source_verification_required"):
        return "Check the claim against the original source and ensure the in-text citation and reference entry agree."
    return "Re-read the revised passage with the relevant objective, method and evidence to confirm that the correction is complete."


def _is_analysis_action(row: Mapping[str, Any]) -> bool:
    category = _clean(row.get("category")).lower()
    text = _clean(" ".join(str(row.get(key) or "") for key in (
        "issue_title", "item", "assessment", "comment", "required_action"
    ))).lower()
    return category in {
        "statistical_accuracy",
        "statistical_reporting_accuracy",
        "analysis_appropriateness",
        "measurement_and_scoring",
        "methods_results_alignment",
        "results_and_interpretation",
    } or any(term in text for term in (
        "re-run", "reanaly", "re-analy", "robustness", "diagnostic", "coefficient",
        "p-value", "confidence interval", "effect size", "model fit", "recalculate",
        "mediation", "moderation", "regression", "anova", "sem", "gmm", "ardl",
    ))


def _analysis_requirement(row: Mapping[str, Any], number: int) -> Dict[str, Any]:
    action = _trim(row.get("required_action") or row.get("comment") or row.get("assessment"), 620)
    consequence = _trim(
        row.get("academic_consequence")
        or "The present result or claim cannot be treated as adequately supported until this check is completed.",
        420,
    )
    return {
        "number": number,
        "priority": _priority(row.get("severity") or "moderate"),
        "location": _location(row),
        "rationale": _trim(row.get("issue_title") or row.get("item") or row.get("assessment"), 360),
        "data_required": (
            "Use the original dataset or source data, variable definitions or codebook, analysis syntax and the complete software output. "
            "Where the finding concerns a table transcription only, the original output and manuscript table are sufficient."
        ),
        "suitable_method": (
            action
            or "Repeat the analysis exactly as specified in the methodology, apply the diagnostics appropriate to that method and document any justified correction."
        ),
        "output_to_report": (
            "Report the corrected or additional table, relevant estimates or qualitative evidence, required diagnostics, uncertainty measures, "
            "decision rule and a revised interpretation that agrees with the output."
        ),
        "consequence_of_omission": consequence,
    }


def build_supervisory_readiness(review: Dict[str, Any]) -> Dict[str, Any]:
    rows = [
        row for row in (review.get("canonical_findings") or review.get("academic_findings") or [])
        if row.get("status") not in {"meets_requirement", "not_applicable"}
    ]
    severity_rank = {"critical": 0, "major": 1, "moderate": 2, "minor": 3}
    rows.sort(key=lambda row: (severity_rank.get(_clean(row.get("severity")).lower(), 9), int(row.get("finding_number") or 9999)))
    actions: List[Dict[str, Any]] = []
    analysis_actions: List[Dict[str, Any]] = []
    seen = set()
    for index, row in enumerate(rows, start=1):
        action = _trim(row.get("required_action") or row.get("comment") or row.get("assessment"), 620)
        issue = _trim(row.get("issue_title") or row.get("item") or row.get("assessment"), 320)
        if not action:
            continue
        signature = (_clean(_location(row)).lower(), action.lower())
        if signature in seen:
            continue
        seen.add(signature)
        actions.append({
            "number": int(row.get("finding_number") or index),
            "priority": _priority(row.get("severity") or "moderate"),
            "severity": _clean(row.get("severity") or "moderate"),
            "location": _location(row),
            "text_requiring_attention": _trim(row.get("exact_source_text") or row.get("problematic_quote"), 360),
            "issue": issue,
            "specific_action": action,
            "why_it_matters": _trim(row.get("academic_consequence") or row.get("comment") or row.get("assessment"), 440),
            "verification": _trim(row.get("verification_test") or _verification(row), 440),
        })
        if _is_analysis_action(row):
            analysis_actions.append(_analysis_requirement(row, int(row.get("finding_number") or index)))

    critical = sum(1 for item in actions if item["severity"].lower() == "critical")
    major = sum(1 for item in actions if item["severity"].lower() == "major")
    moderate = sum(1 for item in actions if item["severity"].lower() == "moderate")
    if critical or major:
        status = "Not ready for supervisor approval"
        meaning = "Essential scholarly or analytical corrections remain. Complete and verify them before the work is treated as ready for approval or submission."
    elif moderate:
        status = "Ready only after targeted corrections"
        meaning = "No critical blocker is visible, but the identified corrections should be completed and checked before approval."
    elif actions:
        status = "Ready for supervisor confirmation after minor refinement"
        meaning = "Only limited refinements remain. The supervisor should confirm the final version before submission."
    else:
        status = "No material correction identified in the selected scope"
        meaning = "The selected scope contains no unresolved material finding in this review. This is not a guarantee of institutional or examination approval."

    stats = review.get("statistical_review") or {}
    warnings = list(stats.get("consistency_warnings") or [])
    verified = int(stats.get("verified_inconsistency_count") or 0)
    omissions = int(stats.get("reporting_omission_count") or 0)
    statistical = {
        "accuracy_status": "Material accuracy issue identified" if verified else "No verified arithmetic or internal-consistency error detected",
        "adequacy_status": "Additional reporting or analysis is required" if omissions or any(w.get("verification") in {"reporting omission", "likely inconsistency"} for w in warnings) else "No material adequacy omission detected by the document-level audit",
        "verified_inconsistencies": verified,
        "reporting_or_adequacy_issues": omissions + sum(1 for w in warnings if w.get("verification") == "likely inconsistency"),
        "limitation": "Accuracy is checked from the submitted tables and narrative. Definitive verification still requires the original dataset, syntax and software output.",
    }
    scope = (review.get("summary") or {}).get("selected_section_scope") or {}
    return {
        "status": status,
        "meaning": meaning,
        "scope_label": "Selected sections" if scope.get("mode") == "selected_sections" else _clean((review.get("summary") or {}).get("document_label") or "Reviewed work"),
        "counts": {"critical": critical, "major": major, "moderate": moderate, "minor": sum(1 for item in actions if item["severity"].lower() == "minor")},
        "actions": actions,
        "additional_analysis_actions": analysis_actions,
        "statistical_assurance": statistical,
        "approval_note": "The report identifies actions required before supervisor approval. It does not guarantee acceptance, examination success or institutional clearance.",
    }


def attach_supervisory_readiness(review: Dict[str, Any]) -> Dict[str, Any]:
    package = build_supervisory_readiness(review)
    review["supervisory_readiness"] = package
    summary = review.setdefault("summary", {})
    summary["supervisory_readiness_status"] = package["status"]
    summary["supervisory_readiness_meaning"] = package["meaning"]
    return review
