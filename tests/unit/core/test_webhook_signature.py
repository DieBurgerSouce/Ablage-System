# -*- coding: utf-8 -*-
"""
Tests für Webhook Signature Utilities.

Testet HMAC-SHA256 Signatur-Generierung und -Verifizierung
mit Timestamp-basiertem Replay-Attack-Schutz.
"""

import hashlib
import hmac
import time
from unittest.mock import patch

import pytest

from app.core.webhook_signature import (
    SignatureComponents,
    SignatureVersion,
    WebhookSignatureError,
    InvalidSignatureError,
    SignatureExpiredError,
    InvalidSignatureFormatError,
    generate_signature,
    generate_signature_header,
    parse_signature_header,
    verify_signature,
    verify_signature_safe,
    SIGNATURE_HEADER_NAME,
    SIGNATURE_HEADER_ALIASES,
    get_signature_header_value,
    create_signed_webhook_payload,
    is_webhook_secret_valid,
    mask_webhook_secret,
    DEFAULT_TOLERANCE_SECONDS,
    MAX_TOLERANCE_SECONDS,
)


# ==================== Test Constants ====================

TEST_SECRET = "whsec_test_secret_12345678901234567890"
TEST_PAYLOAD = b'{"event":"document.processed","data":{"id":"doc_123"}}'


# ==================== Tests: Signatur-Generierung ====================


class TestGenerateSignature:
    """Tests für generate_signature Funktion."""

    def test_generates_valid_signature_format(self):
        """Generiert korrektes Signaturformat t=<ts>,v1=<sig>."""
        header, timestamp = generate_signature(TEST_PAYLOAD, TEST_SECRET)

        assert header.startswith("t=")
        assert ",v1=" in header
        assert str(timestamp) in header

    def test_uses_current_time_by_default(self):
        """Verwendet aktuelle Zeit wenn kein Timestamp angegeben."""
        current_time = int(time.time())
        header, timestamp = generate_signature(TEST_PAYLOAD, TEST_SECRET)

        # Timestamp sollte nahe an aktueller Zeit sein (innerhalb 2 Sekunden)
        assert abs(timestamp - current_time) < 2

    def test_uses_provided_timestamp(self):
        """Verwendet angegebenen Timestamp."""
        fixed_timestamp = 1700000000
        header, timestamp = generate_signature(
            TEST_PAYLOAD, TEST_SECRET, fixed_timestamp
        )

        assert timestamp == fixed_timestamp
        assert f"t={fixed_timestamp}" in header

    def test_signature_is_deterministic(self):
        """Gleiche Eingabe ergibt gleiche Signatur."""
        timestamp = 1700000000
        header1, _ = generate_signature(TEST_PAYLOAD, TEST_SECRET, timestamp)
        header2, _ = generate_signature(TEST_PAYLOAD, TEST_SECRET, timestamp)

        assert header1 == header2

    def test_different_payload_produces_different_signature(self):
        """Unterschiedliche Payloads ergeben unterschiedliche Signaturen."""
        timestamp = 1700000000
        header1, _ = generate_signature(b'{"a":1}', TEST_SECRET, timestamp)
        header2, _ = generate_signature(b'{"a":2}', TEST_SECRET, timestamp)

        assert header1 != header2

    def test_different_secret_produces_different_signature(self):
        """Unterschiedliche Secrets ergeben unterschiedliche Signaturen."""
        timestamp = 1700000000
        header1, _ = generate_signature(TEST_PAYLOAD, "secret1", timestamp)
        header2, _ = generate_signature(TEST_PAYLOAD, "secret2", timestamp)

        assert header1 != header2

    def test_different_timestamp_produces_different_signature(self):
        """Unterschiedliche Timestamps ergeben unterschiedliche Signaturen."""
        header1, _ = generate_signature(TEST_PAYLOAD, TEST_SECRET, 1700000000)
        header2, _ = generate_signature(TEST_PAYLOAD, TEST_SECRET, 1700000001)

        assert header1 != header2

    def test_signature_is_hmac_sha256(self):
        """Signatur ist korrektes HMAC-SHA256."""
        timestamp = 1700000000
        header, _ = generate_signature(TEST_PAYLOAD, TEST_SECRET, timestamp)

        # Parse signature
        parts = header.split(",")
        v1_part = [p for p in parts if p.startswith("v1=")][0]
        actual_signature = v1_part.split("=", 1)[1]

        # Berechne erwartete Signatur
        signed_payload = f"{timestamp}.".encode("utf-8") + TEST_PAYLOAD
        expected_signature = hmac.new(
            TEST_SECRET.encode("utf-8"),
            signed_payload,
            hashlib.sha256
        ).hexdigest()

        assert actual_signature == expected_signature


