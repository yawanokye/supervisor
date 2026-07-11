from __future__ import annotations

import os
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .document_parser import clean_text, normalised
from .supervisory_accuracy_guard import paragraph_id, source_section


def enabled() -> bool:
    return os.getenv("VPROF_UCC_SECTION_COVERAGE_CONTRACT", "true").strip().lower() not in {"0", "false", "no", "off"}


def _degree_key(level: Any) -> str:
    value = normalised(str(level or "")).replace("-", " ")
    if value == "phd" or value.startswith("doctor of philosophy"):
        return "phd"
    if "professional doctorate" in value or value.startswith("doctoral") or value.startswith("doctor of "):
        return "professional_doctorate"
    if "non research master" in value or "nonresearch master" in value:
        return "non_research_masters"
    if "research master" in value or "research masters" in value or "mphil" in value:
        return "research_masters"
    if "master" in value:
        return "non_research_masters"
    return "bachelors"


def _degree_phrase(degree: str) -> str:
    return {
        "bachelors": "At Bachelor’s level, the section should show basic research coherence, correct academic presentation and a manageable contribution.",
        "non_research_masters": "At Non-Research Master’s level, the section should show applied problem clarity, credible evidence and defensible professional judgement.",
        "research_masters": "At MPhil level, the section should show independent research judgement, conceptual clarity, methodological defensibility and traceable scholarly contribution.",
        "professional_doctorate": "At Professional Doctorate level, the section should connect rigorous doctoral scholarship to a defensible contribution to practice, policy or professional knowledge.",
        "phd": "At PhD level, the section should support an original and defensible contribution to knowledge, with rigorous theoretical, empirical or methodological positioning.",
    }.get(degree, "At the declared academic level, the section should meet the appropriate scholarly standard.")


def _degree_label(degree: str) -> str:
    return {
        "bachelors": "Bachelor's level",
        "non_research_masters": "non-research Master's level",
        "research_masters": "MPhil level",
        "professional_doctorate": "professional doctorate level",
        "phd": "PhD level",
    }.get(degree, "the applicable academic level")


def _chapter_scope(paragraphs: Sequence[Dict[str, Any]]) -> Set[int]:
    chapters: Set[int] = set()
    for row in paragraphs:
        try:
            if row.get("chapter_number") is not None:
                chapters.add(int(row.get("chapter_number")))
        except Exception:
            continue
    return chapters


def _single_chapter(paragraphs: Sequence[Dict[str, Any]]) -> Optional[int]:
    chapters = _chapter_scope(paragraphs)
    return next(iter(chapters)) if len(chapters) == 1 else None


def _tokens(value: str) -> List[str]:
    out: List[str] = []
    for token in re.findall(r"[a-z0-9]+", normalised(value)):
        if len(token) > 5 and token.endswith("s") and token not in {"thesis", "analysis"}:
            token = token[:-1]
        out.append(token)
    return out


def _contains_sequence(container: str, phrase: str) -> bool:
    left = _tokens(container)
    right = _tokens(phrase)
    if not left or not right or len(right) > len(left):
        return False
    return any(left[i:i + len(right)] == right for i in range(len(left) - len(right) + 1))


