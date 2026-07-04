from __future__ import annotations

from typing import List, Literal

from pydantic import ConfigDict, BaseModel, Field, model_validator


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
    "assessment_withheld_incomplete_extraction",
]

VivaRecommendation = Literal["required", "recommended", "optional", "not_required"]

CoverageStatus = Literal[
    "fully_assessed",
    "partly_assessed",
    "not_assessed_due_to_retrieval_limit",
    "not_applicable",
]


class StrictAssessmentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssessmentDomain(StrictAssessmentModel):
    domain: str
    judgement: DomainJudgement
    coverage_status: CoverageStatus
    evidence_ids: List[str] = Field(default_factory=list, max_length=24)
    assessment: str
    strengths: List[str] = Field(default_factory=list, max_length=8)
    concerns: List[str] = Field(default_factory=list, max_length=8)
    required_corrections: List[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def validate_evidence_coverage(self):
        if self.coverage_status in {"fully_assessed", "partly_assessed"} and not self.evidence_ids:
            raise ValueError(
                "Evidence IDs are required when an assessment domain is fully or partly assessed."
            )
        if self.coverage_status == "not_assessed_due_to_retrieval_limit":
            if self.judgement != "not_applicable":
                raise ValueError(
                    "A domain not assessed because of retrieval limits must use judgement=not_applicable."
                )
            if self.concerns or self.required_corrections:
                raise ValueError(
                    "A domain that could not be assessed may not impose concerns or corrections."
                )
        return self


class CorrectionItem(StrictAssessmentModel):
    number: int = Field(ge=1)
    classification: CorrectionClass
    chapter_or_section: str
    location: str
    evidence_ids: List[str] = Field(default_factory=list, min_length=1, max_length=12)
    issue: str
    required_correction: str
    rationale: str
    verification_by: str


class OralExaminationQuestion(StrictAssessmentModel):
    category: str
    question: str
    rationale: str


class ExternalAssessmentFoundation(StrictAssessmentModel):
    study_summary: str
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


class ExternalAssessmentEvidence(StrictAssessmentModel):
    results_or_findings: AssessmentDomain
    discussion_and_interpretation: AssessmentDomain
    conclusions_recommendations_and_contribution: AssessmentDomain
    structural_coherence_and_alignment: AssessmentDomain
    academic_writing_and_presentation: AssessmentDomain
    ethics_and_research_integrity: AssessmentDomain
    originality_and_contribution: AssessmentDomain
    major_strengths: List[str] = Field(default_factory=list, max_length=12)
    publication_potential: str


class ExternalAssessmentCorrections(StrictAssessmentModel):
    corrections: List[CorrectionItem] = Field(default_factory=list, max_length=40)
    oral_examination_questions: List[OralExaminationQuestion] = Field(
        default_factory=list,
        max_length=20,
    )
    priority_corrections_before_award: List[str] = Field(
        default_factory=list,
        max_length=20,
    )
    corrections_verification_assessment: str


class ExternalAssessmentDecision(StrictAssessmentModel):
    overall_academic_judgement: str
    final_recommendation: FinalRecommendation
    recommendation_rationale: str
    confidential_comments_to_university: str
    recommendation_confidence: Literal["high", "moderate", "low"]
    corrections_verification_by: str
    viva_recommendation: VivaRecommendation
    examiner_declaration: str


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
    major_strengths: List[str] = Field(default_factory=list, max_length=12)
    publication_potential: str
    corrections: List[CorrectionItem] = Field(default_factory=list, max_length=40)
    oral_examination_questions: List[OralExaminationQuestion] = Field(default_factory=list, max_length=20)
    final_recommendation: FinalRecommendation
    recommendation_rationale: str
    priority_corrections_before_award: List[str] = Field(default_factory=list, max_length=20)
    corrections_verification_assessment: str
    confidential_comments_to_university: str
    recommendation_confidence: Literal["high", "moderate", "low"]
    corrections_verification_by: str
    viva_recommendation: VivaRecommendation
    examiner_declaration: str
