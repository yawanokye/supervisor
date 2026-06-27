from __future__ import annotations

from typing import Dict, Iterable, List

from .document_parser import normalised


# This is an internal supervisory coverage guide. It is deliberately phrased as
# broad academic expectations rather than checklist items or codes. The review
# model must adapt the expectations to the study design and academic level.
GUIDE_BY_SECTION: Dict[str, List[str]] = {
    "title": [
        "The title should accurately express the main constructs, relationship, context and scope without prejudging the result.",
        "The terminology in the title should match the terminology used in the problem, purpose, objectives, questions and methods.",
    ],
    "opening": [
        "The opening should establish the subject, significance and direction of the chapter without duplicating the full background.",
        "Claims about the importance of the topic should be supported or framed cautiously.",
    ],
    "background": [
        "The discussion should progress logically from the wider scholarly or policy context to the study-specific context.",
        "Key concepts, relevant theory and credible empirical evidence should be integrated rather than merely listed.",
        "The background should signal a defensible knowledge gap and lead naturally to the problem statement.",
    ],
    "problem": [
        "The problem should be specific, researchable and demonstrated with credible empirical, policy or practice evidence.",
        "The weaknesses or limits of previous studies or current approaches should be explained, not merely asserted.",
        "The final part should state the precise unresolved issue the study will investigate in its actual context.",
    ],
    "purpose_objectives_questions": [
        "The purpose should flow directly from the problem and use neutral investigative language.",
        "Objectives should be measurable, logically ordered and traceable to the identified gap.",
        "Each objective should align in meaning and scope with a research question or hypothesis.",
        "Causal language should be consistent with the proposed research design.",
    ],
    "significance_scope": [
        "The significance should explain realistic theoretical, practical, policy or contextual contributions appropriate to the level of study.",
        "Delimitations should state the intended boundaries of topic, setting, participants, variables and time where relevant.",
        "Limitations should identify genuine design or implementation constraints, their likely implications and any mitigation.",
        "The organisation of the study should accurately describe the actual chapters.",
    ],
    "theory": [
        "Theories should be directly relevant, accurately explained and linked to specific constructs, objectives or hypotheses.",
        "The boundaries and limitations of each theory should be acknowledged.",
        "At advanced levels, the theoretical positioning and contribution should be explicit and defensible.",
    ],
    "empirical_literature": [
        "The empirical review should be organised around the objectives or relationships examined in the study.",
        "Previous studies should be compared by context, data, methods and findings rather than summarised one by one.",
        "Contradictions, limitations and unresolved questions should lead to a study-specific gap.",
    ],
    "conceptual_framework": [
        "The framework should include only constructs justified by the problem, objectives, theory and literature.",
        "Proposed relationships, mediators, moderators and controls should be clearly explained.",
        "The diagram and narrative should use consistent labels and direction of relationships.",
    ],
    "method_foundation": [
        "The philosophy, paradigm and approach should be stated or clearly implied and should fit the research problem and evidence sought.",
        "The design, study type, time horizon and unit of analysis should be justified and mutually consistent.",
        "Methodological choices should be linked explicitly to the objectives and hypotheses or research questions.",
    ],
    "population_sampling": [
        "The setting, target population, inclusion boundaries and sampling frame should be clear.",
        "The sampling technique and sample-size method should be justified for the intended analysis.",
        "The sampling steps should be replicable and likely biases or non-response should be addressed.",
    ],
    "instrument_measurement": [
        "The data type, source and collection instrument should be described and justified.",
        "The source of questionnaire items, scales, interview guides or archival variables should be traceable.",
        "Constructs, dimensions, indicators, scales, coding and composite-score procedures should be explicit.",
        "Pilot testing, refinement, validity, reliability or qualitative trustworthiness should be addressed as applicable.",
    ],
    "data_collection_analysis": [
        "Permissions, field procedures, timing, response management, storage and anonymisation should be described.",
        "Data preparation, missing values, outliers, assumptions and common-method concerns should be addressed where relevant.",
        "The analysis plan should map each objective or hypothesis to an appropriate technique, model and software.",
    ],
    "ethics": [
        "Ethical approval, informed consent, confidentiality, data protection and participant risk should be addressed in proportion to the study.",
    ],
    "results": [
        "Results should be presented in the order of objectives or hypotheses with accurate tables, figures and statistics.",
        "Interpretation should distinguish statistical or thematic evidence from speculation.",
        "Hypotheses or research questions should be answered consistently and transparently.",
    ],
    "discussion": [
        "The discussion should explain the meaning of findings, connect them to theory and compare them critically with previous studies.",
        "Alternative explanations, context, limitations and practical implications should be considered at the appropriate academic level.",
    ],
    "conclusion_recommendations": [
        "The summary and conclusions should respond directly to the objectives and central problem without introducing new evidence.",
        "Recommendations should follow from specific findings and identify realistic responsible actors where appropriate.",
        "Suggestions for future research should arise from limitations or unresolved findings.",
    ],
    "references_readiness": [
        "In-text citations and references should correspond, follow the required style and be verifiable.",
        "The document should be internally coherent, consistently formatted and defensible as a complete study.",
    ],
    "general": [
        "The section should have a clear purpose, coherent structure, credible evidence and terminology consistent with the rest of the study.",
        "Academic claims should not exceed what the supplied evidence and research design can support.",
    ],
}


