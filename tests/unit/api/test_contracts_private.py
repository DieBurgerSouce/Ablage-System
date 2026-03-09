# -*- coding: utf-8 -*-
"""
Unit Tests fuer Private Contract Management API Endpoints.

Testet:
- POST /privat/spaces/{space_id}/contracts (Vertrag erstellen)
- GET  /privat/spaces/{space_id}/contracts (Vertraege auflisten)
- GET  /privat/contracts/{contract_id} (Vertragsdetails)
- PUT  /privat/contracts/{contract_id} (Vertrag aktualisieren)
- DELETE /privat/contracts/{contract_id} (Vertrag loeschen)
- GET  /privat/spaces/{space_id}/contracts/expiring (Ablaufende Vertraege)
- POST /privat/contracts/{contract_id}/remind (Erinnerungen setzen)
- GET  /privat/spaces/{space_id}/contracts/costs (Kostenuebersicht)
"""

import sys
import pytest
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch

from starlette.requests import Request
from starlette.datastructures import Headers

pytestmark = [pytest.mark.unit, pytest.mark.api]


# Mock jinja2 before contracts_private can be imported
if "jinja2" not in sys.modules:
    sys.modules["jinja2"] = MagicMock()


# =============================================================================
# Fixtures
# =============================================================================


def _make_request(path: str = "/api/v1/privat/contracts", method: str = "GET") -> Request:
    """Erstellt ein echtes Starlette Request-Objekt fuer Rate-Limiter-Kompatibilitaet."""
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": Headers({}).raw,
        "query_string": b"",
        "root_path": "",
        "client": ("127.0.0.1", 12345),
    }
    request = Request(scope)
    request.state.view_rate_limit = None
    request.state._rate_limiting_complete = True
    return request


@pytest.fixture(autouse=True)
def _bypass_rate_limiter():
    """Bypass Rate-Limiter fuer alle Tests."""
    with patch(
        "app.core.rate_limiting.limiter._check_request_limit",
        new_callable=AsyncMock,
    ) as mock_check:
        mock_check.return_value = None
        yield mock_check


@pytest.fixture
def mock_db():
    """Mock AsyncSession."""
    db = AsyncMock()
    db.commit = AsyncMock()
    db.get = AsyncMock()
    return db


