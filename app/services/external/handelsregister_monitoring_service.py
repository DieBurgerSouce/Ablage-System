# -*- coding: utf-8 -*-
"""
Handelsregister Monitoring Service.

Vision 2026 Q4: Erweitertes Handelsregister-Monitoring.

Features:
- Automatische Firmen-Validierung bei Entity-Anlage
- Insolvenz-Monitoring für Kunden/Lieferanten
- Jahresabschluss-Abruf
- Änderungs-Benachrichtigungen
- Integration mit Risk-Scoring
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Set, TypedDict, Union
from uuid import UUID, uuid4

import structlog
try:
    from cachetools import TTLCache
except ImportError:
    # Fallback: einfacher Dict-basierter Cache ohne TTL
    class TTLCache(dict):  # type: ignore[no-redef]
        def __init__(self, maxsize: int = 128, ttl: int = 300):
            super().__init__()
            self._maxsize = maxsize
from prometheus_client import Counter, Gauge

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metrics
# =============================================================================

COMPANY_VALIDATIONS = Counter(
    "handelsregister_validations_total",
    "Total company validations performed",
    ["company_id", "result"]
)

INSOLVENCY_CHECKS = Counter(
    "handelsregister_insolvency_checks_total",
    "Total insolvency checks performed",
    ["company_id"]
)

MONITORED_ENTITIES = Gauge(
    "handelsregister_monitored_entities",
    "Number of entities being monitored",
    ["company_id"]
)

INSOLVENCY_ALERTS = Counter(
    "handelsregister_insolvency_alerts_total",
    "Insolvency alerts triggered",
    ["company_id", "severity"]
)


# =============================================================================
# Enums
# =============================================================================

class CompanyStatus(str, Enum):
    """Status einer Firma im Handelsregister."""
    ACTIVE = "active"
    IN_LIQUIDATION = "in_liquidation"
    DISSOLVED = "dissolved"
    MERGED = "merged"
    UNKNOWN = "unknown"


class InsolvencyType(str, Enum):
    """Art des Insolvenzverfahrens."""
    NONE = "none"
    APPLICATION = "application"        # Antrag gestellt
    PRELIMINARY = "preliminary"        # Vorläufige Insolvenz
    OPENED = "opened"                  # Eröffnet
    SELF_ADMIN = "self_administration"  # Eigenverwaltung
    REJECTED = "rejected"              # Mangels Masse abgewiesen
    CONCLUDED = "concluded"            # Abgeschlossen


class MonitoringEvent(str, Enum):
    """Typ des Monitoring-Events."""
    NAME_CHANGE = "name_change"
    ADDRESS_CHANGE = "address_change"
    MANAGEMENT_CHANGE = "management_change"
    CAPITAL_CHANGE = "capital_change"
    STATUS_CHANGE = "status_change"
    INSOLVENCY_NOTICE = "insolvency_notice"
    ANNUAL_REPORT = "annual_report"
    LIQUIDATION = "liquidation"


class ValidationResult(str, Enum):
    """Ergebnis einer Validierung."""
    VALID = "valid"           # Firma existiert und ist aktiv
    INVALID = "invalid"       # Firma nicht gefunden
    INACTIVE = "inactive"     # Firma aufgeloest/liquidiert
    WARNING = "warning"       # Firma existiert mit Abweichungen
    PENDING = "pending"       # Validierung laeuft


# =============================================================================
# TypedDicts for Type Safety
# =============================================================================


class CompanyValidationDict(TypedDict):
    """Typisiertes Dictionary für CompanyValidation.to_dict()."""
    entity_id: str
    company_name: str
    result: str
    validated_at: str
    register_court: Optional[str]
    register_number: Optional[str]
    legal_form: Optional[str]
    status: str
    name_matches: bool
    address_matches: bool
    discrepancies: List[str]
    insolvency_status: str


class InsolvencyRecordDict(TypedDict):
    """Typisiertes Dictionary für InsolvencyRecord.to_dict()."""
    company_name: str
    court: str
    case_number: str
    insolvency_type: str
    filing_date: str
    opening_date: Optional[str]
    administrator: Optional[str]
    creditor_meeting_date: Optional[str]
    notes: Optional[str]


class AlertDetailsDict(TypedDict, total=False):
    """Details eines Alerts (optionale Felder)."""
    old_status: str
    new_status: str
    change_date: str
    source: str


class MonitoringAlertDict(TypedDict):
    """Typisiertes Dictionary für MonitoringAlert.to_dict()."""
    id: str
    entity_id: str
    company_id: str
    entity_name: str
    event_type: str
    severity: str
    title: str
    message: str
    details: AlertDetailsDict
    old_value: Optional[str]
    new_value: Optional[str]
    detected_at: str
    acknowledged: bool


class AnnualReportDict(TypedDict):
    """Typisiertes Dictionary für AnnualReport.to_dict()."""
    company_name: str
    fiscal_year: int
    publication_date: str
    total_assets: Optional[str]
    equity: Optional[str]
    revenue: Optional[str]
    profit_loss: Optional[str]
    employees: Optional[int]
    equity_ratio: Optional[str]
    return_on_equity: Optional[str]
    debt_ratio: Optional[str]
    document_type: str


class RiskImpactDict(TypedDict):
    """Typisiertes Dictionary für calculate_risk_impact()."""
    entity_id: str
    risk_factor: int
    factors: List[str]


class RiskImpactMinimalDict(TypedDict):
    """Minimales Risk Impact Dictionary für nicht überwachte Entities."""
    risk_factor: int
    reason: str


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class CompanyValidation:
    """Ergebnis einer Firmen-Validierung."""
    entity_id: UUID
    company_name: str
    result: ValidationResult
    validated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Gefundene Daten
    register_court: Optional[str] = None
    register_number: Optional[str] = None
    legal_form: Optional[str] = None
    status: CompanyStatus = CompanyStatus.UNKNOWN

    # Abweichungen
    name_matches: bool = True
    address_matches: bool = True
    discrepancies: List[str] = field(default_factory=list)

    # Insolvenz
    insolvency_status: InsolvencyType = InsolvencyType.NONE

    def to_dict(self) -> CompanyValidationDict:
        """Konvertiert zu Dictionary."""
        return CompanyValidationDict(
            entity_id=str(self.entity_id),
            company_name=self.company_name,
            result=self.result.value,
            validated_at=self.validated_at.isoformat(),
            register_court=self.register_court,
            register_number=self.register_number,
            legal_form=self.legal_form,
            status=self.status.value,
            name_matches=self.name_matches,
            address_matches=self.address_matches,
            discrepancies=self.discrepancies,
            insolvency_status=self.insolvency_status.value,
        )


@dataclass
class InsolvencyRecord:
    """Insolvenz-Eintrag."""
    company_name: str
    court: str
    case_number: str
    insolvency_type: InsolvencyType
    filing_date: date
    opening_date: Optional[date] = None
    administrator: Optional[str] = None
    creditor_meeting_date: Optional[date] = None
    notes: Optional[str] = None

    def to_dict(self) -> InsolvencyRecordDict:
        """Konvertiert zu Dictionary."""
        return InsolvencyRecordDict(
            company_name=self.company_name,
            court=self.court,
            case_number=self.case_number,
            insolvency_type=self.insolvency_type.value,
            filing_date=self.filing_date.isoformat(),
            opening_date=self.opening_date.isoformat() if self.opening_date else None,
            administrator=self.administrator,
            creditor_meeting_date=self.creditor_meeting_date.isoformat() if self.creditor_meeting_date else None,
            notes=self.notes,
        )


@dataclass
class MonitoringAlert:
    """Ein Monitoring-Alert."""
    id: UUID = field(default_factory=uuid4)
    entity_id: UUID = field(default_factory=uuid4)
    company_id: UUID = field(default_factory=uuid4)
    entity_name: str = ""
    event_type: MonitoringEvent = MonitoringEvent.STATUS_CHANGE
    severity: str = "medium"  # low, medium, high, critical

    title: str = ""
    message: str = ""
    details: AlertDetailsDict = field(default_factory=lambda: AlertDetailsDict())

    old_value: Optional[str] = None
    new_value: Optional[str] = None

    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    acknowledged: bool = False
    acknowledged_by: Optional[UUID] = None
    acknowledged_at: Optional[datetime] = None

    def to_dict(self) -> MonitoringAlertDict:
        """Konvertiert zu Dictionary."""
        return MonitoringAlertDict(
            id=str(self.id),
            entity_id=str(self.entity_id),
            company_id=str(self.company_id),
            entity_name=self.entity_name,
            event_type=self.event_type.value,
            severity=self.severity,
            title=self.title,
            message=self.message,
            details=self.details,
            old_value=self.old_value,
            new_value=self.new_value,
            detected_at=self.detected_at.isoformat(),
            acknowledged=self.acknowledged,
        )


@dataclass
class AnnualReport:
    """Jahresabschluss-Daten."""
    company_name: str
    fiscal_year: int
    publication_date: date

    # Bilanzdaten
    total_assets: Optional[Decimal] = None
    equity: Optional[Decimal] = None
    revenue: Optional[Decimal] = None
    profit_loss: Optional[Decimal] = None
    employees: Optional[int] = None

    # Kennzahlen
    equity_ratio: Optional[Decimal] = None  # Eigenkapitalquote
    return_on_equity: Optional[Decimal] = None  # Eigenkapitalrendite
    debt_ratio: Optional[Decimal] = None  # Verschuldungsgrad

    # Dokumente
    document_url: Optional[str] = None
    document_type: str = "full"  # full, abbreviated, micro

    def to_dict(self) -> AnnualReportDict:
        """Konvertiert zu Dictionary."""
        return AnnualReportDict(
            company_name=self.company_name,
            fiscal_year=self.fiscal_year,
            publication_date=self.publication_date.isoformat(),
            total_assets=str(self.total_assets) if self.total_assets else None,
            equity=str(self.equity) if self.equity else None,
            revenue=str(self.revenue) if self.revenue else None,
            profit_loss=str(self.profit_loss) if self.profit_loss else None,
            employees=self.employees,
            equity_ratio=str(self.equity_ratio) if self.equity_ratio else None,
            return_on_equity=str(self.return_on_equity) if self.return_on_equity else None,
            debt_ratio=str(self.debt_ratio) if self.debt_ratio else None,
            document_type=self.document_type,
        )


@dataclass
class MonitoredEntity:
    """Eine überwachte Entity."""
    entity_id: UUID
    company_id: UUID
    entity_name: str
    register_number: Optional[str] = None

    # Monitoring-Konfiguration
    monitor_insolvency: bool = True
    monitor_changes: bool = True
    monitor_annual_reports: bool = True

    # Status
    last_check_at: Optional[datetime] = None
    next_check_at: Optional[datetime] = None
    last_validation: Optional[CompanyValidation] = None

    # Alerts
    pending_alerts: List[MonitoringAlert] = field(default_factory=list)


# =============================================================================
# Service
# =============================================================================

class HandelsregisterMonitoringService:
    """
    Service für Handelsregister-Monitoring.

    Features:
    - Automatische Validierung bei Entity-Anlage
    - Kontinuierliches Insolvenz-Monitoring
    - Jahresabschluss-Abruf
    - Änderungs-Benachrichtigungen
    """

    def __init__(self) -> None:
        self._monitored_entities: Dict[UUID, MonitoredEntity] = {}
        self._alerts: Dict[UUID, MonitoringAlert] = {}
        # SECURITY FIX: TTL-Cache mit max 1000 Einträgen und 1h TTL
        # Verhindert unbegrenztes Wachstum (Memory Leak)
        self._validation_cache: TTLCache[str, CompanyValidation] = TTLCache(
            maxsize=1000,
            ttl=3600,  # 1 Stunde
        )

        logger.info("handelsregister_monitoring_service_initialized")

    async def validate_company(
        self,
        entity_id: UUID,
        company_id: UUID,
        company_name: str,
        address: Optional[str] = None,
        register_number: Optional[str] = None,
    ) -> CompanyValidation:
        """
        Validiert eine Firma im Handelsregister.

        Args:
            entity_id: Entity-ID
            company_id: Company-ID (Tenant)
            company_name: Firmenname
            address: Adresse zur Validierung
            register_number: Bekannte Registernummer

        Returns:
            Validierungsergebnis
        """
        logger.info(
            "validating_company",
            entity_id=str(entity_id),
            company_name=company_name,
        )

        # In Produktion: Echte Handelsregister-API-Abfrage
        # Hier: Mock-Validierung

        validation = await self._perform_validation(
            entity_id=entity_id,
            company_name=company_name,
            address=address,
            register_number=register_number,
        )

        # Cache aktualisieren
        cache_key = f"{company_name}:{register_number or ''}"
        self._validation_cache[cache_key] = validation

        # Metrics
        COMPANY_VALIDATIONS.labels(
            company_id=str(company_id),
            result=validation.result.value,
        ).inc()

        # Wenn Entity noch nicht überwacht wird, hinzufuegen
        if entity_id not in self._monitored_entities:
            await self.start_monitoring(
                entity_id=entity_id,
                company_id=company_id,
                entity_name=company_name,
                register_number=validation.register_number,
            )

        return validation

    async def _perform_validation(
        self,
        entity_id: UUID,
        company_name: str,
        address: Optional[str],
        register_number: Optional[str],
    ) -> CompanyValidation:
        """
        Führt die eigentliche Validierung durch.

        HINWEIS: Mock-Implementierung mit deterministischer Logik.
        In Produktion durch echte Handelsregister-API ersetzen.
        """
        # Erkenne Rechtsform
        legal_form = None
        if "GmbH" in company_name:
            legal_form = "GmbH"
        elif "AG" in company_name:
            legal_form = "AG"
        elif "UG" in company_name:
            legal_form = "UG"
        elif "KG" in company_name:
            legal_form = "KG"
        elif "OHG" in company_name:
            legal_form = "OHG"

        # Deterministisches Seeding basierend auf Firmennamen
        name_hash = int(hashlib.md5(company_name.encode()).hexdigest()[:8], 16)

        if "Test" in company_name or "INVALID" in company_name:
            return CompanyValidation(
                entity_id=entity_id,
                company_name=company_name,
                result=ValidationResult.INVALID,
                discrepancies=["Firma im Handelsregister nicht gefunden"],
            )

        if "INSOLVENT" in company_name:
            # Deterministisch statt random
            mock_hrb = 100000 + (name_hash % 900000)
            return CompanyValidation(
                entity_id=entity_id,
                company_name=company_name,
                result=ValidationResult.WARNING,
                register_court="Amtsgericht Muenchen",
                register_number=register_number or f"HRB {mock_hrb}",
                legal_form=legal_form,
                status=CompanyStatus.IN_LIQUIDATION,
                insolvency_status=InsolvencyType.OPENED,
                discrepancies=["Insolvenzverfahren eröffnet"],
            )

        if "LIQUIDATION" in company_name:
            mock_hrb = 100000 + (name_hash % 900000)
            return CompanyValidation(
                entity_id=entity_id,
                company_name=company_name,
                result=ValidationResult.INACTIVE,
                register_court="Amtsgericht Frankfurt",
                register_number=register_number or f"HRB {mock_hrb}",
                legal_form=legal_form,
                status=CompanyStatus.DISSOLVED,
                discrepancies=["Firma gelöscht"],
            )

        # Standard: Erfolgreiche Validierung mit deterministischen Checks
        mock_hrb = 100000 + (name_hash % 900000)
        # Deterministisch: ~90% Name-Match, ~85% Adress-Match basierend auf Hash
        name_matches = (name_hash % 10) != 0  # 90% True
        address_matches = (name_hash % 7) != 0  # ~85% True

        return CompanyValidation(
            entity_id=entity_id,
            company_name=company_name,
            result=ValidationResult.VALID,
            register_court=self._get_mock_court(company_name),
            register_number=register_number or f"HRB {mock_hrb}",
            legal_form=legal_form,
            status=CompanyStatus.ACTIVE,
            name_matches=name_matches,
            address_matches=address_matches,
        )

    async def check_insolvency(
        self,
        entity_id: UUID,
        company_name: str,
    ) -> Optional[InsolvencyRecord]:
        """
        Prüft auf Insolvenzverfahren.

        Args:
            entity_id: Entity-ID
            company_name: Firmenname

        Returns:
            InsolvencyRecord falls vorhanden
        """
        logger.info(
            "checking_insolvency",
            entity_id=str(entity_id),
            company_name=company_name,
        )

        # In Produktion: Insolvenzbekanntmachungen-API
        # https://www.insolvenzbekanntmachungen.de/

        monitored = self._monitored_entities.get(entity_id)
        if monitored:
            INSOLVENCY_CHECKS.labels(
                company_id=str(monitored.company_id),
            ).inc()

        # Mock: Simuliere Insolvenz bei bestimmten Namen
        if "INSOLVENT" in company_name.upper():
            return InsolvencyRecord(
                company_name=company_name,
                court="Amtsgericht Muenchen",
                case_number=f"IN {uuid4().hex[:4].upper()}/26",
                insolvency_type=InsolvencyType.OPENED,
                filing_date=date.today() - timedelta(days=30),
                opening_date=date.today() - timedelta(days=14),
                administrator="RA Dr. Mustermann",
                creditor_meeting_date=date.today() + timedelta(days=30),
            )

        return None

    async def get_annual_reports(
        self,
        entity_id: UUID,
        company_name: str,
        years: int = 3,
    ) -> List[AnnualReport]:
        """
        Ruft Jahresabschluesse ab.

        Args:
            entity_id: Entity-ID
            company_name: Firmenname
            years: Anzahl Jahre

        Returns:
            Liste von Jahresabschluessen
        """
        logger.info(
            "fetching_annual_reports",
            entity_id=str(entity_id),
            company_name=company_name,
            years=years,
        )

        # In Produktion: Bundesanzeiger-API
        # https://www.bundesanzeiger.de/

        # Mock: Generiere Beispiel-Jahresabschluesse
        reports = []
        current_year = date.today().year

        for i in range(years):
            year = current_year - i - 1
            reports.append(self._generate_mock_annual_report(company_name, year))

        return reports

    def _generate_mock_annual_report(
        self,
        company_name: str,
        year: int,
    ) -> AnnualReport:
        """
        Generiert Mock-Jahresabschluss.

        HINWEIS: Deterministisch für Testbarkeit.
        In Produktion durch Bundesanzeiger-API ersetzen.
        """
        # Deterministisches Seeding basierend auf Name + Jahr
        seed_str = f"{company_name}:{year}"
        seed = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)

        # Deterministischer Revenue: 100k - 10M basierend auf Hash
        base_revenue = Decimal(100000 + (seed % 9900000))
        base_assets = base_revenue * Decimal("1.5")

        # Eigenkapitalquote: 20-50% deterministisch
        equity_ratio_pct = 20 + (seed % 31)  # 20-50
        equity = base_assets * Decimal(str(equity_ratio_pct / 100))

        # Gewinn: -5% bis +15% deterministisch
        profit_pct = -5 + (seed % 21)  # -5 bis +15
        profit = base_revenue * Decimal(str(profit_pct / 100))

        # Mitarbeiter: 5-500 deterministisch
        employees = 5 + (seed % 496)

        # Document Type deterministisch
        doc_types = ["full", "abbreviated", "micro"]
        doc_type = doc_types[seed % 3]

        return AnnualReport(
            company_name=company_name,
            fiscal_year=year,
            publication_date=date(year + 1, 6, 30),
            total_assets=base_assets.quantize(Decimal("0.01")),
            equity=equity.quantize(Decimal("0.01")),
            revenue=base_revenue.quantize(Decimal("0.01")),
            profit_loss=profit.quantize(Decimal("0.01")),
            employees=employees,
            equity_ratio=(equity / base_assets * 100).quantize(Decimal("0.1")),
            return_on_equity=(profit / equity * 100).quantize(Decimal("0.1")) if equity > 0 else None,
            document_type=doc_type,
        )

    async def start_monitoring(
        self,
        entity_id: UUID,
        company_id: UUID,
        entity_name: str,
        register_number: Optional[str] = None,
        monitor_insolvency: bool = True,
        monitor_changes: bool = True,
        monitor_annual_reports: bool = True,
    ) -> MonitoredEntity:
        """
        Startet Monitoring für eine Entity.

        Args:
            entity_id: Entity-ID
            company_id: Company-ID (Tenant)
            entity_name: Firmenname
            register_number: Registernummer
            monitor_insolvency: Insolvenz überwachen
            monitor_changes: Änderungen überwachen
            monitor_annual_reports: Jahresabschluesse überwachen

        Returns:
            MonitoredEntity
        """
        monitored = MonitoredEntity(
            entity_id=entity_id,
            company_id=company_id,
            entity_name=entity_name,
            register_number=register_number,
            monitor_insolvency=monitor_insolvency,
            monitor_changes=monitor_changes,
            monitor_annual_reports=monitor_annual_reports,
            next_check_at=datetime.now(timezone.utc) + timedelta(days=1),
        )

        self._monitored_entities[entity_id] = monitored

        MONITORED_ENTITIES.labels(
            company_id=str(company_id),
        ).set(len([e for e in self._monitored_entities.values() if e.company_id == company_id]))

        logger.info(
            "entity_monitoring_started",
            entity_id=str(entity_id),
            entity_name=entity_name,
        )

        return monitored

    async def stop_monitoring(self, entity_id: UUID) -> bool:
        """
        Stoppt Monitoring für eine Entity.

        Args:
            entity_id: Entity-ID

        Returns:
            True wenn gestoppt
        """
        if entity_id in self._monitored_entities:
            monitored = self._monitored_entities.pop(entity_id)

            MONITORED_ENTITIES.labels(
                company_id=str(monitored.company_id),
            ).set(len([e for e in self._monitored_entities.values() if e.company_id == monitored.company_id]))

            logger.info(
                "entity_monitoring_stopped",
                entity_id=str(entity_id),
            )
            return True

        return False

    async def run_monitoring_check(self) -> List[MonitoringAlert]:
        """
        Führt Monitoring-Prüfung für alle fälligen Entities durch.

        Returns:
            Liste von generierten Alerts
        """
        now = datetime.now(timezone.utc)
        alerts: List[MonitoringAlert] = []

        for monitored in self._monitored_entities.values():
            # Prüfen ob Check fällig
            if monitored.next_check_at and monitored.next_check_at > now:
                continue

            try:
                entity_alerts = await self._check_entity(monitored)
                alerts.extend(entity_alerts)

                # Nächsten Check planen
                monitored.last_check_at = now
                monitored.next_check_at = now + timedelta(days=1)

            except Exception as e:
                # SECURITY: Keine PII/Exception-Details in Logs (CWE-532)
                logger.error(
                    "monitoring_check_failed",
                    entity_id=str(monitored.entity_id),
                    error_type=type(e).__name__,
                )

        return alerts

    async def _check_entity(
        self,
        monitored: MonitoredEntity,
    ) -> List[MonitoringAlert]:
        """Prüft eine einzelne Entity."""
        alerts: List[MonitoringAlert] = []

        # 1. Insolvenz-Check
        if monitored.monitor_insolvency:
            insolvency = await self.check_insolvency(
                monitored.entity_id,
                monitored.entity_name,
            )

            if insolvency and insolvency.insolvency_type != InsolvencyType.NONE:
                # SECURITY: Keine PII (Entity-Namen) in Alert-Titles (CWE-532/GDPR)
                # Entity-ID kann zur Aufloesung verwendet werden, Name nicht in Logs/Titles
                alert = MonitoringAlert(
                    entity_id=monitored.entity_id,
                    company_id=monitored.company_id,
                    entity_name=monitored.entity_name,  # Bleibt für interne Verarbeitung
                    event_type=MonitoringEvent.INSOLVENCY_NOTICE,
                    severity="critical",
                    title="Insolvenzverfahren gemeldet",  # SECURITY: Generischer Titel
                    message=f"Insolvenzverfahren {insolvency.insolvency_type.value} gemeldet",
                    # SECURITY: Nur nicht-PII Details, keine Firmennamen in details
                    details=AlertDetailsDict(
                        source="insolvenzregister",
                    ),
                )
                alerts.append(alert)
                self._alerts[alert.id] = alert

                INSOLVENCY_ALERTS.labels(
                    company_id=str(monitored.company_id),
                    severity="critical",
                ).inc()

        # 2. Validierung wiederholen (bei letzter Warnung)
        if monitored.last_validation and monitored.last_validation.result == ValidationResult.WARNING:
            new_validation = await self._perform_validation(
                entity_id=monitored.entity_id,
                company_name=monitored.entity_name,
                address=None,
                register_number=monitored.register_number,
            )

            if new_validation.status != monitored.last_validation.status:
                # SECURITY: Keine PII (Entity-Namen) in Alert-Titles (CWE-532/GDPR)
                alert = MonitoringAlert(
                    entity_id=monitored.entity_id,
                    company_id=monitored.company_id,
                    entity_name=monitored.entity_name,  # Bleibt für interne Verarbeitung
                    event_type=MonitoringEvent.STATUS_CHANGE,
                    severity="high",
                    title="Handelsregister Status-Änderung",  # SECURITY: Generischer Titel
                    message=f"Status geändert von {monitored.last_validation.status.value} zu {new_validation.status.value}",
                    old_value=monitored.last_validation.status.value,
                    new_value=new_validation.status.value,
                )
                alerts.append(alert)
                self._alerts[alert.id] = alert

            monitored.last_validation = new_validation

        return alerts

    async def get_pending_alerts(
        self,
        company_id: Optional[UUID] = None,
        entity_id: Optional[UUID] = None,
    ) -> List[MonitoringAlert]:
        """
        Holt ausstehende Alerts.

        Args:
            company_id: Optional Company-Filter
            entity_id: Optional Entity-Filter

        Returns:
            Liste von Alerts
        """
        alerts = [a for a in self._alerts.values() if not a.acknowledged]

        if company_id:
            alerts = [a for a in alerts if a.company_id == company_id]

        if entity_id:
            alerts = [a for a in alerts if a.entity_id == entity_id]

        return sorted(alerts, key=lambda a: a.detected_at, reverse=True)

    async def acknowledge_alert(
        self,
        alert_id: UUID,
        user_id: UUID,
        company_id: Optional[UUID] = None,
    ) -> bool:
        """
        Bestätigt einen Alert.

        SECURITY: Validiert Company-Ownership um Cross-Company Access zu verhindern.

        Args:
            alert_id: Alert-ID
            user_id: Benutzer-ID
            company_id: Company-ID für Ownership-Check (EMPFOHLEN)

        Returns:
            True wenn bestätigt

        Raises:
            PermissionError: Wenn company_id nicht zum Alert passt
        """
        alert = self._alerts.get(alert_id)
        if not alert:
            return False

        # SECURITY: Validiere Company-Ownership
        if company_id is not None and alert.company_id != company_id:
            logger.warning(
                "unauthorized_alert_acknowledge_attempt",
                alert_id=str(alert_id),
                user_id=str(user_id),
                user_company_id=str(company_id),
                alert_company_id=str(alert.company_id),
            )
            raise PermissionError(
                f"Keine Berechtigung für Alert {alert_id}. "
                f"Alert gehoert zu anderer Firma."
            )

        alert.acknowledged = True
        alert.acknowledged_by = user_id
        alert.acknowledged_at = datetime.now(timezone.utc)
        return True

    def get_monitored_entities(
        self,
        company_id: Optional[UUID] = None,
    ) -> List[MonitoredEntity]:
        """
        Listet überwachte Entities.

        Args:
            company_id: Optional Company-Filter

        Returns:
            Liste von MonitoredEntity
        """
        entities = list(self._monitored_entities.values())

        if company_id:
            entities = [e for e in entities if e.company_id == company_id]

        return entities

    async def calculate_risk_impact(
        self,
        entity_id: UUID,
    ) -> Union[RiskImpactDict, RiskImpactMinimalDict]:
        """
        Berechnet Risk-Impact basierend auf Handelsregister-Daten.

        Args:
            entity_id: Entity-ID

        Returns:
            Risk-Impact-Daten zur Integration mit RiskScoringService
        """
        monitored = self._monitored_entities.get(entity_id)
        if not monitored:
            return RiskImpactMinimalDict(risk_factor=0, reason="Nicht überwacht")

        risk_factor = 0
        factors: List[str] = []

        # Validierungs-Status
        if monitored.last_validation:
            if monitored.last_validation.result == ValidationResult.INVALID:
                risk_factor += 30
                factors.append("Firma nicht im Handelsregister gefunden")

            elif monitored.last_validation.result == ValidationResult.INACTIVE:
                risk_factor += 50
                factors.append("Firma gelöscht/aufgeloest")

            elif monitored.last_validation.result == ValidationResult.WARNING:
                risk_factor += 15
                factors.append("Warnungen bei Validierung")

            # Insolvenz
            if monitored.last_validation.insolvency_status != InsolvencyType.NONE:
                risk_factor += 40
                factors.append(
                    f"Insolvenzstatus: {monitored.last_validation.insolvency_status.value}"
                )

        # Offene Alerts
        pending = [a for a in self._alerts.values()
                   if a.entity_id == entity_id and not a.acknowledged]
        if pending:
            risk_factor += 10 * len(pending)
            factors.append(f"{len(pending)} offene Alerts")

        return RiskImpactDict(
            entity_id=str(entity_id),
            risk_factor=risk_factor,
            factors=factors,
        )

    def _get_mock_court(self, company_name: str) -> str:
        """Generiert Mock-Registergericht."""
        courts = [
            "Amtsgericht Muenchen",
            "Amtsgericht Frankfurt am Main",
            "Amtsgericht Berlin Charlottenburg",
            "Amtsgericht Hamburg",
            "Amtsgericht Koeln",
            "Amtsgericht Duesseldorf",
        ]
        import hashlib
        idx = int(hashlib.md5(company_name.encode()).hexdigest()[:8], 16) % len(courts)
        return courts[idx]


# =============================================================================
# Factory
# =============================================================================

_service_instance: Optional[HandelsregisterMonitoringService] = None


def get_handelsregister_monitoring_service() -> HandelsregisterMonitoringService:
    """
    Factory-Funktion für HandelsregisterMonitoringService.

    Returns:
        HandelsregisterMonitoringService Instanz
    """
    global _service_instance

    if _service_instance is None:
        _service_instance = HandelsregisterMonitoringService()

    return _service_instance
