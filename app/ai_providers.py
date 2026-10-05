from __future__ import annotations

import asyncio
import copy
import random
import os
from .model_compatibility import capabilities, compatible_effort, adapt_rejected_parameter
from .provider_state import request_state
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, Tuple

import httpx
from pydantic import BaseModel, ValidationError

from .ai_config import HybridAIConfig
from .ai_schemas import AIUsageRecord, AcademicSectionReviewItem

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
        normalised_reviews = []
        for item in reviews:
            if not isinstance(item, dict):
                continue
            try:
                normalised_reviews.append(
                    _normalise_model_payload(item, AcademicSectionReviewItem)
                )
            except AIProviderError:
                # Keep the original item so Pydantic can report a precise error.
                normalised_reviews.append(item)
        value = {"reviews": normalised_reviews}

    elif name in {"AcademicSectionReview", "AcademicSectionReviewItem"}:
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
                "supervisory_comment": str(item.get("supervisory_comment") or "").strip(),
                "illustrative_guidance": str(item.get("illustrative_guidance") or item.get("example") or item.get("illustrative_example") or "").strip(),
            })
        normalised_section = {
            "section_name": section_name,
            "section_score": score,
            "section_assessment": assessment,
            "strengths": strengths,
            "issues": issues,
            "coverage_warning": str(value.get("coverage_warning") or "").strip(),
        }
        if name == "AcademicSectionReviewItem":
            normalised_section["section_key"] = str(
                value.get("section_key") or ""
            ).strip()
        value = normalised_section
        if not assessment and not strengths and not issues:
            raise AIProviderError("The model returned an empty academic section review.")

    elif name == "AcademicVerificationBatch":
        if isinstance(value.get("verification"), dict):
            value = dict(value["verification"])
        verifications = []
        for item in _list(value.get("verifications")):
            if not isinstance(item, dict):
                continue
            row = dict(item)
            row.setdefault("illustrative_guidance", str(row.get("example") or row.get("illustrative_example") or "").strip())
            verifications.append(row)
        missed = []
        for item in _list(value.get("missed_issues")):
            if not isinstance(item, dict):
                continue
            row = dict(item)
            row.setdefault("illustrative_guidance", str(row.get("example") or row.get("illustrative_example") or "").strip())
            missed.append(row)
        value = {"verifications": verifications, "missed_issues": missed}

    elif name == "DecisionBatch":
        value.setdefault("decisions", [])

    elif name in {"ExternalAssessmentReport", "ExternalAssessmentAdjudication"}:
        if isinstance(value.get("external_assessment"), dict):
            value = dict(value["external_assessment"])
        elif isinstance(value.get("report"), dict):
            value = dict(value["report"])
        if name == "ExternalAssessmentReport":
            value.setdefault("major_strengths", [])
        value.setdefault("corrections", [])
        value.setdefault("oral_examination_questions", [])
        value.setdefault("priority_corrections_before_award", [])

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
    status = str(payload.get("status") or "").strip().lower()
    incomplete = payload.get("incomplete_details") or {}
    reason = incomplete.get("reason") if isinstance(incomplete, dict) else ""
    if status == "incomplete":
        if reason == "max_output_tokens":
            raise AIProviderError(
                "OpenAI output was truncated because the output-token limit was reached."
            )
        raise AIProviderError(
            f"OpenAI returned an incomplete response{f' ({reason})' if reason else ''}."
        )

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
                        try:
                            delay = max(0, min(30, float(response.headers.get("retry-after", "0"))))
                        except ValueError:
                            delay = 0
                        await asyncio.sleep(delay or min(8, 1.5 ** attempt) + random.uniform(0,.3))
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
                if isinstance(exc, AIProviderError) and re.search(r"HTTP (?:400|401|403|404|422)", str(exc)):
                    raise
                if attempt < max_retries:
                    await asyncio.sleep(min(8, 1.5 ** attempt))
                    continue
                break
    raise AIProviderError(str(last_error or "The provider request failed."))


