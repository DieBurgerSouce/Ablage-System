"""
Fraud Detection API Endpoints

KI-gestuetzte Betrugserkennung und Analyse.
"""

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.db.models import User
from app.services.finanzki.fraud_detection_service import (
    FraudDetectionService,
    FraudType,
    RiskLevel,
)

router = APIRouter(prefix="/fraud", tags=["Fraud Detection"])


# ==================== Schemas ====================


class FraudAlertSchema(BaseModel):
    """Schema für einzelne Fraud-Alerts."""
    type: str
    risk_level: str
    title: str
    description: str
    amount: Optional[float] = None
    confidence: float
    detected_at: str
    invoice_id: Optional[str] = None
    entity_id: Optional[str] = None
    entity_name: Optional[str] = None
    related_invoice_id: Optional[str] = None
    document_ids: Optional[list[str]] = None


class FraudSummarySchema(BaseModel):
    """Zusammenfassung der Fraud-Analyse."""
    total_alerts: int
    critical: int
    high: int
    medium: int
    low: int
    estimated_risk_amount: float


class FraudAnalysisResponse(BaseModel):
    """Response für vollständige Fraud-Analyse."""
    company_id: str
    analysis_period: dict
    summary: FraudSummarySchema
    alerts: list[FraudAlertSchema]
    analyzed_at: str


class FraudDashboardStats(BaseModel):
    """Dashboard-Statistiken für Fraud Detection."""
    total_alerts_30d: int
    critical_alerts: int
    high_risk_amount: float
    top_fraud_types: list[dict]
    trend: str  # "increasing", "stable", "decreasing"


class FraudConfigSchema(BaseModel):
    """Konfiguration für Fraud Detection."""
    price_deviation_threshold: float = Field(
        0.30, ge=0.1, le=1.0, description="Max. Preisabweichung (0.30 = 30%)"
    )
    duplicate_similarity_threshold: float = Field(
        0.85, ge=0.5, le=1.0, description="Duplikat-Ähnlichkeit (0.85 = 85%)"
    )
    phantom_supplier_days: int = Field(
        90, ge=30, le=365, description="Tage ohne Lieferung"
    )
    expense_pattern_threshold: int = Field(
        5, ge=3, le=20, description="Min. Anzahl für Muster"
    )
    approval_threshold: float = Field(
        5000, ge=100, description="Genehmigungsgrenze in EUR"
    )


class AlertActionRequest(BaseModel):
    """Request für Alert-Aktionen."""
    action: str = Field(..., description="dismiss, investigate, escalate, false_positive")
    comment: Optional[str] = None


# ==================== Endpoints ====================


