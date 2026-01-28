"""
CEO Dashboard API Endpoints

REST API fuer Digital Twin des Unternehmens:
- Executive-Level Uebersicht
- Gesundheits-Score mit Dimensionen
- Trend-Analysen fuer Sparklines
- Anomalie-Erkennung

Feinpoliert und durchdacht - Enterprise CEO Dashboard.
"""

from typing import Dict, List, Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.api.dependencies import get_db, get_current_active_user, get_current_company_id
from app.services.ceo_dashboard.digital_twin_service import DigitalTwinService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/ceo-dashboard", tags=["CEO Dashboard"])


# =============================================================================
# CEO Dashboard Endpoints
# =============================================================================


@router.get(
    "/overview",
    response_model=Dict[str, Any],
    summary="Unternehmens-Uebersicht",
    description="Vollstaendige Uebersicht fuer CEO Dashboard mit allen Metriken"
)
async def get_overview(
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Holt Unternehmens-Uebersicht.

    **Enthaelt:**
    - Gesundheits-Score (overall + Dimensionen)
    - Dokument-Statistiken (heute, Monat)
    - Rechnungs-Status (offen, ueberfaellig)
    - Alert-Zaehler (aktiv, kritisch)
    - Auto-Process Rate

    **Rollen:** Alle authentifizierten Benutzer (company-level)
    """
    logger.info(
        "ceo_dashboard.get_overview",
        user_id=str(current_user.id),
        company_id=str(company_id),
    )

    service = DigitalTwinService()

    try:
        overview = await service.get_overview(company_id, db)
        return overview.to_dict()
    except Exception as e:
        logger.error(
            "ceo_dashboard.overview_failed",
            user_id=str(current_user.id),
            company_id=str(company_id),
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden der Unternehmens-Übersicht",
        )


@router.get(
    "/health-score",
    response_model=Dict[str, Any],
    summary="Gesundheits-Score",
    description="Detaillierter Gesundheits-Score mit allen Dimensionen"
)
async def get_health_score(
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Holt Gesundheits-Score.

    **Dimensionen:**
    - **Financial** (40%): Zahlungsverhalten, Liquiditaet
    - **Operations** (25%): Verarbeitungsrate, Effizienz
    - **Risk** (20%): Risiko-Entities, Alerts
    - **Compliance** (15%): GDPR, Audit-Trail

    **Rollen:** Alle authentifizierten Benutzer
    """
    logger.info(
        "ceo_dashboard.get_health_score",
        user_id=str(current_user.id),
        company_id=str(company_id),
    )

    service = DigitalTwinService()

    try:
        health_score = await service.get_health_score(company_id, db)
        return health_score.to_dict()
    except Exception as e:
        logger.error(
            "ceo_dashboard.health_score_failed",
            user_id=str(current_user.id),
            company_id=str(company_id),
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Berechnen des Gesundheits-Scores",
        )


@router.get(
    "/trends",
    response_model=Dict[str, List[Dict]],
    summary="Trend-Analysen",
    description="Zeitreihen-Daten fuer Sparklines und Charts"
)
async def get_trends(
    days: int = Query(30, ge=7, le=365, description="Anzahl Tage (7-365)"),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, List[Dict]]:
    """
    Holt Trend-Daten fuer Sparklines.

    **Zeitreihen:**
    - documents_processed: Anzahl verarbeiteter Dokumente
    - invoice_volume: Rechnungsvolumen in EUR
    - auto_process_rate: Auto-Verarbeitungsrate (0-1)
    - alert_count: Anzahl neuer Alerts

    **Parameter:**
    - **days**: Zeitraum (7, 30, 90, 365 Tage)

    **Rollen:** Alle authentifizierten Benutzer
    """
    logger.info(
        "ceo_dashboard.get_trends",
        user_id=str(current_user.id),
        company_id=str(company_id),
        days=days,
    )

    service = DigitalTwinService()

    try:
        trends = await service.get_trends(company_id, days, db)
        return trends.to_dict()
    except Exception as e:
        logger.error(
            "ceo_dashboard.trends_failed",
            user_id=str(current_user.id),
            company_id=str(company_id),
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden der Trend-Daten",
        )


@router.get(
    "/anomalies",
    response_model=List[Dict[str, Any]],
    summary="Anomalie-Erkennung",
    description="Erkennt Anomalien in Unternehmens-Metriken"
)
async def get_anomalies(
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """
    Erkennt Anomalien.

    **Erkannte Muster:**
    - Ungewoehnlich viele Alerts
    - Dokument-Verarbeitung stark abgefallen
    - Ungewoehnlich hohe Ausfallrate
    - Unerwartete Spitzen/Taeler in Metriken

    **Schweregrade:** info, warning, critical

    **Rollen:** Alle authentifizierten Benutzer
    """
    logger.info(
        "ceo_dashboard.get_anomalies",
        user_id=str(current_user.id),
        company_id=str(company_id),
    )

    service = DigitalTwinService()

    try:
        anomalies = await service.get_anomalies(company_id, db)
        return [a.to_dict() for a in anomalies]
    except Exception as e:
        logger.error(
            "ceo_dashboard.anomalies_failed",
            user_id=str(current_user.id),
            company_id=str(company_id),
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Erkennen von Anomalien",
        )