async def _get_json_with_retry(
    *,
    url: str,
    headers: Dict[str, str],
    timeout_seconds: int,
    max_retries: int,
) -> Tuple[Dict[str, Any], str]:
    """Retrieve an asynchronous provider response with bounded retries."""
    last_error: Optional[Exception] = None
    timeout = httpx.Timeout(timeout_seconds, connect=min(30, timeout_seconds))
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(max_retries + 1):
            try:
                response = await client.get(url, headers=headers)
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
    raise AIProviderError(str(last_error or "The provider response could not be retrieved."))


async def _poll_openai_background_response(
    *,
    base_url: str,
    response_payload: Dict[str, Any],
    headers: Dict[str, str],
    poll_seconds: int,
    timeout_seconds: int,
    request_timeout_seconds: int,
    max_retries: int,
) -> Tuple[Dict[str, Any], str]:
    """Poll a Responses API background job until it reaches a terminal state."""
    response_id = str(response_payload.get("id") or "").strip()
    if not response_id:
        raise AIProviderError("OpenAI background response did not include an identifier.")

    terminal = {"completed", "failed", "cancelled", "incomplete"}
    payload = response_payload
    request_id = ""
    deadline = time.monotonic() + max(60, int(timeout_seconds))
    while True:
        status = str(payload.get("status") or "").strip().lower()
        if status in terminal:
            if status in {"failed", "cancelled"}:
                error = payload.get("error") or payload.get("incomplete_details") or status
                raise AIProviderError(
                    f"OpenAI background response {status}: {_short(error)}"
                )
            return payload, request_id
        if time.monotonic() >= deadline:
            raise AIProviderError(
                "OpenAI background response exceeded the configured processing window."
            )
        await asyncio.sleep(max(1, int(poll_seconds)))
        payload, latest_request_id = await _get_json_with_retry(
            url=f"{base_url}/responses/{response_id}",
            headers=headers,
            timeout_seconds=max(30, int(request_timeout_seconds)),
            max_retries=max_retries,
        )
        request_id = latest_request_id or request_id



