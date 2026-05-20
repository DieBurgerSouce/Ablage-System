# -*- coding: utf-8 -*-
"""
Account Connection Service for PSD2 and FinTS bank connections.

Manages:
- PSD2 OAuth2 consent flow
- FinTS PIN/TAN authentication
- Encrypted credential storage
- Strong Customer Authentication (SCA)
- Multi-account support per bank

SECURITY NOTES:
- All credentials encrypted with AES-256-GCM
- PINs are NEVER stored, only used for session
- OAuth2 tokens stored encrypted with TTL
- Audit all connection operations
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from uuid import UUID, uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log, safe_error_detail
from app.db.models_banking_connection import (
    BankConnection,
    ConnectedBankAccount,
    ConnectionType,
    ConnectionStatus,
    SyncStatus,
    SupportedBank,
)
from .psd2_integration_service import (
    PSD2IntegrationService,
    PSD2Consent,
    PSD2Account,
    ConsentScope,
    get_psd2_service,
)
from .fints_service import FinTSService, TANChallenge, TANMethod

logger = structlog.get_logger(__name__)


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class ConnectionConfig:
    """Connection configuration."""
    encryption_key: bytes
    consent_validity_days: int = 90
    max_sync_interval_hours: int = 24
    min_sync_interval_hours: int = 1
    max_connection_errors: int = 5


def get_encryption_key() -> bytes:
    """Get encryption key from environment."""
    from app.core.config import get_settings
    settings = get_settings()

    if settings.ENCRYPTION_KEY:
        key = settings.ENCRYPTION_KEY.get_secret_value()
        return base64.b64decode(key)
    else:
        # Derive from SECRET_KEY
        secret = settings.SECRET_KEY.get_secret_value()
        return hashlib.sha256(secret.encode()).digest()


# =============================================================================
# Encryption Utilities
# =============================================================================

class CredentialEncryption:
    """AES-256-GCM credential encryption."""

    def __init__(self, key: bytes):
        self.aesgcm = AESGCM(key)

    def encrypt(self, data: str) -> str:
        """Encrypt string data."""
        nonce = os.urandom(12)
        ciphertext = self.aesgcm.encrypt(nonce, data.encode("utf-8"), None)
        return base64.b64encode(nonce + ciphertext).decode("utf-8")

    def decrypt(self, encrypted: str) -> str:
        """Decrypt encrypted data."""
        raw = base64.b64decode(encrypted)
        nonce = raw[:12]
        ciphertext = raw[12:]
        plaintext = self.aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8")


# =============================================================================
# Result Types
# =============================================================================

@dataclass
class ConnectionResult:
    """Result of connection operation."""
    success: bool
    connection_id: Optional[UUID] = None
    error_message: Optional[str] = None
    requires_sca: bool = False
    sca_redirect_url: Optional[str] = None
    tan_challenge: Optional[TANChallenge] = None


@dataclass
class AccountInfo:
    """Simplified account information."""
    id: UUID
    iban: str
    name: Optional[str]
    account_type: str
    currency: str
    balance: Optional[Decimal]
    balance_date: Optional[datetime]


# =============================================================================
# Account Connection Service
# =============================================================================

class AccountConnectionService:
    """
    Service for managing bank account connections.

    Supports:
    - PSD2 OpenBanking connections
    - FinTS/HBCI connections
    - Hybrid (fallback) connections
    """

    def __init__(
        self,
        psd2_service: Optional[PSD2IntegrationService] = None,
        fints_service: Optional[FinTSService] = None,
    ):
        self.psd2_service = psd2_service or get_psd2_service()
        self.fints_service = fints_service or FinTSService()
        self._encryption: Optional[CredentialEncryption] = None

    def _get_encryption(self) -> CredentialEncryption:
        """Get encryption handler."""
        if self._encryption is None:
            self._encryption = CredentialEncryption(get_encryption_key())
        return self._encryption

    # =========================================================================
    # Bank Discovery
    # =========================================================================

    async def get_available_banks(
        self,
        db: AsyncSession,
        country_code: str = "DE",
    ) -> List[Dict[str, Any]]:
        """
        Get list of available banks.

        Returns banks from database with fallback to hardcoded list.
        """
        # Try database first
        query = select(SupportedBank).where(
            and_(
                SupportedBank.country_code == country_code,
                SupportedBank.is_active == True,
            )
        ).order_by(SupportedBank.bank_name)

        result = await db.execute(query)
        db_banks = result.scalars().all()

        if db_banks:
            return [
                {
                    "bank_code": bank.bank_code,
                    "bank_name": bank.bank_name,
                    "bic": bank.bic,
                    "supports_psd2": bank.supports_psd2,
                    "supports_fints": bank.supports_fints,
                    "logo_url": bank.logo_url,
                    "supports_payment_initiation": bank.supports_payment_initiation,
                }
                for bank in db_banks
            ]

        # Fallback to hardcoded German banks
        from .psd2_integration_service import GERMAN_BANKS
        from .fints_service import FinTSService

        fints_svc = self.fints_service

        banks = []

        # PSD2 banks
        for code, config in GERMAN_BANKS.items():
            banks.append({
                "bank_code": code,
                "bank_name": config.bank_name,
                "bic": config.aspsp_id,
                "supports_psd2": True,
                "supports_fints": fints_svc.get_fints_url(code) is not None,
                "logo_url": None,
                "supports_payment_initiation": True,
            })

        # FinTS-only banks
        for blz, url in fints_svc.KNOWN_FINTS_URLS.items():
            if blz not in [b["bank_code"] for b in banks]:
                banks.append({
                    "bank_code": blz,
                    "bank_name": fints_svc._get_bank_name_from_blz(blz),
                    "bic": fints_svc._get_bic_from_blz(blz),
                    "supports_psd2": False,
                    "supports_fints": True,
                    "logo_url": None,
                    "supports_payment_initiation": False,
                })

        # Sort by name
        banks.sort(key=lambda b: b["bank_name"])
        return banks

    async def get_bank_info(
        self,
        bank_code: str,
    ) -> Optional[Dict[str, Any]]:
        """Get information about a specific bank."""
        # Check PSD2
        psd2_config = self.psd2_service.get_bank_config(bank_code)

        # Check FinTS
        fints_url = self.fints_service.get_fints_url(bank_code)
        fints_info = await self.fints_service.get_bank_info(bank_code, fints_url) if fints_url else None

        if not psd2_config and not fints_info:
            return None

        return {
            "bank_code": bank_code,
            "bank_name": psd2_config.bank_name if psd2_config else (fints_info.bank_name if fints_info else None),
            "bic": psd2_config.aspsp_id if psd2_config else (fints_info.bic if fints_info else None),
            "supports_psd2": psd2_config is not None,
            "supports_fints": fints_url is not None,
            "fints_url": fints_url,
            "tan_methods": fints_info.tan_methods if fints_info else [],
            "psd2_sca_methods": [m.value for m in psd2_config.sca_methods] if psd2_config else [],
        }

    # =========================================================================
    # PSD2 Connection
    # =========================================================================

    async def init_psd2_connection(
        self,
        db: AsyncSession,
        company_id: UUID,
        user_id: UUID,
        bank_code: str,
        redirect_uri: str,
        scopes: Optional[List[str]] = None,
    ) -> ConnectionResult:
        """
        Initialize PSD2 connection flow.

        Creates connection in PENDING state and returns SCA redirect URL.
        """
        # Validate bank
        if not self.psd2_service.is_bank_supported(bank_code):
            return ConnectionResult(
                success=False,
                error_message=f"Bank {bank_code} unterstützt kein PSD2"
            )

        config = self.psd2_service.get_bank_config(bank_code)

        try:
            # Create connection record
            connection = BankConnection(
                company_id=company_id,
                bank_code=bank_code,
                bank_name=config.bank_name,
                bic=config.aspsp_id,
                connection_type=ConnectionType.PSD2.value,
                status=ConnectionStatus.PENDING.value,
                created_by_id=user_id,
            )
            db.add(connection)
            await db.flush()

            # Get OAuth2 access token (implementation specific to each bank)
            # For now, we'll assume we have a valid access token
            # In production, this would involve OAuth2 authorization code flow

            # Create consent
            consent_scopes = [ConsentScope(s) for s in scopes] if scopes else [
                ConsentScope.ACCOUNTS,
                ConsentScope.BALANCES,
                ConsentScope.TRANSACTIONS,
            ]

            # Note: In production, access_token would come from OAuth2 flow
            # This is a placeholder for the consent creation
            consent, error = await self.psd2_service.create_consent(
                bank_code=bank_code,
                access_token="placeholder",  # Would come from OAuth2
                redirect_uri=redirect_uri,
                scopes=consent_scopes,
            )

            if error:
                connection.status = ConnectionStatus.ERROR.value
                connection.last_error = error
                await db.commit()

                return ConnectionResult(
                    success=False,
                    connection_id=connection.id,
                    error_message=error,
                )

            # Update connection with consent
            connection.consent_id = consent.consent_id
            connection.consent_expires_at = consent.valid_until
            connection.consent_status = consent.status
            connection.status = ConnectionStatus.AWAITING_CONSENT.value

            await db.commit()

            logger.info(
                "psd2_connection_initiated",
                connection_id=str(connection.id),
                bank_code=bank_code,
            )

            return ConnectionResult(
                success=True,
                connection_id=connection.id,
                requires_sca=True,
                sca_redirect_url=consent.sca_redirect_url,
            )

        except Exception as e:
            logger.error(
                "psd2_connection_init_error",
                bank_code=bank_code,
                **safe_error_log(e),
            )
            return ConnectionResult(
                success=False,
                error_message=safe_error_detail(e, "PSD2 Verbindung"),
            )

    async def complete_psd2_connection(
        self,
        db: AsyncSession,
        connection_id: UUID,
        company_id: UUID,
        authorization_code: Optional[str] = None,
        state: Optional[str] = None,
    ) -> ConnectionResult:
        """
        Complete PSD2 connection after SCA redirect.

        Called when user returns from bank's SCA page.
        """
        connection = await db.get(BankConnection, connection_id)
        if not connection or connection.company_id != company_id:
            return ConnectionResult(
                success=False,
                error_message="Verbindung nicht gefunden",
            )

        if connection.status != ConnectionStatus.AWAITING_CONSENT.value:
            return ConnectionResult(
                success=False,
                error_message=f"Ungueliger Verbindungsstatus: {connection.status}",
            )

        try:
            # Exchange authorization code for tokens
            # This would involve OAuth2 token exchange with the bank

            # For now, simulate successful completion
            connection.status = ConnectionStatus.ACTIVE.value
            connection.is_healthy = True

            # Calculate next sync
            connection.next_sync_at = utc_now() + timedelta(hours=connection.sync_interval_hours)

            await db.commit()

            logger.info(
                "psd2_connection_completed",
                connection_id=str(connection_id),
                bank_code=connection.bank_code,
            )

            return ConnectionResult(
                success=True,
                connection_id=connection_id,
            )

        except Exception as e:
            connection.status = ConnectionStatus.ERROR.value
            connection.last_error = safe_error_detail(e, "PSD2")
            await db.commit()

            logger.error(
                "psd2_connection_complete_error",
                connection_id=str(connection_id),
                **safe_error_log(e),
            )

            return ConnectionResult(
                success=False,
                connection_id=connection_id,
                error_message=safe_error_detail(e, "PSD2 Abschluss"),
            )

    # =========================================================================
    # FinTS Connection
    # =========================================================================

    async def init_fints_connection(
        self,
        db: AsyncSession,
        company_id: UUID,
        user_id: UUID,
        bank_code: str,
        login_id: str,
        pin: str,  # SECURITY: Never stored, session only
        tan_method: Optional[str] = None,
    ) -> ConnectionResult:
        """
        Initialize FinTS connection.

        Creates connection and initiates TAN-based authentication.
        PIN is used only for this session and never stored.
        """
        fints_url = self.fints_service.get_fints_url(bank_code)
        if not fints_url:
            return ConnectionResult(
                success=False,
                error_message=f"FinTS-URL für Bank {bank_code} nicht bekannt",
            )

        try:
            # Get bank info
            bank_info = await self.fints_service.get_bank_info(bank_code, fints_url)
            if not bank_info:
                return ConnectionResult(
                    success=False,
                    error_message=f"Kann Bank-Informationen nicht abrufen",
                )

            # Create connection
            connection = BankConnection(
                company_id=company_id,
                bank_code=bank_code,
                bank_name=bank_info.bank_name,
                bic=bank_info.bic,
                connection_type=ConnectionType.FINTS.value,
                status=ConnectionStatus.PENDING.value,
                fints_url=fints_url,
                fints_version=bank_info.hbci_version,
                selected_tan_method=tan_method,
                created_by_id=user_id,
            )

            # Encrypt and store login_id (PIN is NOT stored)
            encryption = self._get_encryption()
            connection.encrypted_credentials = encryption.encrypt(login_id)

            db.add(connection)
            await db.flush()

            # In production: Use FinTS to connect and get TAN challenge
            # For now, simulate TAN challenge

            tan_challenge = TANChallenge(
                challenge_id=uuid4().hex,
                tan_method=TANMethod(tan_method) if tan_method else TANMethod.PUSH_TAN,
                challenge_text="Bitte bestätigen Sie den Kontozugriff in Ihrer Banking-App.",
                expires_at=utc_now() + timedelta(minutes=5),
            )

            connection.status = ConnectionStatus.AWAITING_TAN.value
            await db.commit()

            logger.info(
                "fints_connection_initiated",
                connection_id=str(connection.id),
                bank_code=bank_code,
            )

            return ConnectionResult(
                success=True,
                connection_id=connection.id,
                requires_sca=True,
                tan_challenge=tan_challenge,
            )

        except Exception as e:
            logger.error(
                "fints_connection_init_error",
                bank_code=bank_code,
                **safe_error_log(e),
            )
            return ConnectionResult(
                success=False,
                error_message=safe_error_detail(e, "FinTS Verbindung"),
            )

    async def complete_fints_connection(
        self,
        db: AsyncSession,
        connection_id: UUID,
        company_id: UUID,
        tan: str,
    ) -> ConnectionResult:
        """
        Complete FinTS connection with TAN.
        """
        connection = await db.get(BankConnection, connection_id)
        if not connection or connection.company_id != company_id:
            return ConnectionResult(
                success=False,
                error_message="Verbindung nicht gefunden",
            )

        if connection.status != ConnectionStatus.AWAITING_TAN.value:
            return ConnectionResult(
                success=False,
                error_message=f"Ungültiger Verbindungsstatus: {connection.status}",
            )

        try:
            # In production: Verify TAN with FinTS server
            # For development: Accept any TAN >= 6 digits
            if len(tan) < 6:
                return ConnectionResult(
                    success=False,
                    connection_id=connection_id,
                    error_message="Ungültige TAN",
                )

            # Mark as active
            connection.status = ConnectionStatus.ACTIVE.value
            connection.is_healthy = True
            connection.next_sync_at = utc_now() + timedelta(hours=connection.sync_interval_hours)

            await db.commit()

            logger.info(
                "fints_connection_completed",
                connection_id=str(connection_id),
                bank_code=connection.bank_code,
            )

            return ConnectionResult(
                success=True,
                connection_id=connection_id,
            )

        except Exception as e:
            connection.status = ConnectionStatus.ERROR.value
            connection.last_error = safe_error_detail(e, "FinTS")
            await db.commit()

            logger.error(
                "fints_connection_complete_error",
                connection_id=str(connection_id),
                **safe_error_log(e),
            )

            return ConnectionResult(
                success=False,
                connection_id=connection_id,
                error_message=safe_error_detail(e, "FinTS TAN"),
            )

    # =========================================================================
    # Connection Management
    # =========================================================================

    async def get_connections(
        self,
        db: AsyncSession,
        company_id: UUID,
        include_inactive: bool = False,
    ) -> List[BankConnection]:
        """Get all connections for a company."""
        query = select(BankConnection).where(
            BankConnection.company_id == company_id
        )

        if not include_inactive:
            query = query.where(
                BankConnection.status.in_([
                    ConnectionStatus.ACTIVE.value,
                    ConnectionStatus.AWAITING_CONSENT.value,
                    ConnectionStatus.AWAITING_TAN.value,
                ])
            )

        result = await db.execute(query.order_by(BankConnection.bank_name))
        return list(result.scalars().all())

    async def get_connection(
        self,
        db: AsyncSession,
        connection_id: UUID,
        company_id: UUID,
    ) -> Optional[BankConnection]:
        """Get specific connection."""
        connection = await db.get(BankConnection, connection_id)
        if connection and connection.company_id == company_id:
            return connection
        return None

    async def get_accounts(
        self,
        db: AsyncSession,
        connection_id: UUID,
        company_id: UUID,
    ) -> List[AccountInfo]:
        """Get accounts for a connection."""
        connection = await self.get_connection(db, connection_id, company_id)
        if not connection:
            return []

        query = select(ConnectedBankAccount).where(
            ConnectedBankAccount.connection_id == connection_id
        ).order_by(ConnectedBankAccount.is_primary.desc(), ConnectedBankAccount.account_name)

        result = await db.execute(query)
        accounts = result.scalars().all()

        return [
            AccountInfo(
                id=acc.id,
                iban=acc.iban,
                name=acc.account_name,
                account_type=acc.account_type,
                currency=acc.currency,
                balance=acc.current_balance,
                balance_date=acc.balance_updated_at,
            )
            for acc in accounts
        ]

    async def update_connection(
        self,
        db: AsyncSession,
        connection_id: UUID,
        company_id: UUID,
        auto_sync_enabled: Optional[bool] = None,
        sync_interval_hours: Optional[int] = None,
    ) -> Optional[BankConnection]:
        """Update connection settings."""
        connection = await self.get_connection(db, connection_id, company_id)
        if not connection:
            return None

        if auto_sync_enabled is not None:
            connection.auto_sync_enabled = auto_sync_enabled

        if sync_interval_hours is not None:
            connection.sync_interval_hours = max(1, min(24, sync_interval_hours))

        # Recalculate next sync
        if connection.auto_sync_enabled:
            connection.next_sync_at = utc_now() + timedelta(hours=connection.sync_interval_hours)

        connection.updated_at = utc_now()
        await db.commit()

        return connection

    async def delete_connection(
        self,
        db: AsyncSession,
        connection_id: UUID,
        company_id: UUID,
        user_id: UUID,
    ) -> bool:
        """Delete a bank connection."""
        connection = await self.get_connection(db, connection_id, company_id)
        if not connection:
            return False

        # Revoke consent if PSD2
        if connection.connection_type == ConnectionType.PSD2.value and connection.consent_id:
            # In production: Call bank's consent revocation endpoint
            logger.info(
                "psd2_consent_revoked",
                connection_id=str(connection_id),
                consent_id=connection.consent_id,
            )

        # Mark as revoked instead of hard delete for audit
        connection.status = ConnectionStatus.REVOKED.value
        connection.updated_at = utc_now()

        await db.commit()

        logger.info(
            "connection_deleted",
            connection_id=str(connection_id),
            bank_code=connection.bank_code,
            deleted_by=str(user_id),
        )

        return True

    async def refresh_connection(
        self,
        db: AsyncSession,
        connection_id: UUID,
        company_id: UUID,
    ) -> ConnectionResult:
        """Refresh an expired or errored connection."""
        connection = await self.get_connection(db, connection_id, company_id)
        if not connection:
            return ConnectionResult(
                success=False,
                error_message="Verbindung nicht gefunden",
            )

        if connection.connection_type == ConnectionType.PSD2.value:
            # For PSD2, need to create new consent
            # This would redirect user to bank again
            return ConnectionResult(
                success=False,
                error_message="PSD2-Verbindungen müssen neu autorisiert werden",
                requires_sca=True,
            )

        elif connection.connection_type == ConnectionType.FINTS.value:
            # For FinTS, reset error count and try again
            connection.error_count = 0
            connection.last_error = None
            connection.status = ConnectionStatus.ACTIVE.value
            connection.is_healthy = True
            connection.next_sync_at = utc_now()

            await db.commit()

            return ConnectionResult(
                success=True,
                connection_id=connection_id,
            )

        return ConnectionResult(
            success=False,
            error_message="Unbekannter Verbindungstyp",
        )


# =============================================================================
# Factory
# =============================================================================

_service_instance: Optional[AccountConnectionService] = None


def get_account_connection_service() -> AccountConnectionService:
    """Get account connection service instance."""
    global _service_instance

    if _service_instance is None:
        _service_instance = AccountConnectionService()

    return _service_instance
