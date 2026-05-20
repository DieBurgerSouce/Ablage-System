# -*- coding: utf-8 -*-
"""
Integration Tests for PSD2 Banking Service.

Tests PSD2 consent flow, account information, balances, transactions, and payment initiation.

SECURITY NOTES:
- Uses FAKE IBANs only (DE00000000000000000000 format)
- NEVER logs PII or sensitive data
- All error messages in German
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from uuid import uuid4
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from typing import List, Dict, Any, Optional

import httpx

from app.services.banking.psd2_integration_service import (
    PSD2IntegrationService,
    PSD2Consent,
    PSD2Account,
    PSD2Balance,
    PSD2Transaction,
    PSD2PaymentRequest,
    PSD2PaymentResponse,
    ConsentScope,
    SCAMethod,
    TransactionPage,
    get_psd2_service,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_db():
    """Mock database session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def psd2_service():
    """Create PSD2 service instance for testing."""
    return PSD2IntegrationService(use_sandbox=True, timeout=30.0)


@pytest.fixture
def test_bank_code():
    """Test bank code (Deutsche Bank)."""
    return "10070000"


@pytest.fixture
def test_access_token():
    """Test OAuth2 access token."""
    return f"test_token_{uuid4().hex}"


@pytest.fixture
def test_consent_id():
    """Test consent ID."""
    return f"consent_{uuid4().hex}"


@pytest.fixture
def test_account_id():
    """Test account resource ID."""
    return f"acc_{uuid4().hex}"


@pytest.fixture
def test_payment_id():
    """Test payment ID."""
    return f"payment_{uuid4().hex}"


@pytest.fixture
def fake_iban():
    """FAKE IBAN for testing - NEVER use real IBANs."""
    return "DE00000000000000000000"


@pytest.fixture
def redirect_uri():
    """Test redirect URI."""
    return "https://example.com/callback"


# =============================================================================
# Test Consent Flow
# =============================================================================

class TestPSD2ConsentFlow:
    """Test PSD2 consent creation and management."""

    @pytest.mark.asyncio
    async def test_create_consent_success(
        self,
        psd2_service: PSD2IntegrationService,
        test_bank_code: str,
        test_access_token: str,
        redirect_uri: str,
    ):
        """Test successful consent creation."""
        consent_id = f"consent_{uuid4().hex}"
        valid_until = date.today() + timedelta(days=90)

        # Mock HTTP response
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "consentId": consent_id,
            "consentStatus": "received",
            "_links": {
                "scaRedirect": {
                    "href": "https://bank.example.com/sca"
                }
            },
            "scaStatus": "started",
        }

        with patch.object(psd2_service, "_get_client") as mock_get_client:
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            consent, error = await psd2_service.create_consent(
                bank_code=test_bank_code,
                access_token=test_access_token,
                redirect_uri=redirect_uri,
                scopes=[ConsentScope.ACCOUNTS, ConsentScope.BALANCES, ConsentScope.TRANSACTIONS],
                valid_until=valid_until,
            )

            assert consent is not None
            assert error is None
            assert consent.consent_id == consent_id
            assert consent.status == "received"
            assert consent.sca_redirect_url == "https://bank.example.com/sca"
            assert consent.sca_status == "started"
            assert len(consent.scopes) == 3

    @pytest.mark.asyncio
    async def test_get_consent_status_valid(
        self,
        psd2_service: PSD2IntegrationService,
        test_bank_code: str,
        test_access_token: str,
        test_consent_id: str,
    ):
        """Test checking consent status (valid)."""
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "consentStatus": "valid"
        }

        with patch.object(psd2_service, "_get_client") as mock_get_client:
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            status, error = await psd2_service.get_consent_status(
                bank_code=test_bank_code,
                access_token=test_access_token,
                consent_id=test_consent_id,
            )

            assert status == "valid"
            assert error is None

    @pytest.mark.asyncio
    async def test_get_consent_status_revoked(
        self,
        psd2_service: PSD2IntegrationService,
        test_bank_code: str,
        test_access_token: str,
        test_consent_id: str,
    ):
        """Test checking consent status (revoked)."""
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "consentStatus": "revokedByPsu"
        }

        with patch.object(psd2_service, "_get_client") as mock_get_client:
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            status, error = await psd2_service.get_consent_status(
                bank_code=test_bank_code,
                access_token=test_access_token,
                consent_id=test_consent_id,
            )

            assert status == "revokedByPsu"
            assert error is None

    @pytest.mark.asyncio
    async def test_consent_expired(
        self,
        psd2_service: PSD2IntegrationService,
        test_bank_code: str,
        test_access_token: str,
        test_consent_id: str,
    ):
        """Test expired consent handling."""
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "consentStatus": "expired"
        }

        with patch.object(psd2_service, "_get_client") as mock_get_client:
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            status, error = await psd2_service.get_consent_status(
                bank_code=test_bank_code,
                access_token=test_access_token,
                consent_id=test_consent_id,
            )

            assert status == "expired"
            assert error is None


