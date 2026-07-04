from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional


class AIConfigurationError(ValueError):
    """Raised when the required expert-review provider is not configured."""


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
    """Academic-review routing configuration.

    Light, Standard and Advanced Review use DeepSeek. Advanced Review uses the
    advanced model with maximum reasoning and an independent second-pass audit.
    OpenAI fields remain optional for backwards compatibility only.
    """

    enabled: bool
    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_review_model: str
    deepseek_advanced_model: str
    deepseek_reasoning_effort: str
    deepseek_advanced_reasoning_effort: str
    deepseek_advanced_primary_reasoning_effort: str
    deepseek_thinking_enabled: bool

    openai_api_key: str
    openai_base_url: str
    openai_review_model: str
    openai_review_reasoning_effort: str

    confidence_threshold: float
    max_context_chars_per_rule: int
    max_map_input_chars: int
    max_output_tokens: int
    light_max_output_tokens: int
    standard_max_output_tokens: int
    advanced_max_output_tokens: int
    timeout_seconds: int
    max_retries: int
    max_parallel_calls: int
    section_batch_size: int
    light_section_batch_size: int
    advanced_section_batch_size: int
    verification_batch_size: int
    recovery_batch_size: int
    max_recovery_batches: int
    max_short_section_fallbacks: int
    advanced_audit_max_findings: int
    advanced_audit_max_output_tokens: int
    strict_failure: bool
    structured_output_retries: int
    advanced_quality_control: bool

    deepseek_pro_input_price: float
    deepseek_pro_cached_input_price: float
    deepseek_pro_output_price: float
    openai_review_input_price: float
    openai_review_cached_input_price: float
    openai_review_output_price: float

    # Compatibility fields for dormant legacy modules.
    deepseek_extract_model: str = "deepseek-v4-pro"
    use_flash_document_map: bool = False
    provider_failover: bool = False
    verify_critical: bool = True
    verify_manual: bool = True
    verify_disagreement: bool = True
    verify_meets_sample_rate: float = 0.0
    max_rules_per_batch: int = 5
    deepseek_flash_input_price: float = 0.14
    deepseek_flash_cached_input_price: float = 0.0028
    deepseek_flash_output_price: float = 0.28
    openai_mini_model: str = "gpt-5.4"
    openai_advanced_model: str = "gpt-5.4"
    openai_mini_reasoning_effort: str = "high"
    openai_advanced_reasoning_effort: str = "high"
    mini_max_output_tokens: int = 7500
    review_max_output_tokens: int = 9000
    openai_mini_input_price: float = 2.50
    openai_mini_cached_input_price: float = 0.25
    openai_mini_output_price: float = 15.00
    openai_advanced_input_price: float = 2.50
    openai_advanced_cached_input_price: float = 0.25
    openai_advanced_output_price: float = 15.00
    external_assessment_foundation_max_output_tokens: int = 3400
    external_assessment_evidence_max_output_tokens: int = 3400
    external_assessment_integrity_max_output_tokens: int = 2800
    external_assessment_corrections_max_output_tokens: int = 3400
    external_assessment_decision_max_output_tokens: int = 2200
    external_assessment_stage_timeout_seconds: int = 600
    external_assessment_request_timeout_seconds: int = 240
    external_assessment_request_max_retries: int = 0

    @classmethod
    def from_env(cls) -> "HybridAIConfig":
        review_model = os.getenv("DEEPSEEK_REVIEW_MODEL", "deepseek-v4-pro").strip()
        advanced_model = os.getenv("DEEPSEEK_ADVANCED_MODEL", review_model).strip()
        openai_model = os.getenv("OPENAI_REVIEW_MODEL", "gpt-5.4").strip()
        standard_tokens = _env_int("AI_STANDARD_MAX_OUTPUT_TOKENS", 5200)
        advanced_tokens = _env_int("AI_ADVANCED_MAX_OUTPUT_TOKENS", 6800)
        openai_effort = os.getenv("OPENAI_REVIEW_REASONING_EFFORT", "high").strip().lower()

        return cls(
            enabled=_env_bool("AI_REVIEW_ENABLED", True),
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", "").strip(),
            deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
            deepseek_review_model=review_model,
            deepseek_advanced_model=advanced_model,
            deepseek_reasoning_effort=os.getenv("DEEPSEEK_REASONING_EFFORT", "high").strip().lower(),
            deepseek_advanced_reasoning_effort=os.getenv("DEEPSEEK_ADVANCED_REASONING_EFFORT", "max").strip().lower(),
            deepseek_advanced_primary_reasoning_effort=os.getenv(
                "DEEPSEEK_ADVANCED_PRIMARY_REASONING_EFFORT", "high"
            ).strip().lower(),
            deepseek_thinking_enabled=_env_bool("DEEPSEEK_THINKING_ENABLED", True),

            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            openai_review_model=openai_model,
            openai_review_reasoning_effort=openai_effort,

            confidence_threshold=_env_float("AI_CONFIDENCE_THRESHOLD", 0.78, 0.0, 1.0),
            max_context_chars_per_rule=_env_int("AI_MAX_CONTEXT_CHARS_PER_RULE", 9000),
            max_map_input_chars=_env_int("AI_MAX_MAP_INPUT_CHARS", 30000),
            max_output_tokens=_env_int("AI_MAX_OUTPUT_TOKENS", 8000),
            light_max_output_tokens=_env_int("AI_LIGHT_MAX_OUTPUT_TOKENS", 3800),
            standard_max_output_tokens=standard_tokens,
            advanced_max_output_tokens=advanced_tokens,
            timeout_seconds=_env_int("AI_TIMEOUT_SECONDS", 180),
            max_retries=_env_int("AI_MAX_RETRIES", 1, 0),
            max_parallel_calls=_env_int("AI_MAX_PARALLEL_CALLS", 4),
            section_batch_size=_env_int("AI_SECTION_BATCH_SIZE", 5),
            light_section_batch_size=_env_int("AI_LIGHT_SECTION_BATCH_SIZE", 6),
            advanced_section_batch_size=_env_int("AI_ADVANCED_SECTION_BATCH_SIZE", 4),
            verification_batch_size=_env_int("AI_VERIFICATION_BATCH_SIZE", 24),
            recovery_batch_size=_env_int("AI_RECOVERY_BATCH_SIZE", 6),
            max_recovery_batches=_env_int("AI_MAX_RECOVERY_BATCHES", 2),
            max_short_section_fallbacks=_env_int("AI_MAX_SHORT_SECTION_FALLBACKS", 2, 0),
            advanced_audit_max_findings=_env_int("AI_ADVANCED_AUDIT_MAX_FINDINGS", 24),
            advanced_audit_max_output_tokens=_env_int("AI_ADVANCED_AUDIT_MAX_OUTPUT_TOKENS", 4800),
            strict_failure=_env_bool("AI_STRICT_FAILURE", False),
            structured_output_retries=_env_int("AI_STRUCTURED_OUTPUT_RETRIES", 0, 0),
            advanced_quality_control=_env_bool("AI_ADVANCED_SECOND_PASS", True),

            deepseek_pro_input_price=_env_float("PRICE_DEEPSEEK_PRO_INPUT", 0.435),
            deepseek_pro_cached_input_price=_env_float("PRICE_DEEPSEEK_PRO_CACHED_INPUT", 0.003625),
            deepseek_pro_output_price=_env_float("PRICE_DEEPSEEK_PRO_OUTPUT", 0.87),
            openai_review_input_price=_env_float("PRICE_OPENAI_REVIEW_INPUT", 2.50),
            openai_review_cached_input_price=_env_float("PRICE_OPENAI_REVIEW_CACHED_INPUT", 0.25),
            openai_review_output_price=_env_float("PRICE_OPENAI_REVIEW_OUTPUT", 15.00),

            deepseek_extract_model=review_model,
            openai_mini_model=openai_model,
            openai_advanced_model=openai_model,
            openai_mini_reasoning_effort=openai_effort,
            openai_advanced_reasoning_effort=openai_effort,
            mini_max_output_tokens=standard_tokens,
            review_max_output_tokens=advanced_tokens,
            external_assessment_foundation_max_output_tokens=_env_int(
                "AI_EXTERNAL_ASSESSMENT_FOUNDATION_MAX_OUTPUT_TOKENS",
                3400,
            ),
            external_assessment_evidence_max_output_tokens=_env_int(
                "AI_EXTERNAL_ASSESSMENT_EVIDENCE_MAX_OUTPUT_TOKENS",
                3400,
            ),
            external_assessment_integrity_max_output_tokens=_env_int(
                "AI_EXTERNAL_ASSESSMENT_INTEGRITY_MAX_OUTPUT_TOKENS",
                2800,
            ),
            external_assessment_corrections_max_output_tokens=_env_int(
                "AI_EXTERNAL_ASSESSMENT_CORRECTIONS_MAX_OUTPUT_TOKENS",
                3400,
            ),
            external_assessment_decision_max_output_tokens=_env_int(
                "AI_EXTERNAL_ASSESSMENT_DECISION_MAX_OUTPUT_TOKENS",
                2200,
            ),
            external_assessment_stage_timeout_seconds=_env_int(
                "AI_EXTERNAL_ASSESSMENT_STAGE_TIMEOUT_SECONDS",
                600,
            ),
            external_assessment_request_timeout_seconds=_env_int(
                "AI_EXTERNAL_ASSESSMENT_REQUEST_TIMEOUT_SECONDS",
                240,
            ),
            external_assessment_request_max_retries=_env_int(
                "AI_EXTERNAL_ASSESSMENT_REQUEST_MAX_RETRIES",
                0,
                0,
            ),
        )

    @property
    def deepseek_configured(self) -> bool:
        return bool(self.enabled and self.deepseek_api_key)

    @property
    def openai_configured(self) -> bool:
        return bool(self.enabled and self.openai_api_key)

    @property
    def openai_verify_model(self) -> str:
        return self.openai_review_model

    @property
    def openai_premium_model(self) -> str:
        return self.openai_review_model

    @property
    def openai_reasoning_effort(self) -> str:
        return self.openai_review_reasoning_effort

    @property
    def openai_verify_input_price(self) -> float:
        return self.openai_review_input_price

    @property
    def openai_verify_cached_input_price(self) -> float:
        return self.openai_review_cached_input_price

    @property
    def openai_verify_output_price(self) -> float:
        return self.openai_review_output_price

    @property
    def openai_premium_input_price(self) -> float:
        return self.openai_review_input_price

    @property
    def openai_premium_cached_input_price(self) -> float:
        return self.openai_review_cached_input_price

    @property
    def openai_premium_output_price(self) -> float:
        return self.openai_review_output_price

    def resolve_mode(self, requested_mode: str, academic_level: str = "") -> str:
        requested = (requested_mode or "standard").strip().lower()
        requested = {"auto": "standard", "openai_only": "advanced", "hybrid": "standard", "premium": "advanced"}.get(requested, requested)
        if requested not in {"light", "standard", "advanced"}:
            raise AIConfigurationError("Choose Light Review, Standard Review or Advanced Review.")
        if not self.deepseek_configured:
            raise AIConfigurationError(
                "The academic review service is temporarily unavailable because the review provider is not configured."
            )
        return requested

    def public_status(self) -> Dict[str, Any]:
        available = ["light", "standard", "advanced"] if self.deepseek_configured else []
        return {"enabled": self.enabled, "configured": bool(available), "review_depths": available}