def _deepseek_output_text(payload: Dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        raise AIProviderError("DeepSeek returned no completion choices.")
    first = choices[0] if isinstance(choices[0], dict) else {}
    finish_reason = first.get("finish_reason")
    message = first.get("message") or {}
    content = message.get("content")

    if finish_reason == "length":
        raise AIProviderError(
            "DeepSeek output was truncated because the output-token limit was reached."
        )
    if finish_reason == "insufficient_system_resource":
        raise AIProviderError(
            "DeepSeek could not complete the request because provider resources were unavailable."
        )
    if not isinstance(content, str) or not content.strip():
        raise AIProviderError("DeepSeek returned empty JSON content.")
    return content


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
        reasoning_effort: Optional[str] = None,
        max_output_tokens: Optional[int] = None,
        request_timeout_seconds: Optional[int] = None,
        request_max_retries: Optional[int] = None,
        thinking_enabled: Optional[bool] = None,
        image_data_urls: Optional[Sequence[str]] = None,
    ) -> ProviderResult:
        contract = _json_contract(schema_model)
        reinforced_system = (
            system_prompt.rstrip()
            + "\n\n"
            + contract
            + "\nReturn JSON only. Do not use markdown fences."
        )

        effort = (
            reasoning_effort
            or self.config.deepseek_reasoning_effort
            or "high"
        ).lower()
        if effort not in {"high", "max"}:
            effort = "high"

        use_thinking = (
            self.config.deepseek_thinking_enabled
            if thinking_enabled is None
            else bool(thinking_enabled)
        )

        body: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": reinforced_system},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": max_output_tokens or self.config.max_output_tokens,
            "thinking": {"type": "enabled" if use_thinking else "disabled"},
        }
        # DeepSeek's OpenAI-compatible API expects reasoning_effort as a
        # top-level field. The previous nested placement could be rejected by
        # the provider and silently move the whole review to OpenAI.
        if use_thinking:
            body["reasoning_effort"] = effort

        last_error: Optional[Exception] = None
        attempts = max(1, self.config.structured_output_retries + 1)
        requested_output_tokens = int(
            max_output_tokens or self.config.max_output_tokens
        )

        for attempt in range(attempts):
            request_body = dict(body)
            previous_message = str(last_error or "").strip().lower()
            if (
                attempt
                and self.config.deepseek_truncation_recovery_enabled
                and "truncated because the output-token limit" in previous_message
            ):
                expanded = max(
                    requested_output_tokens + 1200,
                    int(
                        requested_output_tokens
                        * self.config.deepseek_truncation_retry_multiplier
                    ),
                )
                request_body["max_tokens"] = min(
                    self.config.deepseek_max_output_tokens,
                    expanded,
                )
                # A cut-off strict JSON object cannot be repaired while hidden
                # reasoning continues to consume the same completion budget.
                # The bounded retry therefore prioritises the complete schema.
                request_body["thinking"] = {"type": "disabled"}
                request_body.pop("reasoning_effort", None)
            if attempt:
                request_body["messages"] = [
                    request_body["messages"][0],
                    {
                        "role": "user",
                        "content": (
                            user_prompt
                            + "\n\nThe previous response was empty, incomplete, or did not "
                              "match the required schema. Return one complete compact JSON object "
                              "matching the schema exactly. Do not repeat source passages, do not "
                              "add commentary outside JSON, and keep assessments and actions concise."
                        ),
                    },
                ]

            try:
                payload, request_id = await _post_json_with_retry(
                    url=f"{self.config.deepseek_base_url}/chat/completions",
                    headers={
                        "Authorization": (
                            f"Bearer {self.config.deepseek_api_key}"
                        ),
                        "Content-Type": "application/json",
                    },
                    payload=request_body,
                    timeout_seconds=(
                        request_timeout_seconds
                        if request_timeout_seconds is not None
                        else self.config.timeout_seconds
                    ),
                    max_retries=(
                        request_max_retries
                        if request_max_retries is not None
                        else self.config.max_retries
                    ),
                )

                raw = _extract_json_text(_deepseek_output_text(payload))
                raw = _normalise_model_payload(raw, schema_model)
                validated = schema_model.model_validate(raw)

                usage_source = payload.get("usage") or {}
                input_tokens = _usage_value(
                    usage_source,
                    "prompt_tokens",
                    "input_tokens",
                )
                output_tokens = _usage_value(
                    usage_source,
                    "completion_tokens",
                    "output_tokens",
                )
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
                return ProviderResult(
                    data=validated.model_dump(),
                    usage=usage,
                )

            except (ValidationError, AIProviderError) as exc:
                last_error = exc
                message = str(exc).lower()
                if (
                    "truncated because the output-token limit" in message
                    and purpose in {
                        "batched_academic_review",
                        "chapter_packet_coverage_recovery",
                        "single_target_coverage_recovery",
                    }
                ):
                    # Do not pay for the same oversized academic packet twice.
                    # The academic engine responds to finish_reason=length by
                    # splitting the unit into one-target recovery requests.
                    break
                if attempt + 1 >= attempts:
                    break

        if isinstance(last_error, ValidationError):
            raise AIProviderError(
                f"DeepSeek output failed schema validation: {last_error}"
            ) from last_error
        raise AIProviderError(str(last_error or "DeepSeek request failed."))

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
        request_timeout_seconds: Optional[int] = None,
        request_max_retries: Optional[int] = None,
        thinking_enabled: Optional[bool] = None,
        image_data_urls: Optional[Sequence[str]] = None,
    ) -> ProviderResult:
        schema = _make_openai_strict_schema(schema_model.model_json_schema())
        caps = capabilities(model)
        effort = compatible_effort(model, reasoning_effort or self.config.openai_reasoning_effort or 'medium')

        user_content: Any = user_prompt
        valid_images = [
            str(value) for value in image_data_urls or []
            if str(value).startswith("data:image/")
        ][:max(1, int(os.getenv("AI_MAX_FRAMEWORK_IMAGES", "12")))]
        if valid_images and not caps['vision']:
            system_prompt += '\nThis model cannot inspect the supplied images. Do not claim to verify diagram arrows or legibility. Request manual visual verification when needed.'
            valid_images = []
        if valid_images:
            user_content = [
                {"type": "input_text", "text": user_prompt},
                *[
                    {"type": "input_image", "image_url": value, "detail": "high"}
                    for value in valid_images
                ],
            ]
        base_input = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        base_body: Dict[str, Any] = {
            "model": model,
            "input": base_input,
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
        if effort:
            base_body["reasoning"] = {"effort": effort}
        if not caps["structured"]:
            base_body["text"]["format"] = {"type": "json_object"}
            base_input[0]["content"] += "\nReturn JSON matching this schema: " + json.dumps(schema)
        if self.config.openai_prompt_cache_enabled:
            cache_source = (
                f"{model}\n{purpose}\n{system_prompt}\n"
                + json.dumps(schema, sort_keys=True, separators=(",", ":"))
            )
            base_body["prompt_cache_key"] = hashlib.sha256(
                cache_source.encode("utf-8")
            ).hexdigest()[:64]

        use_background = bool(
            self.config.openai_background_mode_enabled
            and caps["background"]
            and effort in {"high", "xhigh", "max"}
        )
        if use_background:
            base_body["background"] = True

        last_error: Optional[Exception] = None
        attempts = max(1, self.config.structured_output_retries + 1)
        requested_output_tokens = int(
            max_output_tokens or self.config.max_output_tokens
        )
        for attempt in range(attempts):
            body = copy.deepcopy(base_body)
            if attempt:
                previous_message = str(last_error or "").lower()
                if "truncated because the output-token limit" in previous_message:
                    # A strict JSON response cannot be repaired from a cut-off
                    # object. Give the one structured-output retry enough room,
                    # bounded by the application's global output ceiling.
                    expanded = max(
                        requested_output_tokens + 1600,
                        requested_output_tokens * 2,
                    )
                    body["max_output_tokens"] = min(
                        int(self.config.max_output_tokens), int(expanded)
                    )
                    retry_instruction = (
                        "The previous JSON object was truncated. Return a complete, "
                        "concise JSON object. Preserve every required field, avoid "
                        "repeating the source text, and keep explanations direct."
                    )
                else:
                    retry_instruction = (
                        "The previous response was empty, incomplete, or did not "
                        "match the required schema. Return one complete JSON object "
                        "that follows the supplied schema exactly."
                    )
                retry_text = user_prompt + "\n\n" + retry_instruction
                retry_content: Any = retry_text
                if valid_images:
                    retry_content = [
                        {"type": "input_text", "text": retry_text},
                        *[
                            {"type": "input_image", "image_url": value, "detail": "high"}
                            for value in valid_images
                        ],
                    ]
                body["input"] = [base_input[0], {"role": "user", "content": retry_content}]
            try:
                headers = {
                    "Authorization": f"Bearer {self.config.openai_api_key}",
                    "Content-Type": "application/json",
                }
                timeout = request_timeout_seconds or self.config.timeout_seconds
                retries = self.config.max_retries if request_max_retries is None else request_max_retries
                manager, state_key, state_hash = request_state(body)
                saved = manager.load(state_key, expected_input_hash=state_hash) if manager else None
                payload = (saved or {}).get('payload')
                if payload and payload.get('status') in {'cancelled','unavailable'}:
                    payload = None  # A manually resumed user-stopped request needs a fresh submission.
                request_id = (saved or {}).get('request_id', '')
                if not payload:
                    budget_key = 'provider-call-budget'
                    budget = manager.load(budget_key) or {} if manager else {}
                    limit = max(0, int(os.getenv('VPROF_CHAPTER_MAX_API_CALLS', '250')))
                    if limit and int(budget.get('submissions',0)) >= limit:
                        raise AIProviderError('Chapter API-call budget reached. Saved work is retained. Increase VPROF_CHAPTER_MAX_API_CALLS and resume to continue.')
                    if manager: manager.save(budget_key, {'submissions': int(budget.get('submissions',0))+1})
                    endpoint = caps['endpoint']
                    for compatibility_attempt in range(5):
                        request_body = copy.deepcopy(body)
                        if endpoint == 'chat':
                            messages = []
                            for item in body['input']:
                                content = item['content']
                                if isinstance(content,list):
                                    content = [({'type':'text','text':v['text']} if v['type']=='input_text' else {'type':'image_url','image_url':{'url':v['image_url']}}) for v in content]
                                messages.append({'role':item['role'],'content':content})
                            request_body = {'model':model,'messages':messages,'max_tokens':body['max_output_tokens']}
                            fmt = body.get('text',{}).get('format')
                            if fmt:
                                request_body['response_format'] = ({'type':'json_schema','json_schema':{k:v for k,v in fmt.items() if k != 'type'}} if fmt.get('type') == 'json_schema' else fmt)
                            if 'reasoning' in body:
                                request_body['reasoning_effort'] = body['reasoning']['effort']
                        try:
                            payload, request_id = await _post_json_with_retry(url=f'{self.config.openai_base_url}/'+('chat/completions' if endpoint=='chat' else 'responses'), headers=headers, payload=request_body,
                                timeout_seconds=min(90,timeout) if body.get('background') else timeout, max_retries=retries)
                            if endpoint == 'chat':
                                message = ((payload.get('choices') or [{}])[0].get('message') or {}).get('content','')
                                if (payload.get('choices') or [{}])[0].get('finish_reason') == 'length':
                                    raise AIProviderError('OpenAI output was truncated because the output-token limit was reached.')
                                u = payload.get('usage') or {}
                                payload = {**payload, 'status':'completed', 'output':[{'type':'message','content':[{'type':'output_text','text':message}]}], 'usage':{'input_tokens':u.get('prompt_tokens',0),'output_tokens':u.get('completion_tokens',0),'input_tokens_details':u.get('prompt_tokens_details',{})}}
                            break
                        except AIProviderError as error:
                            if compatibility_attempt >= 4: raise
                            if endpoint == 'responses' and 'http 400' in str(error).lower() and ('not supported in the responses' in str(error).lower() or 'does not support the responses' in str(error).lower()):
                                endpoint = 'chat'; continue
                            if not adapt_rejected_parameter(body,str(error)): raise
                            if body.get('text',{}).get('format',{}).get('type') != 'json_schema':
                                if 'Return JSON matching this schema:' not in body['input'][0]['content']:
                                    body['input'][0]['content'] += '\nReturn JSON matching this schema: '+json.dumps(schema)
                    if manager:
                        manager.save(state_key, {'payload':payload,'request_id':request_id}, input_hash=state_hash, message='Provider response saved before polling')
                if body.get('background') and str(payload.get('status') or '').lower() not in {'completed','failed','cancelled','incomplete'}:
                    try:
                        payload, poll_id = await _poll_openai_background_response(base_url=self.config.openai_base_url,response_payload=payload,headers=headers,
                            poll_seconds=self.config.openai_background_poll_seconds,timeout_seconds=self.config.openai_background_timeout_seconds,request_timeout_seconds=timeout,max_retries=retries)
                    except AIProviderError as error:
                        if manager and 'HTTP 404' in str(error):
                            manager.save(state_key, {'payload':{**payload,'status':'unavailable'},'request_id':request_id},input_hash=state_hash,message='Retained provider response is no longer retrievable; resume requires a fresh submission')
                        raise
                    request_id = poll_id or request_id
                    if manager: manager.save(state_key, {'payload':payload,'request_id':request_id},input_hash=state_hash,message='Provider terminal response saved')
                raw = _extract_json_text(_openai_output_text(payload))
                raw = _normalise_model_payload(raw, schema_model)
                validated = schema_model.model_validate(raw)

                usage_source = payload.get("usage") or {}
                input_tokens = _usage_value(usage_source, "input_tokens")
                output_tokens = _usage_value(usage_source, "output_tokens")
                cached_tokens = _usage_value(
                    usage_source,
                    "input_tokens_details.cached_tokens",
                )
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
            except (ValidationError, AIProviderError) as exc:
                last_error = exc
                if isinstance(exc, AIProviderError) and re.search(r"HTTP (?:400|401|403|404|422)", str(exc)):
                    break
                if attempt + 1 >= attempts:
                    break

        if isinstance(last_error, ValidationError):
            raise AIProviderError(
                f"OpenAI output for model '{model}' and purpose '{purpose}' failed schema validation: {last_error}"
            ) from last_error
        raise AIProviderError(
            f"OpenAI request for model '{model}' and purpose '{purpose}' failed: "
            f"{str(last_error or 'unknown provider error')}"
        )
