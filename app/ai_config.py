from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional


class AIConfigurationError(ValueError):
    """Raised when the expert-review service is not configured."""


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float, minimum: float = 0.0, maximum: Optional[float] = None) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    value = max(minimum, value)
    return min(value, maximum) if maximum is not None else value


@dataclass(frozen=True)
class HybridAIConfig:
    """OpenAI-only review configuration.

    The historic class name is retained so older modules and deployments do not break.
    DeepSeek is deliberately disabled in this release.
    """

    enabled: bool
    openai_api_key: str
    openai_base_url: str
    openai_mini_model: str
    openai_review_model: str
    openai_advanced_model: str
    openai_mini_reasoning_effort: str
    openai_review_reasoning_effort: str
    openai_advanced_reasoning_effort: str
    confidence_threshold: float
    max_context_chars_per_rule: int
    max_map_input_chars: int
    max_output_tokens: int
    mini_max_output_tokens: int
    review_max_output_tokens: int
    advanced_max_output_tokens: int
    timeout_seconds: int
    max_retries: int
    max_parallel_calls: int
    section_batch_size: int
    verification_batch_size: int
    strict_failure: bool
    structured_output_retries: int

    openai_mini_input_price: float
    openai_mini_cached_input_price: float
    openai_mini_output_price: float
    openai_review_input_price: float
    openai_review_cached_input_price: float
    openai_review_output_price: float
    openai_advanced_input_price: float
    openai_advanced_cached_input_price: float
    openai_advanced_output_price: float

    # Backward-compatible fields used by dormant legacy modules.
    deepseek_api_key: str = ""
    deepseek_base_url: str = ""
    deepseek_extract_model: str = ""
    deepseek_review_model: str = ""
    deepseek_reasoning_effort: str = ""
    use_flash_document_map: bool = False
    provider_failover: bool = False
    verify_critical: bool = True
    verify_manual: bool = True
    verify_disagreement: bool = True
    verify_meets_sample_rate: float = 0.0
    max_rules_per_batch: int = 5
    deepseek_flash_input_price: float = 0.0
    deepseek_flash_cached_input_price: float = 0.0
    deepseek_flash_output_price: float = 0.0
    deepseek_pro_input_price: float = 0.0
    deepseek_pro_cached_input_price: float = 0.0
    deepseek_pro_output_price: float = 0.0

    @classmethod
    def from_env(cls) -> "HybridAIConfig":
        review_model = os.getenv("OPENAI_REVIEW_MODEL", os.getenv("OPENAI_VERIFY_MODEL", "gpt-5.4")).strip()
        advanced_model = os.getenv("OPENAI_ADVANCED_MODEL", os.getenv("OPENAI_PREMIUM_MODEL", "gpt-5.5")).strip()
        return cls(
            enabled=_env_bool("AI_REVIEW_ENABLED", True),
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            openai_mini_model=os.getenv("OPENAI_MINI_MODEL", "gpt-5.4-mini").strip(),
            openai_review_model=review_model,
            openai_advanced_model=advanced_model,
            openai_mini_reasoning_effort=os.getenv("OPENAI_MINI_REASONING_EFFORT", "low").strip().lower(),
            openai_review_reasoning_effort=os.getenv("OPENAI_REVIEW_REASONING_EFFORT", "medium").strip().lower(),
            openai_advanced_reasoning_effort=os.getenv("OPENAI_ADVANCED_REASONING_EFFORT", "high").strip().lower(),
            confidence_threshold=_env_float("AI_CONFIDENCE_THRESHOLD", 0.78, 0.0, 1.0),
            max_context_chars_per_rule=_env_int("AI_MAX_CONTEXT_CHARS_PER_RULE", 9000),
            max_map_input_chars=_env_int("AI_MAX_MAP_INPUT_CHARS", 30000),
            max_output_tokens=_env_int("AI_MAX_OUTPUT_TOKENS", 7000),
            mini_max_output_tokens=_env_int("AI_MINI_MAX_OUTPUT_TOKENS", 6500),
            review_max_output_tokens=_env_int("AI_REVIEW_MAX_OUTPUT_TOKENS", 8000),
            advanced_max_output_tokens=_env_int("AI_ADVANCED_MAX_OUTPUT_TOKENS", 9000),
            timeout_seconds=_env_int("AI_TIMEOUT_SECONDS", 100),
            max_retries=_env_int("AI_MAX_RETRIES", 1, 0),
            max_parallel_calls=_env_int("AI_MAX_PARALLEL_CALLS", 3),
            section_batch_size=_env_int("AI_SECTION_BATCH_SIZE", 3),
            verification_batch_size=_env_int("AI_VERIFICATION_BATCH_SIZE", 3),
            strict_failure=_env_bool("AI_STRICT_FAILURE", False),
            structured_output_retries=_env_int("AI_STRUCTURED_OUTPUT_RETRIES", 1, 0),
            openai_mini_input_price=_env_float("PRICE_OPENAI_MINI_INPUT", 0.75),
            openai_mini_cached_input_price=_env_float("PRICE_OPENAI_MINI_CACHED_INPUT", 0.075),
            openai_mini_output_price=_env_float("PRICE_OPENAI_MINI_OUTPUT", 4.50),
            openai_review_input_price=_env_float("PRICE_OPENAI_REVIEW_INPUT", 2.50),
            openai_review_cached_input_price=_env_float("PRICE_OPENAI_REVIEW_CACHED_INPUT", 0.25),
            openai_review_output_price=_env_float("PRICE_OPENAI_REVIEW_OUTPUT", 15.00),
            openai_advanced_input_price=_env_float("PRICE_OPENAI_ADVANCED_INPUT", 5.00),
            openai_advanced_cached_input_price=_env_float("PRICE_OPENAI_ADVANCED_CACHED_INPUT", 0.50),
            openai_advanced_output_price=_env_float("PRICE_OPENAI_ADVANCED_OUTPUT", 30.00),
        )

    @property
    def openai_configured(self) -> bool:
        return bool(self.enabled and self.openai_api_key)

    @property
    def deepseek_configured(self) -> bool:
        return False

    @property
    def openai_verify_model(self) -> str:
        return self.openai_review_model

    @property
    def openai_premium_model(self) -> str:
        return self.openai_advanced_model

    @property
    def openai_reasoning_effort(self) -> str:
        return self.openai_review_reasoning_effort

    def resolve_mode(self, requested_mode: str, academic_level: str = "") -> str:
        requested = (requested_mode or "standard").strip().lower()
        aliases = {
            "auto": "standard",
            "openai_only": "standard",
            "hybrid": "standard",
            "premium": "advanced",
        }
        requested = aliases.get(requested, requested)
        if requested not in {"standard", "advanced"}:
            raise AIConfigurationError("Choose Standard Review or Advanced Review.")
        if not self.openai_configured:
            raise AIConfigurationError("The expert review service is not configured. Add OPENAI_API_KEY on the server.")
        return requested

    def public_status(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "configured": self.openai_configured,
            "review_depths": ["standard", "advanced"],
        }