@router.get("/analyze", response_model=FraudAnalysisResponse)
async def analyze_fraud(
    days: int = Query(90, ge=7, le=365, description="Analysezeitraum in Tagen"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Führt vollständige Fraud-Analyse durch.

    Analysiert alle Betrugsarten:
    - Duplikat-Rechnungen
    - Preis-Anomalien
    - Phantom-Lieferanten
    - Spesen-Betrug
    - Kickback-Muster
    - Shell-Companies
    - Runde Betraege
    - Invoice-Splitting
    - Wochenend-Rechnungen
    """
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Keine Firma zugewiesen")

    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    service = FraudDetectionService(db)
    result = await service.analyze_all(
        company_id=current_user.company_id,
        start_date=start_date,
        end_date=end_date,
    )

    return result


@router.get("/dashboard", response_model=FraudDashboardStats)
async def get_fraud_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Liefert Dashboard-Statistiken für Fraud Detection.

    Zeigt:
    - Gesamtzahl Alerts (30 Tage)
    - Kritische Alerts
    - Geschätzter Risikobetrag
    - Top Betrugsarten
    - Trend
    """
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Keine Firma zugewiesen")

    service = FraudDetectionService(db)

    # Aktuelle 30 Tage
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=30)
    current = await service.analyze_all(
        company_id=current_user.company_id,
        start_date=start_date,
        end_date=end_date,
    )

    # Vorherige 30 Tage für Trend
    prev_end = start_date
    prev_start = prev_end - timedelta(days=30)
    previous = await service.analyze_all(
        company_id=current_user.company_id,
        start_date=prev_start,
        end_date=prev_end,
    )

    # Trend berechnen
    current_count = current["summary"]["total_alerts"]
    previous_count = previous["summary"]["total_alerts"]
    if current_count > previous_count * 1.1:
        trend = "increasing"
    elif current_count < previous_count * 0.9:
        trend = "decreasing"
    else:
        trend = "stable"

    # Top Fraud Types
    type_counts: dict[str, int] = {}
    for alert in current["alerts"]:
        fraud_type = alert["type"]
        type_counts[fraud_type] = type_counts.get(fraud_type, 0) + 1

    top_types = [
        {"type": t, "count": c}
        for t, c in sorted(type_counts.items(), key=lambda x: -x[1])[:5]
    ]

    return FraudDashboardStats(
        total_alerts_30d=current_count,
        critical_alerts=current["summary"]["critical"],
        high_risk_amount=current["summary"]["estimated_risk_amount"],
        top_fraud_types=top_types,
        trend=trend,
    )


@router.get("/alerts", response_model=list[FraudAlertSchema])
async def get_fraud_alerts(
    fraud_type: Optional[FraudType] = Query(None, description="Filter nach Betrugsart"),
    risk_level: Optional[RiskLevel] = Query(None, description="Filter nach Risikostufe"),
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Listet Fraud-Alerts mit Filterung.
    """
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Keine Firma zugewiesen")

    service = FraudDetectionService(db)
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    result = await service.analyze_all(
        company_id=current_user.company_id,
        start_date=start_date,
        end_date=end_date,
    )

    alerts = result["alerts"]

    # Filtern
    if fraud_type:
        alerts = [a for a in alerts if a["type"] == fraud_type]
    if risk_level:
        alerts = [a for a in alerts if a["risk_level"] == risk_level]

    # Sortieren nach Risiko (kritisch zuerst)
    risk_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    alerts.sort(key=lambda x: (risk_order.get(x["risk_level"], 99), -x.get("confidence", 0)))

    # Paginieren
    return alerts[offset:offset + limit]


@router.get("/alerts/{alert_id}")
async def get_fraud_alert_detail(
    alert_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Liefert Details zu einem spezifischen Alert.

    Hinweis: Alerts werden on-the-fly generiert und nicht persistent gespeichert.
    Diese Route ist für zukuenftige Erweiterung mit persistenter Alert-Speicherung.
    """
    raise HTTPException(
        status_code=501,
        detail="Alert-Persistierung noch nicht implementiert. Nutzen Sie /analyze für aktuelle Alerts."
    )


@router.post("/alerts/{alert_id}/action")
async def take_alert_action(
    alert_id: str,
    action: AlertActionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Führt Aktion auf Alert aus.

    Aktionen:
    - dismiss: Alert verwerfen
    - investigate: Zur Untersuchung markieren
    - escalate: An Vorgesetzten eskalieren
    - false_positive: Als Fehlalarm markieren
    """
    raise HTTPException(
        status_code=501,
        detail="Alert-Aktionen noch nicht implementiert. Geplant für zukuenftige Version."
    )


@router.get("/config", response_model=FraudConfigSchema)
async def get_fraud_config(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Liefert aktuelle Fraud Detection Konfiguration.
    """
    service = FraudDetectionService(db)
    return FraudConfigSchema(
        price_deviation_threshold=service.config["price_deviation_threshold"],
        duplicate_similarity_threshold=service.config["duplicate_similarity_threshold"],
        phantom_supplier_days=service.config["phantom_supplier_days"],
        expense_pattern_threshold=service.config["expense_pattern_threshold"],
        approval_threshold=service.config["approval_threshold"],
    )


@router.patch("/config", response_model=FraudConfigSchema)
async def update_fraud_config(
    config: FraudConfigSchema,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Aktualisiert Fraud Detection Konfiguration.

    Nur für Admins verfügbar.
    """
    if current_user.role not in ["admin", "owner"]:
        raise HTTPException(status_code=403, detail="Nur Admins können Konfiguration ändern")

    # In Zukunft: Speicherung in DB pro Company
    # Aktuell: Nur Validierung, keine Persistenz
    return config


@router.get("/types", response_model=list[dict])
async def get_fraud_types():
    """
    Listet alle unterstützten Betrugsarten.
    """
    return [
        {
            "type": FraudType.DUPLICATE_INVOICE,
            "name": "Duplikat-Rechnung",
            "description": "Mehrfach eingereichte oder ähnliche Rechnungen",
        },
        {
            "type": FraudType.PRICE_ANOMALY,
            "name": "Preis-Anomalie",
            "description": "Ungewoehnliche Preisabweichungen vom historischen Durchschnitt",
        },
        {
            "type": FraudType.PHANTOM_SUPPLIER,
            "name": "Phantom-Lieferant",
            "description": "Lieferant ohne nachweisbare Lieferungen",
        },
        {
            "type": FraudType.EXPENSE_FRAUD,
            "name": "Spesen-Betrug",
            "description": "Verdaechtige Muster bei Spesenabrechungen",
        },
        {
            "type": FraudType.KICKBACK,
            "name": "Kickback",
            "description": "Konsistente Preisaufschlaege als mögliche Rückverguetung",
        },
        {
            "type": FraudType.SHELL_COMPANY,
            "name": "Shell-Company",
            "description": "Mehrere Lieferanten mit gleichen Bankverbindungen/Adressen",
        },
        {
            "type": FraudType.ROUND_AMOUNT,
            "name": "Runde Betraege",
            "description": "Verdaechtig viele runde Betraege",
        },
        {
            "type": FraudType.SPLIT_INVOICE,
            "name": "Invoice-Splitting",
            "description": "Aufgeteilte Rechnungen zur Umgehung von Genehmigungsgrenzen",
        },
        {
            "type": FraudType.WEEKEND_INVOICE,
            "name": "Wochenend-Rechnung",
            "description": "Am Wochenende erstellte Rechnungen",
        },
    ]


@router.get("/risk-levels", response_model=list[dict])
async def get_risk_levels():
    """
    Listet alle Risikostufen mit Beschreibung.
    """
    return [
        {
            "level": RiskLevel.CRITICAL,
            "name": "Kritisch",
            "description": "Sofortige Untersuchung erforderlich",
            "color": "#dc2626",
        },
        {
            "level": RiskLevel.HIGH,
            "name": "Hoch",
            "description": "Zeitnahe Überprüfung empfohlen",
            "color": "#ea580c",
        },
        {
            "level": RiskLevel.MEDIUM,
            "name": "Mittel",
            "description": "Bei Gelegenheit prüfen",
            "color": "#ca8a04",
        },
        {
            "level": RiskLevel.LOW,
            "name": "Niedrig",
            "description": "Zur Kenntnisnahme",
            "color": "#65a30d",
        },
    ]


@router.get("/entity/{entity_id}/risk-profile")
async def get_entity_risk_profile(
    entity_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Liefert Fraud-Risikoprofil für eine Entity (Kunde/Lieferant).
    """
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Keine Firma zugewiesen")

    service = FraudDetectionService(db)

    # Analyse für letztes Jahr
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=365)

    result = await service.analyze_all(
        company_id=current_user.company_id,
        start_date=start_date,
        end_date=end_date,
    )

    # Alerts für diese Entity filtern
    entity_alerts = [
        a for a in result["alerts"]
        if a.get("entity_id") == str(entity_id)
    ]

    # Risiko-Score berechnen (basierend auf Alerts)
    risk_score = 0
    for alert in entity_alerts:
        if alert["risk_level"] == "critical":
            risk_score += 40
        elif alert["risk_level"] == "high":
            risk_score += 25
        elif alert["risk_level"] == "medium":
            risk_score += 10
        else:
            risk_score += 5

    risk_score = min(100, risk_score)

    return {
        "entity_id": str(entity_id),
        "risk_score": risk_score,
        "risk_level": (
            "critical" if risk_score >= 75
            else "high" if risk_score >= 50
            else "medium" if risk_score >= 25
            else "low"
        ),
        "total_alerts": len(entity_alerts),
        "alerts_by_type": {},
        "recent_alerts": entity_alerts[:5],
        "recommendation": (
            "Sofortige Überprüfung erforderlich" if risk_score >= 75
            else "Erhöhte Aufmerksamkeit empfohlen" if risk_score >= 50
            else "Regelmäßige Überprüfung" if risk_score >= 25
            else "Keine besonderen Massnahmen erforderlich"
        ),
    }
