# -*- coding: utf-8 -*-
"""Unit tests for webhook verification functions in inbound_service."""

import hashlib
import hmac as hmac_mod
import time

import pytest

from app.services.webhooks.inbound_service import (
    MAX_PAYLOAD_SIZE,
    SIGNATURE_TIMESTAMP_TOLERANCE_SECONDS,
    compute_payload_hash,
    sanitize_payload_for_preview,
    validate_timestamp,
    verify_webhook_signature,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_max_payload_size_is_1mb(self) -> None:
        assert MAX_PAYLOAD_SIZE == 1024 * 1024
        assert MAX_PAYLOAD_SIZE == 1048576

    def test_signature_timestamp_tolerance(self) -> None:
        assert SIGNATURE_TIMESTAMP_TOLERANCE_SECONDS == 300


# ---------------------------------------------------------------------------
# compute_payload_hash
# ---------------------------------------------------------------------------


class TestComputePayloadHash:
    def test_returns_sha256_hex(self) -> None:
        payload = b'{"event": "test"}'
        result = compute_payload_hash(payload)
        expected = hashlib.sha256(payload).hexdigest()
        assert result == expected

    def test_consistent_for_same_input(self) -> None:
        payload = b"hello world"
        assert compute_payload_hash(payload) == compute_payload_hash(payload)

    def test_different_payloads_different_hashes(self) -> None:
        hash1 = compute_payload_hash(b"payload_a")
        hash2 = compute_payload_hash(b"payload_b")
        assert hash1 != hash2

    def test_empty_payload(self) -> None:
        result = compute_payload_hash(b"")
        expected = hashlib.sha256(b"").hexdigest()
        assert result == expected

    def test_hash_length_is_64_hex(self) -> None:
        result = compute_payload_hash(b"test")
        assert len(result) == 64
        # Should be valid hex
        int(result, 16)


# ---------------------------------------------------------------------------
# verify_webhook_signature
# ---------------------------------------------------------------------------


class TestVerifyWebhookSignature:
    def _create_valid_signature(
        self, payload: bytes, timestamp: str, secret: str
    ) -> str:
        message = f"{timestamp}.".encode() + payload
        return hmac_mod.new(secret.encode(), message, hashlib.sha256).hexdigest()

    def test_valid_signature_returns_true(self) -> None:
        payload = b'{"event": "document.created"}'
        timestamp = "1710000000"
        secret = "test-webhook-secret-123"
        signature = self._create_valid_signature(payload, timestamp, secret)

        result = verify_webhook_signature(payload, signature, timestamp, secret)
        assert result is True

    def test_invalid_signature_returns_false(self) -> None:
        payload = b'{"event": "document.created"}'
        timestamp = "1710000000"
        secret = "test-webhook-secret-123"

        result = verify_webhook_signature(payload, "invalid_signature", timestamp, secret)
        assert result is False

    def test_wrong_secret_returns_false(self) -> None:
        payload = b'{"event": "test"}'
        timestamp = "1710000000"
        correct_secret = "correct-secret"
        wrong_secret = "wrong-secret"
        signature = self._create_valid_signature(payload, timestamp, correct_secret)

        result = verify_webhook_signature(payload, signature, timestamp, wrong_secret)
        assert result is False

    def test_tampered_payload_returns_false(self) -> None:
        original_payload = b'{"amount": 100}'
        tampered_payload = b'{"amount": 999}'
        timestamp = "1710000000"
        secret = "secret"
        signature = self._create_valid_signature(original_payload, timestamp, secret)

        result = verify_webhook_signature(tampered_payload, signature, timestamp, secret)
        assert result is False

    def test_different_timestamp_returns_false(self) -> None:
        payload = b'{"event": "test"}'
        secret = "secret"
        signature = self._create_valid_signature(payload, "1000000", secret)

        result = verify_webhook_signature(payload, signature, "9999999", secret)
        assert result is False

    def test_empty_timestamp_still_works(self) -> None:
        payload = b"data"
        secret = "secret"
        signature = self._create_valid_signature(payload, "", secret)

        result = verify_webhook_signature(payload, signature, "", secret)
        assert result is True

    def test_empty_payload(self) -> None:
        payload = b""
        timestamp = "12345"
        secret = "secret"
        signature = self._create_valid_signature(payload, timestamp, secret)

        result = verify_webhook_signature(payload, signature, timestamp, secret)
        assert result is True


# ---------------------------------------------------------------------------
# validate_timestamp
# ---------------------------------------------------------------------------


class TestValidateTimestamp:
    def test_current_timestamp_is_valid(self) -> None:
        now = str(int(time.time()))
        assert validate_timestamp(now) is True

    def test_old_timestamp_is_invalid(self) -> None:
        old = str(int(time.time()) - 600)  # 10 min ago
        assert validate_timestamp(old) is False

    def test_future_timestamp_within_tolerance_is_valid(self) -> None:
        future = str(int(time.time()) + 100)
        assert validate_timestamp(future) is True

    def test_far_future_timestamp_is_invalid(self) -> None:
        far_future = str(int(time.time()) + 600)
        assert validate_timestamp(far_future) is False

    def test_non_numeric_timestamp_is_invalid(self) -> None:
        assert validate_timestamp("not-a-number") is False

    def test_empty_string_is_invalid(self) -> None:
        assert validate_timestamp("") is False


# ---------------------------------------------------------------------------
# sanitize_payload_for_preview
# ---------------------------------------------------------------------------


class TestSanitizePayloadForPreview:
    def test_redacts_pii_fields(self) -> None:
        data = {"name": "Max Mustermann", "event": "created", "iban": "DE123"}
        pii_fields = {"name", "iban"}

        result = sanitize_payload_for_preview(data, pii_fields)

        assert result["name"] == "[REDACTED]"
        assert result["iban"] == "[REDACTED]"
        assert result["event"] == "created"

    def test_case_insensitive_pii_matching(self) -> None:
        data = {"Name": "Max", "EMAIL": "test@example.com"}
        pii_fields = {"name", "email"}

        result = sanitize_payload_for_preview(data, pii_fields)

        assert result["Name"] == "[REDACTED]"
        assert result["EMAIL"] == "[REDACTED]"

    def test_nested_dict_sanitization(self) -> None:
        data = {
            "order": {
                "customer_name": "Max",
                "amount": 100,
            }
        }
        pii_fields = {"customer_name"}

        result = sanitize_payload_for_preview(data, pii_fields)

        assert result["order"]["customer_name"] == "[REDACTED]"
        assert result["order"]["amount"] == 100

    def test_list_of_dicts_sanitization(self) -> None:
        data = {
            "items": [
                {"name": "Max", "id": 1},
                {"name": "Anna", "id": 2},
            ]
        }
        pii_fields = {"name"}

        result = sanitize_payload_for_preview(data, pii_fields)

        assert result["items"][0]["name"] == "[REDACTED]"
        assert result["items"][1]["name"] == "[REDACTED]"
        assert result["items"][0]["id"] == 1

    def test_no_pii_fields_returns_unchanged(self) -> None:
        data = {"event": "test", "amount": 42}
        result = sanitize_payload_for_preview(data, set())
        assert result == data

    def test_empty_data(self) -> None:
        result = sanitize_payload_for_preview({}, {"name"})
        assert result == {}
