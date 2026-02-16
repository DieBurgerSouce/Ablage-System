# -*- coding: utf-8 -*-
"""
Smart Dashboard API Endpoints für Ablage-System.

REST API + WebSocket für:
- Echtzeit-KPIs mit Tab-Struktur
- Rollen-basierte Widget-Filterung
- Benutzerdefinierte Widget-Layouts
- Dokument-Fortschritts-Tracking (DHL-Stil)
- WebSocket für Live-Updates

Feinpoliert und durchdacht - Enterprise Smart Dashboard API.
"""

import asyncio
import json
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_errors import safe_error_log
from app.core.types import JSONDict
from app.db.models import User
from app.db.models_smart_dashboard import DashboardTab
from app.api.dependencies import get_db, get_current_active_user, get_current_company_id
from app.services.smart_dashboard_service import SmartDashboardService
from app.services.document_progress_service import DocumentProgressService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/smart-dashboard", tags=["Smart Dashboard"])


# =============================================================================
# Pydantic Schemas
# =============================================================================


class SaveLayoutRequest(BaseModel):
    """Request-Schema für Layout-Speicherung."""
    tab: str = Field(..., description="Dashboard-Tab (overview, finance, documents, workflows, system)")
    layout: Dict[str, object] = Field(..., description="Widget-Layout Konfiguration")


class SaveLayoutResponse(BaseModel):
    """Response-Schema für Layout-Speicherung."""
    id: str
    active_tab: str
    message: str


# =============================================================================
# KPI Endpoints
# =============================================================================


