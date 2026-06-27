from __future__ import annotations

import asyncio
import json

from app.ai_config import HybridAIConfig
from app.ai_providers import DeepSeekProvider, OpenAIProvider
from app.ai_schemas import DocumentMap


async def main():
    config = HybridAIConfig.from_env()

    if config.deepseek_configured:
        provider = DeepSeekProvider(config)
        result = await provider.complete_json(
            model=config.deepseek_review_model,
            system_prompt="Return JSON only.",
            user_prompt="Return an empty thesis map.",
            schema_model=DocumentMap,
            purpose="deepseek_smoke_test",
            reasoning_effort=config.deepseek_reasoning_effort,
            max_output_tokens=1200,
        )
        print(
            "Light/Standard review service OK:",
            config.deepseek_review_model,
            json.dumps(result.data)[:120],
        )
    else:
        print("Light/Standard review service not configured.")

    if config.openai_configured:
        provider = OpenAIProvider(config)
        result = await provider.complete_json(
            model=config.openai_review_model,
            system_prompt="Return JSON only.",
            user_prompt="Return an empty thesis map.",
            schema_model=DocumentMap,
            purpose="openai_smoke_test",
            reasoning_effort=config.openai_review_reasoning_effort,
            max_output_tokens=1200,
        )
        print(
            "Advanced review service OK:",
            config.openai_review_model,
            json.dumps(result.data)[:120],
        )
    else:
        print("Advanced review service not configured.")


if __name__ == "__main__":
    asyncio.run(main())
