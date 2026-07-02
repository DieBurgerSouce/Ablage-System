# -*- coding: utf-8 -*-
"""Payment Service.

Verwaltet SEPA-Zahlungsaufträge:
- Einzelüberweisungen (PAIN.001)
- Lastschriften (PAIN.008)
- Sammelzahlungen (Batches)
- Zahlungsstatus-Tracking

TAN-Workflow:
1. Payment erstellen (draft)
2. Payment freigeben (approved)
3. An Bank senden → TAN-Challenge
4. TAN eingeben → Bestätigung
5. Status: confirmed/rejected

Hinweis: Verwendet 'beneficiary_*' Feldnamen (nicht 'creditor_*')
um Konsistenz mit existierenden Schemas zu wahren.
"""

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from decimal import Decimal

from app.core.datetime_utils import utc_now
from typing import Optional, List, Dict, Any, Tuple, Union, TYPE_CHECKING
from uuid import UUID, uuid4
import structlog
import re

from sqlalchemy import select, func, and_, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    PaymentStatus,
    PaymentType,
    PaymentOrderCreate,
    PaymentOrderResponse,
)

if TYPE_CHECKING:
    from app.db.models import PaymentOrder

logger = structlog.get_logger(__name__)


# IBAN-Validierung
IBAN_PATTERN = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$")

# BIC-Validierung
BIC_PATTERN = re.compile(r"^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$")


@dataclass
class PaymentValidationResult:
    """Ergebnis der Zahlungsvalidierung."""
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class SEPAPaymentData:
    """SEPA-Zahlungsdaten für XML-Generierung."""
    payment_id: str
    creditor_name: str
    creditor_iban: str
    creditor_bic: Optional[str]
    amount: Decimal
    currency: str
    reference: str
    execution_date: date
    end_to_end_id: Optional[str]
    payment_type: PaymentType