@pytest.fixture
def mock_user():
    """Mock authentifizierter Benutzer."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "privat@ablage.local"
    user.is_active = True
    return user


@pytest.fixture
def space_id():
    """Test Space-ID."""
    return uuid.uuid4()


@pytest.fixture
def mock_contract():
    """Mock Contract-Objekt."""
    contract = MagicMock()
    contract.id = uuid.uuid4()
    contract.space_id = uuid.uuid4()
    contract.title = "Handyvertrag Telekom"
    contract.partner_name = "Deutsche Telekom AG"
    contract.contract_number = "TK-2026-001"
    contract.category = "telekommunikation"
    contract.status = "active"
    contract.description = "Mobilfunkvertrag"
    contract.start_date = date(2026, 1, 1)
    contract.end_date = date(2028, 1, 1)
    contract.duration_months = 24
    contract.cancellation_notice_days = 90
    contract.next_cancellation_date = date(2027, 10, 1)
    contract.auto_renewal = True
    contract.renewal_period_months = 12
    contract.monthly_cost = Decimal("39.99")
    contract.yearly_cost = Decimal("479.88")
    contract.currency = "EUR"
    contract.document_id = None
    contract.extraction_confidence = None
    contract.notes = None
    contract.tags = ["mobilfunk", "telekom"]
    contract.created_at = datetime.now(timezone.utc)
    contract.updated_at = datetime.now(timezone.utc)
    return contract


# =============================================================================
# Contract CRUD Tests
# =============================================================================


class TestCreateContract:
    """Tests fuer POST /privat/spaces/{space_id}/contracts."""

    @pytest.mark.asyncio
    async def test_create_contract_success(self, mock_db, mock_user, mock_contract, space_id):
        """Vertrag wird erfolgreich erstellt."""
        with patch(
            "app.api.v1.contracts_private._get_space_or_404",
            new_callable=AsyncMock,
        ) as mock_space_check, patch(
            "app.api.v1.contracts_private.get_contract_management_service"
        ) as mock_get_service:
            mock_space_check.return_value = MagicMock()
            mock_service = MagicMock()
            mock_service.create_contract = AsyncMock(return_value=mock_contract)
            mock_service.schedule_reminders = AsyncMock()
            mock_get_service.return_value = mock_service

            from app.api.v1.contracts_private import create_contract, PrivatContractCreate

            data = PrivatContractCreate(
                title="Handyvertrag",
                partner_name="Telekom",
                category="telekommunikation",
            )

            result = await create_contract(
                request=_make_request("/api/v1/privat/spaces/x/contracts", "POST"),
                space_id=space_id,
                data=data,
                db=mock_db,
                current_user=mock_user,
            )

            assert result.title == "Handyvertrag Telekom"
            assert result.partner_name == "Deutsche Telekom AG"
            mock_service.create_contract.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_contract_space_not_found(self, mock_db, mock_user, space_id):
        """404 wenn Space nicht gefunden."""
        from fastapi import HTTPException

        with patch(
            "app.api.v1.contracts_private._get_space_or_404",
            new_callable=AsyncMock,
            side_effect=HTTPException(status_code=404, detail="Space nicht gefunden"),
        ):
            from app.api.v1.contracts_private import create_contract, PrivatContractCreate

            data = PrivatContractCreate(
                title="Test",
                partner_name="Partner",
            )

            with pytest.raises(HTTPException) as exc_info:
                await create_contract(
                    request=_make_request("/api/v1/privat/spaces/x/contracts", "POST"),
                    space_id=space_id,
                    data=data,
                    db=mock_db,
                    current_user=mock_user,
                )
            assert exc_info.value.status_code == 404


class TestListContracts:
    """Tests fuer GET /privat/spaces/{space_id}/contracts."""

    @pytest.mark.asyncio
    async def test_list_contracts_success(self, mock_db, mock_user, mock_contract, space_id):
        """Vertraege werden paginiert zurueckgegeben."""
        with patch(
            "app.api.v1.contracts_private._get_space_or_404",
            new_callable=AsyncMock,
        ), patch(
            "app.api.v1.contracts_private.get_contract_management_service"
        ) as mock_get_service:
            mock_service = MagicMock()
            mock_service.list_contracts = AsyncMock(
                return_value=([mock_contract], 1)
            )
            mock_get_service.return_value = mock_service

            from app.api.v1.contracts_private import list_contracts

            result = await list_contracts(
                request=_make_request("/api/v1/privat/spaces/x/contracts"),
                space_id=space_id,
                category=None,
                status_filter=None,
                expiring_within_days=None,
                page=1,
                page_size=50,
                db=mock_db,
                current_user=mock_user,
            )

            assert result.total == 1
            assert len(result.items) == 1
            assert result.page == 1
            assert result.page_size == 50

    @pytest.mark.asyncio
    async def test_list_contracts_empty(self, mock_db, mock_user, space_id):
        """Leere Liste wenn keine Vertraege vorhanden."""
        with patch(
            "app.api.v1.contracts_private._get_space_or_404",
            new_callable=AsyncMock,
        ), patch(
            "app.api.v1.contracts_private.get_contract_management_service"
        ) as mock_get_service:
            mock_service = MagicMock()
            mock_service.list_contracts = AsyncMock(return_value=([], 0))
            mock_get_service.return_value = mock_service

            from app.api.v1.contracts_private import list_contracts

            result = await list_contracts(
                request=_make_request("/api/v1/privat/spaces/x/contracts"),
                space_id=space_id,
                category=None,
                status_filter=None,
                expiring_within_days=None,
                page=1,
                page_size=50,
                db=mock_db,
                current_user=mock_user,
            )

            assert result.total == 0
            assert result.items == []


class TestGetContract:
    """Tests fuer GET /privat/contracts/{contract_id}."""

    @pytest.mark.asyncio
    async def test_get_contract_success(self, mock_db, mock_user, mock_contract):
        """Vertragsdetails werden korrekt zurueckgegeben."""
        with patch(
            "app.api.v1.contracts_private._get_space_or_404",
            new_callable=AsyncMock,
        ), patch(
            "app.api.v1.contracts_private.get_contract_management_service"
        ) as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_by_id = AsyncMock(return_value=mock_contract)
            mock_get_service.return_value = mock_service

            from app.api.v1.contracts_private import get_contract

            result = await get_contract(
                request=_make_request("/api/v1/privat/contracts/x"),
                contract_id=mock_contract.id,
                db=mock_db,
                current_user=mock_user,
            )

            assert result.title == "Handyvertrag Telekom"
            assert result.days_until_cancellation is not None

    @pytest.mark.asyncio
    async def test_get_contract_not_found(self, mock_db, mock_user):
        """404 wenn Vertrag nicht gefunden."""
        from fastapi import HTTPException

        with patch(
            "app.api.v1.contracts_private.get_contract_management_service"
        ) as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_by_id = AsyncMock(return_value=None)
            mock_get_service.return_value = mock_service

            from app.api.v1.contracts_private import get_contract

            with pytest.raises(HTTPException) as exc_info:
                await get_contract(
                    request=_make_request("/api/v1/privat/contracts/x"),
                    contract_id=uuid.uuid4(),
                    db=mock_db,
                    current_user=mock_user,
                )
            assert exc_info.value.status_code == 404
            assert "Vertrag nicht gefunden" in exc_info.value.detail


class TestUpdateContract:
    """Tests fuer PUT /privat/contracts/{contract_id}."""

    @pytest.mark.asyncio
    async def test_update_contract_success(self, mock_db, mock_user, mock_contract):
        """Vertrag wird erfolgreich aktualisiert."""
        with patch(
            "app.api.v1.contracts_private._get_space_or_404",
            new_callable=AsyncMock,
        ), patch(
            "app.api.v1.contracts_private.get_contract_management_service"
        ) as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_by_id = AsyncMock(return_value=mock_contract)
            mock_service.update_contract = AsyncMock(return_value=mock_contract)
            mock_service.schedule_reminders = AsyncMock()
            mock_get_service.return_value = mock_service

            from app.api.v1.contracts_private import update_contract, PrivatContractUpdate

            data = PrivatContractUpdate(title="Neuer Titel")

            result = await update_contract(
                request=_make_request("/api/v1/privat/contracts/x", "PUT"),
                contract_id=mock_contract.id,
                data=data,
                db=mock_db,
                current_user=mock_user,
            )

            assert result.title == "Handyvertrag Telekom"
            mock_service.update_contract.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_contract_not_found(self, mock_db, mock_user):
        """404 wenn Vertrag zum Aktualisieren nicht gefunden."""
        from fastapi import HTTPException

        with patch(
            "app.api.v1.contracts_private.get_contract_management_service"
        ) as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_by_id = AsyncMock(return_value=None)
            mock_get_service.return_value = mock_service

            from app.api.v1.contracts_private import update_contract, PrivatContractUpdate

            data = PrivatContractUpdate(title="Neuer Titel")

            with pytest.raises(HTTPException) as exc_info:
                await update_contract(
                    request=_make_request("/api/v1/privat/contracts/x", "PUT"),
                    contract_id=uuid.uuid4(),
                    data=data,
                    db=mock_db,
                    current_user=mock_user,
                )
            assert exc_info.value.status_code == 404


class TestDeleteContract:
    """Tests fuer DELETE /privat/contracts/{contract_id}."""

    @pytest.mark.asyncio
    async def test_delete_contract_success(self, mock_db, mock_user, mock_contract):
        """Vertrag wird erfolgreich geloescht."""
        with patch(
            "app.api.v1.contracts_private._get_space_or_404",
            new_callable=AsyncMock,
        ), patch(
            "app.api.v1.contracts_private.get_contract_management_service"
        ) as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_by_id = AsyncMock(return_value=mock_contract)
            mock_service.delete_contract = AsyncMock(return_value=True)
            mock_get_service.return_value = mock_service

            from app.api.v1.contracts_private import delete_contract

            result = await delete_contract(
                request=_make_request("/api/v1/privat/contracts/x", "DELETE"),
                contract_id=mock_contract.id,
                db=mock_db,
                current_user=mock_user,
            )

            assert result is None
            mock_service.delete_contract.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_contract_not_found(self, mock_db, mock_user):
        """404 wenn Vertrag zum Loeschen nicht gefunden."""
        from fastapi import HTTPException

        with patch(
            "app.api.v1.contracts_private.get_contract_management_service"
        ) as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_by_id = AsyncMock(return_value=None)
            mock_get_service.return_value = mock_service

            from app.api.v1.contracts_private import delete_contract

            with pytest.raises(HTTPException) as exc_info:
                await delete_contract(
                    request=_make_request("/api/v1/privat/contracts/x", "DELETE"),
                    contract_id=uuid.uuid4(),
                    db=mock_db,
                    current_user=mock_user,
                )
            assert exc_info.value.status_code == 404


# =============================================================================
# Expiring Contracts & Costs
# =============================================================================


class TestExpiringContracts:
    """Tests fuer GET /privat/spaces/{space_id}/contracts/expiring."""

    @pytest.mark.asyncio
    async def test_expiring_contracts_success(self, mock_db, mock_user, mock_contract, space_id):
        """Ablaufende Vertraege werden zurueckgegeben."""
        with patch(
            "app.api.v1.contracts_private._get_space_or_404",
            new_callable=AsyncMock,
        ), patch(
            "app.api.v1.contracts_private.get_contract_management_service"
        ) as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_expiring_contracts = AsyncMock(
                return_value=[mock_contract]
            )
            mock_get_service.return_value = mock_service

            from app.api.v1.contracts_private import get_expiring_contracts

            result = await get_expiring_contracts(
                request=_make_request("/api/v1/privat/spaces/x/contracts/expiring"),
                space_id=space_id,
                days=90,
                db=mock_db,
                current_user=mock_user,
            )

            assert len(result) == 1


class TestContractCosts:
    """Tests fuer GET /privat/spaces/{space_id}/contracts/costs."""

    @pytest.mark.asyncio
    async def test_get_contract_costs_success(self, mock_db, mock_user, space_id):
        """Kostenuebersicht wird korrekt berechnet."""
        with patch(
            "app.api.v1.contracts_private._get_space_or_404",
            new_callable=AsyncMock,
        ), patch(
            "app.api.v1.contracts_private.get_contract_management_service"
        ) as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_contract_cost_summary = AsyncMock(
                return_value={
                    "monthly_total": Decimal("89.98"),
                    "yearly_total": Decimal("1079.76"),
                    "by_category": {
                        "telekommunikation": Decimal("39.99"),
                        "versicherung": Decimal("49.99"),
                    },
                }
            )
            mock_get_service.return_value = mock_service

            from app.api.v1.contracts_private import get_contract_costs

            result = await get_contract_costs(
                request=_make_request("/api/v1/privat/spaces/x/contracts/costs"),
                space_id=space_id,
                db=mock_db,
                current_user=mock_user,
            )

            assert result.monthly_total == Decimal("89.98")
            assert result.yearly_total == Decimal("1079.76")
            assert "telekommunikation" in result.by_category


# =============================================================================
# Schema Validation Tests
# =============================================================================


class TestContractSchemas:
    """Tests fuer Pydantic-Schema-Validierung."""

    def test_create_request_valid(self):
        """Gueltiger PrivatContractCreate."""
        from app.api.v1.contracts_private import PrivatContractCreate

        req = PrivatContractCreate(
            title="Mietvertrag",
            partner_name="Immobilien GmbH",
            monthly_cost=Decimal("850.00"),
        )
        assert req.title == "Mietvertrag"
        assert req.auto_renewal is False

    def test_create_request_empty_title(self):
        """Leerer Titel wird abgelehnt."""
        from pydantic import ValidationError
        from app.api.v1.contracts_private import PrivatContractCreate

        with pytest.raises(ValidationError):
            PrivatContractCreate(title="", partner_name="Partner")

    def test_update_request_partial(self):
        """PrivatContractUpdate erlaubt partielle Updates."""
        from app.api.v1.contracts_private import PrivatContractUpdate

        req = PrivatContractUpdate(title="Neuer Titel")
        dumped = req.model_dump(exclude_unset=True)
        assert dumped == {"title": "Neuer Titel"}

    def test_create_request_negative_cost(self):
        """Negative Kosten werden abgelehnt."""
        from pydantic import ValidationError
        from app.api.v1.contracts_private import PrivatContractCreate

        with pytest.raises(ValidationError):
            PrivatContractCreate(
                title="Test",
                partner_name="Partner",
                monthly_cost=Decimal("-10.00"),
            )
