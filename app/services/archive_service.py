"""GoBD Archive Service - Revisionssichere Dokumentenarchivierung.

Implementiert die gesetzlichen Anforderungen nach GoBD:
- Nachvollziehbarkeit: Vollstaendiger Audit-Trail
- Unveraenderbarkeit: SHA-256 Hash-Signatur
- Vollstaendigkeit: Aufbewahrungsfristen-Management
- Ordnung: Kategorisierung nach Dokumenttyp

Basiert auf:
- §147 AO (Abgabenordnung)
- §257 HGB (Handelsgesetzbuch)
- §14b UStG (Umsatzsteuergesetz)
"""

import hashlib
import uuid
from datetime import date, datetime, timedelta
from typing import Optional

import structlog
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import (
    DocumentNotFoundError,
    ArchiveError,
    VerificationError,
    ImmutabilityViolationError,
)
from app.db.models import (
    Document,
    DocumentArchive,
    RetentionSetting,
    RetentionCategory,
    HashAlgorithm,
    User,
)

logger = structlog.get_logger(__name__)


# Standard-Aufbewahrungsfristen nach deutschem Recht
DEFAULT_RETENTION_YEARS: dict[str, int] = {
    RetentionCategory.INVOICE.value: 10,         # §147 AO, §14b UStG
    RetentionCategory.CONTRACT.value: 10,        # §147 AO, §257 HGB
    RetentionCategory.CORRESPONDENCE.value: 6,   # §257 HGB
    RetentionCategory.BOOKING_DOCUMENT.value: 10,  # §147 AO
    RetentionCategory.ANNUAL_REPORT.value: 10,   # §257 HGB
    RetentionCategory.TAX_DOCUMENT.value: 10,    # §147 AO
    RetentionCategory.EMPLOYEE_DOCUMENT.value: 10,  # §257 HGB
    RetentionCategory.OTHER.value: 6,            # §147 AO (Minimum)
}


