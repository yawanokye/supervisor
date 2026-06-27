from __future__ import annotations

from app.ai_config import AIConfigurationError, HybridAIConfig


def test_light_and_standard_require_deepseek(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = HybridAIConfig.from_env()

    assert config.resolve_mode("light") == "light"
    assert config.resolve_mode("standard") == "standard"

    try:
        config.resolve_mode("advanced")
        assert False, "Advanced should require OpenAI."
    except AIConfigurationError:
        pass


def test_advanced_requires_openai(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    config = HybridAIConfig.from_env()

    assert config.resolve_mode("advanced") == "advanced"

    for depth in ("light", "standard"):
        try:
            config.resolve_mode(depth)
            assert False, f"{depth} should require DeepSeek."
        except AIConfigurationError:
            pass


def test_both_providers_make_all_depths_available(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    config = HybridAIConfig.from_env()

    assert config.deepseek_review_model == "deepseek-v4-pro"
    assert config.openai_review_model == "gpt-5.4"
    assert config.public_status()["review_depths"] == [
        "light",
        "standard",
        "advanced",
    ]
