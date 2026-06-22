from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pydantic import BaseModel
from app.ai_config import HybridAIConfig
from app.ai_providers import DeepSeekProvider, OpenAIProvider


class DiagnosticResult(BaseModel):
    status: str
    message: str


async def main() -> None:
    config = HybridAIConfig.from_env()
    print(f"DeepSeek configured: {config.deepseek_configured}; model: {config.deepseek_review_model}")
    print(f"OpenAI configured: {config.openai_configured}; model: {config.openai_verify_model}")
    prompt = 'Return JSON with status="ok" and message="provider connection succeeded".'
    if config.deepseek_configured:
        try:
            result = await DeepSeekProvider(config).complete_json(
                model=config.deepseek_review_model,
                system_prompt="You are a provider diagnostics assistant.",
                user_prompt=prompt,
                schema_model=DiagnosticResult,
                purpose="provider_diagnostic",
                thinking=False,
            )
            print("DeepSeek OK:", result.data)
        except Exception as exc:
            print("DeepSeek FAILED:", exc)
    if config.openai_configured:
        try:
            result = await OpenAIProvider(config).complete_json(
                model=config.openai_verify_model,
                system_prompt="You are a provider diagnostics assistant.",
                user_prompt=prompt,
                schema_model=DiagnosticResult,
                purpose="provider_diagnostic",
                reasoning_effort="low",
            )
            print("OpenAI OK:", result.data)
        except Exception as exc:
            print("OpenAI FAILED:", exc)


if __name__ == "__main__":
    asyncio.run(main())
