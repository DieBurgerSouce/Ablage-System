# -*- coding: utf-8 -*-
"""Document Lifecycle Engine - GoBD-konforme Dokumenten-Lebenszyklusverwaltung.

Enterprise-Feature: Automatisierte Verwaltung des gesamten Dokumenten-Lebenszyklus
von Archivierung bis Vernichtung, konform mit GoBD, §147 AO und §257 HGB.

Kernfunktionen:
- Scan auf ablaufende Aufbewahrungsfristen
- Automatische Archivierung mit Hash-Verifikation
- Vernichtungsprotokolle nach GoBD
- Lifecycle-Dashboard mit Statistiken
- Fristverlängerung mit Audit-Trail
- Zusammenfassung nach Kategorie und Status
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

import structlog
from sqlalchemy import select, and_, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ArchiveError
from app.db.models import (
    Document,
    DocumentArchive,
    RetentionSetting,
    AuditLog,
)
from app.services.archive_service import archive_service

logger = structlog.get_logger(__name__)


class DocumentLifecycleEngine:
    """Engine fuer GoBD-konforme Dokumenten-Lebenszyklus-Verwaltung.

    Verwaltet den gesamten Lebenszyklus archivierter Dokumente:
    - Ueberwachung ablaufender Aufbewahrungsfristen
    - Automatische Archivierung abgelaufener Dokumente
    - Erstellung von Vernichtungsprotokollen
    - Dashboard-Statistiken fuer Compliance-Uebersicht
    """

    async def scan_expiring_documents(
        self,
        db: AsyncSession,
        days_ahead: int = 30,
        company_id: Optional[uuid.UUID] = None,
    ) -> List[DocumentArchive]:
        """Scannt nach Dokumenten, deren Aufbewahrungsfrist bald ablaeuft.

        Args:
            db: Datenbank-Session
            days_ahead: Tage im Voraus pruefen
            company_id: Optional Firmen-ID fuer Filterung

        Returns:
            Liste von DocumentArchive-Objekten mit ablaufender Frist
        """
        expiry_threshold = date.today() + timedelta(days=days_ahead)

        conditions = [
            DocumentArchive.retention_expires_at <= expiry_threshold,
            DocumentArchive.retention_expires_at >= date.today(),
        ]
        if company_id is not None:
            conditions.append(DocumentArchive.company_id == company_id)

        result = await db.execute(
            select(DocumentArchive)
            .options(selectinload(DocumentArchive.document))
            .where(and_(*conditions))
            .order_by(DocumentArchive.retention_expires_at.asc())
        )
        archives = list(result.scalars().all())

        logger.info(
            "lifecycle_scan_expiring",
            days_ahead=days_ahead,
            found=len(archives),
            company_id=str(company_id) if company_id else "all",
        )

        return archives

    async def auto_archive_expired(
        self,
        db: AsyncSession,
        system_user_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, int]:
        """Archiviert automatisch Dokumente, deren Aufbewahrungsfrist ueberschritten ist.

        Prueft Dokumente, die archiviert sind und deren Frist abgelaufen ist.
        Verifiziert dabei die Hash-Integritaet.

        Args:
            db: Datenbank-Session
            system_user_id: System-User-ID fuer Audit-Trail

        Returns:
            Dictionary mit Statistiken (verified, failed, total)
        """
        today = date.today()

        result = await db.execute(
            select(DocumentArchive)
            .options(selectinload(DocumentArchive.document))
            .where(
                and_(
                    DocumentArchive.retention_expires_at < today,
                    DocumentArchive.is_verified == True,
                )
            )
            .order_by(DocumentArchive.retention_expires_at.asc())
        )
        expired_archives = list(result.scalars().all())

        stats: Dict[str, int] = {
            "total": len(expired_archives),
            "verified": 0,
            "verification_failed": 0,
            "already_expired": len(expired_archives),
        }

        for archive in expired_archives:
            if archive.document is None:
                continue

            try:
                is_valid = await archive_service.verify_document_integrity(
                    db, archive.document_id
                )
                if is_valid:
                    stats["verified"] += 1
                else:
                    stats["verification_failed"] += 1
                    logger.warning(
                        "lifecycle_verification_failed_on_expiry",
                        archive_id=str(archive.id),
                        document_id=str(archive.document_id),
                    )
            except Exception as e:
                stats["verification_failed"] += 1
                logger.error(
                    "lifecycle_auto_archive_error",
                    archive_id=str(archive.id),
                    error=str(e),
                )

        await db.commit()

        logger.info(
            "lifecycle_auto_archive_completed",
            total=stats["total"],
            verified=stats["verified"],
            failed=stats["verification_failed"],
        )

        return stats

    async def generate_destruction_protocol(
        self,
        db: AsyncSession,
        document_ids: List[uuid.UUID],
        user_id: uuid.UUID,
        reason: str = "Aufbewahrungsfrist abgelaufen",
    ) -> Dict[str, object]:
        """Erstellt ein GoBD-konformes Vernichtungsprotokoll.

        Das Protokoll dokumentiert:
        - Welche Dokumente vernichtet werden
        - Wer die Vernichtung angeordnet hat
        - Wann die Aufbewahrungsfrist abgelaufen ist
        - Hash-Verifikation vor Vernichtung

        Args:
            db: Datenbank-Session
            document_ids: IDs der zu vernichtenden Dokumente
            user_id: ID des anordnenden Benutzers
            reason: Begruendung der Vernichtung

        Returns:
            Dictionary mit Vernichtungsprotokoll-Daten
        """
        protocol_id = uuid.uuid4()
        protocol_items: List[Dict[str, object]] = []
        errors: List[Dict[str, str]] = []

        for doc_id in document_ids:
            result = await db.execute(
                select(DocumentArchive)
                .options(selectinload(DocumentArchive.document))
                .where(DocumentArchive.document_id == doc_id)
            )
            archive = result.scalar_one_or_none()

            if archive is None:
                errors.append({
                    "document_id": str(doc_id),
                    "error": "Kein Archiv-Eintrag gefunden",
                })
                continue

            if archive.retention_expires_at > date.today():
                errors.append({
                    "document_id": str(doc_id),
                    "error": (
                        f"Aufbewahrungsfrist laeuft erst am "
                        f"{archive.retention_expires_at.isoformat()} ab"
                    ),
                })
                continue

            document = archive.document
            doc_filename = document.filename if document else "unbekannt"
            doc_original_filename = document.original_filename if document else "unbekannt"

            protocol_items.append({
                "document_id": str(doc_id),
                "filename": doc_filename,
                "original_filename": doc_original_filename,
                "retention_category": archive.retention_category,
                "retention_years": archive.retention_years,
                "archived_at": (
                    archive.archived_at.isoformat()
                    if archive.archived_at else None
                ),
                "retention_expired_at": archive.retention_expires_at.isoformat(),
                "content_hash": archive.content_hash,
                "hash_algorithm": archive.hash_algorithm,
                "is_verified": archive.is_verified,
            })

        protocol = {
            "protocol_id": str(protocol_id),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generated_by": str(user_id),
            "reason": reason,
            "legal_basis": "§147 AO, §257 HGB - Aufbewahrungsfrist abgelaufen",
            "total_documents": len(document_ids),
            "approved_for_destruction": len(protocol_items),
            "rejected": len(errors),
            "items": protocol_items,
            "errors": errors,
        }

        # Audit-Log erstellen
        audit_entry = AuditLog(
            id=uuid.uuid4(),
            action="destruction_protocol_generated",
            resource_type="document_archive",
            resource_id=protocol_id,
            user_id=user_id,
            audit_metadata={
                "protocol_id": str(protocol_id),
                "document_count": len(protocol_items),
                "reason": reason,
            },
        )
        db.add(audit_entry)
        await db.commit()

        logger.info(
            "lifecycle_destruction_protocol_generated",
            protocol_id=str(protocol_id),
            total=len(document_ids),
            approved=len(protocol_items),
            rejected=len(errors),
        )

        return protocol

    async def get_lifecycle_dashboard(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> Dict[str, object]:
        """Erstellt eine Uebersicht des Dokumenten-Lebenszyklus fuer eine Firma.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID

        Returns:
            Dictionary mit Dashboard-Daten
        """
        today = date.today()
        thirty_days = today + timedelta(days=30)
        ninety_days = today + timedelta(days=90)

        # Aktive Dokumente (nicht archiviert)
        active_result = await db.execute(
            select(func.count(Document.id))
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.is_archived == False,
                    Document.deleted_at.is_(None),
                )
            )
        )
        active_count = active_result.scalar() or 0

        # Archivierte Dokumente
        archived_result = await db.execute(
            select(func.count(DocumentArchive.id))
            .where(DocumentArchive.company_id == company_id)
        )
        archived_count = archived_result.scalar() or 0

        # In 30 Tagen ablaufend
        expiring_30_result = await db.execute(
            select(func.count(DocumentArchive.id))
            .where(
                and_(
                    DocumentArchive.company_id == company_id,
                    DocumentArchive.retention_expires_at <= thirty_days,
                    DocumentArchive.retention_expires_at >= today,
                )
            )
        )
        expiring_30 = expiring_30_result.scalar() or 0

        # In 90 Tagen ablaufend
        expiring_90_result = await db.execute(
            select(func.count(DocumentArchive.id))
            .where(
                and_(
                    DocumentArchive.company_id == company_id,
                    DocumentArchive.retention_expires_at <= ninety_days,
                    DocumentArchive.retention_expires_at >= today,
                )
            )
        )
        expiring_90 = expiring_90_result.scalar() or 0

        # Bereits abgelaufen (bereit zur Vernichtung)
        expired_result = await db.execute(
            select(func.count(DocumentArchive.id))
            .where(
                and_(
                    DocumentArchive.company_id == company_id,
                    DocumentArchive.retention_expires_at < today,
                )
            )
        )
        expired_count = expired_result.scalar() or 0

        # Verifikation fehlgeschlagen
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

        # Aufschluesselung nach Kategorie
        category_result = await db.execute(
            select(
                DocumentArchive.retention_category,
                func.count(DocumentArchive.id),
            )
            .where(DocumentArchive.company_id == company_id)
            .group_by(DocumentArchive.retention_category)
        )
        by_category = dict(category_result.all())

        dashboard: Dict[str, object] = {
            "company_id": str(company_id),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "counts": {
                "active": active_count,
                "archived": archived_count,
                "expiring_30_days": expiring_30,
                "expiring_90_days": expiring_90,
                "expired": expired_count,
                "verification_failed": unverified_count,
            },
            "by_category": by_category,
        }

        logger.info(
            "lifecycle_dashboard_generated",
            company_id=str(company_id),
            active=active_count,
            archived=archived_count,
            expiring_30=expiring_30,
        )

        return dashboard

    async def extend_retention(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        new_years: int,
        reason: str,
        user_id: uuid.UUID,
    ) -> DocumentArchive:
        """Verlaengert die Aufbewahrungsfrist eines Dokuments.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            new_years: Neue Aufbewahrungsdauer in Jahren (ab heute)
            reason: Begruendung der Verlaengerung
            user_id: ID des aendernden Benutzers

        Returns:
            Aktualisiertes DocumentArchive-Objekt

        Raises:
            ArchiveError: Wenn kein Archiv-Eintrag gefunden oder Frist ungueltig
        """
        result = await db.execute(
            select(DocumentArchive)
            .where(DocumentArchive.document_id == document_id)
            .with_for_update()
        )
        archive = result.scalar_one_or_none()

        if archive is None:
            raise ArchiveError(
                f"Kein Archiv-Eintrag fuer Dokument {document_id} gefunden"
            )

        old_expires_at = archive.retention_expires_at
        old_years = archive.retention_years

        # Neue Frist berechnen: ab heute + neue Jahre
        new_expires_at = date.today() + timedelta(days=new_years * 365)

        # Sicherheitscheck: neue Frist muss nach alter Frist liegen
        if new_expires_at <= old_expires_at:
            raise ArchiveError(
                f"Neue Frist ({new_expires_at.isoformat()}) muss nach der "
                f"aktuellen Frist ({old_expires_at.isoformat()}) liegen"
            )

        archive.retention_years = new_years
        archive.retention_expires_at = new_expires_at
        archive.retention_reminder_sent = False
        archive.retention_reminder_at = None

        # Audit-Log
        audit_entry = AuditLog(
            id=uuid.uuid4(),
            action="retention_extended",
            resource_type="document_archive",
            resource_id=archive.id,
            user_id=user_id,
            audit_metadata={
                "document_id": str(document_id),
                "old_years": old_years,
                "new_years": new_years,
                "old_expires_at": old_expires_at.isoformat(),
                "new_expires_at": new_expires_at.isoformat(),
                "reason": reason,
            },
        )
        db.add(audit_entry)
        await db.commit()
        await db.refresh(archive)

        logger.info(
            "lifecycle_retention_extended",
            document_id=str(document_id),
            old_years=old_years,
            new_years=new_years,
            old_expires=old_expires_at.isoformat(),
            new_expires=new_expires_at.isoformat(),
            reason=reason,
            user_id=str(user_id),
        )

        return archive

    async def get_retention_summary(
        self,
        db: AsyncSession,
        company_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, object]:
        """Erstellt eine Zusammenfassung der Aufbewahrungsfristen.

        Args:
            db: Datenbank-Session
            company_id: Optional Firmen-ID fuer Filterung

        Returns:
            Dictionary mit Aufschluesselung nach Kategorie und Status
        """
        today = date.today()
        conditions: List[object] = []
        if company_id is not None:
            conditions.append(DocumentArchive.company_id == company_id)

        # Pro Kategorie: total, aktiv, ablaufend, abgelaufen
        base_query = select(
            DocumentArchive.retention_category,
            func.count(DocumentArchive.id).label("total"),
            func.sum(
                case(
                    (DocumentArchive.retention_expires_at >= today, 1),
                    else_=0,
                )
            ).label("active"),
            func.sum(
                case(
                    (
                        and_(
                            DocumentArchive.retention_expires_at >= today,
                            DocumentArchive.retention_expires_at <= today + timedelta(days=90),
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("expiring_soon"),
            func.sum(
                case(
                    (DocumentArchive.retention_expires_at < today, 1),
                    else_=0,
                )
            ).label("expired"),
        )

        if conditions:
            base_query = base_query.where(and_(*conditions))

        base_query = base_query.group_by(DocumentArchive.retention_category)

        result = await db.execute(base_query)
        rows = result.all()

        categories: List[Dict[str, object]] = []
        for row in rows:
            categories.append({
                "category": row.retention_category,
                "total": row.total,
                "active": int(row.active or 0),
                "expiring_soon_90_days": int(row.expiring_soon or 0),
                "expired": int(row.expired or 0),
            })

        # Retention-Settings laden fuer gesetzliche Fristen
        settings_result = await db.execute(
            select(RetentionSetting)
            .order_by(RetentionSetting.category)
        )
        retention_settings = list(settings_result.scalars().all())

        settings_data: List[Dict[str, object]] = []
        for setting in retention_settings:
            settings_data.append({
                "category": setting.category,
                "display_name": setting.display_name,
                "retention_years": setting.retention_years,
                "legal_basis": getattr(setting, "legal_basis", None),
            })

        summary: Dict[str, object] = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "company_id": str(company_id) if company_id else "all",
            "categories": categories,
            "retention_settings": settings_data,
        }

        logger.info(
            "lifecycle_retention_summary_generated",
            company_id=str(company_id) if company_id else "all",
            category_count=len(categories),
        )

        return summary


# Singleton-Instanz
document_lifecycle_engine = DocumentLifecycleEngine()
