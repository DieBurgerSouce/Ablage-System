# -*- coding: utf-8 -*-
"""
Payment Initiation Service for PSD2 PISP and FinTS payments.

Handles:
- SEPA Credit Transfer
- SEPA Direct Debit (future)
- Batch payments
- Payment scheduling
- TAN/SCA handling

SECURITY NOTES:
- All payment data encrypted
- Dual approval for high-value payments
- Audit all payment operations
- Never log payment amounts or beneficiary details
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from uuid import UUID, uuid4

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
from prometheus_client import Counter, Histogram

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log, safe_error_detail
from app.db.models_banking_connection import (
    BankConnection,
    ConnectedBankAccount,
    PaymentInitiation,
    PaymentInitiationStatus,
    ConnectionStatus,
)
from .psd2_integration_service import (
    PSD2IntegrationService,
    PSD2PaymentRequest,
    PSD2PaymentResponse,
    get_psd2_service,
)
from .fints_service import FinTSService, TANChallenge

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metrics
# =============================================================================

PAYMENTS_INITIATED = Counter(
    "banking_payments_initiated_total",
    "Total payments initiated",
    ["company_id", "payment_type", "status"]
)

PAYMENTS_COMPLETED = Counter(
    "banking_payments_completed_total",
    "Total payments completed",
    ["company_id", "payment_type"]
)

PAYMENT_DURATION = Histogram(
    "banking_payment_duration_seconds",
    "Payment processing duration",
    ["company_id", "payment_type"]
)


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class PaymentConfig:
    """Payment configuration."""
    require_approval_above: Decimal = Decimal("5000.00")  # Require approval above this amount
    max_single_payment: Decimal = Decimal("100000.00")
    max_daily_total: Decimal = Decimal("500000.00")
    allow_future_dated: bool = True
    max_future_days: int = 365
    allow_batch_payments: bool = True
    max_batch_size: int = 100


DEFAULT_CONFIG = PaymentConfig()


# =============================================================================
# Types
# =============================================================================

@dataclass
class PaymentRequest:
    """Payment request."""
    company_id: UUID
    account_id: UUID
    creditor_name: str
    creditor_iban: str
    creditor_bic: Optional[str]
    amount: Decimal
    currency: str = "EUR"
    reference: Optional[str] = None
    end_to_end_id: Optional[str] = None
    execution_date: Optional[date] = None
    invoice_id: Optional[UUID] = None
    document_id: Optional[UUID] = None


@dataclass
class PaymentResult:
    """Payment initiation result."""
    success: bool
    payment_id: Optional[UUID] = None
    status: Optional[str] = None
    error_message: Optional[str] = None
    requires_approval: bool = False
    requires_sca: bool = False
    sca_redirect_url: Optional[str] = None
    tan_challenge: Optional[TANChallenge] = None


@dataclass
class BatchPaymentRequest:
    """Batch payment request."""
    company_id: UUID
    account_id: UUID
    payments: List[PaymentRequest]
    batch_name: Optional[str] = None
    execution_date: Optional[date] = None


@dataclass
class BatchPaymentResult:
    """Batch payment result."""
    success: bool
    batch_id: Optional[UUID] = None
    total_count: int = 0
    total_amount: Decimal = Decimal("0")
    error_message: Optional[str] = None
    requires_approval: bool = False
    individual_results: List[PaymentResult] = field(default_factory=list)


# =============================================================================
# Payment Initiation Service
# =============================================================================

class PaymentInitiationService:
    """
    Service for initiating payments.

    Supports:
    - SEPA Credit Transfer via PSD2 PISP
    - SEPA Credit Transfer via FinTS
    - Batch payments
    - Scheduled payments
    - Dual approval workflow
    """

    def __init__(
        self,
        psd2_service: Optional[PSD2IntegrationService] = None,
        fints_service: Optional[FinTSService] = None,
        config: Optional[PaymentConfig] = None,
    ):
        self.psd2_service = psd2_service or get_psd2_service()
        self.fints_service = fints_service or FinTSService()
        self.config = config or DEFAULT_CONFIG

        logger.info("payment_initiation_service_initialized")

    # =========================================================================
    # Payment Initiation
    # =========================================================================

    async def initiate_payment(
        self,
        db: AsyncSession,
        request: PaymentRequest,
        user_id: UUID,
        redirect_uri: Optional[str] = None,
    ) -> PaymentResult:
        """
        Initiate a SEPA Credit Transfer.

        Args:
            db: Database session
            request: Payment request details
            user_id: User initiating the payment
            redirect_uri: Redirect URI for PSD2 SCA

        Returns:
            PaymentResult with status and any SCA requirements
        """
        # Validate request
        validation_error = self._validate_payment_request(request)
        if validation_error:
            return PaymentResult(
                success=False,
                error_message=validation_error,
            )

        # Get account and connection
        account = await db.get(ConnectedBankAccount, request.account_id)
        if not account:
            return PaymentResult(
                success=False,
                error_message="Konto nicht gefunden",
            )

        connection = await db.get(BankConnection, account.connection_id)
        if not connection or connection.company_id != request.company_id:
            return PaymentResult(
                success=False,
                error_message="Keine Berechtigung für dieses Konto",
            )

        if connection.status != ConnectionStatus.ACTIVE.value:
            return PaymentResult(
                success=False,
                error_message=f"Verbindung nicht aktiv: {connection.status}",
            )

        # Check daily limit
        daily_total = await self._get_daily_payment_total(db, request.company_id)
        if daily_total + request.amount > self.config.max_daily_total:
            return PaymentResult(
                success=False,
                error_message=f"Tageslimit von {self.config.max_daily_total} EUR wuerde überschritten",
            )

        # Check if approval required
        requires_approval = request.amount >= self.config.require_approval_above

        # Generate end-to-end ID if not provided
        end_to_end_id = request.end_to_end_id or f"ABLAGE-{uuid4().hex[:12].upper()}"

        try:
            # Create payment record
            payment = PaymentInitiation(
                company_id=request.company_id,
                connection_id=connection.id,
                account_id=account.id,
                payment_type="sepa_credit",
                debtor_iban=account.iban,
                debtor_name=None,  # Filled from connection
                creditor_name=request.creditor_name,
                creditor_iban=request.creditor_iban,
                creditor_bic=request.creditor_bic,
                amount=request.amount,
                currency=request.currency,
                reference=request.reference,
                end_to_end_id=end_to_end_id,
                requested_execution_date=datetime.combine(request.execution_date, datetime.min.time()) if request.execution_date else None,
                invoice_id=request.invoice_id,
                document_id=request.document_id,
                status=PaymentInitiationStatus.DRAFT.value if requires_approval else PaymentInitiationStatus.PENDING_APPROVAL.value,
                requires_approval=requires_approval,
                created_by_id=user_id,
            )

            db.add(payment)
            await db.flush()

            # If approval required, return early
            if requires_approval:
                await db.commit()

                logger.info(
                    "payment_requires_approval",
                    payment_id=str(payment.id),
                    # SECURITY: Never log amounts
                )

                return PaymentResult(
                    success=True,
                    payment_id=payment.id,
                    status=payment.status,
                    requires_approval=True,
                )

            # Initiate with bank
            if connection.connection_type == "psd2":
                result = await self._initiate_psd2_payment(
                    db, connection, payment, redirect_uri
                )
            else:
                result = await self._initiate_fints_payment(
                    db, connection, payment
                )

            await db.commit()

            PAYMENTS_INITIATED.labels(
                company_id=str(request.company_id),
                payment_type="sepa_credit",
                status=result.status or "unknown",
            ).inc()

            return result

        except Exception as e:
            await db.rollback()

            logger.error(
                "payment_initiation_error",
                **safe_error_log(e),
            )

            return PaymentResult(
                success=False,
                error_message=safe_error_detail(e, "Zahlung"),
            )

    async def _initiate_psd2_payment(
        self,
        db: AsyncSession,
        connection: BankConnection,
        payment: PaymentInitiation,
        redirect_uri: Optional[str],
    ) -> PaymentResult:
        """Initiate payment via PSD2 PISP."""
        if not redirect_uri:
            return PaymentResult(
                success=False,
                payment_id=payment.id,
                error_message="Redirect URI erforderlich für PSD2 Zahlung",
            )

        psd2_request = PSD2PaymentRequest(
            debtor_iban=payment.debtor_iban,
            debtor_name=payment.debtor_name,
            creditor_name=payment.creditor_name,
            creditor_iban=payment.creditor_iban,
            creditor_bic=payment.creditor_bic,
            amount=payment.amount,
            currency=payment.currency,
            remittance_info=payment.reference,
            end_to_end_id=payment.end_to_end_id,
            requested_execution_date=payment.requested_execution_date.date() if payment.requested_execution_date else None,
        )

        response, error = await self.psd2_service.initiate_payment(
            bank_code=connection.bank_code,
            access_token="placeholder",  # Would come from stored tokens
            payment=psd2_request,
            redirect_uri=redirect_uri,
        )

        if error:
            payment.status = PaymentInitiationStatus.REJECTED.value
            payment.rejection_reason = error
            return PaymentResult(
                success=False,
                payment_id=payment.id,
                status=payment.status,
                error_message=error,
            )

        # Update payment with PSD2 response
        payment.psd2_payment_id = response.payment_id
        payment.psd2_status = response.transaction_status
        payment.sca_redirect_url = response.sca_redirect_url
        payment.sca_status = response.sca_status
        payment.status = PaymentInitiationStatus.AWAITING_SCA.value
        payment.submitted_at = utc_now()

        return PaymentResult(
            success=True,
            payment_id=payment.id,
            status=payment.status,
            requires_sca=True,
            sca_redirect_url=response.sca_redirect_url,
        )

    async def _initiate_fints_payment(
        self,
        db: AsyncSession,
        connection: BankConnection,
        payment: PaymentInitiation,
    ) -> PaymentResult:
        """Initiate payment via FinTS."""
        # FinTS requires TAN for each payment
        # We would need to call the FinTS service here

        # For now, simulate TAN challenge
        tan_challenge = TANChallenge(
            challenge_id=uuid4().hex,
            tan_method=connection.selected_tan_method or "push_tan",
            challenge_text=f"Bitte bestätigen Sie die Überweisung an {payment.creditor_name}",
            expires_at=utc_now() + timedelta(minutes=5),
        )

        payment.tan_required = True
        payment.tan_method = tan_challenge.tan_method
        payment.tan_challenge = tan_challenge.challenge_text
        payment.status = PaymentInitiationStatus.AWAITING_SCA.value
        payment.submitted_at = utc_now()

        return PaymentResult(
            success=True,
            payment_id=payment.id,
            status=payment.status,
            requires_sca=True,
            tan_challenge=tan_challenge,
        )

    # =========================================================================
    # Payment Completion
    # =========================================================================

    async def complete_payment_sca(
        self,
        db: AsyncSession,
        payment_id: UUID,
        company_id: UUID,
        user_id: UUID,
        tan: Optional[str] = None,
        authorization_code: Optional[str] = None,
    ) -> PaymentResult:
        """
        Complete payment after SCA.

        Args:
            db: Database session
            payment_id: Payment to complete
            company_id: Company ID for security
            user_id: User completing the payment
            tan: TAN for FinTS payments
            authorization_code: Authorization code for PSD2
        """
        payment = await db.get(PaymentInitiation, payment_id)
        if not payment or payment.company_id != company_id:
            return PaymentResult(
                success=False,
                error_message="Zahlung nicht gefunden",
            )

        if payment.status != PaymentInitiationStatus.AWAITING_SCA.value:
            return PaymentResult(
                success=False,
                payment_id=payment_id,
                error_message=f"Ungültiger Status: {payment.status}",
            )

        connection = await db.get(BankConnection, payment.connection_id)
        if not connection:
            return PaymentResult(
                success=False,
                payment_id=payment_id,
                error_message="Verbindung nicht gefunden",
            )

        try:
            if connection.connection_type == "psd2":
                # For PSD2, check payment status after SCA
                status, error = await self.psd2_service.get_payment_status(
                    bank_code=connection.bank_code,
                    access_token="placeholder",
                    payment_id=payment.psd2_payment_id or "",
                )

                if error:
                    payment.status = PaymentInitiationStatus.REJECTED.value
                    payment.rejection_reason = error
                else:
                    payment.psd2_status = status
                    if status in ("ACCP", "ACSC", "ACSP"):
                        payment.status = PaymentInitiationStatus.ACCEPTED.value
                        payment.executed_at = utc_now()
                    elif status in ("RJCT", "CANC"):
                        payment.status = PaymentInitiationStatus.REJECTED.value
                    else:
                        payment.status = PaymentInitiationStatus.SUBMITTED.value

            else:
                # For FinTS, verify TAN
                if not tan or len(tan) < 6:
                    return PaymentResult(
                        success=False,
                        payment_id=payment_id,
                        error_message="Ungültige TAN",
                    )

                # In production: Verify TAN with FinTS
                payment.status = PaymentInitiationStatus.ACCEPTED.value
                payment.executed_at = utc_now()

            await db.commit()

            if payment.status == PaymentInitiationStatus.ACCEPTED.value:
                PAYMENTS_COMPLETED.labels(
                    company_id=str(company_id),
                    payment_type="sepa_credit",
                ).inc()

            logger.info(
                "payment_sca_completed",
                payment_id=str(payment_id),
                status=payment.status,
            )

            return PaymentResult(
                success=payment.status in (
                    PaymentInitiationStatus.ACCEPTED.value,
                    PaymentInitiationStatus.SUBMITTED.value,
                ),
                payment_id=payment_id,
                status=payment.status,
            )

        except Exception as e:
            logger.error(
                "payment_sca_error",
                payment_id=str(payment_id),
                **safe_error_log(e),
            )
            return PaymentResult(
                success=False,
                payment_id=payment_id,
                error_message=safe_error_detail(e, "SCA"),
            )

    async def approve_payment(
        self,
        db: AsyncSession,
        payment_id: UUID,
        company_id: UUID,
        approver_id: UUID,
    ) -> PaymentResult:
        """Approve a payment that requires approval."""
        payment = await db.get(PaymentInitiation, payment_id)
        if not payment or payment.company_id != company_id:
            return PaymentResult(
                success=False,
                error_message="Zahlung nicht gefunden",
            )

        if payment.status != PaymentInitiationStatus.DRAFT.value:
            return PaymentResult(
                success=False,
                payment_id=payment_id,
                error_message=f"Zahlung kann nicht freigegeben werden: {payment.status}",
            )

        # Prevent self-approval
        if payment.created_by_id == approver_id:
            return PaymentResult(
                success=False,
                payment_id=payment_id,
                error_message="Eigene Zahlungen können nicht freigegeben werden",
            )

        payment.status = PaymentInitiationStatus.PENDING_APPROVAL.value
        payment.approved_by_id = approver_id
        payment.approved_at = utc_now()

        await db.commit()

        logger.info(
            "payment_approved",
            payment_id=str(payment_id),
            approver_id=str(approver_id),
        )

        return PaymentResult(
            success=True,
            payment_id=payment_id,
            status=payment.status,
        )

    async def cancel_payment(
        self,
        db: AsyncSession,
        payment_id: UUID,
        company_id: UUID,
        user_id: UUID,
        reason: Optional[str] = None,
    ) -> PaymentResult:
        """Cancel a pending payment."""
        payment = await db.get(PaymentInitiation, payment_id)
        if not payment or payment.company_id != company_id:
            return PaymentResult(
                success=False,
                error_message="Zahlung nicht gefunden",
            )

        if payment.status not in (
            PaymentInitiationStatus.DRAFT.value,
            PaymentInitiationStatus.PENDING_APPROVAL.value,
            PaymentInitiationStatus.AWAITING_SCA.value,
        ):
            return PaymentResult(
                success=False,
                payment_id=payment_id,
                error_message=f"Zahlung kann nicht storniert werden: {payment.status}",
            )

        payment.status = PaymentInitiationStatus.CANCELLED.value
        payment.rejection_reason = reason or "Vom Benutzer storniert"

        await db.commit()

        logger.info(
            "payment_cancelled",
            payment_id=str(payment_id),
            cancelled_by=str(user_id),
        )

        return PaymentResult(
            success=True,
            payment_id=payment_id,
            status=payment.status,
        )

    # =========================================================================
    # Batch Payments
    # =========================================================================

    async def initiate_batch_payment(
        self,
        db: AsyncSession,
        request: BatchPaymentRequest,
        user_id: UUID,
    ) -> BatchPaymentResult:
        """Initiate a batch of payments."""
        if not self.config.allow_batch_payments:
            return BatchPaymentResult(
                success=False,
                error_message="Sammelzahlungen sind deaktiviert",
            )

        if len(request.payments) > self.config.max_batch_size:
            return BatchPaymentResult(
                success=False,
                error_message=f"Maximal {self.config.max_batch_size} Zahlungen pro Batch",
            )

        # Calculate total
        total_amount = sum(p.amount for p in request.payments)

        # Check daily limit
        daily_total = await self._get_daily_payment_total(db, request.company_id)
        if daily_total + total_amount > self.config.max_daily_total:
            return BatchPaymentResult(
                success=False,
                error_message=f"Tageslimit von {self.config.max_daily_total} EUR wuerde überschritten",
            )

        requires_approval = total_amount >= self.config.require_approval_above

        # Create individual payments
        results = []
        for payment_request in request.payments:
            payment_request.company_id = request.company_id
            payment_request.account_id = request.account_id
            if request.execution_date:
                payment_request.execution_date = request.execution_date

            result = await self.initiate_payment(
                db=db,
                request=payment_request,
                user_id=user_id,
            )
            results.append(result)

        success_count = sum(1 for r in results if r.success)

        logger.info(
            "batch_payment_initiated",
            total=len(request.payments),
            success=success_count,
            requires_approval=requires_approval,
        )

        return BatchPaymentResult(
            success=success_count > 0,
            total_count=len(request.payments),
            total_amount=total_amount,
            requires_approval=requires_approval,
            individual_results=results,
        )

    # =========================================================================
    # Payment Queries
    # =========================================================================

    async def get_pending_payments(
        self,
        db: AsyncSession,
        company_id: UUID,
        limit: int = 50,
    ) -> List[PaymentInitiation]:
        """Get pending payments requiring action."""
        query = select(PaymentInitiation).where(
            and_(
                PaymentInitiation.company_id == company_id,
                PaymentInitiation.status.in_([
                    PaymentInitiationStatus.DRAFT.value,
                    PaymentInitiationStatus.PENDING_APPROVAL.value,
                    PaymentInitiationStatus.AWAITING_SCA.value,
                ]),
            )
        ).order_by(PaymentInitiation.created_at.desc()).limit(limit)

        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_scheduled_payments(
        self,
        db: AsyncSession,
        company_id: UUID,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> List[PaymentInitiation]:
        """Get scheduled future-dated payments."""
        conditions = [
            PaymentInitiation.company_id == company_id,
            PaymentInitiation.requested_execution_date.isnot(None),
            PaymentInitiation.status.in_([
                PaymentInitiationStatus.ACCEPTED.value,
                PaymentInitiationStatus.SUBMITTED.value,
            ]),
        ]

        if from_date:
            conditions.append(PaymentInitiation.requested_execution_date >= datetime.combine(from_date, datetime.min.time()))
        if to_date:
            conditions.append(PaymentInitiation.requested_execution_date <= datetime.combine(to_date, datetime.max.time()))

        query = select(PaymentInitiation).where(
            and_(*conditions)
        ).order_by(PaymentInitiation.requested_execution_date.asc())

        result = await db.execute(query)
        return list(result.scalars().all())

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _validate_payment_request(self, request: PaymentRequest) -> Optional[str]:
        """Validate payment request."""
        if request.amount <= 0:
            return "Betrag muss positiv sein"

        if request.amount > self.config.max_single_payment:
            return f"Maximalbetrag von {self.config.max_single_payment} EUR überschritten"

        if not request.creditor_name or len(request.creditor_name) > 140:
            return "Ungültiger Empfängername (1-140 Zeichen)"

        if not request.creditor_iban or len(request.creditor_iban) < 15:
            return "Ungültige IBAN"

        if request.execution_date:
            today = date.today()
            if request.execution_date < today:
                return "Ausführungsdatum liegt in der Vergangenheit"
            if not self.config.allow_future_dated:
                if request.execution_date > today:
                    return "Terminzahlungen sind nicht erlaubt"
            if (request.execution_date - today).days > self.config.max_future_days:
                return f"Ausführungsdatum maximal {self.config.max_future_days} Tage in der Zukunft"

        return None

    async def _get_daily_payment_total(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> Decimal:
        """Get total payment amount for today."""
        today_start = datetime.combine(date.today(), datetime.min.time())

        query = select(func.coalesce(func.sum(PaymentInitiation.amount), 0)).where(
            and_(
                PaymentInitiation.company_id == company_id,
                PaymentInitiation.created_at >= today_start,
                PaymentInitiation.status.in_([
                    PaymentInitiationStatus.ACCEPTED.value,
                    PaymentInitiationStatus.SUBMITTED.value,
                    PaymentInitiationStatus.AWAITING_SCA.value,
                    PaymentInitiationStatus.PENDING_APPROVAL.value,
                ]),
            )
        )

        result = await db.execute(query)
        return Decimal(str(result.scalar() or 0))


# =============================================================================
# Factory
# =============================================================================

_service_instance: Optional[PaymentInitiationService] = None


def get_payment_initiation_service(
    config: Optional[PaymentConfig] = None,
) -> PaymentInitiationService:
    """Get payment initiation service instance."""
    global _service_instance

    if _service_instance is None or config is not None:
        _service_instance = PaymentInitiationService(config=config)

    return _service_instance
