"""Cost-aware multi-provider routing integrated with VProfessor's providers.

This module intentionally reuses :mod:`app.ai_providers` rather than adding a
second SDK stack. It preserves the application's strict Pydantic schemas,
checkpoint payloads, native DOCX comments and existing usage accounting.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, Type

from pydantic import BaseModel

from .ai_config import HybridAIConfig
from .ai_providers import (
    AIProviderError,
    DeepSeekProvider,
    OpenAIProvider,
    ProviderResult,
)
from .ai_schemas import AIUsageRecord

logger = logging.getLogger(__name__)


class RoutingProfile(str, Enum):
    ECONOMY = "economy"
    BALANCED = "balanced"
    QUALITY = "quality"


class ReviewStage(str, Enum):
    DOCUMENT_TRIAGE = "document_triage"
    STRUCTURE_MAP = "structure_map"
    LANGUAGE_SCAN = "language_scan"
    COMMENT_DEDUPLICATION = "comment_deduplication"
    LIGHT_REVIEW = "light_review"
    STANDARD_REVIEW = "standard_review"
    RESEARCH_INTENSIVE_REVIEW = "research_intensive_review"
    ADVANCED_REVIEW = "advanced_review"
    FINAL_AUDIT = "final_audit"
    RESEARCH_INTENSIVE_AUDIT = "research_intensive_audit"
    EXTERNAL_EXAMINATION = "external_examination"
    JSON_REPAIR = "json_repair"


class ProviderName(str, Enum):
    OPENAI = "openai"
    DEEPSEEK = "deepseek"


@dataclass(frozen=True)
class RouteTarget:
    provider: ProviderName
    model: str
    reasoning_effort: str
    thinking_enabled: Optional[bool] = None


@dataclass(frozen=True)
class RoutePlan:
    stage: ReviewStage
    profile: RoutingProfile
    primary: RouteTarget
    fallback: Optional[RouteTarget]
    escalation: Optional[RouteTarget]
    allow_escalation: bool

    def signature(self) -> str:
        values = [
            self.profile.value,
            self.stage.value,
            f"{self.primary.provider.value}:{self.primary.model}:{self.primary.reasoning_effort}",
        ]
        if self.fallback:
            values.append(
                f"fallback={self.fallback.provider.value}:{self.fallback.model}:{self.fallback.reasoning_effort}"
            )
        if self.escalation:
            values.append(
                f"escalation={self.escalation.provider.value}:{self.escalation.model}:{self.escalation.reasoning_effort}"
            )
        values.append(f"selective={int(self.allow_escalation)}")
        return "|".join(values)


class _CircuitState:
    failures = {ProviderName.OPENAI: 0, ProviderName.DEEPSEEK: 0}
    open_until = {ProviderName.OPENAI: 0.0, ProviderName.DEEPSEEK: 0.0}

    @classmethod
    def available(cls, provider: ProviderName) -> bool:
        return time.monotonic() >= cls.open_until[provider]

    @classmethod
    def success(cls, provider: ProviderName) -> None:
        cls.failures[provider] = 0
        cls.open_until[provider] = 0.0

    @classmethod
    def failure(cls, provider: ProviderName) -> None:
        cls.failures[provider] += 1
        if cls.failures[provider] >= 3:
            cls.open_until[provider] = time.monotonic() + 45.0


class CostAwareAIProvider:
    """Drop-in provider with stage-aware routing, failover and escalation."""

    def __init__(self, config: HybridAIConfig):
        self.config = config
        self.openai = OpenAIProvider(config) if config.openai_configured else None
        self.deepseek = DeepSeekProvider(config) if config.deepseek_configured else None

    @property
    def profile(self) -> RoutingProfile:
        try:
            return RoutingProfile(self.config.routing_profile)
        except ValueError:
            return RoutingProfile.BALANCED

    def _deepseek_v4_pro_only_mode(self) -> bool:
        """Return True when expert review should stay on DeepSeek V4 Pro.

        This mode is intended for users who prefer one strong DeepSeek Pro
        expert route rather than mixing Flash, OpenAI mini and OpenAI expert
        calls. It is especially useful for Research Master's/MPhil standard
        review where a cheap first pass produced too few or too shallow
        comments. The route is still schema-bound and keeps the existing
        deterministic quality gates.
        """
        raw = os.getenv("VPROF_EXPERT_PROVIDER_MODE", "").strip().lower()
        flag = os.getenv("VPROF_FORCE_DEEPSEEK_V4_PRO", "false").strip().lower()
        return raw in {
            "deepseek_v4_pro_only",
            "deepseek_pro_only",
            "v4_pro_only",
            "deepseek-only",
            "deepseek_only",
        } or flag in {"1", "true", "yes", "on"}

    def _stage_allows_deepseek_pro_only(self, stage: ReviewStage) -> bool:
        # Keep external examination separately governed unless explicitly
        # requested in a future release. The user's current concern is
        # supervisory review quality for MPhil Standard review.
        return stage is not ReviewStage.EXTERNAL_EXAMINATION

    def _enabled(self, target: Optional[RouteTarget]) -> bool:
        if target is None:
            return False
        if not _CircuitState.available(target.provider):
            return False
        if target.provider is ProviderName.OPENAI:
            return bool(self.config.enable_openai_routing and self.openai)
        return bool(self.config.enable_deepseek_routing and self.deepseek)

    def _normalise_targets(
        self,
        primary: RouteTarget,
        fallback: Optional[RouteTarget],
        escalation: Optional[RouteTarget],
    ) -> tuple[RouteTarget, Optional[RouteTarget], Optional[RouteTarget]]:
        primary_enabled = primary if self._enabled(primary) else None
        fallback_enabled = fallback if self._enabled(fallback) else None
        escalation_enabled = escalation if self._enabled(escalation) else None
        selected_primary = primary_enabled or fallback_enabled or escalation_enabled
        if selected_primary is None:
            raise AIProviderError(
                "No enabled AI provider is configured. Add OPENAI_API_KEY or "
                "DEEPSEEK_API_KEY and enable the corresponding router provider."
            )
        selected_fallback = (
            fallback_enabled
            if fallback_enabled is not None and fallback_enabled != selected_primary
            else None
        )
        if selected_fallback is None:
            for candidate in (primary_enabled, escalation_enabled):
                if candidate is not None and candidate != selected_primary:
                    selected_fallback = candidate
                    break
        selected_escalation = (
            escalation_enabled
            if escalation_enabled is not None and escalation_enabled != selected_primary
            else None
        )
        return selected_primary, selected_fallback, selected_escalation

    def plan(
        self,
        *,
        stage: str | ReviewStage,
        review_depth: str = "standard",
        requested_model: str = "",
        requested_effort: str = "",
    ) -> RoutePlan:
        stage_value = stage if isinstance(stage, ReviewStage) else ReviewStage(str(stage))
        profile = self.profile
        config = self.config

        ds_fast = RouteTarget(
            ProviderName.DEEPSEEK,
            config.deepseek_fast_model,
            config.deepseek_reasoning_effort or "high",
            False,
        )
        ds_quality = RouteTarget(
            ProviderName.DEEPSEEK,
            config.deepseek_quality_model,
            config.deepseek_advanced_primary_reasoning_effort or "high",
            True,
        )
        oa_chapter = RouteTarget(
            ProviderName.OPENAI,
            config.openai_chapter_model,
            config.openai_chapter_reasoning_effort,
        )
        oa_fast = RouteTarget(
            ProviderName.OPENAI,
            config.openai_fast_model,
            "low",
        )
        oa_expert = RouteTarget(
            ProviderName.OPENAI,
            config.openai_expert_model,
            config.openai_expert_reasoning_effort,
        )
        oa_requested = RouteTarget(
            ProviderName.OPENAI,
            requested_model or config.openai_chapter_model,
            requested_effort or config.openai_chapter_reasoning_effort,
        )

        if self._deepseek_v4_pro_only_mode() and self._stage_allows_deepseek_pro_only(stage_value):
            # One expert-class DeepSeek V4 Pro route for every supervisory
            # review stage. Do not fall back to Flash or OpenAI in this mode;
            # a provider failure should be visible so the user can retry rather
            # than receiving a lower-quality mixed-route output.
            primary, fallback, escalation = self._normalise_targets(
                ds_quality,
                None,
                None,
            )
            return RoutePlan(stage_value, profile, primary, fallback, escalation, False)

        cheap = {
            ReviewStage.DOCUMENT_TRIAGE,
            ReviewStage.STRUCTURE_MAP,
            ReviewStage.LANGUAGE_SCAN,
            ReviewStage.COMMENT_DEDUPLICATION,
            ReviewStage.JSON_REPAIR,
        }
        if stage_value in cheap:
            if profile is RoutingProfile.QUALITY:
                primary, fallback, escalation = self._normalise_targets(
                    oa_chapter, ds_fast, None
                )
            else:
                primary, fallback, escalation = self._normalise_targets(
                    ds_fast, oa_chapter, None
                )
            return RoutePlan(stage_value, profile, primary, fallback, escalation, False)

        if stage_value in {ReviewStage.LIGHT_REVIEW, ReviewStage.STANDARD_REVIEW}:
            if profile is RoutingProfile.QUALITY:
                primary, fallback, escalation = self._normalise_targets(
                    oa_chapter, ds_fast, oa_expert
                )
            elif profile is RoutingProfile.ECONOMY:
                primary, fallback, escalation = self._normalise_targets(
                    ds_fast, ds_quality, None
                )
            else:
                # Keep the ordinary review within DeepSeek when Flash has a
                # transient/schema failure. If the provider is unavailable,
                # use GPT-5.4 nano rather than silently moving the whole
                # chapter to GPT-5.4 mini.
                primary, fallback, escalation = self._normalise_targets(
                    ds_fast, oa_fast, oa_chapter
                )
            return RoutePlan(
                stage_value,
                profile,
                primary,
                fallback,
                escalation,
                config.selective_escalation_enabled,
            )

        if stage_value is ReviewStage.RESEARCH_INTENSIVE_REVIEW:
            # Research Master's/MPhil and doctoral work must not share the
            # ordinary Flash-first route used for applied programmes. Balanced
            # mode uses DeepSeek Pro for the full scholarly first pass and
            # reserves OpenAI expert judgement for the bounded audit.
            if profile is RoutingProfile.QUALITY:
                primary, fallback, escalation = self._normalise_targets(
                    oa_requested if requested_model else oa_expert,
                    ds_quality,
                    None,
                )
            elif profile is RoutingProfile.ECONOMY:
                primary, fallback, escalation = self._normalise_targets(
                    ds_quality,
                    oa_chapter,
                    None,
                )
            else:
                primary, fallback, escalation = self._normalise_targets(
                    ds_quality,
                    oa_chapter,
                    None,
                )
            return RoutePlan(
                stage_value, profile, primary, fallback, escalation, False
            )

        if stage_value is ReviewStage.ADVANCED_REVIEW:
            if profile is RoutingProfile.ECONOMY:
                primary, fallback, escalation = self._normalise_targets(
                    ds_quality, oa_chapter, oa_expert
                )
            elif profile is RoutingProfile.QUALITY:
                primary, fallback, escalation = self._normalise_targets(
                    oa_requested if requested_model else oa_expert,
                    ds_quality,
                    oa_expert,
                )
            else:
                primary, fallback, escalation = self._normalise_targets(
                    oa_chapter, ds_quality, oa_expert
                )
            return RoutePlan(
                stage_value,
                profile,
                primary,
                fallback,
                escalation,
                config.selective_escalation_enabled,
            )

        if stage_value is ReviewStage.RESEARCH_INTENSIVE_AUDIT:
            # One bounded expert audit gives Research Master's/MPhil work the
            # conceptual and methodological depth that GPT-5.4 mini alone did
            # not consistently provide. Economy mode may remain DeepSeek-led.
            if profile is RoutingProfile.ECONOMY:
                primary, fallback, escalation = self._normalise_targets(
                    ds_quality,
                    oa_chapter,
                    None,
                )
            else:
                primary, fallback, escalation = self._normalise_targets(
                    oa_requested if requested_model else oa_expert,
                    ds_quality,
                    None,
                )
            return RoutePlan(
                stage_value, profile, primary, fallback, escalation, False
            )

        if stage_value is ReviewStage.FINAL_AUDIT:
            if profile is RoutingProfile.QUALITY:
                primary_choice = oa_requested if requested_model else oa_expert
            else:
                primary_choice = oa_chapter
            primary, fallback, escalation = self._normalise_targets(
                primary_choice,
                ds_quality,
                oa_requested if requested_model else oa_expert,
            )
            return RoutePlan(
                stage_value,
                profile,
                primary,
                fallback,
                escalation,
                config.selective_escalation_enabled,
            )

        # External assessment remains OpenAI-led because it produces the final
        # degree recommendation. DeepSeek Pro is a provider-failure fallback.
        primary, fallback, escalation = self._normalise_targets(
            oa_requested,
            ds_quality,
            None,
        )
        return RoutePlan(stage_value, profile, primary, fallback, escalation, False)

    def route_signature(
        self,
        *,
        stage: str | ReviewStage,
        review_depth: str = "standard",
        requested_model: str = "",
        requested_effort: str = "",
    ) -> str:
        return self.plan(
            stage=stage,
            review_depth=review_depth,
            requested_model=requested_model,
            requested_effort=requested_effort,
        ).signature()

    async def _call(
        self,
        target: RouteTarget,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_model: Type[BaseModel],
        purpose: str,
        max_output_tokens: Optional[int],
        request_timeout_seconds: Optional[int],
        request_max_retries: Optional[int],
    ) -> ProviderResult:
        provider = self.openai if target.provider is ProviderName.OPENAI else self.deepseek
        if provider is None:
            raise AIProviderError(f"{target.provider.value} is not configured.")
        try:
            result = await provider.complete_json(
                model=target.model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema_model=schema_model,
                purpose=purpose,
                reasoning_effort=target.reasoning_effort,
                max_output_tokens=max_output_tokens,
                request_timeout_seconds=request_timeout_seconds,
                request_max_retries=request_max_retries,
                thinking_enabled=target.thinking_enabled,
            )
        except Exception:
            _CircuitState.failure(target.provider)
            raise
        _CircuitState.success(target.provider)
        return result

    @staticmethod
    def _iter_signal_rows(value: Any):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from CostAwareAIProvider._iter_signal_rows(child)
        elif isinstance(value, list):
            for child in value:
                yield from CostAwareAIProvider._iter_signal_rows(child)

    def _needs_escalation(self, data: dict[str, Any]) -> bool:
        threshold = self.config.escalation_confidence_threshold
        for row in self._iter_signal_rows(data):
            if row.get("needs_expert_review") or row.get("requires_expert_review"):
                return True
            if row.get("needs_openai_verification"):
                return True
            confidence = row.get("confidence")
            if confidence is not None:
                try:
                    confidence_value = float(confidence)
                    if confidence_value > 1 and confidence_value <= 100:
                        confidence_value /= 100
                    if confidence_value < threshold:
                        return True
                except (TypeError, ValueError):
                    pass
            severity = str(
                row.get("severity") or row.get("highest_severity") or ""
            ).strip().lower()
            if severity in {"critical", "fundamental", "fatal"}:
                return True
        return False

    def _price_usage(self, usage: AIUsageRecord) -> AIUsageRecord:
        if usage.estimated_cost_usd > 0:
            return usage
        uncached = max(0, usage.input_tokens - usage.cached_input_tokens)
        p_in, p_cache, p_out = self.config.prices_for_model(
            usage.provider, usage.model
        )
        cost = (
            uncached / 1_000_000 * p_in
            + usage.cached_input_tokens / 1_000_000 * p_cache
            + usage.output_tokens / 1_000_000 * p_out
        )
        return usage.model_copy(update={"estimated_cost_usd": round(cost, 6)})

    def _combine_usage(
        self,
        first: AIUsageRecord,
        final: AIUsageRecord,
        *,
        purpose: str,
    ) -> AIUsageRecord:
        first = self._price_usage(first)
        final = self._price_usage(final)
        return AIUsageRecord(
            provider="routed",
            model=f"{first.model}->{final.model}",
            purpose=purpose,
            input_tokens=first.input_tokens + final.input_tokens,
            cached_input_tokens=(
                first.cached_input_tokens + final.cached_input_tokens
            ),
            output_tokens=first.output_tokens + final.output_tokens,
            estimated_cost_usd=round(
                first.estimated_cost_usd + final.estimated_cost_usd, 6
            ),
            request_id="|".join(
                value for value in (first.request_id, final.request_id) if value
            ),
        )

    @staticmethod
    def _escalation_prompt(user_prompt: str, first_pass: dict[str, Any]) -> str:
        compact = json.dumps(
            first_pass, ensure_ascii=False, separators=(",", ":")
        )
        if len(compact) > 18000:
            compact = compact[:18000]
        return (
            "Review the original evidence and the first-pass assessment below. "
            "Correct only material errors, resolve uncertainty and return one "
            "definitive JSON object matching the required schema. Preserve all "
            "evidence boundaries. Do not invent facts, quotations, citations or "
            "paragraph locations.\n\n"
            f"FIRST_PASS_ASSESSMENT:\n{compact}\n\n"
            f"ORIGINAL_REQUEST:\n{user_prompt}"
        )

    async def complete_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema_model: Type[BaseModel],
        purpose: str,
        reasoning_effort: Optional[str] = None,
        max_output_tokens: Optional[int] = None,
        request_timeout_seconds: Optional[int] = None,
        request_max_retries: Optional[int] = None,
        stage: str | ReviewStage = ReviewStage.STANDARD_REVIEW,
        review_depth: str = "standard",
        allow_escalation: Optional[bool] = None,
    ) -> ProviderResult:
        plan = self.plan(
            stage=stage,
            review_depth=review_depth,
            requested_model=model,
            requested_effort=reasoning_effort or "",
        )

        try:
            primary = await self._call(
                plan.primary,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema_model=schema_model,
                purpose=purpose,
                max_output_tokens=max_output_tokens,
                request_timeout_seconds=request_timeout_seconds,
                request_max_retries=request_max_retries,
            )
        except Exception as primary_error:
            if plan.fallback is None:
                raise
            logger.warning(
                "Primary routed model failed for %s, using fallback: %s",
                plan.stage.value,
                primary_error,
            )
            return await self._call(
                plan.fallback,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema_model=schema_model,
                purpose=f"{purpose}_provider_fallback",
                max_output_tokens=max_output_tokens,
                request_timeout_seconds=request_timeout_seconds,
                request_max_retries=request_max_retries,
            )

        should_escalate = (
            plan.allow_escalation
            if allow_escalation is None
            else bool(allow_escalation and plan.allow_escalation)
        )
        if (
            not should_escalate
            or plan.escalation is None
            or plan.escalation == plan.primary
            or not self._needs_escalation(primary.data)
        ):
            return primary

        first_costed = self._price_usage(primary.usage)
        if first_costed.estimated_cost_usd >= self.config.default_call_budget_usd:
            return ProviderResult(data=primary.data, usage=first_costed)

        try:
            expert = await self._call(
                plan.escalation,
                system_prompt=system_prompt,
                user_prompt=self._escalation_prompt(user_prompt, primary.data),
                schema_model=schema_model,
                purpose=f"{purpose}_selective_expert_escalation",
                max_output_tokens=max_output_tokens,
                request_timeout_seconds=request_timeout_seconds,
                request_max_retries=request_max_retries,
            )
        except Exception as escalation_error:
            logger.warning(
                "Selective expert escalation failed, retaining first pass: %s",
                escalation_error,
            )
            return ProviderResult(data=primary.data, usage=first_costed)

        combined = self._combine_usage(
            primary.usage,
            expert.usage,
            purpose=purpose,
        )
        if combined.estimated_cost_usd > self.config.default_call_budget_usd:
            logger.info(
                "Routed call exceeded the advisory budget after completion: %.6f",
                combined.estimated_cost_usd,
            )
        return ProviderResult(data=expert.data, usage=combined)


def stage_for_depth(depth: str) -> ReviewStage:
    value = str(depth or "standard").strip().lower()
    if value == "light":
        return ReviewStage.LIGHT_REVIEW
    if value == "advanced":
        return ReviewStage.ADVANCED_REVIEW
    return ReviewStage.STANDARD_REVIEW


def estimate_tokens(text: str) -> int:
    value = str(text or "")
    if not value:
        return 0
    words = len(re.findall(r"\S+", value))
    return max(1, int(max(words * 1.35, len(value) / 3.7)))
