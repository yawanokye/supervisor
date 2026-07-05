from pathlib import Path

from app.ai_config import HybridAIConfig
from app.academic_ai_engine import REVIEW_LEVEL_PROFILES, _batch


def test_fast_defaults(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    for name in (
        "AI_SECTION_BATCH_SIZE",
        "AI_LIGHT_SECTION_BATCH_SIZE",
        "AI_ADVANCED_SECTION_BATCH_SIZE",
        "AI_STRUCTURED_OUTPUT_RETRIES",
        "OPENAI_CHAPTER_MODEL",
        "OPENAI_EXPERT_MODEL",
        "OPENAI_FINAL_AUDIT_MODEL",
        "OPENAI_EXTERNAL_MODEL",
        "OPENAI_REVIEW_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)

    config = HybridAIConfig.from_env()
    assert config.light_section_batch_size == 6
    assert config.section_batch_size == 5
    assert config.advanced_section_batch_size == 4
    assert config.structured_output_retries == 0
    assert config.openai_chapter_model == "gpt-5.4-mini"
    assert config.openai_expert_model == "gpt-5.4"
    assert config.openai_final_audit_model == "gpt-5.4"
    assert config.openai_chapter_reasoning_effort == "high"


def test_typical_chapter_needs_four_advanced_primary_batches():
    sections = list(range(15))
    assert len(_batch(sections, 4)) == 4


def test_issue_limits_are_concise_but_level_calibrated():
    assert REVIEW_LEVEL_PROFILES["light"]["normal_issue_limit_per_section"] == 2
    assert REVIEW_LEVEL_PROFILES["standard"]["normal_issue_limit_per_section"] == 4
    assert REVIEW_LEVEL_PROFILES["advanced"]["normal_issue_limit_per_section"] == 5


def test_universal_accuracy_audit_is_present_for_all_depths():
    source = Path("app/academic_ai_engine.py").read_text(encoding="utf-8")
    assert "academic-comment-audit-v1.9.2-gpt-5.4" in source
    assert "Accuracy is mandatory at every review depth" in source
    assert "verification_batches" in source
    assert "audit_model = config.openai_final_audit_model" in source
