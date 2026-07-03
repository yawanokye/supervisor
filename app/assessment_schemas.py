from __future__ import annotations

from typing import List, Literal

from pydantic import ConfigDict, BaseModel, Field


DomainJudgement = Literal[
    "strong_and_fully_appropriate",
    "appropriate_with_minor_refinement",
    "partly_appropriate_major_revision_required",
    "fundamentally_deficient",
    "not_applicable",
]

CorrectionClass = Literal["critical", "major", "moderate", "minor"]

FinalRecommendation = Literal[
    "pass_without_corrections",
    "pass_subject_to_minor_corrections",
    "pass_subject_to_major_corrections",
    "revise_and_resubmit_for_re_examination",
    "award_lower_degree_where_permitted",
    "fail",
    "corrections_satisfactorily_completed",
    "corrections_not_satisfactorily_completed",
]

VivaRecommendation = Literal["required", "recommended", "optional", "not_required"]


class StrictAssessmentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssessmentDomain(StrictAssessmentModel):
    domain: str
    judgement: DomainJudgement
    assessment: str
    strengths: List[str] = Field(default_factory=list)
    concerns: List[str] = Field(default_factory=list)
    required_corrections: List[str] = Field(default_factory=list)


class CorrectionItem(StrictAssessmentModel):
    number: int = Field(ge=1)
    classification: CorrectionClass
    chapter_or_section: str
    location: str
    issue: str
    required_correction: str
    rationale: str
    verification_by: str


class OralExaminationQuestion(StrictAssessmentModel):
    category: str
    question: str
    rationale: str


class ExternalAssessmentReport(StrictAssessmentModel):
    study_summary: str
    overall_academic_judgement: str
    degree_standard_judgement: str
    chapter_one_gate_status: Literal[
        "passed",
        "major_concern",
        "fundamentally_deficient",
        "not_applicable",
    ]
    chapter_one_assessment: AssessmentDomain
    research_problem_and_purpose: AssessmentDomain
    literature_and_theoretical_foundation: AssessmentDomain
    methodology_and_procedures: AssessmentDomain
    results_or_findings: AssessmentDomain
    discussion_and_interpretation: AssessmentDomain
    conclusions_recommendations_and_contribution: AssessmentDomain
    structural_coherence_and_alignment: AssessmentDomain
    academic_writing_and_presentation: AssessmentDomain
    ethics_and_research_integrity: AssessmentDomain
    originality_and_contribution: AssessmentDomain
    major_strengths: List[str] = Field(default_factory=list)
    publication_potential: str
    corrections: List[CorrectionItem] = Field(default_factory=list)
    oral_examination_questions: List[OralExaminationQuestion] = Field(default_factory=list)
    final_recommendation: FinalRecommendation
    recommendation_rationale: str
    priority_corrections_before_award: List[str] = Field(default_factory=list)
    corrections_verification_assessment: str
    confidential_comments_to_university: str
    recommendation_confidence: Literal["high", "moderate", "low"]
    corrections_verification_by: str
    viva_recommendation: VivaRecommendation
    examiner_declaration: str
