from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Sequence


ROLE_LABELS: Dict[str, str] = {
    "introduction_problem": "Introduction, research problem and study alignment",
    "contextual_background": "Contextual or disciplinary background",
    "literature_theory": "Literature, theory and conceptual positioning",
    "methodology": "Methodology, measurement, ethics and reproducibility",
    "results": "Results, findings and analytical evidence",
    "discussion": "Discussion, synthesis and interpretation",
    "conclusion_contribution": "Conclusions, contribution, implications and recommendations",
    "article_or_study": "Article, study or empirical paper chapter",
    "other": "Discipline-sensitive supporting chapter",
}

ROLE_SPECIALISTS: Dict[str, str] = {
    "introduction_problem": "Research problem, framing and alignment specialist",
    "contextual_background": "Context, disciplinary positioning and scope specialist",
    "literature_theory": "Theory, evidence synthesis and research-gap specialist",
    "methodology": "Research design, measurement, ethics and reproducibility specialist",
    "results": "Results, statistical or qualitative analysis, and reporting specialist",
    "discussion": "Interpretation, theory integration and rival-explanation specialist",
    "conclusion_contribution": "Synthesis, contribution, conclusion and recommendation specialist",
    "article_or_study": "Article-based doctoral thesis and cross-paper integration specialist",
    "other": "Discipline-sensitive thesis reviewer",
}

STANDARD_FIVE_CHAPTER_ROLES = {
    1: "introduction_problem",
    2: "literature_theory",
    3: "methodology",
    4: "results",
    5: "conclusion_contribution",
}

ROLE_TERMS: Dict[str, Sequence[str]] = {
    "introduction_problem": (
        "introduction", "background to the study", "background of the study",
        "statement of the problem", "problem statement", "purpose of the study",
        "aim of the study", "research objectives", "research questions",
        "research hypotheses", "significance of the study", "scope of the study",
    ),
    "contextual_background": (
        "contextual framework", "contextual background", "institutional context",
        "historical background", "country context", "industry context",
        "disciplinary context", "structural dynamics", "study context",
    ),
    "literature_theory": (
        "literature review", "review of literature", "theoretical framework",
        "theoretical review", "conceptual review", "conceptual framework",
        "empirical review", "research gap", "hypothesis development",
        "proposition development", "state of the art",
    ),
    "methodology": (
        "methodology", "research methods", "research methodology", "research design",
        "research philosophy", "research paradigm", "research approach", "population",
        "sampling", "sample size", "data collection", "instrument", "measurement",
        "operationalisation", "operationalization", "data analysis", "model specification",
        "diagnostic tests", "ethical considerations", "ethics", "trustworthiness",
    ),
    "results": (
        "results", "findings", "research findings", "empirical results", "data analysis",
        "model estimates", "descriptive statistics", "hypothesis testing", "themes",
        "analysis of evidence", "presentation of results",
    ),
    "discussion": (
        "discussion", "discussion of findings", "discussion of results",
        "interpretation of findings", "interpretation of results", "integrative discussion",
        "synthesis", "alternative explanations", "rival explanations",
    ),
    "conclusion_contribution": (
        "summary of findings", "summary of the study", "conclusion", "conclusions",
        "recommendation", "recommendations", "contribution to knowledge",
        "original contribution", "theoretical contribution", "methodological contribution",
        "practical implications", "policy implications", "limitations of the study",
        "future research", "directions for future research",
    ),
    "article_or_study": (
        "paper one", "paper two", "paper three", "essay one", "essay two", "essay three",
        "study one", "study two", "study three", "article one", "article two", "article three",
    ),
}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", _clean(value).lower()).strip()


def academic_level_key(level: Any) -> str:
    value = _norm(level).replace("-", " ")
    if value in {"phd", "dphil"} or "doctor of philosophy" in value:
        return "phd"
    if "professional doctorate" in value or value.startswith("doctor of ") or value.startswith("doctoral"):
        return "professional_doctorate"
    if "research master" in value or "mphil" in value:
        return "research_masters"
    if "non research master" in value or "master" in value:
        return "non_research_masters"
    return "bachelors"


