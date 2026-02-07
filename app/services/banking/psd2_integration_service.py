# -*- coding: utf-8 -*-
"""
PSD2 Integration Service for OpenBanking API access.

Implements PSD2 Account Information Service (AIS) and Payment Initiation Service (PISP).

Supported Banks:
- Deutsche Bank (https://developer.db.com)
- Commerzbank (https://developer.commerzbank.com)
- ING (https://developer.ing.com)
- N26 (https://developer.n26.com)

SECURITY NOTES:
- All API credentials stored encrypted (AES-256-GCM)
- OAuth2 tokens have limited TTL
- SCA (Strong Customer Authentication) required for all operations
- Never log IBANs, account numbers, or balances
- Audit all PSD2 API calls
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any, TypedDict
from urllib.parse import urlencode, quote
from uuid import UUID, uuid4

import httpx
import structlog
from prometheus_client import Counter, Histogram

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metrics
# =============================================================================

PSD2_API_CALLS = Counter(
    "psd2_api_calls_total",
    "Total PSD2 API calls",
    ["bank_code", "endpoint", "status"]
)

PSD2_API_DURATION = Histogram(
    "psd2_api_duration_seconds",
    "PSD2 API call duration",
    ["bank_code", "endpoint"]
)

PSD2_CONSENT_CREATED = Counter(
    "psd2_consent_created_total",
    "PSD2 consents created",
    ["bank_code"]
)

PSD2_SCA_COMPLETED = Counter(
    "psd2_sca_completed_total",
    "PSD2 SCA completions",
    ["bank_code", "method"]
)


# =============================================================================
# Types
# =============================================================================

class PSD2Endpoint(str, Enum):
    """PSD2 API endpoints."""
    CONSENTS = "/v1/consents"
    CONSENTS_STATUS = "/v1/consents/{consent_id}/status"
    ACCOUNTS = "/v1/accounts"
    BALANCES = "/v1/accounts/{account_id}/balances"
    TRANSACTIONS = "/v1/accounts/{account_id}/transactions"
    PAYMENTS = "/v1/payments/sepa-credit-transfers"
    PAYMENT_STATUS = "/v1/payments/sepa-credit-transfers/{payment_id}"


class SCAMethod(str, Enum):
    """Strong Customer Authentication methods."""
    REDIRECT = "redirect"
    DECOUPLED = "decoupled"
    EMBEDDED = "embedded"


class ConsentScope(str, Enum):
    """PSD2 consent scopes."""
    ACCOUNTS = "accounts"
    BALANCES = "balances"
    TRANSACTIONS = "transactions"


@dataclass
class PSD2BankConfig:
    """Configuration for a PSD2 bank."""
    bank_code: str
    bank_name: str
    base_url: str
    sandbox_url: Optional[str] = None
    aspsp_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    certificate_path: Optional[str] = None
    private_key_path: Optional[str] = None
    sca_methods: List[SCAMethod] = field(default_factory=lambda: [SCAMethod.REDIRECT])
    requires_qwac: bool = True  # Qualified Website Authentication Certificate


@dataclass
class PSD2Consent:
    """PSD2 consent information."""
    consent_id: str
    status: str
    scopes: List[str]
    valid_until: Optional[datetime] = None
    frequency_per_day: int = 4
    recurring_indicator: bool = True
    combined_service_indicator: bool = False
    sca_redirect_url: Optional[str] = None
    sca_status: Optional[str] = None


@dataclass
class PSD2Account:
    """Account information from PSD2 API."""
    resource_id: str
    iban: str
    name: Optional[str] = None
    product: Optional[str] = None
    currency: str = "EUR"
    bic: Optional[str] = None
    cash_account_type: Optional[str] = None
    status: Optional[str] = None


@dataclass
class PSD2Balance:
    """Balance information from PSD2 API."""
    balance_type: str  # closingBooked, expected, authorised
    amount: Decimal
    currency: str
    reference_date: Optional[date] = None
    credit_limit_included: bool = False


@dataclass
class PSD2Transaction:
    """Transaction from PSD2 API."""
    transaction_id: Optional[str]
    booking_date: date
    value_date: date
    amount: Decimal
    currency: str
    creditor_name: Optional[str] = None
    creditor_iban: Optional[str] = None
    debtor_name: Optional[str] = None
    debtor_iban: Optional[str] = None
    remittance_info: Optional[str] = None
    end_to_end_id: Optional[str] = None
    mandate_id: Optional[str] = None
    creditor_id: Optional[str] = None
    bank_transaction_code: Optional[str] = None
    proprietary_bank_code: Optional[str] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PSD2PaymentRequest:
    """Payment initiation request."""
    debtor_iban: str
    debtor_name: Optional[str]
    creditor_name: str
    creditor_iban: str
    creditor_bic: Optional[str]
    amount: Decimal
    currency: str = "EUR"
    remittance_info: Optional[str] = None
    end_to_end_id: Optional[str] = None
    requested_execution_date: Optional[date] = None


@dataclass
class PSD2PaymentResponse:
    """Payment initiation response."""
    payment_id: str
    transaction_status: str
    sca_redirect_url: Optional[str] = None
    sca_status: Optional[str] = None


class TransactionPage(TypedDict):
    """Paginated transaction response."""
    transactions: List[PSD2Transaction]
    has_more: bool
    next_page_token: Optional[str]


# =============================================================================
# Bank Configurations (German Banks)
# =============================================================================

GERMAN_BANKS: Dict[str, PSD2BankConfig] = {
    # Deutsche Bank
    "10070000": PSD2BankConfig(
        bank_code="10070000",
        bank_name="Deutsche Bank",
        base_url="https://api.db.com",
        sandbox_url="https://sandbox.api.db.com",
        aspsp_id="DEUTDEFF",
        sca_methods=[SCAMethod.REDIRECT, SCAMethod.DECOUPLED],
    ),
    "50070010": PSD2BankConfig(
        bank_code="50070010",
        bank_name="Deutsche Bank Frankfurt",
        base_url="https://api.db.com",
        sandbox_url="https://sandbox.api.db.com",
        aspsp_id="DEUTDEFF",
        sca_methods=[SCAMethod.REDIRECT, SCAMethod.DECOUPLED],
    ),

    # Commerzbank
    "37040044": PSD2BankConfig(
        bank_code="37040044",
        bank_name="Commerzbank",
        base_url="https://psd2.api.commerzbank.com",
        sandbox_url="https://psd2.sandbox.commerzbank.com",
        aspsp_id="COBADEFF",
        sca_methods=[SCAMethod.REDIRECT],
    ),

    # ING
    "50010517": PSD2BankConfig(
        bank_code="50010517",
        bank_name="ING",
        base_url="https://api.ing.com",
        sandbox_url="https://sandbox.api.ing.com",
        aspsp_id="INGDDEFF",
        sca_methods=[SCAMethod.REDIRECT],
        requires_qwac=True,
    ),

    # N26
    "10019610": PSD2BankConfig(
        bank_code="10019610",
        bank_name="N26",
        base_url="https://api.n26.com",
        sandbox_url="https://sandbox.api.n26.com",
        aspsp_id="N26AG",
        sca_methods=[SCAMethod.REDIRECT],
    ),
}


# =============================================================================
# PSD2 Service
# =============================================================================

class PSD2IntegrationService:
    """
    PSD2 OpenBanking integration service.

    Provides:
    - Consent management (AIS)
    - Account information
    - Balance queries
    - Transaction history
    - Payment initiation (PISP)
    """

    def __init__(
        self,
        use_sandbox: bool = False,
        timeout: float = 30.0,
    ):
        self.use_sandbox = use_sandbox
        self.timeout = timeout
        self._http_client: Optional[httpx.AsyncClient] = None

        logger.info(
            "psd2_service_initialized",
            use_sandbox=use_sandbox,
        )

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=False,
            )
        return self._http_client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    def get_bank_config(self, bank_code: str) -> Optional[PSD2BankConfig]:
        """Get configuration for a bank."""
        return GERMAN_BANKS.get(bank_code)

    def get_supported_banks(self) -> List[PSD2BankConfig]:
        """Get list of supported PSD2 banks."""
        return list(GERMAN_BANKS.values())

    def is_bank_supported(self, bank_code: str) -> bool:
        """Check if bank supports PSD2."""
        return bank_code in GERMAN_BANKS

    # =========================================================================
    # Consent Management
    # =========================================================================

    async def create_consent(
        self,
        bank_code: str,
        access_token: str,
        redirect_uri: str,
        scopes: List[ConsentScope],
        valid_until: Optional[date] = None,
        frequency_per_day: int = 4,
        ibans: Optional[List[str]] = None,
    ) -> Tuple[Optional[PSD2Consent], Optional[str]]:
        """
        Create a new PSD2 consent.

        Args:
            bank_code: Bank's BLZ
            access_token: OAuth2 access token
            redirect_uri: Redirect URI after SCA
            scopes: Requested access scopes
            valid_until: Consent validity (default: 90 days)
            frequency_per_day: Max API calls per day
            ibans: Specific IBANs (optional, all if not specified)

        Returns:
            Tuple of (consent, error_message)
        """
        config = self.get_bank_config(bank_code)
        if not config:
            return None, f"Bank {bank_code} nicht unterstuetzt"

        if valid_until is None:
            valid_until = date.today() + timedelta(days=90)

        # Build consent request
        access_dict: Dict[str, Any] = {}
        if ibans:
            access_dict["accounts"] = [{"iban": iban} for iban in ibans]
            access_dict["balances"] = [{"iban": iban} for iban in ibans]
            access_dict["transactions"] = [{"iban": iban} for iban in ibans]
        else:
            if ConsentScope.ACCOUNTS in scopes:
                access_dict["accounts"] = []
            if ConsentScope.BALANCES in scopes:
                access_dict["balances"] = []
            if ConsentScope.TRANSACTIONS in scopes:
                access_dict["transactions"] = []

        payload = {
            "access": access_dict,
            "recurringIndicator": True,
            "validUntil": valid_until.isoformat(),
            "frequencyPerDay": frequency_per_day,
            "combinedServiceIndicator": False,
        }

        base_url = config.sandbox_url if self.use_sandbox else config.base_url
        url = f"{base_url}{PSD2Endpoint.CONSENTS.value}"

        try:
            import time
            start_time = time.time()

            client = await self._get_client()
            response = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "X-Request-ID": str(uuid4()),
                    "TPP-Redirect-URI": redirect_uri,
                    "TPP-Nok-Redirect-URI": redirect_uri + "?error=true",
                },
            )

            duration = time.time() - start_time
            PSD2_API_DURATION.labels(
                bank_code=bank_code,
                endpoint="consents",
            ).observe(duration)

            if response.status_code in (200, 201):
                data = response.json()
                consent = PSD2Consent(
                    consent_id=data.get("consentId"),
                    status=data.get("consentStatus"),
                    scopes=[s.value for s in scopes],
                    valid_until=datetime.fromisoformat(valid_until.isoformat()),
                    frequency_per_day=frequency_per_day,
                    sca_redirect_url=data.get("_links", {}).get("scaRedirect", {}).get("href"),
                    sca_status=data.get("scaStatus"),
                )

                PSD2_CONSENT_CREATED.labels(bank_code=bank_code).inc()
                PSD2_API_CALLS.labels(
                    bank_code=bank_code,
                    endpoint="consents",
                    status="success",
                ).inc()

                logger.info(
                    "psd2_consent_created",
                    bank_code=bank_code,
                    consent_id=consent.consent_id,
                    # SECURITY: Never log IBANs
                )

                return consent, None

            else:
                error_msg = self._parse_error(response)
                PSD2_API_CALLS.labels(
                    bank_code=bank_code,
                    endpoint="consents",
                    status="error",
                ).inc()

                logger.warning(
                    "psd2_consent_failed",
                    bank_code=bank_code,
                    status_code=response.status_code,
                    error=error_msg,
                )
                return None, error_msg

        except Exception as e:
            PSD2_API_CALLS.labels(
                bank_code=bank_code,
                endpoint="consents",
                status="exception",
            ).inc()

            logger.error(
                "psd2_consent_exception",
                bank_code=bank_code,
                **safe_error_log(e),
            )
            return None, safe_error_detail(e, "PSD2 Consent")

    async def get_consent_status(
        self,
        bank_code: str,
        access_token: str,
        consent_id: str,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Get consent status.

        Returns:
            Tuple of (status, error_message)
        """
        config = self.get_bank_config(bank_code)
        if not config:
            return None, f"Bank {bank_code} nicht unterstuetzt"

        base_url = config.sandbox_url if self.use_sandbox else config.base_url
        url = f"{base_url}{PSD2Endpoint.CONSENTS_STATUS.value.format(consent_id=consent_id)}"

        try:
            client = await self._get_client()
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "X-Request-ID": str(uuid4()),
                },
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("consentStatus"), None
            else:
                return None, self._parse_error(response)

        except Exception as e:
            logger.error(
                "psd2_consent_status_error",
                bank_code=bank_code,
                **safe_error_log(e),
            )
            return None, safe_error_detail(e, "PSD2 Status")

    # =========================================================================
    # Account Information
    # =========================================================================

    async def get_accounts(
        self,
        bank_code: str,
        access_token: str,
        consent_id: str,
    ) -> Tuple[List[PSD2Account], Optional[str]]:
        """
        Get list of accounts.

        Returns:
            Tuple of (accounts, error_message)
        """
        config = self.get_bank_config(bank_code)
        if not config:
            return [], f"Bank {bank_code} nicht unterstuetzt"

        base_url = config.sandbox_url if self.use_sandbox else config.base_url
        url = f"{base_url}{PSD2Endpoint.ACCOUNTS.value}"

        try:
            import time
            start_time = time.time()

            client = await self._get_client()
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Consent-ID": consent_id,
                    "X-Request-ID": str(uuid4()),
                },
            )

            duration = time.time() - start_time
            PSD2_API_DURATION.labels(
                bank_code=bank_code,
                endpoint="accounts",
            ).observe(duration)

            if response.status_code == 200:
                data = response.json()
                accounts = []

                for acc in data.get("accounts", []):
                    accounts.append(PSD2Account(
                        resource_id=acc.get("resourceId"),
                        iban=acc.get("iban"),
                        name=acc.get("name"),
                        product=acc.get("product"),
                        currency=acc.get("currency", "EUR"),
                        bic=acc.get("bic"),
                        cash_account_type=acc.get("cashAccountType"),
                        status=acc.get("status"),
                    ))

                PSD2_API_CALLS.labels(
                    bank_code=bank_code,
                    endpoint="accounts",
                    status="success",
                ).inc()

                logger.info(
                    "psd2_accounts_retrieved",
                    bank_code=bank_code,
                    account_count=len(accounts),
                )

                return accounts, None
            else:
                error_msg = self._parse_error(response)
                PSD2_API_CALLS.labels(
                    bank_code=bank_code,
                    endpoint="accounts",
                    status="error",
                ).inc()
                return [], error_msg

        except Exception as e:
            PSD2_API_CALLS.labels(
                bank_code=bank_code,
                endpoint="accounts",
                status="exception",
            ).inc()
            logger.error(
                "psd2_accounts_error",
                bank_code=bank_code,
                **safe_error_log(e),
            )
            return [], safe_error_detail(e, "PSD2 Accounts")

    async def get_balances(
        self,
        bank_code: str,
        access_token: str,
        consent_id: str,
        account_id: str,
    ) -> Tuple[List[PSD2Balance], Optional[str]]:
        """
        Get account balances.

        Returns:
            Tuple of (balances, error_message)
        """
        config = self.get_bank_config(bank_code)
        if not config:
            return [], f"Bank {bank_code} nicht unterstuetzt"

        base_url = config.sandbox_url if self.use_sandbox else config.base_url
        url = f"{base_url}{PSD2Endpoint.BALANCES.value.format(account_id=account_id)}"

        try:
            client = await self._get_client()
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Consent-ID": consent_id,
                    "X-Request-ID": str(uuid4()),
                },
            )

            if response.status_code == 200:
                data = response.json()
                balances = []

                for bal in data.get("balances", []):
                    amount_data = bal.get("balanceAmount", {})
                    balances.append(PSD2Balance(
                        balance_type=bal.get("balanceType"),
                        amount=Decimal(str(amount_data.get("amount", 0))),
                        currency=amount_data.get("currency", "EUR"),
                        reference_date=self._parse_date(bal.get("referenceDate")),
                        credit_limit_included=bal.get("creditLimitIncluded", False),
                    ))

                PSD2_API_CALLS.labels(
                    bank_code=bank_code,
                    endpoint="balances",
                    status="success",
                ).inc()

                # SECURITY: Never log balance amounts
                logger.info(
                    "psd2_balances_retrieved",
                    bank_code=bank_code,
                    balance_count=len(balances),
                )

                return balances, None
            else:
                error_msg = self._parse_error(response)
                PSD2_API_CALLS.labels(
                    bank_code=bank_code,
                    endpoint="balances",
                    status="error",
                ).inc()
                return [], error_msg

        except Exception as e:
            PSD2_API_CALLS.labels(
                bank_code=bank_code,
                endpoint="balances",
                status="exception",
            ).inc()
            logger.error(
                "psd2_balances_error",
                bank_code=bank_code,
                **safe_error_log(e),
            )
            return [], safe_error_detail(e, "PSD2 Balances")

    async def get_transactions(
        self,
        bank_code: str,
        access_token: str,
        consent_id: str,
        account_id: str,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        booking_status: str = "booked",  # booked, pending, both
        page_token: Optional[str] = None,
    ) -> Tuple[TransactionPage, Optional[str]]:
        """
        Get account transactions.

        Returns:
            Tuple of (TransactionPage, error_message)
        """
        config = self.get_bank_config(bank_code)
        if not config:
            return TransactionPage(transactions=[], has_more=False, next_page_token=None), f"Bank {bank_code} nicht unterstuetzt"

        # Default: last 90 days
        if date_from is None:
            date_from = date.today() - timedelta(days=90)
        if date_to is None:
            date_to = date.today()

        base_url = config.sandbox_url if self.use_sandbox else config.base_url
        url = f"{base_url}{PSD2Endpoint.TRANSACTIONS.value.format(account_id=account_id)}"

        params = {
            "dateFrom": date_from.isoformat(),
            "dateTo": date_to.isoformat(),
            "bookingStatus": booking_status,
        }

        if page_token:
            params["pageToken"] = page_token

        try:
            import time
            start_time = time.time()

            client = await self._get_client()
            response = await client.get(
                url,
                params=params,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Consent-ID": consent_id,
                    "X-Request-ID": str(uuid4()),
                },
            )

            duration = time.time() - start_time
            PSD2_API_DURATION.labels(
                bank_code=bank_code,
                endpoint="transactions",
            ).observe(duration)

            if response.status_code == 200:
                data = response.json()
                transactions: List[PSD2Transaction] = []

                # Parse booked transactions
                booked = data.get("transactions", {}).get("booked", [])
                for tx in booked:
                    transactions.append(self._parse_transaction(tx))

                # Check for pagination
                links = data.get("_links", {})
                next_link = links.get("next", {}).get("href")
                has_more = next_link is not None

                # Extract page token from next link
                next_page_token = None
                if next_link and "pageToken=" in next_link:
                    next_page_token = next_link.split("pageToken=")[1].split("&")[0]

                PSD2_API_CALLS.labels(
                    bank_code=bank_code,
                    endpoint="transactions",
                    status="success",
                ).inc()

                logger.info(
                    "psd2_transactions_retrieved",
                    bank_code=bank_code,
                    transaction_count=len(transactions),
                    has_more=has_more,
                )

                return TransactionPage(
                    transactions=transactions,
                    has_more=has_more,
                    next_page_token=next_page_token,
                ), None

            else:
                error_msg = self._parse_error(response)
                PSD2_API_CALLS.labels(
                    bank_code=bank_code,
                    endpoint="transactions",
                    status="error",
                ).inc()
                return TransactionPage(transactions=[], has_more=False, next_page_token=None), error_msg

        except Exception as e:
            PSD2_API_CALLS.labels(
                bank_code=bank_code,
                endpoint="transactions",
                status="exception",
            ).inc()
            logger.error(
                "psd2_transactions_error",
                bank_code=bank_code,
                **safe_error_log(e),
            )
            return TransactionPage(transactions=[], has_more=False, next_page_token=None), safe_error_detail(e, "PSD2 Transactions")

    # =========================================================================
    # Payment Initiation (PISP)
    # =========================================================================

    async def initiate_payment(
        self,
        bank_code: str,
        access_token: str,
        payment: PSD2PaymentRequest,
        redirect_uri: str,
    ) -> Tuple[Optional[PSD2PaymentResponse], Optional[str]]:
        """
        Initiate a SEPA Credit Transfer.

        Returns:
            Tuple of (payment_response, error_message)
        """
        config = self.get_bank_config(bank_code)
        if not config:
            return None, f"Bank {bank_code} nicht unterstuetzt"

        payload = {
            "debtorAccount": {
                "iban": payment.debtor_iban,
            },
            "instructedAmount": {
                "amount": str(payment.amount),
                "currency": payment.currency,
            },
            "creditorName": payment.creditor_name,
            "creditorAccount": {
                "iban": payment.creditor_iban,
            },
        }

        if payment.debtor_name:
            payload["debtorAccount"]["name"] = payment.debtor_name
        if payment.creditor_bic:
            payload["creditorAgent"] = payment.creditor_bic
        if payment.remittance_info:
            payload["remittanceInformationUnstructured"] = payment.remittance_info
        if payment.end_to_end_id:
            payload["endToEndIdentification"] = payment.end_to_end_id
        if payment.requested_execution_date:
            payload["requestedExecutionDate"] = payment.requested_execution_date.isoformat()

        base_url = config.sandbox_url if self.use_sandbox else config.base_url
        url = f"{base_url}{PSD2Endpoint.PAYMENTS.value}"

        try:
            import time
            start_time = time.time()

            client = await self._get_client()
            response = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "X-Request-ID": str(uuid4()),
                    "TPP-Redirect-URI": redirect_uri,
                    "TPP-Nok-Redirect-URI": redirect_uri + "?error=true",
                },
            )

            duration = time.time() - start_time
            PSD2_API_DURATION.labels(
                bank_code=bank_code,
                endpoint="payments",
            ).observe(duration)

            if response.status_code in (200, 201):
                data = response.json()
                payment_response = PSD2PaymentResponse(
                    payment_id=data.get("paymentId"),
                    transaction_status=data.get("transactionStatus"),
                    sca_redirect_url=data.get("_links", {}).get("scaRedirect", {}).get("href"),
                    sca_status=data.get("scaStatus"),
                )

                PSD2_API_CALLS.labels(
                    bank_code=bank_code,
                    endpoint="payments",
                    status="success",
                ).inc()

                logger.info(
                    "psd2_payment_initiated",
                    bank_code=bank_code,
                    payment_id=payment_response.payment_id,
                    status=payment_response.transaction_status,
                    # SECURITY: Never log amounts or IBANs
                )

                return payment_response, None

            else:
                error_msg = self._parse_error(response)
                PSD2_API_CALLS.labels(
                    bank_code=bank_code,
                    endpoint="payments",
                    status="error",
                ).inc()

                logger.warning(
                    "psd2_payment_failed",
                    bank_code=bank_code,
                    status_code=response.status_code,
                    error=error_msg,
                )
                return None, error_msg

        except Exception as e:
            PSD2_API_CALLS.labels(
                bank_code=bank_code,
                endpoint="payments",
                status="exception",
            ).inc()
            logger.error(
                "psd2_payment_exception",
                bank_code=bank_code,
                **safe_error_log(e),
            )
            return None, safe_error_detail(e, "PSD2 Payment")

    async def get_payment_status(
        self,
        bank_code: str,
        access_token: str,
        payment_id: str,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Get payment status.

        Returns:
            Tuple of (status, error_message)
        """
        config = self.get_bank_config(bank_code)
        if not config:
            return None, f"Bank {bank_code} nicht unterstuetzt"

        base_url = config.sandbox_url if self.use_sandbox else config.base_url
        url = f"{base_url}{PSD2Endpoint.PAYMENT_STATUS.value.format(payment_id=payment_id)}"

        try:
            client = await self._get_client()
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "X-Request-ID": str(uuid4()),
                },
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("transactionStatus"), None
            else:
                return None, self._parse_error(response)

        except Exception as e:
            logger.error(
                "psd2_payment_status_error",
                bank_code=bank_code,
                **safe_error_log(e),
            )
            return None, safe_error_detail(e, "PSD2 Payment Status")

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _parse_error(self, response: httpx.Response) -> str:
        """Parse error from PSD2 response."""
        try:
            data = response.json()
            messages = []

            # Standard PSD2 error format
            if "tppMessages" in data:
                for msg in data["tppMessages"]:
                    messages.append(msg.get("text", msg.get("code", "Unbekannter Fehler")))
            elif "message" in data:
                messages.append(data["message"])
            elif "error_description" in data:
                messages.append(data["error_description"])

            return "; ".join(messages) if messages else f"HTTP {response.status_code}"

        except Exception:
            logger.exception(
                "psd2_error_response_parse_failed",
                status_code=response.status_code,
            )
            return f"HTTP {response.status_code}"

    def _parse_date(self, date_str: Optional[str]) -> Optional[date]:
        """Parse date string."""
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
        except (ValueError, AttributeError):
            return None

    def _parse_transaction(self, tx: Dict[str, Any]) -> PSD2Transaction:
        """Parse transaction from PSD2 response."""
        amount_data = tx.get("transactionAmount", {})
        amount = Decimal(str(amount_data.get("amount", 0)))

        creditor_acc = tx.get("creditorAccount", {})
        debtor_acc = tx.get("debtorAccount", {})

        return PSD2Transaction(
            transaction_id=tx.get("transactionId") or tx.get("entryReference"),
            booking_date=self._parse_date(tx.get("bookingDate")) or date.today(),
            value_date=self._parse_date(tx.get("valueDate")) or date.today(),
            amount=amount,
            currency=amount_data.get("currency", "EUR"),
            creditor_name=tx.get("creditorName"),
            creditor_iban=creditor_acc.get("iban"),
            debtor_name=tx.get("debtorName"),
            debtor_iban=debtor_acc.get("iban"),
            remittance_info=tx.get("remittanceInformationUnstructured"),
            end_to_end_id=tx.get("endToEndId"),
            mandate_id=tx.get("mandateId"),
            creditor_id=tx.get("creditorId"),
            bank_transaction_code=tx.get("bankTransactionCode"),
            proprietary_bank_code=tx.get("proprietaryBankTransactionCode"),
            raw_data=tx,
        )


# =============================================================================
# Factory
# =============================================================================

_service_instance: Optional[PSD2IntegrationService] = None


def get_psd2_service(use_sandbox: bool = False) -> PSD2IntegrationService:
    """Get PSD2 integration service instance."""
    global _service_instance

    if _service_instance is None:
        _service_instance = PSD2IntegrationService(use_sandbox=use_sandbox)

    return _service_instance
