# -*- coding: utf-8 -*-
"""Tests for JSONB input validation (CWE-89, CWE-400)."""

import pytest

from app.core.jsonb_validators import (
    validate_jsonb_size,
    validate_jsonb_depth,
    validate_jsonb_keys,
    validate_jsonb_payload,
    MAX_JSONB_SIZE_BYTES,
    MAX_NESTING_DEPTH,
    MAX_ARRAY_LENGTH,
)


class TestJSONBSize:
    """Test JSONB size limits."""

    def test_small_payload_passes(self):
        validate_jsonb_size({"key": "value"})

    def test_oversized_payload_rejected(self):
        large_data = {"key": "x" * (MAX_JSONB_SIZE_BYTES + 1)}
        with pytest.raises(ValueError, match="zu gross"):
            validate_jsonb_size(large_data)

    def test_exact_limit_passes(self):
        # Should not raise for payloads at the limit
        data = {"k": "v"}
        validate_jsonb_size(data, max_bytes=1024)


class TestJSONBDepth:
    """Test JSONB nesting depth limits."""

    def test_flat_object_passes(self):
        validate_jsonb_depth({"a": 1, "b": 2})

    def test_acceptable_nesting_passes(self):
        data = {"a": {"b": {"c": {"d": {"e": "value"}}}}}
        validate_jsonb_depth(data, max_depth=5)

    def test_deeply_nested_rejected(self):
        # Build 10-level deep nesting
        data: dict = {"value": "deep"}
        for i in range(10):
            data = {"level": data}
        with pytest.raises(ValueError, match="zu tief"):
            validate_jsonb_depth(data, max_depth=5)

    def test_long_array_rejected(self):
        data = list(range(MAX_ARRAY_LENGTH + 1))
        with pytest.raises(ValueError, match="zu lang"):
            validate_jsonb_depth(data)

    def test_acceptable_array_passes(self):
        data = list(range(50))
        validate_jsonb_depth(data)


class TestJSONBKeys:
    """Test JSONB key validation."""

    def test_normal_keys_pass(self):
        validate_jsonb_keys({"name": "test", "value": 42})

    def test_sql_injection_in_key_rejected(self):
        with pytest.raises(ValueError, match="Sonderzeichen"):
            validate_jsonb_keys({"key'; DROP TABLE--": "value"})

    def test_null_byte_in_key_rejected(self):
        with pytest.raises(ValueError, match="Sonderzeichen"):
            validate_jsonb_keys({"key\x00": "value"})

    def test_nested_injection_detected(self):
        with pytest.raises(ValueError, match="Sonderzeichen"):
            validate_jsonb_keys({"outer": {"inner'--": "value"}})

    def test_allowed_keys_whitelist(self):
        validate_jsonb_keys(
            {"field": "name", "op": "eq"},
            allowed_keys={"field", "op", "value"},
        )

    def test_disallowed_key_rejected(self):
        with pytest.raises(ValueError, match="Unbekannter"):
            validate_jsonb_keys(
                {"field": "name", "exploit": "value"},
                allowed_keys={"field", "op", "value"},
            )


class TestJSONBPayloadFull:
    """Test full payload validation."""

    def test_valid_rule_condition(self):
        condition = {
            "field": "amount",
            "op": "greater_than",
            "value": 1000,
        }
        validate_jsonb_payload(condition)

    def test_valid_composite_condition(self):
        condition = {
            "and": [
                {"field": "amount", "op": "gt", "value": 100},
                {"field": "type", "op": "eq", "value": "invoice"},
            ]
        }
        validate_jsonb_payload(condition, max_depth=5)

    def test_oversized_and_deep_rejected(self):
        # Both too large and too deep
        data: dict = {"value": "x" * 60000}
        for i in range(10):
            data = {"level": data}
        with pytest.raises(ValueError):
            validate_jsonb_payload(data)