def is_phd_level(level: Any) -> bool:
    return academic_level_key(level) == "phd"


def uses_flexible_phd_structure(level: Any) -> bool:
    """Only a PhD is structurally flexible by default.

    Professional doctorates remain doctoral in scholarly standard but use the
    application's standard five-chapter supervisory structure unless an
    institution-specific profile is introduced later.
    """
    return is_phd_level(level)


def _role_scores(text: str) -> Dict[str, int]:
    value = _norm(text)
    scores: Dict[str, int] = defaultdict(int)
    for role, terms in ROLE_TERMS.items():
        for term in terms:
            normal = _norm(term)
            if normal and normal in value:
                scores[role] += 3 if value.startswith(normal) else 1
    return dict(scores)


def infer_chapter_role(
    chapter_number: Any,
    heading: str = "",
    content: str = "",
    *,
    academic_level: Any = "",
    flexible_phd: bool | None = None,
) -> str:
    try:
        number = int(chapter_number) if chapter_number is not None else None
    except (TypeError, ValueError):
        number = None

    flexible = uses_flexible_phd_structure(academic_level) if flexible_phd is None else bool(flexible_phd)
    if not flexible and number in STANDARD_FIVE_CHAPTER_ROLES:
        return STANDARD_FIVE_CHAPTER_ROLES[number]

    combined = f"{heading} {content}".strip()
    scores = _role_scores(combined)
    if scores:
        ranked = sorted(scores.items(), key=lambda item: (item[1], item[0]), reverse=True)
        best_role, best_score = ranked[0]
        if best_score > 0:
            # A chapter explicitly titled Discussion should not be classified as
            # Results merely because it repeats the word results in its prose.
            heading_scores = _role_scores(heading)
            if heading_scores:
                heading_best = max(heading_scores.items(), key=lambda item: item[1])
                if heading_best[1] >= 3:
                    return heading_best[0]
            return best_role

    if number in STANDARD_FIVE_CHAPTER_ROLES:
        return STANDARD_FIVE_CHAPTER_ROLES[number]
    return "other"


def build_chapter_role_map(
    paragraphs: Sequence[Mapping[str, Any]],
    academic_level: Any,
) -> Dict[int, Dict[str, Any]]:
    grouped: Dict[int, List[Mapping[str, Any]]] = defaultdict(list)
    for row in paragraphs:
        try:
            number = int(row.get("chapter_number"))
        except (TypeError, ValueError):
            continue
        grouped[number].append(row)

    flexible = uses_flexible_phd_structure(academic_level)
    output: Dict[int, Dict[str, Any]] = {}
    for number, rows in sorted(grouped.items()):
        heading = next(
            (
                _clean(row.get("text") or row.get("heading"))
                for row in rows
                if row.get("is_heading") and _clean(row.get("text") or row.get("heading"))
            ),
            _clean(rows[0].get("heading") if rows else ""),
        )
        substantive = " ".join(
            _clean(row.get("text"))
            for row in rows
            if not row.get("is_heading") and _clean(row.get("text"))
        )[:12000]
        role = infer_chapter_role(
            number,
            heading,
            substantive,
            academic_level=academic_level,
            flexible_phd=flexible,
        )
        roles = [role]
        if not flexible and number == 4 and "discussion" not in roles:
            roles.append("discussion")
        output[number] = {
            "chapter_number": number,
            "heading": heading or f"Chapter {number}",
            "role": role,
            "roles": roles,
            "role_label": ROLE_LABELS.get(role, ROLE_LABELS["other"]),
            "specialist_role": ROLE_SPECIALISTS.get(role, ROLE_SPECIALISTS["other"]),
            "paragraph_count": len(rows),
        }
    return output


def chapters_for_roles(
    role_map: Mapping[int, Mapping[str, Any]],
    roles: Iterable[str],
) -> List[int]:
    wanted = set(roles)
    return sorted(
        int(number)
        for number, row in role_map.items()
        if row.get("role") in wanted or bool(set(row.get("roles") or []) & wanted)
    )
