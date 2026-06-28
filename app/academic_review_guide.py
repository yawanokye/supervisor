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
        "The statement of the problem should be clear, specific, researchable, significant and located in the actual study context.",
        "It should distinguish the undesirable practical or empirical condition from the underlying knowledge gap.",
        "The problem should be demonstrated with credible evidence, explain who or what is affected, and show why the issue requires investigation.",
        "The weaknesses, inconsistencies, controversies or limits of previous research should be synthesised rather than merely asserted.",
        "The final part should identify the precise unresolved issue, variables or phenomenon, population or unit, and context that the study will investigate.",
        "The problem must not be framed as a predetermined conclusion or as a general topic without an investigable gap.",
    ],
    "purpose_objectives_questions": [
        "The purpose should flow directly from the problem and use neutral investigative language.",
        "The general and specific objectives should arise from the dimensions of the problem, be measurable, logically ordered and collectively sufficient to address the gap.",
        "Each research question should correspond to an objective in meaning, variables, population and scope.",
        "Hypotheses should be developed where the design, theory and objectives require testable directional or non-directional propositions.",
        "Every hypothesis should be theoretically or empirically justified and align with an objective, variables and intended analysis.",
        "Causal terms such as effect, impact or influence should be consistent with the design and evidence that can be produced.",
    ],
    "significance_scope": [
        "The significance should explain realistic theoretical, practical, policy or contextual contributions appropriate to the level of study.",
        "Delimitations should state the intended boundaries of topic, setting, participants, variables and time where relevant.",
        "Limitations should identify genuine design or implementation constraints, their likely implications and any mitigation.",
        "The organisation of the study should accurately describe the actual chapters.",
    ],
    "literature_chapter": [
        "The chapter should review the central concepts and clarify their boundaries, dimensions and use in the study.",
        "Appropriate theory or theories should be accurately explained, critically evaluated and connected to the constructs, objectives and expected relationships.",
        "The empirical literature should be organised around the objectives, constructs or relationships rather than enumerated study by study.",
        "Studies should be compared and synthesised across context, data, methods and findings, with contradictions and limitations made explicit.",
        "The chapter should end by showing the implications of the review for the research gap, hypotheses or propositions, conceptual framework and methods.",
    ],
    "methods_chapter": [
        "The chapter should explain and justify the complete methods and procedures required to answer every research question or test every hypothesis.",
        "The research paradigm, approach, design, setting, population, sampling, instruments or data sources, validity or trustworthiness, procedures, ethics and analysis should form one coherent design.",
        "The analysis method for each objective, question or hypothesis should be explicit, appropriate and reproducible.",
        "Instrument development, adaptation, scoring, pilot evidence, reliability and validity should be reported where applicable.",
        "Completed studies should report what was actually done, while proposals should clearly state what will be done.",
    ],
    "results_discussion_chapter": [
        "The results should be complete, internally accurate and presented in the order of the objectives, questions or hypotheses.",
        "Narrative statements must agree with tables, figures, coefficients, signs, sample sizes, totals, percentages, significance values, confidence intervals and hypothesis decisions.",
        "The interpretation should state what the result means without overstating causality, statistical importance or practical significance.",
        "The discussion should explain the findings thoroughly, compare them critically with theory and empirical literature, and address agreements, contradictions, unexpected results and plausible alternative explanations.",
        "The chapter should distinguish presentation of evidence from interpretation and discussion, even when both appear in one chapter.",
    ],
    "final_chapter": [
        "The chapter should provide a concise overview of the study and summarise the main findings by objective, question or hypothesis.",
        "The summary of findings should not repeat tables, coefficients, test statistics or the full analysis reported in the results chapter.",
        "Conclusions should be inferential statements drawn from the findings, not a restatement of the results or new evidence.",
        "The contribution, implications, unexpected findings and limitations should be stated at the level justified by the study.",
        "Each recommendation should follow from a specific finding and identify an appropriate actor or area of action where relevant.",
        "Suggestions for further research should arise from limitations, unresolved questions or new insights.",
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
        "Results should be presented in the order of objectives, questions or hypotheses with complete and internally accurate tables, figures, themes and statistics.",
        "Check consistency among narrative claims, table values, totals, percentages, sample sizes, coefficient signs, significance values, confidence intervals and hypothesis decisions.",
        "Interpretation should distinguish statistical, qualitative or mixed-method evidence from speculation and should not exceed the design.",
        "Every objective, research question and hypothesis should receive a clear, traceable result.",
    ],
    "discussion": [
        "The discussion should explain why the findings matter, not merely repeat the results.",
        "Each major finding should be connected to the relevant objective, theory and empirical literature.",
        "Agreements, contradictions, unexpected findings, contextual influences and alternative explanations should be examined critically.",
        "Theoretical, practical and policy implications should remain proportionate to the evidence and academic level.",
    ],
    "conclusion_recommendations": [
        "The summary should present the main findings by objective or question without repeating analysis outputs, tables, coefficients or test statistics.",
        "Conclusions should interpret what the findings establish and should not merely restate the results or introduce new evidence.",
        "The chapter should identify contributions, implications, anomalies and limitations at a level justified by the study.",
        "Recommendations should follow from specific findings and identify realistic responsible actors where appropriate.",
        "Suggestions for future research should arise from limitations, unresolved findings or new questions generated by the study.",
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
    if "literature review" in value or "review of related literature" in value:
        keys.append("literature_chapter")
    if "empirical" in value or "literature review" in value:
        keys.append("empirical_literature")
    if "conceptual framework" in value:
        keys.append("conceptual_framework")
    if any(term in value for term in ("research methods", "research methodology", "materials and methods", "methodology")):
        keys.append("methods_chapter")
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
    if "results and discussion" in value:
        keys.append("results_discussion_chapter")
    if any(term in value for term in ("results", "findings", "hypothesis testing", "descriptive statistics")):
        keys.append("results")
    if "discussion" in value:
        keys.append("discussion")
    if any(term in value for term in ("summary conclusions", "summary, conclusions", "chapter five")):
        keys.append("final_chapter")
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
