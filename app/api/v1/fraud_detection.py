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

from app.api.dependencies import get_current_user, get_db, get_user_company_id_dep
from app.db.models import User
from app.db.models_alert import Alert, AlertCategory
from app.services.alert_center_service import get_alert_center_service
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
    escalate_to: Optional[UUID] = Field(
        None, description="Ziel-Benutzer für escalate (optional; sonst an den Aufrufer)"
    )


# ==================== Endpoints ====================


@router.get("/analyze", response_model=FraudAnalysisResponse)
async def analyze_fraud(
    days: int = Query(90, ge=7, le=365, description="Analysezeitraum in Tagen"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
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
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    service = FraudDetectionService(db)
    result = await service.analyze_all(
        company_id=company_id,
        start_date=start_date,
        end_date=end_date,
    )

    return result


@router.get("/dashboard", response_model=FraudDashboardStats)
async def get_fraud_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
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
    service = FraudDetectionService(db)

    # Aktuelle 30 Tage
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=30)
    current = await service.analyze_all(
        company_id=company_id,
        start_date=start_date,
        end_date=end_date,
    )

    # Vorherige 30 Tage für Trend
    prev_end = start_date
    prev_start = prev_end - timedelta(days=30)
    previous = await service.analyze_all(
        company_id=company_id,
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
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(50, ge=1, le=200, description="Eintraege pro Seite"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """
    Listet Fraud-Alerts mit Filterung.
    """
    service = FraudDetectionService(db)
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    result = await service.analyze_all(
        company_id=company_id,
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
    offset = (page - 1) * per_page
    return alerts[offset:offset + per_page]


@router.get("/alerts/{alert_id}")
async def get_fraud_alert_detail(
    alert_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> dict:
    """
    Liefert Details zu einem persistierten Fraud-Alert (mandantengetrennt).

    Liest den Alert aus dem zentralen Alert-Center (Kategorie "fraud"), gefiltert
    nach der Firma des Benutzers. 404, falls kein passender Alert existiert.
    """
    service = get_alert_center_service(db)
    alert = await service.get_alert(alert_id, company_id=company_id)
    if alert is None or alert.category != AlertCategory.FRAUD.value:
        raise HTTPException(status_code=404, detail="Alert nicht gefunden")
    return alert.to_dict()


@router.post("/alerts/{alert_id}/action")
async def take_alert_action(
    alert_id: UUID,
    action: AlertActionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> dict:
    """
    Führt eine Aktion auf einem persistierten Fraud-Alert aus (mit Statuspersistenz).

    Aktionen:
    - dismiss: Alert verwerfen
    - investigate: Zur Untersuchung markieren (in Bearbeitung)
    - escalate: An (optional benannten) Benutzer eskalieren
    - false_positive: Als Fehlalarm verwerfen
    """
    service = get_alert_center_service(db)

    # Existenz + Mandanten-Scope prüfen (404 statt Information Leak)
    alert = await service.get_alert(alert_id, company_id=company_id)
    if alert is None or alert.category != AlertCategory.FRAUD.value:
        raise HTTPException(status_code=404, detail="Alert nicht gefunden")

    action_name = action.action.strip().lower()
    updated: Optional[Alert]

    if action_name == "dismiss":
        updated = await service.dismiss_alert(
            alert_id, user_id=current_user.id, reason=action.comment, company_id=company_id
        )
    elif action_name == "false_positive":
        updated = await service.dismiss_alert(
            alert_id,
            user_id=current_user.id,
            reason=action.comment or "Als Fehlalarm markiert",
            company_id=company_id,
        )
    elif action_name == "investigate":
        updated = await service.acknowledge_alert(
            alert_id, user_id=current_user.id, company_id=company_id
        )
    elif action_name == "escalate":
        # Ohne explizites Ziel wird an den ausführenden Benutzer eskaliert.
        updated = await service.escalate_alert(
            alert_id,
            escalate_to_id=action.escalate_to or current_user.id,
            escalated_by_id=current_user.id,
            reason=action.comment,
            company_id=company_id,
        )
    else:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unbekannte Aktion: {action.action}. "
                "Erlaubt: dismiss, investigate, escalate, false_positive"
            ),
        )

    if updated is None:
        # Sollte nach der Existenzpruefung nicht auftreten (z.B. Race Condition)
        raise HTTPException(status_code=404, detail="Alert nicht gefunden")

    return updated.to_dict()


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
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """
    Liefert Fraud-Risikoprofil für eine Entity (Kunde/Lieferant).
    """
    service = FraudDetectionService(db)

    # Analyse für letztes Jahr
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=365)

    result = await service.analyze_all(
        company_id=company_id,
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