@router.get(
    "/kpis",
    response_model=JSONDict,
    summary="Echtzeit-KPIs",
    description="Aktuelle KPI-Werte für das Dashboard",
)
async def get_kpis(
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> JSONDict:
    """
    Holt aktuelle KPI-Werte.

    **KPIs:**
    - open_invoices_total: Anzahl offener Rechnungen
    - open_invoices_amount: Gesamtbetrag offener Rechnungen (EUR)
    - overdue_invoices_count: Überfällige Rechnungen
    - documents_today: Heute verarbeitete Dokumente
    - ocr_queue_length: OCR-Warteschlangen-Länge
    - cashflow_current: Aktueller Cashflow (EUR)
    - active_alerts: Aktive Alerts

    **Rollen:** Alle authentifizierten Benutzer
    """
    logger.info(
        "smart_dashboard.api.get_kpis",
        user_id=str(current_user.id),
        company_id=str(company_id),
    )

    service = SmartDashboardService()

    try:
        kpis = await service.get_realtime_kpis(db, company_id)
        return {"kpis": kpis}
    except Exception as e:
        logger.error(
            "smart_dashboard.api.get_kpis_failed",
            user_id=str(current_user.id),
            company_id=str(company_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden der KPIs",
        )


# =============================================================================
# Tab Endpoints
# =============================================================================


@router.get(
    "/tabs/{tab}",
    response_model=JSONDict,
    summary="Tab-spezifische Daten",
    description="Daten für einen spezifischen Dashboard-Tab",
)
async def get_tab_data(
    tab: str,
    role: Optional[str] = Query(None, description="Rollen-Filter"),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> JSONDict:
    """
    Holt Daten für einen spezifischen Dashboard-Tab.

    **Tabs:**
    - overview: Übersicht mit Top-KPIs und letzten Aktivitaeten
    - finance: Cashflow, offene Rechnungen, Skonto-Möglichkeiten
    - documents: Verarbeitungs-Queue, OCR-Statistiken, Qualitaetsmetriken
    - workflows: Aktive Workflows, Genehmigungen, SLA-Status
    - system: CPU/GPU-Auslastung, Warteschlangen-Tiefen, Fehlerraten

    **Rollen:** Alle authentifizierten Benutzer
    """
    # Tab validieren
    try:
        dashboard_tab = DashboardTab(tab)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungültiger Tab: {tab}. Erlaubt: overview, finance, documents, workflows, system",
        )

    logger.info(
        "smart_dashboard.api.get_tab_data",
        user_id=str(current_user.id),
        company_id=str(company_id),
        tab=tab,
    )

    service = SmartDashboardService()

    try:
        data = await service.get_tab_data(
            db, company_id, current_user.id, dashboard_tab, role,
        )
        return data
    except Exception as e:
        logger.error(
            "smart_dashboard.api.get_tab_data_failed",
            user_id=str(current_user.id),
            company_id=str(company_id),
            tab=tab,
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Laden der Tab-Daten ({tab})",
        )


# =============================================================================
# Widget Endpoints
# =============================================================================


@router.get(
    "/widgets",
    response_model=JSONDict,
    summary="Rollen-basierte Widget-Liste",
    description="Widget-Liste basierend auf der Benutzerrolle",
)
async def get_widgets(
    role: Optional[str] = Query(None, description="Benutzerrolle (z.B. buchhaltung, geschäftsführung)"),
    current_user: User = Depends(get_current_active_user),
) -> JSONDict:
    """
    Holt die Widget-Liste basierend auf der Benutzerrolle.

    **Rollen:**
    - buchhaltung: Rechnungen, Zahlungslaeufe, Mahnungen, Skonto
    - geschäftsführung: KPIs, Cashflow, Anomalien, Trends
    - sachbearbeitung: Eingangs-Queue, Dokumente, Aufgaben

    Falls keine Rolle angegeben, wird sachbearbeitung als Standard verwendet.
    """
    user_role = role or getattr(current_user, "role", "sachbearbeitung") or "sachbearbeitung"

    service = SmartDashboardService()

    try:
        widgets = await service.get_role_widgets(user_role)
        return {"role": user_role, "widgets": widgets}
    except Exception as e:
        logger.error(
            "smart_dashboard.api.get_widgets_failed",
            user_id=str(current_user.id),
            role=user_role,
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden der Widget-Liste",
        )


# =============================================================================
# Layout Endpoints
# =============================================================================


@router.put(
    "/layout",
    response_model=JSONDict,
    summary="Widget-Layout speichern",
    description="Benutzerdefiniertes Widget-Layout speichern",
)
async def save_layout(
    request: SaveLayoutRequest,
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> JSONDict:
    """
    Speichert das benutzerdefinierte Widget-Layout.

    Der Benutzer kann Widgets per Drag-and-Drop anordnen,
    und das Layout wird pro Tab gespeichert.
    """
    # Tab validieren
    try:
        dashboard_tab = DashboardTab(request.tab)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungültiger Tab: {request.tab}",
        )

    logger.info(
        "smart_dashboard.api.save_layout",
        user_id=str(current_user.id),
        company_id=str(company_id),
        tab=request.tab,
    )

    service = SmartDashboardService()

    try:
        config = await service.save_layout(
            db, company_id, current_user.id, dashboard_tab, request.layout,
        )
        return {
            "id": str(config.id),
            "active_tab": config.active_tab,
            "message": "Layout erfolgreich gespeichert",
        }
    except Exception as e:
        logger.error(
            "smart_dashboard.api.save_layout_failed",
            user_id=str(current_user.id),
            company_id=str(company_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Speichern des Layouts",
        )


# =============================================================================
# Trend Endpoints
# =============================================================================


@router.get(
    "/trends",
    response_model=JSONDict,
    summary="KPI-Trends",
    description="KPI-Trend-Daten für Sparklines und Charts",
)
async def get_trends(
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> JSONDict:
    """
    Holt KPI-Trend-Daten.

    Vergleicht aktuelle KPI-Werte mit den Werten der Vorperiode
    und liefert Richtung und prozentuale Änderung.

    **Rollen:** Alle authentifizierten Benutzer
    """
    logger.info(
        "smart_dashboard.api.get_trends",
        user_id=str(current_user.id),
        company_id=str(company_id),
    )

    service = SmartDashboardService()

    try:
        trends = await service.calculate_kpi_trends(db, company_id)
        return {"trends": trends}
    except Exception as e:
        logger.error(
            "smart_dashboard.api.get_trends_failed",
            user_id=str(current_user.id),
            company_id=str(company_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden der Trend-Daten",
        )


# =============================================================================
# Document Progress Endpoints
# =============================================================================


@router.get(
    "/progress/{document_id}",
    response_model=JSONDict,
    summary="Dokument-Fortschritt",
    description="Fortschritts-Status eines einzelnen Dokuments",
)
async def get_document_progress(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> JSONDict:
    """
    Holt den Fortschritts-Status eines Dokuments.

    Zeigt alle Verarbeitungsschritte im DHL-Tracking-Stil:
    Hochgeladen -> OCR laeuft -> Extraktion -> Validierung -> Fertig

    **Rollen:** Alle authentifizierten Benutzer (mit Dokumentzugriff)
    """
    logger.info(
        "smart_dashboard.api.get_progress",
        user_id=str(current_user.id),
        document_id=str(document_id),
    )

    service = DocumentProgressService()

    try:
        tracker = await service.get_progress(db, document_id)

        if not tracker:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Fortschritts-Tracker nicht gefunden",
            )

        return tracker.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "smart_dashboard.api.get_progress_failed",
            user_id=str(current_user.id),
            document_id=str(document_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden des Dokument-Fortschritts",
        )


@router.get(
    "/progress/batch",
    response_model=JSONDict,
    summary="Batch-Fortschritt",
    description="Gesamtfortschritt aller aktiven Dokumente oder eines Batches",
)
async def get_batch_progress(
    batch_id: Optional[UUID] = Query(None, description="Optionale Batch-ID"),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> JSONDict:
    """
    Holt den Gesamtfortschritt aller aktiven Dokumentenverarbeitungen.

    **Enthält:**
    - Gesamtanzahl Dokumente
    - Abgeschlossene / In Bearbeitung / Fehler
    - Gesamtfortschritt in Prozent
    - Durchschnittliche Verarbeitungszeit
    - Geschätzte Restzeit
    - Letzte Fehler

    **Rollen:** Alle authentifizierten Benutzer
    """
    logger.info(
        "smart_dashboard.api.get_batch_progress",
        user_id=str(current_user.id),
        company_id=str(company_id),
    )

    service = DocumentProgressService()

    try:
        progress = await service.get_batch_progress(db, company_id, batch_id)
        return progress
    except Exception as e:
        logger.error(
            "smart_dashboard.api.get_batch_progress_failed",
            user_id=str(current_user.id),
            company_id=str(company_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden des Batch-Fortschritts",
        )


# =============================================================================
# WebSocket Endpoint
# =============================================================================


@router.websocket("/ws/dashboard/{company_id}")
async def dashboard_websocket(
    websocket: WebSocket,
    company_id: UUID,
) -> None:
    """WebSocket für Echtzeit-KPI-Updates und Document-Progress.

    Sendet periodische KPI-Updates und reagiert auf
    Dokument-Fortschritts-Änderungen via Redis Pub/Sub.

    Nachrichten-Format:
    {
        "type": "kpi_update" | "progress_update" | "error",
        "data": { ... }
    }
    """
    await websocket.accept()

    logger.info(
        "smart_dashboard.ws.connected",
        company_id=str(company_id),
    )

    try:
        from app.api.dependencies import AsyncSessionLocal

        refresh_interval = 30  # Sekunden

        while True:
            try:
                async with AsyncSessionLocal() as db:
                    service = SmartDashboardService()

                    # KPIs senden
                    kpis = await service.get_realtime_kpis(db, company_id)
                    await websocket.send_json({
                        "type": "kpi_update",
                        "data": kpis,
                    })

                    # Aktive Progress-Tracker senden
                    progress_service = DocumentProgressService()
                    batch_data = await progress_service.get_batch_progress(
                        db, company_id,
                    )
                    await websocket.send_json({
                        "type": "progress_update",
                        "data": batch_data,
                    })

            except Exception as e:
                logger.warning(
                    "smart_dashboard.ws.update_error",
                    company_id=str(company_id),
                    **safe_error_log(e),
                )
                try:
                    await websocket.send_json({
                        "type": "error",
                        "data": {"message": "Fehler beim Laden der Dashboard-Daten"},
                    })
                except Exception:
                    break

            # Auf nächsten Zyklus oder Client-Nachricht warten
            try:
                # receive_text mit Timeout, damit wir periodisch updaten
                message = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=float(refresh_interval),
                )
                # Client kann refresh_interval ändern
                try:
                    data = json.loads(message)
                    if "refresh_interval" in data:
                        new_interval = int(data["refresh_interval"])
                        refresh_interval = max(5, min(new_interval, 300))
                except (json.JSONDecodeError, ValueError):
                    pass
            except asyncio.TimeoutError:
                # Timeout = normaler Update-Zyklus
                continue

    except WebSocketDisconnect:
        logger.info(
            "smart_dashboard.ws.disconnected",
            company_id=str(company_id),
        )
    except Exception as e:
        logger.error(
            "smart_dashboard.ws.error",
            company_id=str(company_id),
            **safe_error_log(e),
        )
