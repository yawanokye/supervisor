from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Sequence, Set

from .thesis_structure import build_chapter_role_map

_STOP = {
    "about", "after", "against", "among", "and", "association", "between", "effect",
    "effects", "examine", "investigate", "relationship", "role", "study", "the", "their",
    "this", "through", "using", "with", "within", "whether", "impact", "influence",
    "assess", "determine", "evaluate", "analyse", "analyze", "explore", "identify",
}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", _clean(value).lower()).strip()


def _tokens(value: Any) -> Set[str]:
    return {
        token for token in _norm(value).split()
        if len(token) >= 4 and token not in _STOP
    }


def _objective_candidates(paragraphs: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    in_objective_section = False
    for row in paragraphs:
        heading = _norm(row.get("heading") or "")
        text = _clean(row.get("text"))
        low = _norm(text)
        if row.get("is_heading"):
            in_objective_section = any(term in low for term in (
                "research objective", "objectives of the study", "specific objectives",
                "research question", "research questions", "hypothesis", "hypotheses",
            ))
            continue
        if not text or int(row.get("chapter_number") or 0) not in {0, 1}:
            continue
        numbered = bool(re.match(r"^(?:[ivxlcdm]+|\d+)[.)]\s+", text, flags=re.I))
        starts_with_research_verb = bool(re.match(
            r"^(?:to\s+)?(?:assess|determine|evaluate|examine|investigate|analyse|analyze|explore|identify|test|estimate)\b",
            low,
        ))
        hypothesis = bool(re.match(r"^h\s*\d+", low))
        if in_objective_section and (numbered or starts_with_research_verb or hypothesis):
            rows.append({
                "text": text[:700],
                "paragraph": row.get("paragraph"),
                "page": row.get("page"),
                "chapter_number": row.get("chapter_number"),
            })
        if len(rows) >= 24:
            break
    return rows


def build_objective_alignment_matrix(
    paragraphs: Sequence[Mapping[str, Any]],
    academic_level: Any,
) -> Dict[str, Any]:
    objectives = _objective_candidates(paragraphs)
    role_map = build_chapter_role_map(paragraphs, academic_level)
    target_roles = (
        "methodology", "results", "discussion", "conclusion_contribution"
    )
    rows_by_role: Dict[str, List[Mapping[str, Any]]] = {role: [] for role in target_roles}
    for row in paragraphs:
        try:
            chapter = int(row.get("chapter_number"))
        except (TypeError, ValueError):
            continue
        role_row = role_map.get(chapter) or {}
        roles = list(role_row.get("roles") or [role_row.get("role")])
        for role in roles:
            if role in rows_by_role:
                rows_by_role[role].append(row)

    matrix: List[Dict[str, Any]] = []
    for index, objective in enumerate(objectives, start=1):
        objective_tokens = _tokens(objective["text"])
        stage_evidence: Dict[str, List[Dict[str, Any]]] = {}
        missing: List[str] = []
        for role in target_roles:
            matches: List[Dict[str, Any]] = []
            for candidate in rows_by_role[role]:
                candidate_text = _clean(candidate.get("text"))
                candidate_tokens = _tokens(candidate_text)
                overlap = len(objective_tokens & candidate_tokens)
                denominator = max(1, min(len(objective_tokens), 8))
                number_signal = bool(re.search(
                    rf"\b(?:objective|question|hypothesis)\s*{index}\b|\bh\s*{index}\b",
                    _norm(candidate_text),
                ))
                if number_signal or overlap / denominator >= 0.30:
                    matches.append({
                        "chapter_number": candidate.get("chapter_number"),
                        "heading": _clean(candidate.get("heading")),
                        "paragraph": candidate.get("paragraph"),
                        "page": candidate.get("page"),
                        "text": candidate_text[:420],
                        "token_overlap": overlap,
                    })
                if len(matches) >= 3:
                    break
            stage_evidence[role] = matches
            if not matches:
                missing.append(role)
        matrix.append({
            "number": index,
            "objective": objective["text"],
            "source": objective,
            "stage_evidence": stage_evidence,
            "missing_stages": missing,
            "complete_trace": not missing,
        })

    return {
        "objective_count": len(objectives),
        "objectives": matrix,
        "complete_trace_count": sum(1 for row in matrix if row["complete_trace"]),
        "incomplete_trace_count": sum(1 for row in matrix if not row["complete_trace"]),
        "chapter_role_map": role_map,
        "note": (
            "This matrix is a lexical traceability aid. It identifies likely links for expert review and does not replace substantive judgement of whether the method, result, discussion and conclusion actually answer each objective."
        ),
    }
