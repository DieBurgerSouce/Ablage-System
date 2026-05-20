"""Tests for Odoo ERP Connector.

Testet die Odoo-spezifische Implementierung des ERP-Connectors
mit Mock-XML-RPC-Aufrufen.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from uuid import uuid4
import xmlrpc.client

from app.services.erp.odoo_connector import OdooConnector
from app.services.erp.base_connector import (
    ERPConnectionConfig,
    ERPConnectionStatus,
    ERPSyncDirection,
    ERPSyncResult,
    ERPEntity,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def odoo_config():
    """Create a test Odoo configuration."""
    return ERPConnectionConfig(
        id=uuid4(),
        company_id=uuid4(),
        erp_type="odoo",
        name="Test Odoo",
        url="https://odoo.example.com",
        database="testdb",
        username="admin",
        api_key="secret_api_key",
        sync_direction=ERPSyncDirection.BIDIRECTIONAL,
        sync_interval_minutes=15,
        enabled_entities=[ERPEntity.CUSTOMER, ERPEntity.SUPPLIER, ERPEntity.INVOICE],
        max_requests_per_minute=60,
        batch_size=100,
    )


@pytest.fixture
def mock_common_proxy():
    """Create a mock for XML-RPC common proxy."""
    mock = MagicMock()
    mock.authenticate.return_value = 1  # UID
    mock.version.return_value = {"server_version": "17.0"}
    return mock


@pytest.fixture
def mock_models_proxy():
    """Create a mock for XML-RPC models proxy."""
    mock = MagicMock()
    return mock


@pytest.fixture
def odoo_connector(odoo_config):
    """Create an OdooConnector instance for testing."""
    return OdooConnector(odoo_config)


# =============================================================================
# Connection Tests
# =============================================================================


class TestOdooConnection:
    """Tests for Odoo connection handling."""

    @pytest.mark.asyncio
    async def test_initial_state(self, odoo_connector):
        """Test initial connector state."""
        assert odoo_connector.status == ERPConnectionStatus.DISCONNECTED
        assert odoo_connector._authenticated is False
        assert odoo_connector._uid is None

    @pytest.mark.asyncio
    async def test_connect_success(self, odoo_connector, mock_common_proxy, mock_models_proxy):
        """Test successful connection to Odoo."""
        with patch.object(xmlrpc.client, "ServerProxy") as mock_proxy:
            # First call for common, second for models
            mock_proxy.side_effect = [mock_common_proxy, mock_models_proxy]

            result = await odoo_connector.connect()

            assert result is True
            assert odoo_connector.status == ERPConnectionStatus.CONNECTED
            assert odoo_connector._authenticated is True
            assert odoo_connector._uid == 1

    @pytest.mark.asyncio
    async def test_connect_auth_failed(self, odoo_connector, mock_common_proxy, mock_models_proxy):
        """Test connection with failed authentication."""
        mock_common_proxy.authenticate.return_value = None  # Auth failed

        with patch.object(xmlrpc.client, "ServerProxy") as mock_proxy:
            mock_proxy.side_effect = [mock_common_proxy, mock_models_proxy]

            result = await odoo_connector.connect()

            assert result is False
            assert odoo_connector.status == ERPConnectionStatus.ERROR
            assert odoo_connector._authenticated is False
            assert "fehlgeschlagen" in odoo_connector.last_error.lower()

    @pytest.mark.asyncio
    async def test_connect_exception(self, odoo_connector):
        """Test connection with exception."""
        with patch.object(xmlrpc.client, "ServerProxy") as mock_proxy:
            mock_proxy.side_effect = Exception("Connection refused")

            result = await odoo_connector.connect()

            assert result is False
            assert odoo_connector.status == ERPConnectionStatus.ERROR
            assert "Connection refused" in odoo_connector.last_error

    @pytest.mark.asyncio
    async def test_disconnect(self, odoo_connector, mock_common_proxy, mock_models_proxy):
        """Test disconnection from Odoo."""
        with patch.object(xmlrpc.client, "ServerProxy") as mock_proxy:
            mock_proxy.side_effect = [mock_common_proxy, mock_models_proxy]
            await odoo_connector.connect()

        await odoo_connector.disconnect()

        assert odoo_connector.status == ERPConnectionStatus.DISCONNECTED
        assert odoo_connector._authenticated is False
        assert odoo_connector._uid is None
        assert odoo_connector._common is None
        assert odoo_connector._models is None

    @pytest.mark.asyncio
    async def test_get_version(self, odoo_connector, mock_common_proxy, mock_models_proxy):
        """Test getting Odoo version."""
        with patch.object(xmlrpc.client, "ServerProxy") as mock_proxy:
            mock_proxy.side_effect = [mock_common_proxy, mock_models_proxy]
            await odoo_connector.connect()

        version = await odoo_connector.get_version()

        assert version == "17.0"


# =============================================================================
# Customer Sync Tests
# =============================================================================


class TestOdooCustomerSync:
    """Tests for customer synchronization."""

    @pytest.mark.asyncio
    async def test_sync_customers_pull(self, odoo_connector, mock_common_proxy, mock_models_proxy):
        """Test pulling customers from Odoo."""
        # Setup mock response
        mock_customers = [
            {
                "id": 1,
                "name": "Test Customer",
                "email": "test@example.com",
                "phone": "+49123456",
                "write_date": "2024-01-01 00:00:00",
            },
            {
                "id": 2,
                "name": "Another Customer",
                "email": "another@example.com",
                "write_date": "2024-01-02 00:00:00",
            },
        ]
        mock_models_proxy.execute_kw.return_value = mock_customers

        with patch.object(xmlrpc.client, "ServerProxy") as mock_proxy:
            mock_proxy.side_effect = [mock_common_proxy, mock_models_proxy]
            await odoo_connector.connect()

            result = await odoo_connector.sync_customers(direction=ERPSyncDirection.PULL)

            assert isinstance(result, ERPSyncResult)
            assert result.entity == ERPEntity.CUSTOMER
            assert result.direction == ERPSyncDirection.PULL
            assert result.success is True
            assert result.records_synced == 2

    @pytest.mark.asyncio
    async def test_sync_customers_with_since(self, odoo_connector, mock_common_proxy, mock_models_proxy):
        """Test pulling customers with since filter."""
        mock_models_proxy.execute_kw.return_value = []

        with patch.object(xmlrpc.client, "ServerProxy") as mock_proxy:
            mock_proxy.side_effect = [mock_common_proxy, mock_models_proxy]
            await odoo_connector.connect()

            since = datetime(2024, 1, 1)
            result = await odoo_connector.sync_customers(since=since)

            assert result.success is True
            # Verify execute_kw was called (sync happened)
            assert mock_models_proxy.execute_kw.called

    @pytest.mark.asyncio
    async def test_get_customer(self, odoo_connector, mock_common_proxy, mock_models_proxy):
        """Test getting a single customer."""
        mock_customer = {
            "id": 123,
            "name": "Test Customer",
            "email": "test@example.com",
        }
        mock_models_proxy.execute_kw.return_value = [mock_customer]

        with patch.object(xmlrpc.client, "ServerProxy") as mock_proxy:
            mock_proxy.side_effect = [mock_common_proxy, mock_models_proxy]
            await odoo_connector.connect()

            customer = await odoo_connector.get_customer("123")

            assert customer is not None
            assert customer["id"] == 123
            assert customer["name"] == "Test Customer"

    @pytest.mark.asyncio
    async def test_get_customer_not_found(self, odoo_connector, mock_common_proxy, mock_models_proxy):
        """Test getting a non-existent customer."""
        mock_models_proxy.execute_kw.return_value = []

        with patch.object(xmlrpc.client, "ServerProxy") as mock_proxy:
            mock_proxy.side_effect = [mock_common_proxy, mock_models_proxy]
            await odoo_connector.connect()

            customer = await odoo_connector.get_customer("999")

            assert customer is None

    @pytest.mark.asyncio
    async def test_create_customer(self, odoo_connector, mock_common_proxy, mock_models_proxy):
        """Test creating a customer in Odoo."""
        mock_models_proxy.execute_kw.return_value = 456

        with patch.object(xmlrpc.client, "ServerProxy") as mock_proxy:
            mock_proxy.side_effect = [mock_common_proxy, mock_models_proxy]
            await odoo_connector.connect()

            customer_id = await odoo_connector.create_customer({
                "name": "New Customer",
                "email": "new@example.com",
            })

            assert customer_id == "456"

    @pytest.mark.asyncio
    async def test_update_customer(self, odoo_connector, mock_common_proxy, mock_models_proxy):
        """Test updating a customer in Odoo."""
        mock_models_proxy.execute_kw.return_value = True

        with patch.object(xmlrpc.client, "ServerProxy") as mock_proxy:
            mock_proxy.side_effect = [mock_common_proxy, mock_models_proxy]
            await odoo_connector.connect()

            result = await odoo_connector.update_customer("123", {
                "name": "Updated Customer",
            })

            assert result is True


# =============================================================================
# Supplier Sync Tests
# =============================================================================


class TestOdooSupplierSync:
    """Tests for supplier synchronization."""

    @pytest.mark.asyncio
    async def test_sync_suppliers(self, odoo_connector, mock_common_proxy, mock_models_proxy):
        """Test pulling suppliers from Odoo."""
        mock_suppliers = [
            {"id": 1, "name": "Supplier 1"},
            {"id": 2, "name": "Supplier 2"},
        ]
        mock_models_proxy.execute_kw.return_value = mock_suppliers

        with patch.object(xmlrpc.client, "ServerProxy") as mock_proxy:
            mock_proxy.side_effect = [mock_common_proxy, mock_models_proxy]
            await odoo_connector.connect()

            result = await odoo_connector.sync_suppliers()

            assert result.success is True
            assert result.entity == ERPEntity.SUPPLIER
            assert result.records_synced == 2

    @pytest.mark.asyncio
    async def test_create_supplier(self, odoo_connector, mock_common_proxy, mock_models_proxy):
        """Test creating a supplier in Odoo."""
        mock_models_proxy.execute_kw.return_value = 789

        with patch.object(xmlrpc.client, "ServerProxy") as mock_proxy:
            mock_proxy.side_effect = [mock_common_proxy, mock_models_proxy]
            await odoo_connector.connect()

            supplier_id = await odoo_connector.create_supplier({
                "name": "New Supplier",
            })

            assert supplier_id == "789"


# =============================================================================
# Invoice Sync Tests
# =============================================================================


class TestOdooInvoiceSync:
    """Tests for invoice synchronization."""

    @pytest.mark.asyncio
    async def test_sync_invoices(self, odoo_connector, mock_common_proxy, mock_models_proxy):
        """Test pulling invoices from Odoo."""
        mock_invoices = [
            {
                "id": 1,
                "name": "INV/2024/0001",
                "move_type": "out_invoice",
                "amount_total": 1000.00,
            },
        ]
        mock_models_proxy.execute_kw.return_value = mock_invoices

        with patch.object(xmlrpc.client, "ServerProxy") as mock_proxy:
            mock_proxy.side_effect = [mock_common_proxy, mock_models_proxy]
            await odoo_connector.connect()

            result = await odoo_connector.sync_invoices()

            assert result.success is True
            assert result.entity == ERPEntity.INVOICE
            assert result.records_synced == 1

    @pytest.mark.asyncio
    async def test_get_invoice(self, odoo_connector, mock_common_proxy, mock_models_proxy):
        """Test getting a single invoice."""
        mock_invoice = {
            "id": 123,
            "name": "INV/2024/0001",
            "amount_total": 500.00,
        }
        mock_models_proxy.execute_kw.return_value = [mock_invoice]

        with patch.object(xmlrpc.client, "ServerProxy") as mock_proxy:
            mock_proxy.side_effect = [mock_common_proxy, mock_models_proxy]
            await odoo_connector.connect()

            invoice = await odoo_connector.get_invoice("123")

            assert invoice is not None
            assert invoice["name"] == "INV/2024/0001"

    @pytest.mark.asyncio
    async def test_update_payment_status(self, odoo_connector, mock_common_proxy, mock_models_proxy):
        """Test updating invoice payment status."""
        with patch.object(xmlrpc.client, "ServerProxy") as mock_proxy:
            mock_proxy.side_effect = [mock_common_proxy, mock_models_proxy]
            await odoo_connector.connect()

            result = await odoo_connector.update_payment_status(
                erp_id="123",
                status="paid",
                payment_date=datetime.now(),
                amount=500.00,
            )

            assert result is True


# =============================================================================
# Document Attachment Tests
# =============================================================================


class TestOdooAttachments:
    """Tests for document attachments."""

    @pytest.mark.asyncio
    async def test_attach_document(self, odoo_connector, mock_common_proxy, mock_models_proxy):
        """Test attaching a document to an invoice."""
        mock_models_proxy.execute_kw.return_value = 999

        with patch.object(xmlrpc.client, "ServerProxy") as mock_proxy:
            mock_proxy.side_effect = [mock_common_proxy, mock_models_proxy]
            await odoo_connector.connect()

            result = await odoo_connector.attach_document(
                entity=ERPEntity.INVOICE,
                erp_id="123",
                document_data=b"PDF content here",
                filename="invoice.pdf",
                mime_type="application/pdf",
            )

            assert result is True
            # Verify execute_kw was called
            assert mock_models_proxy.execute_kw.called

    @pytest.mark.asyncio
    async def test_attach_document_unknown_entity(self, odoo_connector, mock_common_proxy, mock_models_proxy):
        """Test attaching document with unknown entity type."""
        with patch.object(xmlrpc.client, "ServerProxy") as mock_proxy:
            mock_proxy.side_effect = [mock_common_proxy, mock_models_proxy]
            await odoo_connector.connect()

            result = await odoo_connector.attach_document(
                entity=ERPEntity.PAYMENT,  # Not mapped
                erp_id="123",
                document_data=b"test",
                filename="test.pdf",
                mime_type="application/pdf",
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_get_attachments(self, odoo_connector, mock_common_proxy, mock_models_proxy):
        """Test getting attachments for an entity."""
        mock_attachments = [
            {"id": 1, "name": "doc1.pdf", "mimetype": "application/pdf"},
            {"id": 2, "name": "doc2.pdf", "mimetype": "application/pdf"},
        ]
        mock_models_proxy.execute_kw.return_value = mock_attachments

        with patch.object(xmlrpc.client, "ServerProxy") as mock_proxy:
            mock_proxy.side_effect = [mock_common_proxy, mock_models_proxy]
            await odoo_connector.connect()

            attachments = await odoo_connector.get_attachments(
                entity=ERPEntity.INVOICE,
                erp_id="123",
            )

            assert len(attachments) == 2
            assert attachments[0]["name"] == "doc1.pdf"


# =============================================================================
# Additional Odoo Methods Tests
# =============================================================================


class TestOdooAdditionalMethods:
    """Tests for additional Odoo-specific methods."""

    @pytest.mark.asyncio
    async def test_get_company_info(self, odoo_connector, mock_common_proxy, mock_models_proxy):
        """Test getting company information."""
        mock_company = {
            "id": 1,
            "name": "Test Company",
            "email": "company@example.com",
            "vat": "DE123456789",
        }
        mock_models_proxy.execute_kw.return_value = [mock_company]

        with patch.object(xmlrpc.client, "ServerProxy") as mock_proxy:
            mock_proxy.side_effect = [mock_common_proxy, mock_models_proxy]
            await odoo_connector.connect()

            company = await odoo_connector.get_company_info()

            assert company is not None
            assert company["name"] == "Test Company"
            assert company["vat"] == "DE123456789"

    @pytest.mark.asyncio
    async def test_search_partners(self, odoo_connector, mock_common_proxy, mock_models_proxy):
        """Test searching for partners."""
        mock_partners = [
            {"id": 1, "name": "Test Partner", "email": "test@example.com"},
        ]
        mock_models_proxy.execute_kw.return_value = mock_partners

        with patch.object(xmlrpc.client, "ServerProxy") as mock_proxy:
            mock_proxy.side_effect = [mock_common_proxy, mock_models_proxy]
            await odoo_connector.connect()

            partners = await odoo_connector.search_partners("test")

            assert len(partners) == 1
            assert partners[0]["name"] == "Test Partner"

    @pytest.mark.asyncio
    async def test_get_currencies(self, odoo_connector, mock_common_proxy, mock_models_proxy):
        """Test getting currencies."""
        mock_currencies = [
            {"id": 1, "name": "EUR", "symbol": "€", "rate": 1.0},
            {"id": 2, "name": "USD", "symbol": "$", "rate": 1.1},
        ]
        mock_models_proxy.execute_kw.return_value = mock_currencies

        with patch.object(xmlrpc.client, "ServerProxy") as mock_proxy:
            mock_proxy.side_effect = [mock_common_proxy, mock_models_proxy]
            await odoo_connector.connect()

            currencies = await odoo_connector.get_currencies()

            assert len(currencies) == 2
            assert currencies[0]["name"] == "EUR"
            assert currencies[1]["name"] == "USD"


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestOdooErrorHandling:
    """Tests for error handling in Odoo connector."""

    @pytest.mark.asyncio
    async def test_sync_customers_error(self, odoo_connector, mock_common_proxy, mock_models_proxy):
        """Test sync error handling."""
        mock_models_proxy.execute_kw.side_effect = Exception("API Error")

        with patch.object(xmlrpc.client, "ServerProxy") as mock_proxy:
            mock_proxy.side_effect = [mock_common_proxy, mock_models_proxy]
            await odoo_connector.connect()

            result = await odoo_connector.sync_customers()

            assert result.success is False
            assert "API Error" in result.error_message

    @pytest.mark.asyncio
    async def test_get_customer_error(self, odoo_connector, mock_common_proxy, mock_models_proxy):
        """Test get_customer error handling."""
        mock_models_proxy.execute_kw.side_effect = Exception("Read Error")

        with patch.object(xmlrpc.client, "ServerProxy") as mock_proxy:
            mock_proxy.side_effect = [mock_common_proxy, mock_models_proxy]
            await odoo_connector.connect()

            customer = await odoo_connector.get_customer("123")

            assert customer is None

    @pytest.mark.asyncio
    async def test_create_customer_error(self, odoo_connector, mock_common_proxy, mock_models_proxy):
        """Test create_customer error handling."""
        mock_models_proxy.execute_kw.side_effect = Exception("Create Error")

        with patch.object(xmlrpc.client, "ServerProxy") as mock_proxy:
            mock_proxy.side_effect = [mock_common_proxy, mock_models_proxy]
            await odoo_connector.connect()

            customer_id = await odoo_connector.create_customer({"name": "Test"})

            assert customer_id is None


# =============================================================================
# Field Mapping Tests
# =============================================================================


class TestOdooFieldMapping:
    """Tests for field mapping functionality."""

    def test_map_customer_to_odoo(self, odoo_connector):
        """Test customer field mapping to Odoo format."""
        local_customer = {
            "name": "Test Customer",
            "email": "test@example.com",
            "phone": "+49123456789",
            "mobile": "+49987654321",
            "address": {
                "street": "Test Street 1",
                "street2": "Apt 2",
                "city": "Berlin",
                "zip": "12345",
            },
            "vat_id": "DE123456789",
        }

        odoo_data = odoo_connector._map_customer_to_odoo(local_customer)

        assert odoo_data["name"] == "Test Customer"
        assert odoo_data["email"] == "test@example.com"
        assert odoo_data["phone"] == "+49123456789"
        assert odoo_data["mobile"] == "+49987654321"
        assert odoo_data["street"] == "Test Street 1"
        assert odoo_data["street2"] == "Apt 2"
        assert odoo_data["city"] == "Berlin"
        assert odoo_data["zip"] == "12345"
        assert odoo_data["vat"] == "DE123456789"
        assert odoo_data["customer_rank"] == 1

    def test_map_customer_to_odoo_minimal(self, odoo_connector):
        """Test customer mapping with minimal data."""
        local_customer = {
            "name": "Minimal Customer",
        }

        odoo_data = odoo_connector._map_customer_to_odoo(local_customer)

        assert odoo_data["name"] == "Minimal Customer"
        assert odoo_data["email"] == ""
        assert odoo_data["phone"] == ""
        assert odoo_data["customer_rank"] == 1
