from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Sequence

from .comment_quality import public_text, sentence_safe_trim


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", _clean(value).lower()).strip()


def article_ready_review_principles() -> str:
    """Shared review contract borrowed from ArticleReady's revision philosophy.

    The intent is to make VProfessor review-first and evidence-preserving. The
    native DOCX, inline annotated DOCX and PDF/report are delivery formats only,
    not the source of the academic judgement.
    """
    return """
ArticleReady-style evidence-preserving review contract:
- First identify the actual study type, research route, data structure, unit of analysis, analysis technique and evidence available in the document. Do not assume a regression, PROCESS, SEM, qualitative or mixed-method route unless the text shows it.
- Preserve confirmed data, quotations, coefficients, tables, themes and findings. If stronger or additional analysis is needed, recommend it and name the evidence required rather than pretending it has been performed.
- Review methods, results and discussion as an integrated chain: objective/question/hypothesis -> design -> data/instrument -> analysis -> results table -> interpretation -> discussion -> conclusion/recommendation.
- For methods, assess design fit, sampling logic, instrument/source credibility, validity, reliability, ethics, reproducibility, assumptions and analysis-by-objective alignment.
- For results, assess whether every research question or hypothesis is answered, whether tables/figures are numbered and interpreted correctly, whether statistics are internally consistent, and whether diagnostics, effect sizes, confidence intervals or qualitative evidence are reported where the method requires them.
- For discussion, assess whether the author explains meaning, compares with theory and empirical literature, addresses unexpected or non-significant findings, recognises limitations and avoids overclaiming beyond the design.
- Use journal-quality revision guidance: say what is wrong, why it matters, exactly what to revise, and provide a context-specific example only when it helps the student understand the correction.
- Classify every unresolved action as Essential before approval, Strongly recommended, or Optional refinement. Each action must state the exact location, the specific correction, the academic reason and how the supervisor can verify completion.
- Anchor every action to the exact sentence, paragraph or table row that requires it. When several distinct actions concern the same sentence, keep them in one numbered native Word comment box rather than scattering duplicate comment boxes across the sentence.
- Keep the full substantive review in the report. Convert only actionable, evidence-anchored corrections into Word comments. Native comments must not compress away important academic judgement.
""".strip()


_METHOD_GROUPS = {
    "Quantitative statistical analysis": (
        "regression", "correlation", "anova", "ancova", "manova", "t-test", "chi-square",
        "logistic", "sem", "pls", "factor", "mediation", "moderation", "process macro",
        "panel", "time series", "unit root", "cointegration", "gmm", "ardl", "structural equation",
    ),
    "Qualitative analysis": (
        "qualitative", "interview", "focus group", "thematic", "coding", "theme", "trustworthiness",
        "credibility", "dependability", "confirmability", "transferability", "quotation",
    ),
    "Mixed-methods analysis": (
        "mixed methods", "mixed-methods", "triangulation", "joint display", "convergent", "explanatory sequential",
        "exploratory sequential", "integration of findings",
    ),
    "Review or evidence synthesis": (
        "systematic review", "scoping review", "meta-analysis", "prisma", "screening", "inclusion criteria",
        "exclusion criteria", "quality appraisal", "risk of bias",
    ),
}

_ANALYSIS_CATEGORIES = {
    "Method fit and reproducibility": {"methodological_rigour", "methods_results_alignment", "ethics_and_integrity"},
    "Results accuracy and completeness": {"statistical_reporting_accuracy", "results_and_interpretation", "tables_figures_and_presentation"},
    "Discussion and interpretation": {"discussion_quality", "discussion_and_integration", "conclusions_and_recommendations"},
    "Cross-chapter alignment": {"cross_section_coherence", "objectives_questions_hypotheses", "research_gap_and_problem"},
    "Source and evidence integrity": {"citations_and_sources", "empirical_evidence", "critical_analysis"},
}


def detect_review_route_from_text(text: str) -> List[str]:
    low = _norm(text)
    routes: List[str] = []
    for label, terms in _METHOD_GROUPS.items():
        if any(term in low for term in terms):
            routes.append(label)
    return routes or ["General thesis or dissertation review"]