# =============================================================================
# Test Account Information
# =============================================================================

class TestPSD2Accounts:
    """Test PSD2 account listing and details."""

    @pytest.mark.asyncio
    async def test_list_accounts_success(
        self,
        psd2_service: PSD2IntegrationService,
        test_bank_code: str,
        test_access_token: str,
        test_consent_id: str,
        fake_iban: str,
    ):
        """Test successful account listing."""
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "accounts": [
                {
                    "resourceId": "acc_001",
                    "iban": fake_iban,
                    "name": "Test Girokonto",
                    "product": "Girokonto",
                    "currency": "EUR",
                    "bic": "DEUTDEFF",
                    "cashAccountType": "CACC",
                    "status": "enabled",
                },
                {
                    "resourceId": "acc_002",
                    "iban": "DE11111111111111111111",
                    "name": "Test Sparkonto",
                    "product": "Sparkonto",
                    "currency": "EUR",
                    "bic": "DEUTDEFF",
                    "cashAccountType": "SVGS",
                    "status": "enabled",
                }
            ]
        }

        with patch.object(psd2_service, "_get_client") as mock_get_client:
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            accounts, error = await psd2_service.get_accounts(
                bank_code=test_bank_code,
                access_token=test_access_token,
                consent_id=test_consent_id,
            )

            assert error is None
            assert len(accounts) == 2
            assert accounts[0].resource_id == "acc_001"
            assert accounts[0].iban == fake_iban
            assert accounts[0].name == "Test Girokonto"
            assert accounts[1].product == "Sparkonto"

    @pytest.mark.asyncio
    async def test_get_account_details(
        self,
        psd2_service: PSD2IntegrationService,
        test_bank_code: str,
        test_access_token: str,
        test_consent_id: str,
        fake_iban: str,
    ):
        """Test getting single account details."""
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "accounts": [
                {
                    "resourceId": "acc_001",
                    "iban": fake_iban,
                    "name": "Test Business Account",
                    "product": "Business Current Account",
                    "currency": "EUR",
                    "bic": "DEUTDEFF",
                    "cashAccountType": "CACC",
                    "status": "enabled",
                }
            ]
        }

        with patch.object(psd2_service, "_get_client") as mock_get_client:
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            accounts, error = await psd2_service.get_accounts(
                bank_code=test_bank_code,
                access_token=test_access_token,
                consent_id=test_consent_id,
            )

            assert error is None
            assert len(accounts) == 1
            account = accounts[0]
            assert account.resource_id == "acc_001"
            assert account.iban == fake_iban
            assert account.product == "Business Current Account"

    @pytest.mark.asyncio
    async def test_account_not_found(
        self,
        psd2_service: PSD2IntegrationService,
        test_bank_code: str,
        test_access_token: str,
        test_consent_id: str,
    ):
        """Test account not found error."""
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 404
        mock_response.json.return_value = {
            "tppMessages": [
                {
                    "code": "RESOURCE_UNKNOWN",
                    "text": "Konto nicht gefunden"
                }
            ]
        }

        with patch.object(psd2_service, "_get_client") as mock_get_client:
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            accounts, error = await psd2_service.get_accounts(
                bank_code=test_bank_code,
                access_token=test_access_token,
                consent_id=test_consent_id,
            )

            assert len(accounts) == 0
            assert error == "Konto nicht gefunden"


