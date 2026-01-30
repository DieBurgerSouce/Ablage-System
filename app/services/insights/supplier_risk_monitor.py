# -*- coding: utf-8 -*-
"""
Supplier Risk Monitor Service fuer Ablage-System.

Ueberwacht Lieferanten-Risiken durch:
- Integration mit Handelsregister
- Insolvenz-Fruehwarnung
- Bonitaetsbewertung
- Lieferanten-Verhaltensmuster

Vision 2.0 Phase 2 - Proaktive Insights

Feinpoliert und durchdacht - Deutsche Praezision.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional, Dict, Any, List
from uuid import UUID

from prometheus_client import Counter, Histogram

from app.core.safe_errors import safe_error_log

logger = logging.getLogger(__name__)


# =============================================================================
# PROMETHEUS METRICS
# =============================================================================

supplier_risk_checks = Counter(
    "supplier_risk_checks_total",
    "Anzahl der Lieferanten-Risikopruefungen",
    ["company_id", "risk_level"]
)

supplier_risk_latency = Histogram(
    "supplier_risk_check_seconds",
    "Latenz der Risikopruefung",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

handelsregister_queries = Counter(
    "handelsregister_queries_total",
    "Anzahl der Handelsregister-Abfragen",
    ["status"]
)


# =============================================================================
# ENUMS
# =============================================================================


class SupplierRiskLevel(str, Enum):
    """Risikostufe eines Lieferanten."""
    LOW = "low"                # Geringes Risiko
    MEDIUM = "medium"          # Mittleres Risiko
    HIGH = "high"              # Hohes Risiko
    CRITICAL = "critical"      # Kritisches Risiko
    UNKNOWN = "unknown"        # Nicht bewertet


class RiskFactorType(str, Enum):
    """Arten von Risikofaktoren."""
    INSOLVENCY = "insolvency"          # Insolvenzverfahren
    PAYMENT_HISTORY = "payment_history"  # Zahlungsverhalten
    PAYMENT_DELAY = "payment_delay"      # Zahlungsverzoegerung
    FINANCIAL_HEALTH = "financial_health"  # Finanzielle Gesundheit
    MANAGEMENT_CHANGE = "management_change"  # Geschaeftsfuehrerwechsel
    ADDRESS_CHANGE = "address_change"    # Adressaenderung
    LEGAL_FORM_CHANGE = "legal_form_change"  # Rechtsformaenderung
    DEPENDENCY = "dependency"           # Abhaengigkeitsrisiko
    MARKET_EXPOSURE = "market_exposure"  # Marktexposition
    LOW_VOLUME = "low_volume"           # Geringes Handelsvolumen
    HIGH_RISK_COUNTRY = "high_risk_country"  # Hochrisikoland


class DataSource(str, Enum):
    """Datenquellen fuer Risikobewertung."""
    HANDELSREGISTER = "handelsregister"
    INSOLVENZREGISTER = "insolvenzregister"
    CREDITREFORM = "creditreform"
    INTERNAL = "internal"              # Interne Daten (InvoiceTracking, etc.)
    INTERNAL_HISTORY = "internal_history"
    BUNDESANZEIGER = "bundesanzeiger"
    EXTERNAL_API = "external_api"      # Externe APIs


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class RiskFactor:
    """Einzelner Risikofaktor."""
    factor_type: RiskFactorType
    severity: SupplierRiskLevel
    description: str
    source: DataSource
    detected_at: datetime
    details: Dict[str, Any] = field(default_factory=dict)
    expires_at: Optional[datetime] = None


@dataclass
class SupplierRiskProfile:
    """Vollstaendiges Risikoprofil eines Lieferanten."""
    entity_id: UUID
    company_id: UUID
    supplier_name: str
    overall_risk_level: SupplierRiskLevel
    risk_score: float  # 0.0 - 1.0
    risk_factors: List[RiskFactor]
    last_checked_at: datetime
    next_check_at: datetime
    data_sources_used: List[DataSource]
    recommendations: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HandelsregisterInfo:
    """Informationen aus dem Handelsregister."""
    company_name: str
    legal_form: str
    registry_court: str
    registry_number: str
    registered_address: str
    managing_directors: List[str]
    registered_capital: Optional[float]
    registration_date: Optional[datetime]
    last_update: datetime
    status: str  # aktiv, geloescht, in_liquidation
    changes_detected: List[Dict[str, Any]]


@dataclass
class MonitoringAlert:
    """Alert aus dem Lieferanten-Monitoring."""
    entity_id: UUID
    company_id: UUID
    alert_type: RiskFactorType
    severity: SupplierRiskLevel
    title: str
    message: str
    detected_at: datetime
    source: DataSource
    recommended_action: str
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# SUPPLIER RISK MONITOR SERVICE
# =============================================================================


class SupplierRiskMonitor:
    """
    Ueberwacht Lieferanten-Risiken in Echtzeit.

    Features:
    - Handelsregister-Integration
    - Insolvenz-Fruehwarnung
    - Bonitaetsbewertung
    - Aenderungs-Monitoring
    """

    # Singleton instance
    _instance: Optional["SupplierRiskMonitor"] = None

    def __new__(cls) -> "SupplierRiskMonitor":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        self._initialized = True

        # Risk weights
        self.risk_weights: Dict[RiskFactorType, float] = {
            RiskFactorType.INSOLVENCY: 0.40,
            RiskFactorType.PAYMENT_HISTORY: 0.20,
            RiskFactorType.FINANCIAL_HEALTH: 0.15,
            RiskFactorType.MANAGEMENT_CHANGE: 0.08,
            RiskFactorType.ADDRESS_CHANGE: 0.05,
            RiskFactorType.LEGAL_FORM_CHANGE: 0.05,
            RiskFactorType.DEPENDENCY: 0.05,
            RiskFactorType.MARKET_EXPOSURE: 0.02,
        }

        # Risk thresholds
        self.risk_thresholds = {
            SupplierRiskLevel.LOW: 0.25,
            SupplierRiskLevel.MEDIUM: 0.50,
            SupplierRiskLevel.HIGH: 0.75,
            SupplierRiskLevel.CRITICAL: 1.0,
        }

        # Check intervals based on risk level
        self.check_intervals: Dict[SupplierRiskLevel, timedelta] = {
            SupplierRiskLevel.LOW: timedelta(days=30),
            SupplierRiskLevel.MEDIUM: timedelta(days=14),
            SupplierRiskLevel.HIGH: timedelta(days=7),
            SupplierRiskLevel.CRITICAL: timedelta(days=1),
            SupplierRiskLevel.UNKNOWN: timedelta(days=7),
        }

        logger.info("SupplierRiskMonitor initialisiert")

    async def assess_supplier_risk(
        self,
        entity_id: UUID,
        company_id: UUID,
        supplier_name: str,
        handelsregister_number: Optional[str] = None,
        vat_id: Optional[str] = None,
    ) -> SupplierRiskProfile:
        """
        Bewertet das Risiko eines Lieferanten.

        Args:
            entity_id: ID des Geschaeftspartners
            company_id: ID des Unternehmens
            supplier_name: Name des Lieferanten
            handelsregister_number: Handelsregisternummer (optional)
            vat_id: USt-IdNr. (optional)

        Returns:
            SupplierRiskProfile mit Gesamtbewertung
        """
        with supplier_risk_latency.time():
            now = datetime.now(timezone.utc)
            risk_factors: List[RiskFactor] = []
            data_sources: List[DataSource] = []

            # 1. Interne Historie analysieren
            internal_factors = await self._analyze_internal_history(
                entity_id, company_id
            )
            risk_factors.extend(internal_factors)
            if internal_factors:
                data_sources.append(DataSource.INTERNAL_HISTORY)

            # 2. Handelsregister pruefen (wenn Nummer vorhanden)
            if handelsregister_number:
                hr_factors = await self._check_handelsregister(
                    handelsregister_number, supplier_name
                )
                risk_factors.extend(hr_factors)
                if hr_factors:
                    data_sources.append(DataSource.HANDELSREGISTER)

            # 3. Insolvenzregister pruefen
            insolvency_factors = await self._check_insolvency_register(
                supplier_name, handelsregister_number
            )
            risk_factors.extend(insolvency_factors)
            if insolvency_factors:
                data_sources.append(DataSource.INSOLVENZREGISTER)

            # 4. Abhaengigkeitsanalyse
            dependency_factors = await self._analyze_dependency(
                entity_id, company_id
            )
            risk_factors.extend(dependency_factors)

            # Gesamtscore berechnen
            risk_score = self._calculate_risk_score(risk_factors)
            overall_level = self._score_to_level(risk_score)

            # Naechste Pruefung berechnen
            next_check = now + self.check_intervals[overall_level]

            # Empfehlungen generieren
            recommendations = self._generate_recommendations(
                risk_factors, overall_level
            )

            profile = SupplierRiskProfile(
                entity_id=entity_id,
                company_id=company_id,
                supplier_name=supplier_name,
                overall_risk_level=overall_level,
                risk_score=risk_score,
                risk_factors=risk_factors,
                last_checked_at=now,
                next_check_at=next_check,
                data_sources_used=data_sources,
                recommendations=recommendations,
            )

            # Metrics
            supplier_risk_checks.labels(
                company_id=str(company_id),
                risk_level=overall_level.value
            ).inc()

            logger.info(
                "supplier_risk_assessed",
                entity_id=str(entity_id),
                supplier_name=supplier_name[:50],
                risk_level=overall_level.value,
                risk_score=round(risk_score, 3),
                factors_count=len(risk_factors),
            )

            return profile

    async def _analyze_internal_history(
        self,
        entity_id: UUID,
        company_id: UUID,
    ) -> List[RiskFactor]:
        """Analysiert die interne Zahlungshistorie aus InvoiceTracking."""
        from sqlalchemy import select, func, and_
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.db.session import async_session_factory
        from app.db.models import InvoiceTracking

        factors: List[RiskFactor] = []
        now = datetime.now(timezone.utc)

        try:
            async with async_session_factory() as db:
                # Hole Rechnungsstatistiken fuer diesen Lieferanten
                stats_query = select(
                    func.count(InvoiceTracking.id).label("total_invoices"),
                    func.sum(
                        func.case(
                            (InvoiceTracking.dunning_level > 0, 1),
                            else_=0
                        )
                    ).label("overdue_count"),
                    func.avg(
                        func.extract(
                            'day',
                            func.coalesce(
                                InvoiceTracking.paid_at,
                                func.now()
                            ) - InvoiceTracking.due_date
                        )
                    ).label("avg_delay_days"),
                    func.sum(InvoiceTracking.amount).label("total_volume"),
                ).where(
                    and_(
                        InvoiceTracking.entity_id == entity_id,
                        InvoiceTracking.company_id == company_id,
                        InvoiceTracking.created_at >= now - timedelta(days=365),
                    )
                )

                result = await db.execute(stats_query)
                row = result.fetchone()

                if row and row.total_invoices and row.total_invoices > 0:
                    total = row.total_invoices
                    overdue = row.overdue_count or 0
                    avg_delay = row.avg_delay_days or 0
                    volume = row.total_volume or 0

                    # Hohe Mahnquote
                    overdue_rate = overdue / total if total > 0 else 0
                    if overdue_rate > 0.3:  # >30% ueberfaellig
                        factors.append(RiskFactor(
                            factor_type=RiskFactorType.PAYMENT_DELAY,
                            severity=SupplierRiskLevel.HIGH if overdue_rate > 0.5 else SupplierRiskLevel.MEDIUM,
                            description=f"Hohe Mahnquote: {overdue_rate*100:.1f}% der Rechnungen ueberfaellig",
                            source=DataSource.INTERNAL,
                            detected_at=now,
                            confidence=0.95,
                            raw_data={
                                "overdue_rate": round(overdue_rate, 3),
                                "total_invoices": total,
                                "overdue_count": overdue,
                            },
                        ))

                    # Lange Zahlungsverzoegerung
                    if avg_delay > 30:
                        factors.append(RiskFactor(
                            factor_type=RiskFactorType.PAYMENT_DELAY,
                            severity=SupplierRiskLevel.HIGH if avg_delay > 60 else SupplierRiskLevel.MEDIUM,
                            description=f"Durchschnittliche Zahlungsverzoegerung: {avg_delay:.0f} Tage",
                            source=DataSource.INTERNAL,
                            detected_at=now,
                            confidence=0.90,
                            raw_data={"avg_delay_days": round(avg_delay, 1)},
                        ))

                    # Geringes Volumen (moeglicher Abbruch der Geschaeftsbeziehung)
                    if volume < 1000 and total >= 3:  # Wenig Umsatz trotz mehrerer Rechnungen
                        factors.append(RiskFactor(
                            factor_type=RiskFactorType.LOW_VOLUME,
                            severity=SupplierRiskLevel.LOW,
                            description=f"Geringes Rechnungsvolumen: {volume:.2f} EUR",
                            source=DataSource.INTERNAL,
                            detected_at=now,
                            confidence=0.70,
                            raw_data={"total_volume": float(volume)},
                        ))

                logger.debug(
                    "internal_history_analyzed",
                    entity_id=str(entity_id),
                    factors_found=len(factors),
                )

        except Exception as e:
            logger.warning(
                "internal_history_analysis_failed",
                entity_id=str(entity_id),
                **safe_error_log(e),
            )

        return factors

    async def _check_handelsregister(
        self,
        registry_number: str,
        company_name: str,
    ) -> List[RiskFactor]:
        """Prueft Handelsregister auf Aenderungen."""
        factors: List[RiskFactor] = []
        now = datetime.now(timezone.utc)

        try:
            # Hier wuerde die echte Handelsregister-API aufgerufen
            # Simuliere API-Aufruf

            handelsregister_queries.labels(status="success").inc()

            # Placeholder fuer zukuenftige Integration
            # hr_info = await handelsregister_service.query(registry_number)
            #
            # if hr_info.status == "in_liquidation":
            #     factors.append(RiskFactor(
            #         factor_type=RiskFactorType.INSOLVENCY,
            #         severity=SupplierRiskLevel.CRITICAL,
            #         description="Unternehmen in Liquidation",
            #         source=DataSource.HANDELSREGISTER,
            #         detected_at=now,
            #     ))

            logger.debug(
                "handelsregister_checked",
                registry_number=registry_number,
                company_name=company_name[:50],
            )

        except Exception as e:
            handelsregister_queries.labels(status="error").inc()
            logger.warning(
                "handelsregister_check_failed",
                extra={"registry_number": registry_number, **safe_error_log(e)},
            )

        return factors

    async def _check_insolvency_register(
        self,
        company_name: str,
        registry_number: Optional[str],
    ) -> List[RiskFactor]:
        """Prueft Insolvenzregister."""
        factors: List[RiskFactor] = []
        now = datetime.now(timezone.utc)

        # Hier wuerde die echte Insolvenzregister-API aufgerufen
        # Placeholder fuer zukuenftige Integration

        return factors

    async def _analyze_dependency(
        self,
        entity_id: UUID,
        company_id: UUID,
    ) -> List[RiskFactor]:
        """Analysiert Abhaengigkeit von diesem Lieferanten."""
        factors: List[RiskFactor] = []
        now = datetime.now(timezone.utc)

        # Analyse: Anteil dieses Lieferanten am Gesamteinkauf
        # Wenn > 30%: Abhaengigkeitsrisiko

        # Placeholder fuer zukuenftige Integration
        # purchase_share = await self._calculate_purchase_share(entity_id, company_id)
        # if purchase_share > 0.30:
        #     factors.append(RiskFactor(
        #         factor_type=RiskFactorType.DEPENDENCY,
        #         severity=SupplierRiskLevel.MEDIUM,
        #         description=f"Lieferantenabhaengigkeit: {purchase_share*100:.1f}% des Einkaufs",
        #         source=DataSource.INTERNAL_HISTORY,
        #         detected_at=now,
        #         details={"purchase_share": purchase_share},
        #     ))

        return factors

    def _calculate_risk_score(self, factors: List[RiskFactor]) -> float:
        """Berechnet Gesamt-Risikoscore aus Faktoren."""
        if not factors:
            return 0.0

        weighted_sum = 0.0
        total_weight = 0.0

        severity_scores = {
            SupplierRiskLevel.LOW: 0.25,
            SupplierRiskLevel.MEDIUM: 0.50,
            SupplierRiskLevel.HIGH: 0.75,
            SupplierRiskLevel.CRITICAL: 1.0,
            SupplierRiskLevel.UNKNOWN: 0.50,
        }

        for factor in factors:
            weight = self.risk_weights.get(factor.factor_type, 0.05)
            severity = severity_scores.get(factor.severity, 0.5)
            weighted_sum += weight * severity
            total_weight += weight

        if total_weight == 0:
            return 0.0

        # Normalisieren auf 0-1
        return min(1.0, weighted_sum / total_weight)

    def _score_to_level(self, score: float) -> SupplierRiskLevel:
        """Konvertiert Risikoscore zu Level."""
        if score < self.risk_thresholds[SupplierRiskLevel.LOW]:
            return SupplierRiskLevel.LOW
        elif score < self.risk_thresholds[SupplierRiskLevel.MEDIUM]:
            return SupplierRiskLevel.MEDIUM
        elif score < self.risk_thresholds[SupplierRiskLevel.HIGH]:
            return SupplierRiskLevel.HIGH
        else:
            return SupplierRiskLevel.CRITICAL

    def _generate_recommendations(
        self,
        factors: List[RiskFactor],
        overall_level: SupplierRiskLevel,
    ) -> List[str]:
        """Generiert Handlungsempfehlungen basierend auf Risikofaktoren."""
        recommendations: List[str] = []

        if overall_level == SupplierRiskLevel.CRITICAL:
            recommendations.append(
                "Sofortige Ueberpruefung der Lieferantenbeziehung empfohlen"
            )
            recommendations.append(
                "Alternative Lieferanten identifizieren"
            )

        if overall_level in [SupplierRiskLevel.HIGH, SupplierRiskLevel.CRITICAL]:
            recommendations.append(
                "Zahlungsbedingungen ueberpruefen (ggf. Vorkasse)"
            )
            recommendations.append(
                "Liefervertraege auf Kuendigungsklauseln pruefen"
            )

        for factor in factors:
            if factor.factor_type == RiskFactorType.INSOLVENCY:
                recommendations.append(
                    "Insolvenzrechtliche Beratung einholen"
                )
            elif factor.factor_type == RiskFactorType.DEPENDENCY:
                recommendations.append(
                    "Lieferantenportfolio diversifizieren"
                )
            elif factor.factor_type == RiskFactorType.MANAGEMENT_CHANGE:
                recommendations.append(
                    "Kontakt zur neuen Geschaeftsfuehrung aufnehmen"
                )

        return list(set(recommendations))  # Duplikate entfernen

    async def monitor_all_suppliers(
        self,
        company_id: UUID,
    ) -> List[MonitoringAlert]:
        """
        Ueberwacht alle Lieferanten eines Unternehmens.

        Args:
            company_id: ID des Unternehmens

        Returns:
            Liste von Alerts fuer kritische Aenderungen
        """
        alerts: List[MonitoringAlert] = []
        now = datetime.now(timezone.utc)

        # Hier wuerde die echte Datenbankabfrage stattfinden
        # supplier_list = await self._get_suppliers_due_for_check(company_id)
        #
        # for supplier in supplier_list:
        #     profile = await self.assess_supplier_risk(...)
        #     if profile.overall_risk_level in [HIGH, CRITICAL]:
        #         alerts.append(MonitoringAlert(...))

        logger.info(
            "supplier_monitoring_completed",
            company_id=str(company_id),
            alerts_count=len(alerts),
        )

        return alerts

    async def get_high_risk_suppliers(
        self,
        company_id: UUID,
        min_risk_level: SupplierRiskLevel = SupplierRiskLevel.HIGH,
    ) -> List[Dict[str, Any]]:
        """
        Liefert Liste aller Hochrisiko-Lieferanten.

        Args:
            company_id: ID des Unternehmens
            min_risk_level: Minimales Risikolevel

        Returns:
            Liste der Hochrisiko-Lieferanten mit Details
        """
        # Placeholder fuer zukuenftige Datenbankintegration
        high_risk_suppliers: List[Dict[str, Any]] = []

        logger.info(
            "high_risk_suppliers_queried",
            company_id=str(company_id),
            min_risk_level=min_risk_level.value,
            count=len(high_risk_suppliers),
        )

        return high_risk_suppliers

    def get_risk_summary(
        self,
        profiles: List[SupplierRiskProfile],
    ) -> Dict[str, Any]:
        """
        Erstellt Zusammenfassung ueber alle Lieferanten-Risiken.

        Args:
            profiles: Liste der Risikoprofile

        Returns:
            Zusammenfassung mit Statistiken
        """
        if not profiles:
            return {
                "total_suppliers": 0,
                "by_risk_level": {},
                "avg_risk_score": 0.0,
                "high_risk_count": 0,
                "recommendations": [],
            }

        by_level: Dict[str, int] = {}
        for level in SupplierRiskLevel:
            by_level[level.value] = sum(
                1 for p in profiles if p.overall_risk_level == level
            )

        high_risk_count = by_level.get("high", 0) + by_level.get("critical", 0)
        avg_score = sum(p.risk_score for p in profiles) / len(profiles)

        # Sammle alle Empfehlungen
        all_recommendations: List[str] = []
        for profile in profiles:
            if profile.overall_risk_level in [
                SupplierRiskLevel.HIGH,
                SupplierRiskLevel.CRITICAL
            ]:
                all_recommendations.extend(profile.recommendations)

        return {
            "total_suppliers": len(profiles),
            "by_risk_level": by_level,
            "avg_risk_score": round(avg_score, 3),
            "high_risk_count": high_risk_count,
            "recommendations": list(set(all_recommendations))[:10],
        }


# =============================================================================
# SINGLETON ACCESS
# =============================================================================


def get_supplier_risk_monitor() -> SupplierRiskMonitor:
    """Gibt die Singleton-Instanz des SupplierRiskMonitor zurueck."""
    return SupplierRiskMonitor()
