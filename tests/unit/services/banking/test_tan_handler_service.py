# -*- coding: utf-8 -*-
"""
Tests fuer TANHandlerService.

Testet:
- Challenge-Erstellung
- TAN-Verifikation
- Timeout-Handling
- Rate-Limiting
- Challenge-Stornierung
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from unittest.mock import patch

from app.services.banking.tan_handler_service import (
    TANHandlerService,
    TANMethod,
    ChallengeStatus,
    TANChallenge,
    TANVerificationResult,
)


class TestChallengeCreation:
    """Tests fuer Challenge-Erstellung."""

    @pytest.fixture
    def service(self) -> TANHandlerService:
        return TANHandlerService(secret_key="test_secret_key_12345")

    def test_create_challenge_push_tan(self, service: TANHandlerService):
        """Sollte pushTAN-Challenge erstellen."""
        payment_id = uuid4()
        user_id = uuid4()

        challenge = service.create_challenge(
            payment_id=payment_id,
            user_id=user_id,
            method=TANMethod.PUSH_TAN,
            amount=100.00,
            creditor="Test GmbH",
        )

        assert challenge.payment_id == payment_id
        assert challenge.user_id == user_id
        assert challenge.method == TANMethod.PUSH_TAN
        assert challenge.status == ChallengeStatus.PENDING
        assert challenge.attempts == 0
        assert challenge.max_attempts == 3

    def test_create_challenge_photo_tan(self, service: TANHandlerService):
        """Sollte photoTAN-Challenge mit Daten erstellen."""
        payment_id = uuid4()
        user_id = uuid4()

        challenge = service.create_challenge(
            payment_id=payment_id,
            user_id=user_id,
            method=TANMethod.PHOTO_TAN,
            amount=500.00,
            iban="DE89370400440532013000",
        )

        assert challenge.method == TANMethod.PHOTO_TAN
        assert challenge.challenge_data is not None  # Base64-kodierte Daten

    def test_create_challenge_chip_tan(self, service: TANHandlerService):
        """Sollte chipTAN-Challenge mit Flicker-Code erstellen."""
        payment_id = uuid4()
        user_id = uuid4()

        challenge = service.create_challenge(
            payment_id=payment_id,
            user_id=user_id,
            method=TANMethod.CHIP_TAN,
            amount=1000.00,
        )

        assert challenge.method == TANMethod.CHIP_TAN
        assert challenge.flicker_code is not None

    def test_create_challenge_text_generated(self, service: TANHandlerService):
        """Sollte Challenge-Text generieren."""
        challenge = service.create_challenge(
            payment_id=uuid4(),
            user_id=uuid4(),
            method=TANMethod.PUSH_TAN,
            amount=123.45,
            creditor="Muster AG",
            iban="DE89370400440532013000",
        )

        assert "123.45" in challenge.challenge_text
        assert "Muster AG" in challenge.challenge_text
        # IBAN sollte maskiert sein
        assert "DE89" in challenge.challenge_text
        assert "...3000" in challenge.challenge_text or "0000" in challenge.challenge_text

    def test_create_challenge_expiry(self, service: TANHandlerService):
        """Sollte Challenge mit korrektem Ablauf erstellen."""
        challenge = service.create_challenge(
            payment_id=uuid4(),
            user_id=uuid4(),
            method=TANMethod.PUSH_TAN,
        )

        # Ablauf sollte ~5 Minuten in der Zukunft sein
        now = datetime.utcnow()
        assert challenge.expires_at > now
        assert challenge.expires_at < now + timedelta(minutes=10)


class TestChallengeID:
    """Tests fuer Challenge-ID-Generierung."""

    @pytest.fixture
    def service(self) -> TANHandlerService:
        return TANHandlerService()

    def test_challenge_id_format(self, service: TANHandlerService):
        """Sollte korrektes Format haben."""
        challenge_id = service._generate_challenge_id()

        assert challenge_id.startswith("TAN-")
        assert len(challenge_id) > 10

    def test_challenge_id_unique(self, service: TANHandlerService):
        """Sollte eindeutige IDs generieren."""
        ids = [service._generate_challenge_id() for _ in range(100)]
        assert len(ids) == len(set(ids))


class TestTANVerification:
    """Tests fuer TAN-Verifikation."""

    @pytest.fixture
    def service(self) -> TANHandlerService:
        return TANHandlerService(secret_key="test_secret_key")

    def test_verify_tan_success(self, service: TANHandlerService):
        """Sollte gueltige TAN akzeptieren."""
        user_id = uuid4()
        challenge = service.create_challenge(
            payment_id=uuid4(),
            user_id=user_id,
            method=TANMethod.PUSH_TAN,
        )

        # Development: "123456" wird immer akzeptiert
        result = service.verify_tan(challenge.challenge_id, "123456", user_id)

        assert result.success
        assert result.message == "TAN erfolgreich verifiziert"

    def test_verify_tan_wrong_tan(self, service: TANHandlerService):
        """Sollte falsche TAN ablehnen."""
        user_id = uuid4()
        challenge = service.create_challenge(
            payment_id=uuid4(),
            user_id=user_id,
            method=TANMethod.PUSH_TAN,
        )

        result = service.verify_tan(challenge.challenge_id, "999999", user_id)

        assert not result.success
        assert result.remaining_attempts is not None
        assert result.remaining_attempts > 0

    def test_verify_tan_invalid_format(self, service: TANHandlerService):
        """Sollte ungueltige TAN ablehnen."""
        user_id = uuid4()
        challenge = service.create_challenge(
            payment_id=uuid4(),
            user_id=user_id,
            method=TANMethod.PUSH_TAN,
        )

        result = service.verify_tan(challenge.challenge_id, "12345", user_id)

        assert not result.success

    def test_verify_tan_max_attempts(self, service: TANHandlerService):
        """Sollte nach 3 Versuchen sperren."""
        user_id = uuid4()
        challenge = service.create_challenge(
            payment_id=uuid4(),
            user_id=user_id,
            method=TANMethod.PUSH_TAN,
        )

        # 3 falsche Versuche
        for i in range(3):
            result = service.verify_tan(challenge.challenge_id, "999999", user_id)

        assert not result.success
        assert result.locked
        assert result.remaining_attempts == 0

    def test_verify_tan_challenge_not_found(self, service: TANHandlerService):
        """Sollte Fehler bei unbekannter Challenge zurueckgeben."""
        result = service.verify_tan("TAN-unknown", "123456", uuid4())

        assert not result.success
        assert "nicht gefunden" in result.message

    def test_verify_tan_wrong_user(self, service: TANHandlerService):
        """Sollte Fehler bei falschem User zurueckgeben."""
        user_id = uuid4()
        other_user_id = uuid4()

        challenge = service.create_challenge(
            payment_id=uuid4(),
            user_id=user_id,
            method=TANMethod.PUSH_TAN,
        )

        result = service.verify_tan(challenge.challenge_id, "123456", other_user_id)

        assert not result.success
        assert "verweigert" in result.message

    def test_verify_tan_expired_challenge(self, service: TANHandlerService):
        """Sollte abgelaufene Challenge ablehnen."""
        user_id = uuid4()
        challenge = service.create_challenge(
            payment_id=uuid4(),
            user_id=user_id,
            method=TANMethod.PUSH_TAN,
        )

        # Setze Ablaufzeit in die Vergangenheit
        challenge.expires_at = datetime.utcnow() - timedelta(minutes=1)

        result = service.verify_tan(challenge.challenge_id, "123456", user_id)

        assert not result.success
        assert "abgelaufen" in result.message


class TestChallengeStatus:
    """Tests fuer Challenge-Status."""

    @pytest.fixture
    def service(self) -> TANHandlerService:
        return TANHandlerService()

    def test_challenge_status_after_verification(self, service: TANHandlerService):
        """Sollte Status nach Verifikation aendern."""
        user_id = uuid4()
        challenge = service.create_challenge(
            payment_id=uuid4(),
            user_id=user_id,
            method=TANMethod.PUSH_TAN,
        )

        assert challenge.status == ChallengeStatus.PENDING

        service.verify_tan(challenge.challenge_id, "123456", user_id)

        # Hole aktualisierte Challenge
        updated = service.get_challenge(challenge.challenge_id, user_id)
        assert updated.status == ChallengeStatus.VERIFIED

    def test_challenge_status_after_failure(self, service: TANHandlerService):
        """Sollte Status nach 3 Fehlversuchen aendern."""
        user_id = uuid4()
        challenge = service.create_challenge(
            payment_id=uuid4(),
            user_id=user_id,
            method=TANMethod.PUSH_TAN,
        )

        for _ in range(3):
            service.verify_tan(challenge.challenge_id, "999999", user_id)

        updated = service.get_challenge(challenge.challenge_id, user_id)
        assert updated.status == ChallengeStatus.FAILED


class TestChallengeCancellation:
    """Tests fuer Challenge-Stornierung."""

    @pytest.fixture
    def service(self) -> TANHandlerService:
        return TANHandlerService()

    def test_cancel_challenge_success(self, service: TANHandlerService):
        """Sollte Challenge erfolgreich stornieren."""
        user_id = uuid4()
        challenge = service.create_challenge(
            payment_id=uuid4(),
            user_id=user_id,
            method=TANMethod.PUSH_TAN,
        )

        result = service.cancel_challenge(challenge.challenge_id, user_id)

        assert result is True

        updated = service.get_challenge(challenge.challenge_id, user_id)
        assert updated.status == ChallengeStatus.CANCELLED

    def test_cancel_challenge_wrong_user(self, service: TANHandlerService):
        """Sollte Stornierung durch falschen User ablehnen."""
        user_id = uuid4()
        other_user_id = uuid4()

        challenge = service.create_challenge(
            payment_id=uuid4(),
            user_id=user_id,
            method=TANMethod.PUSH_TAN,
        )

        result = service.cancel_challenge(challenge.challenge_id, other_user_id)

        assert result is False

    def test_cancel_challenge_already_verified(self, service: TANHandlerService):
        """Sollte Stornierung nach Verifikation ablehnen."""
        user_id = uuid4()
        challenge = service.create_challenge(
            payment_id=uuid4(),
            user_id=user_id,
            method=TANMethod.PUSH_TAN,
        )

        service.verify_tan(challenge.challenge_id, "123456", user_id)

        result = service.cancel_challenge(challenge.challenge_id, user_id)

        assert result is False


class TestAvailableMethods:
    """Tests fuer TAN-Verfahren-Abfrage."""

    @pytest.fixture
    def service(self) -> TANHandlerService:
        return TANHandlerService()

    def test_get_available_methods(self, service: TANHandlerService):
        """Sollte verfuegbare Methoden zurueckgeben."""
        user_id = uuid4()
        methods = service.get_available_methods(user_id)

        assert len(methods) > 0
        assert any(m["method"] == TANMethod.PUSH_TAN.value for m in methods)

    def test_methods_have_required_fields(self, service: TANHandlerService):
        """Sollte alle erforderlichen Felder enthalten."""
        methods = service.get_available_methods(uuid4())

        for method in methods:
            assert "method" in method
            assert "name" in method
            assert "description" in method


class TestCleanup:
    """Tests fuer Challenge-Bereinigung."""

    @pytest.fixture
    def service(self) -> TANHandlerService:
        return TANHandlerService()

    def test_cleanup_expired_challenges(self, service: TANHandlerService):
        """Sollte abgelaufene Challenges bereinigen."""
        user_id = uuid4()

        # Erstelle Challenge und setze Ablauf in Vergangenheit
        challenge = service.create_challenge(
            payment_id=uuid4(),
            user_id=user_id,
            method=TANMethod.PUSH_TAN,
        )
        challenge.expires_at = datetime.utcnow() - timedelta(hours=2)

        count = service.cleanup_expired()

        # Sollte mindestens eine Challenge bereinigt haben
        assert count >= 1
