from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import httpx
from pydantic import BaseModel, ValidationError

from .ai_config import HybridAIConfig
from .ai_schemas import AIUsageRecord


class AIProviderError(RuntimeError):
    pass


@dataclass
class ProviderResult:
    data: Dict[str, Any]
    usage: AIUsageRecord


def _extract_json_text(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                value = json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                raise AIProviderError(f"The model returned invalid JSON: {exc}") from exc
        else:
            raise AIProviderError(f"The model returned invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise AIProviderError("The model response must be a JSON object.")
    return value


def _make_openai_strict_schema(value: Any) -> Any:
    """Convert Pydantic JSON Schema into OpenAI's strict structured-output subset."""
    if isinstance(value, list):
        return [_make_openai_strict_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    output: Dict[str, Any] = {}
    for key, item in value.items():
        if key in {"default"}:
            continue
        output[key] = _make_openai_strict_schema(item)
    if output.get("type") == "object" or "properties" in output:
        properties = output.get("properties") or {}
        output["additionalProperties"] = False
        output["required"] = list(properties.keys())
    return output


def _openai_output_text(payload: Dict[str, Any]) -> str:
    chunks = []
    for item in payload.get("output", []) or []:
        if item.get("type") != "message":
            continue
        for content in item.get("content", []) or []:
            if content.get("type") == "output_text":
                chunks.append(content.get("text", ""))
            elif content.get("type") == "refusal":
                raise AIProviderError(content.get("refusal") or "The OpenAI model refused the request.")
    if chunks:
        return "".join(chunks)
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    raise AIProviderError("OpenAI returned no structured text output.")


def _usage_value(source: Dict[str, Any], *paths: str) -> int:
    for path in paths:
        cursor: Any = source
        valid = True
        for part in path.split("."):
            if not isinstance(cursor, dict) or part not in cursor:
                valid = False
                break
            cursor = cursor[part]
        if valid and isinstance(cursor, (int, float)):
            return int(cursor)
    return 0


async def _post_json_with_retry(
    *,
    url: str,
    headers: Dict[str, str],
    payload: Dict[str, Any],
    timeout_seconds: int,
    max_retries: int,
) -> Tuple[Dict[str, Any], str]:
    last_error: Optional[Exception] = None
    timeout = httpx.Timeout(timeout_seconds, connect=min(30, timeout_seconds))
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(max_retries + 1):
            try:
                response = await client.post(url, headers=headers, json=payload)
                request_id = response.headers.get("x-request-id", "")
                if response.status_code in {408, 409, 429} or response.status_code >= 500:
                    if attempt < max_retries:
                        await asyncio.sleep(min(8, 1.5 ** attempt))
                        continue
                response.raise_for_status()
                value = response.json()
                if not isinstance(value, dict):
                    raise AIProviderError("Provider returned a non-object response.")
                return value, request_id
            except (httpx.HTTPError, ValueError, AIProviderError) as exc:
                last_error = exc
                if attempt < max_retries:
                    await asyncio.sleep(min(8, 1.5 ** attempt))
                    continue
                break
    raise AIProviderError(str(last_error or "The provider request failed."))


class DeepSeekProvider:
    def __init__(self, config: HybridAIConfig):
        self.config = config

    async def complete_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema_model: type[BaseModel],
        purpose: str,
        thinking: bool,
    ) -> ProviderResult:
        body: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt + "\nThe final response must be valid JSON."},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": self.config.max_output_tokens,
            "thinking": {"type": "enabled" if thinking else "disabled"},
        }
        if thinking:
            body["reasoning_effort"] = self.config.deepseek_reasoning_effort

        payload, request_id = await _post_json_with_retry(
            url=f"{self.config.deepseek_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.config.deepseek_api_key}",
                "Content-Type": "application/json",
            },
            payload=body,
            timeout_seconds=self.config.timeout_seconds,
            max_retries=self.config.max_retries,
        )
        try:
            text = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIProviderError("DeepSeek returned no message content.") from exc
        raw = _extract_json_text(text)
        try:
            validated = schema_model.model_validate(raw)
        except ValidationError as exc:
            raise AIProviderError(f"DeepSeek output failed schema validation: {exc}") from exc

        usage_source = payload.get("usage") or {}
        input_tokens = _usage_value(usage_source, "prompt_tokens")
        output_tokens = _usage_value(usage_source, "completion_tokens")
        cached_tokens = _usage_value(
            usage_source,
            "prompt_cache_hit_tokens",
            "prompt_tokens_details.cached_tokens",
        )
        usage = AIUsageRecord(
            provider="deepseek",
            model=model,
            purpose=purpose,
            input_tokens=input_tokens,
            cached_input_tokens=cached_tokens,
            output_tokens=output_tokens,
            request_id=request_id or payload.get("id", ""),
        )
        return ProviderResult(data=validated.model_dump(), usage=usage)


class OpenAIProvider:
    def __init__(self, config: HybridAIConfig):
        self.config = config

    async def complete_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema_model: type[BaseModel],
        purpose: str,
        reasoning_effort: Optional[str] = None,
    ) -> ProviderResult:
        schema = _make_openai_strict_schema(schema_model.model_json_schema())
        body: Dict[str, Any] = {
            "model": model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_model.__name__.lower(),
                    "strict": True,
                    "schema": schema,
                }
            },
            "max_output_tokens": self.config.max_output_tokens,
            "store": False,
        }
        effort = reasoning_effort or self.config.openai_reasoning_effort
        if effort and effort != "none":
            body["reasoning"] = {"effort": effort}

        payload, request_id = await _post_json_with_retry(
            url=f"{self.config.openai_base_url}/responses",
            headers={
                "Authorization": f"Bearer {self.config.openai_api_key}",
                "Content-Type": "application/json",
            },
            payload=body,
            timeout_seconds=self.config.timeout_seconds,
            max_retries=self.config.max_retries,
        )
        raw = _extract_json_text(_openai_output_text(payload))
        try:
            validated = schema_model.model_validate(raw)
        except ValidationError as exc:
            raise AIProviderError(f"OpenAI output failed schema validation: {exc}") from exc

        usage_source = payload.get("usage") or {}
        input_tokens = _usage_value(usage_source, "input_tokens")
        output_tokens = _usage_value(usage_source, "output_tokens")
        cached_tokens = _usage_value(usage_source, "input_tokens_details.cached_tokens")
        usage = AIUsageRecord(
            provider="openai",
            model=model,
            purpose=purpose,
            input_tokens=input_tokens,
            cached_input_tokens=cached_tokens,
            output_tokens=output_tokens,
            request_id=request_id or payload.get("id", ""),
        )
        return ProviderResult(data=validated.model_dump(), usage=usage)
