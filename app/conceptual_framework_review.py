from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Sequence


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", _clean(value).lower()).strip()


QUANTITATIVE_SIGNALS = (
    "quantitative", "regression", "ordinary least squares", "ols", "logit",
    "logistic regression", "probit", "structural equation", "sem", "pls sem",
    "anova", "ancova", "manova", "chi square", "correlation", "coefficient",
    "hypothesis testing", "p value", "confidence interval", "effect size",
    "mediation", "moderation", "panel data", "time series", "multilevel model",
)

FRAMEWORK_SIGNALS = (
    "conceptual framework", "conceptual model", "research framework",
    "analytical framework", "proposed model", "hypothesised model",
    "hypothesized model", "path model",
)

ALIGNMENT_SECTION_SIGNALS = {
    "objective": ("research objective", "specific objective", "objectives of the study"),
    "question": ("research question", "questions of the study"),
    "hypothesis": ("research hypothesis", "hypotheses", "hypothesis development"),
    "framework": FRAMEWORK_SIGNALS,
    "theory": ("theoretical framework", "theoretical review", "underpinning theory"),
    "measurement": (
        "measurement of variables", "operationalisation", "operationalization",
        "variable definition", "model specification", "data analysis",
    ),
}


def is_quantitative_study(
    paragraphs: Sequence[Mapping[str, Any]], research_approach: Any = ""
) -> bool:
    approach = _norm(research_approach)
    if "quantitative" in approach or "mixed" in approach:
        return True
    text = " ".join(_norm(row.get("text")) for row in paragraphs)
    signals = sum(1 for term in QUANTITATIVE_SIGNALS if term in text)
    has_hypothesis = bool(re.search(r"\b(?:h0|h1|hypothes(?:is|es))\b", text))
    return signals >= 2 or (signals >= 1 and has_hypothesis)


def _row_blob(row: Mapping[str, Any]) -> str:
    return _norm(" ".join([
        _clean(row.get("heading")),
        " ".join(_clean(value) for value in row.get("section_path") or []),
        _clean(row.get("text")),
        " ".join(_clean(value) for value in row.get("drawing_descriptions") or []),
    ]))


def _row_roles(row: Mapping[str, Any]) -> List[str]:
    blob = _row_blob(row)
    roles = [
        role for role, signals in ALIGNMENT_SECTION_SIGNALS.items()
        if any(signal in blob for signal in signals)
    ]
    if re.match(r"^(?:h\s*0?\d+|hypothesis\s+\d+)", _norm(row.get("text"))):
        roles.append("hypothesis")
    if row.get("contains_drawing") or re.search(r"\b(?:figure|fig)\.?\s*\d+", blob):
        if "framework" in blob or "model" in blob:
            roles.append("diagram")
    return list(dict.fromkeys(roles))


def build_quantitative_framework_audit(
    current_paragraphs: Sequence[Dict[str, Any]],
    context_paragraphs: Sequence[Dict[str, Any]],
    *,
    research_approach: Any = "",
    max_chars: int = 36000,
) -> Dict[str, Any] | None:
    """Build one mandatory expert packet for a detected quantitative framework.

    The packet deliberately brings the research logic together instead of
    assessing the framework paragraph in isolation. Earlier chapters may be
    included as alignment context, but current-document evidence is prioritised.
    """
    current = list(current_paragraphs or [])
    context = list(context_paragraphs or [])
    all_rows = current + context
    if not is_quantitative_study(all_rows, research_approach):
        return None

    framework_rows = [row for row in all_rows if "framework" in _row_roles(row)]
    if not framework_rows:
        return None

    current_ids = {id(row) for row in current}
    candidates: List[tuple[int, int, Dict[str, Any], List[str]]] = []
    for order, row in enumerate(all_rows):
        roles = _row_roles(row)
        if not roles:
            continue
        priority = 0 if "framework" in roles or "diagram" in roles else 1
        if id(row) not in current_ids:
            priority += 2
        candidates.append((priority, order, row, roles))

    selected: List[Dict[str, Any]] = []
    selected_roles: Dict[int, List[str]] = {}
    used_chars = 0
    for _, order, row, roles in sorted(candidates, key=lambda item: (item[0], item[1])):
        size = len(_clean(row.get("text"))) + 220
        if selected and used_chars + size > max(8000, int(max_chars)):
            continue
        selected.append(row)
        selected_roles[id(row)] = roles
        used_chars += size

    selected.sort(key=lambda row: (
        0 if id(row) in current_ids else 1,
        int(row.get("paragraph") or 0),
    ))
    diagram_rows = [row for row in selected if "diagram" in selected_roles.get(id(row), [])]
    visible_drawing_count = sum(int(row.get("drawing_count") or 0) for row in diagram_rows)
    visual_image_count = sum(
        len(row.get("drawing_image_data_urls") or []) for row in diagram_rows
    )
    current_framework = any(id(row) in current_ids for row in framework_rows)
    chapter_numbers = sorted({
        int(row.get("chapter_number")) for row in selected
        if isinstance(row.get("chapter_number"), int)
    })

    return {
        "heading": "Mandatory quantitative conceptual-framework alignment audit",
        "chapter_number": chapter_numbers[0] if len(chapter_numbers) == 1 else None,
        "section_path": [],
        "part": 1,
        "paragraphs": selected,
        "alignment_audit": True,
        "conceptual_framework_audit": True,
        "extra_context": {
            "quantitative_study_confirmed": True,
            "framework_found_in_current_review_scope": current_framework,
            "framework_found_in_alignment_context": any(id(row) not in current_ids for row in framework_rows),
            "diagram_or_figure_reference_found": bool(diagram_rows),
            "embedded_drawing_count": visible_drawing_count,
            "diagram_images_supplied_to_expert": visual_image_count,
            "audited_components": sorted({
                role for roles in selected_roles.values() for role in roles
            }),
            "instruction": (
                "This is a mandatory expert audit. Reconstruct the study logic from the supplied objectives, research questions, hypotheses, theory, conceptual-framework narrative, diagram labels, measurement definitions and model specification. "
                "Create an internal one-to-one matrix and verify that every quantitative objective is represented by a matching question or hypothesis where applicable, the same constructs, population and scope, and an appropriate proposed relationship in the framework. "
                "Inspect the diagram and narrative for all predictors, outcomes, mediators, moderators and control variables; arrow direction; direct, indirect and interaction paths; construct naming; duplicated or orphan constructs; theoretical justification; and consistency with operational definitions and the planned analysis. "
                "Do not require every study to use OLS. Treat effect estimation as compatible with an appropriate regression class, generalized linear model, multilevel model, panel or time-series estimator, SEM, PLS-SEM, mediation, moderation or another justified quantitative model. Separately test whether any causal wording is warranted by the design. "
                "Check that descriptive objectives are not forced into unsupported causal paths and that inferential hypotheses are testable, correctly directed when directional, and traceable to the analysis plan and reported results when those chapters are supplied. "
                "When diagram images are supplied, inspect their visible labels, arrows, direction and legibility directly and reconcile them with the framework narrative. If the actual diagram pixels or arrowheads are not recoverable from the supplied evidence, do not claim that their visual direction or legibility was verified. Issue one precise manual visual-verification finding anchored to the framework caption or narrative, while still completing the textual alignment audit."
            ),
        },
    }