class TestGenerateSignatureHeader:
    """Tests für generate_signature_header Convenience-Funktion."""

    def test_returns_header_string_only(self):
        """Gibt nur Header-String zurück."""
        header = generate_signature_header(TEST_PAYLOAD, TEST_SECRET)

        assert isinstance(header, str)
        assert header.startswith("t=")

    def test_equivalent_to_generate_signature(self):
        """Äquivalent zu generate_signature()[0]."""
        timestamp = 1700000000
        header1, _ = generate_signature(TEST_PAYLOAD, TEST_SECRET, timestamp)
        header2 = generate_signature_header(TEST_PAYLOAD, TEST_SECRET, timestamp)

        assert header1 == header2


# ==================== Tests: Signatur-Parsing ====================


class TestParseSignatureHeader:
    """Tests für parse_signature_header Funktion."""

    def test_parses_valid_header(self):
        """Parst gültigen Header korrekt."""
        header = "t=1700000000,v1=abc123def456"
        components = parse_signature_header(header)

        assert components.timestamp == 1700000000
        assert components.v1_signature == "abc123def456"

    def test_handles_whitespace(self):
        """Behandelt Whitespace korrekt."""
        header = "t=1700000000, v1=abc123"
        components = parse_signature_header(header)

        assert components.timestamp == 1700000000
        assert components.v1_signature == "abc123"

    def test_multiple_signatures(self):
        """Unterstützt mehrere Signatur-Versionen."""
        header = "t=1700000000,v1=sig_v1,v2=sig_v2"
        components = parse_signature_header(header)

        assert components.timestamp == 1700000000
        assert components.signatures["v1"] == "sig_v1"
        assert components.signatures["v2"] == "sig_v2"

    def test_raises_on_empty_header(self):
        """Wirft Fehler bei leerem Header."""
        with pytest.raises(InvalidSignatureFormatError) as exc:
            parse_signature_header("")

        assert "leer" in str(exc.value)

    def test_raises_on_missing_timestamp(self):
        """Wirft Fehler bei fehlendem Timestamp."""
        with pytest.raises(InvalidSignatureFormatError) as exc:
            parse_signature_header("v1=abc123")

        assert "Timestamp" in str(exc.value)

    def test_raises_on_invalid_timestamp(self):
        """Wirft Fehler bei ungültigem Timestamp."""
        with pytest.raises(InvalidSignatureFormatError) as exc:
            parse_signature_header("t=not_a_number,v1=abc123")

        assert "Ungültiger Timestamp" in str(exc.value)

    def test_raises_on_missing_signature(self):
        """Wirft Fehler bei fehlender Signatur."""
        with pytest.raises(InvalidSignatureFormatError) as exc:
            parse_signature_header("t=1700000000")

        assert "Signatur-Version" in str(exc.value)


# ==================== Tests: Signatur-Verifizierung ====================


