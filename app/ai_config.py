from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional


class AIConfigurationError(ValueError):
    """Raised when a requested AI routing mode is not configured."""


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
    enabled: bool
    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_extract_model: str
    deepseek_review_model: str
    deepseek_reasoning_effort: str
    openai_api_key: str
    openai_base_url: str
    openai_verify_model: str
    openai_premium_model: str
    openai_reasoning_effort: str
    confidence_threshold: float
    max_rules_per_batch: int
    max_context_chars_per_rule: int
    max_map_input_chars: int
    max_output_tokens: int
    timeout_seconds: int
    max_retries: int
    max_parallel_calls: int
    use_flash_document_map: bool
    strict_failure: bool
    verify_critical: bool
    verify_manual: bool
    verify_disagreement: bool
    verify_meets_sample_rate: float

    # Prices are estimates only and can be overridden without changing code.
    deepseek_flash_input_price: float
    deepseek_flash_cached_input_price: float
    deepseek_flash_output_price: float
    deepseek_pro_input_price: float
    deepseek_pro_cached_input_price: float
    deepseek_pro_output_price: float
    openai_verify_input_price: float
    openai_verify_cached_input_price: float
    openai_verify_output_price: float
    openai_premium_input_price: float
    openai_premium_cached_input_price: float
    openai_premium_output_price: float

    @classmethod
    def from_env(cls) -> "HybridAIConfig":
        return cls(
            enabled=_env_bool("AI_REVIEW_ENABLED", True),
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", "").strip(),
            deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
            deepseek_extract_model=os.getenv("DEEPSEEK_EXTRACT_MODEL", "deepseek-v4-flash").strip(),
            deepseek_review_model=os.getenv("DEEPSEEK_REVIEW_MODEL", "deepseek-v4-pro").strip(),
            deepseek_reasoning_effort=os.getenv("DEEPSEEK_REASONING_EFFORT", "high").strip().lower(),
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            openai_verify_model=os.getenv("OPENAI_VERIFY_MODEL", "gpt-5.4").strip(),
            openai_premium_model=os.getenv("OPENAI_PREMIUM_MODEL", "gpt-5.5").strip(),
            openai_reasoning_effort=os.getenv("OPENAI_REASONING_EFFORT", "medium").strip().lower(),
            confidence_threshold=_env_float("AI_CONFIDENCE_THRESHOLD", 0.82, 0.0, 1.0),
            max_rules_per_batch=_env_int("AI_MAX_RULES_PER_BATCH", 5),
            max_context_chars_per_rule=_env_int("AI_MAX_CONTEXT_CHARS_PER_RULE", 12000),
            max_map_input_chars=_env_int("AI_MAX_MAP_INPUT_CHARS", 36000),
            max_output_tokens=_env_int("AI_MAX_OUTPUT_TOKENS", 7000),
            timeout_seconds=_env_int("AI_TIMEOUT_SECONDS", 150),
            max_retries=_env_int("AI_MAX_RETRIES", 2, 0),
            max_parallel_calls=_env_int("AI_MAX_PARALLEL_CALLS", 2),
            use_flash_document_map=_env_bool("AI_USE_FLASH_DOCUMENT_MAP", True),
            strict_failure=_env_bool("AI_STRICT_FAILURE", False),
            verify_critical=_env_bool("AI_VERIFY_CRITICAL", True),
            verify_manual=_env_bool("AI_VERIFY_MANUAL", True),
            verify_disagreement=_env_bool("AI_VERIFY_DISAGREEMENT", True),
            verify_meets_sample_rate=_env_float("AI_VERIFY_MEETS_SAMPLE_RATE", 0.10, 0.0, 1.0),
            deepseek_flash_input_price=_env_float("PRICE_DEEPSEEK_FLASH_INPUT", 0.14),
            deepseek_flash_cached_input_price=_env_float("PRICE_DEEPSEEK_FLASH_CACHED_INPUT", 0.0028),
            deepseek_flash_output_price=_env_float("PRICE_DEEPSEEK_FLASH_OUTPUT", 0.28),
            deepseek_pro_input_price=_env_float("PRICE_DEEPSEEK_PRO_INPUT", 0.435),
            deepseek_pro_cached_input_price=_env_float("PRICE_DEEPSEEK_PRO_CACHED_INPUT", 0.003625),
            deepseek_pro_output_price=_env_float("PRICE_DEEPSEEK_PRO_OUTPUT", 0.87),
            openai_verify_input_price=_env_float("PRICE_OPENAI_VERIFY_INPUT", 2.50),
            openai_verify_cached_input_price=_env_float("PRICE_OPENAI_VERIFY_CACHED_INPUT", 0.25),
            openai_verify_output_price=_env_float("PRICE_OPENAI_VERIFY_OUTPUT", 15.00),
            openai_premium_input_price=_env_float("PRICE_OPENAI_PREMIUM_INPUT", 5.00),
            openai_premium_cached_input_price=_env_float("PRICE_OPENAI_PREMIUM_CACHED_INPUT", 0.50),
            openai_premium_output_price=_env_float("PRICE_OPENAI_PREMIUM_OUTPUT", 30.00),
        )

    @property
    def deepseek_configured(self) -> bool:
        return bool(self.enabled and self.deepseek_api_key)

    @property
    def openai_configured(self) -> bool:
        return bool(self.enabled and self.openai_api_key)

    def resolve_mode(self, requested_mode: str) -> str:
        requested = (requested_mode or "auto").strip().lower()
        allowed = {"auto", "local", "deepseek_only", "openai_only", "hybrid", "premium"}
        if requested not in allowed:
            raise AIConfigurationError(f"Unsupported AI review mode: {requested_mode}")

        if requested == "local" or not self.enabled:
            return "local"
        if requested == "auto":
            if self.deepseek_configured and self.openai_configured:
                return "hybrid"
            if self.deepseek_configured:
                return "deepseek_only"
            if self.openai_configured:
                return "openai_only"
            return "local"
        if requested == "deepseek_only" and not self.deepseek_configured:
            raise AIConfigurationError("DeepSeek review was selected, but DEEPSEEK_API_KEY is not configured.")
        if requested == "openai_only" and not self.openai_configured:
            raise AIConfigurationError("OpenAI review was selected, but OPENAI_API_KEY is not configured.")
        if requested in {"hybrid", "premium"}:
            missing = []
            if not self.deepseek_configured:
                missing.append("DEEPSEEK_API_KEY")
            if not self.openai_configured:
                missing.append("OPENAI_API_KEY")
            if missing:
                raise AIConfigurationError(
                    f"{requested.title()} review requires both providers. Configure: {', '.join(missing)}."
                )
        return requested

    def public_status(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "deepseek_configured": self.deepseek_configured,
            "openai_configured": self.openai_configured,
            "automatic_mode": self.resolve_mode("auto"),
            "models": {
                "deepseek_extract": self.deepseek_extract_model,
                "deepseek_review": self.deepseek_review_model,
                "openai_verify": self.openai_verify_model,
                "openai_premium": self.openai_premium_model,
            },
            "routing": {
                "confidence_threshold": self.confidence_threshold,
                "max_rules_per_batch": self.max_rules_per_batch,
                "verify_critical": self.verify_critical,
                "verify_manual": self.verify_manual,
            },
        }
