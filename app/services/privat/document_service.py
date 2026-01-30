"""Service fuer die Verwaltung privater Dokumente."""

import gc
import uuid
import os
import re
from pathlib import Path
from datetime import datetime
from app.core.datetime_utils import utc_now
from typing import Optional, List, Tuple, BinaryIO
from contextlib import contextmanager

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.models import PrivatDocument, PrivatFolder, PrivatSpace
from app.db.schemas import (
    PrivatDocumentCreate,
    PrivatDocumentUpdate,
    PrivatDocumentResponse,
    PrivatDocumentListResponse,
    PrivatDocumentType,
)
from app.services.privat.encryption_service import (
    PrivatEncryptionService,
    generate_brute_force_identifier,
)
from app.core.config import settings
from app.core.audit_logger import AuditLogger, SecurityEventType
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


def secure_memory_cleanup(*variables: bytes) -> None:
    """Sichere Speicherbereinigung fuer sensible Daten im RAM.

    SECURITY FIX (Iteration 19): CWE-226/CWE-316 Prevention
    - Python bytes sind immutable, daher KEINE direkte Ueberschreibung moeglich
    - Diese Funktion loescht Referenzen und triggert Garbage Collection
    - WICHTIG: Caller MUSS sicherstellen, dass ALLE Referenzen geloescht sind!

    Best Practices fuer sensible Daten:
    1. Minimiere die Lebensdauer von Plaintext im RAM
    2. Verwende lokale Variablen statt Klassenvariablen fuer Plaintext
    3. Rufe diese Funktion nach Gebrauch auf
    4. In kritischen Szenarien: Verwende bytearray (mutable) statt bytes

    Args:
        *variables: Bytes-Objekte die bereinigt werden sollen
                    (Hinweis: Die Referenzen werden hier nicht wirklich
                    geloescht, das muss im aufrufenden Code geschehen!)
    """
    # Expliziter GC-Lauf um nicht mehr referenzierte Objekte freizugeben
    # SECURITY: Dies ist defense-in-depth - die Hauptverantwortung liegt
    # beim Caller, alle Referenzen auf sensible Daten zu loeschen
    gc.collect()

    logger.debug(
        "privat_secure_memory_cleanup",
        garbage_collected=True,
        hint="Caller must ensure all references to sensitive data are deleted",
    )


class SecureBytesWrapper:
    """Wrapper fuer sichere Handhabung von sensiblen Bytes.

    SECURITY (Iteration 19): Defense-in-depth fuer sensible Daten im RAM.
    Verwendet intern bytearray fuer ueberschreibbare Speicherung.

    Verwendung:
        with SecureBytesWrapper(plaintext) as secure_data:
            # Verwende secure_data.data fuer Operationen
            process(secure_data.data)
        # Nach dem with-Block: Daten automatisch ueberschrieben!
    """

    def __init__(self, data: bytes) -> None:
        """Initialisiert den Wrapper mit sensiblen Daten.

        Args:
            data: Die zu schuetzenden Bytes
        """
        # Konvertiere zu bytearray fuer spaetere Ueberschreibung
        self._data = bytearray(data)
        self._is_cleared = False

    @property
    def data(self) -> bytes:
        """Gibt die Daten als bytes zurueck.

        Returns:
            Die gespeicherten Daten

        Raises:
            RuntimeError: Wenn Daten bereits bereinigt wurden
        """
        if self._is_cleared:
            raise RuntimeError("Sensible Daten wurden bereits bereinigt!")
        return bytes(self._data)

    def clear(self) -> None:
        """Ueberschreibt die Daten mit Nullen und bereinigt den Speicher.

        SECURITY: Diese Methode ueberschreibt den bytearray mit Nullen,
        wodurch die sensiblen Daten im RAM vernichtet werden.
        """
        if not self._is_cleared:
            # Ueberschreibe mit Nullen
            for i in range(len(self._data)):
                self._data[i] = 0
            # Loesche die Referenz
            del self._data
            self._is_cleared = True
            # Trigger GC
            gc.collect()
            logger.debug("privat_secure_bytes_cleared")

    def __enter__(self) -> "SecureBytesWrapper":
        """Context Manager Entry."""
        return self

    def __exit__(self, exc_type: type, exc_val: Exception, exc_tb: object) -> None:
        """Context Manager Exit - bereinigt automatisch."""
        self.clear()

    def __del__(self) -> None:
        """Destruktor - letzte Chance zur Bereinigung."""
        if not self._is_cleared:
            try:
                self.clear()
            except Exception:
                pass  # Im Destruktor keine Exceptions werfen


# Singleton Audit Logger - MANDATORY for Enterprise Security
_audit_logger: Optional[AuditLogger] = None
_audit_logger_init_attempted: bool = False


class AuditLoggerRequiredError(RuntimeError):
    """Ausnahme wenn der Audit Logger nicht verfuegbar ist.

    SECURITY: Audit Logging ist fuer das Privat-Modul PFLICHT (Enterprise Requirement).
    Ohne funktionierendes Audit Logging duerfen keine Operationen ausgefuehrt werden.
    """
    pass