# =============================================================================
# Test Balances
# =============================================================================

class TestPSD2Balances:
    """Test PSD2 balance retrieval."""

    @pytest.mark.asyncio
    async def test_get_balance_success(
        self,
        psd2_service: PSD2IntegrationService,
        test_bank_code: str,
        test_access_token: str,
        test_consent_id: str,
        test_account_id: str,
    ):
        """Test successful balance retrieval."""
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "balances": [
                {
                    "balanceType": "closingBooked",
                    "balanceAmount": {
                        "amount": "5000.00",
                        "currency": "EUR"
                    },
                    "referenceDate": "2026-02-13",
                    "creditLimitIncluded": False
                }
            ]
        }

        with patch.object(psd2_service, "_get_client") as mock_get_client:
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            balances, error = await psd2_service.get_balances(
                bank_code=test_bank_code,
                access_token=test_access_token,
                consent_id=test_consent_id,
                account_id=test_account_id,
            )

            assert error is None
            assert len(balances) == 1
            balance = balances[0]
            assert balance.balance_type == "closingBooked"
            assert balance.amount == Decimal("5000.00")
            assert balance.currency == "EUR"
            assert balance.reference_date == date(2026, 2, 13)

    @pytest.mark.asyncio
    async def test_multiple_balances(
        self,
        psd2_service: PSD2IntegrationService,
        test_bank_code: str,
        test_access_token: str,
        test_consent_id: str,
        test_account_id: str,
    ):
        """Test retrieving multiple balance types."""
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "balances": [
                {
                    "balanceType": "closingBooked",
                    "balanceAmount": {
                        "amount": "5000.00",
                        "currency": "EUR"
                    },
                    "referenceDate": "2026-02-13",
                },
                {
                    "balanceType": "expected",
                    "balanceAmount": {
                        "amount": "4800.00",
                        "currency": "EUR"
                    },
                    "referenceDate": "2026-02-13",
                },
                {
                    "balanceType": "authorised",
                    "balanceAmount": {
                        "amount": "10000.00",
                        "currency": "EUR"
                    },
                    "creditLimitIncluded": True,
                }
            ]
        }

        with patch.object(psd2_service, "_get_client") as mock_get_client:
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            balances, error = await psd2_service.get_balances(
                bank_code=test_bank_code,
                access_token=test_access_token,
                consent_id=test_consent_id,
                account_id=test_account_id,
            )

            assert error is None
            assert len(balances) == 3
            assert balances[0].balance_type == "closingBooked"
            assert balances[1].balance_type == "expected"
            assert balances[2].balance_type == "authorised"
            assert balances[2].credit_limit_included is True

    @pytest.mark.asyncio
    async def test_balance_error_handling(
        self,
        psd2_service: PSD2IntegrationService,
        test_bank_code: str,
        test_access_token: str,
        test_consent_id: str,
        test_account_id: str,
    ):
        """Test balance retrieval error handling."""
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 403
        mock_response.json.return_value = {
            "tppMessages": [
                {
                    "code": "CONSENT_INVALID",
                    "text": "Zustimmung ungueltig oder abgelaufen"
                }
            ]
        }

        with patch.object(psd2_service, "_get_client") as mock_get_client:
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            balances, error = await psd2_service.get_balances(
                bank_code=test_bank_code,
                access_token=test_access_token,
                consent_id=test_consent_id,
                account_id=test_account_id,
            )

            assert len(balances) == 0
            assert error == "Zustimmung ungueltig oder abgelaufen"


