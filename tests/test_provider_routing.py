from __future__ import annotations

from pathlib import Path

from app.ai_config import AIConfigurationError, HybridAIConfig


def test_all_review_depths_use_openai_o3_mini(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_REVIEW_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_REVIEW_REASONING_EFFORT", raising=False)
    config = HybridAIConfig.from_env()

    assert config.resolve_mode("light") == "light"
    assert config.resolve_mode("standard") == "standard"
    assert config.resolve_mode("advanced") == "advanced"
    assert config.openai_review_model == "o3-mini"
    assert config.openai_review_reasoning_effort == "high"
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


def test_academic_engine_routes_to_openai_o3_mini():
    source = Path("app/academic_ai_engine.py").read_text(encoding="utf-8")
    assert "provider = openai" in source
    assert "primary_model = config.openai_review_model" in source
    assert 'purpose=f"{depth}_universal_comment_accuracy_audit"' in source
    assert "audit_model = config.openai_review_model" in source
    assert "audit_effort = config.openai_review_reasoning_effort" in source
    assert '"active_provider": "openai"' in source
