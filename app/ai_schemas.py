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


class AIUsageRecord(StrictModel):
    provider: str
    model: str
    purpose: str
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    request_id: str = ""
