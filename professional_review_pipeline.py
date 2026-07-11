from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from .finding_order import chapter_number as ordered_chapter_number, document_order_key, order_and_number_rows
from .reviewer_language import academic_level_label, professionalise_reviewer_language


SEVERITY_ORDER = {"critical": 0, "major": 1, "moderate": 2, "minor": 3}
CHAPTER_NAMES = {
    1: "Chapter One",
    2: "Chapter Two",
    3: "Chapter Three",
    4: "Chapter Four",
    5: "Chapter Five",
}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", _clean(value).lower()).strip()


def _legacy_chapter_number(row: Dict[str, Any]) -> int | None:
    value = row.get("chapter_number")
    try:
        if value is not None:
            return int(value)
    except (TypeError, ValueError):
        pass
    for evidence in row.get("evidence") or []:
        try:
            if evidence.get("chapter_number") is not None:
                return int(evidence.get("chapter_number"))
        except (TypeError, ValueError):
            continue
    section = _norm(row.get("section_reference") or row.get("section"))
    match = re.search(r"\bchapter\s+(\d+)\b", section)
    if match:
        return int(match.group(1))
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
    for word, number in words.items():
        if f"chapter {word}" in section:
            return number
    return None


def _chapter_number(row: Dict[str, Any]) -> int | None:
    return ordered_chapter_number(row) or _legacy_chapter_number(row)


def _evidence_location(row: Dict[str, Any]) -> str:
    evidence = row.get("evidence") or []
    if not evidence:
        return _clean(row.get("section_reference") or row.get("section") or "Unanchored chapter-level finding")
    best = evidence[0]
    parts: List[str] = []
    section = _clean(best.get("section_reference") or best.get("heading") or row.get("section_reference") or row.get("section"))
    if section:
        parts.append(section)
    if best.get("table_number"):
        label = f"Table {_clean(best.get('table_number'))}"
        title = _clean(best.get("table_title"))
        if title:
            label += f": {title}"
        if best.get("table_row") is not None:
            label += f", row {best.get('table_row')}"
        parts.append(label)
    elif best.get("paragraph") is not None:
        parts.append(f"paragraph {best.get('paragraph')}")
    if best.get("page") is not None:
        parts.append(f"page {best.get('page')}")
    return ", ".join(dict.fromkeys(parts))


def _scope_key(summary: Dict[str, Any]) -> str:
    scope = _norm(summary.get("review_scope"))
    if scope == "full thesis" or summary.get("review_scope") == "full_thesis":
        return "full_thesis"
    if scope in {"chapter range", "combined chapters"} or summary.get("review_scope") == "chapter_range":
        return "chapter_range"
    return "chapter"


def professional_scope_profile(summary: Dict[str, Any]) -> Dict[str, Any]:
    scope = _scope_key(summary)
    level = academic_level_label(summary.get("academic_level"))
    level_phrase = f"At {level}" if level != "the applicable academic level" else "At the applicable academic level"
    if scope == "full_thesis":
        return {
            "scope": scope,
            "role": "Professional thesis examiner",
            "report_title": "PROFESSIONAL THESIS EXAMINER’S REPORT",
            "judgement_unit": "the complete thesis",
            "primary_task": (
                "Evaluate the thesis as an integrated scholarly argument, determine whether the evidence supports the claims, "
                "verify chapter-to-chapter alignment, assess originality and contribution, and state a defensible examination recommendation."
            ),
            "required_outputs": [
                "overall examination judgement",
                "critical submission blockers",
                "chapter-by-chapter judgements",
                "objective-to-conclusion alignment audit",
                "methods quality audit",
                "results and statistical or analytical accuracy audit",
                "discussion and contribution audit",
                "prioritised correction plan",
                "evidence required for verification",
                "final examiner recommendation",
            ],
        }
    if scope == "chapter_range":
        return {
            "scope": scope,
            "role": "Senior supervisor and cross-chapter reviewer",
            "report_title": "PROFESSIONAL COMBINED-CHAPTER REVIEW",
            "judgement_unit": "each submitted chapter and the links between them",
            "primary_task": (
                "Review every submitted chapter independently, then test sequential alignment across the range. "
                "Do not treat earlier chapters as context-only when they form part of the requested review."
            ),
            "required_outputs": [
                "overall combined-chapter judgement",
                "chapter-specific strengths and weaknesses",
                "cross-chapter alignment findings",
                "methods or analysis audit where those chapters are present",
                "prioritised corrections by chapter",
                "readiness for the next thesis stage",
            ],
        }
    return {
        "scope": scope,
        "role": "Professional chapter supervisor",
        "report_title": "PROFESSIONAL CHAPTER REVIEW",
        "judgement_unit": "the selected chapter",
        "primary_task": (
            f"Review every section and subsection of the chapter under review. {level_phrase}, apply the depth, rigour and scholarly independence expected. "
            "Use other supplied chapters only to test alignment and do not issue unsupported whole-thesis judgements."
        ),
        "required_outputs": [
            "chapter-level judgement",
            "section-by-section strengths and corrections",
            "alignment findings relevant to the chapter",
            "method or analysis audit when the selected chapter requires it",
            "prioritised revision plan",
            "chapter readiness judgement",
        ],
    }


