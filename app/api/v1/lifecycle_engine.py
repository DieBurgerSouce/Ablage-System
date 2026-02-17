# -*- coding: utf-8 -*-
"""
Document Lifecycle Engine API Endpoints.

GoBD-konforme Dokumenten-Lebenszyklus-Verwaltung:
- GET  /lifecycle/dashboard                    - Uebersicht-Statistiken
- GET  /lifecycle/expiring                     - Ablaufende Dokumente
- POST /lifecycle/extend/{document_id}         - Aufbewahrungsfrist verlaengern
- GET  /lifecycle/destruction-protocols        - Vernichtungsprotokolle auflisten
- POST /lifecycle/destruction-protocols        - Vernichtungsprotokoll erstellen
- GET  /lifecycle/retention-summary            - Aufbewahrungsfristen-Zusammenfassung

Gesetzliche Grundlagen: §147 AO, §257 HGB, §14b UStG
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.api.schemas.lifecycle import (
    LifecycleDashboardResponse,
    LifecycleDashboardCounts,
    ExpiringDocumentResponse,
    RetentionExtensionRequest,
    RetentionExtensionResponse,
    DestructionProtocolRequest,
    DestructionProtocolResponse,
    DestructionProtocolItem,
    DestructionProtocolError,
    RetentionSummaryResponse,
    RetentionCategorySummary,
    RetentionSettingInfo,
)
from app.core.exceptions import ArchiveError, DocumentNotFoundError
from app.core.rate_limiting import limiter
from app.core.safe_errors import safe_error_log
from app.db.models import User
from app.services.document_lifecycle_engine import document_lifecycle_engine

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/lifecycle",
    tags=["Lifecycle Engine"],
)


# =============================================================================
# Dashboard
# =============================================================================


@router.get(
    "/dashboard",
    response_model=LifecycleDashboardResponse,
    summary="Lifecycle-Dashboard",
)
@limiter.limit("30/minute")
async def get_lifecycle_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> LifecycleDashboardResponse:
    """
    Gibt die Lifecycle-Uebersicht fuer die aktuelle Firma zurueck.

    Zeigt Zaehler fuer aktive, archivierte, ablaufende und
    abgelaufene Dokumente sowie eine Aufschluesselung nach Kategorie.
    """
    try:
        dashboard = await document_lifecycle_engine.get_lifecycle_dashboard(
            db, current_user.company_id
        )

        counts_data = dashboard.get("counts", {})
        return LifecycleDashboardResponse(
            company_id=str(dashboard.get("company_id", "")),
            generated_at=str(dashboard.get("generated_at", "")),
            counts=LifecycleDashboardCounts(
                active=counts_data.get("active", 0),
                archived=counts_data.get("archived", 0),
                expiring_30_days=counts_data.get("expiring_30_days", 0),
                expiring_90_days=counts_data.get("expiring_90_days", 0),
                expired=counts_data.get("expired", 0),
                verification_failed=counts_data.get("verification_failed", 0),
            ),
            by_category=dashboard.get("by_category", {}),
        )
    except Exception as e:
        logger.error("lifecycle_dashboard_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lifecycle-Dashboard konnte nicht abgerufen werden",
        )


# =============================================================================
# Expiring Documents
# =============================================================================


@router.get(
    "/expiring",
    response_model=List[ExpiringDocumentResponse],
    summary="Ablaufende Dokumente",
)
@limiter.limit("30/minute")
async def get_expiring_documents(
    request: Request,
    days: int = Query(
        30, ge=1, le=365, description="Tage im Voraus pruefen"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[ExpiringDocumentResponse]:
    """
    Listet Dokumente auf, deren Aufbewahrungsfrist bald ablaeuft.

    Zeigt alle archivierten Dokumente der aktuellen Firma,
    deren Frist innerhalb der angegebenen Tage ablaeuft.
    """
    try:
        archives = await document_lifecycle_engine.scan_expiring_documents(
            db,
            days_ahead=days,
            company_id=current_user.company_id,
        )

        today = date.today()
        results: List[ExpiringDocumentResponse] = []
        for archive in archives:
            days_until = (archive.retention_expires_at - today).days
            doc = archive.document

            results.append(
                ExpiringDocumentResponse(
                    archive_id=str(archive.id),
                    document_id=str(archive.document_id),
                    filename=doc.filename if doc else None,
                    retention_category=archive.retention_category,
                    retention_years=archive.retention_years,
                    retention_expires_at=archive.retention_expires_at,
                    days_until_expiry=days_until,
                    is_verified=archive.is_verified,
                    archived_at=(
                        archive.archived_at.isoformat()
                        if archive.archived_at else None
                    ),
                )
            )

        return results
    except Exception as e:
        logger.error("lifecycle_expiring_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ablaufende Dokumente konnten nicht abgerufen werden",
        )


# =============================================================================
# Retention Extension
# =============================================================================


@router.post(
    "/extend/{document_id}",
    response_model=RetentionExtensionResponse,
    summary="Aufbewahrungsfrist verlaengern",
    status_code=status.HTTP_200_OK,
)
@limiter.limit("10/minute")
async def extend_document_retention(
    request: Request,
    body: RetentionExtensionRequest,
    document_id: UUID = Path(..., description="Dokument-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> RetentionExtensionResponse:
    """
    Verlaengert die Aufbewahrungsfrist eines archivierten Dokuments.

    Erstellt einen Audit-Trail-Eintrag mit Begruendung.
    Die neue Frist wird ab heute berechnet.
    """
    try:
        # Alten Stand merken
        from sqlalchemy import select
        from app.db.models import DocumentArchive

        old_result = await db.execute(
            select(DocumentArchive)
            .where(DocumentArchive.document_id == document_id)
        )
        old_archive = old_result.scalar_one_or_none()
        if old_archive is None:
            raise ArchiveError(
                f"Kein Archiv-Eintrag fuer Dokument {document_id} gefunden"
            )

        old_years = old_archive.retention_years
        old_expires = old_archive.retention_expires_at

        archive = await document_lifecycle_engine.extend_retention(
            db,
            document_id=document_id,
            new_years=body.new_years,
            reason=body.reason,
            user_id=current_user.id,
        )

        return RetentionExtensionResponse(
            archive_id=str(archive.id),
            document_id=str(archive.document_id),
            old_years=old_years,
            new_years=archive.retention_years,
            old_expires_at=old_expires,
            new_expires_at=archive.retention_expires_at,
            reason=body.reason,
            extended_at=archive.archived_at.isoformat() if archive.archived_at else "",
        )
    except ArchiveError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            "lifecycle_extend_failed",
            document_id=str(document_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fristverlaengerung konnte nicht durchgefuehrt werden",
        )


# =============================================================================
# Destruction Protocols
# =============================================================================


@router.get(
    "/destruction-protocols",
    response_model=Dict[str, str],
    summary="Vernichtungsprotokolle auflisten",
)
@limiter.limit("30/minute")
async def list_destruction_protocols(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, str]:
    """
    Gibt eine Info-Nachricht zurueck.

    Vernichtungsprotokolle werden bei Erstellung im Audit-Log gespeichert.
    Fuer historische Protokolle nutzen Sie den Audit-Trail-Endpunkt.
    """
    return {
        "info": (
            "Vernichtungsprotokolle werden im Audit-Log gespeichert. "
            "Nutzen Sie GET /api/v1/audit?action=destruction_protocol_generated "
            "fuer die historische Uebersicht."
        ),
    }


@router.post(
    "/destruction-protocols",
    response_model=DestructionProtocolResponse,
    summary="Vernichtungsprotokoll erstellen",
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("5/minute")
async def create_destruction_protocol(
    request: Request,
    body: DestructionProtocolRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DestructionProtocolResponse:
    """
    Erstellt ein GoBD-konformes Vernichtungsprotokoll.

    Prueft fuer jedes Dokument:
    - Existiert ein Archiv-Eintrag?
    - Ist die Aufbewahrungsfrist abgelaufen?
    - Ist die Integritaet verifiziert?

    Nur Dokumente mit abgelaufener Frist werden zur Vernichtung freigegeben.
    """
    try:
        protocol = await document_lifecycle_engine.generate_destruction_protocol(
            db,
            document_ids=body.document_ids,
            user_id=current_user.id,
            reason=body.reason,
        )

        items = [
            DestructionProtocolItem(**item)
            for item in protocol.get("items", [])
        ]
        errors = [
            DestructionProtocolError(**err)
            for err in protocol.get("errors", [])
        ]

        return DestructionProtocolResponse(
            protocol_id=str(protocol.get("protocol_id", "")),
            generated_at=str(protocol.get("generated_at", "")),
            generated_by=str(protocol.get("generated_by", "")),
            reason=str(protocol.get("reason", "")),
            legal_basis=str(protocol.get("legal_basis", "")),
            total_documents=int(protocol.get("total_documents", 0)),
            approved_for_destruction=int(protocol.get("approved_for_destruction", 0)),
            rejected=int(protocol.get("rejected", 0)),
            items=items,
            errors=errors,
        )
    except Exception as e:
        logger.error(
            "lifecycle_destruction_protocol_failed",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Vernichtungsprotokoll konnte nicht erstellt werden",
        )


# =============================================================================
# Retention Summary
# =============================================================================


@router.get(
    "/retention-summary",
    response_model=RetentionSummaryResponse,
    summary="Aufbewahrungsfristen-Zusammenfassung",
)
@limiter.limit("30/minute")
async def get_retention_summary(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> RetentionSummaryResponse:
    """
    Gibt eine Zusammenfassung der Aufbewahrungsfristen zurueck.

    Zeigt pro Kategorie: Gesamt, Aktiv, Bald ablaufend, Abgelaufen.
    Zusaetzlich die konfigurierten Aufbewahrungsfristen-Einstellungen.
    """
    try:
        summary = await document_lifecycle_engine.get_retention_summary(
            db, company_id=current_user.company_id
        )

        categories = [
            RetentionCategorySummary(**cat)
            for cat in summary.get("categories", [])
        ]
        settings = [
            RetentionSettingInfo(**s)
            for s in summary.get("retention_settings", [])
        ]

        return RetentionSummaryResponse(
            generated_at=str(summary.get("generated_at", "")),
            company_id=str(summary.get("company_id", "")),
            categories=categories,
            retention_settings=settings,
        )
    except Exception as e:
        logger.error("lifecycle_retention_summary_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Aufbewahrungsfristen-Zusammenfassung konnte nicht abgerufen werden",
        )
