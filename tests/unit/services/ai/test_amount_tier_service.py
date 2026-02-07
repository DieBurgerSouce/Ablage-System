# -*- coding: utf-8 -*-
"""
Unit Tests fuer AmountTierService.

Tests fuer betragsbasierte Freigabestufen und Approval-Modi.
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai.amount_tier_service import (
    AmountTierService,
    AmountTier,
    ApprovalMode,
    DEFAULT_TIERS,
    get_amount_tier_service,
)
from app.db.models import Company


class TestDefaultTiers:
    """Tests fuer Standard-Betragstufen."""

    @pytest.mark.asyncio
    async def test_default_tiers_returned_when_no_custom(self) -> None:
        """Test: Ohne Custom-Config werden Default-Tiers zurueckgegeben."""
        # Setup
        db = AsyncMock(spec=AsyncSession)
        company_id = uuid4()

        # Mock company without filing_rules
        company = MagicMock(spec=Company)
        company.filing_rules = None

        db.execute = AsyncMock()
        db.execute.return_value.scalar_one_or_none = MagicMock(return_value=company)

        service = AmountTierService(db)

        # Execute
        tiers = await service.get_tiers(company_id)

        # Verify
        assert len(tiers) == 3
        assert tiers[0].name == "Automatisch"
        assert tiers[0].max_amount == Decimal("500.00")
        assert tiers[0].approval_mode == "auto"
        assert tiers[1].name == "Ein-Klick"
        assert tiers[2].name == "Explizit"

    @pytest.mark.asyncio
    async def test_default_tiers_have_correct_settings(self) -> None:
        """Test: Default-Tiers haben korrekte Einstellungen."""
        assert len(DEFAULT_TIERS) == 3
        assert DEFAULT_TIERS[0].approval_mode == "auto"
        assert DEFAULT_TIERS[1].approval_mode == "one_click"
        assert DEFAULT_TIERS[2].approval_mode == "explicit"
        assert DEFAULT_TIERS[2].max_amount > DEFAULT_TIERS[1].max_amount


class TestCustomTiers:
    """Tests fuer Custom-Betragstufen."""

    @pytest.mark.asyncio
    async def test_custom_tiers_stored_and_retrieved(self) -> None:
        """Test: Custom-Tiers werden gespeichert und abgerufen."""
        # Setup
        db = AsyncMock(spec=AsyncSession)
        company_id = uuid4()

        company = MagicMock(spec=Company)
        company.filing_rules = {
            "amount_tiers": [
                {
                    "name": "Test1",
                    "max_amount": "1000.00",
                    "approval_mode": "auto",
                    "min_trust_level": "auto_accept",
                },
                {
                    "name": "Test2",
                    "max_amount": "10000.00",
                    "approval_mode": "explicit",
                    "min_trust_level": "assistance",
                },
            ]
        }

        db.execute = AsyncMock()
        db.execute.return_value.scalar_one_or_none = MagicMock(return_value=company)

        service = AmountTierService(db)

        # Execute
        tiers = await service.get_tiers(company_id)

        # Verify
        assert len(tiers) == 2
        assert tiers[0].name == "Test1"
        assert tiers[0].max_amount == Decimal("1000.00")
        assert tiers[1].name == "Test2"

    @pytest.mark.asyncio
    async def test_update_tiers_with_validation(self) -> None:
        """Test: Tiers werden mit Validierung aktualisiert."""
        # Setup
        db = AsyncMock(spec=AsyncSession)
        company_id = uuid4()

        company = MagicMock(spec=Company)
        company.filing_rules = {}

        db.execute = AsyncMock()
        db.execute.return_value.scalar_one_or_none = MagicMock(return_value=company)
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        service = AmountTierService(db)

        new_tiers = [
            AmountTier(
                name="Custom1",
                max_amount=Decimal("2000.00"),
                approval_mode="auto",
                min_trust_level="confidence",
            ),
            AmountTier(
                name="Custom2",
                max_amount=Decimal("50000.00"),
                approval_mode="explicit",
                min_trust_level="assistance",
            ),
        ]

        # Execute
        saved = await service.update_tiers(company_id, new_tiers)

        # Verify
        assert len(saved) == 2
        assert saved[0].name == "Custom1"
        db.flush.assert_called_once()
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_tiers_invalid_ordering_rejected(self) -> None:
        """Test: Aufsteigende max_amounts werden validiert."""
        # Setup
        db = AsyncMock(spec=AsyncSession)
        company_id = uuid4()

        company = MagicMock(spec=Company)
        company.filing_rules = {}

        db.execute = AsyncMock()
        db.execute.return_value.scalar_one_or_none = MagicMock(return_value=company)
        db.rollback = AsyncMock()

        service = AmountTierService(db)

        # Invalid: descending amounts
        invalid_tiers = [
            AmountTier(
                name="Tier1",
                max_amount=Decimal("5000.00"),
                approval_mode="auto",
                min_trust_level="confidence",
            ),
            AmountTier(
                name="Tier2",
                max_amount=Decimal("2000.00"),  # Descending!
                approval_mode="explicit",
                min_trust_level="assistance",
            ),
        ]

        # Execute & Verify
        with pytest.raises(ValueError, match="aufsteigend"):
            await service.update_tiers(company_id, invalid_tiers)

    @pytest.mark.asyncio
    async def test_update_tiers_minimum_two_required(self) -> None:
        """Test: Mindestens 2 Stufen erforderlich."""
        # Setup
        db = AsyncMock(spec=AsyncSession)
        company_id = uuid4()
        db.rollback = AsyncMock()

        service = AmountTierService(db)

        # Only one tier
        invalid_tiers = [
            AmountTier(
                name="Only",
                max_amount=Decimal("5000.00"),
                approval_mode="explicit",
                min_trust_level="assistance",
            ),
        ]

        # Execute & Verify
        with pytest.raises(ValueError, match="Mindestens"):
            await service.update_tiers(company_id, invalid_tiers)

    @pytest.mark.asyncio
    async def test_update_tiers_last_must_be_explicit(self) -> None:
        """Test: Letzte Stufe muss EXPLICIT sein."""
        # Setup
        db = AsyncMock(spec=AsyncSession)
        company_id = uuid4()
        db.rollback = AsyncMock()

        service = AmountTierService(db)

        # Last tier is not explicit
        invalid_tiers = [
            AmountTier(
                name="Tier1",
                max_amount=Decimal("5000.00"),
                approval_mode="auto",
                min_trust_level="confidence",
            ),
            AmountTier(
                name="Tier2",
                max_amount=Decimal("50000.00"),
                approval_mode="one_click",  # Should be explicit!
                min_trust_level="assistance",
            ),
        ]

        # Execute & Verify
        with pytest.raises(ValueError, match="Explizit"):
            await service.update_tiers(company_id, invalid_tiers)


class TestApprovalMode:
    """Tests fuer Freigabemodus-Bestimmung."""

    @pytest.mark.asyncio
    async def test_approval_mode_auto_under_500(self) -> None:
        """Test: Betrag < 500 EUR -> AUTO."""
        # Setup
        db = AsyncMock(spec=AsyncSession)
        company_id = uuid4()

        company = MagicMock(spec=Company)
        company.filing_rules = None

        db.execute = AsyncMock()
        db.execute.return_value.scalar_one_or_none = MagicMock(return_value=company)

        service = AmountTierService(db)

        # Execute
        mode = await service.get_approval_mode(company_id, Decimal("400.00"), "auto_accept")

        # Verify
        assert mode == "auto"

    @pytest.mark.asyncio
    async def test_approval_mode_one_click_500_to_5000(self) -> None:
        """Test: 500 <= Betrag <= 5000 EUR -> ONE_CLICK."""
        # Setup
        db = AsyncMock(spec=AsyncSession)
        company_id = uuid4()

        company = MagicMock(spec=Company)
        company.filing_rules = None

        db.execute = AsyncMock()
        db.execute.return_value.scalar_one_or_none = MagicMock(return_value=company)

        service = AmountTierService(db)

        # Execute
        mode = await service.get_approval_mode(company_id, Decimal("2500.00"), "confidence")

        # Verify
        assert mode == "one_click"

    @pytest.mark.asyncio
    async def test_approval_mode_explicit_over_5000(self) -> None:
        """Test: Betrag > 5000 EUR -> EXPLICIT."""
        # Setup
        db = AsyncMock(spec=AsyncSession)
        company_id = uuid4()

        company = MagicMock(spec=Company)
        company.filing_rules = None

        db.execute = AsyncMock()
        db.execute.return_value.scalar_one_or_none = MagicMock(return_value=company)

        service = AmountTierService(db)

        # Execute
        mode = await service.get_approval_mode(company_id, Decimal("10000.00"), "autonomous")

        # Verify
        assert mode == "explicit"

    @pytest.mark.asyncio
    async def test_boundary_500_exactly(self) -> None:
        """Test: Betrag = 500 EUR -> AUTO (<=)."""
        # Setup
        db = AsyncMock(spec=AsyncSession)
        company_id = uuid4()

        company = MagicMock(spec=Company)
        company.filing_rules = None

        db.execute = AsyncMock()
        db.execute.return_value.scalar_one_or_none = MagicMock(return_value=company)

        service = AmountTierService(db)

        # Execute
        mode = await service.get_approval_mode(company_id, Decimal("500.00"), "auto_accept")

        # Verify
        assert mode == "auto"

    @pytest.mark.asyncio
    async def test_boundary_5000_exactly(self) -> None:
        """Test: Betrag = 5000 EUR -> ONE_CLICK (<=)."""
        # Setup
        db = AsyncMock(spec=AsyncSession)
        company_id = uuid4()

        company = MagicMock(spec=Company)
        company.filing_rules = None

        db.execute = AsyncMock()
        db.execute.return_value.scalar_one_or_none = MagicMock(return_value=company)

        service = AmountTierService(db)

        # Execute
        mode = await service.get_approval_mode(company_id, Decimal("5000.00"), "confidence")

        # Verify
        assert mode == "one_click"

    @pytest.mark.asyncio
    async def test_trust_level_escalation(self) -> None:
        """Test: Insufficenter Trust-Level escaliert zu naechster Stufe."""
        # Setup
        db = AsyncMock(spec=AsyncSession)
        company_id = uuid4()

        company = MagicMock(spec=Company)
        company.filing_rules = None

        db.execute = AsyncMock()
        db.execute.return_value.scalar_one_or_none = MagicMock(return_value=company)

        service = AmountTierService(db)

        # Betrag 400 EUR (AUTO tier requires auto_accept)
        # but we have only 'assistance' -> escalate to one_click
        mode = await service.get_approval_mode(company_id, Decimal("400.00"), "assistance")

        # Verify
        assert mode == "one_click"  # Escalated from auto


class TestDependencyInjection:
    """Tests fuer Dependency Injection."""

    def test_get_amount_tier_service_factory(self) -> None:
        """Test: Factory function erstellt Service."""
        # Setup
        db = AsyncMock(spec=AsyncSession)

        # Execute
        service = get_amount_tier_service(db)

        # Verify
        assert isinstance(service, AmountTierService)
        assert service.db == db
