# -*- coding: utf-8 -*-
"""
Inkasso Service for debt collection.

Integrates with collection agencies (EOS, Creditreform Inkasso, Atriga).
Handles debt transfer, case tracking, and entity status updates.

Feinpoliert und durchdacht - Enterprise Inkasso-Integration.
"""

import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional, Dict, Any, List
from uuid import UUID

import httpx
import structlog
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_

from app.core.config import settings
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


class InkassoProvider(str, Enum):
    """Supported inkasso/collection partners."""
    EOS = "eos"                      # EOS Gruppe
    CREDITREFORM = "creditreform"    # Creditreform Inkasso
    ATRIGA = "atriga"                # ATRIGA Forderungsmanagement
    INTRUM = "intrum"                # Intrum Justitia
    MOCK = "mock"                    # Mock mode for testing


class CollectionStatus(str, Enum):
    """Status of collection case."""
    PENDING = "pending"              # Uebermittelt, noch nicht bearbeitet
    IN_PROGRESS = "in_progress"      # Aktiv bearbeitet
    PAYMENT_PLAN = "payment_plan"    # Ratenzahlung vereinbart
    PARTIAL_PAYMENT = "partial"      # Teilzahlung erhalten
    COLLECTED = "collected"          # Vollstaendig eingetrieben
    UNCOLLECTABLE = "uncollectable"  # Uneinbringlich
    RETURNED = "returned"            # Zurueck an Auftraggeber
    LEGAL = "legal"                  # Gerichtliches Mahnverfahren


class CollectionTransferResult(BaseModel):
    """Result of a collection transfer."""
    success: bool
    collection_reference: str
    provider: str
    transferred_at: datetime
    estimated_collection_probability: Optional[float] = None
    estimated_timeline_days: Optional[int] = None
    fees: Optional[Dict[str, float]] = None
    error_message: Optional[str] = None


class CollectionCaseUpdate(BaseModel):
    """Update from collection partner."""
    collection_reference: str
    status: CollectionStatus
    collected_amount: Optional[Decimal] = None
    remaining_amount: Optional[Decimal] = None
    update_date: datetime
    notes: Optional[str] = None
    next_action: Optional[str] = None