def get_audit_logger() -> AuditLogger:
    """Gibt den Audit Logger zurueck (Lazy Initialization).

    SECURITY: Audit Logging ist MANDATORY fuer das Privat-Modul.
    Bei Initialisierungsfehler wird eine Exception geworfen.

    Returns:
        AuditLogger instance

    Raises:
        AuditLoggerRequiredError: Wenn der Audit Logger nicht initialisiert werden kann
    """
    global _audit_logger, _audit_logger_init_attempted

    if _audit_logger is not None:
        return _audit_logger

    if _audit_logger_init_attempted:
        # Bereits einmal fehlgeschlagen - nicht erneut versuchen
        raise AuditLoggerRequiredError(
            "Audit Logger konnte nicht initialisiert werden. "
            "Bitte pruefen Sie die Konfiguration."
        )

    _audit_logger_init_attempted = True
    try:
        _audit_logger = AuditLogger()
        logger.info("privat_audit_logger_initialized")
        return _audit_logger
    except Exception as e:
        logger.error(
            "privat_audit_logger_init_failed",
            **safe_error_log(e),
            error_type=type(e).__name__,
        )
        raise AuditLoggerRequiredError(
            f"Audit Logger konnte nicht initialisiert werden: {e}"
        ) from e


class PathTraversalError(ValueError):
    """Ausnahme bei Path-Traversal-Versuch."""
    pass


class AccessDeniedError(PermissionError):
    """Ausnahme bei fehlender Berechtigung."""
    pass


class WeakPasswordError(ValueError):
    """Ausnahme bei zu schwachem Passwort."""
    pass


# Enterprise Password Requirements
MIN_PASSWORD_LENGTH = 14
PASSWORD_REQUIREMENTS_DE = (
    "Passwort muss mindestens 14 Zeichen lang sein und "
    "Grossbuchstaben, Kleinbuchstaben, Zahlen und Sonderzeichen enthalten"
)


