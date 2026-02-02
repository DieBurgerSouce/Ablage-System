# -*- coding: utf-8 -*-
"""
Extended Alerts Service fuer Ablage-System.

Erweitert das bestehende Alert-System um zusaetzliche Alert-Typen:
- CASH_001/002: Liquiditaetswarnungen (integriert mit CashflowPredictionService)
- CONT_001/002: Vertragswarnungen (Ablauf, Kuendigungsfristen)
- COMP_006/007: Compliance-Warnungen (GDPR-Loeschfristen, Aufbewahrungsfristen)
- SUPP_001/002: Lieferanten-Warnungen (Insolvenz, Ownership-Change)

SECURITY:
- NIEMALS Entity-Namen, Kundennummern oder IBANs loggen (PII)
- Alle Warnungen mit company_id gefiltert (Multi-Tenant)
- Keine sensiblen Daten in Alert-Messages

Feinpoliert und durchdacht - Enterprise Extended Alert Management.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_errors import safe_error_log
from app.db.models_alert import Alert, AlertCategory, AlertSeverity, AlertStatus
from app.db.models_contract import Contract, ContractStatus, ContractDeadline
from app.db.models import BusinessEntity, Document, Company
from app.services.alert_center_service import AlertCenterService, AlertCodes

logger = structlog.get_logger(__name__)


# =============================================================================
# Extended Alert Codes
# =============================================================================


class ExtendedAlertCodes:
    """Erweiterte Alert-Codes fuer neue Alert-Typen."""

    # Cashflow/Liquiditaet
    CASH_SHORTFALL = "CASH_001"  # Liquiditaetsengpass in X Tagen
    CASH_UNEXPECTED_OUTGOING = "CASH_002"  # Unerwarteter Zahlungsausgang

    # Vertraege
    CONTRACT_EXPIRING = "CONT_001"  # Vertrag laeuft aus in X Tagen
    CONTRACT_NOTICE_DEADLINE = "CONT_002"  # Kuendigungsfrist in X Tagen
    CONTRACT_AUTO_RENEWAL_WARNING = "CONT_003"  # Automatische Verlaengerung steht bevor

    # Compliance
    GDPR_DELETION_DUE = "COMP_006"  # GDPR-Loeschfrist erreicht
    RETENTION_EXPIRY = "COMP_007"  # Aufbewahrungsfrist endet

    # Lieferanten
    SUPPLIER_INSOLVENCY = "SUPP_001"  # Lieferant Insolvenz erkannt
    SUPPLIER_OWNERSHIP_CHANGE = "SUPP_002"  # Ownership-Change bei Lieferant

    # Payment-related
    PAYMENT_SKONTO_EXPIRING = "PAY_001"  # Skonto-Frist laeuft ab
    PAYMENT_OVERDUE_CRITICAL = "PAY_002"  # Kritisch ueberfaellige Zahlung


# =============================================================================
# Extended Alert Templates (German)
# =============================================================================


EXTENDED_ALERT_TEMPLATES: Dict[str, Dict[str, str]] = {
    ExtendedAlertCodes.CASH_SHORTFALL: {
        "title": "Liquiditaetsengpass in {days} Tagen erwartet",
        "message": "Basierend auf der Cashflow-Prognose wird am {date} ein Liquiditaetsengpass "
                   "von voraussichtlich {amount} EUR erwartet. Empfohlene Massnahmen pruefen.",
    },
    ExtendedAlertCodes.CASH_UNEXPECTED_OUTGOING: {
        "title": "Unerwarteter Zahlungsausgang erkannt",
        "message": "Ein unerwarteter Zahlungsausgang von {amount} EUR wurde fuer {date} "
                   "identifiziert. Dieser Betrag weicht signifikant von den ueblichen Mustern ab.",
    },
    ExtendedAlertCodes.CONTRACT_EXPIRING: {
        "title": "Vertrag laeuft in {days} Tagen ab",
        "message": "Der Vertrag '{contract_title}' (Nr. {contract_number}) laeuft am {end_date} ab. "
                   "Bitte pruefen Sie, ob eine Verlaengerung oder Kuendigung erforderlich ist.",
    },
    ExtendedAlertCodes.CONTRACT_NOTICE_DEADLINE: {
        "title": "Kuendigungsfrist in {days} Tagen",
        "message": "Die Kuendigungsfrist fuer Vertrag '{contract_title}' (Nr. {contract_number}) "
                   "endet am {notice_date}. Bei Nichtkuendigung erfolgt ggf. automatische Verlaengerung.",
    },
    ExtendedAlertCodes.CONTRACT_AUTO_RENEWAL_WARNING: {
        "title": "Automatische Vertragsverlaengerung steht bevor",
        "message": "Der Vertrag '{contract_title}' wird am {renewal_date} automatisch verlaengert, "
                   "wenn keine Kuendigung erfolgt. Neue Laufzeit: {renewal_months} Monate.",
    },
    ExtendedAlertCodes.GDPR_DELETION_DUE: {
        "title": "GDPR-Loeschfrist erreicht",
        "message": "Die DSGVO-Loeschfrist fuer {document_count} Dokument(e) ist erreicht. "
                   "Eine Loeschung oder begruendete Verlaengerung ist erforderlich.",
    },
    ExtendedAlertCodes.RETENTION_EXPIRY: {
        "title": "Aufbewahrungsfrist endet",
        "message": "Die gesetzliche Aufbewahrungsfrist fuer {document_count} Dokument(e) endet "
                   "am {expiry_date}. Eine Archivierung oder Loeschung kann erfolgen.",
    },
    ExtendedAlertCodes.SUPPLIER_INSOLVENCY: {
        "title": "Moegliche Lieferanten-Insolvenz erkannt",
        "message": "Es gibt Hinweise auf finanzielle Schwierigkeiten bei einem Lieferanten. "
                   "Offene Bestellungen und Rechnungen sollten geprueft werden.",
    },
    ExtendedAlertCodes.SUPPLIER_OWNERSHIP_CHANGE: {
        "title": "Ownership-Change bei Lieferant erkannt",
        "message": "Bei einem Ihrer Lieferanten wurde ein Eigentuemerwechsel festgestellt. "
                   "Vertraege und Konditionen sollten ueberprueft werden.",
    },
    ExtendedAlertCodes.PAYMENT_SKONTO_EXPIRING: {
        "title": "Skonto-Frist laeuft in {days} Tagen ab",
        "message": "Die Skonto-Frist fuer eine Rechnung ueber {amount} EUR laeuft am {deadline} ab. "
                   "Potenzielle Ersparnis: {savings} EUR ({percentage}%).",
    },
    ExtendedAlertCodes.PAYMENT_OVERDUE_CRITICAL: {
        "title": "Kritisch ueberfaellige Zahlung",
        "message": "Eine Rechnung ist seit {days} Tagen ueberfaellig. "
                   "Ausstehender Betrag: {amount} EUR. Mahnstufe: {dunning_level}.",
    },
}


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class CashflowAlertData:
    """Daten fuer Cashflow-bezogene Alerts."""

    date: date
    predicted_balance: Decimal
    shortfall_amount: Decimal
    days_until: int
    confidence: float
    recommendations: List[str]


@dataclass
class ContractAlertData:
    """Daten fuer Vertrags-bezogene Alerts."""

    contract_id: UUID
    contract_number: Optional[str]
    contract_title: str
    deadline_date: date
    days_remaining: int
    deadline_type: str  # "expiration", "notice", "renewal"
    auto_renewal: bool
    renewal_months: Optional[int]


@dataclass
class ComplianceAlertData:
    """Daten fuer Compliance-bezogene Alerts."""

    document_count: int
    expiry_date: date
    compliance_type: str  # "gdpr_deletion", "retention_expiry"
    document_ids: List[UUID]
    action_required: str


@dataclass
class SupplierAlertData:
    """Daten fuer Lieferanten-bezogene Alerts."""

    entity_id: UUID
    alert_type: str  # "insolvency", "ownership_change"
    source: str  # Quelle der Information
    confidence: float
    open_orders_count: int
    open_invoices_amount: Decimal


# =============================================================================
# Extended Alerts Service
# =============================================================================


class ExtendedAlertsService:
    """
    Service fuer erweiterte Alert-Typen.

    Erweitert den AlertCenterService um:
    - Cashflow-basierte Alerts (Integration mit CashflowPredictionService)
    - Vertrags-Alerts (Contract-Fristen und -Ablaufe)
    - Compliance-Alerts (GDPR, Aufbewahrungsfristen)
    - Lieferanten-Alerts (Insolvenz, Ownership-Changes)

    SECURITY:
    - Multi-Tenant via company_id Filter
    - Keine PII in Logs oder Alert-Messages
    - Sichere Aggregation von Daten
    """

    def __init__(self, db: AsyncSession):
        """
        Initialisiere Service mit Datenbankverbindung.

        Args:
            db: AsyncSession fuer Datenbankzugriff
        """
        self.db = db
        self._alert_center: Optional[AlertCenterService] = None

    @property
    def alert_center(self) -> AlertCenterService:
        """Lazy-load AlertCenterService."""
        if self._alert_center is None:
            self._alert_center = AlertCenterService(self.db)
        return self._alert_center

    # =========================================================================
    # Cashflow Alerts
    # =========================================================================

    async def check_cashflow_alerts(
        self,
        company_id: UUID,
        days_ahead: int = 30,
    ) -> List[Alert]:
        """
        Prueft auf Cashflow-bezogene Alert-Bedingungen.

        Integriert mit CashflowPredictionService fuer:
        - Liquiditaetsengpaesse (CASH_001)
        - Unerwartete Zahlungsausgaenge (CASH_002)

        Args:
            company_id: Mandanten-ID
            days_ahead: Vorausschau in Tagen

        Returns:
            Liste erstellter Alerts
        """
        from app.services.ai.cashflow_prediction_service import (
            get_cashflow_prediction_service,
            WarningSeverity as CashWarningSeverity,
            WarningType,
        )

        created_alerts: List[Alert] = []

        try:
            cashflow_service = get_cashflow_prediction_service(self.db)
            warnings = await cashflow_service.get_cashflow_warnings(company_id, days_ahead)

            for warning in warnings:
                # Map WarningType zu AlertCode
                if warning.type == WarningType.SHORTFALL:
                    alert_code = ExtendedAlertCodes.CASH_SHORTFALL
                    severity = AlertSeverity.CRITICAL
                elif warning.type == WarningType.LARGE_OUTGOING:
                    alert_code = ExtendedAlertCodes.CASH_UNEXPECTED_OUTGOING
                    severity = AlertSeverity.MEDIUM
                else:
                    # Andere Warning-Types werden vom Standard-System behandelt
                    continue

                # Map CashflowWarning Severity zu AlertSeverity
                if warning.severity == CashWarningSeverity.CRITICAL:
                    severity = AlertSeverity.CRITICAL
                elif warning.severity == CashWarningSeverity.WARNING:
                    severity = AlertSeverity.HIGH

                # Recurrence Key fuer Deduplizierung
                recurrence_key = f"cash_{alert_code}_{warning.date.isoformat()}_{company_id}"

                # Template-Daten (SECURITY: Keine Entity-Namen)
                template_data = {
                    "days": warning.days_until_trigger,
                    "date": warning.date.strftime("%d.%m.%Y"),
                    "amount": f"{float(abs(warning.affected_amount or 0)):,.2f}",
                }

                template = EXTENDED_ALERT_TEMPLATES.get(alert_code, {})
                title = template.get("title", "Cashflow-Warnung").format(**template_data)
                message = template.get("message", warning.message).format(**template_data)

                alert = await self.alert_center.create_alert(
                    company_id=company_id,
                    alert_code=alert_code,
                    category=AlertCategory.RISK,
                    severity=severity,
                    title=title,
                    message=message,
                    source_type="cashflow_prediction",
                    metadata={
                        "predicted_balance": float(warning.predicted_balance),
                        "days_until": warning.days_until_trigger,
                        "affected_amount": float(warning.affected_amount) if warning.affected_amount else None,
                    },
                    context={
                        "suggested_actions": warning.suggested_actions,
                        "warning_date": warning.date.isoformat(),
                    },
                    available_actions=["acknowledge", "dismiss", "create_task"],
                    recurrence_key=recurrence_key,
                    auto_dismiss_hours=72,  # Auto-Dismiss nach 3 Tagen
                )

                created_alerts.append(alert)
                logger.debug(
                    "cashflow_alert_created",
                    alert_id=str(alert.id),
                    alert_code=alert_code,
                    days_until=warning.days_until_trigger,
                )

        except Exception as e:
            logger.error(
                "cashflow_alerts_check_failed",
                company_id=str(company_id),
                **safe_error_log(e),
            )

        logger.info(
            "cashflow_alerts_checked",
            company_id=str(company_id),
            alerts_created=len(created_alerts),
        )

        return created_alerts

    # =========================================================================
    # Contract Alerts
    # =========================================================================

    async def check_contract_alerts(
        self,
        company_id: UUID,
        days_ahead: int = 90,
    ) -> List[Alert]:
        """
        Prueft auf Vertrags-bezogene Alert-Bedingungen.

        Alerts fuer:
        - Vertragsablauf (CONT_001)
        - Kuendigungsfristen (CONT_002)
        - Automatische Verlaengerungen (CONT_003)

        Args:
            company_id: Mandanten-ID
            days_ahead: Vorausschau in Tagen

        Returns:
            Liste erstellter Alerts
        """
        created_alerts: List[Alert] = []
        today = date.today()
        cutoff_date = today + timedelta(days=days_ahead)

        try:
            # Aktive Vertraege mit bevorstehenden Fristen
            result = await self.db.execute(
                select(Contract).where(
                    and_(
                        Contract.company_id == company_id,
                        Contract.status.in_([
                            ContractStatus.ACTIVE.value,
                            ContractStatus.DRAFT.value,
                        ]),
                        or_(
                            # Vertragsablauf innerhalb des Zeitraums
                            and_(
                                Contract.expiration_date.isnot(None),
                                Contract.expiration_date <= cutoff_date,
                                Contract.expiration_date >= today,
                            ),
                            # Kuendigungsfrist innerhalb des Zeitraums (berechnet)
                            and_(
                                Contract.expiration_date.isnot(None),
                                Contract.notice_period_days.isnot(None),
                            ),
                        ),
                    )
                )
            )
            contracts = result.scalars().all()

            # Reminder-Tage fuer verschiedene Dringlichkeitsstufen
            reminder_days = [90, 60, 30, 14, 7, 1]

            for contract in contracts:
                try:
                    # 1. Vertragsablauf-Alert (CONT_001)
                    if contract.expiration_date:
                        days_until_expiry = (contract.expiration_date - today).days

                        if days_until_expiry in reminder_days and 0 <= days_until_expiry <= days_ahead:
                            alert = await self._create_contract_expiry_alert(
                                company_id=company_id,
                                contract=contract,
                                days_remaining=days_until_expiry,
                            )
                            if alert:
                                created_alerts.append(alert)

                    # 2. Kuendigungsfrist-Alert (CONT_002)
                    if contract.expiration_date and contract.notice_period_days:
                        notice_deadline = contract.expiration_date - timedelta(
                            days=contract.notice_period_days
                        )
                        days_until_notice = (notice_deadline - today).days

                        if days_until_notice in reminder_days and 0 <= days_until_notice <= days_ahead:
                            alert = await self._create_contract_notice_alert(
                                company_id=company_id,
                                contract=contract,
                                notice_deadline=notice_deadline,
                                days_remaining=days_until_notice,
                            )
                            if alert:
                                created_alerts.append(alert)

                    # 3. Auto-Renewal-Alert (CONT_003)
                    if contract.auto_renewal and contract.expiration_date:
                        days_until_renewal = (contract.expiration_date - today).days

                        # Warnung 30 Tage vor automatischer Verlaengerung
                        if days_until_renewal == 30:
                            alert = await self._create_auto_renewal_alert(
                                company_id=company_id,
                                contract=contract,
                            )
                            if alert:
                                created_alerts.append(alert)

                except Exception as contract_e:
                    logger.warning(
                        "contract_alert_creation_failed",
                        contract_id=str(contract.id),
                        **safe_error_log(contract_e),
                    )

        except Exception as e:
            logger.error(
                "contract_alerts_check_failed",
                company_id=str(company_id),
                **safe_error_log(e),
            )

        logger.info(
            "contract_alerts_checked",
            company_id=str(company_id),
            alerts_created=len(created_alerts),
        )

        return created_alerts

    async def _create_contract_expiry_alert(
        self,
        company_id: UUID,
        contract: Contract,
        days_remaining: int,
    ) -> Optional[Alert]:
        """Erstellt Alert fuer Vertragsablauf."""
        recurrence_key = f"cont_expiry_{contract.id}_{days_remaining}d"

        # Severity basierend auf verbleibenden Tagen
        if days_remaining <= 7:
            severity = AlertSeverity.CRITICAL
        elif days_remaining <= 30:
            severity = AlertSeverity.HIGH
        elif days_remaining <= 60:
            severity = AlertSeverity.MEDIUM
        else:
            severity = AlertSeverity.LOW

        template = EXTENDED_ALERT_TEMPLATES[ExtendedAlertCodes.CONTRACT_EXPIRING]
        template_data = {
            "days": days_remaining,
            "contract_title": contract.title[:50] if contract.title else "Unbenannter Vertrag",
            "contract_number": contract.contract_number or "N/A",
            "end_date": contract.expiration_date.strftime("%d.%m.%Y") if contract.expiration_date else "N/A",
        }

        return await self.alert_center.create_alert(
            company_id=company_id,
            alert_code=ExtendedAlertCodes.CONTRACT_EXPIRING,
            category=AlertCategory.DEADLINE,
            severity=severity,
            title=template["title"].format(**template_data),
            message=template["message"].format(**template_data),
            source_type="contract_management",
            source_id=str(contract.id),
            document_id=contract.document_id,
            metadata={
                "contract_id": str(contract.id),
                "days_remaining": days_remaining,
                "expiration_date": contract.expiration_date.isoformat() if contract.expiration_date else None,
                "auto_renewal": contract.auto_renewal,
            },
            available_actions=["acknowledge", "renew_contract", "terminate_contract", "dismiss"],
            recurrence_key=recurrence_key,
        )

    async def _create_contract_notice_alert(
        self,
        company_id: UUID,
        contract: Contract,
        notice_deadline: date,
        days_remaining: int,
    ) -> Optional[Alert]:
        """Erstellt Alert fuer Kuendigungsfrist."""
        recurrence_key = f"cont_notice_{contract.id}_{days_remaining}d"

        # Severity basierend auf verbleibenden Tagen
        if days_remaining <= 7:
            severity = AlertSeverity.CRITICAL
        elif days_remaining <= 14:
            severity = AlertSeverity.HIGH
        else:
            severity = AlertSeverity.MEDIUM

        template = EXTENDED_ALERT_TEMPLATES[ExtendedAlertCodes.CONTRACT_NOTICE_DEADLINE]
        template_data = {
            "days": days_remaining,
            "contract_title": contract.title[:50] if contract.title else "Unbenannter Vertrag",
            "contract_number": contract.contract_number or "N/A",
            "notice_date": notice_deadline.strftime("%d.%m.%Y"),
        }

        return await self.alert_center.create_alert(
            company_id=company_id,
            alert_code=ExtendedAlertCodes.CONTRACT_NOTICE_DEADLINE,
            category=AlertCategory.DEADLINE,
            severity=severity,
            title=template["title"].format(**template_data),
            message=template["message"].format(**template_data),
            source_type="contract_management",
            source_id=str(contract.id),
            document_id=contract.document_id,
            metadata={
                "contract_id": str(contract.id),
                "days_remaining": days_remaining,
                "notice_deadline": notice_deadline.isoformat(),
                "expiration_date": contract.expiration_date.isoformat() if contract.expiration_date else None,
                "notice_period_days": contract.notice_period_days,
            },
            available_actions=["acknowledge", "send_termination", "dismiss"],
            recurrence_key=recurrence_key,
        )

    async def _create_auto_renewal_alert(
        self,
        company_id: UUID,
        contract: Contract,
    ) -> Optional[Alert]:
        """Erstellt Alert fuer bevorstehende automatische Verlaengerung."""
        recurrence_key = f"cont_renewal_{contract.id}"

        template = EXTENDED_ALERT_TEMPLATES[ExtendedAlertCodes.CONTRACT_AUTO_RENEWAL_WARNING]
        template_data = {
            "contract_title": contract.title[:50] if contract.title else "Unbenannter Vertrag",
            "renewal_date": contract.expiration_date.strftime("%d.%m.%Y") if contract.expiration_date else "N/A",
            "renewal_months": contract.renewal_period_months or 12,
        }

        return await self.alert_center.create_alert(
            company_id=company_id,
            alert_code=ExtendedAlertCodes.CONTRACT_AUTO_RENEWAL_WARNING,
            category=AlertCategory.DEADLINE,
            severity=AlertSeverity.HIGH,
            title=template["title"].format(**template_data),
            message=template["message"].format(**template_data),
            source_type="contract_management",
            source_id=str(contract.id),
            document_id=contract.document_id,
            metadata={
                "contract_id": str(contract.id),
                "renewal_date": contract.expiration_date.isoformat() if contract.expiration_date else None,
                "renewal_months": contract.renewal_period_months,
            },
            available_actions=["acknowledge", "terminate_contract", "dismiss"],
            recurrence_key=recurrence_key,
        )

    # =========================================================================
    # Compliance Alerts
    # =========================================================================

    async def check_compliance_alerts(
        self,
        company_id: UUID,
        days_ahead: int = 30,
    ) -> List[Alert]:
        """
        Prueft auf Compliance-bezogene Alert-Bedingungen.

        Alerts fuer:
        - GDPR-Loeschfristen (COMP_006)
        - Aufbewahrungsfristen (COMP_007)

        Args:
            company_id: Mandanten-ID
            days_ahead: Vorausschau in Tagen

        Returns:
            Liste erstellter Alerts
        """
        created_alerts: List[Alert] = []
        today = date.today()
        cutoff_date = today + timedelta(days=days_ahead)

        try:
            # GDPR-Loeschfristen pruefen
            gdpr_alerts = await self._check_gdpr_deletion_due(company_id, today, cutoff_date)
            created_alerts.extend(gdpr_alerts)

            # Aufbewahrungsfristen pruefen
            retention_alerts = await self._check_retention_expiry(company_id, today, cutoff_date)
            created_alerts.extend(retention_alerts)

        except Exception as e:
            logger.error(
                "compliance_alerts_check_failed",
                company_id=str(company_id),
                **safe_error_log(e),
            )

        logger.info(
            "compliance_alerts_checked",
            company_id=str(company_id),
            alerts_created=len(created_alerts),
        )

        return created_alerts

    async def _check_gdpr_deletion_due(
        self,
        company_id: UUID,
        today: date,
        cutoff_date: date,
    ) -> List[Alert]:
        """Prueft auf GDPR-Loeschfristen."""
        alerts: List[Alert] = []

        # Dokumente mit GDPR-Loeschfrist finden
        # Annahme: Document hat ein Feld 'gdpr_deletion_date' oder 'retention_until'
        result = await self.db.execute(
            select(func.count(Document.id), func.min(Document.retention_until))
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                    Document.retention_until.isnot(None),
                    Document.retention_until <= cutoff_date,
                    Document.retention_until >= today,
                    Document.metadata.op("->")("gdpr_relevant").astext == "true",
                )
            )
        )
        row = result.one_or_none()

        if row and row[0] > 0:
            document_count = row[0]
            expiry_date = row[1]

            recurrence_key = f"gdpr_deletion_{company_id}_{expiry_date.isoformat() if expiry_date else today.isoformat()}"

            template = EXTENDED_ALERT_TEMPLATES[ExtendedAlertCodes.GDPR_DELETION_DUE]
            template_data = {
                "document_count": document_count,
            }

            alert = await self.alert_center.create_alert(
                company_id=company_id,
                alert_code=ExtendedAlertCodes.GDPR_DELETION_DUE,
                category=AlertCategory.COMPLIANCE,
                severity=AlertSeverity.HIGH,
                title=template["title"].format(**template_data),
                message=template["message"].format(**template_data),
                source_type="gdpr_compliance",
                metadata={
                    "document_count": document_count,
                    "earliest_expiry": expiry_date.isoformat() if expiry_date else None,
                },
                available_actions=["acknowledge", "delete_documents", "extend_retention", "dismiss"],
                recurrence_key=recurrence_key,
            )
            alerts.append(alert)

        return alerts

    async def _check_retention_expiry(
        self,
        company_id: UUID,
        today: date,
        cutoff_date: date,
    ) -> List[Alert]:
        """Prueft auf ablaufende Aufbewahrungsfristen."""
        alerts: List[Alert] = []

        # Dokumente mit ablaufender Aufbewahrungsfrist (nicht GDPR-relevant)
        result = await self.db.execute(
            select(func.count(Document.id), func.min(Document.retention_until))
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                    Document.retention_until.isnot(None),
                    Document.retention_until <= cutoff_date,
                    Document.retention_until >= today,
                    or_(
                        Document.metadata.op("->")("gdpr_relevant").is_(None),
                        Document.metadata.op("->")("gdpr_relevant").astext != "true",
                    ),
                )
            )
        )
        row = result.one_or_none()

        if row and row[0] > 0:
            document_count = row[0]
            expiry_date = row[1]

            recurrence_key = f"retention_expiry_{company_id}_{expiry_date.isoformat() if expiry_date else today.isoformat()}"

            template = EXTENDED_ALERT_TEMPLATES[ExtendedAlertCodes.RETENTION_EXPIRY]
            template_data = {
                "document_count": document_count,
                "expiry_date": expiry_date.strftime("%d.%m.%Y") if expiry_date else "N/A",
            }

            alert = await self.alert_center.create_alert(
                company_id=company_id,
                alert_code=ExtendedAlertCodes.RETENTION_EXPIRY,
                category=AlertCategory.COMPLIANCE,
                severity=AlertSeverity.MEDIUM,
                title=template["title"].format(**template_data),
                message=template["message"].format(**template_data),
                source_type="retention_management",
                metadata={
                    "document_count": document_count,
                    "earliest_expiry": expiry_date.isoformat() if expiry_date else None,
                },
                available_actions=["acknowledge", "archive_documents", "delete_documents", "dismiss"],
                recurrence_key=recurrence_key,
            )
            alerts.append(alert)

        return alerts

    # =========================================================================
    # Supplier Alerts
    # =========================================================================

    async def create_supplier_insolvency_alert(
        self,
        company_id: UUID,
        entity_id: UUID,
        source: str,
        confidence: float,
        open_orders_count: int = 0,
        open_invoices_amount: Decimal = Decimal("0"),
    ) -> Optional[Alert]:
        """
        Erstellt Alert fuer moegliche Lieferanten-Insolvenz.

        Wird typischerweise von externen Diensten oder manuell getriggert.

        Args:
            company_id: Mandanten-ID
            entity_id: Lieferanten-ID
            source: Quelle der Information (z.B. "creditreform", "manual")
            confidence: Konfidenz der Information (0-1)
            open_orders_count: Anzahl offener Bestellungen
            open_invoices_amount: Summe offener Rechnungen

        Returns:
            Erstellter Alert oder None
        """
        recurrence_key = f"supplier_insolvency_{entity_id}"

        # Severity basierend auf Exposure
        if open_invoices_amount > Decimal("50000"):
            severity = AlertSeverity.CRITICAL
        elif open_invoices_amount > Decimal("10000"):
            severity = AlertSeverity.HIGH
        else:
            severity = AlertSeverity.MEDIUM

        template = EXTENDED_ALERT_TEMPLATES[ExtendedAlertCodes.SUPPLIER_INSOLVENCY]

        try:
            alert = await self.alert_center.create_alert(
                company_id=company_id,
                alert_code=ExtendedAlertCodes.SUPPLIER_INSOLVENCY,
                category=AlertCategory.RISK,
                severity=severity,
                title=template["title"],
                message=template["message"],
                source_type="supplier_monitoring",
                source_id=source,
                entity_id=entity_id,
                metadata={
                    # SECURITY: Keine Entity-Namen hier
                    "source": source,
                    "confidence": confidence,
                    "open_orders_count": open_orders_count,
                    "open_invoices_amount": float(open_invoices_amount),
                },
                available_actions=["acknowledge", "contact_supplier", "stop_orders", "dismiss"],
                recurrence_key=recurrence_key,
            )

            logger.info(
                "supplier_insolvency_alert_created",
                alert_id=str(alert.id),
                entity_id=str(entity_id),
                severity=severity.value,
            )

            return alert

        except Exception as e:
            logger.error(
                "supplier_insolvency_alert_failed",
                entity_id=str(entity_id),
                **safe_error_log(e),
            )
            return None

    async def create_supplier_ownership_change_alert(
        self,
        company_id: UUID,
        entity_id: UUID,
        source: str,
        change_details: Optional[Dict[str, Any]] = None,
    ) -> Optional[Alert]:
        """
        Erstellt Alert fuer Lieferanten-Eigentuemerwechsel.

        Args:
            company_id: Mandanten-ID
            entity_id: Lieferanten-ID
            source: Quelle der Information
            change_details: Details zum Wechsel (optional)

        Returns:
            Erstellter Alert oder None
        """
        recurrence_key = f"supplier_ownership_{entity_id}"

        template = EXTENDED_ALERT_TEMPLATES[ExtendedAlertCodes.SUPPLIER_OWNERSHIP_CHANGE]

        try:
            alert = await self.alert_center.create_alert(
                company_id=company_id,
                alert_code=ExtendedAlertCodes.SUPPLIER_OWNERSHIP_CHANGE,
                category=AlertCategory.RISK,
                severity=AlertSeverity.MEDIUM,
                title=template["title"],
                message=template["message"],
                source_type="supplier_monitoring",
                source_id=source,
                entity_id=entity_id,
                metadata={
                    "source": source,
                    "change_details": change_details or {},
                },
                available_actions=["acknowledge", "review_contracts", "contact_supplier", "dismiss"],
                recurrence_key=recurrence_key,
            )

            logger.info(
                "supplier_ownership_change_alert_created",
                alert_id=str(alert.id),
                entity_id=str(entity_id),
            )

            return alert

        except Exception as e:
            logger.error(
                "supplier_ownership_change_alert_failed",
                entity_id=str(entity_id),
                **safe_error_log(e),
            )
            return None

    # =========================================================================
    # Comprehensive Check
    # =========================================================================

    async def run_all_checks(
        self,
        company_id: UUID,
        days_ahead: int = 30,
    ) -> Dict[str, Any]:
        """
        Fuehrt alle Alert-Checks aus.

        Args:
            company_id: Mandanten-ID
            days_ahead: Vorausschau in Tagen

        Returns:
            Zusammenfassung aller erstellten Alerts
        """
        logger.info(
            "extended_alerts_check_started",
            company_id=str(company_id),
            days_ahead=days_ahead,
        )

        results = {
            "company_id": str(company_id),
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "days_ahead": days_ahead,
            "cashflow_alerts": 0,
            "contract_alerts": 0,
            "compliance_alerts": 0,
            "total_alerts": 0,
            "errors": [],
        }

        # Cashflow-Alerts
        try:
            cashflow_alerts = await self.check_cashflow_alerts(company_id, days_ahead)
            results["cashflow_alerts"] = len(cashflow_alerts)
        except Exception as e:
            results["errors"].append({
                "type": "cashflow",
                "error": str(e),
            })

        # Contract-Alerts
        try:
            contract_alerts = await self.check_contract_alerts(company_id, days_ahead)
            results["contract_alerts"] = len(contract_alerts)
        except Exception as e:
            results["errors"].append({
                "type": "contract",
                "error": str(e),
            })

        # Compliance-Alerts
        try:
            compliance_alerts = await self.check_compliance_alerts(company_id, days_ahead)
            results["compliance_alerts"] = len(compliance_alerts)
        except Exception as e:
            results["errors"].append({
                "type": "compliance",
                "error": str(e),
            })

        results["total_alerts"] = (
            results["cashflow_alerts"] +
            results["contract_alerts"] +
            results["compliance_alerts"]
        )

        logger.info(
            "extended_alerts_check_completed",
            company_id=str(company_id),
            total_alerts=results["total_alerts"],
            errors=len(results["errors"]),
        )

        return results


# =============================================================================
# Factory Function
# =============================================================================


def get_extended_alerts_service(db: AsyncSession) -> ExtendedAlertsService:
    """Factory-Funktion fuer ExtendedAlertsService."""
    return ExtendedAlertsService(db)
