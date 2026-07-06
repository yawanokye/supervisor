from __future__ import annotations

import json
from pathlib import Path

from app.academic_ai_engine import (
    _batch_prompt,
    _degree_issue_limit,
    _degree_specific_review_contract,
)
from app.ai_config import HybridAIConfig
from app.model_router import CostAwareAIProvider, ProviderName, ReviewStage
from app.supervisory_accuracy_guard import deterministic_expert_issues


def _section() -> dict:
    return {
        "section_key": "S001P01",
        "heading": "Statement of the Problem",
        "chapter_number": 1,
        "section_path": ["CHAPTER ONE", "Statement of the Problem"],
        "part": 1,
        "paragraphs": [{
            "paragraph": 1,
            "text": "The problem requires a defensible local evidence base.",
            "heading": "Statement of the Problem",
            "section_path": ["CHAPTER ONE", "Statement of the Problem"],
            "chapter_number": 1,
            "document_role": "current",
            "is_heading": False,
        }],
    }


def test_research_masters_has_deeper_issue_capacity_than_non_research_masters() -> None:
    assert _degree_issue_limit("Non-Research Masters", "standard") == 5
    assert _degree_issue_limit("Research Masters / MPhil", "standard") == 6
    assert _degree_issue_limit("Research Masters / MPhil", "advanced") == 7


def test_mphil_contract_is_research_intensive_and_chapter_specific() -> None:
    mphil = _degree_specific_review_contract(
        "Research Masters / MPhil", 1, "standard"
    )
    applied = _degree_specific_review_contract(
        "Non-Research Masters", 1, "standard"
    )

    assert mphil["orientation"] == "research-intensive-master's"
    assert mphil["per_section_issue_ceiling_not_quota"] == 6
    assert mphil["independent_audit_material_finding_capacity"] == 36
    assert len(mphil["chapter_specific_mandatory_checks"]) >= 8
    assert any("Audit in-text citations" in item for item in mphil["chapter_specific_mandatory_checks"])

    assert applied["orientation"] == "applied-master's"
    assert applied["per_section_issue_ceiling_not_quota"] == 5
    assert len(applied["chapter_specific_mandatory_checks"]) >= 6


def test_batch_prompt_operationalises_mphil_depth() -> None:
    review = {
        "summary": {
            "academic_level": "Research Masters / MPhil",
            "research_approach": "quantitative",
            "selected_chapter": 1,
        }
    }
    packet = json.loads(_batch_prompt(review, [_section()], [], {}, "standard"))
    contract = packet["review_context"]["degree_specific_review_contract"]

    assert packet["coverage_contract"]["normal_issue_limit_per_section"] == 6
    assert packet["coverage_contract"]["independent_audit_material_finding_capacity"] == 36
    assert contract["degree_key"] == "research_masters"
    assert "contextually evidenced research problem" in " ".join(contract["mandatory_dimensions"])


def test_research_masters_defaults_enable_deep_review(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek")
    for key in (
        "AI_RESEARCH_MASTERS_MAX_OUTPUT_TOKENS",
        "AI_RESEARCH_MASTERS_AUDIT_MAX_OUTPUT_TOKENS",
        "OPENAI_RESEARCH_MASTERS_AUDIT_REASONING_EFFORT",
        "VPROF_RESEARCH_MASTERS_DEEP_REVIEW",
    ):
        monkeypatch.delenv(key, raising=False)

    config = HybridAIConfig.from_env()
    assert config.research_masters_deep_review is True
    assert config.research_masters_max_output_tokens == 9000
    assert config.research_masters_audit_max_output_tokens == 6500
    assert config.research_masters_audit_reasoning_effort == "high"


def test_balanced_research_masters_route_uses_pro_then_one_expert_audit(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek")
    monkeypatch.setenv("VPROF_ROUTING_PROFILE", "balanced")
    config = HybridAIConfig.from_env()
    router = CostAwareAIProvider(config)

    first = router.plan(
        stage=ReviewStage.RESEARCH_INTENSIVE_REVIEW,
        review_depth="standard",
        requested_model=config.openai_expert_model,
        requested_effort="high",
    )
    audit = router.plan(
        stage=ReviewStage.RESEARCH_INTENSIVE_AUDIT,
        review_depth="standard",
        requested_model=config.openai_expert_model,
        requested_effort="high",
    )

    assert first.primary.provider is ProviderName.DEEPSEEK
    assert first.primary.model == config.deepseek_quality_model
    assert first.allow_escalation is False
    assert audit.primary.provider is ProviderName.OPENAI
    assert audit.primary.model == config.openai_expert_model
    assert audit.allow_escalation is False


def test_mphil_deterministic_depth_checks_find_alignment_and_significance() -> None:
    rows = [
        {
            "paragraph": 1,
            "text": "The purpose of this study is to examine environmental sustainability.",
            "heading": "Purpose of the Study",
            "section_path": ["CHAPTER ONE", "Purpose of the Study"],
            "chapter_number": 1,
            "document_role": "current",
            "is_heading": False,
        },
        {
            "paragraph": 2,
            "text": "To assess awareness and operational performance among firms.",
            "heading": "Research Objectives",
            "section_path": ["CHAPTER ONE", "Research Objectives"],
            "chapter_number": 1,
            "document_role": "current",
            "is_heading": False,
        },
        {
            "paragraph": 3,
            "text": "As the results reveal a connection, firms will benefit from the study.",
            "heading": "Significance of the Study",
            "section_path": ["CHAPTER ONE", "Significance of the Study"],
            "chapter_number": 1,
            "document_role": "current",
            "is_heading": False,
        },
        {
            "paragraph": 4,
            "text": "Awareness means the extent of awareness among managers.",
            "heading": "Definition of Terms",
            "section_path": ["CHAPTER ONE", "Definition of Terms"],
            "chapter_number": 1,
            "document_role": "current",
            "is_heading": False,
        },
    ]
    issues = deterministic_expert_issues(
        rows, academic_level="Research Masters / MPhil"
    )
    ids = {item["finding_id"] for item in issues}
    assert "DET-DEGREE-PURPOSE-OBJECTIVE-COVERAGE" in ids
    assert "DET-DEGREE-PREMATURE-SIGNIFICANCE-RESULTS" in ids
    assert "DET-DEGREE-WEAK-CORE-DEFINITIONS" in ids


def test_pipeline_uses_degree_calibrated_stage_and_checkpoint_version() -> None:
    source = Path("app/academic_ai_engine.py").read_text(encoding="utf-8")
    assert "ReviewStage.RESEARCH_INTENSIVE_REVIEW" in source
    assert "ReviewStage.RESEARCH_INTENSIVE_AUDIT" in source
    assert "academic-review-v1.9.8.6-final-mphil-depth" in source
    assert "academic-comment-audit-v1.9.8.6-final-mphil-depth" in source
