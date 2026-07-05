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


async def main() -> None:
    config = HybridAIConfig.from_env()
    if not config.openai_configured:
        raise SystemExit("Set OPENAI_API_KEY before running this smoke test.")

    provider = OpenAIProvider(config)
    result = await provider.complete_json(
        model=config.openai_review_model,
        system_prompt=(
            "You are testing the structured-output connection. Return only a "
            "valid document map for the supplied text."
        ),
        user_prompt=(
            "Study title: Digital procurement and efficiency. Objective: assess "
            "the relationship between e-ordering and procurement efficiency."
        ),
        schema_model=DocumentMap,
        purpose="openai_o3_mini_smoke_test",
        reasoning_effort=config.openai_review_reasoning_effort,
        max_output_tokens=1200,
    )
    print(
        "OpenAI smoke test passed:",
        config.openai_review_model,
        result.usage.request_id,
    )


if __name__ == "__main__":
    asyncio.run(main())