# =============================================================================
# Test Transactions
# =============================================================================

class TestPSD2Transactions:
    """Test PSD2 transaction retrieval."""

    @pytest.mark.asyncio
    async def test_fetch_transactions_success(
        self,
        psd2_service: PSD2IntegrationService,
        test_bank_code: str,
        test_access_token: str,
        test_consent_id: str,
        test_account_id: str,
        fake_iban: str,
    ):
        """Test successful transaction fetch."""
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "transactions": {
                "booked": [
                    {
                        "transactionId": "tx_001",
                        "bookingDate": "2026-02-10",
                        "valueDate": "2026-02-10",
                        "transactionAmount": {
                            "amount": "-150.00",
                            "currency": "EUR"
                        },
                        "creditorName": "Test Supplier GmbH",
                        "creditorAccount": {
                            "iban": "DE22222222222222222222"
                        },
                        "debtorName": "Test Customer",
                        "debtorAccount": {
                            "iban": fake_iban
                        },
                        "remittanceInformationUnstructured": "Rechnung 12345",
                    }
                ]
            },
            "_links": {}
        }

        with patch.object(psd2_service, "_get_client") as mock_get_client:
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            page, error = await psd2_service.get_transactions(
                bank_code=test_bank_code,
                access_token=test_access_token,
                consent_id=test_consent_id,
                account_id=test_account_id,
            )

            assert error is None
            assert len(page["transactions"]) == 1
            assert page["has_more"] is False
            assert page["next_page_token"] is None

            tx = page["transactions"][0]
            assert tx.transaction_id == "tx_001"
            assert tx.amount == Decimal("-150.00")
            assert tx.creditor_name == "Test Supplier GmbH"

    @pytest.mark.asyncio
    async def test_transactions_date_filter(
        self,
        psd2_service: PSD2IntegrationService,
        test_bank_code: str,
        test_access_token: str,
        test_consent_id: str,
        test_account_id: str,
    ):
        """Test transaction filtering by date range."""
        date_from = date(2026, 1, 1)
        date_to = date(2026, 1, 31)

        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "transactions": {
                "booked": [
                    {
                        "transactionId": "tx_jan_001",
                        "bookingDate": "2026-01-15",
                        "valueDate": "2026-01-15",
                        "transactionAmount": {
                            "amount": "1000.00",
                            "currency": "EUR"
                        },
                    }
                ]
            },
            "_links": {}
        }

        with patch.object(psd2_service, "_get_client") as mock_get_client:
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            page, error = await psd2_service.get_transactions(
                bank_code=test_bank_code,
                access_token=test_access_token,
                consent_id=test_consent_id,
                account_id=test_account_id,
                date_from=date_from,
                date_to=date_to,
            )

            assert error is None
            assert len(page["transactions"]) == 1
            # Verify date filter was applied in request
            call_kwargs = mock_client.get.call_args
            assert call_kwargs.kwargs["params"]["dateFrom"] == "2026-01-01"
            assert call_kwargs.kwargs["params"]["dateTo"] == "2026-01-31"

    @pytest.mark.asyncio
    async def test_transactions_pagination(
        self,
        psd2_service: PSD2IntegrationService,
        test_bank_code: str,
        test_access_token: str,
        test_consent_id: str,
        test_account_id: str,
    ):
        """Test transaction pagination."""
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "transactions": {
                "booked": [
                    {
                        "transactionId": f"tx_{i:03d}",
                        "bookingDate": "2026-02-13",
                        "valueDate": "2026-02-13",
                        "transactionAmount": {
                            "amount": "100.00",
                            "currency": "EUR"
                        },
                    }
                    for i in range(50)
                ]
            },
            "_links": {
                "next": {
                    "href": "/v1/accounts/acc_001/transactions?pageToken=token_next_page"
                }
            }
        }

        with patch.object(psd2_service, "_get_client") as mock_get_client:
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            page, error = await psd2_service.get_transactions(
                bank_code=test_bank_code,
                access_token=test_access_token,
                consent_id=test_consent_id,
                account_id=test_account_id,
            )

            assert error is None
            assert len(page["transactions"]) == 50
            assert page["has_more"] is True
            assert page["next_page_token"] == "token_next_page"

    @pytest.mark.asyncio
    async def test_transactions_empty_result(
        self,
        psd2_service: PSD2IntegrationService,
        test_bank_code: str,
        test_access_token: str,
        test_consent_id: str,
        test_account_id: str,
    ):
        """Test empty transaction result."""
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "transactions": {
                "booked": []
            },
            "_links": {}
        }

        with patch.object(psd2_service, "_get_client") as mock_get_client:
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            page, error = await psd2_service.get_transactions(
                bank_code=test_bank_code,
                access_token=test_access_token,
                consent_id=test_consent_id,
                account_id=test_account_id,
            )

            assert error is None
            assert len(page["transactions"]) == 0
            assert page["has_more"] is False


