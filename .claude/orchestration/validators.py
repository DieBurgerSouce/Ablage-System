"""
Centralized input validation for orchestration system.
Enterprise-grade validation with comprehensive error messages in German.

Provides reusable validators for all orchestration inputs to ensure:
- Type safety (no unexpected types)
- Range validation (bounds checking)
- Security (path traversal prevention)
- Data integrity (format validation)
"""

from typing import List, Optional, Any, Dict
from pathlib import Path
from dataclasses import dataclass
import re


@dataclass
class ValidationError:
    """Validation error with German message."""
    field: str
    message_de: str
    severity: str  # "critical", "high", "medium", "low"


class OrchestrationValidator:
    """Centralized validation for all orchestration inputs."""

    # Valid values for enums
    VALID_TIERS = {"opus", "sonnet", "haiku"}
    VALID_MODELS = {"opus", "sonnet", "haiku"}
    VALID_QUALITY_LEVELS = {"passed", "warning", "failed"}

    # Limits
    MAX_PROMPT_LENGTH = 100000  # ~25k tokens
    MAX_FILE_PATHS = 1000
    MAX_PATTERN_LENGTH = 1000
    MAX_TOKENS = 1000000  # 1M token limit
    MAX_CONFIDENCE = 1.0
    MIN_CONFIDENCE = 0.0

    @staticmethod
    def validate_tier(tier: str, field_name: str = "tier") -> Optional[ValidationError]:
        """
        Validate model tier string.

        Args:
            tier: Tier value to validate
            field_name: Name of field for error message

        Returns:
            ValidationError if invalid, None if valid
        """
        if not isinstance(tier, str):
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} muss ein String sein, nicht {type(tier).__name__}",
                severity="critical"
            )
        if tier not in OrchestrationValidator.VALID_TIERS:
            return ValidationError(
                field=field_name,
                message_de=f"Ungültiger {field_name}: '{tier}'. Erlaubt: {OrchestrationValidator.VALID_TIERS}",
                severity="critical"
            )
        return None

    @staticmethod
    def validate_confidence(confidence: float, field_name: str = "confidence") -> Optional[ValidationError]:
        """
        Validate confidence score (must be 0.0-1.0).

        Args:
            confidence: Confidence value to validate
            field_name: Name of field for error message

        Returns:
            ValidationError if invalid, None if valid
        """
        if not isinstance(confidence, (int, float)):
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} muss numerisch sein, nicht {type(confidence).__name__}",
                severity="critical"
            )
        if not (OrchestrationValidator.MIN_CONFIDENCE <= confidence <= OrchestrationValidator.MAX_CONFIDENCE):
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} muss zwischen {OrchestrationValidator.MIN_CONFIDENCE} und {OrchestrationValidator.MAX_CONFIDENCE} liegen, ist {confidence}",
                severity="high"
            )
        return None

    @staticmethod
    def validate_file_paths(file_paths: List[str], field_name: str = "file_paths") -> Optional[ValidationError]:
        """
        Validate file paths (no path traversal, valid types).

        Args:
            file_paths: List of file paths to validate
            field_name: Name of field for error message

        Returns:
            ValidationError if invalid, None if valid
        """
        if not isinstance(file_paths, list):
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} muss eine Liste sein, nicht {type(file_paths).__name__}",
                severity="critical"
            )

        if len(file_paths) > OrchestrationValidator.MAX_FILE_PATHS:
            return ValidationError(
                field=field_name,
                message_de=f"Zu viele Dateien: {len(file_paths)} > {OrchestrationValidator.MAX_FILE_PATHS}",
                severity="high"
            )

        for i, path in enumerate(file_paths):
            if not isinstance(path, str):
                return ValidationError(
                    field=f"{field_name}[{i}]",
                    message_de=f"Dateipfad muss String sein, nicht {type(path).__name__}",
                    severity="high"
                )

            # Path traversal check
            if ".." in path:
                return ValidationError(
                    field=f"{field_name}[{i}]",
                    message_de=f"Unsicherer Dateipfad erkannt: '{path}' (Path Traversal verhindert)",
                    severity="critical"
                )

            # Absolute path check (security)
            if path.startswith("/") or (len(path) > 1 and path[1] == ":"):
                return ValidationError(
                    field=f"{field_name}[{i}]",
                    message_de=f"Absolute Pfade nicht erlaubt: '{path}'",
                    severity="high"
                )

        return None

    @staticmethod
    def validate_task_prompt(prompt: str, min_length: int = 5) -> Optional[ValidationError]:
        """
        Validate task prompt (non-empty, type check, length).

        Args:
            prompt: Task prompt to validate
            min_length: Minimum prompt length

        Returns:
            ValidationError if invalid, None if valid
        """
        if not isinstance(prompt, str):
            return ValidationError(
                field="task_prompt",
                message_de=f"Task-Prompt muss String sein, nicht {type(prompt).__name__}",
                severity="critical"
            )
        if len(prompt.strip()) < min_length:
            return ValidationError(
                field="task_prompt",
                message_de=f"Task-Prompt zu kurz ({len(prompt)} Zeichen, minimum {min_length})",
                severity="high"
            )
        if len(prompt) > OrchestrationValidator.MAX_PROMPT_LENGTH:
            return ValidationError(
                field="task_prompt",
                message_de=f"Task-Prompt zu lang ({len(prompt)} Zeichen, maximum {OrchestrationValidator.MAX_PROMPT_LENGTH})",
                severity="high"
            )
        return None

    @staticmethod
    def validate_tokens(tokens: int, max_tokens: int = MAX_TOKENS) -> Optional[ValidationError]:
        """
        Validate token count (positive, reasonable bounds).

        Args:
            tokens: Token count to validate
            max_tokens: Maximum allowed tokens

        Returns:
            ValidationError if invalid, None if valid
        """
        if not isinstance(tokens, int):
            return ValidationError(
                field="tokens",
                message_de=f"Token-Anzahl muss Integer sein, nicht {type(tokens).__name__}",
                severity="critical"
            )
        if tokens < 0:
            return ValidationError(
                field="tokens",
                message_de=f"Token-Anzahl kann nicht negativ sein: {tokens}",
                severity="critical"
            )
        if tokens > max_tokens:
            return ValidationError(
                field="tokens",
                message_de=f"Token-Anzahl zu hoch: {tokens} > {max_tokens}",
                severity="high"
            )
        return None

    @staticmethod
    def validate_pattern(pattern: str, field_name: str = "pattern") -> Optional[ValidationError]:
        """
        Validate task pattern string.

        Args:
            pattern: Pattern string to validate
            field_name: Name of field for error message

        Returns:
            ValidationError if invalid, None if valid
        """
        if not isinstance(pattern, str):
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} muss String sein, nicht {type(pattern).__name__}",
                severity="critical"
            )
        if len(pattern) == 0:
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} darf nicht leer sein",
                severity="high"
            )
        if len(pattern) > OrchestrationValidator.MAX_PATTERN_LENGTH:
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} zu lang: {len(pattern)} > {OrchestrationValidator.MAX_PATTERN_LENGTH}",
                severity="medium"
            )
        # Pattern should be alphanumeric + underscore/hyphen
        if not re.match(r'^[a-z0-9_-]+$', pattern):
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} enthält ungültige Zeichen: '{pattern}' (nur a-z, 0-9, _, - erlaubt)",
                severity="medium"
            )
        return None

    @staticmethod
    def validate_quality_level(level: str, field_name: str = "quality_level") -> Optional[ValidationError]:
        """
        Validate quality level string.

        Args:
            level: Quality level to validate
            field_name: Name of field for error message

        Returns:
            ValidationError if invalid, None if valid
        """
        if not isinstance(level, str):
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} muss String sein, nicht {type(level).__name__}",
                severity="critical"
            )
        if level not in OrchestrationValidator.VALID_QUALITY_LEVELS:
            return ValidationError(
                field=field_name,
                message_de=f"Ungültiger {field_name}: '{level}'. Erlaubt: {OrchestrationValidator.VALID_QUALITY_LEVELS}",
                severity="critical"
            )
        return None

    @staticmethod
    def validate_code(code: str, field_name: str = "code") -> Optional[ValidationError]:
        """
        Validate code string (non-empty, type check).

        Args:
            code: Code string to validate
            field_name: Name of field for error message

        Returns:
            ValidationError if invalid, None if valid
        """
        if not isinstance(code, str):
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} muss String sein, nicht {type(code).__name__}",
                severity="critical"
            )
        if len(code.strip()) == 0:
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} darf nicht leer sein",
                severity="high"
            )
        return None

    @staticmethod
    def validate_model_name(model: str, field_name: str = "model") -> Optional[ValidationError]:
        """
        Validate model name string.

        Args:
            model: Model name to validate
            field_name: Name of field for error message

        Returns:
            ValidationError if invalid, None if valid
        """
        if not isinstance(model, str):
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} muss String sein, nicht {type(model).__name__}",
                severity="critical"
            )
        if len(model.strip()) == 0:
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} darf nicht leer sein",
                severity="critical"
            )
        return None

    @staticmethod
    def validate_decision(decision: str, field_name: str = "decision") -> Optional[ValidationError]:
        """
        Validate decision text (non-empty, reasonable length).

        Args:
            decision: Decision text to validate
            field_name: Name of field for error message

        Returns:
            ValidationError if invalid, None if valid
        """
        if not isinstance(decision, str):
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} muss String sein, nicht {type(decision).__name__}",
                severity="critical"
            )
        if len(decision.strip()) == 0:
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} darf nicht leer sein",
                severity="high"
            )
        if len(decision) > 50000:  # ~12.5k tokens
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} zu lang: {len(decision)} Zeichen > 50000",
                severity="medium"
            )
        return None

    @staticmethod
    def validate_reasoning(reasoning: str, field_name: str = "reasoning") -> Optional[ValidationError]:
        """
        Validate reasoning text (non-empty, reasonable length).

        Args:
            reasoning: Reasoning text to validate
            field_name: Name of field for error message

        Returns:
            ValidationError if invalid, None if valid
        """
        if not isinstance(reasoning, str):
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} muss String sein, nicht {type(reasoning).__name__}",
                severity="critical"
            )
        if len(reasoning.strip()) == 0:
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} darf nicht leer sein",
                severity="high"
            )
        if len(reasoning) > 10000:  # ~2.5k tokens
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} zu lang: {len(reasoning)} Zeichen > 10000",
                severity="low"
            )
        return None

    @staticmethod
    def validate_affected_patterns(patterns: List[str], field_name: str = "affected_patterns") -> Optional[ValidationError]:
        """
        Validate affected patterns list.

        Args:
            patterns: List of patterns to validate
            field_name: Name of field for error message

        Returns:
            ValidationError if invalid, None if valid
        """
        if not isinstance(patterns, list):
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} muss eine Liste sein, nicht {type(patterns).__name__}",
                severity="critical"
            )
        for i, pattern in enumerate(patterns):
            if not isinstance(pattern, str):
                return ValidationError(
                    field=f"{field_name}[{i}]",
                    message_de=f"Pattern muss String sein, nicht {type(pattern).__name__}",
                    severity="high"
                )
            if len(pattern.strip()) == 0:
                return ValidationError(
                    field=f"{field_name}[{i}]",
                    message_de=f"Pattern darf nicht leer sein",
                    severity="medium"
                )
        return None

    @staticmethod
    def validate_ttl_days(ttl: int, field_name: str = "ttl_days") -> Optional[ValidationError]:
        """
        Validate TTL in days.

        Args:
            ttl: TTL value to validate
            field_name: Name of field for error message

        Returns:
            ValidationError if invalid, None if valid
        """
        if not isinstance(ttl, int):
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} muss Integer sein, nicht {type(ttl).__name__}",
                severity="critical"
            )
        if ttl < 1:
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} muss mindestens 1 Tag sein, ist {ttl}",
                severity="high"
            )
        if ttl > 365:
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} zu hoch: {ttl} > 365 Tage",
                severity="medium"
            )
        return None

    @staticmethod
    def validate_tags(tags: List[str], field_name: str = "tags") -> Optional[ValidationError]:
        """
        Validate tags list.

        Args:
            tags: List of tags to validate
            field_name: Name of field for error message

        Returns:
            ValidationError if invalid, None if valid
        """
        if not isinstance(tags, list):
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} muss eine Liste sein, nicht {type(tags).__name__}",
                severity="critical"
            )
        if len(tags) > 50:
            return ValidationError(
                field=field_name,
                message_de=f"Zu viele Tags: {len(tags)} > 50",
                severity="medium"
            )
        for i, tag in enumerate(tags):
            if not isinstance(tag, str):
                return ValidationError(
                    field=f"{field_name}[{i}]",
                    message_de=f"Tag muss String sein, nicht {type(tag).__name__}",
                    severity="high"
                )
            if len(tag.strip()) == 0:
                return ValidationError(
                    field=f"{field_name}[{i}]",
                    message_de=f"Tag darf nicht leer sein",
                    severity="medium"
                )
        return None

    @staticmethod
    def validate_context(context: Dict[str, Any], field_name: str = "context") -> Optional[ValidationError]:
        """
        Validate context dictionary.

        Args:
            context: Context dict to validate
            field_name: Name of field for error message

        Returns:
            ValidationError if invalid, None if valid
        """
        if not isinstance(context, dict):
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} muss Dictionary sein, nicht {type(context).__name__}",
                severity="critical"
            )
        return None

    @staticmethod
    def validate_execution_time_ms(time_ms: int, field_name: str = "execution_time_ms") -> Optional[ValidationError]:
        """
        Validate execution time in milliseconds.

        Args:
            time_ms: Execution time to validate
            field_name: Name of field for error message

        Returns:
            ValidationError if invalid, None if valid
        """
        if not isinstance(time_ms, int):
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} muss Integer sein, nicht {type(time_ms).__name__}",
                severity="critical"
            )
        if time_ms < 0:
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} kann nicht negativ sein: {time_ms}",
                severity="critical"
            )
        if time_ms > 3600000:  # 1 hour
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} unrealistisch hoch: {time_ms}ms > 1 Stunde",
                severity="medium"
            )
        return None

    @staticmethod
    def validate_success_flag(success: bool, field_name: str = "success") -> Optional[ValidationError]:
        """
        Validate success boolean flag.

        Args:
            success: Success flag to validate
            field_name: Name of field for error message

        Returns:
            ValidationError if invalid, None if valid
        """
        if not isinstance(success, bool):
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} muss Boolean sein, nicht {type(success).__name__}",
                severity="critical"
            )
        return None

    @staticmethod
    def validate_escalated_flag(escalated: bool, field_name: str = "escalated") -> Optional[ValidationError]:
        """
        Validate escalated boolean flag.

        Args:
            escalated: Escalated flag to validate
            field_name: Name of field for error message

        Returns:
            ValidationError if invalid, None if valid
        """
        if not isinstance(escalated, bool):
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} muss Boolean sein, nicht {type(escalated).__name__}",
                severity="critical"
            )
        return None

    @staticmethod
    def validate_escalation_path(path: str, field_name: str = "escalation_path") -> Optional[ValidationError]:
        """
        Validate escalation path string (e.g., "haiku->sonnet").

        Args:
            path: Escalation path to validate
            field_name: Name of field for error message

        Returns:
            ValidationError if invalid, None if valid
        """
        if not isinstance(path, str):
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} muss String sein, nicht {type(path).__name__}",
                severity="critical"
            )
        # Expected format: "tier->tier"
        if "->" not in path:
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} ungültiges Format: '{path}' (erwartet: 'tier->tier')",
                severity="high"
            )
        parts = path.split("->")
        if len(parts) != 2:
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} ungültiges Format: '{path}' (zu viele '->'')",
                severity="high"
            )
        for i, tier in enumerate(parts):
            if tier not in OrchestrationValidator.VALID_TIERS:
                return ValidationError(
                    field=f"{field_name}[part {i}]",
                    message_de=f"Ungültiger Tier in {field_name}: '{tier}'",
                    severity="high"
                )
        return None

    @staticmethod
    def validate_cache_hit_flag(cache_hit: bool, field_name: str = "cache_hit") -> Optional[ValidationError]:
        """
        Validate cache_hit boolean flag.

        Args:
            cache_hit: Cache hit flag to validate
            field_name: Name of field for error message

        Returns:
            ValidationError if invalid, None if valid
        """
        if not isinstance(cache_hit, bool):
            return ValidationError(
                field=field_name,
                message_de=f"{field_name} muss Boolean sein, nicht {type(cache_hit).__name__}",
                severity="critical"
            )
        return None


def validate_all(validators: List[Optional[ValidationError]]) -> List[ValidationError]:
    """
    Collect all validation errors from a list of validator results.

    Args:
        validators: List of validation results (None or ValidationError)

    Returns:
        List of all errors found (empty if all valid)

    Example:
        >>> errors = validate_all([
        ...     OrchestrationValidator.validate_tier("opus"),
        ...     OrchestrationValidator.validate_confidence(0.95),
        ...     OrchestrationValidator.validate_task_prompt("Implement feature")
        ... ])
        >>> if errors:
        ...     for error in errors:
        ...         logger.error("validation_error", field=error.field, message=error.message_de)
    """
    return [err for err in validators if err is not None]


def has_critical_errors(errors: List[ValidationError]) -> bool:
    """
    Check if any validation errors are critical severity.

    Args:
        errors: List of validation errors

    Returns:
        True if any error is critical severity
    """
    return any(err.severity == "critical" for err in errors)
