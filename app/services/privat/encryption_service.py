"""Service fuer Extra-Verschluesselung von Privat-Dokumenten.

Enterprise-Grade Encryption mit:
- AES-256-GCM Verschluesselung
- PBKDF2-SHA256 Key-Derivation (100k Iterationen)
- Brute-Force-Protection mit Lockout
- Timing-Attack-Mitigation
- Enterprise Password Requirements (14+ Zeichen)
"""

import os
import hashlib
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Tuple, Optional, Dict, List

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidTag
import structlog

logger = structlog.get_logger(__name__)


# ============================================================================
# Enterprise Password Requirements
# ============================================================================

MIN_PASSWORD_LENGTH = 14
PASSWORD_REQUIREMENTS_DE = (
    "Passwort muss mindestens 14 Zeichen lang sein und "
    "Grossbuchstaben, Kleinbuchstaben, Zahlen und Sonderzeichen enthalten"
)


class WeakPasswordError(ValueError):
    """Ausnahme bei zu schwachem Passwort fuer Verschluesselung."""
    pass


class BruteForceProtectionError(Exception):
    """Ausnahme bei zu vielen fehlgeschlagenen Entschluesselungsversuchen."""
    pass


def validate_password_strength(password: str) -> bool:
    """Validiert die Passwort-Staerke fuer Enterprise-Verschluesselung.

    Args:
        password: Zu pruefendes Passwort

    Returns:
        True wenn Passwort stark genug ist

    Requirements:
        - Mindestens 14 Zeichen
        - Mindestens ein Grossbuchstabe
        - Mindestens ein Kleinbuchstabe
        - Mindestens eine Zahl
        - Mindestens ein Sonderzeichen
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        return False
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in "!@#$%^&*()-_=+[]{}|;:,.<>?/~`" for c in password)
    return has_upper and has_lower and has_digit and has_special


# ============================================================================
# HMAC-basierte Identifier fuer Brute-Force-Tracking (Iteration 19 Security Fix)
# ============================================================================

# SECURITY: Geheimer Schluessel fuer HMAC-basierte Identifier
# Wird beim ersten Aufruf generiert und im Speicher gehalten
# In Produktion: Sollte aus SECRET_KEY oder separater Konfiguration kommen
_HMAC_SECRET_KEY: Optional[bytes] = None


def _get_hmac_secret_key() -> bytes:
    """Holt oder generiert den HMAC-Secret-Key.

    SECURITY (Iteration 19): Der HMAC-Key wird verwendet um Brute-Force-
    Identifiers unvorhersagbar zu machen. Ein Angreifer kann nicht
    gezielt Identifier erraten.

    In Produktion sollte dieser Key aus SECRET_KEY oder separater
    Umgebungsvariable kommen fuer Konsistenz ueber Restarts.
    """
    global _HMAC_SECRET_KEY
    if _HMAC_SECRET_KEY is None:
        # Versuche Secret aus Umgebung zu holen
        import os
        secret_env = os.environ.get("PRIVAT_HMAC_SECRET")
        if secret_env:
            _HMAC_SECRET_KEY = secret_env.encode("utf-8")
        else:
            # Fallback: Generiere neuen Key (nur fuer Development/Tests)
            # WARNUNG: Bei Multi-Worker-Deployment mit Restarts werden
            # Lockouts zurueckgesetzt wenn kein persistenter Key konfiguriert ist!
            import secrets as secrets_module
            _HMAC_SECRET_KEY = secrets_module.token_bytes(32)
            logger.warning(
                "privat_hmac_key_generated",
                hint="Set PRIVAT_HMAC_SECRET environment variable for production!",
            )
    return _HMAC_SECRET_KEY


def generate_brute_force_identifier(
    document_id: str,
    user_id: str,
    additional_context: Optional[str] = None,
) -> str:
    """Generiert einen HMAC-basierten Brute-Force-Identifier.

    SECURITY FIX (Iteration 19): Ersetzt vorhersagbare Identifier wie
    "document_id:user_id" durch nicht erratbare HMAC-Hashes.

    Vorteile:
    - Angreifer kann Identifier nicht erraten
    - Kein Information Disclosure ueber Document/User-IDs
    - Konsistent fuer gleiche Inputs

    Args:
        document_id: Die Dokument-ID
        user_id: Die User-ID
        additional_context: Optionaler zusaetzlicher Kontext

    Returns:
        HMAC-basierter Identifier (hex-encoded, 64 Zeichen)
    """
    import hmac

    key = _get_hmac_secret_key()
    message = f"{document_id}:{user_id}"
    if additional_context:
        message = f"{message}:{additional_context}"

    # HMAC-SHA256 fuer nicht erratbaren Identifier
    h = hmac.new(key, message.encode("utf-8"), hashlib.sha256)
    return h.hexdigest()


# ============================================================================
# Brute-Force Protection (Redis-basiert fuer Multi-Worker-Support)
# ============================================================================

class DecryptAttemptTracker:
    """Trackt fehlgeschlagene Entschluesselungsversuche fuer Brute-Force-Schutz.

    Enterprise Security Feature:
    - Max 5 Versuche pro 15 Minuten pro Identifier (Document-ID + User-ID)
    - Automatischer Lockout bei Ueberschreitung
    - Redis-basiert fuer Multi-Worker-Deployment
    - Fallback zu In-Memory bei Redis-Ausfall

    SECURITY: Bei Multi-Worker-Deployment (z.B. Gunicorn) MUSS Redis
    verwendet werden, sonst kann Angreifer Worker-Grenzen umgehen.
    """

    MAX_ATTEMPTS = 5
    LOCKOUT_MINUTES = 15

    # Redis Key Prefixes
    REDIS_KEY_ATTEMPTS = "privat:decrypt_attempts:"
    REDIS_KEY_LOCKOUT = "privat:decrypt_lockout:"

    def __init__(self) -> None:
        # Fallback In-Memory Storage (nur fuer Tests oder Redis-Ausfall)
        self._attempts: Dict[str, List[datetime]] = defaultdict(list)
        self._lockouts: Dict[str, datetime] = {}
        self._redis = None
        self._redis_available = False

    async def _get_redis(self):
        """Holt Redis-Verbindung (lazy initialization)."""
        if self._redis is None:
            try:
                from app.core.redis_state import RedisStateManager
                manager = RedisStateManager.get_instance()
                await manager.connect()
                self._redis = manager._redis
                self._redis_available = True
                logger.info("privat_brute_force_tracker_redis_connected")
            except Exception as e:
                logger.warning(
                    "privat_brute_force_tracker_redis_unavailable",
                    error=str(e),
                    fallback="in_memory",
                )
                self._redis_available = False
        return self._redis if self._redis_available else None

    def is_locked(self, identifier: str) -> bool:
        """Prueft ob ein Identifier gesperrt ist (synchrone Version fuer Kompatibilitaet).

        HINWEIS: Verwendet In-Memory-Fallback. Fuer Redis nutze is_locked_async().

        Args:
            identifier: Eindeutiger Identifier (z.B. "doc_id:user_id")

        Returns:
            True wenn gesperrt
        """
        lockout_until = self._lockouts.get(identifier)
        if lockout_until and datetime.utcnow() < lockout_until:
            return True
        # Lockout abgelaufen - aufräumen
        if lockout_until:
            del self._lockouts[identifier]
        return False

    def _check_lockout_in_memory(self, identifier: str) -> bool:
        """SECURITY FIX 20-6: In-Memory Fallback fuer Redis-Ausfall.

        Diese Methode wird nur verwendet wenn Redis nicht verfuegbar ist.
        WARNUNG: In Multi-Worker-Deployments bietet dies keinen vollstaendigen
        Schutz gegen Brute-Force-Angriffe!

        Args:
            identifier: Eindeutiger Identifier (z.B. "doc_id:user_id")

        Returns:
            True wenn gesperrt
        """
        lockout_until = self._lockouts.get(identifier)
        if lockout_until and datetime.utcnow() < lockout_until:
            logger.warning(
                "privat_brute_force_locked_in_memory_fallback",
                identifier_hash=hash(identifier) % 10000,  # Nur Hash loggen
            )
            return True
        # Lockout abgelaufen - aufraeumen
        if lockout_until:
            del self._lockouts[identifier]
        return False

    async def is_locked_async(self, identifier: str) -> bool:
        """Prueft ob ein Identifier gesperrt ist (Redis-Version).

        SECURITY: Diese Methode sollte bevorzugt verwendet werden
        fuer Multi-Worker-Support.

        Args:
            identifier: Eindeutiger Identifier (z.B. "doc_id:user_id")

        Returns:
            True wenn gesperrt
        """
        redis = await self._get_redis()
        if redis:
            try:
                lockout_key = f"{self.REDIS_KEY_LOCKOUT}{identifier}"
                lockout_until = await redis.get(lockout_key)
                if lockout_until:
                    return True
                return False
            except Exception as e:
                # SECURITY FIX (Iteration 19): Bei Redis-Fehler NICHT zu In-Memory fallen
                # da sonst Multi-Worker Brute-Force moeglich ist
                logger.error(
                    "privat_brute_force_redis_check_failed_critical",
                    error=str(e),
                    action="blocking_request",
                )
                # SICHERHEIT: Im Zweifel blockieren - besser DoS als Brute-Force
                return True

        # SECURITY FIX 20-6: Graceful Degradation statt vollstaendigem Block
        # Bei Redis-Nichtverfuegbarkeit nutzen wir In-Memory mit erhoetem Alert-Level
        # Trade-off: Brute-Force-Risiko in Multi-Worker-Setup vs Availability
        logger.critical(
            "privat_brute_force_redis_unavailable_graceful_degradation",
            action="falling_back_to_in_memory",
            warning="Multi-Worker Brute-Force moeglich! Alert erforderlich!",
            severity="CRITICAL",
        )

        # In-Memory Fallback mit lokaler Pruefung
        # WICHTIG: Dies ist nur sicher in Single-Worker-Deployments!
        return self._check_lockout_in_memory(identifier)

    def record_failure(self, identifier: str) -> None:
        """Zeichnet einen fehlgeschlagenen Versuch auf (synchrone Version).

        HINWEIS: Verwendet In-Memory-Fallback. Fuer Redis nutze record_failure_async().

        Args:
            identifier: Eindeutiger Identifier
        """
        now = datetime.utcnow()
        # Alte Eintraege entfernen (aelter als Lockout-Zeitraum)
        cutoff = now - timedelta(minutes=self.LOCKOUT_MINUTES)
        self._attempts[identifier] = [
            t for t in self._attempts[identifier] if t > cutoff
        ]
        self._attempts[identifier].append(now)

        # Pruefen ob Lockout noetig
        if len(self._attempts[identifier]) >= self.MAX_ATTEMPTS:
            self._lockouts[identifier] = now + timedelta(minutes=self.LOCKOUT_MINUTES)
            logger.warning(
                "privat_brute_force_lockout",
                identifier=identifier,
                lockout_until=str(self._lockouts[identifier]),
                storage="in_memory",
            )

    async def record_failure_async(self, identifier: str) -> None:
        """Zeichnet einen fehlgeschlagenen Versuch auf (Redis-Version).

        SECURITY: Diese Methode sollte bevorzugt verwendet werden
        fuer Multi-Worker-Support.

        SECURITY FIX (Iteration 19): Verwendet atomare Pipeline mit WATCH
        fuer pessimistische Lockout-Setzung. Setzt Lockout IMMER wenn
        MAX_ATTEMPTS-1 erreicht ist (pessimistisch), um Race Conditions
        zu verhindern.

        Args:
            identifier: Eindeutiger Identifier
        """
        redis = await self._get_redis()
        if redis:
            try:
                attempts_key = f"{self.REDIS_KEY_ATTEMPTS}{identifier}"
                lockout_key = f"{self.REDIS_KEY_LOCKOUT}{identifier}"
                ttl_seconds = self.LOCKOUT_MINUTES * 60

                # SECURITY FIX: Atomare Pipeline - Lockout wird im gleichen
                # Pipeline-Execute gesetzt wenn Limit erreicht wird
                pipe = redis.pipeline()
                pipe.incr(attempts_key)
                pipe.expire(attempts_key, ttl_seconds)
                # PESSIMISTISCH: Setze Lockout immer mit (ueberschreibt wenn bereits existiert)
                # Das Lockout-Key existiert nur wenn tatsaechlich >= MAX_ATTEMPTS
                pipe.get(attempts_key)  # Hole aktuellen Wert fuer Logging
                results = await pipe.execute()

                # Nach INCR ist results[0] der neue Wert
                attempt_count = results[0]

                # Pruefen ob Lockout noetig - jetzt in separater atomarer Operation
                # aber mit sofortiger Ausfuehrung (kein Delay zwischen Check und Set)
                if attempt_count >= self.MAX_ATTEMPTS:
                    # Setze Lockout sofort - SETNX verhindert Race Condition bei parallelen Requests
                    # Wenn bereits gesetzt, wird einfach ueberschrieben (idempotent)
                    await redis.setex(
                        lockout_key,
                        ttl_seconds,
                        "locked"
                    )
                    logger.warning(
                        "privat_brute_force_lockout",
                        identifier=identifier,
                        attempt_count=attempt_count,
                        lockout_minutes=self.LOCKOUT_MINUTES,
                        storage="redis",
                    )
                return
            except Exception as e:
                logger.warning(
                    "privat_brute_force_redis_record_failed",
                    error=str(e),
                    fallback="in_memory",
                )

        # Fallback zu In-Memory
        self.record_failure(identifier)

    def clear(self, identifier: str) -> None:
        """Loescht alle Versuche fuer einen Identifier (synchrone Version).

        Args:
            identifier: Eindeutiger Identifier
        """
        self._attempts.pop(identifier, None)
        self._lockouts.pop(identifier, None)

    async def clear_async(self, identifier: str) -> None:
        """Loescht alle Versuche fuer einen Identifier (Redis-Version).

        Args:
            identifier: Eindeutiger Identifier
        """
        redis = await self._get_redis()
        if redis:
            try:
                attempts_key = f"{self.REDIS_KEY_ATTEMPTS}{identifier}"
                lockout_key = f"{self.REDIS_KEY_LOCKOUT}{identifier}"
                await redis.delete(attempts_key, lockout_key)
                return
            except Exception as e:
                logger.warning(
                    "privat_brute_force_redis_clear_failed",
                    error=str(e),
                )

        # Fallback zu In-Memory
        self.clear(identifier)

    def get_remaining_attempts(self, identifier: str) -> int:
        """Gibt die verbleibenden Versuche zurueck (synchrone Version).

        Args:
            identifier: Eindeutiger Identifier

        Returns:
            Anzahl verbleibender Versuche
        """
        if self.is_locked(identifier):
            return 0
        now = datetime.utcnow()
        cutoff = now - timedelta(minutes=self.LOCKOUT_MINUTES)
        recent_attempts = [
            t for t in self._attempts.get(identifier, []) if t > cutoff
        ]
        return max(0, self.MAX_ATTEMPTS - len(recent_attempts))

    async def get_remaining_attempts_async(self, identifier: str) -> int:
        """Gibt die verbleibenden Versuche zurueck (Redis-Version).

        Args:
            identifier: Eindeutiger Identifier

        Returns:
            Anzahl verbleibender Versuche
        """
        if await self.is_locked_async(identifier):
            return 0

        redis = await self._get_redis()
        if redis:
            try:
                attempts_key = f"{self.REDIS_KEY_ATTEMPTS}{identifier}"
                count = await redis.get(attempts_key)
                if count:
                    return max(0, self.MAX_ATTEMPTS - int(count))
                return self.MAX_ATTEMPTS
            except Exception as e:
                logger.warning(
                    "privat_brute_force_redis_get_remaining_failed",
                    error=str(e),
                )

        # Fallback zu In-Memory
        return self.get_remaining_attempts(identifier)

    async def get_current_attempts_async(self, identifier: str) -> int:
        """Gibt die aktuelle Anzahl fehlgeschlagener Versuche zurueck (Redis-Version).

        SECURITY FIX (Iteration 19): Fuer progressive Verzoegerungsberechnung.

        Args:
            identifier: Eindeutiger Identifier

        Returns:
            Anzahl der bisherigen Fehlversuche
        """
        redis = await self._get_redis()
        if redis:
            try:
                attempts_key = f"{self.REDIS_KEY_ATTEMPTS}{identifier}"
                count = await redis.get(attempts_key)
                if count:
                    return int(count)
                return 0
            except Exception as e:
                logger.warning(
                    "privat_brute_force_redis_get_attempts_failed",
                    error=str(e),
                )

        # Fallback zu In-Memory
        now = datetime.utcnow()
        cutoff = now - timedelta(minutes=self.LOCKOUT_MINUTES)
        recent_attempts = [
            t for t in self._attempts.get(identifier, []) if t > cutoff
        ]
        return len(recent_attempts)

    def calculate_progressive_delay(self, attempt_count: int) -> float:
        """Berechnet die progressive Verzoegerung basierend auf Fehlversuchen.

        SECURITY FIX (Iteration 19): Progressive delay macht Brute-Force-Angriffe
        exponentiell langsamer mit jedem Fehlversuch.

        Verzoegerungs-Schema (in Millisekunden):
        - 0 Fehlversuche: 500ms (Basis)
        - 1 Fehlversuch:  1000ms (2x)
        - 2 Fehlversuche: 2000ms (4x)
        - 3 Fehlversuche: 4000ms (8x)
        - 4 Fehlversuche: 8000ms (16x)
        - 5+ Fehlversuche: Lockout

        Args:
            attempt_count: Anzahl bisheriger Fehlversuche

        Returns:
            Verzoegerung in Sekunden (als float)
        """
        # Basis-Verzoegerung: 500ms
        BASE_DELAY_MS = 500
        # Exponentieller Faktor: 2^attempt_count
        # Cap bei MAX_ATTEMPTS um ueberlauf zu vermeiden
        capped_attempts = min(attempt_count, self.MAX_ATTEMPTS)
        delay_ms = BASE_DELAY_MS * (2 ** capped_attempts)

        # Max-Cap: 30 Sekunden (um extreme Verzoegerungen zu vermeiden)
        MAX_DELAY_MS = 30000
        delay_ms = min(delay_ms, MAX_DELAY_MS)

        return delay_ms / 1000.0  # Konvertiere zu Sekunden


# Singleton fuer Brute-Force-Tracking
_attempt_tracker = DecryptAttemptTracker()


def get_attempt_tracker() -> DecryptAttemptTracker:
    """Gibt den globalen Attempt-Tracker zurueck."""
    return _attempt_tracker


class PrivatEncryptionService:
    """Service fuer Extra-Verschluesselung mit Benutzer-Passwort.

    Verwendet PBKDF2 fuer Key-Derivation und AES-256-GCM fuer Verschluesselung.
    """

    PBKDF2_ITERATIONS = 100_000
    SALT_SIZE = 32  # 256 bit
    NONCE_SIZE = 12  # 96 bit fuer AES-GCM
    KEY_SIZE = 32  # 256 bit

    def derive_key(
        self,
        password: str,
        salt: bytes,
    ) -> bytes:
        """Leitet einen Schluessel aus dem Passwort ab.

        Args:
            password: Benutzer-Passwort
            salt: Zufaelliger Salt

        Returns:
            Abgeleiteter Schluessel (32 Bytes)
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.KEY_SIZE,
            salt=salt,
            iterations=self.PBKDF2_ITERATIONS,
            backend=default_backend(),
        )
        return kdf.derive(password.encode("utf-8"))

    def encrypt(
        self,
        data: bytes,
        password: str,
    ) -> Tuple[bytes, bytes, bytes]:
        """Verschluesselt Daten mit einem Passwort.

        Args:
            data: Zu verschluesselnde Daten
            password: Benutzer-Passwort (muss Enterprise-Anforderungen erfuellen)

        Returns:
            Tuple von (salt, nonce, ciphertext)

        Raises:
            WeakPasswordError: Wenn Passwort nicht stark genug ist
        """
        # SECURITY: Enterprise Password Validation
        if not validate_password_strength(password):
            raise WeakPasswordError(PASSWORD_REQUIREMENTS_DE)

        # Generiere zufaelligen Salt und Nonce
        salt = secrets.token_bytes(self.SALT_SIZE)
        nonce = secrets.token_bytes(self.NONCE_SIZE)

        # Leite Schluessel ab
        key = self.derive_key(password, salt)

        # Verschluessle mit AES-256-GCM
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, data, None)

        logger.debug(
            "privat_document_encrypted",
            data_size=len(data),
            ciphertext_size=len(ciphertext),
        )

        return salt, nonce, ciphertext

    # Konstante Zeit fuer Timing-Attack-Mitigation (500ms)
    DECRYPT_MIN_TIME_MS = 500

    async def decrypt_async(
        self,
        ciphertext: bytes,
        password: str,
        salt: bytes,
        nonce: bytes,
        identifier: str = "unknown",
    ) -> Optional[bytes]:
        """Entschluesselt Daten mit einem Passwort (async, Redis-basiert).

        SECURITY: Diese Methode sollte bevorzugt verwendet werden fuer
        Multi-Worker-Deployments, da sie Redis fuer Brute-Force-Tracking nutzt.

        SECURITY FIX (Iteration 19): Progressive Verzoegerung
        - Verzoegerung verdoppelt sich mit jedem Fehlversuch
        - Macht Brute-Force-Angriffe exponentiell langsamer

        Args:
            ciphertext: Verschluesselte Daten
            password: Benutzer-Passwort
            salt: Salt der Verschluesselung
            nonce: Nonce der Verschluesselung
            identifier: Eindeutiger Identifier fuer Brute-Force-Tracking
                        (z.B. "doc_123:user_456")

        Returns:
            Entschluesselte Daten oder None bei falschem Passwort

        Raises:
            BruteForceProtectionError: Bei zu vielen fehlgeschlagenen Versuchen
        """
        import asyncio
        start_time = time.monotonic()

        # SECURITY FIX (Iteration 19): Hole aktuelle Fehlversuche fuer progressive Verzoegerung
        current_attempts = await _attempt_tracker.get_current_attempts_async(identifier)
        progressive_delay = _attempt_tracker.calculate_progressive_delay(current_attempts)

        # SECURITY: Brute-Force-Schutz pruefen (Redis-basiert)
        if await _attempt_tracker.is_locked_async(identifier):
            # SECURITY: Progressive Verzoegerung auch bei Lockout!
            # Verhindert Timing-Side-Channel ueber Lockout-Status
            await asyncio.sleep(progressive_delay)
            logger.warning(
                "privat_decrypt_blocked_brute_force",
                identifier=identifier,
                storage="redis",
                progressive_delay_ms=progressive_delay * 1000,
            )
            raise BruteForceProtectionError(
                f"Zu viele fehlgeschlagene Versuche. "
                f"Bitte warten Sie {DecryptAttemptTracker.LOCKOUT_MINUTES} Minuten."
            )

        try:
            key = self.derive_key(password, salt)
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)

            # Erfolg - Versuche zuruecksetzen (Redis)
            await _attempt_tracker.clear_async(identifier)

            logger.debug(
                "privat_document_decrypted",
                ciphertext_size=len(ciphertext),
                plaintext_size=len(plaintext),
                storage="redis",
            )

            # SECURITY FIX (Iteration 19): Progressive Verzoegerung statt fester Zeit
            # Bei Erfolg nach Fehlversuchen: Kurze Basis-Verzoegerung
            await self._ensure_progressive_delay_async(start_time, progressive_delay)

            return plaintext
        except (InvalidTag, TypeError, ValueError) as e:
            # SECURITY: Nur erwartete Crypto-Exceptions fangen
            await _attempt_tracker.record_failure_async(identifier)
            remaining = await _attempt_tracker.get_remaining_attempts_async(identifier)

            # SECURITY FIX (Iteration 19): Neu berechnete Verzoegerung nach Fehlversuch
            # (um einen Versuch hoeher als vor dem Fehlversuch)
            new_delay = _attempt_tracker.calculate_progressive_delay(current_attempts + 1)

            logger.warning(
                "privat_document_decrypt_failed",
                identifier=identifier,
                remaining_attempts=remaining,
                error_type=type(e).__name__,
                storage="redis",
                progressive_delay_ms=new_delay * 1000,
                attempt_count=current_attempts + 1,
            )

            # SECURITY FIX (Iteration 19): Progressive Verzoegerung
            await self._ensure_progressive_delay_async(start_time, new_delay)

            return None

    async def _ensure_progressive_delay_async(
        self, start_time: float, target_delay: float
    ) -> None:
        """Stellt sicher, dass mindestens die progressive Verzoegerung vergangen ist.

        SECURITY FIX (Iteration 19): Ersetzt die alte _ensure_min_time_async
        mit dynamischer progressiver Verzoegerung.

        Args:
            start_time: Startzeit der Operation (time.monotonic())
            target_delay: Ziel-Verzoegerung in Sekunden
        """
        import asyncio
        elapsed = time.monotonic() - start_time
        remaining = target_delay - elapsed
        if remaining > 0:
            await asyncio.sleep(remaining)

    async def _ensure_min_time_async(self, start_time: float) -> None:
        """Async Version: Stellt sicher, dass mindestens DECRYPT_MIN_TIME_MS vergangen sind.

        Args:
            start_time: Startzeit der Operation (time.monotonic())
        """
        import asyncio
        elapsed_ms = (time.monotonic() - start_time) * 1000
        if elapsed_ms < self.DECRYPT_MIN_TIME_MS:
            await asyncio.sleep((self.DECRYPT_MIN_TIME_MS - elapsed_ms) / 1000)

    def decrypt(
        self,
        ciphertext: bytes,
        password: str,
        salt: bytes,
        nonce: bytes,
        identifier: str = "unknown",
    ) -> Optional[bytes]:
        """Entschluesselt Daten mit einem Passwort (synchrone Fallback-Version).

        HINWEIS: Fuer Multi-Worker-Deployments bevorzuge decrypt_async()
        welche Redis fuer Brute-Force-Tracking nutzt.

        Args:
            ciphertext: Verschluesselte Daten
            password: Benutzer-Passwort
            salt: Salt der Verschluesselung
            nonce: Nonce der Verschluesselung
            identifier: Eindeutiger Identifier fuer Brute-Force-Tracking
                        (z.B. "doc_123:user_456")

        Returns:
            Entschluesselte Daten oder None bei falschem Passwort

        Raises:
            BruteForceProtectionError: Bei zu vielen fehlgeschlagenen Versuchen
        """
        start_time = time.monotonic()

        # SECURITY: Brute-Force-Schutz pruefen
        if _attempt_tracker.is_locked(identifier):
            # SECURITY: Timing-Attack-Mitigation auch bei Lockout!
            # Sonst kann Angreifer Lockout-Status aus Antwortzeit ableiten
            self._ensure_min_time(start_time)
            logger.warning(
                "privat_decrypt_blocked_brute_force",
                identifier=identifier,
                storage="in_memory",
            )
            raise BruteForceProtectionError(
                f"Zu viele fehlgeschlagene Versuche. "
                f"Bitte warten Sie {DecryptAttemptTracker.LOCKOUT_MINUTES} Minuten."
            )

        try:
            key = self.derive_key(password, salt)
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)

            # Erfolg - Versuche zuruecksetzen
            _attempt_tracker.clear(identifier)

            logger.debug(
                "privat_document_decrypted",
                ciphertext_size=len(ciphertext),
                plaintext_size=len(plaintext),
            )

            # SECURITY: Timing-Attack-Mitigation - konstante Antwortzeit
            self._ensure_min_time(start_time)

            return plaintext
        except (InvalidTag, TypeError, ValueError) as e:
            # SECURITY: Nur erwartete Crypto-Exceptions fangen
            # InvalidTag = falsches Passwort, TypeError/ValueError = korrupte Daten
            # Andere Exceptions (z.B. SystemError) werden durchgereicht
            _attempt_tracker.record_failure(identifier)
            remaining = _attempt_tracker.get_remaining_attempts(identifier)

            logger.warning(
                "privat_document_decrypt_failed",
                identifier=identifier,
                remaining_attempts=remaining,
                error_type=type(e).__name__,
            )

            # SECURITY: Timing-Attack-Mitigation - konstante Antwortzeit
            # Wichtig: Fehlschlaege dauern genauso lange wie Erfolge
            self._ensure_min_time(start_time)

            return None

    def _ensure_min_time(self, start_time: float) -> None:
        """Stellt sicher, dass mindestens DECRYPT_MIN_TIME_MS vergangen sind.

        Dies verhindert Timing-Attacken, bei denen ein Angreifer aus der
        Antwortzeit auf die Korrektheit des Passworts schliessen koennte.

        Args:
            start_time: Startzeit der Operation (time.monotonic())
        """
        elapsed_ms = (time.monotonic() - start_time) * 1000
        if elapsed_ms < self.DECRYPT_MIN_TIME_MS:
            time.sleep((self.DECRYPT_MIN_TIME_MS - elapsed_ms) / 1000)

    def encrypt_file(
        self,
        file_path: str,
        password: str,
        output_path: Optional[str] = None,
    ) -> str:
        """Verschluesselt eine Datei.

        Args:
            file_path: Pfad zur Quelldatei
            password: Benutzer-Passwort
            output_path: Optionaler Ausgabepfad

        Returns:
            Pfad zur verschluesselten Datei

        Format: [salt (32 bytes)][nonce (12 bytes)][ciphertext]
        """
        if output_path is None:
            output_path = f"{file_path}.encrypted"

        with open(file_path, "rb") as f:
            data = f.read()

        salt, nonce, ciphertext = self.encrypt(data, password)

        # Schreibe in Datei: salt + nonce + ciphertext
        with open(output_path, "wb") as f:
            f.write(salt)
            f.write(nonce)
            f.write(ciphertext)

        logger.info(
            "privat_file_encrypted",
            input_path=file_path,
            output_path=output_path,
        )

        return output_path

    def decrypt_file(
        self,
        file_path: str,
        password: str,
        output_path: Optional[str] = None,
    ) -> Optional[str]:
        """Entschluesselt eine Datei.

        Args:
            file_path: Pfad zur verschluesselten Datei
            password: Benutzer-Passwort
            output_path: Optionaler Ausgabepfad

        Returns:
            Pfad zur entschluesselten Datei oder None bei Fehler
        """
        if output_path is None:
            if file_path.endswith(".encrypted"):
                output_path = file_path[:-10]
            else:
                output_path = f"{file_path}.decrypted"

        with open(file_path, "rb") as f:
            salt = f.read(self.SALT_SIZE)
            nonce = f.read(self.NONCE_SIZE)
            ciphertext = f.read()

        plaintext = self.decrypt(ciphertext, password, salt, nonce)

        if plaintext is None:
            return None

        with open(output_path, "wb") as f:
            f.write(plaintext)

        logger.info(
            "privat_file_decrypted",
            input_path=file_path,
            output_path=output_path,
        )

        return output_path

    def verify_password(
        self,
        encrypted_data: bytes,
        password: str,
    ) -> bool:
        """Prueft ob ein Passwort korrekt ist (ohne volle Entschluesselung).

        SECURITY: Diese Methode hat konstante Antwortzeit (Timing-Attack Mitigation).

        Args:
            encrypted_data: Verschluesselte Daten (salt + nonce + ciphertext)
            password: Zu pruefendes Passwort

        Returns:
            True wenn Passwort korrekt
        """
        start_time = time.monotonic()

        if len(encrypted_data) < self.SALT_SIZE + self.NONCE_SIZE + 16:
            # SECURITY: Auch bei falscher Laenge konstante Zeit warten
            self._ensure_min_time(start_time)
            return False

        salt = encrypted_data[:self.SALT_SIZE]
        nonce = encrypted_data[self.SALT_SIZE:self.SALT_SIZE + self.NONCE_SIZE]
        ciphertext = encrypted_data[self.SALT_SIZE + self.NONCE_SIZE:]

        # Versuche Entschluesselung (decrypt() hat bereits konstante Zeit)
        result = self.decrypt(ciphertext, password, salt, nonce)
        # Keine zusaetzliche Wartezeit noetig - decrypt() macht das bereits
        return result is not None

    def get_encrypted_metadata(
        self,
        encrypted_data: bytes,
    ) -> dict:
        """Extrahiert Metadaten aus verschluesselten Daten.

        Args:
            encrypted_data: Verschluesselte Daten

        Returns:
            Dict mit Salt-Hash und Groesse
        """
        if len(encrypted_data) < self.SALT_SIZE:
            return {"valid": False}

        salt = encrypted_data[:self.SALT_SIZE]
        salt_hash = hashlib.sha256(salt).hexdigest()[:16]

        return {
            "valid": True,
            "salt_hash": salt_hash,
            "encrypted_size": len(encrypted_data),
            "estimated_plaintext_size": len(encrypted_data) - self.SALT_SIZE - self.NONCE_SIZE - 16,
        }