# =============================================================================
# Test Payment Initiation
# =============================================================================

class TestPSD2Payments:
    """Test PSD2 payment initiation."""

    @pytest.mark.asyncio
    async def test_initiate_payment_success(
        self,
        psd2_service: PSD2IntegrationService,
        test_bank_code: str,
        test_access_token: str,
        redirect_uri: str,
        fake_iban: str,
    ):
        """Test successful payment initiation."""
        payment_id = f"payment_{uuid4().hex}"

        payment_request = PSD2PaymentRequest(
            debtor_iban=fake_iban,
            debtor_name="Test Debtor",
            creditor_name="Test Creditor GmbH",
            creditor_iban="DE33333333333333333333",
            creditor_bic="COBADEFF",
            amount=Decimal("250.00"),
            currency="EUR",
            remittance_info="Test Payment",
        )

        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "paymentId": payment_id,
            "transactionStatus": "RCVD",
            "_links": {
                "scaRedirect": {
                    "href": "https://bank.example.com/sca/payment"
                }
            },
            "scaStatus": "started",
        }

        with patch.object(psd2_service, "_get_client") as mock_get_client:
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            payment_response, error = await psd2_service.initiate_payment(
                bank_code=test_bank_code,
                access_token=test_access_token,
                payment=payment_request,
                redirect_uri=redirect_uri,
            )

            assert error is None
            assert payment_response is not None
            assert payment_response.payment_id == payment_id
            assert payment_response.transaction_status == "RCVD"
            assert payment_response.sca_redirect_url == "https://bank.example.com/sca/payment"

    @pytest.mark.asyncio
    async def test_get_payment_status_success(
        self,
        psd2_service: PSD2IntegrationService,
        test_bank_code: str,
        test_access_token: str,
        test_payment_id: str,
    ):
        """Test getting payment status."""
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "transactionStatus": "ACSC"  # AcceptedSettlementCompleted
        }

        with patch.object(psd2_service, "_get_client") as mock_get_client:
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            status, error = await psd2_service.get_payment_status(
                bank_code=test_bank_code,
                access_token=test_access_token,
                payment_id=test_payment_id,
            )

            assert error is None
            assert status == "ACSC"

    @pytest.mark.asyncio
    async def test_payment_validation_error(
        self,
        psd2_service: PSD2IntegrationService,
        test_bank_code: str,
        test_access_token: str,
        redirect_uri: str,
        fake_iban: str,
    ):
        """Test payment validation error."""
        payment_request = PSD2PaymentRequest(
            debtor_iban=fake_iban,
            debtor_name="Test Debtor",
            creditor_name="Test Creditor",
            creditor_iban="INVALID_IBAN",
            creditor_bic=None,
            amount=Decimal("100.00"),
        )

        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "tppMessages": [
                {
                    "code": "FORMAT_ERROR",
                    "text": "Ungueltige IBAN"
                }
            ]
        }

        with patch.object(psd2_service, "_get_client") as mock_get_client:
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            payment_response, error = await psd2_service.initiate_payment(
                bank_code=test_bank_code,
                access_token=test_access_token,
                payment=payment_request,
                redirect_uri=redirect_uri,
            )

            assert payment_response is None
            assert error == "Ungueltige IBAN"

    @pytest.mark.asyncio
    async def test_payment_insufficient_funds(
        self,
        psd2_service: PSD2IntegrationService,
        test_bank_code: str,
        test_access_token: str,
        redirect_uri: str,
        fake_iban: str,
    ):
        """Test insufficient funds error."""
        payment_request = PSD2PaymentRequest(
            debtor_iban=fake_iban,
            debtor_name="Test Debtor",
            creditor_name="Test Creditor",
            creditor_iban="DE44444444444444444444",
            creditor_bic="DEUTDEFF",
            amount=Decimal("999999.00"),
        )

        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "tppMessages": [
                {
                    "code": "INSUFFICIENT_FUNDS",
                    "text": "Nicht ausreichende Deckung"
                }
            ]
        }

        with patch.object(psd2_service, "_get_client") as mock_get_client:
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            payment_response, error = await psd2_service.initiate_payment(
                bank_code=test_bank_code,
                access_token=test_access_token,
                payment=payment_request,
                redirect_uri=redirect_uri,
            )

            assert payment_response is None
            assert error == "Nicht ausreichende Deckung"