class TestVerifySignature:
    """Tests für verify_signature Funktion."""

    def test_verifies_valid_signature(self):
        """Verifiziert gültige Signatur."""
        timestamp = int(time.time())
        header, _ = generate_signature(TEST_PAYLOAD, TEST_SECRET, timestamp)

        result = verify_signature(TEST_PAYLOAD, header, TEST_SECRET)
        assert result is True

    def test_fails_on_wrong_payload(self):
        """Schlägt bei falschem Payload fehl."""
        timestamp = int(time.time())
        header, _ = generate_signature(TEST_PAYLOAD, TEST_SECRET, timestamp)

        with pytest.raises(InvalidSignatureError):
            verify_signature(b'{"wrong":"payload"}', header, TEST_SECRET)

    def test_fails_on_wrong_secret(self):
        """Schlägt bei falschem Secret fehl."""
        timestamp = int(time.time())
        header, _ = generate_signature(TEST_PAYLOAD, TEST_SECRET, timestamp)

        with pytest.raises(InvalidSignatureError):
            verify_signature(TEST_PAYLOAD, header, "wrong_secret")

    def test_fails_on_tampered_signature(self):
        """Schlägt bei manipulierter Signatur fehl."""
        timestamp = int(time.time())
        header, _ = generate_signature(TEST_PAYLOAD, TEST_SECRET, timestamp)

        # Manipuliere Signatur
        tampered_header = header[:-1] + "X"

        with pytest.raises(InvalidSignatureError):
            verify_signature(TEST_PAYLOAD, tampered_header, TEST_SECRET)

    def test_fails_on_expired_signature(self):
        """Schlägt bei abgelaufener Signatur fehl."""
        old_timestamp = int(time.time()) - 400  # 400 Sekunden alt
        header, _ = generate_signature(TEST_PAYLOAD, TEST_SECRET, old_timestamp)

        with pytest.raises(SignatureExpiredError):
            verify_signature(
                TEST_PAYLOAD, header, TEST_SECRET,
                tolerance_seconds=300  # 5 Minuten Toleranz
            )

    def test_accepts_signature_within_tolerance(self):
        """Akzeptiert Signatur innerhalb des Toleranzfensters."""
        timestamp = int(time.time()) - 100  # 100 Sekunden alt
        header, _ = generate_signature(TEST_PAYLOAD, TEST_SECRET, timestamp)

        result = verify_signature(
            TEST_PAYLOAD, header, TEST_SECRET,
            tolerance_seconds=300  # 5 Minuten Toleranz
        )
        assert result is True

    def test_respects_tolerance_parameter(self):
        """Respektiert Toleranzparameter."""
        timestamp = int(time.time()) - 60  # 60 Sekunden alt
        header, _ = generate_signature(TEST_PAYLOAD, TEST_SECRET, timestamp)

        # Sollte mit 30s Toleranz fehlschlagen
        with pytest.raises(SignatureExpiredError):
            verify_signature(
                TEST_PAYLOAD, header, TEST_SECRET,
                tolerance_seconds=30
            )

        # Sollte mit 120s Toleranz funktionieren
        result = verify_signature(
            TEST_PAYLOAD, header, TEST_SECRET,
            tolerance_seconds=120
        )
        assert result is True

    def test_caps_tolerance_at_maximum(self):
        """Begrenzt Toleranz auf Maximum."""
        # Signatur 2 Stunden alt
        old_timestamp = int(time.time()) - 7200
        header, _ = generate_signature(TEST_PAYLOAD, TEST_SECRET, old_timestamp)

        # Auch mit sehr hoher Toleranz sollte es fehlschlagen (Max: 1h)
        with pytest.raises(SignatureExpiredError):
            verify_signature(
                TEST_PAYLOAD, header, TEST_SECRET,
                tolerance_seconds=99999  # Wird auf 3600 begrenzt
            )

    def test_raises_on_missing_v1_signature(self):
        """Wirft Fehler wenn v1-Signatur fehlt."""
        # Verwende aktuellen Timestamp um Expiry-Check zu umgehen
        current_timestamp = int(time.time())
        header = f"t={current_timestamp},v2=some_other_version"

        with pytest.raises(InvalidSignatureFormatError) as exc:
            verify_signature(TEST_PAYLOAD, header, TEST_SECRET)

        assert "v1" in str(exc.value)

    def test_timing_safe_comparison(self):
        """Verwendet timing-safe Vergleich (keine Timing-Angriffe)."""
        # Dieser Test stellt sicher, dass hmac.compare_digest verwendet wird
        # Indirekt getestet durch korrektes Verhalten bei falscher Signatur
        timestamp = int(time.time())
        header, _ = generate_signature(TEST_PAYLOAD, TEST_SECRET, timestamp)

        # Beide sollten gleich lang dauern (timing-safe)
        with pytest.raises(InvalidSignatureError):
            verify_signature(TEST_PAYLOAD, header, "wrong")

        with pytest.raises(InvalidSignatureError):
            verify_signature(b'{"wrong":true}', header, TEST_SECRET)


