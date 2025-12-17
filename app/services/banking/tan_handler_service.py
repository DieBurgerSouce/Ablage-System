# -*- coding: utf-8 -*-
"""TAN Handler Service.

Verwaltet TAN-Challenges und -Verifikation fuer SEPA-Zahlungen.

Unterstuetzte TAN-Verfahren:
- pushTAN (App-basiert)
- photoTAN (QR-Code)
- chipTAN (Karte + Leser)
- smsTAN (SMS)

Sicherheitsfeatures:
- Challenge-Timeout (5 Minuten)
- Max. 3 Versuche
- Rate-Limiting
- Audit-Logging
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, Any, List
from uuid import UUID, uuid4
import hashlib
import hmac
import secrets
import base64
import structlog

logger = structlog.get_logger(__name__)


class TANMethod(str, Enum):
    """TAN-Verfahren."""
    PUSH_TAN = "pushTAN"
    PHOTO_TAN = "photoTAN"
    CHIP_TAN = "chipTAN"
    SMS_TAN = "smsTAN"
    APP_TAN = "appTAN"


class ChallengeStatus(str, Enum):
    """Challenge-Status."""
    PENDING = "pending"
    VERIFIED = "verified"
    EXPIRED = "expired"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TANChallenge:
    """TAN-Challenge Daten."""
    challenge_id: str
    payment_id: UUID
    user_id: UUID
    method: TANMethod
    challenge_data: Optional[str]  # Base64-kodierte Daten (z.B. QR-Code)
    challenge_text: Optional[str]  # Menschenlesbare Challenge
    flicker_code: Optional[str]  # Fuer chipTAN
    status: ChallengeStatus
    created_at: datetime
    expires_at: datetime
    attempts: int = 0
    max_attempts: int = 3
    verified_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TANVerificationResult:
    """Ergebnis der TAN-Verifikation."""
    success: bool
    challenge_id: str
    message: str
    remaining_attempts: Optional[int] = None
    locked: bool = False


class TANHandlerService:
    """Service fuer TAN-Challenge und -Verifikation."""

    # Konfiguration
    CHALLENGE_TIMEOUT_MINUTES = 5
    MAX_ATTEMPTS = 3
    RATE_LIMIT_WINDOW = 300  # 5 Minuten
    RATE_LIMIT_MAX = 10  # Max. Challenges pro Fenster

    # SECURITY: TAN-Verifikations Rate Limiting
    TAN_VERIFY_RATE_LIMIT_WINDOW = 60  # 1 Minute
    TAN_VERIFY_RATE_LIMIT_MAX = 5  # Max. 5 TAN-Versuche pro Minute

    # SECURITY: User-Level Lockout nach zu vielen fehlgeschlagenen Challenges
    USER_LOCKOUT_THRESHOLD = 3  # Nach 3 fehlgeschlagenen Challenges
    USER_LOCKOUT_DURATION = 3600  # 1 Stunde Lockout

    # In-Memory Store (in Produktion: Redis)
    _challenges: Dict[str, TANChallenge] = {}
    _rate_limits: Dict[str, List[datetime]] = {}
    _tan_verify_attempts: Dict[str, List[datetime]] = {}  # TAN-Verifikations-Versuche
    _user_lockouts: Dict[str, datetime] = {}  # User-Lockouts
    _failed_challenges: Dict[str, int] = {}  # Fehlgeschlagene Challenges pro User

    def __init__(self, secret_key: Optional[str] = None):
        """Initialisiere TAN-Handler.

        Args:
            secret_key: Geheimer Schluessel fuer Challenge-Signierung
        """
        self._secret_key = secret_key or secrets.token_hex(32)

    def create_challenge(
        self,
        payment_id: UUID,
        user_id: UUID,
        method: TANMethod = TANMethod.PUSH_TAN,
        amount: Optional[float] = None,
        creditor: Optional[str] = None,
        iban: Optional[str] = None,
    ) -> TANChallenge:
        """Erstelle neue TAN-Challenge.

        Args:
            payment_id: Zahlungs-ID
            user_id: Benutzer-ID
            method: TAN-Verfahren
            amount: Betrag (fuer Challenge-Text)
            creditor: Empfaenger (fuer Challenge-Text)
            iban: IBAN (fuer Challenge-Text)

        Returns:
            TANChallenge
        """
        # Rate-Limiting pruefen
        if not self._check_rate_limit(user_id):
            raise ValueError("Zu viele TAN-Anfragen. Bitte warten Sie einige Minuten.")

        challenge_id = self._generate_challenge_id()
        now = datetime.utcnow()
        expires_at = now + timedelta(minutes=self.CHALLENGE_TIMEOUT_MINUTES)

        # Challenge-Text generieren
        challenge_text = self._generate_challenge_text(amount, creditor, iban)

        # Challenge-Daten je nach Methode
        challenge_data = None
        flicker_code = None

        if method == TANMethod.PHOTO_TAN:
            challenge_data = self._generate_photo_tan_data(payment_id, amount, iban)
        elif method == TANMethod.CHIP_TAN:
            flicker_code = self._generate_flicker_code(payment_id, amount, iban)

        challenge = TANChallenge(
            challenge_id=challenge_id,
            payment_id=payment_id,
            user_id=user_id,
            method=method,
            challenge_data=challenge_data,
            challenge_text=challenge_text,
            flicker_code=flicker_code,
            status=ChallengeStatus.PENDING,
            created_at=now,
            expires_at=expires_at,
            metadata={
                "amount": amount,
                "creditor": creditor,
                "iban": iban,
            },
        )

        # Speichere Challenge
        self._challenges[challenge_id] = challenge

        logger.info(
            "tan_challenge_created",
            challenge_id=challenge_id,
            payment_id=str(payment_id),
            method=method.value,
            expires_at=expires_at.isoformat(),
        )

        return challenge

    def verify_tan(
        self,
        challenge_id: str,
        tan: str,
        user_id: UUID,
    ) -> TANVerificationResult:
        """Verifiziere TAN.

        Args:
            challenge_id: Challenge-ID
            tan: Eingegebene TAN
            user_id: Benutzer-ID

        Returns:
            TANVerificationResult
        """
        user_key = str(user_id)

        # SECURITY: User-Lockout pruefen
        if self._is_user_locked(user_id):
            logger.warning(
                "tan_verification_blocked",
                user_id=user_key,
                reason="user_locked_out",
            )
            return TANVerificationResult(
                success=False,
                challenge_id=challenge_id,
                message="Konto temporaer gesperrt. Bitte versuchen Sie es spaeter erneut.",
                locked=True,
            )

        # SECURITY: TAN-Verifikations Rate Limiting
        if not self._check_tan_verify_rate_limit(user_id):
            logger.warning(
                "tan_verification_rate_limited",
                user_id=user_key,
                challenge_id=challenge_id,
            )
            return TANVerificationResult(
                success=False,
                challenge_id=challenge_id,
                message="Zu viele Versuche. Bitte warten Sie einen Moment.",
            )

        # Challenge holen
        challenge = self._challenges.get(challenge_id)

        if not challenge:
            logger.warning(
                "tan_verification_failed",
                challenge_id=challenge_id,
                reason="challenge_not_found",
            )
            return TANVerificationResult(
                success=False,
                challenge_id=challenge_id,
                message="Challenge nicht gefunden",
            )

        # User-Zugehoerigkeit pruefen
        if challenge.user_id != user_id:
            logger.warning(
                "tan_verification_failed",
                challenge_id=challenge_id,
                reason="user_mismatch",
            )
            return TANVerificationResult(
                success=False,
                challenge_id=challenge_id,
                message="Zugriff verweigert",
            )

        # Status pruefen
        if challenge.status != ChallengeStatus.PENDING:
            return TANVerificationResult(
                success=False,
                challenge_id=challenge_id,
                message=f"Challenge-Status: {challenge.status.value}",
            )

        # Ablauf pruefen
        if datetime.utcnow() > challenge.expires_at:
            challenge.status = ChallengeStatus.EXPIRED
            logger.info(
                "tan_challenge_expired",
                challenge_id=challenge_id,
            )
            return TANVerificationResult(
                success=False,
                challenge_id=challenge_id,
                message="Challenge abgelaufen",
            )

        # Versuch zaehlen
        challenge.attempts += 1

        # TAN validieren
        if not self._validate_tan(challenge, tan):
            remaining = challenge.max_attempts - challenge.attempts

            if remaining <= 0:
                challenge.status = ChallengeStatus.FAILED

                # SECURITY: User-Level Lockout Tracking
                self._increment_failed_challenges(user_id)
                is_locked = self._check_and_lock_user_if_needed(user_id)

                logger.warning(
                    "tan_challenge_locked",
                    challenge_id=challenge_id,
                    payment_id=str(challenge.payment_id),
                    user_locked=is_locked,
                )
                return TANVerificationResult(
                    success=False,
                    challenge_id=challenge_id,
                    message="Maximale Versuche ueberschritten. Konto wird temporaer gesperrt." if is_locked else "Maximale Versuche ueberschritten",
                    remaining_attempts=0,
                    locked=is_locked,
                )

            logger.info(
                "tan_verification_failed",
                challenge_id=challenge_id,
                attempts=challenge.attempts,
                remaining=remaining,
            )
            return TANVerificationResult(
                success=False,
                challenge_id=challenge_id,
                message="Ungueltige TAN",
                remaining_attempts=remaining,
            )

        # Erfolgreiche Verifikation
        challenge.status = ChallengeStatus.VERIFIED
        challenge.verified_at = datetime.utcnow()

        logger.info(
            "tan_verification_success",
            challenge_id=challenge_id,
            payment_id=str(challenge.payment_id),
        )

        return TANVerificationResult(
            success=True,
            challenge_id=challenge_id,
            message="TAN erfolgreich verifiziert",
        )

    def cancel_challenge(
        self,
        challenge_id: str,
        user_id: UUID,
    ) -> bool:
        """Storniere Challenge.

        Args:
            challenge_id: Challenge-ID
            user_id: Benutzer-ID

        Returns:
            True wenn erfolgreich
        """
        challenge = self._challenges.get(challenge_id)

        if not challenge:
            return False

        if challenge.user_id != user_id:
            return False

        if challenge.status != ChallengeStatus.PENDING:
            return False

        challenge.status = ChallengeStatus.CANCELLED

        logger.info(
            "tan_challenge_cancelled",
            challenge_id=challenge_id,
        )

        return True

    def get_challenge(
        self,
        challenge_id: str,
        user_id: UUID,
    ) -> Optional[TANChallenge]:
        """Hole Challenge-Status.

        Args:
            challenge_id: Challenge-ID
            user_id: Benutzer-ID

        Returns:
            TANChallenge oder None
        """
        challenge = self._challenges.get(challenge_id)

        if not challenge:
            return None

        if challenge.user_id != user_id:
            return None

        # Pruefe Ablauf
        if challenge.status == ChallengeStatus.PENDING:
            if datetime.utcnow() > challenge.expires_at:
                challenge.status = ChallengeStatus.EXPIRED

        return challenge

    def get_available_methods(self, user_id: UUID) -> List[Dict[str, Any]]:
        """Hole verfuegbare TAN-Verfahren fuer User.

        In Produktion wuerde dies aus User-Einstellungen oder Bank-API kommen.

        Args:
            user_id: Benutzer-ID

        Returns:
            Liste von TAN-Verfahren
        """
        # Standard-Verfahren (in Produktion: aus DB/Bank-API)
        methods = [
            {
                "method": TANMethod.PUSH_TAN.value,
                "name": "pushTAN",
                "description": "TAN per Banking-App",
                "icon": "smartphone",
                "preferred": True,
            },
            {
                "method": TANMethod.PHOTO_TAN.value,
                "name": "photoTAN",
                "description": "QR-Code mit App scannen",
                "icon": "qr_code",
                "preferred": False,
            },
            {
                "method": TANMethod.SMS_TAN.value,
                "name": "smsTAN",
                "description": "TAN per SMS",
                "icon": "sms",
                "preferred": False,
            },
        ]

        return methods

    def cleanup_expired(self) -> int:
        """Bereinige abgelaufene Challenges.

        Returns:
            Anzahl bereinigter Challenges
        """
        now = datetime.utcnow()
        expired_ids = []

        for challenge_id, challenge in self._challenges.items():
            if challenge.expires_at < now - timedelta(hours=1):
                expired_ids.append(challenge_id)

        for challenge_id in expired_ids:
            del self._challenges[challenge_id]

        if expired_ids:
            logger.info(
                "tan_challenges_cleaned",
                count=len(expired_ids),
            )

        return len(expired_ids)

    # =========================================================================
    # Private Methoden
    # =========================================================================

    def _generate_challenge_id(self) -> str:
        """Generiere eindeutige Challenge-ID."""
        return f"TAN-{secrets.token_hex(16)}"

    def _generate_challenge_text(
        self,
        amount: Optional[float],
        creditor: Optional[str],
        iban: Optional[str],
    ) -> str:
        """Generiere menschenlesbaren Challenge-Text."""
        parts = ["Zahlung bestaetigen:"]

        if amount:
            parts.append(f"Betrag: {amount:.2f} EUR")
        if creditor:
            parts.append(f"Empfaenger: {creditor}")
        if iban:
            # IBAN maskieren
            masked_iban = f"{iban[:4]}...{iban[-4:]}"
            parts.append(f"IBAN: {masked_iban}")

        return " | ".join(parts)

    def _generate_photo_tan_data(
        self,
        payment_id: UUID,
        amount: Optional[float],
        iban: Optional[str],
    ) -> str:
        """Generiere photoTAN-Daten (Base64-kodiert).

        In Produktion wuerde hier ein echtes QR-Code-Bild generiert.
        """
        # Simulierte Daten
        data = {
            "type": "photoTAN",
            "payment_id": str(payment_id),
            "amount": amount,
            "iban": iban,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # In Produktion: QR-Code generieren
        import json
        json_data = json.dumps(data)
        return base64.b64encode(json_data.encode()).decode()

    def _generate_flicker_code(
        self,
        payment_id: UUID,
        amount: Optional[float],
        iban: Optional[str],
    ) -> str:
        """Generiere chipTAN Flicker-Code.

        In Produktion wuerde hier ein echter Flicker-Code generiert.
        """
        # Simulierter Flicker-Code (HHD 1.4 Format)
        # Format: Start + Daten + Ende
        return f"11{str(payment_id)[:8]}0E"

    def _validate_tan(self, challenge: TANChallenge, tan: str) -> bool:
        """Validiere TAN gegen Challenge.

        In Produktion wuerde hier die Bank-API verwendet.

        Args:
            challenge: TAN-Challenge
            tan: Eingegebene TAN

        Returns:
            True wenn gueltig
        """
        # Einfache Validierung fuer Development
        # In Produktion: Bank-API oder HMAC-Verifikation

        # TAN-Format pruefen (6 Ziffern)
        if not tan or len(tan) != 6:
            return False

        if not tan.isdigit():
            return False

        # SECURITY: Development-only bypass - NUR wenn explizit aktiviert!
        # In Production MUSS TAN_DEV_BYPASS_ENABLED=false sein
        import os
        dev_bypass_enabled = os.environ.get("TAN_DEV_BYPASS_ENABLED", "false").lower() == "true"
        if dev_bypass_enabled and tan == "123456":
            logger.warning(
                "tan_dev_bypass_used",
                challenge_id=challenge.challenge_id,
                WARNING="Development-Bypass aktiv! NICHT FUER PRODUKTION!",
            )
            return True

        # HMAC-basierte Validierung (simuliert)
        expected_tan = self._compute_expected_tan(challenge)
        return hmac.compare_digest(tan, expected_tan)

    def _compute_expected_tan(self, challenge: TANChallenge) -> str:
        """Berechne erwartete TAN (fuer Simulation).

        In Produktion: Bank-seitige Generierung.
        """
        # Einfache HMAC-basierte TAN
        data = f"{challenge.challenge_id}:{challenge.payment_id}:{challenge.created_at.isoformat()}"
        h = hmac.new(
            self._secret_key.encode(),
            data.encode(),
            hashlib.sha256
        )
        # Nehme 6 Ziffern aus dem Hash
        return str(int(h.hexdigest()[:8], 16) % 1000000).zfill(6)

    def _check_rate_limit(self, user_id: UUID) -> bool:
        """Pruefe Rate-Limit.

        Args:
            user_id: Benutzer-ID

        Returns:
            True wenn erlaubt
        """
        user_key = str(user_id)
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=self.RATE_LIMIT_WINDOW)

        # Hole bisherige Requests
        requests = self._rate_limits.get(user_key, [])

        # Entferne alte Requests
        requests = [r for r in requests if r > window_start]

        # Pruefe Limit
        if len(requests) >= self.RATE_LIMIT_MAX:
            return False

        # Fuege neuen Request hinzu
        requests.append(now)
        self._rate_limits[user_key] = requests

        return True

    def _check_tan_verify_rate_limit(self, user_id: UUID) -> bool:
        """Pruefe Rate-Limit fuer TAN-Verifikation.

        Verhindert Brute-Force-Angriffe durch Limitierung der
        Verifikationsversuche pro Zeitfenster.

        Args:
            user_id: Benutzer-ID

        Returns:
            True wenn erlaubt
        """
        user_key = str(user_id)
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=self.TAN_VERIFY_RATE_LIMIT_WINDOW)

        # Hole bisherige Versuche
        attempts = self._tan_verify_attempts.get(user_key, [])

        # Entferne alte Versuche
        attempts = [a for a in attempts if a > window_start]

        # Pruefe Limit
        if len(attempts) >= self.TAN_VERIFY_RATE_LIMIT_MAX:
            return False

        # Fuege neuen Versuch hinzu
        attempts.append(now)
        self._tan_verify_attempts[user_key] = attempts

        return True

    def _is_user_locked(self, user_id: UUID) -> bool:
        """Pruefe ob User gesperrt ist.

        Args:
            user_id: Benutzer-ID

        Returns:
            True wenn gesperrt
        """
        user_key = str(user_id)
        lockout_time = self._user_lockouts.get(user_key)

        if not lockout_time:
            return False

        # Pruefe ob Lockout abgelaufen
        if datetime.utcnow() > lockout_time + timedelta(seconds=self.USER_LOCKOUT_DURATION):
            # Lockout aufheben
            del self._user_lockouts[user_key]
            self._failed_challenges[user_key] = 0
            return False

        return True

    def _increment_failed_challenges(self, user_id: UUID) -> None:
        """Erhoehe Zaehler fuer fehlgeschlagene Challenges.

        Args:
            user_id: Benutzer-ID
        """
        user_key = str(user_id)
        current = self._failed_challenges.get(user_key, 0)
        self._failed_challenges[user_key] = current + 1

    def _check_and_lock_user_if_needed(self, user_id: UUID) -> bool:
        """Pruefe und sperre User bei zu vielen Fehlversuchen.

        Args:
            user_id: Benutzer-ID

        Returns:
            True wenn User gesperrt wurde
        """
        user_key = str(user_id)
        failed_count = self._failed_challenges.get(user_key, 0)

        if failed_count >= self.USER_LOCKOUT_THRESHOLD:
            self._user_lockouts[user_key] = datetime.utcnow()
            logger.warning(
                "user_tan_lockout",
                user_id=user_key,
                failed_challenges=failed_count,
                lockout_duration_seconds=self.USER_LOCKOUT_DURATION,
            )
            return True

        return False


# Singleton-Instanz
tan_handler = TANHandlerService()