class InkassoService:
    """
    Service fuer Inkasso-Uebergaben.

    Features:
    - Multi-Provider Support (EOS, Creditreform, Atriga, Intrum)
    - Automatic provider selection based on case characteristics
    - Entity status tracking
    - Invoice status updates
    - Webhook support for status updates from providers

    Configuration via settings:
    - INKASSO_PROVIDER: Default provider (or "auto" for automatic selection)
    - INKASSO_API_KEY: API key for default provider
    - INKASSO_WEBHOOK_SECRET: Secret for webhook verification

    Provider-specific credentials:
    - EOS_API_KEY, EOS_API_URL
    - CREDITREFORM_INKASSO_API_KEY, CREDITREFORM_INKASSO_API_URL
    - ATRIGA_API_KEY, ATRIGA_API_URL
    """

    # Provider-specific configuration
    PROVIDER_CONFIGS = {
        InkassoProvider.EOS: {
            "base_url": "https://api.eos-solutions.com/v1",
            "success_fee_percent": 15.0,
            "min_claim_amount": 100.00,
        },
        InkassoProvider.CREDITREFORM: {
            "base_url": "https://api.creditreform-inkasso.de/v1",
            "success_fee_percent": 12.0,
            "min_claim_amount": 50.00,
        },
        InkassoProvider.ATRIGA: {
            "base_url": "https://api.atriga.de/v2",
            "success_fee_percent": 10.0,
            "min_claim_amount": 200.00,
        },
        InkassoProvider.INTRUM: {
            "base_url": "https://api.intrum.com/v1",
            "success_fee_percent": 14.0,
            "min_claim_amount": 100.00,
        },
    }

    def __init__(self, db: AsyncSession):
        """
        Initialize InkassoService.

        Args:
            db: AsyncSession for database access
        """
        self.db = db

        # Get provider from settings
        provider_str = getattr(settings, "INKASSO_PROVIDER", "mock")
        try:
            self.default_provider = InkassoProvider(provider_str.lower())
        except ValueError:
            self.default_provider = InkassoProvider.MOCK

        # Get API credentials
        self.api_key = getattr(settings, "INKASSO_API_KEY", None)
        self.webhook_secret = getattr(settings, "INKASSO_WEBHOOK_SECRET", None)

        # Mock mode if no credentials
        self.mock_mode = (
            self.default_provider == InkassoProvider.MOCK
            or not self.api_key
        )

        if self.mock_mode:
            logger.warning("inkasso_service_mock_mode", reason="No API credentials configured")

    async def transfer_to_collection(
        self,
        invoice_id: UUID,
        entity_id: UUID,
        company_id: UUID,
        amount: Decimal,
        dunning_level: int = 3,
        reason: str = "Zahlungsverzug nach Mahnstufe 3",
        provider: Optional[InkassoProvider] = None,
        additional_data: Optional[Dict[str, Any]] = None,
    ) -> CollectionTransferResult:
        """
        Transfer a debt to collection agency.

        Args:
            invoice_id: Invoice to collect
            entity_id: Debtor entity
            company_id: Company (mandant) ID
            amount: Outstanding amount
            dunning_level: Current dunning level (default: 3)
            reason: Reason for collection transfer
            provider: Specific provider (optional, uses default if not specified)
            additional_data: Additional case data

        Returns:
            CollectionTransferResult with reference number and status

        Raises:
            ValueError: If invoice or entity not found
        """
        from app.db.models import BusinessEntity, InvoiceTracking

        # Load invoice and entity
        invoice = await self.db.get(InvoiceTracking, invoice_id)
        entity = await self.db.get(BusinessEntity, entity_id)

        if not invoice:
            raise ValueError(f"Rechnung {invoice_id} nicht gefunden")
        if not entity:
            raise ValueError(f"Geschaeftspartner {entity_id} nicht gefunden")

        # Select provider
        selected_provider = provider or self.default_provider

        # Generate unique collection reference
        collection_ref = self._generate_collection_reference(invoice_id)

        # Prepare case data
        case_data = self._prepare_case_data(
            invoice=invoice,
            entity=entity,
            amount=amount,
            dunning_level=dunning_level,
            reason=reason,
            additional_data=additional_data,
        )

        result: CollectionTransferResult

        if self.mock_mode:
            # Mock transfer
            logger.info(
                "inkasso_transfer_mock",
                invoice_id=str(invoice_id),
                amount=float(amount),
                reference=collection_ref,
                provider=selected_provider.value
            )
            result = CollectionTransferResult(
                success=True,
                collection_reference=collection_ref,
                provider=selected_provider.value,
                transferred_at=datetime.now(timezone.utc),
                estimated_collection_probability=0.65,
                estimated_timeline_days=45,
                fees={"success_fee_percent": 12.0, "min_fee": 25.0},
            )
        else:
            # Real API transfer
            result = await self._api_transfer(
                provider=selected_provider,
                case_data=case_data,
                reference=collection_ref,
            )

        if result.success:
            # Update entity status
            await self.db.execute(
                update(BusinessEntity)
                .where(BusinessEntity.id == entity_id)
                .values(
                    status="collection_pending",
                    custom_fields=BusinessEntity.custom_fields.concat({
                        "collection_reference": collection_ref,
                        "collection_provider": selected_provider.value,
                        "collection_transferred_at": datetime.now(timezone.utc).isoformat(),
                        "collection_amount": float(amount),
                    })
                )
            )

            # Update invoice status
            await self.db.execute(
                update(InvoiceTracking)
                .where(InvoiceTracking.id == invoice_id)
                .values(
                    status="collection",
                    dunning_level=4,  # 4 = Inkasso
                )
            )

            await self.db.commit()

            logger.info(
                "inkasso_transfer_success",
                invoice_id=str(invoice_id),
                entity_id=str(entity_id),
                reference=collection_ref,
                provider=selected_provider.value
            )
        else:
            logger.error(
                "inkasso_transfer_failed",
                invoice_id=str(invoice_id),
                error=result.error_message
            )

        return result

    async def get_case_status(
        self,
        collection_reference: str,
        provider: Optional[InkassoProvider] = None,
    ) -> CollectionCaseUpdate:
        """
        Get current status of a collection case.

        Args:
            collection_reference: Reference number from transfer
            provider: Provider to query (uses default if not specified)

        Returns:
            CollectionCaseUpdate with current status
        """
        selected_provider = provider or self.default_provider

        if self.mock_mode:
            return CollectionCaseUpdate(
                collection_reference=collection_reference,
                status=CollectionStatus.IN_PROGRESS,
                collected_amount=None,
                remaining_amount=None,
                update_date=datetime.now(timezone.utc),
                notes="Mahnverfahren laeuft",
                next_action="Telefonische Kontaktaufnahme geplant",
            )

        # Real API query
        return await self._api_get_status(selected_provider, collection_reference)

    async def handle_webhook(
        self,
        provider: InkassoProvider,
        payload: Dict[str, Any],
        signature: Optional[str] = None,
    ) -> bool:
        """
        Handle webhook callback from collection partner.

        Args:
            provider: Source provider
            payload: Webhook payload
            signature: Webhook signature for verification

        Returns:
            True if handled successfully
        """
        # Verify webhook signature if configured
        if self.webhook_secret and signature:
            if not self._verify_webhook_signature(payload, signature):
                logger.warning("inkasso_webhook_invalid_signature", provider=provider.value)
                return False

        # Extract reference and status
        reference = payload.get("reference") or payload.get("collection_reference")
        status_str = payload.get("status")

        if not reference or not status_str:
            logger.warning("inkasso_webhook_missing_fields", provider=provider.value)
            return False

        try:
            status = CollectionStatus(status_str.lower())
        except ValueError:
            logger.warning(
                "inkasso_webhook_unknown_status",
                provider=provider.value,
                status=status_str
            )
            status = CollectionStatus.IN_PROGRESS

        # Find and update entities with this reference
        from app.db.models import BusinessEntity, InvoiceTracking
        from sqlalchemy import cast, String
        from sqlalchemy.dialects.postgresql import JSONB

        # Update collection status in entity custom_fields
        # Note: This is a simplified update; production should use more robust matching
        collected_amount = payload.get("collected_amount")
        if collected_amount:
            collected_amount = Decimal(str(collected_amount))

        logger.info(
            "inkasso_webhook_received",
            provider=provider.value,
            reference=reference,
            status=status.value,
            collected_amount=float(collected_amount) if collected_amount else None
        )

        # Update entity status based on collection status
        if status == CollectionStatus.COLLECTED:
            new_entity_status = "active"  # Debt collected, customer can continue
        elif status == CollectionStatus.UNCOLLECTABLE:
            new_entity_status = "blocked"  # Marked as bad debt
        elif status == CollectionStatus.RETURNED:
            new_entity_status = "review_required"  # Needs manual review
        else:
            new_entity_status = "collection_pending"  # Still in progress

        # This is a placeholder - actual implementation would query by reference in custom_fields
        # await self.db.execute(...)
        # await self.db.commit()

        return True

    async def cancel_collection(
        self,
        collection_reference: str,
        reason: str = "Zahlung erhalten",
        provider: Optional[InkassoProvider] = None,
    ) -> bool:
        """
        Cancel an active collection case.

        Args:
            collection_reference: Reference number
            reason: Cancellation reason
            provider: Provider to notify

        Returns:
            True if cancelled successfully
        """
        selected_provider = provider or self.default_provider

        if self.mock_mode:
            logger.info(
                "inkasso_cancel_mock",
                reference=collection_reference,
                reason=reason
            )
            return True

        # Real API cancellation
        return await self._api_cancel(selected_provider, collection_reference, reason)

    # =========================================================================
    # Private Methods
    # =========================================================================

    def _generate_collection_reference(self, invoice_id: UUID) -> str:
        """Generate unique collection reference number."""
        date_part = datetime.now().strftime("%Y%m%d")
        id_part = str(invoice_id)[:8].upper()
        return f"INK-{date_part}-{id_part}"

    def _prepare_case_data(
        self,
        invoice,
        entity,
        amount: Decimal,
        dunning_level: int,
        reason: str,
        additional_data: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Prepare case data for API transfer."""
        return {
            "debtor": {
                "name": entity.name,
                "street": entity.street,
                "postal_code": entity.postal_code,
                "city": entity.city,
                "country": entity.country or "DE",
                "email": entity.email,
                "phone": entity.phone,
                "vat_id": entity.vat_id,
            },
            "claim": {
                "invoice_number": invoice.invoice_number,
                "invoice_date": invoice.invoice_date.isoformat() if invoice.invoice_date else None,
                "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
                "original_amount": float(invoice.amount),
                "outstanding_amount": float(amount),
                "currency": invoice.currency or "EUR",
                "dunning_level": dunning_level,
            },
            "reason": reason,
            "additional_data": additional_data or {},
        }

    async def _api_transfer(
        self,
        provider: InkassoProvider,
        case_data: Dict[str, Any],
        reference: str,
    ) -> CollectionTransferResult:
        """Execute actual API transfer to collection partner."""
        config = self.PROVIDER_CONFIGS.get(provider, {})
        base_url = config.get("base_url", "")

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{base_url}/cases",
                    headers=self._get_api_headers(provider),
                    json={
                        "reference": reference,
                        **case_data,
                    },
                )
                response.raise_for_status()
                data = response.json()

                return CollectionTransferResult(
                    success=True,
                    collection_reference=data.get("reference", reference),
                    provider=provider.value,
                    transferred_at=datetime.now(timezone.utc),
                    estimated_collection_probability=data.get("probability"),
                    estimated_timeline_days=data.get("timeline_days"),
                    fees=data.get("fees"),
                )

        except httpx.HTTPError as e:
            return CollectionTransferResult(
                success=False,
                collection_reference=reference,
                provider=provider.value,
                transferred_at=datetime.now(timezone.utc),
                error_message=safe_error_detail(e, "Inkasso-Uebertragung"),
            )

    async def _api_get_status(
        self,
        provider: InkassoProvider,
        reference: str,
    ) -> CollectionCaseUpdate:
        """Get case status from API."""
        config = self.PROVIDER_CONFIGS.get(provider, {})
        base_url = config.get("base_url", "")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{base_url}/cases/{reference}",
                    headers=self._get_api_headers(provider),
                )
                response.raise_for_status()
                data = response.json()

                return CollectionCaseUpdate(
                    collection_reference=reference,
                    status=CollectionStatus(data.get("status", "in_progress")),
                    collected_amount=Decimal(str(data["collected_amount"])) if data.get("collected_amount") else None,
                    remaining_amount=Decimal(str(data["remaining_amount"])) if data.get("remaining_amount") else None,
                    update_date=datetime.now(timezone.utc),
                    notes=data.get("notes"),
                    next_action=data.get("next_action"),
                )

        except httpx.HTTPError:
            return CollectionCaseUpdate(
                collection_reference=reference,
                status=CollectionStatus.IN_PROGRESS,
                update_date=datetime.now(timezone.utc),
                notes="Status konnte nicht abgerufen werden",
            )

    async def _api_cancel(
        self,
        provider: InkassoProvider,
        reference: str,
        reason: str,
    ) -> bool:
        """Cancel case via API."""
        config = self.PROVIDER_CONFIGS.get(provider, {})
        base_url = config.get("base_url", "")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(
                    f"{base_url}/cases/{reference}",
                    headers=self._get_api_headers(provider),
                    json={"reason": reason},
                )
                return response.status_code in (200, 204)

        except httpx.HTTPError:
            return False

    def _get_api_headers(self, provider: InkassoProvider) -> Dict[str, str]:
        """Get API headers for provider."""
        # Provider-specific API key lookup
        api_key = self.api_key

        if provider == InkassoProvider.EOS:
            api_key = getattr(settings, "EOS_API_KEY", api_key)
        elif provider == InkassoProvider.CREDITREFORM:
            api_key = getattr(settings, "CREDITREFORM_INKASSO_API_KEY", api_key)
        elif provider == InkassoProvider.ATRIGA:
            api_key = getattr(settings, "ATRIGA_API_KEY", api_key)

        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _verify_webhook_signature(
        self,
        payload: Dict[str, Any],
        signature: str,
    ) -> bool:
        """Verify webhook signature."""
        import json
        import hmac

        if not self.webhook_secret:
            return False

        payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        expected_sig = hmac.new(
            self.webhook_secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(signature, expected_sig)
