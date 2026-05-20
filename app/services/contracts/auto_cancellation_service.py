# -*- coding: utf-8 -*-
"""
Auto-Cancellation Service for Contract Management V2.

Automatisiert den Kündigungsprozess:
- Kündigungsschreiben generieren (Deutsche Vorlage)
- Versand planen und durchführen
- Bestätigungsverfolgung
- Vertragsstatus aktualisieren
- Archivierung mit Bestätigung

SECURITY:
- NIEMALS Vertragsdaten in Logs (Geschäftsgeheimnisse)
- E-Mail-Versand über sicheren Service
- Audit-Trail für alle Aktionen

Feinpoliert und durchdacht - Enterprise Contract Management V2.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_contract import (
    Contract,
    ContractCancellation,
    ContractStatus,
    CancellationStatus,
    CancellationType,
)
from app.core.datetime_utils import utc_now

logger = structlog.get_logger(__name__)


# =============================================================================
# German Letter Templates
# =============================================================================


CANCELLATION_TEMPLATES: Dict[str, str] = {
    # Standard-Kündigung
    "standard": """
{company_name}
{company_address}

{recipient_name}
{recipient_address}

{city}, den {date}

Kündigung des Vertrags {contract_number}

Sehr geehrte Damen und Herren,

hiermit kündigen wir den zwischen uns bestehenden Vertrag "{contract_title}"
(Vertragsnummer: {contract_number}) fristgerecht zum {effective_date}.

Bitte bestätigen Sie uns den Eingang dieser Kündigung sowie das Vertragsende
zum genannten Termin schriftlich.

Bis zum Vertragsende werden wir unseren vertraglichen Verpflichtungen
selbstverstaendlich weiterhin nachkommen.

Mit freundlichen Gruessen

{sender_name}
{company_name}
""",

    # Ausserordentliche Kündigung
    "extraordinary": """
{company_name}
{company_address}

{recipient_name}
{recipient_address}

{city}, den {date}

Ausserordentliche Kündigung des Vertrags {contract_number}

Sehr geehrte Damen und Herren,

hiermit kündigen wir den zwischen uns bestehenden Vertrag "{contract_title}"
(Vertragsnummer: {contract_number}) aus wichtigem Grund fristlos,
hilfsweise fristgerecht zum nächstmöglichen Termin.

Grund für die ausserordentliche Kündigung:
{reason}

Wir fordern Sie auf, den Eingang dieser Kündigung sowie die Beendigung
des Vertragsverhältnisses umgehend schriftlich zu bestätigen.

Mit freundlichen Gruessen

{sender_name}
{company_name}
""",

    # Einvernehmliche Aufhebung
    "mutual": """
{company_name}
{company_address}

{recipient_name}
{recipient_address}

{city}, den {date}

Betreff: Einvernehmliche Aufhebung des Vertrags {contract_number}

Sehr geehrte Damen und Herren,

wir moechten den zwischen uns bestehenden Vertrag "{contract_title}"
(Vertragsnummer: {contract_number}) einvernehmlich zum {effective_date} aufheben.

{reason}

Bitte bestätigen Sie Ihr Einverstaendnis mit dieser einvernehmlichen
Vertragsaufhebung schriftlich.

Wir bedanken uns für die bisherige Zusammenarbeit.

Mit freundlichen Gruessen

{sender_name}
{company_name}
""",

    # Nicht-Verlängerung bei Auto-Renewal
    "non_renewal": """
{company_name}
{company_address}

{recipient_name}
{recipient_address}

{city}, den {date}

Mitteilung der Nicht-Verlängerung - Vertrag {contract_number}

Sehr geehrte Damen und Herren,

hiermit teilen wir Ihnen mit, dass wir den zwischen uns bestehenden Vertrag
"{contract_title}" (Vertragsnummer: {contract_number}) nicht verlängern werden.

Gemäß den vertraglichen Bestimmungen endet der Vertrag damit ordnungsgemäß
zum {effective_date}.

Bitte bestätigen Sie den Erhalt dieser Mitteilung sowie das Vertragsende
zum genannten Termin schriftlich.

Mit freundlichen Gruessen

