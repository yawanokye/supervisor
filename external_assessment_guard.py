from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .checkpointing import stable_hash
from .document_parser import clean_text, explicit_chapter_marker, normalised


ROLE_SPECS: Dict[str, Dict[str, Any]] = {
    "foundation": {
        "label": "Research foundation, problem, purpose and questions",
        "terms": (
            "background to the study", "background of the study",
            "statement of the problem", "problem statement", "research problem",
            "research gap", "purpose of the study", "aim of the study",
            "research objective", "research objectives", "research question",
            "research questions", "research hypothesis", "research hypotheses",
            "significance of the study", "scope of the study", "delimitation",
            "limitations of the study", "organisation of the study",
        ),
    },
    "literature_theory": {
        "label": "Literature, theory and conceptual positioning",
        "terms": (
            "literature review", "review of related literature", "theoretical review",
            "theoretical framework", "conceptual review", "conceptual framework",
            "conceptual model", "empirical review", "hypothesis development",
            "theoretical foundation", "research gap",
        ),
    },
    "methodology": {
        "label": "Methodology and research procedures",
        "terms": (
            "research methodology", "research methods", "methodology",
            "research philosophy", "research paradigm", "research approach",
            "research design", "study area", "population", "sample size",
            "sampling procedure", "sampling technique", "data collection instrument",
            "data collection procedure", "validity and reliability", "ethical considerations",
            "data processing and analysis", "model specification", "diagnostic test",
        ),
    },
    "results": {
        "label": "Evidence, analysis, results or findings",
        "terms": (
            "results", "research findings", "empirical findings", "empirical results",
            "presentation of findings", "presentation of results", "data analysis",
            "descriptive statistics", "hypothesis testing", "measurement model",
            "structural model", "indicator loading", "factor loading", "average variance extracted",
            "fornell larcker", "htmt", "heterotrait monotrait", "variance inflation factor",
            "bootstrapping", "path coefficient", "r squared", "effect size", "predictive relevance",
            "plspredict", "model fit", "regression result", "thematic findings",
        ),
    },
    "discussion": {
        "label": "Discussion, synthesis and interpretation",
        "terms": (
            "discussion of findings", "discussion of results", "discussion",
            "interpretation of findings", "interpretation of results",
            "synthesis of findings", "alternative explanation",
        ),
    },
    "conclusions": {
        "label": "Conclusions, recommendations and contribution",
        "terms": (
            "summary of findings", "conclusion", "conclusions", "recommendation",
            "recommendations", "contribution to knowledge", "original contribution",
            "theoretical contribution", "practical implication", "policy implication",
            "limitations", "future research", "suggestions for further research",
        ),
    },
    "ethics": {
        "label": "Ethics and research integrity",
        "terms": (
            "ethical consideration", "ethical considerations", "ethical clearance",
            "ethics approval", "ethical approval", "informed consent", "confidentiality",
            "anonymity", "institutional review board", "research ethics committee",
        ),
    },
    "references": {
        "label": "References and source integrity",
        "terms": (
            "references", "bibliography", "doi.org", "https://doi.org",
        ),
    },
}


METHOD_RUBRICS: Dict[str, Dict[str, Any]] = {
    "pls_sem": {
        "label": "PLS-SEM",
        "signals": (
            "pls sem", "pls-sem", "partial least squares", "smartpls",
            "measurement model", "structural model", "htmt", "fornell larcker",
        ),
        "checks": (
            "construct operationalisation and indicator specification",
            "indicator loadings and the treatment of weak indicators",
            "internal consistency using appropriate coefficients",
            "convergent validity through AVE",
            "discriminant validity using HTMT and supporting checks",
            "collinearity using inner and outer VIF where applicable",
            "bootstrapping settings, path coefficients, confidence intervals and effect sizes",
            "R², predictive relevance and out-of-sample prediction where claimed",
            "moderation or mediation specification and interpretation",
            "sample-size justification using statistical power rather than the ten-times rule alone",
            "common-method bias and the limits of cross-sectional self-report evidence",
        ),
    },
    "covariance_sem": {
        "label": "Covariance-based SEM",
        "signals": (
            "structural equation modelling", "structural equation modeling", "amos",
            "confirmatory factor analysis", "cfa", "comparative fit index", "rmsea",
        ),
        "checks": (
            "measurement model identification and estimator choice",
            "factor loadings, reliability and construct validity",
            "global fit indices and defensible thresholds",
            "normality, missing data and outlier treatment",
            "structural paths, indirect effects and uncertainty intervals",
            "model modification practices and theory-based justification",
        ),
    },
    "econometrics": {
        "label": "Econometric or regression analysis",
        "signals": (
            "regression", "panel data", "time series", "fixed effects", "random effects",
            "instrumental variable", "difference in differences", "cointegration", "ardl",
        ),
        "checks": (
            "model specification and variable operationalisation",
            "identification assumptions and threats to causal interpretation",
            "diagnostic testing appropriate to the data structure",
            "robust or clustered inference and small-sample limitations",
            "endogeneity, omitted-variable bias and sensitivity analysis",
            "economic as well as statistical significance",
        ),
    },
    "qualitative": {
        "label": "Qualitative inquiry",
        "signals": (
            "qualitative", "thematic analysis", "phenomenology", "grounded theory",
            "case study", "interview", "focus group", "coding", "saturation",
        ),
        "checks": (
            "philosophical and methodological coherence",
            "sampling logic and information adequacy",
            "data-generation procedures and reflexivity",
            "transparent coding and theme development",
            "credibility, dependability, confirmability and transferability",
            "clear linkage between interpretations and participant evidence",
        ),
    },
    "mixed_methods": {
        "label": "Mixed-methods research",
        "signals": (
            "mixed methods", "mixed-method", "convergent design", "explanatory sequential",
            "exploratory sequential", "integration of quantitative and qualitative",
        ),
        "checks": (
            "rationale for mixing methods",
            "priority, timing and sequence of strands",
            "sampling and analysis within each strand",
            "integration at design, analysis and interpretation stages",
            "handling of convergence, complementarity and divergence",
            "meta-inferences that are supported by both strands",
        ),
    },
}


