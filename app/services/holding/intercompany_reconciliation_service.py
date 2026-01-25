# -*- coding: utf-8 -*-
"""
Intercompany Reconciliation Service.

Automatischer Abgleich zwischen Holding-Gesellschaften:
- IC-Salden tracken und abgleichen
- Eliminierungen fuer Konsolidierung vorbereiten
- Differenzen identifizieren und ausgleichen
- Audit-Trail fuer IC-Transaktionen

Created: 2026-01-21
Phase 5.3 der Strategischen Roadmap.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional, Dict, Any, List, Tuple
from uuid import UUID, uuid4

import structlog
from sqlalchemy import select, func, and_, or_, case, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Company,
    Document,
    InvoiceTracking,
    BusinessEntity,
    BankAccount,
    BankTransaction,
    UserCompany,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums
# =============================================================================


class ICTransactionType(str, Enum):
    """Typ der Intercompany-Transaktion."""

    INVOICE = "invoice"  # Interne Rechnung
    LOAN = "loan"  # Darlehen zwischen Firmen
    DIVIDEND = "dividend"  # Gewinnausschuettung
    MANAGEMENT_FEE = "management_fee"  # Management-Gebuehr
    COST_ALLOCATION = "cost_allocation"  # Kostenallokation
    CASH_POOLING = "cash_pooling"  # Cash-Pooling Transfer
    SERVICE = "service"  # Interne Dienstleistung
    OTHER = "other"


class ReconciliationStatus(str, Enum):
    """Status des Abgleichs."""

    MATCHED = "matched"  # Beide Seiten stimmen ueberein
    UNMATCHED = "unmatched"  # Keine Gegenbuchung gefunden
    PARTIAL = "partial"  # Teilweise abgeglichen
    DISPUTED = "disputed"  # Differenz festgestellt
    PENDING = "pending"  # Noch nicht abgeglichen


class DifferenceType(str, Enum):
    """Art der Differenz."""

    AMOUNT = "amount"  # Betragsdifferenz
    DATE = "date"  # Datumsdifferenz
    MISSING_COUNTERPART = "missing_counterpart"  # Fehlende Gegenbuchung
    CURRENCY = "currency"  # Waehrungsdifferenz
    TIMING = "timing"  # Timing-Differenz (Periodenabgrenzung)


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class ICTransaction:
    """Intercompany-Transaktion."""

    id: UUID
    from_company_id: UUID
    from_company_name: str
    to_company_id: UUID
    to_company_name: str
    transaction_type: ICTransactionType
    amount: Decimal
    currency: str
    reference: str
    document_id: Optional[UUID]
    invoice_id: Optional[UUID]
    transaction_date: datetime
    due_date: Optional[datetime]
    description: Optional[str]
    status: ReconciliationStatus = ReconciliationStatus.PENDING
    matched_transaction_id: Optional[UUID] = None


@dataclass
class ICBalance:
    """Intercompany-Saldo zwischen zwei Firmen."""

    company_a_id: UUID
    company_a_name: str
    company_b_id: UUID
    company_b_name: str
    balance_a_to_b: Decimal  # Was A an B schuldet (positiv) oder A von B fordern kann (negativ)
    balance_b_to_a: Decimal  # Was B an A schuldet
    net_balance: Decimal  # Netto-Position (positiv = A schuldet B)
    open_transactions_count: int
    last_reconciled_at: Optional[datetime]
    currency: str = "EUR"


@dataclass
class ReconciliationDifference:
    """Identifizierte Differenz im Abgleich."""

    id: UUID
    difference_type: DifferenceType
    from_company_id: UUID
    to_company_id: UUID
    transaction_id: Optional[UUID]
    counterpart_id: Optional[UUID]
    expected_amount: Decimal
    actual_amount: Decimal
    difference_amount: Decimal
    expected_date: Optional[datetime]
    actual_date: Optional[datetime]
    description: str
    recommendation: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EliminationEntry:
    """Eliminierungsbuchung fuer Konsolidierung."""

    id: UUID
    account_debit: str  # Soll-Konto
    account_credit: str  # Haben-Konto
    amount: Decimal
    description: str
    from_company_id: UUID
    to_company_id: UUID
    transaction_ids: List[UUID]
    elimination_type: str  # receivables, payables, revenue, expense
    period: str  # z.B. "2026-01"


@dataclass
class ReconciliationReport:
    """Vollstaendiger Abstimmungsbericht."""

    generated_at: datetime
    period_start: datetime
    period_end: datetime
    companies_involved: List[Dict[str, Any]]
    total_ic_volume: Decimal
    matched_volume: Decimal
    unmatched_volume: Decimal
    balances: List[ICBalance]
    differences: List[ReconciliationDifference]
    eliminations: List[EliminationEntry]
    statistics: Dict[str, Any]


# =============================================================================
# Service
# =============================================================================


class IntercompanyReconciliationService:
    """Service fuer Intercompany-Abstimmung und Konsolidierung.

    Features:
    - Automatische Erkennung von IC-Transaktionen
    - Saldo-Tracking zwischen Firmen
    - Differenz-Identifikation und Aufloesung
    - Eliminierungsbuchungen generieren
    - Audit-Trail und Reports
    """

    # Toleranz fuer Betragsabweichungen (0.5% oder 1 EUR)
    AMOUNT_TOLERANCE_PERCENT = Decimal("0.005")
    AMOUNT_TOLERANCE_ABSOLUTE = Decimal("1.00")

    # Toleranz fuer Datumsabweichungen (Tage)
    DATE_TOLERANCE_DAYS = 5

    def __init__(self, db: AsyncSession):
        self.db = db

    # -------------------------------------------------------------------------
    # IC-Transaktionen identifizieren
    # -------------------------------------------------------------------------

    async def identify_ic_transactions(
        self,
        company_ids: List[UUID],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[ICTransaction]:
        """Identifiziere Intercompany-Transaktionen.

        Eine Transaktion ist IC wenn:
        - Rechnungsaussteller und -empfaenger beide zur Holding gehoeren
        - Oder explizit als IC markiert

        Args:
            company_ids: IDs der Holding-Firmen
            start_date: Startdatum (optional)
            end_date: Enddatum (optional)

        Returns:
            Liste der IC-Transaktionen
        """
        if not company_ids:
            return []

        if end_date is None:
            end_date = datetime.now(timezone.utc)
        if start_date is None:
            start_date = end_date - timedelta(days=365)

        # Hole Company-Namen fuer Mapping
        company_names = await self._get_company_names(company_ids)

        # Hole alle Entities die zu unseren Firmen gehoeren
        ic_entity_map = await self._build_ic_entity_map(company_ids)

        ic_transactions: List[ICTransaction] = []

        # Finde IC-Rechnungen
        ic_invoices = await self._find_ic_invoices(
            company_ids, ic_entity_map, start_date, end_date, company_names
        )
        ic_transactions.extend(ic_invoices)

        # Finde IC-Bank-Transaktionen (Cash Pooling, etc.)
        ic_bank_txns = await self._find_ic_bank_transactions(
            company_ids, start_date, end_date, company_names
        )
        ic_transactions.extend(ic_bank_txns)

        logger.info(
            "IC-Transaktionen identifiziert",
            total_count=len(ic_transactions),
            invoice_count=len(ic_invoices),
            bank_txn_count=len(ic_bank_txns),
        )

        return ic_transactions

    async def _get_company_names(self, company_ids: List[UUID]) -> Dict[UUID, str]:
        """Hole Company-Namen fuer IDs."""
        result = await self.db.execute(
            select(Company.id, Company.name).where(Company.id.in_(company_ids))
        )
        return {row[0]: row[1] for row in result.all()}

    async def _build_ic_entity_map(
        self, company_ids: List[UUID]
    ) -> Dict[UUID, List[UUID]]:
        """Baue Mapping von Entity zu Companies.

        Returns:
            Dict[entity_id, list_of_company_ids_entity_belongs_to]
        """
        result = await self.db.execute(
            select(BusinessEntity.id, BusinessEntity.company_presence)
            .where(BusinessEntity.company_presence.isnot(None))
        )

        entity_map: Dict[UUID, List[UUID]] = {}
        company_id_strs = {str(c) for c in company_ids}

        for entity_id, presence in result.all():
            if presence:
                matching_companies = [
                    UUID(c) for c in presence if c in company_id_strs
                ]
                if matching_companies:
                    entity_map[entity_id] = matching_companies

        return entity_map

    async def _find_ic_invoices(
        self,
        company_ids: List[UUID],
        ic_entity_map: Dict[UUID, List[UUID]],
        start_date: datetime,
        end_date: datetime,
        company_names: Dict[UUID, str],
    ) -> List[ICTransaction]:
        """Finde IC-Rechnungen."""
        ic_transactions: List[ICTransaction] = []

        if not ic_entity_map:
            return ic_transactions

        # Hole Rechnungen mit IC-Entities
        result = await self.db.execute(
            select(InvoiceTracking)
            .where(
                InvoiceTracking.company_id.in_(company_ids),
                InvoiceTracking.entity_id.in_(list(ic_entity_map.keys())),
                InvoiceTracking.invoice_date >= start_date,
                InvoiceTracking.invoice_date <= end_date,
            )
        )
        invoices = result.scalars().all()

        for inv in invoices:
            # Bestimme die Gegenpartei-Firma
            entity_companies = ic_entity_map.get(inv.entity_id, [])

            # Filtere die austellende Firma heraus
            counterpart_companies = [c for c in entity_companies if c != inv.company_id]

            if not counterpart_companies:
                continue

            # Nehme erste Gegenpartei (oder koennte komplexer sein)
            to_company_id = counterpart_companies[0]

            # Bestimme Richtung basierend auf invoice_type
            if inv.invoice_type == "outgoing":
                # Wir (company_id) stellen Rechnung an to_company
                from_id = inv.company_id
                to_id = to_company_id
            else:
                # Wir (company_id) erhalten Rechnung von to_company
                from_id = to_company_id
                to_id = inv.company_id

            ic_transactions.append(
                ICTransaction(
                    id=uuid4(),
                    from_company_id=from_id,
                    from_company_name=company_names.get(from_id, "Unbekannt"),
                    to_company_id=to_id,
                    to_company_name=company_names.get(to_id, "Unbekannt"),
                    transaction_type=ICTransactionType.INVOICE,
                    amount=Decimal(str(inv.amount)),
                    currency="EUR",
                    reference=inv.invoice_number or "",
                    document_id=inv.document_id,
                    invoice_id=inv.id,
                    transaction_date=inv.invoice_date or datetime.now(timezone.utc),
                    due_date=inv.due_date,
                    description=f"IC-Rechnung {inv.invoice_number}",
                    status=ReconciliationStatus.PENDING,
                )
            )

        return ic_transactions

    async def _find_ic_bank_transactions(
        self,
        company_ids: List[UUID],
        start_date: datetime,
        end_date: datetime,
        company_names: Dict[UUID, str],
    ) -> List[ICTransaction]:
        """Finde IC-Bank-Transaktionen (z.B. Cash Pooling).

        Identifiziert Transaktionen zwischen Konten verschiedener Firmen
        basierend auf IBAN-Matching.
        """
        ic_transactions: List[ICTransaction] = []

        # Hole alle IBANs unserer Firmen
        iban_result = await self.db.execute(
            select(BankAccount.iban, BankAccount.company_id)
            .where(
                BankAccount.company_id.in_(company_ids),
                BankAccount.iban.isnot(None),
            )
        )
        company_ibans = {row[0]: row[1] for row in iban_result.all()}

        if not company_ibans:
            return ic_transactions

        # Finde Transaktionen die eine unserer IBANs als Gegenkonto haben
        result = await self.db.execute(
            select(BankTransaction)
            .where(
                BankTransaction.company_id.in_(company_ids),
                BankTransaction.counterparty_iban.in_(list(company_ibans.keys())),
                BankTransaction.booking_date >= start_date,
                BankTransaction.booking_date <= end_date,
            )
        )
        transactions = result.scalars().all()

        for txn in transactions:
            counterpart_company = company_ibans.get(txn.counterparty_iban)
            if not counterpart_company or counterpart_company == txn.company_id:
                continue

            # Bestimme Richtung basierend auf Betrag
            if txn.amount > 0:
                # Eingehende Zahlung - von Gegenseite zu uns
                from_id = counterpart_company
                to_id = txn.company_id
            else:
                # Ausgehende Zahlung - von uns zu Gegenseite
                from_id = txn.company_id
                to_id = counterpart_company

            # Bestimme Transaktionstyp
            txn_type = self._classify_bank_transaction(txn.purpose or "")

            ic_transactions.append(
                ICTransaction(
                    id=uuid4(),
                    from_company_id=from_id,
                    from_company_name=company_names.get(from_id, "Unbekannt"),
                    to_company_id=to_id,
                    to_company_name=company_names.get(to_id, "Unbekannt"),
                    transaction_type=txn_type,
                    amount=abs(Decimal(str(txn.amount))),
                    currency="EUR",
                    reference=txn.reference or "",
                    document_id=txn.matched_document_id,
                    invoice_id=None,
                    transaction_date=txn.booking_date,
                    due_date=None,
                    description=txn.purpose,
                    status=ReconciliationStatus.PENDING,
                )
            )

        return ic_transactions

    def _classify_bank_transaction(self, purpose: str) -> ICTransactionType:
        """Klassifiziere Bank-Transaktion nach IC-Typ."""
        purpose_lower = purpose.lower()

        if any(kw in purpose_lower for kw in ["darlehen", "loan", "kredit"]):
            return ICTransactionType.LOAN
        if any(kw in purpose_lower for kw in ["dividende", "gewinn", "ausschuettung"]):
            return ICTransactionType.DIVIDEND
        if any(kw in purpose_lower for kw in ["management", "verwaltung", "gebuehr"]):
            return ICTransactionType.MANAGEMENT_FEE
        if any(kw in purpose_lower for kw in ["umlage", "allokation", "verteilung"]):
            return ICTransactionType.COST_ALLOCATION
        if any(kw in purpose_lower for kw in ["pool", "clearing", "konzern"]):
            return ICTransactionType.CASH_POOLING
        if any(kw in purpose_lower for kw in ["rechnung", "invoice"]):
            return ICTransactionType.INVOICE

        return ICTransactionType.OTHER

    # -------------------------------------------------------------------------
    # Saldo-Berechnung
    # -------------------------------------------------------------------------

    async def calculate_ic_balances(
        self,
        company_ids: List[UUID],
        as_of_date: Optional[datetime] = None,
    ) -> List[ICBalance]:
        """Berechne IC-Salden zwischen allen Firmen-Paaren.

        Args:
            company_ids: Firmen der Holding
            as_of_date: Stichtag (default: heute)

        Returns:
            Liste der IC-Salden fuer jedes Firmenpaar
        """
        if len(company_ids) < 2:
            return []

        if as_of_date is None:
            as_of_date = datetime.now(timezone.utc)

        company_names = await self._get_company_names(company_ids)
        ic_transactions = await self.identify_ic_transactions(
            company_ids,
            start_date=datetime(2000, 1, 1, tzinfo=timezone.utc),
            end_date=as_of_date,
        )

        # Gruppiere nach Firmenpaar
        pair_transactions: Dict[Tuple[UUID, UUID], List[ICTransaction]] = {}

        for txn in ic_transactions:
            # Sortiere IDs um konsistente Paare zu haben
            pair = tuple(sorted([txn.from_company_id, txn.to_company_id]))
            if pair not in pair_transactions:
                pair_transactions[pair] = []
            pair_transactions[pair].append(txn)

        # Berechne Salden pro Paar
        balances: List[ICBalance] = []

        for (company_a, company_b), transactions in pair_transactions.items():
            # A->B Transaktionen (A schuldet B)
            a_to_b = sum(
                txn.amount
                for txn in transactions
                if txn.from_company_id == company_a
            )
            # B->A Transaktionen (B schuldet A)
            b_to_a = sum(
                txn.amount
                for txn in transactions
                if txn.from_company_id == company_b
            )

            balances.append(
                ICBalance(
                    company_a_id=company_a,
                    company_a_name=company_names.get(company_a, "Unbekannt"),
                    company_b_id=company_b,
                    company_b_name=company_names.get(company_b, "Unbekannt"),
                    balance_a_to_b=a_to_b,
                    balance_b_to_a=b_to_a,
                    net_balance=a_to_b - b_to_a,
                    open_transactions_count=len(transactions),
                    last_reconciled_at=None,
                    currency="EUR",
                )
            )

        return balances

    # -------------------------------------------------------------------------
    # Abstimmung (Reconciliation)
    # -------------------------------------------------------------------------

    async def reconcile_transactions(
        self,
        company_ids: List[UUID],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Tuple[List[ICTransaction], List[ReconciliationDifference]]:
        """Gleiche IC-Transaktionen ab.

        Versucht Gegenbuchungen zu finden und Differenzen zu identifizieren.

        Args:
            company_ids: Firmen der Holding
            start_date: Startdatum
            end_date: Enddatum

        Returns:
            Tuple von (abgeglichene Transaktionen, gefundene Differenzen)
        """
        ic_transactions = await self.identify_ic_transactions(
            company_ids, start_date, end_date
        )

        differences: List[ReconciliationDifference] = []
        matched_ids: set = set()

        # Versuche jede Transaktion mit einer Gegenbuchung zu matchen
        for i, txn in enumerate(ic_transactions):
            if txn.id in matched_ids:
                continue

            # Suche Gegenbuchung
            match = self._find_matching_transaction(
                txn,
                [t for j, t in enumerate(ic_transactions) if j > i and t.id not in matched_ids],
            )

            if match:
                # Match gefunden
                txn.status = ReconciliationStatus.MATCHED
                txn.matched_transaction_id = match.id
                match.status = ReconciliationStatus.MATCHED
                match.matched_transaction_id = txn.id
                matched_ids.add(txn.id)
                matched_ids.add(match.id)

                # Pruefe auf Betrags- oder Datums-Differenzen
                amount_diff = abs(txn.amount - match.amount)
                if amount_diff > Decimal("0.01"):
                    differences.append(
                        ReconciliationDifference(
                            id=uuid4(),
                            difference_type=DifferenceType.AMOUNT,
                            from_company_id=txn.from_company_id,
                            to_company_id=txn.to_company_id,
                            transaction_id=txn.id,
                            counterpart_id=match.id,
                            expected_amount=txn.amount,
                            actual_amount=match.amount,
                            difference_amount=amount_diff,
                            expected_date=txn.transaction_date,
                            actual_date=match.transaction_date,
                            description=f"Betragsdifferenz bei {txn.reference}",
                            recommendation="Betraege pruefen und korrigieren",
                        )
                    )
            else:
                # Kein Match gefunden
                txn.status = ReconciliationStatus.UNMATCHED
                differences.append(
                    ReconciliationDifference(
                        id=uuid4(),
                        difference_type=DifferenceType.MISSING_COUNTERPART,
                        from_company_id=txn.from_company_id,
                        to_company_id=txn.to_company_id,
                        transaction_id=txn.id,
                        counterpart_id=None,
                        expected_amount=txn.amount,
                        actual_amount=Decimal("0"),
                        difference_amount=txn.amount,
                        expected_date=txn.transaction_date,
                        actual_date=None,
                        description=f"Fehlende Gegenbuchung fuer {txn.reference}",
                        recommendation="Gegenbuchung in der Gegenseite erfassen",
                    )
                )

        logger.info(
            "IC-Abstimmung abgeschlossen",
            total_transactions=len(ic_transactions),
            matched=len(matched_ids),
            unmatched=len(ic_transactions) - len(matched_ids),
            differences=len(differences),
        )

        return ic_transactions, differences

    def _find_matching_transaction(
        self,
        txn: ICTransaction,
        candidates: List[ICTransaction],
    ) -> Optional[ICTransaction]:
        """Finde passende Gegenbuchung.

        Matching-Kriterien:
        1. Umgekehrte Firmen (from<->to)
        2. Gleicher/aehnlicher Betrag (mit Toleranz)
        3. Aehnliches Datum (mit Toleranz)
        4. Gleiche Referenz (wenn vorhanden)
        """
        for candidate in candidates:
            # Muss umgekehrte Richtung sein
            if not (
                candidate.from_company_id == txn.to_company_id
                and candidate.to_company_id == txn.from_company_id
            ):
                continue

            # Betrags-Pruefung mit Toleranz
            amount_diff = abs(txn.amount - candidate.amount)
            tolerance = max(
                txn.amount * self.AMOUNT_TOLERANCE_PERCENT,
                self.AMOUNT_TOLERANCE_ABSOLUTE,
            )
            if amount_diff > tolerance:
                continue

            # Datums-Pruefung mit Toleranz
            date_diff = abs((txn.transaction_date - candidate.transaction_date).days)
            if date_diff > self.DATE_TOLERANCE_DAYS:
                continue

            # Optional: Referenz-Match
            if txn.reference and candidate.reference:
                if txn.reference.lower() == candidate.reference.lower():
                    return candidate

            # Guter Kandidat auch ohne Referenz-Match
            return candidate

        return None

    # -------------------------------------------------------------------------
    # Eliminierungen generieren
    # -------------------------------------------------------------------------

    async def generate_eliminations(
        self,
        company_ids: List[UUID],
        period: str,
        as_of_date: Optional[datetime] = None,
    ) -> List[EliminationEntry]:
        """Generiere Eliminierungsbuchungen fuer Konsolidierung.

        Erstellt die notwendigen Buchungen um IC-Transaktionen
        fuer den Konzernabschluss zu eliminieren.

        Args:
            company_ids: Firmen der Holding
            period: Periode (z.B. "2026-01")
            as_of_date: Stichtag

        Returns:
            Liste der Eliminierungsbuchungen
        """
        if as_of_date is None:
            as_of_date = datetime.now(timezone.utc)

        # Parse Periode fuer Datumsbereich
        try:
            year, month = map(int, period.split("-"))
            start_date = datetime(year, month, 1, tzinfo=timezone.utc)
            if month == 12:
                end_date = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
            else:
                end_date = datetime(year, month + 1, 1, tzinfo=timezone.utc)
        except (ValueError, IndexError):
            # Fallback: letzter Monat
            end_date = datetime.now(timezone.utc).replace(day=1)
            start_date = (end_date - timedelta(days=1)).replace(day=1)

        ic_transactions = await self.identify_ic_transactions(
            company_ids, start_date, end_date
        )

        eliminations: List[EliminationEntry] = []

        # Gruppiere nach Firmenpaar
        pair_totals: Dict[Tuple[UUID, UUID], Dict[str, Any]] = {}

        for txn in ic_transactions:
            pair = tuple(sorted([txn.from_company_id, txn.to_company_id]))
            if pair not in pair_totals:
                pair_totals[pair] = {
                    "receivables": Decimal("0"),
                    "payables": Decimal("0"),
                    "revenue": Decimal("0"),
                    "expense": Decimal("0"),
                    "transaction_ids": [],
                    "from_company": txn.from_company_id,
                    "to_company": txn.to_company_id,
                }

            data = pair_totals[pair]
            data["transaction_ids"].append(txn.id)

            # Klassifiziere fuer Eliminierung
            if txn.transaction_type == ICTransactionType.INVOICE:
                # Forderung beim Aussteller, Verbindlichkeit beim Empfaenger
                if txn.from_company_id == pair[0]:
                    data["receivables"] += txn.amount
                else:
                    data["payables"] += txn.amount

        # Erstelle Eliminierungsbuchungen
        for (company_a, company_b), data in pair_totals.items():
            # Eliminiere IC-Forderungen gegen IC-Verbindlichkeiten
            if data["receivables"] > 0 or data["payables"] > 0:
                net_amount = data["receivables"] - data["payables"]
                elim_amount = min(data["receivables"], data["payables"])

                if elim_amount > 0:
                    eliminations.append(
                        EliminationEntry(
                            id=uuid4(),
                            account_debit="3000",  # Verbindlichkeiten
                            account_credit="1400",  # Forderungen
                            amount=elim_amount,
                            description=f"IC-Eliminierung Forderungen/Verbindlichkeiten {company_a} <-> {company_b}",
                            from_company_id=company_a,
                            to_company_id=company_b,
                            transaction_ids=data["transaction_ids"],
                            elimination_type="receivables_payables",
                            period=period,
                        )
                    )

        logger.info(
            "Eliminierungen generiert",
            period=period,
            elimination_count=len(eliminations),
            total_eliminated=sum(e.amount for e in eliminations),
        )

        return eliminations

    # -------------------------------------------------------------------------
    # Vollstaendiger Report
    # -------------------------------------------------------------------------

    async def generate_reconciliation_report(
        self,
        company_ids: List[UUID],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        period: Optional[str] = None,
    ) -> ReconciliationReport:
        """Generiere vollstaendigen Abstimmungsbericht.

        Args:
            company_ids: Firmen der Holding
            start_date: Startdatum
            end_date: Enddatum
            period: Periode fuer Eliminierungen (z.B. "2026-01")

        Returns:
            Vollstaendiger ReconciliationReport
        """
        if end_date is None:
            end_date = datetime.now(timezone.utc)
        if start_date is None:
            start_date = end_date - timedelta(days=30)
        if period is None:
            period = end_date.strftime("%Y-%m")

        # Hole Company-Infos
        company_names = await self._get_company_names(company_ids)
        companies_info = [
            {"id": str(cid), "name": name}
            for cid, name in company_names.items()
        ]

        # Fuehre Abstimmung durch
        transactions, differences = await self.reconcile_transactions(
            company_ids, start_date, end_date
        )

        # Berechne Salden
        balances = await self.calculate_ic_balances(company_ids, end_date)

        # Generiere Eliminierungen
        eliminations = await self.generate_eliminations(company_ids, period, end_date)

        # Statistiken
        total_volume = sum(t.amount for t in transactions)
        matched = [t for t in transactions if t.status == ReconciliationStatus.MATCHED]
        matched_volume = sum(t.amount for t in matched)
        unmatched_volume = total_volume - matched_volume

        statistics = {
            "total_transactions": len(transactions),
            "matched_transactions": len(matched),
            "unmatched_transactions": len(transactions) - len(matched),
            "match_rate": len(matched) / len(transactions) if transactions else 0,
            "total_differences": len(differences),
            "differences_by_type": self._count_differences_by_type(differences),
            "elimination_count": len(eliminations),
            "total_eliminated": float(sum(e.amount for e in eliminations)),
        }

        return ReconciliationReport(
            generated_at=datetime.now(timezone.utc),
            period_start=start_date,
            period_end=end_date,
            companies_involved=companies_info,
            total_ic_volume=total_volume,
            matched_volume=matched_volume,
            unmatched_volume=unmatched_volume,
            balances=balances,
            differences=differences,
            eliminations=eliminations,
            statistics=statistics,
        )

    def _count_differences_by_type(
        self, differences: List[ReconciliationDifference]
    ) -> Dict[str, int]:
        """Zaehle Differenzen nach Typ."""
        counts: Dict[str, int] = {}
        for diff in differences:
            diff_type = diff.difference_type.value
            counts[diff_type] = counts.get(diff_type, 0) + 1
        return counts

    # -------------------------------------------------------------------------
    # Hilfsfunktionen fuer UI/API
    # -------------------------------------------------------------------------

    async def get_ic_summary(
        self,
        company_ids: List[UUID],
    ) -> Dict[str, Any]:
        """Hole kompakte IC-Zusammenfassung fuer Dashboard.

        Args:
            company_ids: Firmen der Holding

        Returns:
            Zusammenfassung fuer Dashboard-Anzeige
        """
        if len(company_ids) < 2:
            return {
                "has_ic_relationships": False,
                "message": "Mindestens 2 Firmen erforderlich fuer IC-Analyse",
            }

        # Schnelle Abfrage fuer Uebersicht
        balances = await self.calculate_ic_balances(company_ids)

        total_receivables = sum(b.balance_a_to_b for b in balances)
        total_payables = sum(b.balance_b_to_a for b in balances)
        total_open = sum(b.open_transactions_count for b in balances)

        return {
            "has_ic_relationships": len(balances) > 0,
            "company_pairs": len(balances),
            "total_ic_receivables": float(total_receivables),
            "total_ic_payables": float(total_payables),
            "net_ic_position": float(total_receivables - total_payables),
            "open_transactions": total_open,
            "currency": "EUR",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def to_dict(self, obj: Any) -> Dict[str, Any]:
        """Konvertiere dataclass zu dict fuer JSON-Serialisierung."""
        if isinstance(obj, ICTransaction):
            return {
                "id": str(obj.id),
                "from_company_id": str(obj.from_company_id),
                "from_company_name": obj.from_company_name,
                "to_company_id": str(obj.to_company_id),
                "to_company_name": obj.to_company_name,
                "transaction_type": obj.transaction_type.value,
                "amount": float(obj.amount),
                "currency": obj.currency,
                "reference": obj.reference,
                "document_id": str(obj.document_id) if obj.document_id else None,
                "invoice_id": str(obj.invoice_id) if obj.invoice_id else None,
                "transaction_date": obj.transaction_date.isoformat(),
                "due_date": obj.due_date.isoformat() if obj.due_date else None,
                "description": obj.description,
                "status": obj.status.value,
                "matched_transaction_id": (
                    str(obj.matched_transaction_id)
                    if obj.matched_transaction_id
                    else None
                ),
            }
        if isinstance(obj, ICBalance):
            return {
                "company_a_id": str(obj.company_a_id),
                "company_a_name": obj.company_a_name,
                "company_b_id": str(obj.company_b_id),
                "company_b_name": obj.company_b_name,
                "balance_a_to_b": float(obj.balance_a_to_b),
                "balance_b_to_a": float(obj.balance_b_to_a),
                "net_balance": float(obj.net_balance),
                "open_transactions_count": obj.open_transactions_count,
                "last_reconciled_at": (
                    obj.last_reconciled_at.isoformat()
                    if obj.last_reconciled_at
                    else None
                ),
                "currency": obj.currency,
            }
        if isinstance(obj, ReconciliationDifference):
            return {
                "id": str(obj.id),
                "difference_type": obj.difference_type.value,
                "from_company_id": str(obj.from_company_id),
                "to_company_id": str(obj.to_company_id),
                "transaction_id": str(obj.transaction_id) if obj.transaction_id else None,
                "counterpart_id": str(obj.counterpart_id) if obj.counterpart_id else None,
                "expected_amount": float(obj.expected_amount),
                "actual_amount": float(obj.actual_amount),
                "difference_amount": float(obj.difference_amount),
                "expected_date": obj.expected_date.isoformat() if obj.expected_date else None,
                "actual_date": obj.actual_date.isoformat() if obj.actual_date else None,
                "description": obj.description,
                "recommendation": obj.recommendation,
                "created_at": obj.created_at.isoformat(),
            }
        if isinstance(obj, EliminationEntry):
            return {
                "id": str(obj.id),
                "account_debit": obj.account_debit,
                "account_credit": obj.account_credit,
                "amount": float(obj.amount),
                "description": obj.description,
                "from_company_id": str(obj.from_company_id),
                "to_company_id": str(obj.to_company_id),
                "transaction_ids": [str(tid) for tid in obj.transaction_ids],
                "elimination_type": obj.elimination_type,
                "period": obj.period,
            }
        if isinstance(obj, ReconciliationReport):
            return {
                "generated_at": obj.generated_at.isoformat(),
                "period_start": obj.period_start.isoformat(),
                "period_end": obj.period_end.isoformat(),
                "companies_involved": obj.companies_involved,
                "total_ic_volume": float(obj.total_ic_volume),
                "matched_volume": float(obj.matched_volume),
                "unmatched_volume": float(obj.unmatched_volume),
                "balances": [self.to_dict(b) for b in obj.balances],
                "differences": [self.to_dict(d) for d in obj.differences],
                "eliminations": [self.to_dict(e) for e in obj.eliminations],
                "statistics": obj.statistics,
            }

        return {}


# =============================================================================
# Factory
# =============================================================================


def get_intercompany_reconciliation_service(
    db: AsyncSession,
) -> IntercompanyReconciliationService:
    """Factory function fuer IntercompanyReconciliationService.

    Args:
        db: Async database session

    Returns:
        Configured service instance
    """
    return IntercompanyReconciliationService(db)