class PaymentService:
    """Service für SEPA-Zahlungsaufträge."""

    # Maximale Betraege (konfigurierbar)
    MAX_SINGLE_PAYMENT = Decimal("50000.00")
    MAX_BATCH_TOTAL = Decimal("100000.00")

    async def create_payment(
        self,
        db: AsyncSession,
        company_id: UUID,
        bank_account_id: UUID,
        data: PaymentOrderCreate,
        acting_user_id: Optional[UUID] = None,
    ) -> PaymentOrderResponse:
        """Erstelle neuen Zahlungsauftrag.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            bank_account_id: Quellkonto-ID
            data: Zahlungsdaten

        Returns:
            PaymentOrderResponse
        """
        from app.db.models import BankAccount, PaymentOrder

        # Verifiziere Bankkonto gehoert zur Firma (company-scoped, Migration 269)
        account_query = select(BankAccount).where(
            and_(
                BankAccount.id == bank_account_id,
                BankAccount.company_id == company_id,
                BankAccount.deleted_at.is_(None),
            )
        )
        account_result = await db.execute(account_query)
        account = account_result.scalar_one_or_none()

        if not account:
            raise ValueError("Bankkonto nicht gefunden")

        # SECURITY: Validiere linked_document_id Ownership (falls vorhanden)
        if hasattr(data, 'linked_document_id') and data.linked_document_id:
            from app.db.models import Document
            doc_query = select(Document).where(
                and_(
                    Document.id == data.linked_document_id,
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                )
            )
            doc_result = await db.execute(doc_query)
            if not doc_result.scalar_one_or_none():
                logger.warning(
                    "payment_unauthorized_document_link",
                    document_id=str(data.linked_document_id),
                    company_id=str(company_id),
                )
                raise ValueError("Verknüpftes Dokument nicht gefunden oder keine Berechtigung")

        # SECURITY: Validiere linked_transaction_id Ownership (falls vorhanden)
        if hasattr(data, 'linked_transaction_id') and data.linked_transaction_id:
            from app.db.models import BankTransaction, BankAccount as BA
            tx_query = (
                select(BankTransaction)
                .join(BA)
                .where(
                    and_(
                        BankTransaction.id == data.linked_transaction_id,
                        BA.company_id == company_id,
                    )
                )
            )
            tx_result = await db.execute(tx_query)
            if not tx_result.scalar_one_or_none():
                logger.warning(
                    "payment_unauthorized_transaction_link",
                    transaction_id=str(data.linked_transaction_id),
                    company_id=str(company_id),
                )
                raise ValueError("Verknüpfte Transaktion nicht gefunden oder keine Berechtigung")

        # Validiere Zahlungsdaten
        validation = self._validate_payment(data)
        if not validation.valid:
            raise ValueError(f"Validierungsfehler: {', '.join(validation.errors)}")

        # Generiere End-to-End-ID falls nicht vorhanden.
        # FIX: PaymentOrderCreate hat KEIN end_to_end_id-Feld -> data.end_to_end_id
        # warf AttributeError (pre-existing; bisher nie erreicht, weil create_payment
        # vorher am user-scoped Konto-Lookup scheiterte). getattr -> generieren.
        end_to_end_id = getattr(data, "end_to_end_id", None) or self._generate_end_to_end_id()

        # Erstelle Zahlungsauftrag
        payment = PaymentOrder(
            id=uuid4(),
            user_id=acting_user_id,  # nur Audit; Scope ist company_id
            company_id=account.company_id,
            bank_account_id=bank_account_id,
            batch_id=None,
            payment_type=data.payment_type.value if data.payment_type else PaymentType.TRANSFER.value,
            status=PaymentStatus.DRAFT.value,
            beneficiary_name=data.beneficiary_name,
            beneficiary_iban=self._normalize_iban(data.beneficiary_iban),
            beneficiary_bic=data.beneficiary_bic,
            amount=data.amount,
            currency=data.currency or "EUR",
            reference=data.reference,
            end_to_end_id=end_to_end_id,
            execution_date=data.execution_date or date.today(),
            created_at=utc_now(),
        )

        db.add(payment)
        await db.commit()
        await db.refresh(payment)

        logger.info(
            "payment_created",
            payment_id=str(payment.id),
            amount=str(data.amount),
            beneficiary=data.beneficiary_name,
        )

        return self._to_response(payment)

    async def get_payment(
        self,
        db: AsyncSession,
        company_id: UUID,
        payment_id: UUID,
    ) -> Optional[PaymentOrderResponse]:
        """Hole Zahlungsauftrag.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            payment_id: Zahlungs-ID

        Returns:
            PaymentOrderResponse oder None
        """
        from app.db.models import BankAccount, PaymentOrder

        query = (
            select(PaymentOrder)
            .join(BankAccount)
            .where(
                and_(
                    PaymentOrder.id == payment_id,
                    BankAccount.company_id == company_id,
                )
            )
        )

        result = await db.execute(query)
        payment = result.scalar_one_or_none()

        if not payment:
            return None

        return self._to_response(payment)

    async def list_payments(
        self,
        db: AsyncSession,
        company_id: UUID,
        bank_account_id: Optional[UUID] = None,
        status: Optional[PaymentStatus] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> Tuple[List[PaymentOrderResponse], int]:
        """Liste Zahlungsaufträge.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            bank_account_id: Optional Filter auf Bankkonto
            status: Optional Filter auf Status
            offset: Pagination Offset
            limit: Pagination Limit

        Returns:
            Tuple von (Zahlungen, Gesamtanzahl)
        """
        from app.db.models import BankAccount, PaymentOrder

        # Basis-Query
        base_conditions = [
            BankAccount.company_id == company_id,
        ]

        if bank_account_id:
            base_conditions.append(PaymentOrder.bank_account_id == bank_account_id)

        if status:
            base_conditions.append(PaymentOrder.status == status.value)

        # Count Query
        count_query = (
            select(func.count(PaymentOrder.id))
            .select_from(PaymentOrder)
            .join(BankAccount)
            .where(and_(*base_conditions))
        )
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        # Data Query
        query = (
            select(PaymentOrder)
            .join(BankAccount)
            .where(and_(*base_conditions))
            .order_by(PaymentOrder.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        result = await db.execute(query)
        payments = result.scalars().all()

        return [self._to_response(p) for p in payments], total

    async def approve_payment(
        self,
        db: AsyncSession,
        company_id: UUID,
        payment_id: UUID,
    ) -> PaymentOrderResponse:
        """Genehmige Zahlungsauftrag.

        Setzt Status von DRAFT auf APPROVED.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            payment_id: Zahlungs-ID

        Returns:
            PaymentOrderResponse
        """
        from app.db.models import BankAccount, PaymentOrder

        query = (
            select(PaymentOrder)
            .join(BankAccount)
            .where(
                and_(
                    PaymentOrder.id == payment_id,
                    BankAccount.company_id == company_id,
                )
            )
        )

        result = await db.execute(query)
        payment = result.scalar_one_or_none()

        if not payment:
            raise ValueError("Zahlung nicht gefunden")

        if payment.status != PaymentStatus.DRAFT.value:
            raise ValueError(f"Zahlung kann nicht genehmigt werden (Status: {payment.status})")

        payment.status = PaymentStatus.APPROVED.value
        payment.approved_at = utc_now()
        payment.updated_at = utc_now()

        await db.commit()

        logger.info(
            "payment_approved",
            payment_id=str(payment_id),
            company_id=str(company_id),
        )

        return self._to_response(payment)

    async def cancel_payment(
        self,
        db: AsyncSession,
        company_id: UUID,
        payment_id: UUID,
        reason: Optional[str] = None,
    ) -> PaymentOrderResponse:
        """Storniere Zahlungsauftrag.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            payment_id: Zahlungs-ID
            reason: Stornierungsgrund

        Returns:
            PaymentOrderResponse
        """
        from app.db.models import BankAccount, PaymentOrder

        query = (
            select(PaymentOrder)
            .join(BankAccount)
            .where(
                and_(
                    PaymentOrder.id == payment_id,
                    BankAccount.company_id == company_id,
                )
            )
        )

        result = await db.execute(query)
        payment = result.scalar_one_or_none()

        if not payment:
            raise ValueError("Zahlung nicht gefunden")

        # Nur bestimmte Status können storniert werden
        cancellable_states = [
            PaymentStatus.DRAFT.value,
            PaymentStatus.APPROVED.value,
            PaymentStatus.PENDING_TAN.value,
        ]

        if payment.status not in cancellable_states:
            raise ValueError(f"Zahlung kann nicht storniert werden (Status: {payment.status})")

        payment.status = PaymentStatus.CANCELLED.value
        payment.error_message = reason
        payment.updated_at = utc_now()

        await db.commit()

        logger.info(
            "payment_cancelled",
            payment_id=str(payment_id),
            reason=reason,
        )

        return self._to_response(payment)

    async def submit_payment(
        self,
        db: AsyncSession,
        company_id: UUID,
        payment_id: UUID,
    ) -> Dict[str, Any]:
        """Sende Zahlung an Bank (initiiert TAN-Challenge).

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            payment_id: Zahlungs-ID

        Returns:
            Dict mit TAN-Challenge-Daten
        """
        from app.db.models import BankAccount, PaymentOrder

        query = (
            select(PaymentOrder)
            .join(BankAccount)
            .where(
                and_(
                    PaymentOrder.id == payment_id,
                    BankAccount.company_id == company_id,
                )
            )
        )

        result = await db.execute(query)
        payment = result.scalar_one_or_none()

        if not payment:
            raise ValueError("Zahlung nicht gefunden")

        if payment.status != PaymentStatus.APPROVED.value:
            raise ValueError(f"Zahlung muss genehmigt sein (Status: {payment.status})")

        # Update Status auf PENDING_TAN
        payment.status = PaymentStatus.PENDING_TAN.value
        payment.submitted_at = utc_now()
        payment.updated_at = utc_now()

        await db.commit()

        logger.info(
            "payment_submitted",
            payment_id=str(payment_id),
        )

        # Generiere TAN-Challenge (simuliert)
        # In Produktion wuerde hier FinTS/HBCI verwendet
        tan_challenge = {
            "payment_id": str(payment_id),
            "challenge_type": "photoTAN",  # oder pushTAN, chipTAN, etc.
            "challenge_data": None,  # Base64 QR-Code etc.
            "expires_at": (utc_now() + timedelta(minutes=5)).isoformat(),
            "tan_required": True,
        }

        return tan_challenge

    async def confirm_with_tan(
        self,
        db: AsyncSession,
        company_id: UUID,
        payment_id: UUID,
        tan: str,
    ) -> PaymentOrderResponse:
        """Bestätige Zahlung mit TAN.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            payment_id: Zahlungs-ID
            tan: TAN-Eingabe

        Returns:
            PaymentOrderResponse
        """
        from app.db.models import BankAccount, PaymentOrder

        query = (
            select(PaymentOrder)
            .join(BankAccount)
            .where(
                and_(
                    PaymentOrder.id == payment_id,
                    BankAccount.company_id == company_id,
                )
            )
        )

        result = await db.execute(query)
        payment = result.scalar_one_or_none()

        if not payment:
            raise ValueError("Zahlung nicht gefunden")

        if payment.status != PaymentStatus.PENDING_TAN.value:
            raise ValueError(f"Zahlung wartet nicht auf TAN (Status: {payment.status})")

        # TAN-Validierung (in Produktion über Bank-API)
        if not self._validate_tan(tan):
            payment.tan_attempts = (payment.tan_attempts or 0) + 1

            if payment.tan_attempts >= 3:
                payment.status = PaymentStatus.REJECTED.value
                payment.error_message = "Maximale TAN-Versuche überschritten"
                await db.commit()
                raise ValueError("Maximale TAN-Versuche überschritten")

            await db.commit()
            raise ValueError("Ungültige TAN")

        # Erfolgreiche Bestätigung
        payment.status = PaymentStatus.CONFIRMED.value
        payment.confirmed_at = utc_now()
        payment.updated_at = utc_now()
        payment.bank_reference = self._generate_bank_reference()

        await db.commit()

        logger.info(
            "payment_confirmed",
            payment_id=str(payment_id),
            bank_reference=payment.bank_reference,
        )

        return self._to_response(payment)

    async def get_pending_payments(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> List[PaymentOrderResponse]:
        """Hole alle ausstehenden Zahlungen.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID

        Returns:
            Liste von PaymentOrderResponse
        """
        from app.db.models import BankAccount, PaymentOrder

        pending_statuses = [
            PaymentStatus.DRAFT.value,
            PaymentStatus.APPROVED.value,
            PaymentStatus.PENDING_TAN.value,
        ]

        query = (
            select(PaymentOrder)
            .join(BankAccount)
            .where(
                and_(
                    BankAccount.company_id == company_id,
                    PaymentOrder.status.in_(pending_statuses),
                )
            )
            .order_by(PaymentOrder.execution_date.asc())
        )

        result = await db.execute(query)
        payments = result.scalars().all()

        return [self._to_response(p) for p in payments]

    async def get_skonto_opportunities(
        self,
        db: AsyncSession,
        company_id: UUID,
        days_ahead: int = 14,
    ) -> List[Dict[str, Any]]:
        """Finde Skonto-Möglichkeiten.

        Company-scoped (Migration 269): Es werden die Rechnungen der gesamten
        Firma betrachtet, nicht nur die eines einzelnen Besitzers. Damit sieht
        jeder berechtigte Firmennutzer dieselben Skonto-Chancen und die
        Mandanten-Isolation bleibt gewahrt (eine Firma sieht niemals die
        Rechnungen einer anderen).

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID (Mandanten-Scope)
            days_ahead: Tage vorausschauen

        Returns:
            Liste von Skonto-Möglichkeiten
        """
        from app.db.models import Document

        cutoff_date = date.today() + timedelta(days=days_ahead)

        # Suche Rechnungen mit Skonto (mandantenscoped über company_id)
        query = select(Document).where(
            and_(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
                Document.document_type == "invoice",
            )
        )

        result = await db.execute(query)
        documents = result.scalars().all()

        opportunities = []
        for doc in documents:
            if not doc.extracted_data:
                continue

            extracted = doc.extracted_data
            payment_terms = extracted.get("payment_terms", {})
            skonto = payment_terms.get("skonto")

            if not skonto:
                continue

            skonto_date_str = skonto.get("date")
            skonto_percent = skonto.get("percent")

            if not skonto_date_str or not skonto_percent:
                continue

            try:
                skonto_date = datetime.strptime(skonto_date_str[:10], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                continue

            if skonto_date > cutoff_date:
                continue

            if skonto_date < date.today():
                continue  # Skonto abgelaufen

            gross_amount = extracted.get("amounts", {}).get("gross", 0)
            savings = Decimal(str(gross_amount)) * Decimal(str(skonto_percent)) / 100

            opportunities.append({
                "document_id": str(doc.id),
                "invoice_number": extracted.get("invoice_number"),
                "creditor_name": extracted.get("sender", {}).get("name"),
                "gross_amount": float(gross_amount),
                "skonto_percent": skonto_percent,
                "skonto_date": skonto_date.isoformat(),
                "days_remaining": (skonto_date - date.today()).days,
                "potential_savings": float(savings),
                "discounted_amount": float(Decimal(str(gross_amount)) - savings),
            })

        # Sortiere nach Dringlichkeit
        opportunities.sort(key=lambda x: x["days_remaining"])

        return opportunities

    # =========================================================================
    # Batch-Operationen
    # =========================================================================

    async def create_batch(
        self,
        db: AsyncSession,
        company_id: UUID,
        bank_account_id: UUID,
        name: str,
        payments: List[PaymentOrderCreate],
        acting_user_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """Erstelle Sammelzahlung.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            bank_account_id: Quellkonto-ID
            name: Batch-Name
            payments: Liste von Zahlungen

        Returns:
            Batch-Info
        """
        from app.db.models import BankAccount, PaymentBatch, PaymentOrder

        # Verifiziere Bankkonto
        account_query = select(BankAccount).where(
            and_(
                BankAccount.id == bank_account_id,
                BankAccount.company_id == company_id,
                BankAccount.deleted_at.is_(None),
            )
        )
        account_result = await db.execute(account_query)
        account = account_result.scalar_one_or_none()

        if not account:
            raise ValueError("Bankkonto nicht gefunden")

        # Validiere alle Zahlungen
        errors = []
        total_amount = Decimal("0")

        for i, payment_data in enumerate(payments):
            validation = self._validate_payment(payment_data)
            if not validation.valid:
                errors.extend([f"Zahlung {i+1}: {e}" for e in validation.errors])
            total_amount += payment_data.amount

        if errors:
            raise ValueError(f"Validierungsfehler: {'; '.join(errors)}")

        if total_amount > self.MAX_BATCH_TOTAL:
            raise ValueError(
                f"Batch-Gesamtbetrag ({total_amount}) überschreitet Maximum ({self.MAX_BATCH_TOTAL})"
            )

        # Erstelle Batch und Einzelzahlungen atomar via Savepoint
        # (Batch-Header + N Zahlungsaufträge müssen konsistent sein)
        created_payments = []
        try:
            async with db.begin_nested():
                batch = PaymentBatch(
                    id=uuid4(),
                    user_id=acting_user_id,  # nur Audit; Scope ist company_id
                    company_id=account.company_id,
                    bank_account_id=bank_account_id,
                    batch_name=name,
                    batch_type="SEPA_CT",  # SEPA Credit Transfer als Default
                    status=PaymentStatus.DRAFT.value,
                    payment_count=len(payments),
                    total_amount=total_amount,
                    created_at=utc_now(),
                    created_by_id=acting_user_id,
                    updated_by_id=acting_user_id,
                )

                db.add(batch)

                # Erstelle Einzelzahlungen
                for payment_data in payments:
                    payment = PaymentOrder(
                        id=uuid4(),
                        user_id=acting_user_id,  # nur Audit; Scope ist company_id
                        company_id=account.company_id,
                        bank_account_id=bank_account_id,
                        batch_id=batch.id,
                        payment_type=payment_data.payment_type.value if payment_data.payment_type else PaymentType.TRANSFER.value,
                        status=PaymentStatus.DRAFT.value,
                        beneficiary_name=payment_data.beneficiary_name,
                        beneficiary_iban=self._normalize_iban(payment_data.beneficiary_iban),
                        beneficiary_bic=payment_data.beneficiary_bic,
                        amount=payment_data.amount,
                        currency=payment_data.currency or "EUR",
                        reference=payment_data.reference,
                        end_to_end_id=self._generate_end_to_end_id(),
                        execution_date=payment_data.execution_date or date.today(),
                        created_at=utc_now(),
                    )
                    db.add(payment)
                    created_payments.append(payment)
        except Exception as e:
            logger.error(
                "batch_create_savepoint_fehler",
                batch_name=name,
                payment_count=len(payments),
                error_type=type(e).__name__,
            )
            raise

        await db.commit()

        logger.info(
            "batch_created",
            batch_id=str(batch.id),
            payment_count=len(payments),
            total_amount=str(total_amount),
        )

        return {
            "batch_id": str(batch.id),
            "name": name,
            "payment_count": len(payments),
            "total_amount": float(total_amount),
            "status": PaymentStatus.DRAFT.value,
            "payments": [str(p.id) for p in created_payments],
        }

    # =========================================================================
    # Helper-Methoden
    # =========================================================================

    def _validate_payment(self, data: PaymentOrderCreate) -> PaymentValidationResult:
        """Validiere Zahlungsdaten.

        Hinweis: Verwendet beneficiary_* Feldnamen (Schema-konform).
        """
        errors = []
        warnings = []

        # IBAN validieren (beneficiary_iban in Schema)
        iban_value = getattr(data, 'beneficiary_iban', None) or getattr(data, 'creditor_iban', None)
        if not iban_value:
            errors.append("IBAN fehlt")
        else:
            iban = self._normalize_iban(iban_value)
            if not IBAN_PATTERN.match(iban):
                errors.append("Ungültige IBAN")
            elif not self._validate_iban_checksum(iban):
                errors.append("IBAN-Prüfziffer ungültig")

        # BIC validieren (optional)
        bic_value = getattr(data, 'beneficiary_bic', None) or getattr(data, 'creditor_bic', None)
        if bic_value:
            if not BIC_PATTERN.match(bic_value.upper()):
                errors.append("Ungültige BIC")

        # Betrag validieren
        if data.amount <= 0:
            errors.append("Betrag muss positiv sein")
        elif data.amount > self.MAX_SINGLE_PAYMENT:
            warnings.append(f"Betrag überschreitet {self.MAX_SINGLE_PAYMENT} EUR")

        # Empfängername validieren (beneficiary_name in Schema)
        name_value = getattr(data, 'beneficiary_name', None) or getattr(data, 'creditor_name', None)
        if not name_value or len(name_value) < 2:
            errors.append("Empfängername fehlt oder zu kurz")
        elif len(name_value) > 70:
            errors.append("Empfängername zu lang (max. 70 Zeichen)")

        # Verwendungszweck validieren (optional in Schema)
        reference_value = getattr(data, 'reference', None)
        if reference_value and len(reference_value) > 140:
            errors.append("Verwendungszweck zu lang (max. 140 Zeichen)")

        # Ausführungsdatum validieren
        if data.execution_date:
            if data.execution_date < date.today():
                errors.append("Ausführungsdatum liegt in der Vergangenheit")
            elif data.execution_date > date.today() + timedelta(days=365):
                warnings.append("Ausführungsdatum liegt weit in der Zukunft")

        return PaymentValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def _normalize_iban(self, iban: str) -> str:
        """Normalisiere IBAN (entferne Leerzeichen, uppercase)."""
        return iban.replace(" ", "").upper()

    @staticmethod
    def _to_date(value: Optional[Union[date, datetime]]) -> Optional[date]:
        """Konvertiere datetime oder date zu date.

        Defensive Methode die sowohl date als auch datetime akzeptiert.
        """
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        return value  # Bereits ein date

    def _validate_iban_checksum(self, iban: str) -> bool:
        """Validiere IBAN-Prüfziffer (MOD-97)."""
        try:
            # Verschiebe ersten 4 Zeichen ans Ende
            rearranged = iban[4:] + iban[:4]

            # Ersetze Buchstaben durch Zahlen (A=10, B=11, etc.)
            numeric = ""
            for char in rearranged:
                if char.isalpha():
                    numeric += str(ord(char) - 55)
                else:
                    numeric += char

            # MOD 97 Prüfung
            return int(numeric) % 97 == 1
        except (ValueError, TypeError):
            return False

    def _validate_tan(self, tan: str) -> bool:
        """Validiere TAN-Format.

        In Produktion wuerde hier die Bank-API verwendet.
        """
        # Einfache Validierung: 6 Ziffern
        if not tan or len(tan) != 6:
            return False
        return tan.isdigit()

    def _generate_end_to_end_id(self) -> str:
        """Generiere eindeutige End-to-End-ID."""
        timestamp = utc_now().strftime("%Y%m%d%H%M%S")
        unique = str(uuid4())[:8].upper()
        return f"E2E{timestamp}{unique}"

    def _generate_bank_reference(self) -> str:
        """Generiere Bank-Referenznummer."""
        timestamp = utc_now().strftime("%Y%m%d")
        unique = str(uuid4())[:12].upper()
        return f"REF{timestamp}{unique}"

    def _to_response(self, payment: "PaymentOrder") -> PaymentOrderResponse:
        """Konvertiere DB-Model zu Response."""
        return PaymentOrderResponse(
            id=payment.id,
            user_id=payment.user_id,
            bank_account_id=payment.bank_account_id,
            document_id=payment.document_id,
            invoice_number=payment.invoice_number,
            payment_type=PaymentType(payment.payment_type) if payment.payment_type else PaymentType.SINGLE_PAYMENT,
            sepa_type=payment.sepa_type,
            status=PaymentStatus(payment.status),
            beneficiary_name=payment.beneficiary_name,
            beneficiary_iban=payment.beneficiary_iban,
            beneficiary_bic=payment.beneficiary_bic,
            amount=payment.amount,
            currency=payment.currency or "EUR",
            reference=payment.reference,
            execution_date=self._to_date(payment.execution_date),
            tan_required=payment.tan_required or False,
            uses_skonto=payment.uses_skonto or False,
            skonto_amount=payment.skonto_amount,
            original_amount=payment.original_amount,
            skonto_deadline=self._to_date(payment.skonto_deadline),
            approved_at=payment.approved_at,
            submitted_at=payment.submitted_at,
            created_at=payment.created_at,
            updated_at=payment.updated_at,
        )