def detect_review_route(review: Dict[str, Any]) -> List[str]:
    parts: List[str] = []
    for key in ("study_context", "summary", "overall_academic_assessment"):
        value = review.get(key)
        if isinstance(value, dict):
            parts.extend(str(v) for v in value.values())
        else:
            parts.append(str(value or ""))
    for row in review.get("academic_section_reviews") or []:
        parts.append(str(row.get("heading") or row.get("section_name") or ""))
        parts.append(str(row.get("section_assessment") or ""))
    for row in review.get("academic_findings") or []:
        parts.append(str(row.get("section") or ""))
        parts.append(str(row.get("item") or row.get("issue_title") or ""))
        parts.append(str(row.get("comment") or row.get("assessment") or ""))
    return detect_review_route_from_text("\n".join(parts))


def _finding_text(row: Dict[str, Any]) -> str:
    chunks = [
        row.get("item") or row.get("issue_title") or "",
        row.get("comment") or row.get("assessment") or "",
        row.get("required_action") or "",
        row.get("illustrative_guidance") or "",
    ]
    text = " ".join(_clean(part) for part in chunks if _clean(part))
    return public_text(sentence_safe_trim(text, 420), reject_placeholders=True, reject_incomplete=True)


def _location(row: Dict[str, Any]) -> str:
    evidence = row.get("evidence") or []
    if evidence:
        best = evidence[0]
        bits = []
        if best.get("section_reference"):
            bits.append(_clean(best.get("section_reference")))
        if best.get("table_number"):
            label = "Table " + _clean(best.get("table_number"))
            if best.get("table_title"):
                label += ": " + _clean(best.get("table_title"))
            bits.append(label)
        elif best.get("paragraph") is not None:
            bits.append("paragraph " + str(best.get("paragraph")))
        if bits:
            return ", ".join(bits)
    return _clean(row.get("section_reference") or row.get("section") or "section-level evidence")


def build_articleready_quality_audit(review: Dict[str, Any], *, limit_per_area: int = 5) -> Dict[str, Any]:
    """Create a report-first, ArticleReady-style quality audit from findings.

    This does not invent new findings. It organises the already evidence-gated
    findings into a more useful methods/results/discussion review so the report
    remains as thorough as the native comments.
    """
    rows = list(review.get("academic_findings") or [])
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        cat = _norm(row.get("category") or "other")
        placed = False
        for area, categories in _ANALYSIS_CATEGORIES.items():
            if cat in {_norm(c) for c in categories}:
                grouped[area].append(row)
                placed = True
                break
        if not placed and any(term in _norm(_finding_text(row)) for term in ("method", "analysis", "result", "discussion", "table", "statistic", "hypothesis", "objective")):
            grouped["Method, results and discussion integration"].append(row)

    audit_rows: List[Dict[str, Any]] = []
    for area in (
        "Method fit and reproducibility",
        "Results accuracy and completeness",
        "Discussion and interpretation",
        "Cross-chapter alignment",
        "Source and evidence integrity",
        "Method, results and discussion integration",
    ):
        seen = set()
        for row in grouped.get(area, [])[: max(1, limit_per_area)]:
            finding = _finding_text(row)
            key = _norm(finding)[:160]
            if not finding or key in seen:
                continue
            seen.add(key)
            audit_rows.append({
                "area": area,
                "severity": _clean(row.get("severity") or "moderate"),
                "location": _location(row),
                "finding": finding,
                "required_action": public_text(sentence_safe_trim(_clean(row.get("required_action") or row.get("comment") or row.get("assessment")), 340), reject_placeholders=True, reject_incomplete=True),
            })
    routes = detect_review_route(review)
    return {
        "review_mode": "ArticleReady-style evidence-preserving thesis review",
        "detected_review_routes": routes,
        "audit_rows": audit_rows,
        "principle_summary": (
            "The review is report-first and evidence-preserving. Native Word comments and inline annotations are delivery formats only; "
            "they must not reduce the depth of the academic judgement. Missing or unsupported analysis is recommended as an action, not invented as a result."
        ),
    }


def attach_articleready_quality_audit(review: Dict[str, Any]) -> Dict[str, Any]:
    review["articleready_quality_audit"] = build_articleready_quality_audit(review)
    summary = review.setdefault("summary", {})
    summary["review_engine_style"] = "ArticleReady-style evidence-preserving supervisor review"
    summary["native_docx_is_delivery_only"] = True
    return review