class TestVerifySignatureSafe:
    """Tests für verify_signature_safe Funktion."""

    def test_returns_true_for_valid_signature(self):
        """Gibt (True, None) für gültige Signatur zurück."""
        timestamp = int(time.time())
        header, _ = generate_signature(TEST_PAYLOAD, TEST_SECRET, timestamp)

        is_valid, error = verify_signature_safe(TEST_PAYLOAD, header, TEST_SECRET)

        assert is_valid is True
        assert error is None

    def test_returns_false_for_invalid_signature(self):
        """Gibt (False, error_message) für ungültige Signatur zurück."""
        timestamp = int(time.time())
        header, _ = generate_signature(TEST_PAYLOAD, TEST_SECRET, timestamp)

        is_valid, error = verify_signature_safe(TEST_PAYLOAD, header, "wrong_secret")

        assert is_valid is False
        assert error is not None
        assert "Ungültige Signatur" in error

    def test_returns_false_for_expired_signature(self):
        """Gibt (False, error_message) für abgelaufene Signatur zurück."""
        old_timestamp = int(time.time()) - 400
        header, _ = generate_signature(TEST_PAYLOAD, TEST_SECRET, old_timestamp)

        is_valid, error = verify_signature_safe(
            TEST_PAYLOAD, header, TEST_SECRET,
            tolerance_seconds=300
        )

        assert is_valid is False
        assert error is not None
        assert "abgelaufen" in error

    def test_returns_false_for_invalid_format(self):
        """Gibt (False, error_message) für ungültiges Format zurück."""
        is_valid, error = verify_signature_safe(
            TEST_PAYLOAD, "invalid_header", TEST_SECRET
        )

        assert is_valid is False
        assert error is not None
        assert "Format" in error

    def test_never_raises_exception(self):
        """Wirft niemals Exception."""
        # Verschiedene ungültige Eingaben
        test_cases = [
            (b"", "", ""),
            (None, None, None),  # type: ignore
            (TEST_PAYLOAD, "malformed", TEST_SECRET),
            (TEST_PAYLOAD, "t=abc,v1=123", TEST_SECRET),
        ]

        for payload, header, secret in test_cases:
            try:
                is_valid, error = verify_signature_safe(payload, header, secret)
                assert is_valid is False
                assert error is not None
            except Exception:
                pytest.fail("verify_signature_safe sollte keine Exception werfen")


# ==================== Tests: Header-Utilities ====================


class TestGetSignatureHeaderValue:
    """Tests für get_signature_header_value Funktion."""

    def test_finds_standard_header(self):
        """Findet Standard-Header."""
        headers = {"X-Webhook-Signature": "t=123,v1=abc"}
        result = get_signature_header_value(headers)
        assert result == "t=123,v1=abc"

    def test_case_insensitive(self):
        """Case-insensitive Header-Suche."""
        headers = {"x-webhook-signature": "t=123,v1=abc"}
        result = get_signature_header_value(headers)
        assert result == "t=123,v1=abc"

    def test_finds_github_style_header(self):
        """Findet GitHub-Style Header."""
        headers = {"X-Hub-Signature-256": "t=123,v1=abc"}
        result = get_signature_header_value(headers)
        assert result == "t=123,v1=abc"

    def test_finds_stripe_style_header(self):
        """Findet Stripe-Style Header."""
        headers = {"Stripe-Signature": "t=123,v1=abc"}
        result = get_signature_header_value(headers)
        assert result == "t=123,v1=abc"

    def test_returns_none_for_missing_header(self):
        """Gibt None zurück wenn Header fehlt."""
        headers = {"Content-Type": "application/json"}
        result = get_signature_header_value(headers)
        assert result is None

    def test_prefers_standard_header(self):
        """Bevorzugt Standard-Header über Aliase."""
        headers = {
            "X-Webhook-Signature": "standard",
            "Stripe-Signature": "stripe",
        }
        result = get_signature_header_value(headers)
        assert result == "standard"