def specialist_role_for_chapter(chapter_number: Any, heading: str = "") -> str:
    try:
        chapter = int(chapter_number) if chapter_number is not None else None
    except (TypeError, ValueError):
        chapter = None
    heading_norm = _norm(heading)
    if chapter == 1 or any(term in heading_norm for term in ("problem statement", "research objective", "introduction")):
        return "Research problem, framing and alignment specialist"
    if chapter == 2 or any(term in heading_norm for term in ("literature review", "theoretical framework", "empirical review")):
        return "Theory, evidence synthesis and research-gap specialist"
    if chapter == 3 or any(term in heading_norm for term in ("methodology", "research methods", "sampling", "instrument")):
        return "Research design, measurement, ethics and reproducibility specialist"
    if chapter == 4 or any(term in heading_norm for term in ("results", "findings", "discussion", "analysis")):
        return "Results, statistical or qualitative analysis, and interpretation specialist"
    if chapter == 5 or any(term in heading_norm for term in ("conclusion", "recommendation", "summary of findings")):
        return "Synthesis, contribution, conclusion and recommendation specialist"
    return "Discipline-sensitive thesis reviewer"


def professional_scope_contract(summary: Dict[str, Any]) -> str:
    profile = professional_scope_profile(summary)
    scope = profile["scope"]
    shared = (
        "Act as a professional academic reviewer. Separate verified defects from matters that cannot be confirmed without original data or software output. "
        "For every material finding state the exact location, the problem, why it matters at the actual academic level, the required correction, and a current-study example only when it is genuinely helpful. "
        "Use one canonical finding for the report, native Word comment, inline annotation and correction tracker. Do not create comments to meet a numerical quota. "
        "Prioritise validity, alignment, analytical accuracy and contribution above proofreading."
    )
    if scope == "full_thesis":
        return shared + (
            " Review every chapter as a specialist examiner and then conduct a whole-thesis synthesis. Trace each objective or hypothesis through theory, method, result, discussion, conclusion and recommendation. "
            "Audit every reported analytical model or qualitative theme. Reconcile statistics where the manuscript provides enough information, classify uncertainty honestly, identify evidence needed from the candidate, and provide an examination recommendation proportionate to the unresolved defects."
        )
    if scope == "chapter_range":
        return shared + (
            " Review every chapter in the submitted range, not only the final chapter. Produce a separate judgement for each chapter and a cross-chapter alignment judgement. "
            "Where methods or results are present, audit them using only the analytical route actually used. Identify contradictions in constructs, samples, methods, terminology, tables or claims across chapters."
        )
    return shared + (
        " Review every section and subsection of the chapter under review. Keep the judgement bounded to that chapter, while using preceding chapters only to identify alignment defects that directly affect the selected chapter. "
        "Do not infer that the complete thesis is ready or unready from one chapter alone."
    )


def _requires_original_output(row: Dict[str, Any]) -> bool:
    text = _norm(" ".join(
        _clean(row.get(key))
        for key in ("item", "comment", "required_action", "illustrative_guidance", "category")
    ))
    return any(term in text for term in (
        "original output", "raw data", "software output", "spss", "stata", "r output", "process output",
        "recompute", "recalculate", "diagnostic output", "bootstrap", "residual plot", "model output",
        "cannot be verified", "not verifiable", "confidence interval", "standard error", "degrees of freedom",
    ))


