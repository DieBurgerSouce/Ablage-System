"""GoBD Archive Service - Revisionssichere Dokumenten-Archivierung.

Implementiert die GoBD-konforme Archivierung mit:
- SHA-256 Hash-Signaturen
- RFC 3161 Zeitstempel (optional)
- WORM-Semantik (Write Once Read Many)
- Integritaetspruefungen

Die Archivierung erfuellt die GoBD-Kriterien:
- Nachvollziehbarkeit: Audit-Trail fuer jeden Zugriff
- Unveraenderbarkeit: Hash-Signatur und WORM
- Vollstaendigkeit: Aufbewahrungsfristen-Management
- Ordnung: Kategorisierung nach Dokumenttyp
"""

import hashlib
import uuid
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any, BinaryIO
from dataclasses import dataclass
from enum import Enum
import base64

import structlog
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, DocumentArchive, HashAlgorithm
from app.services.storage_service import StorageService
from app.db.bpmn_models.gobd import (
    ArchiveIntegrityCheck,
    IntegrityCheckStatus,
    TimestampAuthorityConfig,
    AuditChainEventType,
)
from app.services.compliance.audit_chain_service import (
    audit_chain_service,
    ChainEntry,
    log_document_event,
)
from app.services.compliance.retention_service import retention_service
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


class ArchiveError(Exception):
    """Fehler bei der Archivierung."""
    pass


class IntegrityError(Exception):
    """Integritaetsfehler bei der Verifikation."""
    pass


@dataclass
class ArchiveResult:
    """Ergebnis einer Archivierung."""
    archive_id: uuid.UUID
    document_id: uuid.UUID
    content_hash: str
    hash_algorithm: str
    retention_expires_at: date
    tsa_timestamp: Optional[datetime] = None


@dataclass
class IntegrityCheckResult:
    """Ergebnis einer Integritaetspruefung."""
    archive_id: uuid.UUID
    status: IntegrityCheckStatus
    expected_hash: str
    actual_hash: Optional[str]
    hash_match: bool
    tsa_verified: Optional[bool] = None
    error_message: Optional[str] = None
    duration_ms: float = 0