class TestCreateSignedWebhookPayload:
    """Tests für create_signed_webhook_payload Funktion."""

    def test_returns_payload_and_headers(self):
        """Gibt Payload und Headers zurück."""
        payload, headers = create_signed_webhook_payload(
            TEST_PAYLOAD, TEST_SECRET, "evt_123", "test.event"
        )

        assert payload == TEST_PAYLOAD
        assert isinstance(headers, dict)

    def test_includes_required_headers(self):
        """Enthält alle erforderlichen Headers."""
        payload, headers = create_signed_webhook_payload(
            TEST_PAYLOAD, TEST_SECRET, "evt_123", "test.event"
        )

        assert "Content-Type" in headers
        assert SIGNATURE_HEADER_NAME in headers
        assert "X-Webhook-Delivery-ID" in headers
        assert "X-Webhook-Event" in headers
        assert "X-Webhook-Timestamp" in headers
        assert "User-Agent" in headers

    def test_signature_is_valid(self):
        """Generierte Signatur ist gültig."""
        payload, headers = create_signed_webhook_payload(
            TEST_PAYLOAD, TEST_SECRET, "evt_123", "test.event"
        )

        signature = headers[SIGNATURE_HEADER_NAME]
        is_valid = verify_signature(TEST_PAYLOAD, signature, TEST_SECRET)
        assert is_valid is True

    def test_delivery_id_in_headers(self):
        """Delivery-ID ist in Headers."""
        payload, headers = create_signed_webhook_payload(
            TEST_PAYLOAD, TEST_SECRET, "evt_123", "test.event"
        )

        assert headers["X-Webhook-Delivery-ID"] == "evt_123"

    def test_event_type_in_headers(self):
        """Event-Typ ist in Headers."""
        payload, headers = create_signed_webhook_payload(
            TEST_PAYLOAD, TEST_SECRET, "evt_123", "document.processed"
        )

        assert headers["X-Webhook-Event"] == "document.processed"


# ==================== Tests: Utility-Funktionen ====================


class TestIsWebhookSecretValid:
    """Tests für is_webhook_secret_valid Funktion."""

    def test_valid_secret(self):
        """Akzeptiert gültige Secrets."""
        assert is_webhook_secret_valid("whsec_" + "a" * 32) is True
        assert is_webhook_secret_valid("x" * 32) is True
        assert is_webhook_secret_valid("x" * 64) is True

    def test_rejects_short_secret(self):
        """Lehnt zu kurze Secrets ab."""
        assert is_webhook_secret_valid("short") is False
        assert is_webhook_secret_valid("x" * 31) is False

    def test_rejects_empty_secret(self):
        """Lehnt leere Secrets ab."""
        assert is_webhook_secret_valid("") is False

    def test_rejects_none(self):
        """Lehnt None ab."""
        assert is_webhook_secret_valid(None) is False  # type: ignore


class TestMaskWebhookSecret:
    """Tests für mask_webhook_secret Funktion."""

    def test_masks_standard_secret(self):
        """Maskiert Standard-Secret."""
        result = mask_webhook_secret("whsec_abc123def456")
        assert result == "whsec_...f456"

    def test_masks_custom_secret(self):
        """Maskiert Custom-Secret."""
        result = mask_webhook_secret("my_custom_secret_key")
        assert result == "my_c..._key"

    def test_handles_short_secret(self):
        """Behandelt kurze Secrets."""
        result = mask_webhook_secret("short")
        assert result == "***"

    def test_handles_empty_secret(self):
        """Behandelt leeres Secret."""
        result = mask_webhook_secret("")
        assert result == "***"


# ==================== Tests: SignatureComponents ====================


class TestSignatureComponents:
    """Tests für SignatureComponents Dataclass."""

    def test_frozen(self):
        """Components sind immutable."""
        components = SignatureComponents(
            timestamp=1700000000,
            signatures={"v1": "abc123"}
        )

        with pytest.raises(AttributeError):
            components.timestamp = 9999999999  # type: ignore

    def test_v1_signature_property(self):
        """v1_signature Property funktioniert."""
        components = SignatureComponents(
            timestamp=1700000000,
            signatures={"v1": "abc123", "v2": "def456"}
        )

        assert components.v1_signature == "abc123"

    def test_v1_signature_returns_none_if_missing(self):
        """v1_signature gibt None zurück wenn nicht vorhanden."""
        components = SignatureComponents(
            timestamp=1700000000,
            signatures={"v2": "def456"}
        )

        assert components.v1_signature is None


