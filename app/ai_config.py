from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


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


def _env_float(
    name: str,
    default: float,
    minimum: float = 0.0,
    maximum: Optional[float] = None,
) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    value = max(minimum, value)
    return min(value, maximum) if maximum is not None else value


def _env_float_alias(primary: str, legacy: str, default: float) -> float:
    if os.getenv(primary) is not None:
        return _env_float(primary, default)
    if os.getenv(legacy) is not None:
        return _env_float(legacy, default)
    return default


def _normalise_effort(value: str, default: str = "high") -> str:
    effort = (value or default).strip().lower()
    allowed = {"none", "minimal", "low", "medium", "high", "xhigh"}
    return effort if effort in allowed else default


@dataclass(frozen=True)
class HybridAIConfig:
    """Academic-review routing configuration.

    The fast chapter reviewer uses GPT-5.4 mini. Factual verification,
    cross-chapter judgement, advanced research methods/results review and
    external examination use GPT-5.4. Review depth controls breadth and detail,
    not the factual-accuracy threshold.

    DeepSeek fields remain only for backwards compatibility with dormant
    modules and are not used by the active supervisory-review pipeline.
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

    # Compatibility aliases. These resolve to the chapter model/effort.
    openai_review_model: str
    openai_review_reasoning_effort: str

    # Active model roles.
    openai_chapter_model: str
    openai_chapter_reasoning_effort: str
    openai_expert_model: str
    openai_expert_reasoning_effort: str
    openai_final_audit_model: str
    openai_final_audit_reasoning_effort: str
    # Compatibility aliases for older deployments.
    openai_external_model: str
    openai_external_reasoning_effort: str
    openai_external_decision_reasoning_effort: str

    # Active external-examination roles.
    openai_external_domain_model: str
    openai_external_domain_reasoning_effort: str
    openai_external_adjudicator_model: str
    openai_external_adjudicator_reasoning_effort: str

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
    chapter_review_concurrency: int
    chapter_packet_max_chars: int
    chapter_recovery_concurrency: int
    chapter_recovery_max_output_tokens: int
    section_batch_size: int
    light_section_batch_size: int
    advanced_section_batch_size: int
    verification_batch_size: int
    recovery_batch_size: int
    max_recovery_batches: int
    max_short_section_fallbacks: int
    focused_recovery_parallel_calls: int
    focused_recovery_max_output_tokens: int
    focused_recovery_timeout_seconds: int
    max_unresolved_section_fallbacks: int
    advanced_audit_max_findings: int
    advanced_audit_max_output_tokens: int
    strict_failure: bool
    structured_output_retries: int
    advanced_quality_control: bool

    deepseek_pro_input_price: float
    deepseek_pro_cached_input_price: float
    deepseek_pro_output_price: float

    # Compatibility aliases for the chapter model price.
    openai_review_input_price: float
    openai_review_cached_input_price: float
    openai_review_output_price: float

    openai_chapter_input_price: float
    openai_chapter_cached_input_price: float
    openai_chapter_output_price: float
    openai_expert_input_price: float
    openai_expert_cached_input_price: float
    openai_expert_output_price: float

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
    openai_mini_model: str = "gpt-5.4-mini"
    openai_advanced_model: str = "gpt-5.4"
    openai_mini_reasoning_effort: str = "high"
    openai_advanced_reasoning_effort: str = "high"
    mini_max_output_tokens: int = 7500
    review_max_output_tokens: int = 9000
    openai_mini_input_price: float = 0.75
    openai_mini_cached_input_price: float = 0.075
    openai_mini_output_price: float = 4.50
    openai_advanced_input_price: float = 2.50
    openai_advanced_cached_input_price: float = 0.25
    openai_advanced_output_price: float = 15.00
    external_assessment_foundation_max_output_tokens: int = 8000
    external_assessment_evidence_max_output_tokens: int = 8000
    external_assessment_integrity_max_output_tokens: int = 6500
    # Legacy fields retained for compatibility with old environment files.
    external_assessment_corrections_max_output_tokens: int = 8000
    external_assessment_decision_max_output_tokens: int = 5000
    external_assessment_adjudication_max_output_tokens: int = 11000
    external_assessment_stage_timeout_seconds: int = 900
    external_assessment_request_timeout_seconds: int = 360
    external_assessment_request_max_retries: int = 0

    @classmethod
    def from_env(cls) -> "HybridAIConfig":
        review_model = os.getenv(
            "DEEPSEEK_REVIEW_MODEL", "deepseek-v4-pro"
        ).strip()
        advanced_model = os.getenv(
            "DEEPSEEK_ADVANCED_MODEL", review_model
        ).strip()

        # Role-specific variables are authoritative. The old
        # OPENAI_REVIEW_MODEL setting is intentionally ignored so a stale
        # o3-mini value cannot silently override the upgraded workflow.
        chapter_model = os.getenv(
            "OPENAI_CHAPTER_MODEL", "gpt-5.4-mini"
        ).strip()
        expert_model = os.getenv(
            "OPENAI_EXPERT_MODEL", "gpt-5.4"
        ).strip()
        audit_model = os.getenv(
            "OPENAI_FINAL_AUDIT_MODEL", expert_model
        ).strip()
        legacy_external_model = os.getenv(
            "OPENAI_EXTERNAL_MODEL", expert_model
        ).strip()
        external_domain_model = os.getenv(
            "OPENAI_EXTERNAL_DOMAIN_MODEL", legacy_external_model
        ).strip()
        external_adjudicator_model = os.getenv(
            "OPENAI_EXTERNAL_ADJUDICATOR_MODEL", legacy_external_model
        ).strip()

        chapter_effort = _normalise_effort(
            os.getenv("OPENAI_CHAPTER_REASONING_EFFORT", "high")
        )
        expert_effort = _normalise_effort(
            os.getenv("OPENAI_EXPERT_REASONING_EFFORT", "high")
        )
        audit_effort = _normalise_effort(
            os.getenv("OPENAI_FINAL_AUDIT_REASONING_EFFORT", expert_effort)
        )
        legacy_external_effort = _normalise_effort(
            os.getenv("OPENAI_EXTERNAL_REASONING_EFFORT", expert_effort)
        )
        legacy_decision_effort = _normalise_effort(
            os.getenv(
                "OPENAI_EXTERNAL_DECISION_REASONING_EFFORT", "xhigh"
            ),
            default="xhigh",
        )
        external_domain_effort = _normalise_effort(
            os.getenv(
                "OPENAI_EXTERNAL_DOMAIN_REASONING_EFFORT",
                legacy_external_effort,
            )
        )
        external_adjudicator_effort = _normalise_effort(
            os.getenv(
                "OPENAI_EXTERNAL_ADJUDICATOR_REASONING_EFFORT",
                legacy_decision_effort,
            ),
            default="xhigh",
        )

        standard_tokens = _env_int("AI_STANDARD_MAX_OUTPUT_TOKENS", 9000)
        advanced_tokens = _env_int("AI_ADVANCED_MAX_OUTPUT_TOKENS", 12000)

        chapter_input_price = _env_float_alias(
            "PRICE_OPENAI_CHAPTER_INPUT", "PRICE_OPENAI_REVIEW_INPUT", 0.75
        )
        chapter_cached_price = _env_float_alias(
            "PRICE_OPENAI_CHAPTER_CACHED_INPUT",
            "PRICE_OPENAI_REVIEW_CACHED_INPUT",
            0.075,
        )
        chapter_output_price = _env_float_alias(
            "PRICE_OPENAI_CHAPTER_OUTPUT", "PRICE_OPENAI_REVIEW_OUTPUT", 4.50
        )
        expert_input_price = _env_float(
            "PRICE_OPENAI_EXPERT_INPUT", 2.50
        )
        expert_cached_price = _env_float(
            "PRICE_OPENAI_EXPERT_CACHED_INPUT", 0.25
        )
        expert_output_price = _env_float(
            "PRICE_OPENAI_EXPERT_OUTPUT", 15.00
        )

        return cls(
            enabled=_env_bool("AI_REVIEW_ENABLED", True),
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", "").strip(),
            deepseek_base_url=os.getenv(
                "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
            ).rstrip("/"),
            deepseek_review_model=review_model,
            deepseek_advanced_model=advanced_model,
            deepseek_reasoning_effort=os.getenv(
                "DEEPSEEK_REASONING_EFFORT", "high"
            ).strip().lower(),
            deepseek_advanced_reasoning_effort=os.getenv(
                "DEEPSEEK_ADVANCED_REASONING_EFFORT", "max"
            ).strip().lower(),
            deepseek_advanced_primary_reasoning_effort=os.getenv(
                "DEEPSEEK_ADVANCED_PRIMARY_REASONING_EFFORT", "high"
            ).strip().lower(),
            deepseek_thinking_enabled=_env_bool(
                "DEEPSEEK_THINKING_ENABLED", True
            ),

            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            openai_base_url=os.getenv(
                "OPENAI_BASE_URL", "https://api.openai.com/v1"
            ).rstrip("/"),
            openai_review_model=chapter_model,
            openai_review_reasoning_effort=chapter_effort,
            openai_chapter_model=chapter_model,
            openai_chapter_reasoning_effort=chapter_effort,
            openai_expert_model=expert_model,
            openai_expert_reasoning_effort=expert_effort,
            openai_final_audit_model=audit_model,
            openai_final_audit_reasoning_effort=audit_effort,
            openai_external_model=external_domain_model,
            openai_external_reasoning_effort=external_domain_effort,
            openai_external_decision_reasoning_effort=external_adjudicator_effort,
            openai_external_domain_model=external_domain_model,
            openai_external_domain_reasoning_effort=external_domain_effort,
            openai_external_adjudicator_model=external_adjudicator_model,
            openai_external_adjudicator_reasoning_effort=external_adjudicator_effort,

            confidence_threshold=_env_float(
                "AI_CONFIDENCE_THRESHOLD", 0.78, 0.0, 1.0
            ),
            max_context_chars_per_rule=_env_int(
                "AI_MAX_CONTEXT_CHARS_PER_RULE", 9000
            ),
            max_map_input_chars=_env_int("AI_MAX_MAP_INPUT_CHARS", 30000),
            max_output_tokens=_env_int("AI_MAX_OUTPUT_TOKENS", 12000),
            light_max_output_tokens=_env_int(
                "AI_LIGHT_MAX_OUTPUT_TOKENS", 7000
            ),
            standard_max_output_tokens=standard_tokens,
            advanced_max_output_tokens=advanced_tokens,
            timeout_seconds=_env_int("AI_TIMEOUT_SECONDS", 300),
            max_retries=_env_int("AI_MAX_RETRIES", 1, 0),
            max_parallel_calls=_env_int("AI_MAX_PARALLEL_CALLS", 4),
            chapter_review_concurrency=_env_int(
                "AI_CHAPTER_REVIEW_CONCURRENCY", 4
            ),
            chapter_packet_max_chars=_env_int(
                "AI_CHAPTER_PACKET_MAX_CHARS", 120000
            ),
            chapter_recovery_concurrency=_env_int(
                "AI_CHAPTER_RECOVERY_CONCURRENCY", 2
            ),
            chapter_recovery_max_output_tokens=_env_int(
                "AI_CHAPTER_RECOVERY_MAX_OUTPUT_TOKENS", 7000
            ),
            section_batch_size=_env_int("AI_SECTION_BATCH_SIZE", 5),
            light_section_batch_size=_env_int(
                "AI_LIGHT_SECTION_BATCH_SIZE", 6
            ),
            advanced_section_batch_size=_env_int(
                "AI_ADVANCED_SECTION_BATCH_SIZE", 4
            ),
            verification_batch_size=_env_int(
                "AI_VERIFICATION_BATCH_SIZE", 48
            ),
            recovery_batch_size=_env_int("AI_RECOVERY_BATCH_SIZE", 6),
            max_recovery_batches=_env_int("AI_MAX_RECOVERY_BATCHES", 2),
            max_short_section_fallbacks=_env_int(
                "AI_MAX_SHORT_SECTION_FALLBACKS", 2, 0
            ),
            focused_recovery_parallel_calls=_env_int(
                "AI_FOCUSED_RECOVERY_PARALLEL_CALLS", 2
            ),
            focused_recovery_max_output_tokens=_env_int(
                "AI_FOCUSED_RECOVERY_MAX_OUTPUT_TOKENS", 4200
            ),
            focused_recovery_timeout_seconds=_env_int(
                "AI_FOCUSED_RECOVERY_TIMEOUT_SECONDS", 240
            ),
            max_unresolved_section_fallbacks=_env_int(
                "AI_MAX_UNRESOLVED_SECTION_FALLBACKS", 8, 0
            ),
            advanced_audit_max_findings=_env_int(
                "AI_ADVANCED_AUDIT_MAX_FINDINGS", 24
            ),
            advanced_audit_max_output_tokens=_env_int(
                "AI_ADVANCED_AUDIT_MAX_OUTPUT_TOKENS", 8000
            ),
            strict_failure=_env_bool("AI_STRICT_FAILURE", False),
            structured_output_retries=_env_int(
                "AI_STRUCTURED_OUTPUT_RETRIES", 0, 0
            ),
            advanced_quality_control=_env_bool(
                "AI_ADVANCED_SECOND_PASS", True
            ),

            deepseek_pro_input_price=_env_float(
                "PRICE_DEEPSEEK_PRO_INPUT", 0.435
            ),
            deepseek_pro_cached_input_price=_env_float(
                "PRICE_DEEPSEEK_PRO_CACHED_INPUT", 0.003625
            ),
            deepseek_pro_output_price=_env_float(
                "PRICE_DEEPSEEK_PRO_OUTPUT", 0.87
            ),
            openai_review_input_price=chapter_input_price,
            openai_review_cached_input_price=chapter_cached_price,
            openai_review_output_price=chapter_output_price,
            openai_chapter_input_price=chapter_input_price,
            openai_chapter_cached_input_price=chapter_cached_price,
            openai_chapter_output_price=chapter_output_price,
            openai_expert_input_price=expert_input_price,
            openai_expert_cached_input_price=expert_cached_price,
            openai_expert_output_price=expert_output_price,

            deepseek_extract_model=review_model,
            openai_mini_model=chapter_model,
            openai_advanced_model=expert_model,
            openai_mini_reasoning_effort=chapter_effort,
            openai_advanced_reasoning_effort=expert_effort,
            mini_max_output_tokens=standard_tokens,
            review_max_output_tokens=advanced_tokens,
            openai_mini_input_price=chapter_input_price,
            openai_mini_cached_input_price=chapter_cached_price,
            openai_mini_output_price=chapter_output_price,
            openai_advanced_input_price=expert_input_price,
            openai_advanced_cached_input_price=expert_cached_price,
            openai_advanced_output_price=expert_output_price,
            external_assessment_foundation_max_output_tokens=_env_int(
                "AI_EXTERNAL_ASSESSMENT_FOUNDATION_MAX_OUTPUT_TOKENS", 8000
            ),
            external_assessment_evidence_max_output_tokens=_env_int(
                "AI_EXTERNAL_ASSESSMENT_EVIDENCE_MAX_OUTPUT_TOKENS", 8000
            ),
            external_assessment_integrity_max_output_tokens=_env_int(
                "AI_EXTERNAL_ASSESSMENT_INTEGRITY_MAX_OUTPUT_TOKENS", 6500
            ),
            external_assessment_corrections_max_output_tokens=_env_int(
                "AI_EXTERNAL_ASSESSMENT_CORRECTIONS_MAX_OUTPUT_TOKENS", 8000
            ),
            external_assessment_decision_max_output_tokens=_env_int(
                "AI_EXTERNAL_ASSESSMENT_DECISION_MAX_OUTPUT_TOKENS", 5000
            ),
            external_assessment_adjudication_max_output_tokens=_env_int(
                "AI_EXTERNAL_ASSESSMENT_ADJUDICATION_MAX_OUTPUT_TOKENS", 11000
            ),
            external_assessment_stage_timeout_seconds=_env_int(
                "AI_EXTERNAL_ASSESSMENT_STAGE_TIMEOUT_SECONDS", 900
            ),
            external_assessment_request_timeout_seconds=_env_int(
                "AI_EXTERNAL_ASSESSMENT_REQUEST_TIMEOUT_SECONDS", 360
            ),
            external_assessment_request_max_retries=_env_int(
                "AI_EXTERNAL_ASSESSMENT_REQUEST_MAX_RETRIES", 0, 0
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
        return self.openai_final_audit_model

    @property
    def openai_premium_model(self) -> str:
        return self.openai_expert_model

    @property
    def openai_reasoning_effort(self) -> str:
        return self.openai_chapter_reasoning_effort

    @property
    def openai_verify_input_price(self) -> float:
        return self.openai_expert_input_price

    @property
    def openai_verify_cached_input_price(self) -> float:
        return self.openai_expert_cached_input_price

    @property
    def openai_verify_output_price(self) -> float:
        return self.openai_expert_output_price

    @property
    def openai_premium_input_price(self) -> float:
        return self.openai_expert_input_price

    @property
    def openai_premium_cached_input_price(self) -> float:
        return self.openai_expert_cached_input_price

    @property
    def openai_premium_output_price(self) -> float:
        return self.openai_expert_output_price

    def openai_prices_for_model(self, model: str) -> Tuple[float, float, float]:
        """Return input, cached-input and output prices for a model role."""
        value = (model or "").strip().lower()
        expert_models = {
            self.openai_expert_model.lower(),
            self.openai_final_audit_model.lower(),
            self.openai_external_model.lower(),
            self.openai_external_domain_model.lower(),
            self.openai_external_adjudicator_model.lower(),
        }
        if value in expert_models:
            return (
                self.openai_expert_input_price,
                self.openai_expert_cached_input_price,
                self.openai_expert_output_price,
            )
        return (
            self.openai_chapter_input_price,
            self.openai_chapter_cached_input_price,
            self.openai_chapter_output_price,
        )

    def resolve_mode(self, requested_mode: str, academic_level: str = "") -> str:
        requested = (requested_mode or "standard").strip().lower()
        requested = {
            "auto": "standard",
            "openai_only": "advanced",
            "hybrid": "standard",
            "premium": "advanced",
        }.get(requested, requested)
        if requested not in {"light", "standard", "advanced"}:
            raise AIConfigurationError(
                "Choose Light Review, Standard Review or Advanced Review."
            )
        if not self.openai_configured:
            raise AIConfigurationError(
                "The academic review service is temporarily unavailable because "
                "the OpenAI API key is not configured."
            )
        return requested

    def public_status(self) -> Dict[str, Any]:
        available = (
            ["light", "standard", "advanced"]
            if self.openai_configured
            else []
        )
        return {
            "enabled": self.enabled,
            "configured": bool(available),
            "review_depths": available,
        }