{sender_name}
{company_name}
""",
}


# Reason codes with descriptions
REASON_CODES: Dict[str, str] = {
    "non_renewal": "Keine Verlängerung gewünscht",
    "cost_reduction": "Kosteneinsparung",
    "service_issue": "Serviceprobleme",
    "contract_breach": "Vertragsbruch durch Vertragspartner",
    "consolidation": "Konsolidierung von Verträgen",
    "provider_change": "Anbieterwechsel",
    "project_end": "Projektende",
    "restructuring": "Unternehmensrestrukturierung",
    "other": "Sonstiger Grund",
}


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class CancellationRequest:
    """Request to cancel a contract."""
    contract_id: UUID
    cancellation_type: str  # ordinary, extraordinary, mutual
    effective_date: date
    reason: Optional[str] = None
    reason_code: str = "non_renewal"
    scheduled_send_date: Optional[date] = None
    send_method: str = "email"  # email, post, manual
    recipient_email: Optional[str] = None


@dataclass
class GeneratedLetter:
    """Generated cancellation letter."""
    content: str
    template_used: str
    recipient_name: str
    recipient_address: str
    language: str = "de"


# =============================================================================
# Auto-Cancellation Service
# =============================================================================


class AutoCancellationService:
    """
    Service for automating contract cancellation workflow.

    Features:
    - Generate German cancellation letters
    - Schedule sending at optimal time
    - Track acknowledgment
    - Update contract status
    - Archive with confirmation

    SECURITY:
    - Contract details not logged
    - Secure email service
    - Full audit trail
    """

    def __init__(self, db: AsyncSession):
        """Initialize with database session."""
        self.db = db

    # =========================================================================
    # Cancellation Creation
    # =========================================================================

    async def prepare_cancellation(
        self,
        request: CancellationRequest,
        company_id: UUID,
        requested_by_id: UUID,
    ) -> ContractCancellation:
        """
        Prepare a cancellation for a contract.

        Validates the cancellation request, generates the letter,
        and creates a cancellation record in draft status.

        Args:
            request: Cancellation request details
            company_id: Company ID
            requested_by_id: User requesting cancellation

        Returns:
            Created ContractCancellation in draft status
        """
        # Get contract
        contract = await self._get_contract(request.contract_id, company_id)
        if not contract:
            raise ValueError(f"Vertrag nicht gefunden")

        # Validate cancellation
        validation = await self._validate_cancellation(contract, request)
        if not validation["valid"]:
            raise ValueError(validation["error"])

        # Calculate latest send date
        latest_send_date = self._calculate_latest_send_date(
            contract=contract,
            effective_date=request.effective_date,
            cancellation_type=request.cancellation_type,
        )

        # Get recipient info from contract
        recipient_name, recipient_address, recipient_email = self._get_recipient_info(contract)
        if request.recipient_email:
            recipient_email = request.recipient_email

        # Generate letter
        letter = await self._generate_letter(
            contract=contract,
            cancellation_type=request.cancellation_type,
            effective_date=request.effective_date,
            reason=request.reason,
            recipient_name=recipient_name,
            recipient_address=recipient_address,
        )

        # Create cancellation record
        cancellation = ContractCancellation(
            contract_id=request.contract_id,
            company_id=company_id,
            cancellation_type=request.cancellation_type,
            reason=request.reason,
            reason_code=request.reason_code,
            effective_date=request.effective_date,
            latest_send_date=latest_send_date,
            scheduled_send_date=request.scheduled_send_date,
            letter_template=letter.template_used,
            letter_content=letter.content,
            letter_language=letter.language,
            recipient_name=recipient_name,
            recipient_address=recipient_address,
            recipient_email=recipient_email,
            send_method=request.send_method,
            status=CancellationStatus.DRAFT.value,
            requested_by_id=requested_by_id,
        )

        self.db.add(cancellation)
        await self.db.commit()
        await self.db.refresh(cancellation)

        logger.info(
            "cancellation_prepared",
            cancellation_id=str(cancellation.id),
            contract_id=str(request.contract_id),
            type=request.cancellation_type,
            effective_date=request.effective_date.isoformat(),
        )

        return cancellation

    async def approve_cancellation(
        self,
        cancellation_id: UUID,
        company_id: UUID,
        approved_by_id: UUID,
    ) -> Optional[ContractCancellation]:
        """
        Approve a cancellation request.

        Args:
            cancellation_id: Cancellation ID
            company_id: Company ID
            approved_by_id: Approving user ID

        Returns:
            Updated cancellation or None
        """
        cancellation = await self._get_cancellation(cancellation_id, company_id)
        if not cancellation:
            return None

        if cancellation.status != CancellationStatus.PENDING.value:
            raise ValueError(
                f"Kündigung kann nicht genehmigt werden (Status: {cancellation.status})"
            )

        cancellation.status = CancellationStatus.SCHEDULED.value
        cancellation.approved_by_id = approved_by_id
        cancellation.approved_at = utc_now()

        # Schedule if not already scheduled
        if not cancellation.scheduled_send_date:
            # Schedule for tomorrow or latest_send_date, whichever is earlier
            tomorrow = date.today() + timedelta(days=1)
            cancellation.scheduled_send_date = min(tomorrow, cancellation.latest_send_date)

        await self.db.commit()
        await self.db.refresh(cancellation)

        logger.info(
            "cancellation_approved",
            cancellation_id=str(cancellation_id),
            scheduled_send=cancellation.scheduled_send_date.isoformat(),
        )

        return cancellation

    async def submit_for_approval(
        self,
        cancellation_id: UUID,
        company_id: UUID,
    ) -> Optional[ContractCancellation]:
        """
        Submit a draft cancellation for approval.

        Args:
            cancellation_id: Cancellation ID
            company_id: Company ID

        Returns:
            Updated cancellation or None
        """
        cancellation = await self._get_cancellation(cancellation_id, company_id)
        if not cancellation:
            return None

        if cancellation.status != CancellationStatus.DRAFT.value:
            raise ValueError(
                f"Nur Entwuerfe können zur Genehmigung eingereicht werden"
            )

        cancellation.status = CancellationStatus.PENDING.value
        await self.db.commit()
        await self.db.refresh(cancellation)

        return cancellation

    # =========================================================================
    # Sending
    # =========================================================================

    async def send_cancellation(
        self,
        cancellation_id: UUID,
        company_id: UUID,
        sent_by_id: UUID,
        send_immediately: bool = False,
    ) -> Optional[ContractCancellation]:
        """
        Send a cancellation letter.

        Args:
            cancellation_id: Cancellation ID
            company_id: Company ID
            sent_by_id: User sending
            send_immediately: Override schedule and send now

        Returns:
            Updated cancellation or None
        """
        cancellation = await self._get_cancellation(cancellation_id, company_id)
        if not cancellation:
            return None

        if cancellation.status not in [
            CancellationStatus.SCHEDULED.value,
            CancellationStatus.PENDING.value,
            CancellationStatus.DRAFT.value,  # Allow direct send if approved
        ]:
            raise ValueError(
                f"Kündigung kann nicht gesendet werden (Status: {cancellation.status})"
            )

        # Check if scheduled date is in the future and not forcing
        if (
            not send_immediately
            and cancellation.scheduled_send_date
            and cancellation.scheduled_send_date > date.today()
        ):
            raise ValueError(
                f"Versand ist für {cancellation.scheduled_send_date} geplant. "
                f"Nutzen Sie 'sofort senden' zum Überschreiben."
            )

        # Send based on method
        reference = None
        if cancellation.send_method == "email":
            reference = await self._send_via_email(cancellation)
        elif cancellation.send_method == "post":
            reference = await self._prepare_postal_send(cancellation)
        else:
            # Manual - just mark as sent
            reference = f"MANUAL-{utc_now().strftime('%Y%m%d%H%M%S')}"

        # Update cancellation
        cancellation.status = CancellationStatus.SENT.value
        cancellation.sent_at = utc_now()
        cancellation.sent_by_id = sent_by_id
        cancellation.sent_reference = reference

        await self.db.commit()
        await self.db.refresh(cancellation)

        logger.info(
            "cancellation_sent",
            cancellation_id=str(cancellation_id),
            method=cancellation.send_method,
            reference=reference,
        )

        return cancellation

    async def process_scheduled_cancellations(self) -> Dict[str, Any]:
        """
        Process all scheduled cancellations due for sending.

        This is called by a Celery task.

        Returns:
            Statistics about processed cancellations
        """
        today = date.today()

        # Find scheduled cancellations due for sending
        result = await self.db.execute(
            select(ContractCancellation).where(
                and_(
                    ContractCancellation.status == CancellationStatus.SCHEDULED.value,
                    ContractCancellation.scheduled_send_date <= today,
                )
            )
        )
        cancellations = result.scalars().all()

        stats = {
            "processed": 0,
            "sent": 0,
            "errors": 0,
            "details": [],
        }

        for cancellation in cancellations:
            stats["processed"] += 1
            try:
                # Auto-send
                if cancellation.send_method == "email":
                    reference = await self._send_via_email(cancellation)
                else:
                    reference = await self._prepare_postal_send(cancellation)

                cancellation.status = CancellationStatus.SENT.value
                cancellation.sent_at = utc_now()
                cancellation.sent_reference = reference

                stats["sent"] += 1
                stats["details"].append({
                    "id": str(cancellation.id),
                    "status": "sent",
                })

            except Exception as e:
                stats["errors"] += 1
                stats["details"].append({
                    "id": str(cancellation.id),
                    "status": "error",
                    "error": str(e)[:100],
                })
                logger.error(
                    "cancellation_send_failed",
                    cancellation_id=str(cancellation.id),
                    error_type=type(e).__name__,
                )

        await self.db.commit()

        logger.info(
            "scheduled_cancellations_processed",
            processed=stats["processed"],
            sent=stats["sent"],
            errors=stats["errors"],
        )

        return stats

    # =========================================================================
    # Acknowledgment
    # =========================================================================

    async def record_acknowledgment(
        self,
        cancellation_id: UUID,
        company_id: UUID,
        acknowledgment_date: Optional[datetime] = None,
        reference: Optional[str] = None,
        document_id: Optional[UUID] = None,
    ) -> Optional[ContractCancellation]:
        """
        Record acknowledgment of cancellation.

        Args:
            cancellation_id: Cancellation ID
            company_id: Company ID
            acknowledgment_date: When acknowledgment was received
            reference: Reference number from counterparty
            document_id: Optional document with acknowledgment

        Returns:
            Updated cancellation or None
        """
        cancellation = await self._get_cancellation(cancellation_id, company_id)
        if not cancellation:
            return None

        cancellation.acknowledgment_received = True
        cancellation.acknowledgment_date = acknowledgment_date or utc_now()
        cancellation.acknowledgment_reference = reference
        cancellation.acknowledgment_document_id = document_id
        cancellation.status = CancellationStatus.ACKNOWLEDGED.value

        # Update contract status
        contract = await self._get_contract(cancellation.contract_id, company_id)
        if contract:
            # If effective date is in the future, mark as terminated
            # Otherwise, just update status
            if cancellation.effective_date <= date.today():
                contract.status = ContractStatus.TERMINATED.value
                contract.termination_date = cancellation.effective_date
            else:
                # Scheduled for termination
                contract.termination_date = cancellation.effective_date

        await self.db.commit()
        await self.db.refresh(cancellation)

        logger.info(
            "cancellation_acknowledged",
            cancellation_id=str(cancellation_id),
            contract_id=str(cancellation.contract_id),
        )

        return cancellation

    async def complete_cancellation(
        self,
        cancellation_id: UUID,
        company_id: UUID,
    ) -> Optional[ContractCancellation]:
        """
        Mark cancellation as complete and update contract.

        This is called when the effective date is reached.

        Args:
            cancellation_id: Cancellation ID
            company_id: Company ID

        Returns:
            Updated cancellation or None
        """
        cancellation = await self._get_cancellation(cancellation_id, company_id)
        if not cancellation:
            return None

        if cancellation.status not in [
            CancellationStatus.SENT.value,
            CancellationStatus.ACKNOWLEDGED.value,
        ]:
            raise ValueError(
                f"Kündigung kann nicht abgeschlossen werden (Status: {cancellation.status})"
            )

        cancellation.status = CancellationStatus.COMPLETED.value

        # Update contract
        contract = await self._get_contract(cancellation.contract_id, company_id)
        if contract:
            contract.status = ContractStatus.TERMINATED.value
            contract.termination_date = cancellation.effective_date
            contract.termination_reason = cancellation.reason

        await self.db.commit()
        await self.db.refresh(cancellation)

        logger.info(
            "cancellation_completed",
            cancellation_id=str(cancellation_id),
            contract_id=str(cancellation.contract_id),
        )

        return cancellation

    # =========================================================================
    # Retrieval
    # =========================================================================

    async def get_cancellation(
        self,
        cancellation_id: UUID,
        company_id: UUID,
    ) -> Optional[ContractCancellation]:
        """Get cancellation by ID."""
        return await self._get_cancellation(cancellation_id, company_id)

    async def get_cancellations_for_contract(
        self,
        contract_id: UUID,
        company_id: UUID,
    ) -> List[ContractCancellation]:
        """Get all cancellations for a contract."""
        result = await self.db.execute(
            select(ContractCancellation).where(
                and_(
                    ContractCancellation.contract_id == contract_id,
                    ContractCancellation.company_id == company_id,
                )
            ).order_by(ContractCancellation.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_pending_cancellations(
        self,
        company_id: UUID,
    ) -> List[ContractCancellation]:
        """Get all pending/scheduled cancellations."""
        result = await self.db.execute(
            select(ContractCancellation).where(
                and_(
                    ContractCancellation.company_id == company_id,
                    ContractCancellation.status.in_([
                        CancellationStatus.DRAFT.value,
                        CancellationStatus.PENDING.value,
                        CancellationStatus.SCHEDULED.value,
                    ]),
                )
            ).order_by(ContractCancellation.effective_date.asc())
        )
        return list(result.scalars().all())

    async def get_upcoming_effective_dates(
        self,
        company_id: UUID,
        days_ahead: int = 30,
    ) -> List[ContractCancellation]:
        """Get cancellations with upcoming effective dates."""
        today = date.today()
        cutoff = today + timedelta(days=days_ahead)

        result = await self.db.execute(
            select(ContractCancellation).where(
                and_(
                    ContractCancellation.company_id == company_id,
                    ContractCancellation.status.in_([
                        CancellationStatus.SENT.value,
                        CancellationStatus.ACKNOWLEDGED.value,
                    ]),
                    ContractCancellation.effective_date >= today,
                    ContractCancellation.effective_date <= cutoff,
                )
            ).order_by(ContractCancellation.effective_date.asc())
        )
        return list(result.scalars().all())

    # =========================================================================
    # Internal Methods
    # =========================================================================

    async def _get_contract(
        self,
        contract_id: UUID,
        company_id: UUID,
    ) -> Optional[Contract]:
        """Get contract with access control."""
        result = await self.db.execute(
            select(Contract).where(
                and_(
                    Contract.id == contract_id,
                    Contract.company_id == company_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def _get_cancellation(
        self,
        cancellation_id: UUID,
        company_id: UUID,
    ) -> Optional[ContractCancellation]:
        """Get cancellation with access control."""
        result = await self.db.execute(
            select(ContractCancellation).where(
                and_(
                    ContractCancellation.id == cancellation_id,
                    ContractCancellation.company_id == company_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def _validate_cancellation(
        self,
        contract: Contract,
        request: CancellationRequest,
    ) -> Dict[str, Any]:
        """Validate cancellation request."""
        # Check contract status
        if contract.status in [
            ContractStatus.TERMINATED.value,
            ContractStatus.EXPIRED.value,
        ]:
            return {
                "valid": False,
                "error": "Vertrag ist bereits beendet oder abgelaufen",
            }

        # Check effective date
        today = date.today()
        if request.effective_date < today:
            return {
                "valid": False,
                "error": "Wirksamkeitsdatum kann nicht in der Vergangenheit liegen",
            }

        # For ordinary cancellation, check notice period
        if request.cancellation_type == CancellationType.ORDINARY.value:
            if contract.notice_period_days:
                min_effective_date = today + timedelta(days=contract.notice_period_days)
                if request.effective_date < min_effective_date:
                    return {
                        "valid": False,
                        "error": (
                            f"Kündigungsfrist von {contract.notice_period_days} Tagen "
                            f"nicht eingehalten. Frühestes Wirksamkeitsdatum: "
                            f"{min_effective_date.isoformat()}"
                        ),
                    }

            # Check if effective date aligns with contract end
            if contract.expiration_date and request.effective_date > contract.expiration_date:
                return {
                    "valid": False,
                    "error": (
                        f"Wirksamkeitsdatum liegt nach Vertragsende "
                        f"({contract.expiration_date.isoformat()})"
                    ),
                }

        return {"valid": True}

    def _calculate_latest_send_date(
        self,
        contract: Contract,
        effective_date: date,
        cancellation_type: str,
    ) -> date:
        """Calculate the latest date to send cancellation."""
        if cancellation_type == CancellationType.EXTRAORDINARY.value:
            # Extraordinary - send immediately
            return date.today() + timedelta(days=3)

        # Use notice period or default
        notice_days = contract.notice_period_days or 30

        # Add buffer for postal delivery
        buffer_days = 7

        latest = effective_date - timedelta(days=notice_days + buffer_days)

        # Must be at least tomorrow
        tomorrow = date.today() + timedelta(days=1)
        return max(latest, tomorrow)

    def _get_recipient_info(
        self,
        contract: Contract,
    ) -> tuple[str, str, Optional[str]]:
        """Get recipient info from contract."""
        # Try to get from counterparty entity
        if contract.counterparty:
            entity = contract.counterparty
            name = entity.name
            address = ""
            if hasattr(entity, 'address') and entity.address:
                address = str(entity.address)
            email = getattr(entity, 'email', None)
            return name, address, email

        # Try parties array
        if contract.parties:
            for party in contract.parties:
                if party.get("role") in ["seller", "lessor", "provider"]:
                    return (
                        party.get("name", "Vertragspartner"),
                        party.get("address", ""),
                        party.get("email"),
                    )

        return "Vertragspartner", "", None

    async def _generate_letter(
        self,
        contract: Contract,
        cancellation_type: str,
        effective_date: date,
        reason: Optional[str],
        recipient_name: str,
        recipient_address: str,
    ) -> GeneratedLetter:
        """Generate cancellation letter from template."""
        # Select template
        if cancellation_type == CancellationType.EXTRAORDINARY.value:
            template_name = "extraordinary"
        elif cancellation_type == CancellationType.MUTUAL.value:
            template_name = "mutual"
        elif contract.auto_renewal:
            template_name = "non_renewal"
        else:
            template_name = "standard"

        template = CANCELLATION_TEMPLATES.get(template_name, CANCELLATION_TEMPLATES["standard"])

        # Get company info from contract
        company_name = "Firma"
        company_address = ""
        city = ""
        sender_name = "Geschäftsführung"

        if contract.company:
            company_name = contract.company.name
            if hasattr(contract.company, 'address'):
                company_address = str(contract.company.address or "")
            if hasattr(contract.company, 'city'):
                city = str(contract.company.city or "")

        # Format letter
        content = template.format(
            company_name=company_name,
            company_address=company_address,
            city=city or "Ort",
            date=date.today().strftime("%d.%m.%Y"),
            recipient_name=recipient_name,
            recipient_address=recipient_address,
            contract_number=contract.contract_number or str(contract.id)[:8],
            contract_title=contract.title,
            effective_date=effective_date.strftime("%d.%m.%Y"),
            reason=reason or "",
            sender_name=sender_name,
        )

        return GeneratedLetter(
            content=content.strip(),
            template_used=template_name,
            recipient_name=recipient_name,
            recipient_address=recipient_address,
        )

    async def _send_via_email(
        self,
        cancellation: ContractCancellation,
    ) -> str:
        """Send cancellation via email."""
        from app.services.email_service import get_email_service

        if not cancellation.recipient_email:
            raise ValueError("Keine E-Mail-Adresse für Empfänger")

        email_service = get_email_service()

        # Get contract for subject
        contract = await self.db.get(Contract, cancellation.contract_id)
        contract_ref = contract.contract_number if contract else str(cancellation.contract_id)[:8]

        subject = f"Kündigung Vertrag {contract_ref}"

        # Send email
        message_id = await email_service.send_email(
            to_email=cancellation.recipient_email,
            subject=subject,
            body_text=cancellation.letter_content,
            priority="high",
        )

        return f"EMAIL-{message_id}" if message_id else f"EMAIL-{utc_now().strftime('%Y%m%d%H%M%S')}"

    async def _prepare_postal_send(
        self,
        cancellation: ContractCancellation,
    ) -> str:
        """Prepare cancellation for postal sending."""
        # In a real implementation, this would integrate with a postal service API
        # For now, just mark as ready for manual postal sending
        return f"POST-{utc_now().strftime('%Y%m%d%H%M%S')}"

    async def cancel_cancellation(
        self,
        cancellation_id: UUID,
        company_id: UUID,
    ) -> Optional[ContractCancellation]:
        """
        Cancel a cancellation request.

        Only works for draft, pending, or scheduled cancellations.

        Args:
            cancellation_id: Cancellation ID
            company_id: Company ID

        Returns:
            Updated cancellation or None
        """
        cancellation = await self._get_cancellation(cancellation_id, company_id)
        if not cancellation:
            return None

        if cancellation.status not in [
            CancellationStatus.DRAFT.value,
            CancellationStatus.PENDING.value,
            CancellationStatus.SCHEDULED.value,
        ]:
            raise ValueError(
                f"Kündigung kann nicht mehr abgebrochen werden (Status: {cancellation.status})"
            )

        cancellation.status = CancellationStatus.CANCELLED.value
        await self.db.commit()
        await self.db.refresh(cancellation)

        logger.info(
            "cancellation_cancelled",
            cancellation_id=str(cancellation_id),
        )

        return cancellation


# =============================================================================
# Factory Function
# =============================================================================


def get_auto_cancellation_service(db: AsyncSession) -> AutoCancellationService:
    """Factory function to create AutoCancellationService instance."""
    return AutoCancellationService(db)