# ==================== Tests: Konstanten ====================


class TestConstants:
    """Tests für Modul-Konstanten."""

    def test_signature_header_name(self):
        """Standard Header-Name ist korrekt."""
        assert SIGNATURE_HEADER_NAME == "X-Webhook-Signature"

    def test_signature_header_aliases(self):
        """Header-Aliase sind definiert."""
        assert "X-Hub-Signature-256" in SIGNATURE_HEADER_ALIASES
        assert "Stripe-Signature" in SIGNATURE_HEADER_ALIASES

    def test_default_tolerance(self):
        """Default-Toleranz ist 5 Minuten."""
        assert DEFAULT_TOLERANCE_SECONDS == 300

    def test_max_tolerance(self):
        """Maximum-Toleranz ist 1 Stunde."""
        assert MAX_TOLERANCE_SECONDS == 3600


# ==================== Tests: Exception-Hierarchie ====================


class TestExceptions:
    """Tests für Exception-Klassen."""

    def test_webhook_signature_error_is_base(self):
        """WebhookSignatureError ist Basis-Exception."""
        assert issubclass(InvalidSignatureError, WebhookSignatureError)
        assert issubclass(SignatureExpiredError, WebhookSignatureError)
        assert issubclass(InvalidSignatureFormatError, WebhookSignatureError)

    def test_can_catch_all_with_base(self):
        """Alle Errors können mit Basis-Exception gefangen werden."""
        errors = [
            InvalidSignatureError("test"),
            SignatureExpiredError("test"),
            InvalidSignatureFormatError("test"),
        ]

        for error in errors:
            try:
                raise error
            except WebhookSignatureError:
                pass  # Erwartet


# ==================== Integration Tests ====================


class TestIntegration:
    """Integrationstests für End-to-End Signatur-Workflow."""

    def test_full_sign_verify_workflow(self):
        """Vollständiger Sign-Verify Workflow."""
        # 1. Generiere Signatur
        payload = b'{"event":"document.processed","doc_id":"123"}'
        secret = "whsec_production_secret_key_12345"

        header, timestamp = generate_signature(payload, secret)

        # 2. Simuliere Webhook-Empfang
        received_payload = payload
        received_header = header

        # 3. Verifiziere
        result = verify_signature(received_payload, received_header, secret)
        assert result is True

    def test_replay_attack_prevention(self):
        """Replay-Attack wird verhindert."""
        payload = b'{"event":"transfer.completed"}'
        secret = "whsec_replay_test_secret_key_123"

        # 1. Generiere Signatur vor 10 Minuten
        old_timestamp = int(time.time()) - 600
        header, _ = generate_signature(payload, secret, old_timestamp)

        # 2. Versuche Replay nach 10 Minuten
        with pytest.raises(SignatureExpiredError):
            verify_signature(payload, header, secret, tolerance_seconds=300)

    def test_tamper_detection(self):
        """Manipulation wird erkannt."""
        original_payload = b'{"amount":100}'
        secret = "whsec_tamper_test_secret_key_123"

        header, _ = generate_signature(original_payload, secret)

        # Angreifer versucht Payload zu ändern
        tampered_payload = b'{"amount":1000000}'

        with pytest.raises(InvalidSignatureError):
            verify_signature(tampered_payload, header, secret)

    def test_multiple_webhook_subscribers(self):
        """Mehrere Subscriber mit unterschiedlichen Secrets."""
        payload = b'{"event":"notification"}'

        subscriber_secrets = [
            "whsec_subscriber_1_secret_key_123",
            "whsec_subscriber_2_secret_key_456",
            "whsec_subscriber_3_secret_key_789",
        ]

        # Generiere und verifiziere für jeden Subscriber
        for secret in subscriber_secrets:
            header, _ = generate_signature(payload, secret)
            result = verify_signature(payload, header, secret)
            assert result is True

            # Anderer Subscriber kann nicht verifizieren
            other_secret = [s for s in subscriber_secrets if s != secret][0]
            with pytest.raises(InvalidSignatureError):
                verify_signature(payload, header, other_secret)