PRESENCE_SPECS: Dict[str, Dict[str, Any]] = {
    "conceptual_model": {
        "label": "conceptual model or framework",
        "terms": ("conceptual model", "conceptual framework", "proposed model"),
    },
    "hypotheses": {
        "label": "research hypotheses",
        "terms": ("research hypothesis", "research hypotheses", "hypothesis", "hypotheses", "hypothesis development", "hypothesis testing"),
    },
    "research_paradigm_and_design": {
        "label": "research paradigm, philosophy and design",
        "terms": ("research paradigm", "research philosophy", "positivism", "interpretivism", "research design"),
    },
    "sampling_and_data_collection": {
        "label": "sampling, sample size and data collection",
        "terms": ("sample size", "sampling procedure", "sampling technique", "data collection procedure", "data collection instrument"),
    },
    "measurement_model": {
        "label": "measurement-model assessment",
        "terms": ("measurement model", "indicator loading", "factor loading", "average variance extracted", "htmt", "fornell larcker"),
    },
    "structural_model": {
        "label": "structural-model assessment",
        "terms": ("structural model", "path coefficient", "bootstrapping", "r squared", "effect size", "predictive relevance", "plspredict"),
    },
    "results": {
        "label": "results or findings",
        "roles": ("results",),
        "terms": ("results", "findings", "hypothesis testing", "data analysis"),
    },
    "discussion": {
        "label": "discussion and interpretation",
        "roles": ("discussion",),
        "terms": ("discussion of findings", "discussion of results", "interpretation of findings"),
    },
    "conclusions": {
        "label": "conclusions",
        "roles": ("conclusions",),
        "terms": ("conclusion", "conclusions"),
    },
    "recommendations": {
        "label": "recommendations",
        "terms": ("recommendation", "recommendations"),
    },
    "ethics": {
        "label": "ethical considerations or clearance",
        "roles": ("ethics",),
        "terms": ("ethical consideration", "ethical clearance", "ethics approval", "ethical approval", "informed consent"),
    },
    "references": {
        "label": "reference list",
        "terms": ("references", "bibliography"),
        "heading_only_ok": True,
    },
    "appendices": {
        "label": "appendices",
        "terms": ("appendix", "appendices"),
        "heading_only_ok": True,
    },
    "research_instrument": {
        "label": "research instrument",
        "terms": ("questionnaire", "interview guide", "survey instrument", "data collection instrument"),
    },
}




def evidence_id(row: Dict[str, Any], index: int) -> str:
    table_index = row.get("table_index")
    table_row = row.get("table_row")
    if isinstance(table_index, int) and isinstance(table_row, int):
        return f"T{table_index}R{table_row}"
    paragraph = row.get("paragraph")
    if isinstance(paragraph, int):
        return f"P{paragraph}"
    page = row.get("page")
    page_paragraph = row.get("page_paragraph")
    if isinstance(page, int) and isinstance(page_paragraph, int):
        return f"PG{page}P{page_paragraph}"
    return f"E{index + 1}"