def _keys_for_heading(heading: str) -> List[str]:
    value = normalised(heading)
    keys: List[str] = []
    if not value:
        return ["general"]
    if "title" in value or (len(value.split()) > 4 and "chapter" not in value and "audit" not in value):
        keys.append("title")
    if value in {"opening material", "introduction"}:
        keys.append("opening")
    if "background" in value:
        keys.append("background")
    if "problem" in value:
        keys.append("problem")
    if any(term in value for term in ("purpose", "objective", "research question", "hypothesis")):
        keys.append("purpose_objectives_questions")
    if any(term in value for term in ("significance", "significant", "delimitation", "limitation", "scope", "organisation", "organization")):
        keys.append("significance_scope")
    if any(term in value for term in ("theoretical", "theory", "hypotheses development")):
        keys.append("theory")
    if "empirical" in value or "literature review" in value:
        keys.append("empirical_literature")
    if "conceptual framework" in value:
        keys.append("conceptual_framework")
    if any(term in value for term in ("philosophy", "paradigm", "research approach", "research design", "time horizon", "unit of analysis")):
        keys.append("method_foundation")
    if any(term in value for term in ("population", "sampling", "sample size", "study setting", "study area")):
        keys.append("population_sampling")
    if any(term in value for term in ("instrument", "measurement", "operationalisation", "operationalization", "pilot", "validity", "reliability", "trustworthiness", "data source")):
        keys.append("instrument_measurement")
    if any(term in value for term in ("data collection", "data preparation", "data analysis", "model specification", "assumption", "missing data", "outlier")):
        keys.append("data_collection_analysis")
    if "ethic" in value:
        keys.append("ethics")
    if any(term in value for term in ("results", "findings", "hypothesis testing", "descriptive statistics")):
        keys.append("results")
    if "discussion" in value:
        keys.append("discussion")
    if any(term in value for term in ("conclusion", "recommendation", "future research", "summary of findings")):
        keys.append("conclusion_recommendations")
    if any(term in value for term in ("reference", "submission readiness", "whole chapter", "cross chapter")):
        keys.append("references_readiness")
    return keys or ["general"]


def guide_for_heading(heading: str, limit: int = 10) -> List[str]:
    values: List[str] = []
    for key in _keys_for_heading(heading):
        values.extend(GUIDE_BY_SECTION.get(key, []))
    output: List[str] = []
    seen = set()
    for value in values:
        marker = normalised(value)
        if marker and marker not in seen:
            seen.add(marker)
            output.append(value)
        if len(output) >= limit:
            break
    return output