class ArchiveService:
    """Service fuer GoBD-konforme Dokumentenarchivierung."""

    async def archive_document(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
        retention_category: str = RetentionCategory.OTHER.value,
        signature_certificate: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> DocumentArchive:
        """Archiviert ein Dokument GoBD-konform mit SHA-256 Signatur.

        Args:
            db: Datenbank-Session
            document_id: ID des zu archivierenden Dokuments
            user_id: ID des archivierenden Benutzers
            retention_category: Aufbewahrungskategorie
            signature_certificate: Optionales TSA-Zertifikat
            metadata: Zusaetzliche Metadaten

        Returns:
            DocumentArchive: Das erstellte Archiv-Objekt

        Raises:
            DocumentNotFoundError: Wenn das Dokument nicht existiert
            ArchiveError: Wenn das Dokument bereits archiviert ist
        """
        # Dokument laden
        result = await db.execute(
            select(Document)
            .options(selectinload(Document.archive))
            .where(Document.id == document_id)
        )
        document = result.scalar_one_or_none()

        if not document:
            raise DocumentNotFoundError(
                f"Dokument mit ID {document_id} nicht gefunden"
            )

        if document.is_archived:
            raise ArchiveError(
                f"Dokument {document_id} ist bereits archiviert"
            )

        # Hash berechnen aus Dokument-Inhalt
        content_hash = await self._compute_document_hash(document)

        # Aufbewahrungsfrist ermitteln
        retention_years = await self._get_retention_years(
            db, retention_category
        )
        retention_expires_at = date.today() + timedelta(days=retention_years * 365)

        # Archiv-Eintrag erstellen
        archive = DocumentArchive(
            id=uuid.uuid4(),
            document_id=document_id,
            company_id=document.company_id,
            content_hash=content_hash,
            hash_algorithm=HashAlgorithm.SHA256.value,
            signature_timestamp=datetime.now(),
            signature_certificate=signature_certificate,
            retention_category=retention_category,
            retention_years=retention_years,
            retention_expires_at=retention_expires_at,
            archived_by_id=user_id,
            archive_metadata=metadata or {},
        )

        # Dokument als archiviert markieren
        document.is_archived = True
        document.archived_at = datetime.now()

        db.add(archive)
        await db.commit()
        await db.refresh(archive)

        logger.info(
            "document_archived",
            document_id=str(document_id),
            archive_id=str(archive.id),
            retention_category=retention_category,
            retention_years=retention_years,
            content_hash=content_hash[:16] + "...",
        )

        return archive

    async def verify_document_integrity(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
    ) -> bool:
        """Verifiziert die Integritaet eines archivierten Dokuments.

        Vergleicht den aktuellen Hash mit dem archivierten Hash.

        Args:
            db: Datenbank-Session
            document_id: ID des zu verifizierenden Dokuments

        Returns:
            bool: True wenn Integritaet gewaehrleistet, False wenn kompromittiert

        Raises:
            DocumentNotFoundError: Wenn das Dokument nicht existiert
            ArchiveError: Wenn das Dokument nicht archiviert ist
        """
        # Dokument mit Archiv laden
        result = await db.execute(
            select(Document)
            .options(selectinload(Document.archive))
            .where(Document.id == document_id)
        )
        document = result.scalar_one_or_none()

        if not document:
            raise DocumentNotFoundError(
                f"Dokument mit ID {document_id} nicht gefunden"
            )

        if not document.archive:
            raise ArchiveError(
                f"Dokument {document_id} ist nicht archiviert"
            )

        archive = document.archive

        # Aktuellen Hash berechnen
        current_hash = await self._compute_document_hash(document)

        # Mit gespeichertem Hash vergleichen
        is_valid = current_hash == archive.content_hash

        # Verifikationsstatus aktualisieren
        archive.last_verification_at = datetime.now()
        archive.is_verified = is_valid
        if not is_valid:
            archive.verification_failed_reason = (
                f"Hash-Mismatch: Erwartet {archive.content_hash[:16]}..., "
                f"gefunden {current_hash[:16]}..."
            )
            logger.error(
                "document_verification_failed",
                document_id=str(document_id),
                expected_hash=archive.content_hash[:16],
                actual_hash=current_hash[:16],
            )
        else:
            archive.verification_failed_reason = None
            logger.info(
                "document_verification_passed",
                document_id=str(document_id),
            )

        await db.commit()
        return is_valid

    async def get_archive(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
    ) -> Optional[DocumentArchive]:
        """Holt die Archiv-Informationen fuer ein Dokument.

        Args:
            db: Datenbank-Session
            document_id: ID des Dokuments

        Returns:
            DocumentArchive oder None
        """
        result = await db.execute(
            select(DocumentArchive)
            .where(DocumentArchive.document_id == document_id)
        )
        return result.scalar_one_or_none()

    async def get_expiring_archives(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        days_until_expiry: int = 90,
    ) -> list[DocumentArchive]:
        """Findet Archive, die bald ablaufen.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            days_until_expiry: Tage bis zum Ablauf

        Returns:
            Liste von bald ablaufenden Archiven
        """
        expiry_threshold = date.today() + timedelta(days=days_until_expiry)

        result = await db.execute(
            select(DocumentArchive)
            .where(
                and_(
                    DocumentArchive.company_id == company_id,
                    DocumentArchive.retention_expires_at <= expiry_threshold,
                    DocumentArchive.retention_reminder_sent == False,
                )
            )
            .order_by(DocumentArchive.retention_expires_at)
        )
        return list(result.scalars().all())

    async def mark_reminder_sent(
        self,
        db: AsyncSession,
        archive_id: uuid.UUID,
    ) -> None:
        """Markiert einen Archiv-Eintrag als erinnert.

        Args:
            db: Datenbank-Session
            archive_id: Archiv-ID
        """
        result = await db.execute(
            select(DocumentArchive)
            .where(DocumentArchive.id == archive_id)
        )
        archive = result.scalar_one_or_none()

        if archive:
            archive.retention_reminder_sent = True
            archive.retention_reminder_at = datetime.now()
            await db.commit()

    async def check_immutability(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
    ) -> bool:
        """Prueft, ob ein Dokument unveraenderbar ist (archiviert).

        Args:
            db: Datenbank-Session
            document_id: ID des Dokuments

        Returns:
            bool: True wenn unveraenderbar
        """
        result = await db.execute(
            select(Document.is_archived)
            .where(Document.id == document_id)
        )
        row = result.scalar_one_or_none()
        return row is True

    async def validate_modification_allowed(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
    ) -> None:
        """Validiert, dass ein Dokument modifiziert werden darf.

        Args:
            db: Datenbank-Session
            document_id: ID des Dokuments

        Raises:
            ImmutabilityViolationError: Wenn Dokument archiviert ist
        """
        if await self.check_immutability(db, document_id):
            raise ImmutabilityViolationError(
                f"Dokument {document_id} ist archiviert und darf nicht "
                "veraendert werden (GoBD: Unveraenderbarkeit)"
            )

    async def get_retention_settings(
        self,
        db: AsyncSession,
    ) -> list[RetentionSetting]:
        """Holt alle Aufbewahrungsfristen-Einstellungen.

        Args:
            db: Datenbank-Session

        Returns:
            Liste aller RetentionSettings
        """
        result = await db.execute(
            select(RetentionSetting)
            .order_by(RetentionSetting.category)
        )
        return list(result.scalars().all())

    async def update_retention_setting(
        self,
        db: AsyncSession,
        category: str,
        retention_years: int,
        reminder_days_before: int,
        auto_delete_enabled: bool,
        updated_by_id: uuid.UUID,
    ) -> RetentionSetting:
        """Aktualisiert eine Aufbewahrungsfristen-Einstellung.

        Args:
            db: Datenbank-Session
            category: Kategorie-Name
            retention_years: Aufbewahrungsdauer in Jahren
            reminder_days_before: Tage vor Ablauf fuer Warnung
            auto_delete_enabled: Auto-Loeschung aktiviert
            updated_by_id: ID des aendernden Benutzers

        Returns:
            Aktualisierte RetentionSetting
        """
        result = await db.execute(
            select(RetentionSetting)
            .where(RetentionSetting.category == category)
        )
        setting = result.scalar_one_or_none()

        if not setting:
            raise ArchiveError(f"Kategorie '{category}' nicht gefunden")

        setting.retention_years = retention_years
        setting.reminder_days_before = reminder_days_before
        setting.auto_delete_enabled = auto_delete_enabled
        setting.updated_by_id = updated_by_id

        await db.commit()
        await db.refresh(setting)

        logger.info(
            "retention_setting_updated",
            category=category,
            retention_years=retention_years,
            updated_by=str(updated_by_id),
        )

        return setting

    async def get_archive_statistics(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> dict:
        """Holt Statistiken zur Archivierung fuer eine Firma.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID

        Returns:
            Dictionary mit Archiv-Statistiken
        """
        from sqlalchemy import func

        # Gesamtzahl archivierter Dokumente
        total_result = await db.execute(
            select(func.count(DocumentArchive.id))
            .where(DocumentArchive.company_id == company_id)
        )
        total_archived = total_result.scalar() or 0

        # Nach Kategorie
        category_result = await db.execute(
            select(
                DocumentArchive.retention_category,
                func.count(DocumentArchive.id)
            )
            .where(DocumentArchive.company_id == company_id)
            .group_by(DocumentArchive.retention_category)
        )
        by_category = dict(category_result.all())

        # Bald ablaufend (naechste 90 Tage)
        expiring_soon = await db.execute(
            select(func.count(DocumentArchive.id))
            .where(
                and_(
                    DocumentArchive.company_id == company_id,
                    DocumentArchive.retention_expires_at <= date.today() + timedelta(days=90),
                )
            )
        )
        expiring_count = expiring_soon.scalar() or 0

        # Verifikationsstatus
        unverified_result = await db.execute(
            select(func.count(DocumentArchive.id))
            .where(
                and_(
                    DocumentArchive.company_id == company_id,
                    DocumentArchive.is_verified == False,
                )
            )
        )
        unverified_count = unverified_result.scalar() or 0

        return {
            "total_archived": total_archived,
            "by_category": by_category,
            "expiring_soon_90_days": expiring_count,
            "verification_failed": unverified_count,
        }

    # =========================================================================
    # Private Hilfsmethoden
    # =========================================================================

    async def _compute_document_hash(
        self,
        document: Document,
        algorithm: str = HashAlgorithm.SHA256.value,
    ) -> str:
        """Berechnet den Hash eines Dokuments.

        Hasht eine Kombination aus:
        - Dateiinhalt (via checksum)
        - Metadaten (filename, mime_type)
        - Extrahierter Text

        Args:
            document: Das Dokument
            algorithm: Hash-Algorithmus

        Returns:
            Hex-String des Hashes
        """
        # Hash-Algorithmus waehlen
        if algorithm == HashAlgorithm.SHA256.value:
            hasher = hashlib.sha256()
        elif algorithm == HashAlgorithm.SHA384.value:
            hasher = hashlib.sha384()
        elif algorithm == HashAlgorithm.SHA512.value:
            hasher = hashlib.sha512()
        else:
            hasher = hashlib.sha256()

        # Dokument-Attribute in den Hash einbeziehen
        # (unveraenderliche Eigenschaften des Dokuments)
        hasher.update(document.filename.encode("utf-8"))
        hasher.update(document.original_filename.encode("utf-8"))
        if document.mime_type:
            hasher.update(document.mime_type.encode("utf-8"))
        if document.checksum:
            hasher.update(document.checksum.encode("utf-8"))
        if document.extracted_text:
            hasher.update(document.extracted_text.encode("utf-8"))
        if document.file_size:
            hasher.update(str(document.file_size).encode("utf-8"))

        return hasher.hexdigest()

    async def _get_retention_years(
        self,
        db: AsyncSession,
        category: str,
    ) -> int:
        """Ermittelt die Aufbewahrungsdauer fuer eine Kategorie.

        Args:
            db: Datenbank-Session
            category: Kategorie-Name

        Returns:
            Aufbewahrungsdauer in Jahren
        """
        result = await db.execute(
            select(RetentionSetting.retention_years)
            .where(RetentionSetting.category == category)
        )
        years = result.scalar_one_or_none()

        if years is not None:
            return years

        # Fallback auf Default-Werte
        return DEFAULT_RETENTION_YEARS.get(category, 6)


# Singleton-Instanz
archive_service = ArchiveService()