def _verification_label(row: Dict[str, Any]) -> str:
    status = _norm(row.get("verification_status"))
    if status in {"independent ai audit", "focused ai audit"}:
        return "Evidence-checked finding"
    if _requires_original_output(row):
        return "Requires original analytical output"
    if row.get("manual_confirmation_required"):
        return "Requires supervisor confirmation"
    if not row.get("evidence"):
        return "Chapter-level structural finding"
    return "Evidence-anchored finding"


def _anchor_sort(row: Dict[str, Any]) -> Tuple[int, int, int, str]:
    chapter = _chapter_number(row) or 99
    evidence = row.get("evidence") or []
    paragraph = 999999
    table_row = 999999
    if evidence:
        best = evidence[0]
        try:
            paragraph = int(best.get("paragraph") or 999999)
        except (TypeError, ValueError):
            pass
        try:
            table_row = int(best.get("table_row") or 999999)
        except (TypeError, ValueError):
            pass
    return chapter, paragraph, table_row, _norm(row.get("item"))


def build_finding_ledger(review: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build one evidence-led ledger in the same order as the work.

    Numbering follows chapter and passage order, not severity or model-return
    order. Alignment and revision findings are included when actionable so the
    report, native comments and inline annotations can share the same sequence.
    """
    rows: List[Dict[str, Any]] = []
    for source_key in ("academic_findings", "alignment_results", "revision_results"):
        for row in review.get(source_key) or []:
            status = str(row.get("status") or "").strip().lower()
            if status in {"meets_requirement", "not_applicable", "addressed"}:
                continue
            if not any(_clean(row.get(field)) for field in ("item", "issue_title", "comment", "assessment", "required_action")):
                continue
            row.setdefault("finding_source", source_key)
            rows.append(row)

    # Deduplicate only exact finding/location pairs. Similar but distinct
    # analytical issues must remain separate.
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for row in rows:
        best = (row.get("evidence") or [{}])[0]
        signature = (
            _clean(row.get("finding_id")),
            _norm(row.get("item") or row.get("issue_title") or row.get("comment")),
            best.get("paragraph"), best.get("table_index"), best.get("table_row"),
        )
        if signature in seen:
            continue
        seen.add(signature)
        deduped.append(row)

    rows = order_and_number_rows(deduped)
    level = academic_level_label((review.get("summary") or {}).get("academic_level"))
    ledger: List[Dict[str, Any]] = []
    for row in rows:
        number = int(row.get("finding_number"))
        chapter = _chapter_number(row)
        evidence = row.get("evidence") or []
        assessment = professionalise_reviewer_language(_clean(row.get("comment") or row.get("assessment")), level)
        correction = professionalise_reviewer_language(_clean(row.get("required_action")), level)
        example = professionalise_reviewer_language(_clean(row.get("illustrative_guidance")), level)
        ledger.append({
            "number": number,
            "finding_id": _clean(row.get("finding_id")) or f"PF-{number:03d}",
            "chapter_number": chapter,
            "chapter": CHAPTER_NAMES.get(chapter, f"Chapter {chapter}" if chapter else "Cross-thesis review"),
            "section": _clean(row.get("section_reference") or row.get("section") or "Chapter-level review"),
            "location": _evidence_location(row),
            "problematic_quote": _clean(row.get("problematic_quote")),
            "category": _clean(row.get("category") or "other"),
            "severity": _clean(row.get("severity") or "moderate").lower(),
            "confidence": float(row.get("confidence") or 0.0),
            "verification": _verification_label(row),
            "issue": professionalise_reviewer_language(_clean(row.get("item") or row.get("issue_title") or "Academic correction required"), level),
            "assessment": assessment,
            "required_correction": correction,
            "example": example,
            "requires_original_output": _requires_original_output(row),
            "evidence_count": len(evidence),
            "finding_source": row.get("finding_source"),
        })
    return ledger


def _chapter_score(review: Dict[str, Any], chapter: int) -> float | None:
    scores = []
    for section in review.get("academic_section_reviews") or []:
        try:
            section_chapter = int(section.get("chapter_number")) if section.get("chapter_number") is not None else None
        except (TypeError, ValueError):
            section_chapter = None
        if section_chapter != chapter:
            continue
        try:
            scores.append(float(section.get("section_score")))
        except (TypeError, ValueError):
            continue
    return round(sum(scores) / len(scores), 1) if scores else None


def _chapter_decision(counts: Counter, score: float | None, level_label: str = "the applicable academic level") -> str:
    if counts.get("critical", 0):
        return "Fundamental revision required"
    if counts.get("major", 0) >= 3:
        return "Major revision required"
    if counts.get("major", 0):
        return "Substantive revision required"
    if counts.get("moderate", 0):
        return "Targeted revision required"
    if score is not None and score < 70:
        return "Further development required"
    return f"Broadly satisfactory at {level_label}"


def build_chapter_judgements(review: Dict[str, Any], ledger: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    summary = review.get("summary") or {}
    chapters = set()
    for value in summary.get("current_chapters_detected") or []:
        try:
            chapters.add(int(value))
        except (TypeError, ValueError):
            pass
    for row in ledger:
        if row.get("chapter_number"):
            chapters.add(int(row["chapter_number"]))
    if not chapters and summary.get("selected_chapter"):
        try:
            chapters.add(int(summary.get("selected_chapter")))
        except (TypeError, ValueError):
            pass

    strengths_by_chapter: Dict[int, List[str]] = defaultdict(list)
    for strength in review.get("academic_strengths") or []:
        chapter = _chapter_number(strength)
        if chapter:
            text = _clean(strength.get("observation"))
            if text and text not in strengths_by_chapter[chapter]:
                strengths_by_chapter[chapter].append(text)

    level_label = academic_level_label(summary.get("academic_level"))
    output: List[Dict[str, Any]] = []
    for chapter in sorted(chapters):
        chapter_rows = [row for row in ledger if row.get("chapter_number") == chapter]
        counts = Counter(row.get("severity") for row in chapter_rows)
        score = _chapter_score(review, chapter)
        output.append({
            "chapter_number": chapter,
            "chapter": CHAPTER_NAMES.get(chapter, f"Chapter {chapter}"),
            "specialist_role": specialist_role_for_chapter(chapter),
            "score": score,
            "decision": _chapter_decision(counts, score, level_label),
            "severity_counts": dict(counts),
            "strengths": strengths_by_chapter.get(chapter, [])[:4],
            "priority_findings": chapter_rows[:8],
            "finding_numbers": [row["number"] for row in chapter_rows],
        })
    return output


def _is_methods_row(row: Dict[str, Any]) -> bool:
    text = _norm(" ".join((row.get("category", ""), row.get("section", ""), row.get("issue", ""))))
    return row.get("chapter_number") == 3 or any(term in text for term in (
        "method", "design", "sampling", "instrument", "validity", "reliability", "ethics", "trustworthiness", "data collection",
    ))


def _is_results_row(row: Dict[str, Any]) -> bool:
    text = _norm(" ".join((row.get("category", ""), row.get("section", ""), row.get("issue", ""), row.get("assessment", ""))))
    return row.get("chapter_number") == 4 or any(term in text for term in (
        "result", "analysis", "statistic", "coefficient", "p value", "table", "regression", "anova", "sem", "theme", "moderation", "mediation",
    ))


def _is_discussion_row(row: Dict[str, Any]) -> bool:
    text = _norm(" ".join((row.get("category", ""), row.get("section", ""), row.get("issue", ""))))
    return any(term in text for term in ("discussion", "interpretation", "theory", "prior studies", "implication", "unexpected finding"))


def build_methods_results_discussion_audit(ledger: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    methods = [row for row in ledger if _is_methods_row(row)]
    results = [row for row in ledger if _is_results_row(row)]
    discussion = [row for row in ledger if _is_discussion_row(row)]
    evidence_required = []
    for row in ledger:
        if row.get("requires_original_output"):
            evidence_required.append({
                "number": row["number"],
                "location": row["location"],
                "evidence_needed": (
                    "Provide the original data-analysis output, syntax or code, and the corresponding table used to report this result."
                ),
            })
    return {
        "methods_findings": methods,
        "results_accuracy_findings": results,
        "discussion_findings": discussion,
        "evidence_required": evidence_required,
        "accuracy_statement": (
            "The app checks internal consistency and reporting completeness. It does not claim independent recomputation unless raw data, code or original software output is supplied."
        ),
    }


def _cross_chapter_rows(review: Dict[str, Any], ledger: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for item in review.get("alignment_results") or []:
        if item.get("status") in {"meets_requirement", "not_applicable"}:
            continue
        rows.append({
            "source": "alignment engine",
            "section": _clean(item.get("section") or "Cross-chapter alignment"),
            "severity": _clean(item.get("severity") or "major"),
            "finding": _clean(item.get("comment") or item.get("item")),
            "required_correction": _clean(item.get("required_action")),
        })
    for item in ledger:
        if item.get("category") == "cross_section_coherence" or item.get("chapter_number") is None:
            rows.append({
                "source": "professional finding ledger",
                "number": item.get("number"),
                "section": item.get("section"),
                "severity": item.get("severity"),
                "finding": item.get("assessment") or item.get("issue"),
                "required_correction": item.get("required_correction"),
            })
    return rows


def _priority_plan(ledger: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    return {
        "priority_1_validity_and_submission_blockers": [row for row in ledger if row.get("severity") == "critical"],
        "priority_2_major_scholarly_revision": [row for row in ledger if row.get("severity") == "major"],
        "priority_3_targeted_and_editorial_revision": [row for row in ledger if row.get("severity") in {"moderate", "minor"}],
    }


def _overall_recommendation(scope: str, ledger: Sequence[Dict[str, Any]], summary: Dict[str, Any]) -> Dict[str, str]:
    counts = Counter(row.get("severity") for row in ledger)
    if counts.get("critical", 0):
        decision = "Fundamental revision required before approval"
    elif counts.get("major", 0) >= 5:
        decision = "Major revision required"
    elif counts.get("major", 0):
        decision = "Substantive revision required"
    elif counts.get("moderate", 0):
        decision = "Minor-to-moderate revision required"
    else:
        decision = f"Broadly satisfactory at {academic_level_label(summary.get('academic_level'))}"
    if scope == "full_thesis":
        meaning = (
            "This is an examiner-style recommendation based on the manuscript and evidence supplied. "
            "Any statistical or analytical matter marked as requiring original output must be verified before a final examination decision."
        )
    elif scope == "chapter_range":
        meaning = "The submitted chapter range should be revised as an integrated unit before the next stage of thesis development."
    else:
        meaning = "The judgement applies to the selected chapter and should not be treated as a final decision on the complete thesis."
    return {"decision": decision, "meaning": meaning, "reported_readiness": _clean(summary.get("readiness_label"))}


def build_professional_review_package(review: Dict[str, Any]) -> Dict[str, Any]:
    summary = review.get("summary") or {}
    profile = professional_scope_profile(summary)
    ledger = build_finding_ledger(review)
    chapter_judgements = build_chapter_judgements(review, ledger)
    audit = build_methods_results_discussion_audit(ledger)
    package = {
        "profile": profile,
        "scope_contract": professional_scope_contract(summary),
        "finding_ledger": ledger,
        "chapter_judgements": chapter_judgements,
        "cross_chapter_alignment": _cross_chapter_rows(review, ledger),
        "methods_results_discussion_audit": audit,
        "priority_correction_plan": _priority_plan(ledger),
        "recommendation": _overall_recommendation(profile["scope"], ledger, summary),
        "quality_controls": {
            "one_canonical_finding_ledger": True,
            "native_docx_is_delivery_layer": True,
            "finding_quota_used": False,
            "systematic_coverage_driven_review": bool((review.get("summary") or {}).get("systematic_coverage_review")),
            "coverage_release_gate_passed": not bool((review.get("summary") or {}).get("coverage_release_blocking")),
            "examples_must_use_current_study_context": True,
            "statistical_recomputation_claimed_only_with_original_evidence": True,
        },
    }
    return package


def attach_professional_review_package(review: Dict[str, Any]) -> Dict[str, Any]:
    package = build_professional_review_package(review)
    review["professional_review"] = package
    review["finding_ledger"] = package["finding_ledger"]
    summary = review.setdefault("summary", {})
    summary["professional_reviewer_role"] = package["profile"]["role"]
    summary["professional_report_title"] = package["profile"]["report_title"]
    summary["canonical_finding_count"] = len(package["finding_ledger"])
    summary["finding_quota_used"] = False
    return review
