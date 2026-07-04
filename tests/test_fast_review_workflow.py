from pathlib import Path

from app.ai_config import HybridAIConfig
from app.academic_ai_engine import REVIEW_LEVEL_PROFILES, _batch


def test_fast_defaults(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    for name in (
        "AI_SECTION_BATCH_SIZE",
        "AI_LIGHT_SECTION_BATCH_SIZE",
        "AI_ADVANCED_SECTION_BATCH_SIZE",
        "AI_STRUCTURED_OUTPUT_RETRIES",
    ):
        monkeypatch.delenv(name, raising=False)

    config = HybridAIConfig.from_env()
    assert config.light_section_batch_size == 6
    assert config.section_batch_size == 5
    assert config.advanced_section_batch_size == 4
    assert config.structured_output_retries == 0
    assert config.deepseek_advanced_primary_reasoning_effort == "high"
    assert config.deepseek_advanced_reasoning_effort == "max"


def test_typical_chapter_needs_four_advanced_primary_batches():
    sections = list(range(15))
    assert len(_batch(sections, 4)) == 4


def test_issue_limits_are_concise_but_level_calibrated():
    assert REVIEW_LEVEL_PROFILES["light"]["normal_issue_limit_per_section"] == 2
    assert REVIEW_LEVEL_PROFILES["standard"]["normal_issue_limit_per_section"] == 4
    assert REVIEW_LEVEL_PROFILES["advanced"]["normal_issue_limit_per_section"] == 5


def test_universal_accuracy_audit_is_present_for_all_depths():
    source = Path("app/academic_ai_engine.py").read_text(encoding="utf-8")
    assert "academic-comment-audit-v1.8.6-universal" in source
    assert "Accuracy is mandatory at every review depth" in source
    assert "verification_batches" in source
    assert "audit_model = config.deepseek_advanced_model" in source
