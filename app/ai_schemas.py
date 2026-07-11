from __future__ import annotations

from typing import Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field

ReviewStatus = Literal[
    "meets_requirement",
    "partly_meets_requirement",
    "does_not_meet_requirement",
    "manual_review_required",
    "not_applicable",
]
Severity = Literal["critical", "major", "moderate", "minor"]
GuidanceType = Literal["direct_correction", "structural_guidance", "conditional_guidance", "source_verification", "language_pattern", "statistical_verification"]
AcademicCategory = Literal[
    "title_and_focus",
    "chapter_structure",
    "conceptual_clarity",
    "theoretical_grounding",
    "empirical_evidence",
    "critical_analysis",
    "research_gap_and_problem",
    "objectives_questions_hypotheses",
    "methodological_rigour",
    "results_and_interpretation",
    "discussion_and_integration",
    "conclusions_and_recommendations",
    "cross_section_coherence",
    "citations_and_sources",
    "academic_writing",
    "tables_figures_and_presentation",
    "ethics_and_integrity",
    "measurement_and_scoring",
    "statistical_accuracy",
    "analysis_appropriateness",
    "reference_integrity",
    "document_completeness",
    "other",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocumentMap(StrictModel):
    research_problem: str = ""
    purpose: str = ""
    objectives: List[str] = Field(default_factory=list)
    research_questions: List[str] = Field(default_factory=list)
    hypotheses: List[str] = Field(default_factory=list)
    theories: List[str] = Field(default_factory=list)
    variables: List[str] = Field(default_factory=list)
    population_and_sample: str = ""
    methods_by_objective: Dict[str, str] = Field(default_factory=dict)
    findings_by_objective: Dict[str, str] = Field(default_factory=dict)
    conclusions_by_objective: Dict[str, str] = Field(default_factory=dict)
    recommendations_by_finding: Dict[str, str] = Field(default_factory=dict)
    inconsistencies: List[str] = Field(default_factory=list)


class AIDecision(StrictModel):
    code: str
    status: ReviewStatus
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_paragraph_ids: List[str] = Field(default_factory=list)
    problematic_quote: str = ""
    expert_assessment: str
    required_action: str
    needs_openai_verification: bool = False
    verification_reason: str = ""


class DecisionBatch(StrictModel):
    decisions: List[AIDecision]


class AcademicStrength(StrictModel):
    category: AcademicCategory
    section: str
    evidence_paragraph_ids: List[str] = Field(default_factory=list)
    observation: str


class AcademicIssue(StrictModel):
    finding_id: str
    category: AcademicCategory
    section: str
    issue_title: str
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_paragraph_ids: List[str] = Field(default_factory=list)
    problematic_quote: str = ""
    assessment: str
    academic_consequence: str
    required_action: str
    illustrative_guidance: str = ""
    guidance_type: GuidanceType = "direct_correction"
    source_verification_required: bool = False
    context_guard_adjusted: bool = False


class AcademicSectionReview(StrictModel):
    section_name: str
    section_score: float = Field(ge=0.0, le=100.0)
    section_assessment: str
    assessed_paragraph_ids: List[str] = Field(default_factory=list)
    strengths: List[AcademicStrength] = Field(default_factory=list)
    issues: List[AcademicIssue] = Field(default_factory=list)
    coverage_warning: str = ""


class AcademicSectionReviewItem(AcademicSectionReview):
    section_key: str


class AcademicReviewBatch(StrictModel):
    reviews: List[AcademicSectionReviewItem] = Field(default_factory=list)


class AcademicIssueVerification(StrictModel):
    finding_id: str
    keep: bool
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_paragraph_ids: List[str] = Field(default_factory=list)
    problematic_quote: str = ""
    assessment: str
    academic_consequence: str
    required_action: str
    illustrative_guidance: str = ""
    guidance_type: GuidanceType = "direct_correction"
    source_verification_required: bool = False
    context_guard_adjusted: bool = False


class AcademicVerificationBatch(StrictModel):
    verifications: List[AcademicIssueVerification] = Field(default_factory=list)
    missed_issues: List[AcademicIssue] = Field(default_factory=list)


class AIUsageRecord(StrictModel):
    provider: str
    model: str
    purpose: str
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    request_id: str = ""