# =============================================================================
# Test Error Handling
# =============================================================================

class TestPSD2ErrorHandling:
    """Test PSD2 error parsing and handling."""

    @pytest.mark.asyncio
    async def test_api_error_parsing(
        self,
        psd2_service: PSD2IntegrationService,
        test_bank_code: str,
        test_access_token: str,
        test_consent_id: str,
    ):
        """Test parsing of PSD2 API errors."""
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "tppMessages": [
                {
                    "code": "FORMAT_ERROR",
                    "text": "Ungueltige Anfrage"
                },
                {
                    "code": "PARAMETER_INVALID",
                    "text": "Parameter fehlt"
                }
            ]
        }

        with patch.object(psd2_service, "_get_client") as mock_get_client:
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            status, error = await psd2_service.get_consent_status(
                bank_code=test_bank_code,
                access_token=test_access_token,
                consent_id=test_consent_id,
            )

            assert status is None
            assert "Ungueltige Anfrage" in error
            assert "Parameter fehlt" in error

    @pytest.mark.asyncio
    async def test_timeout_handling(
        self,
        test_bank_code: str,
        test_access_token: str,
        test_consent_id: str,
    ):
        """Test timeout error handling."""
        service = PSD2IntegrationService(use_sandbox=True, timeout=0.001)

        with patch.object(service, "_get_client") as mock_get_client:
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_get_client.return_value = mock_client

            status, error = await service.get_consent_status(
                bank_code=test_bank_code,
                access_token=test_access_token,
                consent_id=test_consent_id,
            )

            assert status is None
            assert error is not None
            # Error should be German
            assert "Status" in error or "Timeout" in error

    @pytest.mark.asyncio
    async def test_auth_expired_error(
        self,
        psd2_service: PSD2IntegrationService,
        test_bank_code: str,
        test_access_token: str,
        test_consent_id: str,
        test_account_id: str,
    ):
        """Test expired authentication handling."""
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 401
        mock_response.json.return_value = {
            "tppMessages": [
                {
                    "code": "TOKEN_INVALID",
                    "text": "Token abgelaufen"
                }
            ]
        }

        with patch.object(psd2_service, "_get_client") as mock_get_client:
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            accounts, error = await psd2_service.get_accounts(
                bank_code=test_bank_code,
                access_token=test_access_token,
                consent_id=test_consent_id,
            )

            assert len(accounts) == 0
            assert error == "Token abgelaufen"

    @pytest.mark.asyncio
    async def test_rate_limiting_error(
        self,
        psd2_service: PSD2IntegrationService,
        test_bank_code: str,
        test_access_token: str,
        test_consent_id: str,
        test_account_id: str,
    ):
        """Test rate limiting error."""
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 429
        mock_response.json.return_value = {
            "tppMessages": [
                {
                    "code": "ACCESS_EXCEEDED",
                    "text": "Zugriffslimit ueberschritten"
                }
            ]
        }

        with patch.object(psd2_service, "_get_client") as mock_get_client:
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            balances, error = await psd2_service.get_balances(
                bank_code=test_bank_code,
                access_token=test_access_token,
                consent_id=test_consent_id,
                account_id=test_account_id,
            )

            assert len(balances) == 0
            assert error == "Zugriffslimit ueberschritten"