def validate_password_strength(password: str) -> bool:
    """Validiert die Passwort-Staerke fuer Verschluesselung.

    Enterprise-Standard: Mindestens 14 Zeichen mit Komplexitaet.

    Args:
        password: Das zu validierende Passwort

    Returns:
        True wenn das Passwort stark genug ist
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        return False

    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in "!@#$%^&*()-_=+[]{}|;:,.<>?/~`" for c in password)

    return has_upper and has_lower and has_digit and has_special


class PrivatDocumentService:
    """Service fuer Privat-Dokument CRUD und Verschluesselung."""

    def __init__(self) -> None:
        """Initialisiert den Service."""
        self.encryption_service = PrivatEncryptionService()
        self.storage_base_path = getattr(settings, "PRIVAT_STORAGE_PATH", "/data/privat")

    def _sanitize_filename(self, filename: str) -> str:
        """Bereinigt Dateinamen von Path-Traversal-Versuchen.

        Args:
            filename: Original-Dateiname

        Returns:
            Bereinigter Dateiname (nur Basename, sichere Zeichen)

        Raises:
            PathTraversalError: Bei verdaechtigen Mustern
        """
        # Extrahiere nur den Dateinamen (entferne Pfadkomponenten)
        basename = os.path.basename(filename)

        # Entferne versteckte Dateien (beginnen mit .)
        if basename.startswith('.'):
            basename = basename.lstrip('.')

        # Erlaube nur sichere Zeichen: alphanumerisch, Punkt, Bindestrich, Unterstrich, Leerzeichen
        safe_name = re.sub(r'[^a-zA-Z0-9.\-_ ]', '_', basename)

        # Verhindere doppelte Punkte (..extension)
        while '..' in safe_name:
            safe_name = safe_name.replace('..', '.')

        # Leerer Name? Generiere UUID-basierten
        if not safe_name or safe_name == '.':
            safe_name = f"document_{uuid.uuid4().hex[:8]}"

        logger.debug(
            "filename_sanitized",
            original=filename,
            sanitized=safe_name
        )

        return safe_name

    def _validate_path_within_base(self, file_path: str) -> str:
        """Validiert, dass der Pfad innerhalb des Basisverzeichnisses bleibt.

        Args:
            file_path: Relativer oder absoluter Pfad

        Returns:
            Absoluter, aufgeloester Pfad

        Raises:
            PathTraversalError: Bei Path-Traversal-Versuch
        """
        # Erstelle absoluten Pfad
        full_path = os.path.join(self.storage_base_path, file_path)

        # Resolve symlinks und .. Komponenten
        resolved_path = os.path.realpath(full_path)
        resolved_base = os.path.realpath(self.storage_base_path)

        # Pruefe ob resolved_path innerhalb von resolved_base liegt
        if not resolved_path.startswith(resolved_base + os.sep) and resolved_path != resolved_base:
            logger.warning(
                "path_traversal_attempt",
                file_path=file_path,
                resolved_path=resolved_path,
                base_path=resolved_base
            )
            raise PathTraversalError(
                f"Ungueltiger Pfad: Path-Traversal erkannt"
            )

        return resolved_path

    async def _verify_document_access(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
        required_level: str = "read",
    ) -> PrivatDocument:
        """Verifiziert Benutzerzugriff auf ein Dokument.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            user_id: Benutzer-ID der Anfrage
            required_level: Erforderliche Ebene (read, write, admin)

        Returns:
            Dokument wenn Zugriff erlaubt

        Raises:
            AccessDeniedError: Bei fehlender Berechtigung
        """
        from app.db.models import PrivatSpaceAccess

        # Hole Dokument mit Space
        result = await db.execute(
            select(PrivatDocument, PrivatSpace)
            .join(PrivatSpace, PrivatDocument.space_id == PrivatSpace.id)
            .where(PrivatDocument.id == document_id)
        )
        row = result.first()

        if not row:
            raise AccessDeniedError(f"Dokument {document_id} nicht gefunden oder kein Zugriff")

        document, space = row

        # Owner hat immer vollen Zugriff
        if space.owner_id == user_id:
            return document

        # Pruefe explizite Berechtigung
        # SECURITY: expires_at Validierung - abgelaufene Zugriffe ignorieren!
        from datetime import timezone
        from sqlalchemy import or_
        now = datetime.now(timezone.utc)

        access_result = await db.execute(
            select(PrivatSpaceAccess)
            .where(
                PrivatSpaceAccess.space_id == space.id,
                PrivatSpaceAccess.user_id == user_id,
                # SECURITY: expires_at check - None = kein Ablauf, sonst Datum pruefen
                or_(
                    PrivatSpaceAccess.expires_at == None,
                    PrivatSpaceAccess.expires_at > now
                ),
            )
        )
        access = access_result.scalar_one_or_none()

        if not access:
            logger.warning(
                "idor_attempt_blocked",
                document_id=str(document_id),
                user_id=str(user_id),
                space_id=str(space.id)
            )
            raise AccessDeniedError(f"Kein Zugriff auf Dokument {document_id}")

        # Level-Hierarchie prufen: admin > write > read
        level_hierarchy = {"read": 1, "write": 2, "admin": 3}
        user_level = level_hierarchy.get(access.access_level, 0)
        required = level_hierarchy.get(required_level, 1)

        if user_level < required:
            logger.warning(
                "insufficient_permission",
                document_id=str(document_id),
                user_id=str(user_id),
                has_level=access.access_level,
                required_level=required_level
            )
            raise AccessDeniedError(
                f"Unzureichende Berechtigung: {access.access_level}, benoetigt: {required_level}"
            )

        return document

    async def create(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        file_content: bytes,
        file_name: str,
        mime_type: str,
        data: PrivatDocumentCreate,
        extra_password: Optional[str] = None,
    ) -> PrivatDocument:
        """Erstellt ein neues Dokument.

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            file_content: Datei-Inhalt
            file_name: Original-Dateiname
            mime_type: MIME-Type
            data: Dokument-Daten
            extra_password: Optional Extra-Passwort

        Returns:
            Erstelltes Dokument

        Raises:
            ValueError: Bei ungueltigem Input
        """
        # ==================== Input Validation (Service Layer) ====================

        # Dateigroesse pruefen (max 100 MB)
        max_size = 100 * 1024 * 1024  # 100 MB
        if len(file_content) > max_size:
            raise ValueError(f"Datei zu gross: {len(file_content)} bytes (max {max_size})")

        if len(file_content) == 0:
            raise ValueError("Leere Dateien sind nicht erlaubt")

        # Dateiname validieren
        if not file_name or len(file_name) > 255:
            raise ValueError("Dateiname ungueltig (1-255 Zeichen erforderlich)")

        # MIME-Type validieren (nur sichere Typen)
        allowed_mimes = [
            "application/pdf",
            "image/jpeg", "image/png", "image/gif", "image/webp", "image/tiff",
            "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "text/plain", "text/csv",
            "application/zip", "application/x-zip-compressed",
        ]
        if mime_type and mime_type not in allowed_mimes:
            logger.warning(
                "invalid_mime_type_blocked",
                mime_type=mime_type,
                allowed=allowed_mimes[:5]  # Log nur erste 5
            )
            raise ValueError(f"Dateityp nicht erlaubt: {mime_type}")

        # Titel validieren
        if data.title and len(data.title) > 500:
            raise ValueError("Titel zu lang (max 500 Zeichen)")

        # Beschreibung validieren
        if data.description and len(data.description) > 5000:
            raise ValueError("Beschreibung zu lang (max 5000 Zeichen)")

        # Password-Hinweis validieren (falls verschluesselt)
        if data.extra_encrypted:
            if not extra_password:
                raise WeakPasswordError(PASSWORD_REQUIREMENTS_DE)
            if not validate_password_strength(extra_password):
                raise WeakPasswordError(PASSWORD_REQUIREMENTS_DE)
            if data.password_hint and len(data.password_hint) > 200:
                raise ValueError("Passwort-Hinweis zu lang (max 200 Zeichen)")

        # ==================== End Input Validation ====================

        doc_id = uuid.uuid4()

        # Speicherpfad generieren
        file_path = self._generate_file_path(space_id, doc_id, file_name)

        # Optional verschluesseln
        if data.extra_encrypted and extra_password:
            salt, nonce, ciphertext = self.encryption_service.encrypt(
                file_content, extra_password
            )
            # Speichere verschluesselt: salt + nonce + ciphertext
            file_content = salt + nonce + ciphertext

        # Dokument erstellen (noch ohne commit)
        document = PrivatDocument(
            id=doc_id,
            space_id=space_id,
            folder_id=data.folder_id,
            title=data.title,
            description=data.description,
            document_type=data.document_type.value if isinstance(data.document_type, PrivatDocumentType) else data.document_type,
            tags=data.tags,
            file_path=file_path,
            file_name=file_name,
            file_size=len(file_content),
            mime_type=mime_type,
            extra_encrypted=data.extra_encrypted,
            password_hint=data.password_hint if data.extra_encrypted else None,
            encryption_salt=None,  # Salt ist in der Datei
            created_at=utc_now(),
            updated_at=utc_now(),
        )

        # Transaction Safety: File + DB Commit als atomare Operation
        # Bei Fehler wird die Datei wieder geloescht
        file_saved = False
        try:
            # Datei speichern
            await self._save_file(file_path, file_content)
            file_saved = True

            # DB-Eintrag erstellen und committen
            db.add(document)
            await db.commit()
            await db.refresh(document)

        except Exception as e:
            # Rollback DB falls noetig
            await db.rollback()

            # Cleanup: Datei loeschen wenn bereits gespeichert
            if file_saved:
                try:
                    await self._delete_file(file_path)
                    logger.info(
                        "orphaned_file_cleaned",
                        file_path=file_path,
                        reason=safe_error_detail(e, "Dokument")
                    )
                except Exception as cleanup_error:
                    logger.error(
                        "orphaned_file_cleanup_failed",
                        file_path=file_path,
                        error=str(cleanup_error)
                    )

            # Exception weiterwerfen
            raise

        logger.info(
            "privat_document_created",
            document_id=str(doc_id),
            space_id=str(space_id),
            encrypted=data.extra_encrypted,
        )

        # GDPR Audit Logging (MANDATORY)
        audit = get_audit_logger()
        await audit.log_event(
            event_type=SecurityEventType.PRIVAT_DOCUMENT_CREATED,
            resource_type="privat_document",
            resource_id=str(doc_id),
            details={
                "space_id": str(space_id),
                "document_type": str(data.document_type),
                "encrypted": data.extra_encrypted,
                "file_size": len(file_content),
            },
        )

        return document

    def _generate_file_path(
        self,
        space_id: uuid.UUID,
        doc_id: uuid.UUID,
        file_name: str,
    ) -> str:
        """Generiert den Speicherpfad fuer ein Dokument.

        Args:
            space_id: Space-ID
            doc_id: Dokument-ID
            file_name: Original-Dateiname

        Returns:
            Relativer Speicherpfad

        Security:
            - Dateiname wird bereinigt (Path-Traversal-Schutz)
            - Nur Extension wird verwendet, Rest ist UUID-basiert
        """
        # Security: Dateiname bereinigen
        safe_name = self._sanitize_filename(file_name)

        # Verwende UUID-Prefix fuer Verteilung
        prefix = str(doc_id)[:2]
        ext = os.path.splitext(safe_name)[1]

        # Validiere Extension (nur sichere Zeichen)
        if ext and not re.match(r'^\.[a-zA-Z0-9]+$', ext):
            ext = ""

        return f"{space_id}/{prefix}/{doc_id}{ext}"

    async def _save_file(self, file_path: str, content: bytes) -> None:
        """Speichert eine Datei im Storage.

        Args:
            file_path: Relativer Pfad
            content: Datei-Inhalt

        Raises:
            PathTraversalError: Bei Path-Traversal-Versuch
        """
        # Security: Validiere dass Pfad innerhalb Basis liegt
        full_path = self._validate_path_within_base(file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        with open(full_path, "wb") as f:
            f.write(content)

    async def _read_file(self, file_path: str) -> bytes:
        """Liest eine Datei aus dem Storage.

        Args:
            file_path: Relativer Pfad

        Returns:
            Datei-Inhalt

        Raises:
            PathTraversalError: Bei Path-Traversal-Versuch
        """
        # Security: Validiere dass Pfad innerhalb Basis liegt
        full_path = self._validate_path_within_base(file_path)
        with open(full_path, "rb") as f:
            return f.read()

    async def _delete_file(self, file_path: str) -> None:
        """Loescht eine Datei aus dem Storage.

        Args:
            file_path: Relativer Pfad

        Raises:
            PathTraversalError: Bei Path-Traversal-Versuch
        """
        # Security: Validiere dass Pfad innerhalb Basis liegt
        full_path = self._validate_path_within_base(file_path)
        if os.path.exists(full_path):
            os.remove(full_path)

    async def get_by_id(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
    ) -> Optional[PrivatDocument]:
        """Holt ein Dokument nach ID.

        WARNUNG: Diese Methode fuehrt KEINEN Access-Check durch!
        Fuer API-Aufrufe IMMER get_by_id_with_access_check() verwenden!

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID

        Returns:
            Dokument oder None
        """
        result = await db.execute(
            select(PrivatDocument).where(PrivatDocument.id == document_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_with_access_check(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        requesting_user_id: uuid.UUID,
    ) -> Optional[PrivatDocument]:
        """Holt ein Dokument nach ID MIT Access-Check.

        SECURITY: Diese Methode ist IDOR-sicher:
        - Access-Check erfolgt VOR Rueckgabe des Dokuments
        - Gibt None zurueck wenn Dokument nicht existiert ODER kein Zugriff
        - Keine Information Disclosure ueber Existenz fremder Dokumente

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            requesting_user_id: User-ID fuer Zugriffskontrolle (REQUIRED)

        Returns:
            Dokument wenn existiert UND Zugriff erlaubt, sonst None
        """
        try:
            return await self._verify_document_access(
                db, document_id, requesting_user_id, "read"
            )
        except AccessDeniedError:
            # SECURITY: Einheitliche Antwort - kein Unterschied zwischen
            # "nicht gefunden" und "kein Zugriff" (IDOR-Schutz)
            return None

    async def get_by_id_with_space_and_access_check(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        requesting_user_id: uuid.UUID,
    ) -> Optional[Tuple[PrivatDocument, PrivatSpace]]:
        """Holt Dokument UND Space in EINER atomaren Operation (TOCTOU-sicher).

        SECURITY FIX (Iteration 19): Diese Methode verhindert CWE-367 TOCTOU:
        - Document und Space werden in EINER DB-Query geholt
        - Access-Check und Daten-Abruf sind atomar
        - Kein separater get_by_id() nach Access-Check noetig
        - Verhindert Race Conditions zwischen Check und Use

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            requesting_user_id: User-ID fuer Zugriffskontrolle (REQUIRED)

        Returns:
            Tuple (Document, Space) wenn Zugriff erlaubt, sonst None
        """
        from app.db.models import PrivatSpaceAccess


        # SECURITY: Hole Dokument MIT Space in EINER Query (TOCTOU-sicher!)
        result = await db.execute(
            select(PrivatDocument, PrivatSpace)
            .join(PrivatSpace, PrivatDocument.space_id == PrivatSpace.id)
            .where(PrivatDocument.id == document_id)
        )
        row = result.first()

        if not row:
            # SECURITY: Einheitliche Antwort - keine Info ueber Existenz
            return None

        document, space = row

        # Owner hat immer vollen Zugriff
        if space.owner_id == requesting_user_id:
            return (document, space)

        # Pruefe explizite Berechtigung
        # SECURITY: expires_at Validierung - abgelaufene Zugriffe ignorieren!
        from datetime import timezone
        now = datetime.now(timezone.utc)

        access_result = await db.execute(
            select(PrivatSpaceAccess)
            .where(
                PrivatSpaceAccess.space_id == space.id,
                PrivatSpaceAccess.user_id == requesting_user_id,
                PrivatSpaceAccess.is_active == True,
                or_(
                    PrivatSpaceAccess.expires_at.is_(None),
                    PrivatSpaceAccess.expires_at > now,
                ),
            )
        )
        access = access_result.scalar_one_or_none()

        if not access:
            # SECURITY: Einheitliche Antwort (IDOR-Schutz)
            return None

        return (document, space)

    async def get_content(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        password: Optional[str] = None,
        requesting_user_id: uuid.UUID = None,  # type: ignore  # Required at runtime
    ) -> Optional[Tuple[bytes, str]]:
        """Holt den Inhalt eines Dokuments.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            password: Optional Passwort fuer verschluesselte Dokumente
            requesting_user_id: REQUIRED User-ID fuer Service-Level Zugriffskontrolle

        Returns:
            Tuple von (content, mime_type) oder None

        Raises:
            AccessDeniedError: Wenn kein Zugriff erlaubt
            ValueError: Wenn requesting_user_id nicht gesetzt (Security Requirement)

        Security:
            IDOR-Schutz: Zugriff wird IMMER verifiziert (Enterprise Requirement)
        """
        # SECURITY: requesting_user_id ist PFLICHT (Enterprise Requirement)
        if requesting_user_id is None:
            raise ValueError("requesting_user_id ist erforderlich (Security Requirement)")

        # Service-Level Access Control (IDOR-Schutz)
        document = await self._verify_document_access(
            db, document_id, requesting_user_id, "read"
        )

        content = await self._read_file(document.file_path)

        # Entschluesseln wenn noetig
        if document.extra_encrypted:
            if not password:
                raise ValueError("Passwort erforderlich fuer verschluesseltes Dokument")

            salt = content[:32]
            nonce = content[32:44]
            ciphertext = content[44:]

            # SECURITY: Async decrypt mit Redis-basiertem Brute-Force-Tracking
            # SECURITY FIX (Iteration 19): HMAC-basierter Identifier (nicht erratbar)
            brute_force_identifier = generate_brute_force_identifier(
                document_id=str(document_id),
                user_id=str(requesting_user_id),
            )
            decrypted = await self.encryption_service.decrypt_async(
                ciphertext, password, salt, nonce,
                identifier=brute_force_identifier
            )
            if decrypted is None:
                # SECURITY FIX (Iteration 19): Bereinige sensible Daten bei Fehler
                del salt, nonce, ciphertext
                secure_memory_cleanup()
                raise ValueError("Falsches Passwort")

            content = decrypted

            # SECURITY FIX (Iteration 19): Bereinige temporaere sensible Variablen
            # CWE-226 (Sensitive Information in Resource Not Removed Before Reuse)
            # CWE-316 (Cleartext Storage of Sensitive Information in Memory)
            # Loesche Referenzen auf nicht mehr benoetigte sensible Daten
            del decrypted, salt, nonce, ciphertext
            # Trigger GC fuer nicht mehr referenzierte Objekte
            secure_memory_cleanup()

            # GDPR Audit: Decryption event (MANDATORY)
            audit = get_audit_logger()
            await audit.log_event(
                event_type=SecurityEventType.PRIVAT_DOCUMENT_DECRYPTED,
                user_id=str(requesting_user_id) if requesting_user_id else None,
                resource_type="privat_document",
                resource_id=str(document_id),
                details={"space_id": str(document.space_id)},
            )

        # GDPR Audit: Document download/access (MANDATORY)
        audit = get_audit_logger()
        await audit.log_event(
            event_type=SecurityEventType.PRIVAT_DOCUMENT_DOWNLOADED,
            user_id=str(requesting_user_id) if requesting_user_id else None,
            resource_type="privat_document",
            resource_id=str(document_id),
            details={
                "space_id": str(document.space_id),
                "encrypted": document.extra_encrypted,
            },
        )

        return content, document.mime_type

    async def list_documents(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        folder_id: Optional[uuid.UUID] = None,
        document_type: Optional[PrivatDocumentType] = None,
        search: Optional[str] = None,
        tags: Optional[List[str]] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PrivatDocumentListResponse:
        """Listet Dokumente mit Filterung.

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            folder_id: Optional Ordner-Filter
            document_type: Optional Typ-Filter
            search: Optional Suchbegriff
            tags: Optional Tag-Filter
            page: Seitennummer
            page_size: Elemente pro Seite

        Returns:
            Paginierte Dokumentliste
        """
        conditions = [PrivatDocument.space_id == space_id]

        if folder_id is not None:
            conditions.append(PrivatDocument.folder_id == folder_id)

        if document_type:
            conditions.append(PrivatDocument.document_type == document_type.value)

        if search:
            # SECURITY: Limit search string length to prevent DoS
            if len(search) > 500:
                raise ValueError("Suchbegriff zu lang (max 500 Zeichen)")
            search_term = f"%{search}%"
            conditions.append(
                or_(
                    PrivatDocument.title.ilike(search_term),
                    PrivatDocument.description.ilike(search_term),
                    PrivatDocument.file_name.ilike(search_term),
                )
            )

        # Count total
        count_query = select(func.count(PrivatDocument.id)).where(and_(*conditions))
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Fetch documents
        offset = (page - 1) * page_size
        query = (
            select(PrivatDocument)
            .where(and_(*conditions))
            .order_by(PrivatDocument.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )

        result = await db.execute(query)
        documents = result.scalars().all()

        items = [
            PrivatDocumentResponse(
                id=doc.id,
                space_id=doc.space_id,
                folder_id=doc.folder_id,
                title=doc.title,
                description=doc.description,
                document_type=PrivatDocumentType(doc.document_type),
                tags=doc.tags,
                file_path=doc.file_path,
                file_name=doc.file_name,
                file_size=doc.file_size,
                mime_type=doc.mime_type,
                extra_encrypted=doc.extra_encrypted,
                password_hint=doc.password_hint,
                created_at=doc.created_at,
                updated_at=doc.updated_at,
            )
            for doc in documents
        ]

        pages = (total + page_size - 1) // page_size if page_size > 0 else 0

        return PrivatDocumentListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    async def update(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        data: PrivatDocumentUpdate,
        requesting_user_id: Optional[uuid.UUID] = None,
    ) -> Optional[PrivatDocument]:
        """Aktualisiert ein Dokument.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            data: Update-Daten
            requesting_user_id: Optional User-ID fuer Service-Level Zugriffskontrolle

        Returns:
            Aktualisiertes Dokument oder None

        Raises:
            AccessDeniedError: Wenn requesting_user_id gesetzt und kein Schreibzugriff

        Security:
            IDOR-Schutz: Bei requesting_user_id wird Schreibzugriff verifiziert
        """
        # Service-Level Access Control (IDOR-Schutz)
        if requesting_user_id is not None:
            document = await self._verify_document_access(
                db, document_id, requesting_user_id, "write"
            )
        else:
            document = await self.get_by_id(db, document_id)
            if not document:
                return None

        # Race Condition Prevention: Row Lock (SELECT ... FOR UPDATE)
        # Re-fetch mit Row Lock um sicherzustellen, dass nur eine Transaktion gleichzeitig aendert
        lock_result = await db.execute(
            select(PrivatDocument)
            .where(PrivatDocument.id == document_id)
            .with_for_update(nowait=False)  # Warte auf Lock
        )
        locked_document = lock_result.scalar_one_or_none()
        if not locked_document:
            return None
        document = locked_document

        update_data = data.model_dump(exclude_unset=True)

        for key, value in update_data.items():
            if key == "document_type" and value:
                value = value.value if isinstance(value, PrivatDocumentType) else value
            setattr(document, key, value)

        document.updated_at = utc_now()

        await db.commit()
        await db.refresh(document)

        logger.info(
            "privat_document_updated",
            document_id=str(document_id),
        )

        # GDPR Audit Logging (MANDATORY)
        audit = get_audit_logger()
        await audit.log_event(
            event_type=SecurityEventType.PRIVAT_DOCUMENT_UPDATED,
            user_id=str(requesting_user_id) if requesting_user_id else None,
            resource_type="privat_document",
            resource_id=str(document_id),
            details={
                "space_id": str(document.space_id),
                "updated_fields": list(update_data.keys()),
            },
        )

        return document

    async def delete(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        requesting_user_id: Optional[uuid.UUID] = None,
    ) -> bool:
        """Loescht ein Dokument.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            requesting_user_id: Optional User-ID fuer Service-Level Zugriffskontrolle

        Returns:
            True wenn erfolgreich

        Raises:
            AccessDeniedError: Wenn requesting_user_id gesetzt und kein Admin-Zugriff

        Security:
            IDOR-Schutz: Bei requesting_user_id wird Admin-Zugriff verifiziert
        """
        # Service-Level Access Control (IDOR-Schutz)
        if requesting_user_id is not None:
            # Erst Access-Check, dann Lock
            await self._verify_document_access(
                db, document_id, requesting_user_id, "admin"  # Loeschen erfordert Admin
            )

        # Race Condition Prevention: Row Lock (SELECT ... FOR UPDATE)
        # Verhindert doppelte Loeschung oder Loeschung waehrend Update
        lock_result = await db.execute(
            select(PrivatDocument)
            .where(PrivatDocument.id == document_id)
            .with_for_update(nowait=False)
        )
        document = lock_result.scalar_one_or_none()
        if not document:
            return False

        # SECURITY: Soft-Delete statt Hard-Delete (GDPR-konform, Recovery moeglich)
        # Die Datei wird NICHT sofort geloescht - erst nach Retention-Period
        # durch einen separaten Cleanup-Task

        # Soft-Delete: Markiere als geloescht
        document.is_active = False
        document.deleted_at = utc_now()
        document.deleted_by_id = requesting_user_id

        await db.commit()
        await db.refresh(document)

        logger.info(
            "privat_document_soft_deleted",
            document_id=str(document_id),
            deleted_by=str(requesting_user_id) if requesting_user_id else None,
        )

        # GDPR Audit Logging (MANDATORY - document deletion is a critical event)
        audit = get_audit_logger()
        await audit.log_event(
            event_type=SecurityEventType.PRIVAT_DOCUMENT_DELETED,
            user_id=str(requesting_user_id) if requesting_user_id else None,
            resource_type="privat_document",
            resource_id=str(document_id),
            details={
                "space_id": str(document.space_id),
                "document_title": document.title,
                "was_encrypted": document.extra_encrypted,
                "soft_delete": True,
                "recovery_possible": True,
            },
            severity="warning",
        )

        return True

    async def restore(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        requesting_user_id: uuid.UUID,
    ) -> Optional[PrivatDocument]:
        """Stellt ein geloeschtes Dokument wieder her.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            requesting_user_id: User-ID fuer Access Control

        Returns:
            Wiederhergestelltes Dokument oder None

        Raises:
            AccessDeniedError: Wenn kein Admin-Zugriff
        """
        # Admin-Zugriff erforderlich
        await self._verify_document_access(
            db, document_id, requesting_user_id, "admin"
        )

        result = await db.execute(
            select(PrivatDocument)
            .where(
                PrivatDocument.id == document_id,
                PrivatDocument.deleted_at != None,  # Soft-Deleted Documents only
            )
            .with_for_update(nowait=False)
        )
        document = result.scalar_one_or_none()
        if not document:
            return None

        # Wiederherstellen (Soft-Delete rueckgaengig machen)
        document.deleted_at = None
        document.updated_at = utc_now()

        await db.commit()
        await db.refresh(document)

        logger.info(
            "privat_document_restored",
            document_id=str(document_id),
            restored_by=str(requesting_user_id),
        )

        # GDPR Audit Logging (MANDATORY)
        audit = get_audit_logger()
        await audit.log_event(
            event_type=SecurityEventType.PRIVAT_DOCUMENT_RESTORED,
            user_id=str(requesting_user_id),
            resource_type="privat_document",
            resource_id=str(document_id),
            details={
                "space_id": str(document.space_id),
                "document_title": document.title,
            },
            severity="info",
        )

        return document

    async def move_to_folder(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        folder_id: Optional[uuid.UUID],
        requesting_user_id: Optional[uuid.UUID] = None,
    ) -> Optional[PrivatDocument]:
        """Verschiebt ein Dokument in einen anderen Ordner.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            folder_id: Ziel-Ordner (None fuer Root)
            requesting_user_id: User-ID fuer Access Control (REQUIRED for security)

        Returns:
            Aktualisiertes Dokument oder None

        Raises:
            PermissionError: Kein Zugriff auf Dokument
        """
        # SECURITY: Access Control BEFORE any database modification
        if requesting_user_id is not None:
            await self._verify_document_access(
                db, document_id, requesting_user_id, "write"
            )

        # Race Condition Prevention: Row Lock (SELECT ... FOR UPDATE)
        lock_result = await db.execute(
            select(PrivatDocument)
            .where(PrivatDocument.id == document_id)
            .with_for_update(nowait=False)
        )
        document = lock_result.scalar_one_or_none()
        if not document:
            return None

        if folder_id:
            # Validiere dass Ordner existiert und zum gleichen Space gehoert
            folder_result = await db.execute(
                select(PrivatFolder).where(PrivatFolder.id == folder_id)
            )
            folder = folder_result.scalar_one_or_none()
            if not folder or folder.space_id != document.space_id:
                raise ValueError("Ungültiger Zielordner")

        old_folder_id = document.folder_id
        document.folder_id = folder_id
        document.updated_at = utc_now()

        await db.commit()
        await db.refresh(document)

        logger.info(
            "privat_document_moved",
            document_id=str(document_id),
            folder_id=str(folder_id) if folder_id else None,
            requesting_user_id=str(requesting_user_id) if requesting_user_id else None,
        )

        # GDPR Audit Logging (MANDATORY - document move is a significant event)
        audit = get_audit_logger()
        await audit.log_event(
            event_type=SecurityEventType.PRIVAT_DOCUMENT_UPDATED,
            user_id=str(requesting_user_id) if requesting_user_id else None,
            resource_type="privat_document",
            resource_id=str(document_id),
            details={
                "action": "move_to_folder",
                "space_id": str(document.space_id),
                "old_folder_id": str(old_folder_id) if old_folder_id else None,
                "new_folder_id": str(folder_id) if folder_id else None,
            },
            severity="info",
        )

        return document

    async def change_encryption(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        current_password: Optional[str],
        new_password: Optional[str],
        password_hint: Optional[str] = None,
        requesting_user_id: Optional[uuid.UUID] = None,
    ) -> Optional[PrivatDocument]:
        """Aendert die Verschluesselung eines Dokuments.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            current_password: Aktuelles Passwort (bei verschluesseltem Dokument)
            new_password: Neues Passwort (None zum Entschluesseln)
            password_hint: Optional neuer Passwort-Hinweis
            requesting_user_id: User-ID fuer Access Control (REQUIRED for security)

        Returns:
            Aktualisiertes Dokument oder None

        Raises:
            PermissionError: Kein Zugriff auf Dokument
            ValueError: Falsches Passwort oder fehlendes Passwort
        """
        # SECURITY: Access Control BEFORE any file operations
        # Changing encryption is a CRITICAL operation - strict access control required
        if requesting_user_id is not None:
            await self._verify_document_access(
                db, document_id, requesting_user_id, "write"
            )

        # Race Condition Prevention: Row Lock (SELECT ... FOR UPDATE)
        # Verschluesselung aendern ist kritisch - Lock erforderlich
        lock_result = await db.execute(
            select(PrivatDocument)
            .where(PrivatDocument.id == document_id)
            .with_for_update(nowait=False)
        )
        document = lock_result.scalar_one_or_none()
        if not document:
            return None

        was_encrypted = document.extra_encrypted

        # Inhalt laden und ggf. entschluesseln
        content = await self._read_file(document.file_path)

        if document.extra_encrypted:
            if not current_password:
                raise ValueError("Aktuelles Passwort erforderlich")

            old_salt = content[:32]
            old_nonce = content[32:44]
            old_ciphertext = content[44:]

            # SECURITY: Async decrypt mit Redis-basiertem Brute-Force-Tracking
            # SECURITY FIX (Iteration 19): HMAC-basierter Identifier (nicht erratbar)
            brute_force_identifier = generate_brute_force_identifier(
                document_id=str(document_id),
                user_id=str(requesting_user_id) if requesting_user_id else "system",
            )
            decrypted = await self.encryption_service.decrypt_async(
                old_ciphertext, current_password, old_salt, old_nonce,
                identifier=brute_force_identifier
            )
            if decrypted is None:
                # SECURITY FIX (Iteration 19): Bereinige sensible Daten bei Fehler
                del old_salt, old_nonce, old_ciphertext
                secure_memory_cleanup()
                raise ValueError("Falsches Passwort")

            content = decrypted

            # SECURITY FIX (Iteration 19): Bereinige temporaere sensible Variablen
            # CWE-226/CWE-316: Loesche nicht mehr benoetigte sensible Daten
            del decrypted, old_salt, old_nonce, old_ciphertext
            secure_memory_cleanup()

        # Neu verschluesseln oder unverschluesselt speichern
        if new_password:
            new_salt, new_nonce, new_ciphertext = self.encryption_service.encrypt(
                content, new_password
            )
            # SECURITY FIX (Iteration 19): Plaintext vor Ueberschreibung bereinigen
            del content
            secure_memory_cleanup()
            content = new_salt + new_nonce + new_ciphertext
            # Bereinige temporaere Verschluesselungsdaten
            del new_salt, new_nonce, new_ciphertext
            document.extra_encrypted = True
            document.password_hint = password_hint
        else:
            document.extra_encrypted = False
            document.password_hint = None

        # Datei ueberschreiben
        await self._save_file(document.file_path, content)
        document.file_size = len(content)

        # SECURITY FIX (Iteration 19): Bereinige content nach dem Speichern
        del content
        secure_memory_cleanup()
        document.updated_at = utc_now()

        await db.commit()
        await db.refresh(document)

        logger.info(
            "privat_document_encryption_changed",
            document_id=str(document_id),
            encrypted=document.extra_encrypted,
            requesting_user_id=str(requesting_user_id) if requesting_user_id else None,
        )

        # GDPR Audit Logging (MANDATORY - encryption change is a CRITICAL security event)
        audit = get_audit_logger()
        await audit.log_event(
            event_type=SecurityEventType.PRIVAT_DOCUMENT_UPDATED,
            user_id=str(requesting_user_id) if requesting_user_id else None,
            resource_type="privat_document",
            resource_id=str(document_id),
            details={
                "action": "change_encryption",
                "space_id": str(document.space_id),
                "was_encrypted": was_encrypted,
                "now_encrypted": document.extra_encrypted,
                "encryption_changed": was_encrypted != document.extra_encrypted,
            },
            severity="warning",
        )

        return document