class GoBDArchiveService:
    """Service fuer GoBD-konforme Dokumenten-Archivierung.

    Hauptfunktionen:
    - Dokumente revisionssicher archivieren
    - Hash-Signaturen erstellen und pruefen
    - RFC 3161 Zeitstempel (optional)
    - Integritaetspruefungen durchfuehren
    """

    HASH_ALGORITHM = HashAlgorithm.SHA256

    async def archive_document(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        company_id: uuid.UUID,
        category: str,
        document_content: bytes,
        document_date: Optional[date] = None,
        archived_by_id: Optional[uuid.UUID] = None,
        metadata: Optional[Dict[str, Any]] = None,
        use_tsa: bool = False,
    ) -> ArchiveResult:
        """Archiviert ein Dokument GoBD-konform.

        Args:
            db: Datenbank-Session
            document_id: ID des zu archivierenden Dokuments
            company_id: Firmen-ID
            category: Dokumentkategorie (fuer Aufbewahrungsfrist)
            document_content: Binaerer Inhalt des Dokuments
            document_date: Datum des Dokuments (fuer Fristberechnung)
            archived_by_id: User der archiviert
            metadata: Optionale Metadaten
            use_tsa: RFC 3161 Zeitstempel anfordern

        Returns:
            ArchiveResult mit Details

        Raises:
            ArchiveError: Bei Fehlern
        """
        # 1. Pruefe ob Dokument existiert
        document = await db.get(Document, document_id)
        if not document or document.company_id != company_id:
            raise ArchiveError("Dokument nicht gefunden oder keine Berechtigung")

        # 2. Pruefe ob bereits archiviert
        existing = await self._get_existing_archive(db, document_id)
        if existing:
            raise ArchiveError(
                f"Dokument ist bereits archiviert (Archive-ID: {existing.id})"
            )

        # 3. Berechne Hash
        content_hash = self._calculate_hash(document_content)

        # 4. Berechne Aufbewahrungsfrist
        doc_date = document_date or date.today()
        retention_expires = retention_service.calculate_expiry_date(category, doc_date)
        retention_years = retention_service.get_retention_years(category)

        # 5. Hole optionalen TSA-Zeitstempel
        tsa_timestamp = None
        tsa_token = None
        tsa_provider = None

        if use_tsa:
            tsa_result = await self._get_tsa_timestamp(db, company_id, content_hash)
            if tsa_result:
                tsa_timestamp = tsa_result.get("timestamp")
                tsa_token = tsa_result.get("token")
                tsa_provider = tsa_result.get("provider")

        # 6. Erstelle Archiv-Eintrag
        archive = DocumentArchive(
            document_id=document_id,
            company_id=company_id,
            content_hash=content_hash,
            hash_algorithm=self.HASH_ALGORITHM.value,
            signature_timestamp=datetime.utcnow(),
            signature_certificate=tsa_token,
            retention_category=category.lower(),
            retention_years=retention_years,
            retention_expires_at=retention_expires,
            archived_by_id=archived_by_id,
            archive_metadata=metadata or {},
            is_verified=True,
            last_verification_at=datetime.utcnow(),
        )

        db.add(archive)

        # 7. Aktualisiere Dokument-Status
        document.is_archived = True
        document.archived_at = datetime.utcnow()

        await db.flush()

        # 8. Log in Audit-Chain
        await log_document_event(
            db=db,
            company_id=company_id,
            event_type=AuditChainEventType.DOCUMENT_ARCHIVED,
            document_id=document_id,
            event_data={
                "archive_id": str(archive.id),
                "content_hash": content_hash[:16] + "...",
                "retention_category": category,
                "retention_expires_at": retention_expires.isoformat(),
                "tsa_used": use_tsa,
            },
            user_id=archived_by_id,
        )

        logger.info(
            "document_archived",
            document_id=str(document_id),
            archive_id=str(archive.id),
            category=category,
            retention_expires=retention_expires.isoformat(),
        )

        return ArchiveResult(
            archive_id=archive.id,
            document_id=document_id,
            content_hash=content_hash,
            hash_algorithm=self.HASH_ALGORITHM.value,
            retention_expires_at=retention_expires,
            tsa_timestamp=tsa_timestamp,
        )

    async def verify_archive_integrity(
        self,
        db: AsyncSession,
        archive_id: uuid.UUID,
        company_id: uuid.UUID,
        document_content: bytes,
        triggered_by_id: Optional[uuid.UUID] = None,
        check_type: str = "manual",
    ) -> IntegrityCheckResult:
        """Verifiziert die Integritaet eines archivierten Dokuments.

        Vergleicht den gespeicherten Hash mit dem aktuellen Hash
        des Dokument-Inhalts.

        Args:
            db: Datenbank-Session
            archive_id: Archiv-ID
            company_id: Firmen-ID
            document_content: Aktueller Dokument-Inhalt
            triggered_by_id: User der die Pruefung ausloest
            check_type: Art der Pruefung (manual, scheduled)

        Returns:
            IntegrityCheckResult mit Verifikationsstatus

        Raises:
            ValueError: Wenn Archiv nicht gefunden
        """
        start_time = datetime.utcnow()

        # Hole Archiv
        archive = await db.get(DocumentArchive, archive_id)
        if not archive or archive.company_id != company_id:
            raise ValueError("Archiv nicht gefunden oder keine Berechtigung")

        # Berechne aktuellen Hash
        actual_hash = self._calculate_hash(document_content)
        hash_match = archive.content_hash == actual_hash

        # Erstelle Check-Protokoll
        check = ArchiveIntegrityCheck(
            archive_id=archive_id,
            company_id=company_id,
            check_type=check_type,
            expected_hash=archive.content_hash,
            actual_hash=actual_hash,
            hash_match=hash_match,
            triggered_by_id=triggered_by_id,
        )

        if hash_match:
            check.status = IntegrityCheckStatus.PASSED.value

            # TODO: Optional TSA-Token verifizieren
            # check.tsa_verified = await self._verify_tsa_token(...)

            # Aktualisiere Archiv-Status
            archive.is_verified = True
            archive.last_verification_at = datetime.utcnow()
            archive.verification_failed_reason = None

            # Log Erfolg in Audit-Chain
            await log_document_event(
                db=db,
                company_id=company_id,
                event_type=AuditChainEventType.INTEGRITY_CHECK_PASSED,
                document_id=archive.document_id,
                event_data={
                    "archive_id": str(archive_id),
                    "check_type": check_type,
                },
                user_id=triggered_by_id,
            )
        else:
            check.status = IntegrityCheckStatus.FAILED.value
            check.error_message = "Hash-Werte stimmen nicht ueberein - moegliche Manipulation!"

            # Aktualisiere Archiv-Status
            archive.is_verified = False
            archive.verification_failed_reason = check.error_message

            # Log Fehler in Audit-Chain (KRITISCH!)
            await log_document_event(
                db=db,
                company_id=company_id,
                event_type=AuditChainEventType.INTEGRITY_CHECK_FAILED,
                document_id=archive.document_id,
                event_data={
                    "archive_id": str(archive_id),
                    "check_type": check_type,
                    "error": "hash_mismatch",
                },
                user_id=triggered_by_id,
            )

            logger.error(
                "integrity_check_failed",
                archive_id=str(archive_id),
                expected_hash=archive.content_hash[:16] + "...",
                actual_hash=actual_hash[:16] + "...",
            )

        # Timing
        duration = (datetime.utcnow() - start_time).total_seconds() * 1000
        check.completed_at = datetime.utcnow()
        check.duration_ms = int(duration)

        db.add(check)
        await db.flush()

        return IntegrityCheckResult(
            archive_id=archive_id,
            status=IntegrityCheckStatus(check.status),
            expected_hash=archive.content_hash,
            actual_hash=actual_hash,
            hash_match=hash_match,
            tsa_verified=check.tsa_verified,
            error_message=check.error_message,
            duration_ms=duration,
        )

    async def batch_verify_integrity(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        limit: int = 100,
        verify_older_than_days: int = 90,
        triggered_by_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """Batch-Verifikation aller Archive die laenger nicht geprueft wurden.

        Laedt Dokument-Inhalte aus MinIO Storage und verifiziert Hash-Integritaet.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            limit: Maximale Anzahl zu pruefender Archive
            verify_older_than_days: Nur Archive pruefen die aelter sind
            triggered_by_id: User-ID der die Verifikation ausgeloest hat

        Returns:
            Dict mit Statistiken
        """
        cutoff = datetime.utcnow() - timedelta(days=verify_older_than_days)

        # Finde Archive die geprueft werden muessen
        result = await db.execute(
            select(DocumentArchive)
            .where(
                and_(
                    DocumentArchive.company_id == company_id,
                    or_(
                        DocumentArchive.last_verification_at.is_(None),
                        DocumentArchive.last_verification_at < cutoff,
                    )
                )
            )
            .limit(limit)
        )
        archives = result.scalars().all()

        stats = {
            "archives_found": len(archives),
            "verified": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "errors": [],
        }

        if not archives:
            logger.info(
                "batch_verification_no_archives",
                company_id=str(company_id),
            )
            return stats

        # Initialisiere Storage-Service
        storage = StorageService()
        if not storage.available:
            stats["message"] = "Storage-Service nicht verfuegbar"
            logger.warning(
                "batch_verification_storage_unavailable",
                company_id=str(company_id),
            )
            return stats

        # Lade alle Dokumente fuer die Archive (fuer file_path)
        archive_doc_ids = [archive.document_id for archive in archives]
        doc_result = await db.execute(
            select(Document).where(
                Document.id.in_(archive_doc_ids),
                Document.company_id == company_id,
            )
        )
        documents = {doc.id: doc for doc in doc_result.scalars().all()}

        for archive in archives:
            document = documents.get(archive.document_id)

            if not document or not document.file_path:
                stats["skipped"] += 1
                stats["errors"].append({
                    "archive_id": str(archive.id),
                    "reason": "Dokument oder Dateipfad nicht gefunden",
                })
                continue

            try:
                # Lade Dokument-Inhalt aus Storage
                document_content = await storage.download_document(document.file_path)

                # Verifiziere Integritaet
                check_result = await self.verify_archive_integrity(
                    db=db,
                    archive_id=archive.id,
                    company_id=company_id,
                    document_content=document_content,
                    triggered_by_id=triggered_by_id,
                    check_type="batch",
                )

                stats["verified"] += 1
                if check_result.hash_match:
                    stats["passed"] += 1
                else:
                    stats["failed"] += 1
                    stats["errors"].append({
                        "archive_id": str(archive.id),
                        "reason": "Hash-Mismatch - moegliche Manipulation!",
                        "expected_hash": check_result.expected_hash[:16] + "...",
                        "actual_hash": check_result.actual_hash[:16] + "..." if check_result.actual_hash else None,
                    })

            except Exception as e:
                stats["skipped"] += 1
                stats["errors"].append({
                    "archive_id": str(archive.id),
                    "reason": safe_error_detail(e, "Archiv"),
                })
                logger.error(
                    "batch_verification_error",
                    archive_id=str(archive.id),
                    **safe_error_log(e),
                )

        logger.info(
            "batch_verification_completed",
            company_id=str(company_id),
            verified=stats["verified"],
            passed=stats["passed"],
            failed=stats["failed"],
            skipped=stats["skipped"],
        )

        return stats

    async def get_archive_by_document(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> Optional[DocumentArchive]:
        """Holt das Archiv fuer ein Dokument.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            company_id: Firmen-ID

        Returns:
            DocumentArchive oder None
        """
        result = await db.execute(
            select(DocumentArchive)
            .where(
                and_(
                    DocumentArchive.document_id == document_id,
                    DocumentArchive.company_id == company_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_archives_with_failed_verification(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> List[DocumentArchive]:
        """Holt alle Archive mit fehlgeschlagener Verifikation.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID

        Returns:
            Liste von Archiven mit Verifikationsfehlern
        """
        result = await db.execute(
            select(DocumentArchive)
            .where(
                and_(
                    DocumentArchive.company_id == company_id,
                    DocumentArchive.is_verified == False,
                )
            )
        )
        return list(result.scalars().all())

    async def get_archive_statistics(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Holt Archivierungs-Statistiken.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID

        Returns:
            Dict mit Statistiken
        """
        # Gesamtanzahl
        total_result = await db.execute(
            select(func.count()).select_from(DocumentArchive)
            .where(DocumentArchive.company_id == company_id)
        )
        total = total_result.scalar() or 0

        # Nach Kategorie
        category_result = await db.execute(
            select(
                DocumentArchive.retention_category,
                func.count().label("count"),
            )
            .where(DocumentArchive.company_id == company_id)
            .group_by(DocumentArchive.retention_category)
        )
        by_category = {row.retention_category: row.count for row in category_result.all()}

        # Verifikationsstatus
        verified_result = await db.execute(
            select(func.count()).select_from(DocumentArchive)
            .where(
                and_(
                    DocumentArchive.company_id == company_id,
                    DocumentArchive.is_verified == True,
                )
            )
        )
        verified = verified_result.scalar() or 0

        failed_result = await db.execute(
            select(func.count()).select_from(DocumentArchive)
            .where(
                and_(
                    DocumentArchive.company_id == company_id,
                    DocumentArchive.is_verified == False,
                )
            )
        )
        failed = failed_result.scalar() or 0

        # Mit TSA
        tsa_result = await db.execute(
            select(func.count()).select_from(DocumentArchive)
            .where(
                and_(
                    DocumentArchive.company_id == company_id,
                    DocumentArchive.signature_certificate.isnot(None),
                )
            )
        )
        with_tsa = tsa_result.scalar() or 0

        return {
            "total_archived": total,
            "by_category": by_category,
            "verification": {
                "verified": verified,
                "failed": failed,
                "verification_rate": round(verified / total * 100, 1) if total > 0 else 100,
            },
            "tsa_timestamped": with_tsa,
        }

    # ================== Helper Methods ==================

    def _calculate_hash(self, content: bytes) -> str:
        """Berechnet SHA-256 Hash des Inhalts."""
        return hashlib.sha256(content).hexdigest()

    async def _get_existing_archive(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
    ) -> Optional[DocumentArchive]:
        """Prueft ob ein Dokument bereits archiviert ist."""
        result = await db.execute(
            select(DocumentArchive)
            .where(DocumentArchive.document_id == document_id)
        )
        return result.scalar_one_or_none()

    async def _get_tsa_timestamp(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        content_hash: str,
    ) -> Optional[Dict[str, Any]]:
        """Holt einen RFC 3161 Zeitstempel von einem TSA.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            content_hash: Hash des zu signierenden Inhalts

        Returns:
            Dict mit timestamp, token, provider oder None
        """
        # Finde aktive TSA-Konfiguration
        result = await db.execute(
            select(TimestampAuthorityConfig)
            .where(
                and_(
                    TimestampAuthorityConfig.company_id == company_id,
                    TimestampAuthorityConfig.is_active == True,
                    TimestampAuthorityConfig.is_default == True,
                )
            )
        )
        tsa_config = result.scalar_one_or_none()

        if not tsa_config:
            # Kein TSA konfiguriert
            return None

        # TODO: Tatsaechlicher RFC 3161 Request
        # Dies erfordert einen HTTP-Client und ASN.1 Parsing
        # Beispiel-Implementierung:
        #
        # import requests
        # from asn1crypto import tsp, cms
        #
        # timestamp_req = tsp.TimeStampReq({
        #     'version': 1,
        #     'message_imprint': {
        #         'hash_algorithm': {'algorithm': 'sha256'},
        #         'hashed_message': bytes.fromhex(content_hash),
        #     },
        #     'cert_req': True,
        # })
        #
        # response = requests.post(
        #     tsa_config.endpoint_url,
        #     data=timestamp_req.dump(),
        #     headers={'Content-Type': 'application/timestamp-query'},
        # )
        #
        # tsp_response = tsp.TimeStampResp.load(response.content)
        # ...

        logger.warning(
            "tsa_timestamp_not_implemented",
            company_id=str(company_id),
            tsa_config=tsa_config.name,
        )

        return None


# Import fuer timedelta
from datetime import timedelta

# Singleton-Instanz
gobd_archive_service = GoBDArchiveService()
