from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ai_config import HybridAIConfig
from app.ai_providers import OpenAIProvider
from app.ai_schemas import DocumentMap


async def _check_model(
    provider: OpenAIProvider,
    *,
    model: str,
    effort: str,
    purpose: str,
) -> None:
    result = await provider.complete_json(
        model=model,
        system_prompt=(
            "You are testing the structured-output connection. Return only a "
            "valid document map for the supplied text."
        ),
        user_prompt=(
            "Study title: Digital procurement and efficiency. Objective: assess "
            "the relationship between e-ordering and procurement efficiency."
        ),
        schema_model=DocumentMap,
        purpose=purpose,
        reasoning_effort=effort,
        max_output_tokens=1200,
    )
    print("OpenAI smoke test passed:", model, result.usage.request_id)


async def main() -> None:
    config = HybridAIConfig.from_env()
    if not config.openai_configured:
        raise SystemExit("Set OPENAI_API_KEY before running this smoke test.")

    provider = OpenAIProvider(config)
    await _check_model(
        provider,
        model=config.openai_chapter_model,
        effort=config.openai_chapter_reasoning_effort,
        purpose="openai_chapter_model_smoke_test",
    )
    if config.openai_expert_model != config.openai_chapter_model:
        await _check_model(
            provider,
            model=config.openai_expert_model,
            effort=config.openai_expert_reasoning_effort,
            purpose="openai_expert_model_smoke_test",
        )


if __name__ == "__main__":
    asyncio.run(main())