# =============================================================================
# Test Metrics Tracking
# =============================================================================

class TestPSD2Metrics:
    """Test PSD2 Prometheus metrics tracking."""

    @pytest.mark.asyncio
    async def test_records_api_call_metrics(
        self,
        psd2_service: PSD2IntegrationService,
        test_bank_code: str,
        test_access_token: str,
        test_consent_id: str,
    ):
        """Test that API calls are tracked in metrics."""
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "accounts": []
        }

        with patch.object(psd2_service, "_get_client") as mock_get_client:
            with patch("app.services.banking.psd2_integration_service.PSD2_API_CALLS") as mock_counter:
                mock_client = AsyncMock(spec=httpx.AsyncClient)
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_get_client.return_value = mock_client

                await psd2_service.get_accounts(
                    bank_code=test_bank_code,
                    access_token=test_access_token,
                    consent_id=test_consent_id,
                )

                # Verify metric was incremented
                mock_counter.labels.assert_called_with(
                    bank_code=test_bank_code,
                    endpoint="accounts",
                    status="success"
                )
                mock_counter.labels.return_value.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_tracks_error_rates(
        self,
        psd2_service: PSD2IntegrationService,
        test_bank_code: str,
        test_access_token: str,
        test_consent_id: str,
    ):
        """Test that errors are tracked in metrics."""
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 500
        mock_response.json.return_value = {
            "message": "Internal Server Error"
        }

        with patch.object(psd2_service, "_get_client") as mock_get_client:
            with patch("app.services.banking.psd2_integration_service.PSD2_API_CALLS") as mock_counter:
                mock_client = AsyncMock(spec=httpx.AsyncClient)
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_get_client.return_value = mock_client

                await psd2_service.get_accounts(
                    bank_code=test_bank_code,
                    access_token=test_access_token,
                    consent_id=test_consent_id,
                )

                # Verify error metric was incremented
                mock_counter.labels.assert_called_with(
                    bank_code=test_bank_code,
                    endpoint="accounts",
                    status="error"
                )

    @pytest.mark.asyncio
    async def test_measures_latency(
        self,
        psd2_service: PSD2IntegrationService,
        test_bank_code: str,
        test_access_token: str,
        redirect_uri: str,
    ):
        """Test that API latency is measured."""
        consent_id = f"consent_{uuid4().hex}"

        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "consentId": consent_id,
            "consentStatus": "received",
            "_links": {},
        }

        with patch.object(psd2_service, "_get_client") as mock_get_client:
            with patch("app.services.banking.psd2_integration_service.PSD2_API_DURATION") as mock_histogram:
                mock_client = AsyncMock(spec=httpx.AsyncClient)
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_get_client.return_value = mock_client

                await psd2_service.create_consent(
                    bank_code=test_bank_code,
                    access_token=test_access_token,
                    redirect_uri=redirect_uri,
                    scopes=[ConsentScope.ACCOUNTS],
                )

                # Verify latency was observed
                mock_histogram.labels.assert_called_with(
                    bank_code=test_bank_code,
                    endpoint="consents"
                )
                # observe() should have been called with a float duration
                assert mock_histogram.labels.return_value.observe.called