def annotate_evidence(paragraphs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    used: Dict[str, int] = defaultdict(int)
    for index, row in enumerate(paragraphs):
        item = dict(row)
        base = clean_text(item.get("evidence_id")) or evidence_id(item, index)
        used[base] += 1
        item["evidence_id"] = base if used[base] == 1 else f"{base}_{used[base]}"
        output.append(item)
    return output


def _word_count(text: Any) -> int:
    return len(re.findall(r"\b[\w’'-]+\b", clean_text(text)))


def _row_text(row: Dict[str, Any]) -> str:
    return clean_text(row.get("text", ""))


def _row_search_text(row: Dict[str, Any]) -> str:
    return normalised(f"{row.get('heading', '')} {_row_text(row)}")


def _is_toc_row(row: Dict[str, Any]) -> bool:
    if bool(row.get("is_toc_entry")):
        return True
    style = normalised(row.get("style", ""))
    if style.startswith("toc") or "table of contents" in style:
        return True
    text = _row_text(row)
    if re.search(r"\.{2,}\s*\d+\s*$", text):
        return True
    return False


def _term_hits(text: str, terms: Iterable[str]) -> List[str]:
    return [term for term in terms if normalised(term) in text]


def _chapter_title(rows: Sequence[Dict[str, Any]], chapter_number: int) -> str:
    markers = [
        (index, row)
        for index, row in enumerate(rows)
        if row.get("chapter_marker_number") == chapter_number
    ]
    if not markers:
        markers = [
            (index, row)
            for index, row in enumerate(rows)
            if row.get("chapter_number") == chapter_number
            and row.get("is_heading")
            and normalised(_row_text(row)).startswith("chapter ")
        ]
    if markers:
        marker_index, marker = markers[-1]
        marker_text = _row_text(marker)
        stripped = re.sub(
            r"^\s*chapter\s+(?:\d+|[ivxlcdm]+|[a-z-]+)\s*[:.\-–—]*\s*",
            "",
            marker_text,
            flags=re.I,
        ).strip()
        if stripped and normalised(stripped) != normalised(marker_text):
            return clean_text(stripped)[:240]
        for candidate in rows[marker_index + 1: marker_index + 7]:
            if candidate.get("is_heading") and candidate.get("chapter_number") == chapter_number:
                value = _row_text(candidate)
                if value and not normalised(value).startswith("chapter "):
                    return value[:240]
        return marker_text[:240]

    headings = [
        _row_text(row)
        for row in rows
        if row.get("chapter_number") == chapter_number and row.get("is_heading")
    ]
    return (headings[0] if headings else f"Chapter {chapter_number}")[:240]


def _role_analysis(rows: Sequence[Dict[str, Any]]) -> Tuple[Dict[str, Any], Dict[str, List[int]]]:
    role_presence: Dict[str, Any] = {}
    role_chapters: Dict[str, List[int]] = {}

    for role, specification in ROLE_SPECS.items():
        evidence: List[str] = []
        matched_terms: List[str] = []
        chapter_scores: Dict[int, float] = defaultdict(float)
        substantive_hits = 0

        for row in rows:
            text = _row_search_text(row)
            hits = _term_hits(text, specification["terms"])
            if not hits:
                continue
            words = _word_count(_row_text(row))
            is_heading = bool(row.get("is_heading"))
            substantive = words >= 12 or row.get("source_kind") == "table_row"
            weight = 3.0 if is_heading else 1.0
            if substantive:
                weight += 2.0
                substantive_hits += 1
            chapter = row.get("chapter_number")
            if isinstance(chapter, int):
                chapter_scores[chapter] += weight * max(1, len(hits))
            if row["evidence_id"] not in evidence:
                evidence.append(row["evidence_id"])
            for hit in hits:
                if hit not in matched_terms:
                    matched_terms.append(hit)

        present = bool(evidence) and (substantive_hits > 0 or len(evidence) >= 2)
        ranked_chapters = [
            chapter
            for chapter, score in sorted(
                chapter_scores.items(), key=lambda item: (-item[1], item[0])
            )
            if score >= 2.0
        ]
        role_chapters[role] = ranked_chapters[:4]
        role_presence[role] = {
            "label": specification["label"],
            "status": "present" if present else "not_confidently_located",
            "matched_terms": matched_terms[:12],
            "evidence_ids": evidence[:80] if role == "references" else evidence[:16],
            "chapter_numbers": ranked_chapters[:4],
        }

    return role_presence, role_chapters


def _front_matter_rows(rows: Sequence[Dict[str, Any]], limit: int = 80) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    for row in rows:
        if len(selected) >= limit:
            break
        chapter = row.get("chapter_number")
        if chapter is None or len(selected) < 35:
            selected.append(row)
        if isinstance(chapter, int) and row.get("chapter_marker_number"):
            break
    return selected or list(rows[:limit])


def _looks_like_person_name(text: str) -> bool:
    value = clean_text(text)
    if not value or not (2 <= len(value.split()) <= 7):
        return False
    low = normalised(value)
    blocked = (
        "university", "department", "school", "faculty", "college", "thesis",
        "dissertation", "degree", "doctor", "master", "bachelor", "submitted",
        "supervisor", "declaration", "copyright", "abstract", "chapter",
    )
    if any(term in low for term in blocked):
        return False
    tokens = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ'’-]+", value)
    if len(tokens) < 2:
        return False
    capitalised = sum(token[:1].isupper() for token in tokens)
    return value.isupper() or capitalised >= max(2, len(tokens) - 1)


def infer_document_metadata(paragraphs: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    rows = annotate_evidence(paragraphs)
    front = _front_matter_rows(rows)
    values = [_row_text(row) for row in front if _row_text(row)]

    candidate_number = ""
    number_evidence = ""
    number_pattern = re.compile(
        r"\b(?:index|student|candidate|registration|reg\.?|id)\s*"
        r"(?:no\.?|number)?\s*[:#\-]?\s*([A-Z0-9][A-Z0-9/\-]{3,})\b",
        flags=re.I,
    )
    for row in front:
        match = number_pattern.search(_row_text(row))
        if match:
            candidate_number = match.group(1).strip()
            number_evidence = row["evidence_id"]
            break

    candidate_name = ""
    name_evidence = ""
    for index, row in enumerate(front):
        text = _row_text(row)
        if re.fullmatch(r"by", normalised(text), flags=re.I):
            for candidate in front[index + 1:index + 5]:
                if _looks_like_person_name(_row_text(candidate)):
                    candidate_name = _row_text(candidate)
                    name_evidence = candidate["evidence_id"]
                    break
        match = re.match(r"^\s*by\s+(.+)$", text, flags=re.I)
        if match and _looks_like_person_name(match.group(1)):
            candidate_name = clean_text(match.group(1))
            name_evidence = row["evidence_id"]
        if candidate_name:
            break

    if not candidate_name and candidate_number:
        number_index = next(
            (index for index, row in enumerate(front) if row["evidence_id"] == number_evidence),
            -1,
        )
        if number_index >= 0:
            for candidate in reversed(front[max(0, number_index - 4):number_index]):
                if _looks_like_person_name(_row_text(candidate)):
                    candidate_name = _row_text(candidate)
                    name_evidence = candidate["evidence_id"]
                    break

    institution = ""
    institution_evidence = ""
    institution_candidates: List[Tuple[float, str, str]] = []
    for row in front:
        text = _row_text(row)
        if not re.search(r"\b(?:university|institute|college)\b", text, flags=re.I):
            continue
        if len(text.split()) > 24:
            continue
        low = normalised(text)
        score = 0.0
        if re.match(r"^(?:the\s+)?(?:university|institute|college)\b", low):
            score += 8.0
        if text.isupper():
            score += 3.0
        if "submitted" in low or "award" in low:
            score -= 5.0
        score -= len(text.split()) * 0.05
        institution_candidates.append((score, text, row["evidence_id"]))
    if institution_candidates:
        _, institution, institution_evidence = max(institution_candidates, key=lambda item: item[0])

    department = ""
    department_evidence = ""
    for row in front:
        text = _row_text(row)
        if re.search(r"\b(?:department|school|faculty|college)\s+of\b", text, flags=re.I):
            if len(text.split()) <= 20:
                department = text
                department_evidence = row["evidence_id"]
                break

    degree_programme = ""
    degree_evidence = ""
    degree_pattern = re.compile(
        r"\b(?:doctor of|ph\.?d\.?|dba|dedd?|master of|m\.?phil\.?|m\.?sc\.?|m\.?a\.?|mba|bachelor of|b\.?sc\.?)\b",
        flags=re.I,
    )
    for row in front:
        text = _row_text(row)
        if degree_pattern.search(text) and len(text.split()) <= 35:
            degree_programme = text
            degree_evidence = row["evidence_id"]
            break

    thesis_title = ""
    title_evidence = ""
    by_front_index = next(
        (
            index
            for index, row in enumerate(front)
            if normalised(_row_text(row)) == "by"
            or normalised(_row_text(row)).startswith("by ")
        ),
        min(len(front), 24),
    )
    eligible_title_rows: List[Tuple[Dict[str, Any], str]] = []
    blocked_title_terms = (
        "university", "institute", "college", "department", "school", "faculty",
        "thesis submitted", "dissertation submitted", "submitted in", "award of",
        "copyright", "index no", "index number", "student number", "candidate number",
        "declaration", "supervisor", "abstract",
    )
    for row in front[:by_front_index]:
        text = _row_text(row)
        low = normalised(text)
        if not text or any(term in low for term in blocked_title_terms):
            continue
        if re.fullmatch(r"(?:title|logo|crest)", low):
            continue
        if len(text.split()) <= 18:
            eligible_title_rows.append((row, text))

    title_candidates: List[Tuple[float, str, str]] = []
    for row, text in eligible_title_rows:
        words = _word_count(text)
        if 5 <= words <= 45 and len(text) <= 500:
            score = words + (6.0 if text.isupper() else 0.0)
            title_candidates.append((score, text, row["evidence_id"]))

    for start_index in range(len(eligible_title_rows)):
        combined: List[str] = []
        evidence: List[str] = []
        previous_paragraph: Optional[int] = None
        for row, text in eligible_title_rows[start_index:start_index + 6]:
            paragraph = row.get("paragraph")
            if (
                previous_paragraph is not None
                and isinstance(paragraph, int)
                and paragraph > previous_paragraph + 2
            ):
                break
            combined.append(text)
            evidence.append(row["evidence_id"])
            previous_paragraph = paragraph if isinstance(paragraph, int) else previous_paragraph
            candidate = clean_text(" ".join(combined))
            words = _word_count(candidate)
            if 5 <= words <= 45 and len(candidate) <= 500:
                uppercase_bonus = 6.0 if all(part.isupper() for part in combined) else 0.0
                title_candidates.append((words + uppercase_bonus, candidate, evidence[0]))

    if title_candidates:
        _, thesis_title, title_evidence = max(title_candidates, key=lambda item: item[0])

    return {
        "candidate_name": candidate_name,
        "candidate_number": candidate_number,
        "degree_programme": degree_programme,
        "department": department,
        "institution": institution,
        "thesis_title": thesis_title,
        "evidence": {
            "candidate_name": name_evidence,
            "candidate_number": number_evidence,
            "degree_programme": degree_evidence,
            "department": department_evidence,
            "institution": institution_evidence,
            "thesis_title": title_evidence,
        },
    }


def _presence_signals(
    rows: Sequence[Dict[str, Any]],
    role_presence: Dict[str, Any],
    detected_chapters: Sequence[int],
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    signals: Dict[str, Any] = {}
    for chapter in detected_chapters:
        chapter_ids = [
            row["evidence_id"]
            for row in rows
            if row.get("chapter_number") == chapter
            and (row.get("is_heading") or row.get("chapter_marker_number") == chapter)
        ]
        if not chapter_ids:
            chapter_ids = [
                row["evidence_id"]
                for row in rows
                if row.get("chapter_number") == chapter
            ][:3]
        signals[f"chapter_{chapter}"] = {
            "label": f"Chapter {chapter}",
            "status": "present",
            "evidence_ids": chapter_ids[:10],
        }

    for key, specification in PRESENCE_SPECS.items():
        evidence: List[str] = []
        matched_terms: List[str] = []
        for role in specification.get("roles", ()):
            role_data = role_presence.get(role) or {}
            evidence.extend(role_data.get("evidence_ids") or [])
            matched_terms.extend(role_data.get("matched_terms") or [])
        for row in rows:
            text = _row_search_text(row)
            hits = _term_hits(text, specification.get("terms", ()))
            if not hits:
                continue
            if not specification.get("heading_only_ok"):
                substantive = _word_count(_row_text(row)) >= 6 or row.get("source_kind") == "table_row"
                if not substantive and not row.get("is_heading"):
                    continue
            evidence.append(row["evidence_id"])
            matched_terms.extend(hits)

        unique_evidence = list(dict.fromkeys(evidence))
        unique_terms = list(dict.fromkeys(matched_terms))
        signals[key] = {
            "label": specification["label"],
            "status": "present" if unique_evidence else "not_confidently_located",
            "evidence_ids": unique_evidence[:16],
            "matched_terms": unique_terms[:12],
        }

    for key, label in (
        ("candidate_name", "candidate name"),
        ("candidate_number", "candidate number"),
        ("degree_programme", "degree programme"),
        ("institution", "institution"),
        ("thesis_title", "thesis title"),
    ):
        value = clean_text(metadata.get(key))
        signals[key] = {
            "label": label,
            "status": "present" if value else "not_confidently_located",
            "value": value,
            "evidence_ids": [metadata.get("evidence", {}).get(key)] if metadata.get("evidence", {}).get(key) else [],
        }

    return signals


def build_method_rubric(
    paragraphs: Sequence[Dict[str, Any]],
    *,
    declared_approach: str = "",
) -> Dict[str, Any]:
    text = normalised(
        " ".join(_row_text(row) for row in paragraphs if _row_text(row))
    )
    approach = normalised(declared_approach)
    detected: List[Dict[str, Any]] = []
    for key, specification in METHOD_RUBRICS.items():
        hits = [signal for signal in specification["signals"] if normalised(signal) in text]
        if key == "qualitative" and "qualitative" in approach:
            hits.append("declared qualitative approach")
        if key == "mixed_methods" and "mixed" in approach:
            hits.append("declared mixed-methods approach")
        if hits:
            detected.append({
                "key": key,
                "label": specification["label"],
                "signals": list(dict.fromkeys(hits))[:10],
                "expert_checks": list(specification["checks"]),
            })

    if not detected:
        generic_checks = [
            "coherence between research questions, design, sampling, data and analysis",
            "adequacy and transparency of data collection and analytical procedures",
            "assumptions, diagnostics and limitations appropriate to the selected method",
            "accuracy and proportionality of interpretation",
        ]
        detected.append({
            "key": "generic",
            "label": clean_text(declared_approach).title() or "Declared research approach",
            "signals": [clean_text(declared_approach)] if clean_text(declared_approach) else [],
            "expert_checks": generic_checks,
        })
    return {
        "detected_methods": detected,
        "instruction": (
            "Judge the actual adequacy and interpretation of these method-specific matters. "
            "Do not award credit merely because a technical term appears."
        ),
    }


def build_document_manifest(
    paragraphs: Sequence[Dict[str, Any]],
    *,
    summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    summary = summary or {}
    rows = annotate_evidence(paragraphs)
    toc_rows = [row for row in rows if _is_toc_row(row)]
    content_rows = [row for row in rows if not _is_toc_row(row)]
    word_count = sum(_word_count(_row_text(row)) for row in content_rows)
    character_count = sum(len(_row_text(row)) for row in content_rows)
    headings = [row for row in content_rows if row.get("is_heading")]
    detected_chapters = sorted({
        int(row["chapter_number"])
        for row in content_rows
        if isinstance(row.get("chapter_number"), int)
    })
    role_presence, role_chapters = _role_analysis(content_rows)
    inferred_metadata = infer_document_metadata(rows)

    chapter_map: List[Dict[str, Any]] = []
    for chapter in detected_chapters:
        chapter_rows = [row for row in content_rows if row.get("chapter_number") == chapter]
        chapter_headings = [
            {"evidence_id": row["evidence_id"], "text": _row_text(row)[:260]}
            for row in chapter_rows if row.get("is_heading")
        ]
        table_indexes = sorted({
            int(row["table_index"])
            for row in chapter_rows
            if isinstance(row.get("table_index"), int)
        })
        inferred_roles = [
            role for role, chapters in role_chapters.items() if chapter in chapters
        ]
        chapter_map.append({
            "chapter_number": chapter,
            "title": _chapter_title(content_rows, chapter),
            "paragraph_count": len(chapter_rows),
            "word_count": sum(_word_count(_row_text(row)) for row in chapter_rows),
            "table_count": len(table_indexes),
            "inferred_roles": inferred_roles,
            "headings": chapter_headings[:45],
        })

    table_indexes = sorted({
        int(row["table_index"])
        for row in content_rows
        if isinstance(row.get("table_index"), int)
    })
    figure_rows = [
        row for row in content_rows
        if re.match(r"^\s*(?:figure|fig\.)\s*\d", _row_text(row), flags=re.I)
    ]
    table_caption_rows = [
        row for row in content_rows
        if re.match(r"^\s*table\s*\d", _row_text(row), flags=re.I)
    ]
    appendix_rows = [
        row for row in content_rows
        if normalised(_row_text(row)).startswith(("appendix", "appendices"))
    ]

    presence_signals = _presence_signals(
        content_rows,
        role_presence,
        detected_chapters,
        inferred_metadata,
    )

    essential_roles = ("foundation", "literature_theory", "methodology", "results", "discussion", "conclusions")
    roles_present = sum(
        1 for role in essential_roles
        if role_presence.get(role, {}).get("status") == "present"
    )
    level = normalised(summary.get("academic_level", ""))
    if "phd" in level or "doctor" in level:
        minimum_words = 15000
    elif "master" in level or "mphil" in level:
        minimum_words = 8000
    else:
        minimum_words = 5000

    toc_chapters = sorted({
        chapter
        for row in toc_rows
        for chapter in [explicit_chapter_marker(_row_text(row))]
        if isinstance(chapter, int)
    })
    missing_from_body = sorted(set(toc_chapters) - set(detected_chapters))
    missing_from_toc = sorted(set(detected_chapters) - set(toc_chapters))
    if not toc_chapters:
        toc_status = "not_available"
    elif missing_from_body or missing_from_toc:
        toc_status = "mismatch"
    else:
        toc_status = "matched"
    toc_reconciliation = {
        "status": toc_status,
        "toc_chapters": toc_chapters,
        "body_chapters": detected_chapters,
        "toc_only_chapters": missing_from_body,
        "body_only_chapters": missing_from_toc,
        "toc_evidence_ids": [row["evidence_id"] for row in toc_rows[:40]],
    }

    warnings: List[str] = []
    if word_count < minimum_words:
        warnings.append(
            f"Only {word_count:,} extracted words were available, below the conservative {minimum_words:,}-word coverage check for the declared level."
        )
    if roles_present < 5:
        warnings.append(
            f"Only {roles_present} of 6 core research functions were confidently located."
        )
    if not detected_chapters:
        warnings.append("No chapter numbering was confidently detected; functional mapping was used instead.")
    if toc_status == "mismatch":
        warnings.append(
            "The table of contents and detected body chapters do not fully agree. "
            f"TOC-only chapters: {missing_from_body or 'none'}; body-only chapters: {missing_from_toc or 'none'}."
        )
    if len(headings) < 8:
        warnings.append("Few headings were extracted, which may indicate weak document structure or incomplete extraction.")
    if "quantitative" in normalised(summary.get("research_approach", "")) and not table_indexes:
        warnings.append("No structured DOCX tables were extracted from a declared quantitative submission.")

    if word_count < 2000 or roles_present < 3 or (len(content_rows) < 6 and word_count < 5000):
        coverage_status = "insufficient"
    elif word_count < minimum_words or roles_present < 5:
        coverage_status = "limited"
    else:
        coverage_status = "sufficient"

    pages = [int(row["page"]) for row in rows if isinstance(row.get("page"), int)]
    source_content_hash = stable_hash([
        {
            "evidence_id": row.get("evidence_id"),
            "chapter_number": row.get("chapter_number"),
            "heading": clean_text(row.get("heading", "")),
            "source_kind": row.get("source_kind"),
            "table_index": row.get("table_index"),
            "table_row": row.get("table_row"),
            "text": _row_text(row),
        }
        for row in rows
    ])
    manifest: Dict[str, Any] = {
        "manifest_version": "1.1",
        "source_content_hash": source_content_hash,
        "filename": clean_text(summary.get("filename", "")),
        "academic_level": clean_text(summary.get("academic_level", "")),
        "research_approach": clean_text(summary.get("research_approach", "")),
        "coverage_status": coverage_status,
        "coverage_score": round(
            min(1.0, word_count / max(1, minimum_words)) * 40
            + min(1.0, roles_present / 6) * 45
            + min(1.0, len(headings) / 20) * 15,
            1,
        ),
        "extraction_warnings": warnings,
        "paragraph_count": len(content_rows),
        "toc_entry_count": len(toc_rows),
        "word_count": word_count,
        "character_count": character_count,
        "page_count_detected": max(pages) if pages else None,
        "heading_count": len(headings),
        "table_count": len(table_indexes),
        "table_row_count": sum(1 for row in content_rows if row.get("source_kind") == "table_row"),
        "figure_caption_count": len(figure_rows),
        "table_caption_count": len(table_caption_rows),
        "appendix_heading_count": len(appendix_rows),
        "detected_chapters": detected_chapters,
        "chapter_count": len(detected_chapters),
        "chapter_map": chapter_map,
        "toc_reconciliation": toc_reconciliation,
        "role_presence": role_presence,
        "role_chapters": role_chapters,
        "presence_signals": presence_signals,
        "inferred_metadata": inferred_metadata,
        "method_rubric": build_method_rubric(
            content_rows,
            declared_approach=summary.get("research_approach", ""),
        ),
        "valid_evidence_ids": [row["evidence_id"] for row in rows],
        "annotated_source_rows": rows,
        "quality_rule": (
            "A component may be described as absent only when its status is confirmed_absent. "
            "The automated manifest uses not_confidently_located when evidence is insufficient, "
            "so uncertainty must never be converted into a finding of absence."
        ),
    }
    manifest["manifest_hash"] = stable_hash({
        key: value
        for key, value in manifest.items()
        if key not in {"valid_evidence_ids", "annotated_source_rows", "manifest_hash"}
    })
    return manifest


def _target_terms(target_roles: Sequence[str]) -> Tuple[str, ...]:
    terms: List[str] = []
    for role in target_roles:
        terms.extend(ROLE_SPECS.get(role, {}).get("terms", ()))
    return tuple(dict.fromkeys(terms))


def select_balanced_evidence(
    paragraphs: Sequence[Dict[str, Any]],
    manifest: Dict[str, Any],
    *,
    target_roles: Sequence[str],
    max_chars: int,
    concise: bool = False,
) -> List[Dict[str, Any]]:
    rows = annotate_evidence(paragraphs)
    target_chapters: List[int] = []
    for role in target_roles:
        target_chapters.extend(manifest.get("role_chapters", {}).get(role, []))
    target_chapters = list(dict.fromkeys(target_chapters))
    if not target_chapters:
        target_chapters = list(manifest.get("detected_chapters") or [])

    terms = _target_terms(target_roles)
    candidates: Dict[Optional[int], Dict[str, Tuple[float, Dict[str, Any]]]] = defaultdict(dict)

    def add(row: Dict[str, Any], score: float) -> None:
        text = _row_text(row)
        if not text:
            return
        chapter = row.get("chapter_number") if isinstance(row.get("chapter_number"), int) else None
        if target_chapters and chapter not in target_chapters and chapter is not None:
            return
        current = candidates[chapter].get(row["evidence_id"])
        if current is None or score > current[0]:
            candidates[chapter][row["evidence_id"]] = (score, row)

    for index, row in enumerate(rows):
        if _is_toc_row(row):
            continue
        text = _row_search_text(row)
        hits = _term_hits(text, terms)
        score = 0.0
        if row.get("is_heading"):
            score += 12.0
        if hits:
            score += 8.0 + 2.0 * min(5, len(hits))
        if row.get("source_kind") == "table_row":
            score += 5.0
        if re.match(r"^\s*(?:table|figure|fig\.)\s*\d", _row_text(row), flags=re.I):
            score += 8.0
        if index < 15 and "foundation" in target_roles:
            score += 3.0
        if score > 0:
            add(row, score)
            if row.get("is_heading"):
                for offset, bonus in ((1, 7.0), (2, 5.0), (3, 3.0)):
                    if index + offset < len(rows):
                        follower = rows[index + offset]
                        if follower.get("chapter_number") == row.get("chapter_number"):
                            add(follower, bonus)

    for chapter in target_chapters:
        chapter_rows = [
            row for row in rows
            if row.get("chapter_number") == chapter and not _is_toc_row(row)
        ]
        for row in chapter_rows[:3] + chapter_rows[-3:]:
            add(row, 2.0)

    if "foundation" in target_roles:
        for row in rows[:25]:
            if _is_toc_row(row):
                continue
            if row.get("chapter_number") is None or row.get("chapter_number") in target_chapters:
                add(row, 2.5)

    groups: Dict[Optional[int], List[Tuple[float, Dict[str, Any]]]] = {
        chapter: sorted(values.values(), key=lambda item: (-item[0], item[1].get("paragraph") or 0))
        for chapter, values in candidates.items()
    }
    ordered_groups: List[Optional[int]] = [chapter for chapter in target_chapters if chapter in groups]
    if None in groups:
        ordered_groups.append(None)
    for chapter in groups:
        if chapter not in ordered_groups:
            ordered_groups.append(chapter)

    selected: List[Dict[str, Any]] = []
    selected_ids = set()
    total = 0
    positions = {chapter: 0 for chapter in ordered_groups}
    text_limit = 900 if concise else 1500

    def serialise(row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": row["evidence_id"],
            "chapter_number": row.get("chapter_number"),
            "heading": clean_text(row.get("heading", ""))[:260],
            "page": row.get("page"),
            "paragraph": row.get("paragraph"),
            "source_kind": row.get("source_kind", "paragraph"),
            "table_index": row.get("table_index"),
            "table_row": row.get("table_row"),
            "text": _row_text(row)[:text_limit],
        }

    while ordered_groups:
        progressed = False
        for chapter in list(ordered_groups):
            position = positions[chapter]
            group = groups.get(chapter, [])
            if position >= len(group):
                ordered_groups.remove(chapter)
                continue
            positions[chapter] += 1
            row = group[position][1]
            if row["evidence_id"] in selected_ids:
                progressed = True
                continue
            item = serialise(row)
            size = len(str(item))
            if selected and total + size > max_chars:
                ordered_groups = []
                break
            selected.append(item)
            selected_ids.add(row["evidence_id"])
            total += size
            progressed = True
        if not progressed:
            break

    return selected


def compact_manifest_for_prompt(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Return a compact manifest without exposing uncited evidence tokens.

    Stage prompts provide their own bounded ``selected_source_evidence`` and
    ``allowed_evidence_ids``.  Repeating evidence IDs inside role-presence,
    metadata or TOC summaries can cause a model to cite an ID whose source text
    was not supplied in that stage.  The prompt manifest therefore retains the
    presence status and an evidence count, but not the raw identifiers.
    """

    role_presence: Dict[str, Any] = {}
    for role, raw in (manifest.get("role_presence") or {}).items():
        item = dict(raw or {})
        evidence_ids = item.pop("evidence_ids", []) or []
        item["evidence_count"] = len(evidence_ids)
        role_presence[role] = item

    presence_signals: Dict[str, Any] = {}
    for key, raw in (manifest.get("presence_signals") or {}).items():
        item = dict(raw or {})
        evidence_ids = item.pop("evidence_ids", []) or []
        item["evidence_count"] = len(evidence_ids)
        presence_signals[key] = item

    toc_reconciliation = dict(manifest.get("toc_reconciliation") or {})
    toc_evidence_ids = toc_reconciliation.pop("toc_evidence_ids", []) or []
    toc_reconciliation["toc_evidence_count"] = len(toc_evidence_ids)

    inferred_metadata = dict(manifest.get("inferred_metadata") or {})
    metadata_evidence = inferred_metadata.pop("evidence", {}) or {}
    inferred_metadata["evidence_available"] = {
        key: bool(value) for key, value in metadata_evidence.items()
    }

    return {
        "manifest_version": manifest.get("manifest_version"),
        "manifest_hash": manifest.get("manifest_hash"),
        "source_content_hash": manifest.get("source_content_hash"),
        "coverage_status": manifest.get("coverage_status"),
        "coverage_score": manifest.get("coverage_score"),
        "extraction_warnings": manifest.get("extraction_warnings"),
        "paragraph_count": manifest.get("paragraph_count"),
        "word_count": manifest.get("word_count"),
        "page_count_detected": manifest.get("page_count_detected"),
        "heading_count": manifest.get("heading_count"),
        "table_count": manifest.get("table_count"),
        "figure_caption_count": manifest.get("figure_caption_count"),
        "appendix_heading_count": manifest.get("appendix_heading_count"),
        "detected_chapters": manifest.get("detected_chapters"),
        "chapter_map": manifest.get("chapter_map"),
        "toc_reconciliation": toc_reconciliation,
        "role_presence": role_presence,
        "role_chapters": manifest.get("role_chapters"),
        "presence_signals": presence_signals,
        "inferred_metadata": inferred_metadata,
        "method_rubric": manifest.get("method_rubric"),
        "quality_rule": manifest.get("quality_rule"),
    }


def _sentences(value: str) -> List[str]:
    return [
        clean_text(item)
        for item in re.split(r"(?<=[.!?])\s+|\n+", clean_text(value))
        if clean_text(item)
    ]


def _claims_absence(sentence: str, alias: str) -> bool:
    value = normalised(sentence)
    target = normalised(alias)
    if not value or not target or target not in value:
        return False
    escaped = re.escape(target)
    absence = r"(?:missing|absent|not supplied|not provided|not presented|not reported|not stated|not included|not available|not identified|not located|could not be found|cannot be found|could not be located|cannot be located|entirely missing)"
    patterns = [
        rf"\b{escaped}\b\s+(?:is|are|was|were|remains|remain)?\s*{absence}",
        rf"\b{absence}\s+{escaped}\b",
        rf"\b(?:thesis|study|document|chapter|submission)\s+(?:does not|did not|fails to|failed to)\s+(?:include|provide|present|report|state|contain)\s+(?:a\s+|an\s+|the\s+)?{escaped}\b",
        rf"\b(?:thesis|study|document|chapter|submission)\s+lacks\s+(?:a\s+|an\s+|the\s+)?{escaped}\b",
        rf"\bthere\s+(?:is|are|was|were)\s+no\s+(?:clear\s+|formal\s+|substantive\s+|identifiable\s+)?{escaped}\b",
        rf"\b(?:thesis|study|document|chapter|submission)\s+(?:contains|provides|presents|reports)\s+no\s+(?:clear\s+|formal\s+|substantive\s+)?{escaped}\b",
        rf"\bno\s+evidence\s+of\s+(?:a\s+|an\s+|the\s+)?{escaped}\b",
    ]
    ambiguous_bare_no = {
        "result", "results", "finding", "findings", "empirical evidence",
        "discussion", "interpretation", "conclusion", "conclusions",
        "recommendation", "recommendations",
    }
    if target not in ambiguous_bare_no:
        patterns.append(
            rf"\bno\s+(?:clear\s+|formal\s+|substantive\s+|identifiable\s+)?{escaped}\b"
        )
    return any(re.search(pattern, value) for pattern in patterns)


def _walk_strings(value: Any, path: str = "") -> Iterable[Tuple[str, str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}" if path else str(key)
            yield from _walk_strings(item, child)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            child = f"{path}[{index}]"
            yield from _walk_strings(item, child)


def find_presence_contradictions(
    value: Any,
    manifest: Dict[str, Any],
    *,
    metadata: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    signals = dict(manifest.get("presence_signals") or {})
    supplied = metadata or {}
    for key in ("candidate_name", "candidate_number", "degree_programme", "institution", "thesis_title"):
        if clean_text(supplied.get(key)):
            signal = dict(signals.get(key) or {})
            signal["status"] = "present"
            signal["value"] = clean_text(supplied.get(key))
            signals[key] = signal

    aliases: Dict[str, Tuple[str, ...]] = {
        "conceptual_model": ("conceptual model", "conceptual framework"),
        "hypotheses": ("hypothesis", "hypotheses"),
        "research_paradigm_and_design": ("research paradigm", "research philosophy", "research design"),
        "sampling_and_data_collection": ("sampling", "sample size", "data collection"),
        "measurement_model": ("measurement model", "measurement-model", "indicator loading", "factor loading", "htmt", "fornell larcker"),
        "structural_model": ("structural model", "structural-model", "path coefficient", "bootstrapping", "r squared", "effect size"),
        "results": ("results", "findings", "empirical evidence"),
        "discussion": ("discussion", "interpretation"),
        "conclusions": ("conclusion", "conclusions"),
        "recommendations": ("recommendation", "recommendations"),
        "ethics": ("ethical clearance", "ethics", "ethical considerations", "ethical approval"),
        "references": ("references", "reference list", "bibliography"),
        "appendices": ("appendix", "appendices"),
        "research_instrument": ("questionnaire", "interview guide", "research instrument", "survey instrument"),
        "candidate_name": ("candidate name", "name of candidate"),
        "candidate_number": ("candidate number", "index number", "student number"),
        "degree_programme": ("degree programme", "programme"),
        "institution": ("institution", "university"),
        "thesis_title": ("thesis title", "dissertation title", "title of thesis"),
    }
    for chapter in manifest.get("detected_chapters") or []:
        aliases[f"chapter_{chapter}"] = (
            f"chapter {chapter}",
            f"chapter {['zero','one','two','three','four','five','six','seven','eight','nine','ten'][chapter] if 0 <= chapter <= 10 else chapter}",
        )

    contradictions: List[Dict[str, Any]] = []
    for path, text in _walk_strings(value):
        for sentence in _sentences(text):
            low = normalised(sentence)
            for key, terms in aliases.items():
                signal = signals.get(key) or {}
                status = signal.get("status")
                if status == "confirmed_absent":
                    continue
                matched_alias = next((term for term in terms if _claims_absence(sentence, term)), None)
                if matched_alias:
                    contradictions.append({
                        "path": path,
                        "component": key,
                        "sentence": sentence,
                        "manifest_status": status or "not_confidently_located",
                        "manifest_evidence_ids": signal.get("evidence_ids") or [],
                        "reason": (
                            "contradicts confirmed source presence"
                            if status == "present"
                            else "converts retrieval uncertainty into a claim of absence"
                        ),
                    })
    unique: List[Dict[str, Any]] = []
    seen = set()
    for item in contradictions:
        key = (item["path"], item["component"], normalised(item["sentence"]))
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def filter_contradicted_rows(
    rows: Sequence[Dict[str, Any]],
    manifest: Dict[str, Any],
    *,
    metadata: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    kept: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    for row in rows:
        contradictions = find_presence_contradictions(row, manifest, metadata=metadata)
        if contradictions:
            rejected.append({"row": row, "contradictions": contradictions})
        else:
            kept.append(row)
    return kept, rejected


def evidence_catalog(
    paragraphs: Sequence[Dict[str, Any]],
    evidence_ids: Iterable[str],
    *,
    text_limit: int = 1200,
) -> List[Dict[str, Any]]:
    wanted = set(clean_text(value) for value in evidence_ids if clean_text(value))
    if not wanted:
        return []
    output: List[Dict[str, Any]] = []
    for row in annotate_evidence(paragraphs):
        if row["evidence_id"] not in wanted:
            continue
        output.append({
            "id": row["evidence_id"],
            "chapter_number": row.get("chapter_number"),
            "heading": clean_text(row.get("heading", ""))[:260],
            "page": row.get("page"),
            "paragraph": row.get("paragraph"),
            "source_kind": row.get("source_kind", "paragraph"),
            "table_index": row.get("table_index"),
            "table_row": row.get("table_row"),
            "text": _row_text(row)[:text_limit],
        })
    return output


def _statistical_tokens(text: Any) -> List[str]:
    value = clean_text(text).replace(",", "")
    tokens = re.findall(
        r"(?<![A-Za-z0-9])[-+]?(?:\d+\.\d+|\.\d+|\d{3,})%?|(?<![A-Za-z0-9])\d+%(?![A-Za-z])",
        value,
    )
    output: List[str] = []
    for token in tokens:
        core = token.rstrip("%")
        try:
            number = float(core)
        except ValueError:
            continue
        if number.is_integer() and 1900 <= number <= 2100 and "%" not in token:
            continue
        if token not in output:
            output.append(token)
    return output


def _source_fact_sentences(text: str) -> List[str]:
    factual_terms = (
        "reported", "observed", "found", "showed", "indicated", "recorded",
        "sample", "respondent", "participant", "case", "usable", "retrieved",
        "coefficient", "loading", "estimate", "value", "score", "rate",
        "percentage", "mean", "median", "standard deviation", "p value",
        "p-value", "r squared", "r2", "r²", "bootstraps", "iterations",
    )
    return [
        sentence
        for sentence in _sentences(text)
        if any(term in normalised(sentence) for term in factual_terms)
    ]


def find_unsupported_numeric_claims(
    value: Any,
    paragraphs: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    lookup = {
        item["id"]: normalised(item.get("text", "")).replace(",", "")
        for item in evidence_catalog(
            paragraphs,
            collect_evidence_ids(value),
            text_limit=10000,
        )
    }
    issues: List[Dict[str, Any]] = []

    def walk(item: Any, path: str = "") -> None:
        if isinstance(item, dict):
            ids = [clean_text(entry) for entry in item.get("evidence_ids", []) if clean_text(entry)]
            if ids:
                evidence_text = " ".join(lookup.get(entry, "") for entry in ids)
                claim_fields = ("assessment", "strengths", "concerns", "issue")
                claim_text = " ".join(
                    clean_text(item.get(field, ""))
                    if not isinstance(item.get(field), list)
                    else " ".join(clean_text(entry) for entry in item.get(field, []))
                    for field in claim_fields
                )
                for sentence in _source_fact_sentences(claim_text):
                    for token in _statistical_tokens(sentence):
                        core = normalised(token.rstrip("%"))
                        if core and core not in evidence_text:
                            issues.append({
                                "path": path,
                                "token": token,
                                "sentence": sentence,
                                "evidence_ids": ids,
                            })
            for key, child in item.items():
                child_path = f"{path}.{key}" if path else str(key)
                walk(child, child_path)
        elif isinstance(item, list):
            for index, child in enumerate(item):
                walk(child, f"{path}[{index}]")

    walk(value)
    unique: List[Dict[str, Any]] = []
    seen = set()
    for issue in issues:
        key = (issue["path"], issue["token"], tuple(issue["evidence_ids"]))
        if key not in seen:
            seen.add(key)
            unique.append(issue)
    return unique


def find_unsupported_reference_risk_claims(
    value: Any,
    manifest: Dict[str, Any],
) -> List[Dict[str, Any]]:
    reference_ids = set(
        clean_text(entry)
        for entry in ((manifest.get("role_presence") or {}).get("references") or {}).get("evidence_ids", [])
        if clean_text(entry)
    )
    # The compact role manifest is intentionally capped for prompt size. For
    # source-integrity allegations, accept any exact reference-list evidence
    # from the full annotated source so late-list entries remain verifiable.
    for row in manifest.get("annotated_source_rows") or []:
        if not isinstance(row, dict):
            continue
        search_text = _row_search_text(row)
        heading_text = normalised(row.get("heading", ""))
        if (
            "references" in search_text
            or "bibliography" in search_text
            or "doi org" in search_text
            or "references" in heading_text
            or "bibliography" in heading_text
        ):
            item_id = clean_text(row.get("evidence_id"))
            if item_id:
                reference_ids.add(item_id)
    risk_terms = (
        "fabricated reference", "fabricated citation", "phantom reference",
        "fake reference", "future-dated reference", "future dated reference",
        "unverifiable reference", "non-existent reference", "nonexistent reference",
        "irrelevant reference", "reference is unreliable", "references are unreliable",
    )
    issues: List[Dict[str, Any]] = []

    def walk(item: Any, path: str = "") -> None:
        if isinstance(item, dict):
            ids = set(clean_text(entry) for entry in item.get("evidence_ids", []) if clean_text(entry))
            claim_text = " ".join(
                clean_text(item.get(field, ""))
                if not isinstance(item.get(field), list)
                else " ".join(clean_text(entry) for entry in item.get(field, []))
                for field in (
                    "assessment", "strengths", "concerns", "required_corrections",
                    "issue", "required_correction", "rationale",
                )
            )
            matched = [term for term in risk_terms if term in normalised(claim_text)]
            if matched and not ids.intersection(reference_ids):
                issues.append({
                    "path": path,
                    "terms": matched,
                    "evidence_ids": sorted(ids),
                })
            for key, child in item.items():
                child_path = f"{path}.{key}" if path else str(key)
                walk(child, child_path)
        elif isinstance(item, list):
            for index, child in enumerate(item):
                walk(child, f"{path}[{index}]")

    walk(value)
    return issues


def collect_evidence_ids(value: Any) -> List[str]:
    output: List[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "evidence_ids" and isinstance(item, list):
                output.extend(clean_text(entry) for entry in item if clean_text(entry))
            else:
                output.extend(collect_evidence_ids(item))
    elif isinstance(value, list):
        for item in value:
            output.extend(collect_evidence_ids(item))
    return list(dict.fromkeys(output))


def validate_evidence_ids(value: Any, allowed_ids: Iterable[str]) -> List[str]:
    allowed = set(allowed_ids)
    return [item for item in collect_evidence_ids(value) if item not in allowed]
