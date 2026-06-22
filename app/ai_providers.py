from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import httpx
from pydantic import BaseModel, ValidationError

from .ai_config import HybridAIConfig
from .ai_schemas import AIUsageRecord

logger = logging.getLogger(__name__)


class AIProviderError(RuntimeError):
    pass


@dataclass
class ProviderResult:
    data: Dict[str, Any]
    usage: AIUsageRecord


def _short(value: Any, limit: int = 1200) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text if len(text) <= limit else text[:limit] + "…"


def _extract_json_text(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise AIProviderError("The model returned empty JSON content.")
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
                raise AIProviderError(f"The model returned invalid JSON: {exc}. Output: {_short(raw)}") from exc
        else:
            raise AIProviderError(f"The model returned invalid JSON: {exc}. Output: {_short(raw)}") from exc
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


def _example_from_schema(schema: Dict[str, Any], root: Optional[Dict[str, Any]] = None, depth: int = 0) -> Any:
    root = root or schema
    if depth > 7:
        return ""
    if "$ref" in schema:
        ref = schema["$ref"].split("/")[-1]
        target = (root.get("$defs") or {}).get(ref, {})
        return _example_from_schema(target, root, depth + 1)
    if "anyOf" in schema:
        options = [x for x in schema["anyOf"] if x.get("type") != "null"]
        return _example_from_schema(options[0] if options else {}, root, depth + 1)
    if "enum" in schema and schema["enum"]:
        return schema["enum"][0]
    kind = schema.get("type")
    if kind == "object" or "properties" in schema:
        return {key: _example_from_schema(value, root, depth + 1) for key, value in (schema.get("properties") or {}).items()}
    if kind == "array":
        return [_example_from_schema(schema.get("items") or {}, root, depth + 1)]
    if kind in {"number", "integer"}:
        return 75 if kind == "integer" else 0.85
    if kind == "boolean":
        return True
    return "text"


def _json_contract(schema_model: type[BaseModel]) -> str:
    schema = schema_model.model_json_schema()
    example = _example_from_schema(schema)
    return (
        "Return one JSON object that matches this schema exactly. Do not rename, omit, or add fields.\n"
        f"JSON SCHEMA:\n{json.dumps(schema, ensure_ascii=False, separators=(',', ':'))}\n"
        f"EXAMPLE SHAPE:\n{json.dumps(example, ensure_ascii=False, separators=(',', ':'))}"
    )


def _clamp(value: Any, low: float, high: float, default: float) -> float:
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return default


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _normalise_model_payload(raw: Dict[str, Any], schema_model: type[BaseModel]) -> Dict[str, Any]:
    """Repair small, common model-format deviations without inventing academic findings."""
    name = schema_model.__name__
    value = dict(raw)

    if name == "AcademicReviewBatch":
        reviews = value.get("reviews") if isinstance(value.get("reviews"), list) else []
        value = {"reviews": reviews}

    elif name == "AcademicSectionReview":
        if isinstance(value.get("review"), dict):
            value = dict(value["review"])
        section_name = str(value.get("section_name") or value.get("section") or "Reviewed section").strip()
        assessment = str(value.get("section_assessment") or value.get("assessment") or value.get("summary") or "").strip()
        score = _clamp(value.get("section_score", value.get("score")), 0, 100, 50.0)
        strengths = []
        for item in _list(value.get("strengths")):
            if not isinstance(item, dict):
                continue
            strengths.append({
                "category": item.get("category") or "other",
                "section": item.get("section") or section_name,
                "evidence_paragraph_ids": _list(item.get("evidence_paragraph_ids") or item.get("paragraph_ids")),
                "observation": str(item.get("observation") or item.get("strength") or "").strip(),
            })
        issues = []
        for idx, item in enumerate(_list(value.get("issues") or value.get("findings")), start=1):
            if not isinstance(item, dict):
                continue
            title = str(item.get("issue_title") or item.get("title") or "Academic issue").strip()
            fid = str(item.get("finding_id") or "").strip()
            if not fid:
                digest = hashlib.sha1(f"{section_name}|{idx}|{title}".encode("utf-8")).hexdigest()[:10]
                fid = f"finding-{digest}"
            issues.append({
                "finding_id": fid,
                "category": item.get("category") or "other",
                "section": item.get("section") or section_name,
                "issue_title": title,
                "severity": item.get("severity") if item.get("severity") in {"critical", "major", "moderate", "minor"} else "moderate",
                "confidence": _clamp(item.get("confidence"), 0, 1, 0.75),
                "evidence_paragraph_ids": _list(item.get("evidence_paragraph_ids") or item.get("paragraph_ids")),
                "problematic_quote": str(item.get("problematic_quote") or item.get("quote") or "").strip(),
                "assessment": str(item.get("assessment") or item.get("expert_assessment") or item.get("explanation") or "").strip(),
                "academic_consequence": str(item.get("academic_consequence") or item.get("consequence") or item.get("implication") or "").strip(),
                "required_action": str(item.get("required_action") or item.get("action") or item.get("recommendation") or "").strip(),
            })
        value = {
            "section_name": section_name,
            "section_score": score,
            "section_assessment": assessment,
            "strengths": strengths,
            "issues": issues,
            "coverage_warning": str(value.get("coverage_warning") or "").strip(),
        }
        if not assessment and not strengths and not issues:
            raise AIProviderError("The model returned an empty academic section review.")

    elif name == "AcademicVerificationBatch":
        if isinstance(value.get("verification"), dict):
            value = dict(value["verification"])
        value.setdefault("verifications", [])
        value.setdefault("missed_issues", [])

    elif name == "DecisionBatch":
        value.setdefault("decisions", [])

    elif name == "DocumentMap":
        defaults = {
            "research_problem": "", "purpose": "", "objectives": [], "research_questions": [],
            "hypotheses": [], "theories": [], "variables": [], "population_and_sample": "",
            "methods_by_objective": {}, "findings_by_objective": {}, "conclusions_by_objective": {},
            "recommendations_by_finding": {}, "inconsistencies": [],
        }
        for key, default in defaults.items():
            value.setdefault(key, default)

    return value


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
    incomplete = payload.get("incomplete_details") or {}
    reason = incomplete.get("reason") if isinstance(incomplete, dict) else ""
    raise AIProviderError(f"OpenAI returned no structured text output{f' ({reason})' if reason else ''}.")


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
                if response.status_code >= 400:
                    raise AIProviderError(
                        f"HTTP {response.status_code} from {url}: {_short(response.text)}"
                        + (f" [request_id={request_id}]" if request_id else "")
                    )
                content_type = (response.headers.get("content-type") or "").lower()
                if "application/json" not in content_type:
                    preview = _short(response.text, 500)
                    raise AIProviderError(
                        "The model service returned a non-JSON response. "
                        f"Content-Type: {content_type or 'unknown'}. Response: {preview}"
                    )
                value = response.json()
                if not isinstance(value, dict):
                    raise AIProviderError("Provider returned a non-object JSON response.")
                return value, request_id
            except (httpx.HTTPError, ValueError, AIProviderError) as exc:
                last_error = exc
                if attempt < max_retries:
                    await asyncio.sleep(min(8, 1.5 ** attempt))
                    continue
                break
    raise AIProviderError(str(last_error or "The provider request failed."))


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
        max_output_tokens: Optional[int] = None,
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
            "max_output_tokens": max_output_tokens or self.config.max_output_tokens,
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
        raw = _normalise_model_payload(raw, schema_model)
        try:
            validated = schema_model.model_validate(raw)
        except ValidationError as exc:
            raise AIProviderError(f"OpenAI output failed schema validation: {exc}") from exc

        usage_source = payload.get("usage") or {}
        input_tokens = _usage_value(usage_source, "input_tokens")
        output_tokens = _usage_value(usage_source, "output_tokens")
        cached_tokens = _usage_value(usage_source, "input_tokens_details.cached_tokens")
        usage = AIUsageRecord(
            provider="openai", model=model, purpose=purpose,
            input_tokens=input_tokens, cached_input_tokens=cached_tokens,
            output_tokens=output_tokens,
            request_id=request_id or payload.get("id", ""),
        )
        return ProviderResult(data=validated.model_dump(), usage=usage)
