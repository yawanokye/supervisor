from __future__ import annotations

from app.ai_config import AIConfigurationError, HybridAIConfig


def test_all_review_depths_use_deepseek(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = HybridAIConfig.from_env()

    assert config.resolve_mode("light") == "light"
    assert config.resolve_mode("standard") == "standard"
    assert config.resolve_mode("advanced") == "advanced"
    assert config.deepseek_review_model == "deepseek-v4-pro"
    assert config.deepseek_advanced_model == "deepseek-v4-pro"
    assert config.deepseek_advanced_reasoning_effort == "max"
    assert config.public_status()["review_depths"] == ["light", "standard", "advanced"]


def test_all_depths_fail_without_deepseek(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    config = HybridAIConfig.from_env()
    for depth in ("light", "standard", "advanced"):
        try:
            config.resolve_mode(depth)
            assert False, f"{depth} should require DeepSeek."
        except AIConfigurationError:
            pass


def test_advanced_engine_routes_to_deepseek():
    from pathlib import Path
    source = Path("app/academic_ai_engine.py").read_text(encoding="utf-8")
    assert "primary_model = config.deepseek_advanced_model" in source
    assert 'purpose=f"{depth}_compact_comment_accuracy_audit"' in source
    assert "audit_model = (" in source
