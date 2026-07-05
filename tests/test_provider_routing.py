from __future__ import annotations

from pathlib import Path

from app.ai_config import AIConfigurationError, HybridAIConfig
from app.academic_ai_engine import _batch_model_route


def test_all_review_depths_use_tiered_openai_models(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    for name in (
        "DEEPSEEK_API_KEY",
        "OPENAI_REVIEW_MODEL",
        "OPENAI_REVIEW_REASONING_EFFORT",
        "OPENAI_CHAPTER_MODEL",
        "OPENAI_EXPERT_MODEL",
        "OPENAI_FINAL_AUDIT_MODEL",
        "OPENAI_EXTERNAL_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    config = HybridAIConfig.from_env()

    assert config.resolve_mode("light") == "light"
    assert config.resolve_mode("standard") == "standard"
    assert config.resolve_mode("advanced") == "advanced"
    assert config.openai_chapter_model == "gpt-5.4-mini"
    assert config.openai_expert_model == "gpt-5.4"
    assert config.openai_final_audit_model == "gpt-5.4"
    assert config.openai_external_model == "gpt-5.4"
    assert config.openai_chapter_reasoning_effort == "high"
    assert config.openai_final_audit_reasoning_effort == "high"
    status = config.public_status()
    assert status["review_depths"] == ["light", "standard", "advanced"]
    assert "provider" not in status
    assert "model" not in status


def test_all_depths_fail_without_openai(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "legacy-key")
    config = HybridAIConfig.from_env()
    for depth in ("light", "standard", "advanced"):
        try:
            config.resolve_mode(depth)
            assert False, f"{depth} should require OpenAI."
        except AIConfigurationError:
            pass


def test_research_intensive_sections_escalate_to_expert_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    config = HybridAIConfig.from_env()
    methods = [{"heading": "Research Methods", "section_path": [], "paragraphs": []}]
    literature = [{"heading": "Definition of Terms", "section_path": [], "paragraphs": []}]

    assert _batch_model_route(methods, "Research Masters (MPhil)", config) == (
        "gpt-5.4",
        "high",
    )
    assert _batch_model_route(literature, "Research Masters (MPhil)", config) == (
        "gpt-5.4-mini",
        "high",
    )
    assert _batch_model_route(methods, "Bachelors", config) == (
        "gpt-5.4-mini",
        "high",
    )


def test_academic_engine_uses_tiered_review_and_expert_audit():
    source = Path("app/academic_ai_engine.py").read_text(encoding="utf-8")
    assert "provider = openai" in source
    assert "_batch_model_route(batch, academic_level, config)" in source
    assert 'purpose=f"{depth}_universal_comment_accuracy_audit"' in source
    assert "audit_model = config.openai_final_audit_model" in source
    assert "audit_effort = config.openai_final_audit_reasoning_effort" in source
    assert '"active_provider": "openai"' in source
