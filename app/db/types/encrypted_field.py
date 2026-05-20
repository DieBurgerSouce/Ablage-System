"""Verschluesselter Feldtyp fuer SQLAlchemy.

Transparente AES-256-GCM Verschluesselung auf Spaltenebene.
Daten werden beim Schreiben automatisch verschluesselt und beim Lesen entschluesselt.

DSGVO-Compliance: IBAN, BIC, Steuernummern werden verschluesselt gespeichert.

Feinpoliert und durchdacht - Enterprise-grade Field-Level Encryption.
"""

from typing import Optional

from sqlalchemy import String, Text
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from app.core.encryption import encrypt_data, decrypt_data, EncryptionError
import structlog

logger = structlog.get_logger(__name__)


class EncryptedString(TypeDecorator):
    """Transparente Verschluesselung fuer String-Spalten.

    Verschluesselt Daten automatisch beim Schreiben in die DB
    und entschluesselt beim Lesen.

    Verwendung:
        class Company(Base):
            iban = Column(EncryptedString(length=34), nullable=True)

    Die Datenbank-Spalte speichert den verschluesselten String (Base64).
    Die verschluesselten Daten sind laenger als der Klartext,
    daher wird die Spalte als Text gespeichert.

    Sicherheitshinweise:
        - AES-256-GCM mit authentifizierter Verschluesselung
        - Optionale AAD (Additional Authenticated Data) fuer Kontext-Bindung
        - Jeder Wert erhaelt eine einzigartige Nonce
        - Entschluesselungsfehler geben None zurueck (kein Crash)
    """

    impl = Text
    cache_ok = True

    def __init__(
        self,
        length: int = 255,
        aad_context: Optional[str] = None,
    ) -> None:
        """Initialisiert den verschluesselten Feldtyp.

        Args:
            length: Maximale Laenge des Klartexts (fuer Dokumentation/Validierung).
                    Die DB-Spalte nutzt Text, da verschluesselte Daten laenger sind.
            aad_context: Additional Authenticated Data Kontext (z.B. 'companies.iban').
                         Verhindert das Verschieben verschluesselter Werte zwischen Spalten.
        """
        super().__init__()
        self._original_length = length
        self._aad_context = aad_context

    def process_bind_param(
        self, value: Optional[str], dialect: Dialect
    ) -> Optional[str]:
        """Verschluesselt den Wert vor dem Schreiben in die DB.

        Args:
            value: Klartext-Wert oder None.
            dialect: SQLAlchemy Dialect (wird nicht verwendet).

        Returns:
            Base64-kodierter verschluesselter String oder None.

        Raises:
            EncryptionError: Wenn die Verschluesselung fehlschlaegt.
        """
        if value is None or value == "":
            return value

        try:
            return encrypt_data(value, associated_data=self._aad_context)
        except EncryptionError:
            logger.error(
                "field_encryption_failed",
                context=self._aad_context,
                value_length=len(value),
            )
            raise

    def process_result_value(
        self, value: Optional[str], dialect: Dialect
    ) -> Optional[str]:
        """Entschluesselt den Wert beim Lesen aus der DB.

        Bei Entschluesselungsfehlern wird None zurueckgegeben statt eines Crashes.
        Dies ist wichtig fuer den Fall, dass Daten mit einem alten Key verschluesselt
        wurden oder noch nicht migriert sind.

        Args:
            value: Verschluesselter String aus der DB oder None.
            dialect: SQLAlchemy Dialect (wird nicht verwendet).

        Returns:
            Entschluesselter Klartext oder None bei Fehler.
        """
        if value is None or value == "":
            return value

        try:
            return decrypt_data(value, associated_data=self._aad_context)
        except EncryptionError:
            logger.error(
                "field_decryption_failed",
                context=self._aad_context,
                value_length=len(value),
            )
            # Return None statt Crash - Daten koennten mit altem Key verschluesselt sein
            return None

    @property
    def original_length(self) -> int:
        """Gibt die maximale Klartext-Laenge zurueck."""
        return self._original_length

    @property
    def aad_context(self) -> Optional[str]:
        """Gibt den AAD-Kontext zurueck."""
        return self._aad_context
