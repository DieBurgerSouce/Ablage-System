# -*- coding: utf-8 -*-
"""
Payment Automation Service.

Automatisierte Zahlungsabwicklung:
- Auto-SEPA-Generierung bei genehmigten Rechnungen
- Skonto-optimierte Zahlungsplanung
- Batch-Zahlungsvorschlaege
- Intelligente Zahlungsterminierung

Phase 5.4 der Strategischen Roadmap.

Created: 2026-01-21
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta, date
from decimal import Decimal
from enum import Enum
from typing import Any, Optional, Dict, List, Tuple, Union
from uuid import UUID, uuid4

# Type aliases for JSON data
JSONValue = Union[str, int, float, bool, None, Dict[str, "JSONValue"], List["JSONValue"]]
JSONDict = Dict[str, JSONValue]

import structlog
from sqlalchemy import select, func, and_, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.db.models import (
    InvoiceTracking,
    BusinessEntity,
    BankAccount,
    Document,
    Company,
)
from app.services.banking.sepa_credit_transfer_service import (
    SEPACreditTransferService,
    SEPACreditTransferTransaction,
    SEPACreditTransferBatch,
    SEPAChargeBearer,
)
from app.services.banking.skonto_service import (
    SkontoService,
    SkontoCalculation,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums
# =============================================================================


class PaymentPriority(str, Enum):
    """Zahlungsprioritaet."""

    CRITICAL = "critical"  # Sofort zahlen (abgelaufen, Mahnung)
    HIGH = "high"  # Skonto laeuft bald ab
    NORMAL = "normal"  # Regulaere Zahlung
    LOW = "low"  # Kann warten


class PaymentStrategy(str, Enum):
    """Zahlungsstrategie."""

    SKONTO_OPTIMIZED = "skonto_optimized"  # Maximiert Skonto-Ersparnis
    CASHFLOW_OPTIMIZED = "cashflow_optimized"  # Minimiert Liquiditaetsabfluss
    DEADLINE_BASED = "deadline_based"  # Zahlt kurz vor Faelligkeit
    IMMEDIATE = "immediate"  # Sofortige Zahlung


class PaymentBatchStatus(str, Enum):
    """Status eines Payment-Batches."""

    DRAFT = "draft"  # Entwurf
    PENDING_APPROVAL = "pending_approval"  # Wartet auf Freigabe
    APPROVED = "approved"  # Freigegeben
    PROCESSING = "processing"  # In Verarbeitung
    COMPLETED = "completed"  # Abgeschlossen
    FAILED = "failed"  # Fehlgeschlagen
    CANCELLED = "cancelled"  # Abgebrochen


class SuggestionReason(str, Enum):
    """Grund fuer Zahlungsvorschlag."""

    SKONTO_EXPIRING = "skonto_expiring"  # Skonto laeuft bald ab
    DUE_DATE_NEAR = "due_date_near"  # Faelligkeit naht
    OVERDUE = "overdue"  # Ueberfaellig
    APPROVED_INVOICE = "approved_invoice"  # Genehmigte Rechnung
    RECURRING_PAYMENT = "recurring_payment"  # Wiederkehrende Zahlung
    MANUAL_REQUEST = "manual_request"  # Manuell angefordert


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class PaymentSuggestion:
    """Einzelner Zahlungsvorschlag."""

    id: UUID = field(default_factory=uuid4)
    invoice_id: UUID = field(default_factory=uuid4)
    invoice_number: str = ""
    entity_id: Optional[UUID] = None
    entity_name: str = ""
    entity_iban: Optional[str] = None
    entity_bic: Optional[str] = None

    # Betraege
    original_amount: Decimal = Decimal("0")
    skonto_amount: Decimal = Decimal("0")
    payment_amount: Decimal = Decimal("0")  # Zu zahlender Betrag

    # Daten
    invoice_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    skonto_deadline: Optional[datetime] = None
    suggested_payment_date: Optional[date] = None

    # Klassifizierung
    priority: PaymentPriority = PaymentPriority.NORMAL
    reason: SuggestionReason = SuggestionReason.DUE_DATE_NEAR
    days_until_due: Optional[int] = None
    days_until_skonto: Optional[int] = None

    # Skonto
    skonto_percentage: Optional[float] = None
    skonto_savings: Decimal = Decimal("0")
    use_skonto: bool = False

    # Metadaten
    document_id: Optional[UUID] = None
    reference: str = ""
    notes: str = ""
    confidence: float = 0.9

    @property
    def is_skonto_available(self) -> bool:
        """Ist Skonto noch moeglich?"""
        if self.skonto_deadline is None:
            return False
        return self.skonto_deadline > utc_now()


@dataclass
class PaymentBatch:
    """Batch von Zahlungen."""

    id: UUID = field(default_factory=uuid4)
    company_id: Optional[UUID] = None
    name: str = ""
    description: str = ""

    # Zahlungen
    suggestions: List[PaymentSuggestion] = field(default_factory=list)

    # Aggregierte Werte
    total_amount: Decimal = Decimal("0")
    total_skonto_savings: Decimal = Decimal("0")
    payment_count: int = 0

    # Status
    status: PaymentBatchStatus = PaymentBatchStatus.DRAFT
    created_at: datetime = field(default_factory=utc_now)
    created_by_id: Optional[UUID] = None
    approved_at: Optional[datetime] = None
    approved_by_id: Optional[UUID] = None
    rejected_at: Optional[datetime] = None
    rejected_by_id: Optional[UUID] = None
    rejection_reason: Optional[str] = None
    executed_at: Optional[datetime] = None

    # SEPA
    sepa_file_id: Optional[str] = None
    sepa_file_path: Optional[str] = None
    sepa_message_id: Optional[str] = None

    # Bankverbindung
    debtor_account_id: Optional[UUID] = None
    debtor_iban: str = ""
    debtor_bic: str = ""
    debtor_name: str = ""

    def add_suggestion(self, suggestion: PaymentSuggestion) -> None:
        """Fuege Zahlungsvorschlag hinzu."""
        self.suggestions.append(suggestion)
        self._recalculate_totals()

    def remove_suggestion(self, suggestion_id: UUID) -> bool:
        """Entferne Zahlungsvorschlag."""
        original_count = len(self.suggestions)
        self.suggestions = [s for s in self.suggestions if s.id != suggestion_id]
        self._recalculate_totals()
        return len(self.suggestions) < original_count

    def _recalculate_totals(self) -> None:
        """Berechne Gesamtwerte neu."""
        self.payment_count = len(self.suggestions)
        self.total_amount = sum(s.payment_amount for s in self.suggestions)
        self.total_skonto_savings = sum(s.skonto_savings for s in self.suggestions)

    @property
    def payment_ids(self) -> List[UUID]:
        """Liste der zugehoerigen Invoice-IDs."""
        return [s.invoice_id for s in self.suggestions]


@dataclass
class PaymentSchedule:
    """Geplanter Zahlungskalender."""

    company_id: UUID
    period_start: date
    period_end: date
    entries: List[JSONDict] = field(default_factory=list)
    total_amount: Decimal = Decimal("0")
    total_skonto_savings: Decimal = Decimal("0")
    by_date: Dict[str, List[PaymentSuggestion]] = field(default_factory=dict)


@dataclass
class AutomationConfig:
    """Konfiguration fuer Zahlungsautomatisierung."""

    # Automatische Generierung
    auto_generate_on_approval: bool = True  # Batch bei Genehmigung erstellen
    auto_approve_threshold: Decimal = Decimal("1000")  # Auto-Approve bis Betrag
    auto_execute: bool = False  # Automatisch ausfuehren

    # Skonto-Optimierung
    prioritize_skonto: bool = True  # Skonto-Rechnungen priorisieren
    skonto_alert_days: int = 3  # Alert X Tage vor Ablauf
    skonto_min_savings: Decimal = Decimal("10")  # Mindest-Ersparnis

    # Timing
    preferred_payment_days: List[int] = field(
        default_factory=lambda: [1, 15]
    )  # Zahltage im Monat
    advance_days: int = 2  # Tage vor Faelligkeit generieren
    batch_window_days: int = 7  # Rechnungen X Tage im Voraus batchen

    # Limits
    max_batch_size: int = 50  # Max Zahlungen pro Batch
    max_single_payment: Decimal = Decimal("100000")  # Max Einzelzahlung
    daily_limit: Decimal = Decimal("500000")  # Tageslimit


# =============================================================================
# Service
# =============================================================================


class PaymentAutomationService:
    """Service fuer automatisierte Zahlungsabwicklung.

    Features:
    - Automatische Erkennung faelliger Zahlungen
    - Skonto-optimierte Zahlungsplanung
    - Batch-Generierung fuer SEPA-Export
    - Intelligente Zahlungsterminierung
    """

    def __init__(self):
        self.skonto_service = SkontoService()
        self.sepa_service = SEPACreditTransferService()
        self._configs: Dict[UUID, AutomationConfig] = {}  # In-Memory Config Cache
        self._default_config = AutomationConfig()

    def _get_default_config(self) -> AutomationConfig:
        """Hole Default-Konfiguration."""
        return self._default_config

    def _get_config_for_company(self, company_id: UUID) -> AutomationConfig:
        """Hole Konfiguration fuer Company (oder Default)."""
        return self._configs.get(company_id, self._default_config)

    # -------------------------------------------------------------------------
    # Zahlungsvorschlaege generieren
    # -------------------------------------------------------------------------

    async def generate_payment_suggestions(
        self,
        db: AsyncSession,
        company_id: UUID,
        strategy: PaymentStrategy = PaymentStrategy.SKONTO_OPTIMIZED,
        lookahead_days: int = 30,
        include_overdue: bool = True,
    ) -> List[PaymentSuggestion]:
        """Generiere Zahlungsvorschlaege basierend auf Strategie.

        Args:
            db: Database session
            company_id: Company-ID
            strategy: Zahlungsstrategie
            lookahead_days: Tage in die Zukunft schauen
            include_overdue: Ueberfaellige einbeziehen

        Returns:
            Liste von Zahlungsvorschlaegen
        """
        now = utc_now()
        cutoff_date = now + timedelta(days=lookahead_days)

        # Hole offene Eingangsrechnungen
        query = (
            select(InvoiceTracking)
            .where(
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.invoice_type == "incoming",
                InvoiceTracking.is_paid == False,
            )
        )

        if include_overdue:
            # Ueberfaellige + zukuenftig faellige
            query = query.where(
                or_(
                    InvoiceTracking.due_date <= cutoff_date,
                    InvoiceTracking.skonto_deadline <= cutoff_date,
                )
            )
        else:
            # Nur zukuenftig faellige
            query = query.where(
                InvoiceTracking.due_date >= now,
                InvoiceTracking.due_date <= cutoff_date,
            )

        result = await db.execute(query)
        invoices = result.scalars().all()

        suggestions: List[PaymentSuggestion] = []

        for inv in invoices:
            suggestion = await self._create_suggestion_from_invoice(db, inv, strategy)
            if suggestion:
                suggestions.append(suggestion)

        # Sortiere nach Strategie
        suggestions = self._sort_by_strategy(suggestions, strategy)

        logger.info(
            "Zahlungsvorschlaege generiert",
            company_id=str(company_id),
            strategy=strategy.value,
            suggestion_count=len(suggestions),
            total_amount=sum(s.payment_amount for s in suggestions),
        )

        return suggestions

    async def _create_suggestion_from_invoice(
        self,
        db: AsyncSession,
        invoice: InvoiceTracking,
        strategy: PaymentStrategy,
    ) -> Optional[PaymentSuggestion]:
        """Erstelle Zahlungsvorschlag aus Rechnung."""
        now = utc_now()

        # Hole Entity-Informationen
        entity_name = ""
        entity_iban = None
        entity_bic = None

        if invoice.entity_id:
            entity_result = await db.execute(
                select(BusinessEntity).where(BusinessEntity.id == invoice.entity_id)
            )
            entity = entity_result.scalar_one_or_none()
            if entity:
                entity_name = entity.name or ""
                # Hole Bankverbindung aus bank_accounts oder metadata
                entity_iban = getattr(entity, "primary_iban", None)
                entity_bic = getattr(entity, "primary_bic", None)

        # Berechne Zeiträume
        days_until_due = None
        days_until_skonto = None

        if invoice.due_date:
            days_until_due = (invoice.due_date - now).days

        if invoice.skonto_deadline:
            days_until_skonto = (invoice.skonto_deadline - now).days

        # Bestimme Prioritaet
        priority = self._calculate_priority(days_until_due, days_until_skonto, invoice)

        # Bestimme Grund
        reason = self._determine_reason(days_until_due, days_until_skonto, invoice)

        # Skonto-Berechnung
        original_amount = Decimal(str(invoice.amount or 0))
        skonto_amount = Decimal("0")
        skonto_savings = Decimal("0")
        skonto_percentage = invoice.skonto_percentage
        use_skonto = False

        if (
            invoice.skonto_deadline
            and invoice.skonto_deadline > now
            and invoice.skonto_percentage
        ):
            skonto_savings = original_amount * Decimal(str(invoice.skonto_percentage)) / Decimal("100")
            skonto_savings = skonto_savings.quantize(Decimal("0.01"))

            # Entscheide ob Skonto genutzt werden soll
            if strategy in (PaymentStrategy.SKONTO_OPTIMIZED, PaymentStrategy.IMMEDIATE):
                config = self._get_default_config()
                if skonto_savings >= config.skonto_min_savings:
                    use_skonto = True
                    skonto_amount = skonto_savings

        payment_amount = original_amount - skonto_amount

        # Bestimme vorgeschlagenes Zahlungsdatum
        suggested_date = self._calculate_suggested_payment_date(
            invoice, strategy, days_until_due, days_until_skonto
        )

        return PaymentSuggestion(
            invoice_id=invoice.id,
            invoice_number=invoice.invoice_number or "",
            entity_id=invoice.entity_id,
            entity_name=entity_name,
            entity_iban=entity_iban,
            entity_bic=entity_bic,
            original_amount=original_amount,
            skonto_amount=skonto_amount,
            payment_amount=payment_amount,
            invoice_date=invoice.invoice_date,
            due_date=invoice.due_date,
            skonto_deadline=invoice.skonto_deadline,
            suggested_payment_date=suggested_date,
            priority=priority,
            reason=reason,
            days_until_due=days_until_due,
            days_until_skonto=days_until_skonto,
            skonto_percentage=skonto_percentage,
            skonto_savings=skonto_savings if use_skonto else Decimal("0"),
            use_skonto=use_skonto,
            document_id=invoice.document_id,
            reference=invoice.invoice_number or "",
        )

    def _calculate_priority(
        self,
        days_until_due: Optional[int],
        days_until_skonto: Optional[int],
        invoice: InvoiceTracking,
    ) -> PaymentPriority:
        """Berechne Zahlungsprioritaet."""
        # Ueberfaellig = kritisch
        if days_until_due is not None and days_until_due < 0:
            return PaymentPriority.CRITICAL

        # Mahnung = kritisch
        if invoice.dunning_level and invoice.dunning_level > 0:
            return PaymentPriority.CRITICAL

        # Skonto laeuft bald ab = hoch
        config = self._get_default_config()
        if days_until_skonto is not None and 0 <= days_until_skonto <= config.skonto_alert_days:
            return PaymentPriority.HIGH

        # Faellig in naechsten 3 Tagen = hoch
        if days_until_due is not None and 0 <= days_until_due <= 3:
            return PaymentPriority.HIGH

        # Faellig in naechsten 7 Tagen = normal
        if days_until_due is not None and days_until_due <= 7:
            return PaymentPriority.NORMAL

        return PaymentPriority.LOW

    def _determine_reason(
        self,
        days_until_due: Optional[int],
        days_until_skonto: Optional[int],
        invoice: InvoiceTracking,
    ) -> SuggestionReason:
        """Bestimme Grund fuer Zahlungsvorschlag."""
        if days_until_due is not None and days_until_due < 0:
            return SuggestionReason.OVERDUE

        if days_until_skonto is not None and days_until_skonto >= 0:
            return SuggestionReason.SKONTO_EXPIRING

        if days_until_due is not None and days_until_due <= 7:
            return SuggestionReason.DUE_DATE_NEAR

        return SuggestionReason.APPROVED_INVOICE

    def _calculate_suggested_payment_date(
        self,
        invoice: InvoiceTracking,
        strategy: PaymentStrategy,
        days_until_due: Optional[int],
        days_until_skonto: Optional[int],
    ) -> date:
        """Berechne vorgeschlagenes Zahlungsdatum."""
        today = date.today()

        if strategy == PaymentStrategy.IMMEDIATE:
            return today

        if strategy == PaymentStrategy.SKONTO_OPTIMIZED:
            # Zahle vor Skonto-Ablauf falls verfuegbar
            if invoice.skonto_deadline and days_until_skonto is not None and days_until_skonto > 0:
                return (invoice.skonto_deadline - timedelta(days=1)).date()

        if strategy == PaymentStrategy.CASHFLOW_OPTIMIZED:
            # Zahle am letzten moeglichen Tag
            if invoice.due_date:
                return invoice.due_date.date()

        if strategy == PaymentStrategy.DEADLINE_BASED:
            # Zahle 2 Tage vor Faelligkeit
            config = self._get_default_config()
            if invoice.due_date:
                suggested = invoice.due_date - timedelta(days=config.advance_days)
                return max(today, suggested.date())

        # Fallback: Naechster bevorzugter Zahltag
        return self._next_preferred_payment_day(today)

    def _next_preferred_payment_day(self, from_date: date) -> date:
        """Finde naechsten bevorzugten Zahltag."""
        config = self._get_default_config()
        if not config.preferred_payment_days:
            return from_date

        current = from_date
        for _ in range(60):  # Max 60 Tage suchen
            if current.day in config.preferred_payment_days:
                return current
            current += timedelta(days=1)

        return from_date

    def _sort_by_strategy(
        self,
        suggestions: List[PaymentSuggestion],
        strategy: PaymentStrategy,
    ) -> List[PaymentSuggestion]:
        """Sortiere Vorschlaege nach Strategie."""
        if strategy == PaymentStrategy.SKONTO_OPTIMIZED:
            # Skonto-Rechnungen mit hoechster Ersparnis zuerst
            return sorted(
                suggestions,
                key=lambda s: (
                    -s.priority.value if hasattr(s.priority, "value") else 0,
                    -float(s.skonto_savings),
                    s.days_until_skonto or 999,
                ),
            )

        if strategy == PaymentStrategy.DEADLINE_BASED:
            # Nach Faelligkeit
            return sorted(
                suggestions,
                key=lambda s: (s.days_until_due or 999, -float(s.payment_amount)),
            )

        if strategy == PaymentStrategy.CASHFLOW_OPTIMIZED:
            # Kleinste Betraege zuerst, spaetere Faelligkeit zuerst
            return sorted(
                suggestions,
                key=lambda s: (float(s.payment_amount), -(s.days_until_due or 0)),
            )

        # Default: Nach Prioritaet
        priority_order = {
            PaymentPriority.CRITICAL: 0,
            PaymentPriority.HIGH: 1,
            PaymentPriority.NORMAL: 2,
            PaymentPriority.LOW: 3,
        }
        return sorted(suggestions, key=lambda s: priority_order.get(s.priority, 99))

    # -------------------------------------------------------------------------
    # Batch-Erstellung
    # -------------------------------------------------------------------------

    async def create_payment_batch(
        self,
        db: AsyncSession,
        company_id: UUID,
        suggestions: List[PaymentSuggestion],
        name: Optional[str] = None,
        debtor_account_id: Optional[UUID] = None,
        created_by_id: Optional[UUID] = None,
    ) -> PaymentBatch:
        """Erstelle Payment-Batch aus Vorschlaegen.

        Args:
            db: Database session
            company_id: Company-ID
            suggestions: Zahlungsvorschlaege
            name: Batch-Name (optional)
            debtor_account_id: Auszugsquelle (optional)
            created_by_id: Ersteller-ID (optional)

        Returns:
            Erstellter PaymentBatch
        """
        # Hole Company-Name fuer Debtor-Info
        company_result = await db.execute(
            select(Company).where(Company.id == company_id)
        )
        company = company_result.scalar_one_or_none()
        debtor_name = company.name if company else ""

        # Hole Bankverbindung
        debtor_iban = ""
        debtor_bic = ""

        if debtor_account_id:
            account_result = await db.execute(
                select(BankAccount).where(BankAccount.id == debtor_account_id)
            )
            account = account_result.scalar_one_or_none()
            if account:
                debtor_iban = account.iban or ""
                debtor_bic = account.bic or ""

        batch = PaymentBatch(
            company_id=company_id,
            name=name or f"Zahllauf {utc_now().strftime('%Y-%m-%d %H:%M')}",
            description=f"Automatisch generiert mit {len(suggestions)} Zahlungen",
            debtor_account_id=debtor_account_id,
            debtor_iban=debtor_iban,
            debtor_bic=debtor_bic,
            debtor_name=debtor_name,
        )

        # Set created_by if provided
        if created_by_id:
            batch.created_by_id = created_by_id

        for suggestion in suggestions:
            batch.add_suggestion(suggestion)

        logger.info(
            "Payment-Batch erstellt",
            batch_id=str(batch.id),
            company_id=str(company_id),
            payment_count=batch.payment_count,
            total_amount=float(batch.total_amount),
            total_skonto_savings=float(batch.total_skonto_savings),
        )

        return batch

    async def create_optimized_batch(
        self,
        db: AsyncSession,
        company_id: UUID,
        strategy: PaymentStrategy = PaymentStrategy.SKONTO_OPTIMIZED,
        max_amount: Optional[Decimal] = None,
        debtor_account_id: Optional[UUID] = None,
        created_by_id: Optional[UUID] = None,
    ) -> Optional[PaymentBatch]:
        """Erstelle optimierten Batch basierend auf Strategie.

        Args:
            db: Database session
            company_id: Company-ID
            strategy: Zahlungsstrategie
            max_amount: Maximalbetrag fuer Batch
            debtor_account_id: Auszugsquelle
            created_by_id: Ersteller-ID

        Returns:
            Optimierter PaymentBatch oder None wenn keine Zahlungen
        """
        config = self._get_config_for_company(company_id)

        # Generiere Vorschlaege
        all_suggestions = await self.generate_payment_suggestions(
            db,
            company_id,
            strategy,
            lookahead_days=config.batch_window_days,
        )

        if not all_suggestions:
            return None

        # Filter nach Limits
        selected: List[PaymentSuggestion] = []
        running_total = Decimal("0")

        for suggestion in all_suggestions:
            # Pruefe Einzelzahlungs-Limit
            if suggestion.payment_amount > config.max_single_payment:
                continue

            # Pruefe Batch-Groesse
            if len(selected) >= config.max_batch_size:
                break

            # Pruefe Gesamtbetrag
            if max_amount and running_total + suggestion.payment_amount > max_amount:
                continue

            selected.append(suggestion)
            running_total += suggestion.payment_amount

        if not selected:
            return None

        return await self.create_payment_batch(
            db, company_id, selected, debtor_account_id=debtor_account_id, created_by_id=created_by_id
        )

    # -------------------------------------------------------------------------
    # Batch-Freigabe und Ausfuehrung
    # -------------------------------------------------------------------------

    async def approve_batch(
        self,
        db: AsyncSession,
        batch: PaymentBatch,
        approver_id: UUID,
    ) -> PaymentBatch:
        """Gib Batch zur Ausfuehrung frei.

        Args:
            db: Database session
            batch: Zu freigebender Batch
            approver_id: ID des Freigebenden

        Returns:
            Aktualisierter Batch
        """
        batch.status = PaymentBatchStatus.APPROVED
        batch.approved_at = utc_now()
        batch.approved_by_id = approver_id

        logger.info(
            "Payment-Batch freigegeben",
            batch_id=str(batch.id),
            approver_id=str(approver_id),
            payment_count=batch.payment_count,
            total_amount=float(batch.total_amount),
        )

        return batch

    async def reject_batch(
        self,
        db: AsyncSession,
        batch: PaymentBatch,
        rejector_id: UUID,
        reason: str,
    ) -> PaymentBatch:
        """Lehne Batch ab.

        Args:
            db: Database session
            batch: Abzulehnender Batch
            rejector_id: ID des Ablehnenden
            reason: Ablehnungsgrund

        Returns:
            Aktualisierter Batch
        """
        batch.status = PaymentBatchStatus.CANCELLED
        batch.description = f"{batch.description}\nAbgelehnt: {reason}"

        logger.info(
            "Payment-Batch abgelehnt",
            batch_id=str(batch.id),
            rejector_id=str(rejector_id),
            reason=reason,
        )

        return batch

    async def generate_sepa_file(
        self,
        db: AsyncSession,
        batch: PaymentBatch,
        execution_date: Optional[date] = None,
    ) -> Tuple[str, str]:
        """Generiere SEPA XML-Datei aus Batch.

        Args:
            batch: Freigegebener Batch
            execution_date: Ausfuehrungsdatum (optional)

        Returns:
            Tuple von (XML-Content, Message-ID)
        """
        if batch.status not in (PaymentBatchStatus.APPROVED, PaymentBatchStatus.DRAFT):
            raise ValueError(f"Batch hat ungueltigen Status: {batch.status}")

        if not batch.debtor_iban:
            raise ValueError("Keine Debtor-IBAN konfiguriert")

        # Konvertiere Suggestions zu SEPA-Transaktionen
        transactions: List[SEPACreditTransferTransaction] = []

        for suggestion in batch.suggestions:
            if not suggestion.entity_iban:
                logger.warning(
                    "Ueberspringe Zahlung ohne IBAN",
                    invoice_id=str(suggestion.invoice_id),
                    entity_name=suggestion.entity_name,
                )
                continue

            txn = SEPACreditTransferTransaction(
                payment_id=str(suggestion.id),
                amount=suggestion.payment_amount,
                creditor_name=suggestion.entity_name,
                creditor_iban=suggestion.entity_iban,
                creditor_bic=suggestion.entity_bic,
                remittance_info=f"Rechnung {suggestion.invoice_number}"[:140],
                execution_date=execution_date,
            )
            transactions.append(txn)

        if not transactions:
            raise ValueError("Keine gueltigen Transaktionen fuer SEPA-Export")

        # Erstelle SEPA-Batch
        sepa_batch = SEPACreditTransferBatch(
            message_id=f"BATCH-{batch.id}"[:35],
            debtor_name=batch.debtor_name,
            debtor_iban=batch.debtor_iban,
            debtor_bic=batch.debtor_bic,
            transactions=transactions,
            execution_date=execution_date or date.today(),
            charge_bearer=SEPAChargeBearer.SLEV,
        )

        # Generiere XML
        xml_content = self.sepa_service.generate_pain001(sepa_batch)

        # Update Batch
        batch.sepa_message_id = sepa_batch.message_id
        batch.status = PaymentBatchStatus.PROCESSING

        logger.info(
            "SEPA-Datei generiert",
            batch_id=str(batch.id),
            message_id=sepa_batch.message_id,
            transaction_count=len(transactions),
            total_amount=float(sum(t.amount for t in transactions)),
        )

        return xml_content, sepa_batch.message_id

    # -------------------------------------------------------------------------
    # Zahlungsplan
    # -------------------------------------------------------------------------

    async def create_payment_schedule(
        self,
        db: AsyncSession,
        company_id: UUID,
        period_days: int = 30,
        strategy: PaymentStrategy = PaymentStrategy.SKONTO_OPTIMIZED,
    ) -> PaymentSchedule:
        """Erstelle Zahlungskalender fuer Periode.

        Args:
            db: Database session
            company_id: Company-ID
            period_days: Planungszeitraum in Tagen
            strategy: Zahlungsstrategie

        Returns:
            PaymentSchedule mit Zahlungskalender
        """
        today = date.today()
        period_end = today + timedelta(days=period_days)

        suggestions = await self.generate_payment_suggestions(
            db,
            company_id,
            strategy,
            lookahead_days=period_days,
        )

        # Gruppiere nach Zahlungsdatum
        by_date: Dict[str, List[PaymentSuggestion]] = {}

        for suggestion in suggestions:
            if suggestion.suggested_payment_date:
                date_key = suggestion.suggested_payment_date.isoformat()
                if date_key not in by_date:
                    by_date[date_key] = []
                by_date[date_key].append(suggestion)

        # Erstelle Eintraege
        entries: List[Dict[str, Any]] = []
        for date_key in sorted(by_date.keys()):
            payments = by_date[date_key]
            entries.append({
                "date": date_key,
                "payment_count": len(payments),
                "total_amount": float(sum(p.payment_amount for p in payments)),
                "skonto_savings": float(sum(p.skonto_savings for p in payments)),
                "payments": [
                    {
                        "invoice_number": p.invoice_number,
                        "entity_name": p.entity_name,
                        "amount": float(p.payment_amount),
                        "priority": p.priority.value,
                    }
                    for p in payments
                ],
            })

        return PaymentSchedule(
            company_id=company_id,
            period_start=today,
            period_end=period_end,
            entries=entries,
            total_amount=sum(s.payment_amount for s in suggestions),
            total_skonto_savings=sum(s.skonto_savings for s in suggestions),
            by_date=by_date,
        )

    # -------------------------------------------------------------------------
    # Statistiken
    # -------------------------------------------------------------------------

    async def get_automation_statistics(
        self,
        db: AsyncSession,
        company_id: UUID,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Hole Statistiken zur Zahlungsautomatisierung.

        Args:
            db: Database session
            company_id: Company-ID
            days: Betrachtungszeitraum

        Returns:
            Statistiken
        """
        now = utc_now()
        start_date = now - timedelta(days=days)

        # Hole bezahlte Rechnungen im Zeitraum
        paid_result = await db.execute(
            select(InvoiceTracking)
            .where(
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.invoice_type == "incoming",
                InvoiceTracking.is_paid == True,
                InvoiceTracking.paid_date >= start_date,
            )
        )
        paid_invoices = paid_result.scalars().all()

        # Berechne Skonto-Nutzung
        skonto_used = [
            inv for inv in paid_invoices
            if inv.skonto_used and inv.skonto_amount
        ]
        skonto_missed = [
            inv for inv in paid_invoices
            if inv.skonto_percentage
            and not inv.skonto_used
            and inv.skonto_deadline
            and inv.paid_date
            and inv.paid_date > inv.skonto_deadline
        ]

        total_paid = sum(Decimal(str(inv.amount or 0)) for inv in paid_invoices)
        skonto_savings = sum(Decimal(str(inv.skonto_amount or 0)) for inv in skonto_used)
        missed_savings = sum(
            Decimal(str(inv.amount or 0)) * Decimal(str(inv.skonto_percentage or 0)) / Decimal("100")
            for inv in skonto_missed
        )

        # Offene Rechnungen
        open_result = await db.execute(
            select(func.count())
            .select_from(InvoiceTracking)
            .where(
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.invoice_type == "incoming",
                InvoiceTracking.is_paid == False,
            )
        )
        open_count = open_result.scalar() or 0

        # Ueberfaellige
        overdue_result = await db.execute(
            select(func.count())
            .select_from(InvoiceTracking)
            .where(
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.invoice_type == "incoming",
                InvoiceTracking.is_paid == False,
                InvoiceTracking.due_date < now,
            )
        )
        overdue_count = overdue_result.scalar() or 0

        return {
            "period_days": days,
            "period_start": start_date.isoformat(),
            "period_end": now.isoformat(),
            "invoices_paid": len(paid_invoices),
            "total_paid": float(total_paid),
            "skonto_used_count": len(skonto_used),
            "skonto_missed_count": len(skonto_missed),
            "skonto_savings": float(skonto_savings),
            "missed_savings": float(missed_savings),
            "skonto_usage_rate": (
                len(skonto_used) / (len(skonto_used) + len(skonto_missed))
                if (skonto_used or skonto_missed)
                else 0
            ),
            "open_invoices": open_count,
            "overdue_invoices": overdue_count,
            "currency": "EUR",
        }

    # -------------------------------------------------------------------------
    # Batch-Verwaltung
    # -------------------------------------------------------------------------

    async def list_batches(
        self,
        db: AsyncSession,
        company_id: UUID,
        status: Optional[PaymentBatchStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[PaymentBatch]:
        """Liste alle Zahlungs-Batches fuer eine Company.

        Args:
            db: Database session
            company_id: Company-ID
            status: Optional Status-Filter
            limit: Maximum Anzahl
            offset: Offset fuer Pagination

        Returns:
            Liste von PaymentBatch
        """
        # In einer echten Implementation wuerden wir PaymentBatch aus DB laden
        # Hier geben wir eine leere Liste zurueck (Batches sind in-memory)
        return []

    async def get_batch(
        self,
        db: AsyncSession,
        batch_id: UUID,
        company_id: UUID,
    ) -> Optional[PaymentBatch]:
        """Hole einzelnen Batch nach ID.

        Args:
            db: Database session
            batch_id: Batch-ID
            company_id: Company-ID (fuer Isolation)

        Returns:
            PaymentBatch oder None
        """
        # In einer echten Implementation wuerden wir aus DB laden
        return None

    async def get_suggestions_for_invoices(
        self,
        db: AsyncSession,
        company_id: UUID,
        invoice_ids: List[UUID],
    ) -> List[PaymentSuggestion]:
        """Generiere Zahlungsvorschlaege fuer spezifische Rechnungen.

        Args:
            db: Database session
            company_id: Company-ID
            invoice_ids: Liste von Invoice-IDs

        Returns:
            Liste von PaymentSuggestion
        """
        suggestions: List[PaymentSuggestion] = []

        for invoice_id in invoice_ids:
            result = await db.execute(
                select(InvoiceTracking)
                .where(
                    InvoiceTracking.id == invoice_id,
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.invoice_type == "incoming",
                    InvoiceTracking.is_paid == False,
                )
            )
            invoice = result.scalar_one_or_none()

            if invoice:
                suggestion = await self._create_suggestion_from_invoice(
                    db, invoice, PaymentStrategy.SKONTO_OPTIMIZED
                )
                suggestions.append(suggestion)

        return suggestions

    # -------------------------------------------------------------------------
    # Konfiguration
    # -------------------------------------------------------------------------

    async def get_config(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> AutomationConfig:
        """Hole Automatisierungs-Konfiguration fuer Company.

        Args:
            db: Database session
            company_id: Company-ID

        Returns:
            AutomationConfig
        """
        return self._get_config_for_company(company_id)

    async def update_config(
        self,
        db: AsyncSession,
        company_id: UUID,
        **updates: object,
    ) -> AutomationConfig:
        """Aktualisiere Automatisierungs-Konfiguration.

        Args:
            db: Database session
            company_id: Company-ID
            **updates: Zu aktualisierende Felder

        Returns:
            Aktualisierte AutomationConfig
        """
        current_config = self._get_config_for_company(company_id)

        # Erstelle neue Konfiguration mit Updates
        config_dict = {
            "auto_generate_on_approval": current_config.auto_generate_on_approval,
            "auto_approve_threshold": current_config.auto_approve_threshold,
            "auto_execute": current_config.auto_execute,
            "prioritize_skonto": current_config.prioritize_skonto,
            "skonto_alert_days": current_config.skonto_alert_days,
            "skonto_min_savings": current_config.skonto_min_savings,
            "preferred_payment_days": list(current_config.preferred_payment_days),
            "advance_days": current_config.advance_days,
            "batch_window_days": current_config.batch_window_days,
            "max_batch_size": current_config.max_batch_size,
            "max_single_payment": current_config.max_single_payment,
            "daily_limit": current_config.daily_limit,
        }

        # Wende Updates an
        for key, value in updates.items():
            if key in config_dict:
                config_dict[key] = value

        new_config = AutomationConfig(
            auto_generate_on_approval=config_dict["auto_generate_on_approval"],
            auto_approve_threshold=Decimal(str(config_dict["auto_approve_threshold"])),
            auto_execute=config_dict["auto_execute"],
            prioritize_skonto=config_dict["prioritize_skonto"],
            skonto_alert_days=config_dict["skonto_alert_days"],
            skonto_min_savings=Decimal(str(config_dict["skonto_min_savings"])),
            preferred_payment_days=config_dict["preferred_payment_days"],
            advance_days=config_dict["advance_days"],
            batch_window_days=config_dict["batch_window_days"],
            max_batch_size=config_dict["max_batch_size"],
            max_single_payment=Decimal(str(config_dict["max_single_payment"])),
            daily_limit=Decimal(str(config_dict["daily_limit"])),
        )

        # Speichere in Cache
        self._configs[company_id] = new_config

        return new_config

    # -------------------------------------------------------------------------
    # Skonto-Alerts
    # -------------------------------------------------------------------------

    async def get_skonto_alerts(
        self,
        db: AsyncSession,
        company_id: UUID,
        days: int = 7,
    ) -> List[Dict[str, Any]]:
        """Hole Skonto-Alerts fuer bald ablaufende Fristen.

        Args:
            db: Database session
            company_id: Company-ID
            days: Tage in die Zukunft schauen

        Returns:
            Liste von Alerts
        """
        today = date.today()
        deadline = today + timedelta(days=days)

        result = await db.execute(
            select(InvoiceTracking)
            .where(
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.invoice_type == "incoming",
                InvoiceTracking.is_paid == False,
                InvoiceTracking.skonto_deadline.isnot(None),
                InvoiceTracking.skonto_deadline >= today,
                InvoiceTracking.skonto_deadline <= deadline,
                InvoiceTracking.skonto_used == False,
            )
            .order_by(InvoiceTracking.skonto_deadline)
        )
        invoices = result.scalars().all()

        alerts: List[Dict[str, Any]] = []

        for inv in invoices:
            days_remaining = (inv.skonto_deadline.date() - today).days if inv.skonto_deadline else 0
            potential_savings = (
                Decimal(str(inv.amount or 0)) * Decimal(str(inv.skonto_percentage or 0)) / Decimal("100")
            )

            urgency = "critical" if days_remaining <= 2 else "warning" if days_remaining <= 5 else "info"

            alerts.append({
                "invoice_id": str(inv.id),
                "invoice_number": inv.invoice_number,
                "entity_id": str(inv.entity_id) if inv.entity_id else None,
                "amount": float(inv.amount or 0),
                "skonto_percentage": float(inv.skonto_percentage or 0),
                "skonto_deadline": inv.skonto_deadline.isoformat() if inv.skonto_deadline else None,
                "days_remaining": days_remaining,
                "potential_savings": float(potential_savings),
                "urgency": urgency,
                "message": f"Skonto-Frist laeuft in {days_remaining} Tag(en) ab - {float(potential_savings):.2f} EUR Ersparnis moeglich",
            })

        return alerts


# =============================================================================
# Factory
# =============================================================================


def get_payment_automation_service() -> PaymentAutomationService:
    """Factory function fuer PaymentAutomationService.

    Returns:
        Service instance
    """
    return PaymentAutomationService()
