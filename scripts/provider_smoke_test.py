from __future__ import annotations

__test__ = False

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai_config import HybridAIConfig
from app.ai_providers import DeepSeekProvider
from app.ai_schemas import DocumentMap


async def main():
    config = HybridAIConfig.from_env()
    if not config.deepseek_configured:
        print("Academic review service not configured.")
        return

    provider = DeepSeekProvider(config)
    standard = await provider.complete_json(
        model=config.deepseek_review_model,
        system_prompt="Return JSON only.",
        user_prompt="Return an empty thesis map.",
        schema_model=DocumentMap,
        purpose="deepseek_standard_smoke_test",
        reasoning_effort=config.deepseek_reasoning_effort,
        max_output_tokens=1200,
    )
    print(
        "Light/Standard service OK:",
        config.deepseek_review_model,
        json.dumps(standard.data)[:120],
    )

    advanced = await provider.complete_json(
        model=config.deepseek_advanced_model,
        system_prompt="Return JSON only.",
        user_prompt="Return an empty thesis map.",
        schema_model=DocumentMap,
        purpose="deepseek_advanced_smoke_test",
        reasoning_effort=config.deepseek_advanced_reasoning_effort,
        max_output_tokens=1200,
    )
    print(
        "Advanced service OK:",
        config.deepseek_advanced_model,
        json.dumps(advanced.data)[:120],
    )


if __name__ == "__main__":
    asyncio.run(main())