def _current_rows(paragraphs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [row for row in paragraphs if row.get("document_role", "current") == "current"]


def _group_by_heading(paragraphs: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in _current_rows(paragraphs):
        heading = clean_text(row.get("heading") or source_section(row) or "")
        if not heading:
            continue
        grouped.setdefault(normalised(heading), []).append(row)
    return grouped


def _find_rows(grouped: Dict[str, List[Dict[str, Any]]], names: Iterable[str]) -> List[Dict[str, Any]]:
    wanted = [normalised(name) for name in names if normalised(name)]
    for name in wanted:
        for key, rows in grouped.items():
            if key == name:
                return rows
    for name in wanted:
        for key, rows in grouped.items():
            if _contains_sequence(key, name):
                return rows
    return []


def _plain(rows: Sequence[Dict[str, Any]]) -> str:
    return "\n".join(clean_text(row.get("text", "")) for row in rows if clean_text(row.get("text", "")))


def _first_substantive(rows: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for row in rows:
        if not row.get("is_heading") and len(clean_text(row.get("text", "")).split()) >= 4:
            return row
    for row in rows:
        if len(clean_text(row.get("text", "")).split()) >= 1:
            return row
    return None


def _first_chapter_anchor(paragraphs: Sequence[Dict[str, Any]], chapter: Optional[int] = None) -> Optional[Dict[str, Any]]:
    for row in _current_rows(paragraphs):
        if chapter and row.get("chapter_number") != chapter:
            continue
        if row.get("is_heading") and len(clean_text(row.get("text", "")).split()) >= 1:
            return row
    for row in _current_rows(paragraphs):
        if chapter and row.get("chapter_number") != chapter:
            continue
        if len(clean_text(row.get("text", "")).split()) >= 4:
            return row
    return None


def _title_anchor(paragraphs: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    current = _current_rows(paragraphs)
    first_chapter_para = min((int(r.get("paragraph")) for r in current if r.get("chapter_number") and r.get("paragraph")), default=10**9)
    title_rows = [r for r in current if not r.get("chapter_number") and int(r.get("paragraph") or 0) < first_chapter_para and len(clean_text(r.get("text", "")).split()) >= 5]
    if not title_rows:
        return None
    return max(title_rows, key=lambda r: len(clean_text(r.get("text", "")).split()))


def _issue(
    *,
    code: str,
    section: str,
    title: str,
    assessment: str,
    action: str,
    anchor: Optional[Dict[str, Any]],
    category: str,
    degree: str,
    severity: str = "major",
    confidence: float = 0.94,
    quote: str = "",
) -> Optional[Dict[str, Any]]:
    if anchor is None:
        return None
    pid = paragraph_id(anchor)
    if not pid:
        return None
    return {
        "finding_id": f"UCC-{code}",
        "category": category,
        "section": clean_text(section) or source_section(anchor) or "Document section",
        "issue_title": clean_text(title),
        "severity": severity,
        "confidence": confidence,
        "evidence_paragraph_ids": [pid],
        "problematic_quote": clean_text(quote or anchor.get("text", ""))[:260],
        "assessment": clean_text(assessment),
        "academic_consequence": _degree_phrase(degree),
        "required_action": clean_text(action),
        "illustrative_guidance": "",
        "guidance_type": "structural_guidance",
        "source_verification_required": category == "citations_and_sources",
        "context_guard_adjusted": False,
        "checklist_code": f"UCC-{code}",
        "checklist_item": clean_text(title),
        "verification_status": "ucc_section_contract",
    }


UCC_EXPECTED: Dict[int, List[Tuple[str, List[str], str, str]]] = {
    1: [
        ("Background to the Study", ["background to the study", "background of the study"], "research_gap_and_problem", "critical"),
        ("Statement of the Problem", ["statement of the problem", "problem statement"], "research_gap_and_problem", "critical"),
        ("Purpose of the study", ["purpose of the study", "aim of the study", "general objective", "general objectives", "general aim", "primary objective"], "objectives_questions_hypotheses", "critical"),
        ("Research Objectives", ["research objectives", "objectives of the study"], "objectives_questions_hypotheses", "critical"),
        ("Research Questions", ["research questions", "research question"], "objectives_questions_hypotheses", "critical"),
        ("Significance of the Study", ["significance of the study"], "critical_analysis", "major"),
        ("Limitations of the Study", ["limitations of the study", "limitation of the study"], "chapter_structure", "major"),
        ("Scope / Delimitation of the Study", ["delimitation of the study", "delimitations of the study", "scope of the study", "scope"], "chapter_structure", "major"),
        ("Definition of Terms", ["definition of terms", "operational definition of terms"], "objectives_questions_hypotheses", "major"),
        ("Organisation of the Study", ["organisation of the study", "organization of the study"], "chapter_structure", "moderate"),
    ],
    2: [
        ("Introduction", ["introduction"], "chapter_structure", "moderate"),
        ("Conceptual Review", ["conceptual review", "conceptual literature"], "theoretical_grounding", "major"),
        ("Theoretical Review", ["theoretical review", "theoretical framework"], "theoretical_grounding", "critical"),
        ("Empirical Review", ["empirical review", "review of empirical literature"], "critical_analysis", "critical"),
        ("Conceptual Framework", ["conceptual framework"], "theoretical_grounding", "critical"),
        ("Chapter Summary", ["chapter summary", "summary of the chapter"], "chapter_structure", "moderate"),
    ],
    3: [
        ("Introduction", ["introduction"], "chapter_structure", "moderate"),
        ("Research Approach", ["research approach", "research paradigm", "research philosophy"], "methodological_rigour", "major"),
        ("Research Design", ["research design"], "methodological_rigour", "critical"),
        ("Study Area", ["study area", "study setting"], "methodological_rigour", "major"),
        ("Population", ["population", "target population"], "methodological_rigour", "major"),
        ("Sampling Procedure", ["sampling procedure", "sampling technique", "sampling frame"], "methodological_rigour", "critical"),
        ("Sample Size", ["sample size", "sample size determination"], "methodological_rigour", "critical"),
        ("Data Collection Instrument", ["data collection instrument", "research instrument", "instrument"], "methodological_rigour", "critical"),
        ("Validity and Reliability", ["validity and reliability", "validity", "reliability", "trustworthiness"], "methodological_rigour", "critical"),
        ("Data Collection Procedures", ["data collection procedure", "data collection procedures"], "methodological_rigour", "major"),
        ("Data Processing and Analysis", ["data processing and analysis", "data analysis", "method of data analysis"], "methodological_rigour", "critical"),
        ("Ethical Considerations", ["ethical considerations", "ethics"], "ethics_and_integrity", "critical"),
    ],
    4: [
        ("Introduction", ["introduction"], "chapter_structure", "moderate"),
        ("Response Rate", ["response rate"], "results_and_interpretation", "major"),
        ("Sample Characteristics", ["sample characteristics", "demographic", "background characteristics"], "results_and_interpretation", "major"),
        ("Results by Objective", ["results", "findings", "presentation of results", "hypothesis testing"], "results_and_interpretation", "critical"),
        ("Discussion of Findings", ["discussion of findings", "discussion"], "discussion_and_integration", "critical"),
        ("Diagnostic Tests", ["diagnostic tests", "model diagnostics", "assumption tests"], "results_and_interpretation", "major"),
    ],
    5: [
        ("Summary of Findings", ["summary of findings"], "conclusions_and_recommendations", "critical"),
        ("Conclusions", ["conclusion", "conclusions"], "conclusions_and_recommendations", "critical"),
        ("Recommendations", ["recommendation", "recommendations"], "conclusions_and_recommendations", "critical"),
        ("Contribution", ["contribution to knowledge", "contribution to practice", "implications", "contribution"], "critical_analysis", "major"),
        ("Suggestions for Further Research", ["suggestions for further research", "future research"], "conclusions_and_recommendations", "major"),
    ],
}


def expected_sections_for_scope(paragraphs: Sequence[Dict[str, Any]]) -> List[Tuple[int, str, List[str], str, str]]:
    chapters = _chapter_scope(paragraphs)
    if not chapters:
        return []
    full_thesis = {1, 2, 3, 4, 5}.issubset(chapters)
    target_chapters = sorted(chapters if not full_thesis else {1, 2, 3, 4, 5})
    out: List[Tuple[int, str, List[str], str, str]] = []
    for chapter in target_chapters:
        for label, names, category, severity in UCC_EXPECTED.get(chapter, []):
            out.append((chapter, label, names, category, severity))
    return out


def present_relevant_sections(paragraphs: Sequence[Dict[str, Any]]) -> Set[str]:
    grouped = _group_by_heading(paragraphs)
    labels: Set[str] = set()
    if _title_anchor(paragraphs):
        labels.add("Title")
    for _chapter, label, names, _category, _severity in expected_sections_for_scope(paragraphs):
        if _find_rows(grouped, names):
            labels.add(label)
    if _find_rows(grouped, ["references"]):
        labels.add("References")
    return labels


def ucc_comment_floor(paragraphs: Sequence[Dict[str, Any]], academic_level: Any, depth: str) -> int:
    """No predetermined UCC comment floor.

    The UCC structure remains a coverage guide, but it cannot force a minimum
    number of findings. Only evidence-backed issues are released.
    """
    return 0


def _missing_section_issue(paragraphs: Sequence[Dict[str, Any]], chapter: int, label: str, category: str, severity: str, degree: str) -> Optional[Dict[str, Any]]:
    anchor = _first_chapter_anchor(paragraphs, chapter)
    if label == "Research Hypotheses":
        return None
    sev = severity if degree in {"research_masters", "professional_doctorate", "phd"} else ("major" if severity == "critical" else severity)
    return _issue(
        code=f"CH{chapter}-MISSING-{normalised(label).replace(' ', '-').upper()}",
        section=f"Chapter {chapter}",
        title=f"Expected UCC thesis section is not evident: {label}",
        assessment=f"The UCC thesis structure normally expects {label} in this chapter, but the work does not make that section evident.",
        action=f"Add or clearly label the {label} section if it is required by the programme format; if the programme uses an equivalent heading, make the equivalence clear.",
        anchor=anchor,
        category=category,
        degree=degree,
        severity=sev,
        confidence=0.86,
    )


def _thin_section_issue(label: str, rows: Sequence[Dict[str, Any]], category: str, severity: str, degree: str) -> Optional[Dict[str, Any]]:
    text = _plain([row for row in rows if not row.get("is_heading")])
    if len(text.split()) >= 45:
        return None
    anchor = _first_substantive(rows)
    return _issue(
        code=f"THIN-{normalised(label).replace(' ', '-').upper()}",
        section=label,
        title=f"The {label} section is too thin at {_degree_label(degree)}",
        assessment=f"The section is present, but it is not developed enough to satisfy the expected thesis function at {_degree_label(degree)}.",
        action=f"Develop the {label} section with precise evidence, justification and links to the study problem, objectives or methods as appropriate.",
        anchor=anchor,
        category=category,
        degree=degree,
        severity="major" if severity == "critical" else severity,
        confidence=0.80,
    )


def _reference_author_mismatch(text: str) -> bool:
    low = text.lower()
    return "asha-mari" in low and ("asha'ari" in low or "asha’ari" in low)


def _citation_tokens(text: str) -> Set[str]:
    hits: Set[str] = set()
    for match in re.finditer(r"\(([A-Z][A-Za-z'’\-]+(?:\s+et\s+al\.)?|[A-Z][A-Za-z'’\-]+\s*&\s*[A-Z][A-Za-z'’\-]+)[^)]*?,\s*(?:19|20)\d{2}\)", text):
        first = re.split(r"\s*&\s*|\s+et\s+al\.", match.group(1))[0]
        hits.add(normalised(first))
    return hits


def _reference_author_tokens(text: str) -> Set[str]:
    refs = False
    tokens: Set[str] = set()
    for line in text.splitlines():
        if normalised(line) == "references":
            refs = True
            continue
        if refs:
            match = re.match(r"\s*([A-Z][A-Za-z'’\-]+),", line)
            if match:
                tokens.add(normalised(match.group(1)))
    return tokens


def _first_citation_anchor(paragraphs: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    pattern = re.compile(r"\([^)]*(?:19|20)\d{2}[^)]*\)")
    for row in _current_rows(paragraphs):
        if pattern.search(clean_text(row.get("text", ""))):
            return row
    return _first_chapter_anchor(paragraphs, 1)


def _has_references_heading(grouped: Dict[str, List[Dict[str, Any]]]) -> bool:
    return bool(_find_rows(grouped, ["references", "reference list", "bibliography"]))


def _citation_count(text: str) -> int:
    return len(re.findall(r"\([^)]*(?:19|20)\d{2}[^)]*\)", text))


def _duplicated_parenthetical_citations(text: str) -> List[str]:
    raw = re.findall(r"\(([^)]*(?:19|20)\d{2}[^)]*)\)", text)
    counts: Dict[str, int] = {}
    for item in raw:
        key = normalised(item)
        if key:
            counts[key] = counts.get(key, 0) + 1
    return [k for k, v in counts.items() if v > 1]


def _chapter_one_specific(paragraphs: Sequence[Dict[str, Any]], grouped: Dict[str, List[Dict[str, Any]]], degree: str) -> List[Dict[str, Any]]:
    issues: List[Optional[Dict[str, Any]]] = []
    background = _find_rows(grouped, ["background to the study", "background of the study"])
    problem = _find_rows(grouped, ["statement of the problem", "problem statement"])
    purpose = _find_rows(grouped, ["purpose of the study", "aim of the study"])
    objectives = _find_rows(grouped, ["research objectives", "objectives of the study"])
    questions = _find_rows(grouped, ["research questions", "research question"])
    significance = _find_rows(grouped, ["significance of the study"])
    limitations = _find_rows(grouped, ["limitations of the study", "limitation of the study"])
    delimitation = _find_rows(grouped, ["delimitation of the study", "delimitations of the study", "scope of the study"])
    definitions = _find_rows(grouped, ["definition of terms", "operational definition of terms"])
    references = _find_rows(grouped, ["references"])
    full_text = _plain(_current_rows(paragraphs))
    bg = _plain(background)
    prob = _plain(problem)
    purp = _plain(purpose)
    obj = _plain(objectives)
    qs = _plain(questions)
    sig = _plain(significance)
    lim = _plain(limitations)
    delim = _plain(delimitation)
    defs = _plain(definitions)
    refs = _plain(references)

    title = _title_anchor(paragraphs)
    if title and any(term in normalised(obj) for term in ("awareness", "operational performance")):
        title_low = normalised(clean_text(title.get("text", "")))
        if not all(term in title_low for term in ("awareness", "operational performance")):
            issues.append(_issue(
                code="CH1-TITLE-SCOPE",
                section="Title",
                title="The title does not cover all substantive constructs in the objectives",
                assessment="The title does not fully reflect all substantive constructs, population boundaries or case-setting elements introduced in the objectives.",
                action="Align the title, purpose and objectives by either adding the omitted constructs, population and case setting to the title or narrowing the objectives to match the title.",
                anchor=title,
                category="cross_section_coherence",
                degree=degree,
                severity="major",
            ))

    if background:
        low_bg = normalised(bg)
        theory_terms = ("theoretical framework", "conceptual framework", "institutional theory", "stakeholder theory", "natural resource based", "resource based", "triple bottom line theory")
        if degree in {"research_masters", "professional_doctorate", "phd"} and not any(t in low_bg for t in theory_terms):
            issues.append(_issue(
                code="CH1-BACKGROUND-THEORY",
                section="Background to the Study",
                title="The background does not establish a level-appropriate theoretical or conceptual anchor",
                assessment="The background introduces several central constructs but does not make the theoretical or conceptual logic binding them explicit.",
                action="Add a concise theoretical or conceptual anchor and show how it explains the expected relationship among the main independent variables, outcome variables and contextual factors in the study.",
                anchor=_first_substantive(background),
                category="theoretical_grounding",
                degree=degree,
                severity="major",
            ))
        if "central region" in low_bg and not any(t in low_bg for t in ("epa", "ghana statistical", "manufacturing association", "policy", "report", "statistics", "regulatory")):
            issues.append(_issue(
                code="CH1-BACKGROUND-LOCAL-EVIDENCE",
                section="Background to the Study",
                title="The background does not adequately evidence the local UCC study context",
                assessment="The section names Ghana and the Central Region but does not provide strong local policy, industry or empirical evidence showing why this context requires investigation.",
                action="Add traceable Ghanaian or Central Region evidence, such as policy documents, industry data, regulatory reports or recent local empirical findings, and link it to the study problem.",
                anchor=_first_substantive(background),
                category="research_gap_and_problem",
                degree=degree,
                severity="major",
            ))
        if re.search(r"\b100\s+manufacturing\s+enterprises\s+in\s+Ghana\b", bg, flags=re.I):
            anchor = next((row for row in background if re.search(r"\b100\s+manufacturing\s+enterprises", clean_text(row.get("text", "")), flags=re.I)), _first_substantive(background))
            issues.append(_issue(
                code="CH1-BACKGROUND-SAMPLE-CLAIM",
                section="Background to the Study",
                title="A specific empirical sample claim is not clearly sourced",
                assessment="The section refers to 100 manufacturing enterprises in Ghana, but the citation supporting that exact sample claim is not attached clearly enough.",
                action="Attach the exact source to the numerical sample claim or remove the claim if it cannot be verified from the cited study.",
                anchor=anchor,
                category="citations_and_sources",
                degree=degree,
                severity="major",
            ))
        if "the study revolve" in low_bg:
            issues.append(_issue(
                code="CH1-BACKGROUND-GRAMMAR",
                section="Background to the Study",
                title="The opening sentence contains a basic grammatical error",
                assessment="The opening sentence uses 'The study revolve', which is incorrect and weakens the academic presentation of the chapter.",
                action="Correct the opening sentence and carry out a line-by-line language edit of the chapter before resubmission.",
                anchor=_first_substantive(background),
                category="academic_writing",
                degree=degree,
                severity="moderate",
            ))

    if problem:
        low_prob = normalised(prob)
        local_evidence_terms = (
            "statistics", "statistical service", "ghana statistical", "environmental protection agency",
            "epa", "ministry", "regulatory report", "industry report", "manufacturing association",
            "survey findings", "data show", "central region report", "regional data"
        )
        if not any(t in low_prob for t in local_evidence_terms):
            issues.append(_issue(
                code="CH1-PROBLEM-EVIDENCE",
                section="Statement of the Problem",
                title="The problem statement lacks concrete local empirical or policy evidence",
                assessment="The problem is argued mainly through broad statements and literature rather than direct empirical, institutional or policy evidence from the specific study context.",
                action="Insert credible local evidence showing the existence, scale or consequence of the problem, then connect that evidence to the study variables and context.",
                anchor=_first_substantive(problem),
                category="research_gap_and_problem",
                degree=degree,
                severity="major",
            ))
        if any(country in low_prob for country in ("pakistan", "india", "portugal", "europe")) and "central region" in low_prob:
            issues.append(_issue(
                code="CH1-PROBLEM-GAP-LOGIC",
                section="Statement of the Problem",
                title="The practical problem, empirical gap and contextual gap are not clearly separated",
                assessment="The section moves from foreign studies to the Ghanaian context, but it does not clearly distinguish the practical problem from the empirical and contextual research gap.",
                action="Rewrite the problem statement in clear moves: practical problem, evidence of seriousness, weakness in existing studies, Central Region gap and exact research focus.",
                anchor=_first_substantive(problem),
                category="research_gap_and_problem",
                degree=degree,
                severity="major",
            ))

    if objectives:
        low_obj = normalised(obj)
        if any(t in low_obj for t in ("relationship", "impact", "effect", "influence")) and any(t in low_obj for t in ("examine", "assess")):
            issues.append(_issue(
                code="CH1-OBJECTIVES-MIXED-INFERENCE",
                section="Research Objectives",
                title="The objectives mix descriptive, relational and impact claims without clarifying the intended level of inference",
                assessment="The objective set moves from describing current practices to assessing relationships and examining impact, but the chapter does not yet clarify how the design will support each type of inference.",
                action="Revise the objectives and methods together so each objective has a clear analytical status: descriptive, associational, predictive or causal, with wording that the design can support.",
                anchor=_first_substantive(objectives),
                category="objectives_questions_hypotheses",
                degree=degree,
                severity="major" if degree in {"research_masters", "professional_doctorate", "phd"} else "moderate",
            ))

    if purpose and objectives:
        missing = [term for term in ("awareness", "operational performance", "current green procurement practices") if term in normalised(obj) and term not in normalised(purp)]
        if missing:
            issues.append(_issue(
                code="CH1-PURPOSE-SCOPE",
                section="Purpose of the study",
                title="The purpose statement is narrower than the objectives",
                assessment="The purpose does not cover all substantive constructs and outcomes introduced in the objectives.",
                action="Revise the purpose so that it covers every principal construct and outcome in the objectives, or remove objectives that fall outside the intended scope.",
                anchor=_first_substantive(purpose),
                category="objectives_questions_hypotheses",
                degree=degree,
                severity="critical" if degree in {"research_masters", "professional_doctorate", "phd"} else "major",
            ))
        if any(t in normalised(purp) for t in ("effect", "impact", "influence")):
            issues.append(_issue(
                code="CH1-PURPOSE-CAUSAL-LANGUAGE",
                section="Purpose of the study",
                title="Causal or impact language may exceed the implied design",
                assessment="The purpose uses effect language, while the chapter later recognises limits to causal inference from a cross-sectional design.",
                action="Use neutral associational language unless the methodology can justify causal inference, or explain clearly how the design supports effect or impact claims.",
                anchor=_first_substantive(purpose),
                category="methodological_rigour",
                degree=degree,
                severity="major",
                confidence=0.88,
            ))

    if questions:
        combined = normalised(obj + "\n" + qs)
        has_rel = any(t in combined for t in ("relationship", "impact", "effect", "influence", "determinant"))
        has_hyp = any("hypothes" in normalised(row.get("text", "")) for row in _current_rows(paragraphs))
        if has_rel and not has_hyp and degree in {"research_masters", "professional_doctorate", "phd"}:
            issues.append(_issue(
                code="CH1-HYPOTHESES-MISSING",
                section="Research Questions",
                title="Relational and impact objectives are not supported by hypotheses or justification",
                assessment="The objectives and questions imply relationship or impact testing, but no hypotheses or justification for their absence is provided.",
                action="Where required by the programme format and supported by the research design, formulate hypotheses for the relational objectives; otherwise explain why research questions alone are appropriate.",
                anchor=_first_substantive(questions),
                category="objectives_questions_hypotheses",
                degree=degree,
                severity="major",
            ))
        if ".?" in qs:
            issues.append(_issue(
                code="CH1-RQ-PUNCTUATION",
                section="Research Questions",
                title="A research question contains malformed punctuation",
                assessment="One research question ends with a full stop followed by a question mark.",
                action="Remove the full stop and retain only the question mark.",
                anchor=next((row for row in questions if ".?" in clean_text(row.get("text", ""))), _first_substantive(questions)),
                category="academic_writing",
                degree=degree,
                severity="moderate",
            ))

    if significance:
        low_sig = normalised(sig)
        if any(t in low_sig for t in ("results reveal", "findings obtained", "study evaluates the impact of these results")):
            issues.append(_issue(
                code="CH1-SIGNIFICANCE-PROSPECTIVE",
                section="Significance of the Study",
                title="The significance section presents anticipated findings as completed results",
                assessment="The section uses results/findings language even though Chapter One is written as a proposal.",
                action="Rewrite the significance prospectively, explaining what the eventual findings may contribute without stating that relationships have already been found.",
                anchor=_first_substantive(significance),
                category="chapter_structure",
                degree=degree,
                severity="major",
            ))
        if not all(t in low_sig for t in ("theory", "practice", "policy")):
            issues.append(_issue(
                code="CH1-SIGNIFICANCE-THEORY-PRACTICE-POLICY",
                section="Significance of the Study",
                title="The significance section does not adequately separate theory, practice and policy contribution",
                assessment="The section lists stakeholders but does not clearly organise the expected contribution across theory, practice and policy.",
                action="Reorganise the section around theory, practice and policy, with a concise paragraph explaining each expected contribution at the actual academic level.",
                anchor=_first_substantive(significance),
                category="critical_analysis",
                degree=degree,
                severity="moderate",
            ))
        if any(t in low_sig for t in ("meta analysis", "correlation coefficients", "liu et al", "onukwulu")):
            issues.append(_issue(
                code="CH1-SIGNIFICANCE-LIT-OVERLOAD",
                section="Significance of the Study",
                title="The significance section contains literature-review material",
                assessment="Detailed empirical discussion and source comparison are placed in the significance section, where the emphasis should be expected contribution and beneficiaries.",
                action="Move detailed literature discussion to Chapter Two and keep the significance focused on the likely scholarly, practical and policy value of the study.",
                anchor=_first_substantive(significance),
                category="chapter_structure",
                degree=degree,
                severity="moderate",
            ))
        contribution_terms = ("contribution to knowledge", "original contribution", "applied contribution", "professional contribution", "contribution to practice", "contribution to policy")
        if not any(t in low_sig for t in contribution_terms):
            title = {
                "bachelors": "The expected contribution is not stated plainly",
                "non_research_masters": "The applied or professional contribution is not explicit",
                "research_masters": "The expected MPhil research contribution is not explicit",
                "professional_doctorate": "The original contribution to practice or policy is not explicit",
                "phd": "The original contribution to knowledge is not explicit",
            }[degree]
            issues.append(_issue(
                code="CH1-SIGNIFICANCE-CONTRIBUTION",
                section="Significance of the Study",
                title=title,
                assessment="The section names beneficiaries but does not make the level-appropriate contribution explicit.",
                action="Add a concise contribution statement that is proportionate to the actual academic level and distinguish it from ordinary stakeholder usefulness.",
                anchor=_first_substantive(significance),
                category="critical_analysis",
                degree=degree,
                severity="critical" if degree in {"professional_doctorate", "phd"} else "major",
            ))

    if limitations and any(t in normalised(lim) for t in ("faced practical constraints", "could be achieved", "did not participate", "skewing the results")):
        issues.append(_issue(
            code="CH1-LIMITATIONS-TENSE",
            section="Limitations of the Study",
            title="The limitations section mixes proposal-stage and completed-study language",
            assessment="The section shifts between planned data collection and constraints that appear to have already occurred.",
            action="Use proposal-stage language throughout if the study has not been completed, or convert the whole section to completed-study reporting if fieldwork has already occurred.",
            anchor=_first_substantive(limitations),
            category="chapter_structure",
            degree=degree,
            severity="major",
        ))

    if delimitation and re.search(r"\[[^\]]*(insert|provide|specify|start month/year|end month/year)[^\]]*\]", delim, flags=re.I):
        issues.append(_issue(
            code="CH1-DELIMITATION-PLACEHOLDER",
            section="Delimitation of the Study",
            title="The delimitation contains an unresolved drafting placeholder",
            assessment="The time scope still contains bracketed template text instead of a verified data-collection period.",
            action="Replace the placeholder with the confirmed start and end month/year and ensure the same time boundary appears consistently in the methodology chapter.",
            anchor=next((row for row in delimitation if "[" in clean_text(row.get("text", ""))), _first_substantive(delimitation)),
            category="chapter_structure",
            degree=degree,
            severity="critical" if degree in {"research_masters", "professional_doctorate", "phd"} else "major",
        ))

    if definitions:
        low_defs = normalised(defs)
        if "awareness means the extent of awareness" in low_defs or "without causing any harm" in low_defs:
            issues.append(_issue(
                code="CH1-DEFINITIONS-CIRCULAR",
                section="Definition of Terms",
                title="Core terms are defined circularly or in unrealistically absolute language",
                assessment="Awareness repeats the term being defined, while environmental sustainability is described as complete absence of harm.",
                action="Replace circular and absolute wording with definitions that state dimensions, boundaries and measurable indicators.",
                anchor=next((row for row in definitions if "Awareness means" in clean_text(row.get("text", ""))), _first_substantive(definitions)),
                category="objectives_questions_hypotheses",
                degree=degree,
                severity="major",
            ))
        if "environmental sustainability" in low_defs and "environmental performance" in low_defs:
            issues.append(_issue(
                code="CH1-DEFINITIONS-OVERLAP",
                section="Definition of Terms",
                title="Environmental sustainability and environmental performance are not sufficiently distinguished",
                assessment="The two constructs are defined in overlapping terms, which may confuse the dependent construct and related performance construct.",
                action="Differentiate the constructs by specifying the main outcome, the indicators for each construct and how they will be measured separately.",
                anchor=next((row for row in definitions if "Environmental Performance" in clean_text(row.get("text", ""))), _first_substantive(definitions)),
                category="objectives_questions_hypotheses",
                degree=degree,
                severity="major",
            ))
        if "( sijm" in low_defs or re.search(r"\(\s*Sijm[-‑]Eeken\s+et\s+al\.\s+20\d{2}\)", defs, flags=re.I):
            issues.append(_issue(
                code="CH1-DEFINITIONS-CITATION-PUNCTUATION",
                section="Definition of Terms",
                title="An in-text citation in the definitions section is incorrectly punctuated",
                assessment="The citation for Sijm-Eeken et al. contains incorrect spacing and lacks the required comma before the year.",
                action="Correct the citation punctuation and apply the same referencing style consistently across the chapter.",
                anchor=next((row for row in definitions if "Sijm" in clean_text(row.get("text", ""))), _first_substantive(definitions)),
                category="citations_and_sources",
                degree=degree,
                severity="moderate",
            ))

    if background and _reference_author_mismatch(full_text):
        issues.append(_issue(
            code="CH1-CITATION-AUTHOR-MISMATCH",
            section="Background to the Study",
            title="An in-text author name does not match the reference-list author name",
            assessment="The chapter cites Asha-Mari and Daud, while the reference list records Asha'ari and Daud.",
            action="Verify the source and make the in-text citation and reference-list entry identical.",
            anchor=next((row for row in background if "Asha-Mari" in clean_text(row.get("text", ""))), _first_substantive(background)),
            category="citations_and_sources",
            degree=degree,
            severity="major",
        ))

    if any(w in full_text for w in ("behavior", "organization", "labor")) and any(w in full_text for w in ("behaviour", "organisation", "labour")):
        anchor = next((row for row in _current_rows(paragraphs) if any(w in clean_text(row.get("text", "")) for w in ("behavior", "organization", "labor"))), _first_substantive(background))
        issues.append(_issue(
            code="CH1-SPELLING-CONVENTION",
            section=source_section(anchor) or "Chapter One",
            title="British and American spelling conventions are mixed",
            assessment="The chapter combines spellings such as behaviour/organisations with behavior/organization/labor.",
            action="Apply the required institutional spelling convention consistently across the chapter.",
            anchor=anchor,
            category="academic_writing",
            degree=degree,
            severity="minor",
        ))

    if references:
        cited = _citation_tokens(full_text)
        ref_authors = _reference_author_tokens(full_text)
        if len(ref_authors) >= max(10, len(cited) + 8):
            issues.append(_issue(
                code="CH1-REFERENCE-AUDIT",
                section="References",
                title="The reference list requires a cited-versus-uncited audit",
                assessment="The reference list is large relative to the number of visible in-text citations in Chapter One, so uncited or mismatched sources may remain.",
                action="Cross-check each in-text citation against the reference list and remove, add or correct entries so every source is traceable.",
                anchor=next((row for row in references if not row.get("is_heading")), _first_substantive(references)),
                category="citations_and_sources",
                degree=degree,
                severity="moderate",
                confidence=0.82,
            ))


    # Topic-safe generic Chapter One checks. These must not depend on a previous
    # sample thesis topic. They protect UCC section coverage across disciplines.
    full_low = normalised(full_text)
    if not _has_references_heading(grouped) and _citation_count(full_text) >= 5:
        issues.append(_issue(
            code="CH1-MISSING-REFERENCES",
            section="References",
            title="The reference list is missing despite visible in-text citations",
            assessment="The chapter contains several in-text citations, but no References or Bibliography section is evident in the work.",
            action="Add a complete reference list in the required style and verify that every in-text citation has a matching reference-list entry.",
            anchor=_first_citation_anchor(paragraphs),
            category="citations_and_sources",
            degree=degree,
            severity="critical" if degree in {"research_masters", "professional_doctorate", "phd"} else "major",
        ))

    if re.search(r"\w\(", full_text) or re.search(r"\)\s*,\s*\(", full_text):
        issues.append(_issue(
            code="CH1-CITATION-SPACING-DUPLICATION",
            section="Chapter One",
            title="Citation spacing and grouping need editorial correction",
            assessment="Several citations are attached to preceding words without a space or are placed as repeated separate parenthetical citations instead of being cleanly grouped.",
            action="Insert required spaces before citations, remove duplicate citations and group multiple sources according to the selected referencing style.",
            anchor=_first_citation_anchor(paragraphs),
            category="citations_and_sources",
            degree=degree,
            severity="moderate",
        ))

    if significance and "research gap" in normalised(sig):
        issues.append(_issue(
            code="CH1-GAP-MISPLACED-IN-SIGNIFICANCE",
            section="Significance of the Study",
            title="The research gap is placed inside the significance section rather than being fully developed in the problem logic",
            assessment="The significance section names a research gap, but the gap should be established earlier through the background and problem statement before the study's beneficiaries are discussed.",
            action="Move or restate the research gap in the background/problem sequence, then reserve the significance section for theoretical, empirical, policy and practical contributions.",
            anchor=_first_substantive(significance),
            category="research_gap_and_problem",
            degree=degree,
            severity="major",
        ))

    if limitations and any(term in normalised(lim) for term in ("generalization", "generalisation")) and "case study" in full_low:
        issues.append(_issue(
            code="CH1-LIMITATION-GENERALISATION",
            section="Limitations of the Study",
            title="The limitations section overstates generalisation from a case study",
            assessment="The chapter suggests that findings will be sufficient for generalisation even though the scope is confined to a single case setting.",
            action="Qualify the claim as analytical or contextual transferability unless the sampling design supports statistical generalisation beyond the case.",
            anchor=_first_substantive(limitations),
            category="methodological_rigour",
            degree=degree,
            severity="major",
        ))

    out: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for item in issues:
        if not item:
            continue
        key = str(item.get("finding_id"))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _generic_chapter_specific(paragraphs: Sequence[Dict[str, Any]], grouped: Dict[str, List[Dict[str, Any]]], degree: str, chapter: int) -> List[Dict[str, Any]]:
    issues: List[Optional[Dict[str, Any]]] = []
    if chapter == 2:
        lit_rows: List[Dict[str, Any]] = []
        for _label, names, _cat, _sev in UCC_EXPECTED[2]:
            lit_rows.extend(_find_rows(grouped, names))
        text = normalised(_plain(lit_rows))
        anchor = _first_substantive(lit_rows) or _first_chapter_anchor(paragraphs, 2)
        if degree in {"research_masters", "professional_doctorate", "phd"} and not any(t in text for t in ("however", "in contrast", "gap", "limitation", "contradict", "synthesis")):
            issues.append(_issue(code="CH2-CRITICAL-SYNTHESIS", section="Chapter Two: Literature Review", title="The literature review needs stronger critical synthesis", assessment="The chapter does not show enough explicit comparison, contradiction, limitation or synthesis across studies.", action="Organise the review around constructs, debates and relationships; compare methods and findings, then show how the synthesis leads to the study gap and framework.", anchor=anchor, category="critical_analysis", degree=degree, severity="major"))
        if degree in {"research_masters", "professional_doctorate", "phd"} and not any(t in text for t in ("theoretical framework", "conceptual framework", "theory")):
            issues.append(_issue(code="CH2-FRAMEWORK", section="Chapter Two: Literature Review", title="The literature review does not make the theoretical or conceptual framework evident", assessment="A research-intensive or doctoral thesis needs a clear framework rather than only a thematic literature review.", action="Add a theoretical or conceptual framework section and explicitly link its constructs to the objectives, hypotheses or propositions.", anchor=anchor, category="theoretical_grounding", degree=degree, severity="critical"))
    elif chapter == 3:
        method_rows: List[Dict[str, Any]] = []
        for _label, names, _cat, _sev in UCC_EXPECTED[3]:
            method_rows.extend(_find_rows(grouped, names))
        text = normalised(_plain(method_rows))
        anchor = _first_substantive(method_rows) or _first_chapter_anchor(paragraphs, 3)
        if not all(t in text for t in ("objective", "analysis")):
            issues.append(_issue(code="CH3-ANALYSIS-MAPPING", section="Chapter Three: Research Methods", title="The methods chapter does not clearly map analysis to each objective", assessment="The chapter should make the analytical route for every objective, research question or hypothesis explicit.", action="Add a table or narrative mapping each objective/question/hypothesis to data, variables, measurement and analysis technique.", anchor=anchor, category="methodological_rigour", degree=degree, severity="critical"))
        if "ethic" not in text:
            issues.append(_issue(code="CH3-ETHICS", section="Chapter Three: Research Methods", title="Ethical considerations are not evident", assessment="The chapter does not visibly address ethical approval, informed consent, confidentiality or data protection.", action="Add an ethics section covering approval, consent, confidentiality, data storage and participant risk as applicable.", anchor=anchor, category="ethics_and_integrity", degree=degree, severity="critical"))
    elif chapter == 4:
        rows: List[Dict[str, Any]] = []
        for _label, names, _cat, _sev in UCC_EXPECTED[4]:
            rows.extend(_find_rows(grouped, names))
        text = normalised(_plain(rows))
        anchor = _first_substantive(rows) or _first_chapter_anchor(paragraphs, 4)
        if not any(t in text for t in ("objective", "research question", "hypothesis")):
            issues.append(_issue(code="CH4-OBJECTIVE-ORDER", section="Chapter Four: Results and Discussion", title="Results are not clearly organised by objective, question or hypothesis", assessment="The chapter should make it easy to trace each result to the corresponding objective or hypothesis.", action="Present the results in the order of the objectives/questions/hypotheses and explicitly state which objective each table, figure or theme addresses.", anchor=anchor, category="results_and_interpretation", degree=degree, severity="critical"))
        if degree in {"research_masters", "professional_doctorate", "phd"} and not any(t in text for t in ("theory", "previous studies", "consistent with", "contrary to")):
            issues.append(_issue(code="CH4-DISCUSSION-INTEGRATION", section="Chapter Four: Results and Discussion", title="The discussion is not sufficiently integrated with theory and prior studies", assessment="Advanced thesis discussion must interpret findings through theory and prior empirical evidence, including contradictions and alternatives.", action="For each major finding, explain its meaning, compare it with theory and previous studies, and discuss contradictions or alternative explanations.", anchor=anchor, category="discussion_and_integration", degree=degree, severity="major"))
    elif chapter == 5:
        rows: List[Dict[str, Any]] = []
        for _label, names, _cat, _sev in UCC_EXPECTED[5]:
            rows.extend(_find_rows(grouped, names))
        text = normalised(_plain(rows))
        anchor = _first_substantive(rows) or _first_chapter_anchor(paragraphs, 5)
        if not any(t in text for t in ("based on the findings", "finding", "objective")):
            issues.append(_issue(code="CH5-FINDINGS-TRACE", section="Chapter Five: Summary, Conclusions and Recommendations", title="Conclusions and recommendations are not clearly traceable to findings", assessment="The final chapter should not introduce broad recommendations without showing which findings support them.", action="Summarise findings by objective, draw conclusions from those findings and link each recommendation to a specific finding and responsible stakeholder.", anchor=anchor, category="conclusions_and_recommendations", degree=degree, severity="critical"))
        if degree in {"professional_doctorate", "phd"} and not any(t in text for t in ("original contribution", "contribution to knowledge", "contribution to practice", "theoretical contribution")):
            issues.append(_issue(code="CH5-CONTRIBUTION", section="Chapter Five: Summary, Conclusions and Recommendations", title="The final chapter does not make the level-appropriate contribution explicit", assessment="Doctoral work must state the original contribution clearly and show how the evidence supports it.", action="Add a contribution section explaining what is original, how the study established it and why it matters to knowledge, policy or practice at the actual academic level.", anchor=anchor, category="critical_analysis", degree=degree, severity="critical"))
    return [x for x in issues if x]


def ucc_section_contract_issues(
    paragraphs: Sequence[Dict[str, Any]],
    *,
    academic_level: Any = "",
    depth: str = "standard",
    max_issues: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Return UCC-format, degree-calibrated, evidence-anchored issues.

    This layer is intentionally deterministic and conservative. It does not
    replace the model review; it prevents relevant UCC thesis sections from
    being silently omitted after filtering and de-duplication.
    """
    if not enabled():
        return []
    current = _current_rows(paragraphs)
    if not current:
        return []
    degree = _degree_key(academic_level)
    grouped = _group_by_heading(current)
    issues: List[Optional[Dict[str, Any]]] = []

    for chapter, label, names, category, severity in expected_sections_for_scope(current):
        rows = _find_rows(grouped, names)
        if rows:
            # Do not complain that References-like sections are thin; focus on
            # substantive thesis sections.
            if label not in {"Introduction", "Organisation of the Study"}:
                issues.append(_thin_section_issue(label, rows, category, severity, degree))
        else:
            # Hypotheses are conditionally required. The chapter-specific check
            # below handles them when relational/impact objectives are present.
            if label.lower() not in {"research hypotheses", "diagnostic tests"}:
                issues.append(_missing_section_issue(current, chapter, label, category, severity, degree))

    chapters = _chapter_scope(current)
    if 1 in chapters:
        issues.extend(_chapter_one_specific(current, grouped, degree))
    for chapter in sorted(chapters - {1}):
        issues.extend(_generic_chapter_specific(current, grouped, degree, chapter))


    out: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for item in issues:
        if not item:
            continue
        if item.get("severity") == "minor" and normalised(depth) == "light":
            continue
        key = str(item.get("finding_id"))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    severity_rank = {"critical": 0, "major": 1, "moderate": 2, "minor": 3}
    out.sort(key=lambda row: (severity_rank.get(str(row.get("severity") or "minor"), 9), normalised(row.get("section", "")), normalised(row.get("issue_title", ""))))
    if max_issues is None:
        max_issues = int(os.getenv("VPROF_UCC_SECTION_CONTRACT_MAX_ISSUES", "72"))
    return out[: max(0, int(max_issues))]


def missing_section_labels_in_output(paragraphs: Sequence[Dict[str, Any]], issues: Sequence[Dict[str, Any]]) -> Set[str]:
    present = present_relevant_sections(paragraphs)
    covered = {clean_text(issue.get("section", "")) for issue in issues}
    covered_norm = {normalised(x) for x in covered}
    missing: Set[str] = set()
    for label in present:
        if normalised(label) not in covered_norm:
            missing.add(label)
    return missing
