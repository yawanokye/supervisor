from __future__ import annotations

import asyncio
import json

from app.ai_config import HybridAIConfig
from app.ai_providers import OpenAIProvider
from app.ai_schemas import DocumentMap

async def main():
    config = HybridAIConfig.from_env()
    if not config.openai_configured:
        raise SystemExit("OPENAI_API_KEY is not configured")
    provider = OpenAIProvider(config)
    for model in (config.openai_mini_model, config.openai_review_model):
        result = await provider.complete_json(
            model=model, system_prompt="Return JSON only.",
            user_prompt="Return an empty thesis map.", schema_model=DocumentMap,
            purpose="smoke_test", reasoning_effort="low", max_output_tokens=1200,
        )
        print(model, "OK", json.dumps(result.data)[:120])

if __name__ == "__main__":
    asyncio.run(main())
