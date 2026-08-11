from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from app.academic_ai_engine import _audit_batch_cap
from app.ai_config import HybridAIConfig
from app.ai_providers import AIProviderError, ProviderResult
from app.ai_schemas import AIUsageRecord
from app.model_router import CostAwareAIProvider, ReviewStage


class AuditPayload(BaseModel):
    judgement: str


def _config(monkeypatch) -> HybridAIConfig:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("VPROF_ENABLE_OPENAI", "true")
    monkeypatch.setenv("VPROF_ENABLE_DEEPSEEK", "false")
    monkeypatch.setenv("VPROF_COMBINED_APP_PIPELINE", "true")
    monkeypatch.setenv("OPENAI_FINAL_SYNTHESIS_MODEL", "gpt-5.6-terra")
    monkeypatch.setenv("OPENAI_FINAL_SYNTHESIS_FALLBACK_MODEL", "gpt-5.6-luna")
    return HybridAIConfig.from_env()


def test_long_standard_audit_has_a_hard_batch_cap(monkeypatch):
    config = _config(monkeypatch)
    assert _audit_batch_cap(
        depth="standard",
        audit_scope="chapter_range",
        batch_limit=4,
        config=config,
    ) == 8
    assert _audit_batch_cap(
        depth="standard",
        audit_scope="complete_thesis",
        batch_limit=4,
        config=config,
    ) == 8
    assert _audit_batch_cap(
        depth="light",
        audit_scope="complete_thesis",
        batch_limit=4,
        config=config,
    ) == 4
    assert _audit_batch_cap(
        depth="advanced",
        audit_scope="complete_thesis",
        batch_limit=4,
        config=config,
    ) == 6


def test_truncated_final_audit_is_returned_for_batch_splitting(monkeypatch):
    router = CostAwareAIProvider(_config(monkeypatch))
    calls: list[str] = []

    async def fake_openai(**kwargs):
        calls.append(kwargs["model"])
        if kwargs["model"] == "gpt-5.6-terra":
            raise AIProviderError(
                "OpenAI output was truncated because the output-token limit was reached."
            )
        return ProviderResult(
            data={"judgement": "fallback"},
            usage=AIUsageRecord(
                provider="openai",
                model=kwargs["model"],
                purpose="test",
            ),
        )

    monkeypatch.setattr(router.openai, "complete_json", fake_openai)
    with pytest.raises(AIProviderError, match="truncated"):
        asyncio.run(router.complete_json(
            model="gpt-5.6-luna",
            system_prompt="Audit.",
            user_prompt="Audit the bounded batch.",
            schema_model=AuditPayload,
            purpose="standard_universal_comment_accuracy_audit",
            reasoning_effort="medium",
            max_output_tokens=4800,
            stage=ReviewStage.FINAL_AUDIT,
            review_depth="standard",
        ))
    assert calls == ["gpt-5.6-terra"]
