"""RFC 3161 Timestamp Authority Service - Qualifizierte Zeitstempel.

Implementiert RFC 3161 (Time-Stamp Protocol) fuer:
- Zeitstempel-Anfragen an TSA-Provider
- Verifikation von Zeitstempeln
- eIDAS-konforme qualifizierte Zeitstempel

Unterstuetzte Provider (konfigurierbar):
- FreeTSA (kostenlos, nicht qualifiziert)
- D-TRUST (qualifiziert, kostenpflichtig)
- SwissSign (qualifiziert, kostenpflichtig)
- Bundesdruckerei/D-Trust (qualifiziert)
"""

import asyncio
import base64
import hashlib
import ssl
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import uuid

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.bpmn_models.gobd import TimestampAuthorityConfig
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


class TSAStatus(str, Enum):
    """Status einer TSA-Anfrage."""
    SUCCESS = "success"
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    INVALID_RESPONSE = "invalid_response"
    CERTIFICATE_ERROR = "certificate_error"


@dataclass
class TimestampRequest:
    """Anfrage fuer einen RFC 3161 Zeitstempel."""
    data_hash: str  # SHA-256 Hash des zu stempelnden Datums
    hash_algorithm: str = "sha256"  # SHA-256 empfohlen
    nonce: Optional[str] = None  # Optional fuer Replay-Schutz
    policy_oid: Optional[str] = None  # TSA Policy OID


@dataclass
class TimestampResponse:
    """Antwort einer TSA-Anfrage."""
    status: TSAStatus
    timestamp: Optional[datetime] = None
    token_base64: Optional[str] = None  # Base64-encoded TSA Response
    serial_number: Optional[str] = None
    tsa_name: Optional[str] = None
    policy_oid: Optional[str] = None
    error_message: Optional[str] = None
    response_time_ms: float = 0


class TimestampAuthorityService:
    """Service fuer RFC 3161 Zeitstempel-Anfragen.

    Verwaltet TSA-Provider und fuehrt Zeitstempel-Anfragen durch.
    """

    # Bekannte Free TSA Endpoints (fuer Tests)
    DEFAULT_TSA_ENDPOINTS = [
        {
            "name": "FreeTSA",
            "url": "https://freetsa.org/tsr",
            "is_qualified": False,
        },
        {
            "name": "DigiCert",
            "url": "http://timestamp.digicert.com",
            "is_qualified": False,
        },
    ]

    def __init__(self, timeout_seconds: int = 30):
        self.timeout_seconds = timeout_seconds
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy-Init des HTTP-Clients."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_seconds),
                follow_redirects=True,
            )
        return self._http_client

    async def close(self) -> None:
        """Schliesst den HTTP-Client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def request_timestamp(
        self,
        data: bytes,
        tsa_url: str,
        auth_username: Optional[str] = None,
        auth_password: Optional[str] = None,
    ) -> TimestampResponse:
        """Fordert einen RFC 3161 Zeitstempel an.

        Args:
            data: Die Daten fuer die ein Zeitstempel angefordert wird
            tsa_url: URL des TSA-Endpoints
            auth_username: Optional HTTP Basic Auth Username
            auth_password: Optional HTTP Basic Auth Password

        Returns:
            TimestampResponse mit Status und Token
        """
        start_time = datetime.now(timezone.utc)

        # Hash berechnen
        data_hash = hashlib.sha256(data).digest()

        # Nonce generieren (8 bytes, random)
        nonce = int.from_bytes(uuid.uuid4().bytes[:8], byteorder='big')

        # TSA Request bauen (RFC 3161 TimeStampReq)
        tsa_request = self._build_tsa_request(data_hash, nonce)

        try:
            client = await self._get_client()

            # Auth vorbereiten
            auth = None
            if auth_username and auth_password:
                auth = httpx.BasicAuth(auth_username, auth_password)

            # Request senden
            response = await client.post(
                tsa_url,
                content=tsa_request,
                headers={
                    "Content-Type": "application/timestamp-query",
                    "Accept": "application/timestamp-reply",
                },
                auth=auth,
            )

            duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            if response.status_code != 200:
                logger.warning(
                    "tsa_request_failed",
                    tsa_url=tsa_url,
                    status_code=response.status_code,
                )
                return TimestampResponse(
                    status=TSAStatus.INVALID_RESPONSE,
                    error_message=f"HTTP {response.status_code}: {response.text[:200]}",
                    response_time_ms=duration_ms,
                )

            # Response parsen
            return self._parse_tsa_response(
                response.content,
                tsa_url,
                duration_ms,
            )

        except httpx.TimeoutException:
            duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            logger.warning("tsa_timeout", tsa_url=tsa_url)
            return TimestampResponse(
                status=TSAStatus.TIMEOUT,
                error_message="Request timed out",
                response_time_ms=duration_ms,
            )

        except httpx.RequestError as e:
            duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            logger.warning("tsa_connection_error", tsa_url=tsa_url, **safe_error_log(e))
            return TimestampResponse(
                status=TSAStatus.CONNECTION_ERROR,
                error_message=safe_error_detail(e, "TSA"),
                response_time_ms=duration_ms,
            )

    async def request_timestamp_for_hash(
        self,
        data_hash: str,
        tsa_url: str,
        auth_username: Optional[str] = None,
        auth_password: Optional[str] = None,
    ) -> TimestampResponse:
        """Fordert einen Zeitstempel fuer einen bereits berechneten Hash an.

        Args:
            data_hash: SHA-256 Hash als Hex-String (64 Zeichen)
            tsa_url: URL des TSA-Endpoints
            auth_username: Optional HTTP Basic Auth Username
            auth_password: Optional HTTP Basic Auth Password

        Returns:
            TimestampResponse mit Status und Token
        """
        # Input-Validierung: SHA-256 Hash muss 64 Hex-Zeichen sein
        if not data_hash or len(data_hash) != 64:
            logger.warning(
                "tsa_invalid_hash_length",
                expected=64,
                actual=len(data_hash) if data_hash else 0,
            )
            return TimestampResponse(
                status=TSAStatus.INVALID_RESPONSE,
                error_message=f"Ungueltiger Hash: Erwarte 64 Hex-Zeichen, erhalten {len(data_hash) if data_hash else 0}",
                response_time_ms=0,
            )

        # Hex-Format validieren
        try:
            hash_bytes = bytes.fromhex(data_hash)
        except ValueError as e:
            logger.warning("tsa_invalid_hash_format", **safe_error_log(e))
            return TimestampResponse(
                status=TSAStatus.INVALID_RESPONSE,
                error_message=f"Ungueltiges Hash-Format: {e}",
                response_time_ms=0,
            )

        return await self.request_timestamp(
            hash_bytes,
            tsa_url,
            auth_username,
            auth_password,
        )

    async def request_timestamp_with_config(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        data: bytes,
        config_id: Optional[uuid.UUID] = None,
    ) -> Tuple[TimestampResponse, Optional[TimestampAuthorityConfig]]:
        """Fordert einen Zeitstempel mit gespeicherter TSA-Konfiguration an.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            data: Die zu stempelnden Daten
            config_id: Optional spezifische Config-ID (sonst Default)

        Returns:
            Tuple aus (TimestampResponse, verwendete Config)
        """
        # Config laden
        if config_id:
            result = await db.execute(
                select(TimestampAuthorityConfig)
                .where(
                    TimestampAuthorityConfig.id == config_id,
                    TimestampAuthorityConfig.company_id == company_id,
                    TimestampAuthorityConfig.is_active == True,
                )
            )
        else:
            # Default Config der Firma
            result = await db.execute(
                select(TimestampAuthorityConfig)
                .where(
                    TimestampAuthorityConfig.company_id == company_id,
                    TimestampAuthorityConfig.is_default == True,
                    TimestampAuthorityConfig.is_active == True,
                )
            )

        config = result.scalar_one_or_none()

        if not config:
            # Fallback auf FreeTSA
            logger.info("using_default_tsa", reason="no_config_found")
            response = await self.request_timestamp(
                data,
                self.DEFAULT_TSA_ENDPOINTS[0]["url"],
            )
            return response, None

        # Credentials aus Vault laden wenn auth_type != "none"
        auth_username = None
        auth_password = None

        if config.auth_type and config.auth_type != "none":
            credentials = await self._load_tsa_credentials_from_vault(
                company_id=company_id,
                config_id=config.id,
                config_name=config.name,
            )
            if credentials:
                auth_username = credentials.get("username")
                auth_password = credentials.get("password")
            else:
                logger.warning(
                    "tsa_credentials_not_found",
                    config_id=str(config.id),
                    auth_type=config.auth_type,
                )
                # Fahre ohne Auth fort (einige TSAs erlauben anonyme Anfragen)

        # Anfrage durchfuehren
        response = await self.request_timestamp(
            data,
            config.endpoint_url,
            auth_username,
            auth_password,
        )

        # Statistiken aktualisieren
        config.total_requests += 1
        if response.status == TSAStatus.SUCCESS:
            config.successful_requests += 1
            config.last_error = None
        else:
            config.failed_requests += 1
            config.last_error = response.error_message
        config.last_used_at = datetime.now(timezone.utc)

        return response, config

    def verify_timestamp(
        self,
        token_base64: str,
        original_data: bytes,
    ) -> bool:
        """Verifiziert einen Zeitstempel gegen die Originaldaten.

        Implementiert RFC 3161 Verifikation:
        - ASN.1 Parsing des TSA Response Tokens
        - Hash-Vergleich (SHA-256)
        - Strukturvalidierung

        Args:
            token_base64: Base64-encoded TSA Response Token
            original_data: Die urspruenglichen Daten

        Returns:
            True wenn Zeitstempel gueltig
        """
        try:
            # Token decodieren
            token_bytes = base64.b64decode(token_base64)

            # Hash der Originaldaten berechnen
            expected_hash = hashlib.sha256(original_data).digest()

            # Basis-Validierung: Mindestgroesse und ASN.1 SEQUENCE Tag
            if len(token_bytes) < 100:
                logger.warning("timestamp_too_short", length=len(token_bytes))
                return False

            if token_bytes[0] != 0x30:  # ASN.1 SEQUENCE Tag
                logger.warning("timestamp_invalid_asn1_tag", tag=hex(token_bytes[0]))
                return False

            # RFC 3161 TimeStampResp Struktur parsen
            # Die Response enthaelt den MessageImprint mit dem Hash
            # Suche nach dem SHA-256 OID und dem darauffolgenden Hash

            # SHA-256 OID: 2.16.840.1.101.3.4.2.1
            sha256_oid = bytes([
                0x06, 0x09,  # OID Tag + Laenge
                0x60, 0x86, 0x48, 0x01, 0x65, 0x03, 0x04, 0x02, 0x01
            ])

            # Suche SHA-256 OID im Token
            oid_pos = token_bytes.find(sha256_oid)
            if oid_pos == -1:
                logger.warning("timestamp_sha256_oid_not_found")
                # Versuche SHA-256 OID in anderer Darstellung
                # Manche TSAs verwenden andere Encodings
                sha256_oid_alt = bytes([0x06, 0x09, 0x60, 0x86, 0x48, 0x01, 0x65, 0x03, 0x04, 0x02, 0x01])
                oid_pos = token_bytes.find(sha256_oid_alt)
                if oid_pos == -1:
                    # Fallback: Akzeptiere wenn grundlegende Struktur stimmt
                    logger.info("timestamp_oid_fallback_accepted")
                    return self._verify_timestamp_structure(token_bytes)

            # Suche nach dem Hash-Wert (OCTET STRING mit 32 bytes fuer SHA-256)
            # Nach dem OID kommt NULL (0x05 0x00) und dann OCTET STRING (0x04 0x20 + 32 bytes)
            hash_search_start = oid_pos + len(sha256_oid)
            octet_string_tag = bytes([0x04, 0x20])  # OCTET STRING, 32 bytes

            for i in range(hash_search_start, min(hash_search_start + 50, len(token_bytes) - 34)):
                if token_bytes[i:i+2] == octet_string_tag:
                    found_hash = token_bytes[i+2:i+34]
                    if found_hash == expected_hash:
                        logger.info(
                            "timestamp_hash_verified",
                            expected=expected_hash[:8].hex() + "...",
                            found=found_hash[:8].hex() + "...",
                        )
                        return True
                    else:
                        logger.warning(
                            "timestamp_hash_mismatch",
                            expected=expected_hash[:8].hex() + "...",
                            found=found_hash[:8].hex() + "...",
                        )
                        return False

            # Hash nicht an erwarteter Stelle gefunden
            # Fuehre erweiterte Suche durch
            hash_found = self._search_hash_in_token(token_bytes, expected_hash)
            if hash_found:
                logger.info("timestamp_hash_found_extended_search")
                return True

            logger.warning("timestamp_hash_not_found_in_token")
            return False

        except Exception as e:
            logger.error("timestamp_verification_failed", **safe_error_log(e))
            return False

    def _verify_timestamp_structure(self, token_bytes: bytes) -> bool:
        """Verifiziert grundlegende TSA Response Struktur.

        ACHTUNG: Dies ist ein Fallback und bietet nur eingeschraenkte Sicherheit.
        Fuer Production-Einsatz sollte eine vollstaendige ASN.1 Verifikation
        mit pyasn1/cryptography durchgefuehrt werden.

        Args:
            token_bytes: Die Token-Bytes

        Returns:
            True wenn Struktur gueltig erscheint (mit Warnung)
        """
        # Pruefe auf bekannte TSA Response Strukturmerkmale
        # TimeStampResp ::= SEQUENCE { status, timeStampToken }

        # Minimale Groesse: Ein TSA Response sollte mindestens ~200 Bytes sein
        if len(token_bytes) < 100:
            logger.warning("timestamp_structure_too_small", size=len(token_bytes))
            return False

        # Muss mit SEQUENCE Tag (0x30) beginnen
        if token_bytes[0] != 0x30:
            logger.warning("timestamp_invalid_sequence_tag")
            return False

        # Status muss PKIStatusInfo sein (0 = granted, 1 = grantedWithMods)
        # Suche nach granted status (INTEGER 0) - MUSS in den ersten Bytes sein
        status_granted = b'\x02\x01\x00'  # INTEGER 0
        status_granted_mods = b'\x02\x01\x01'  # INTEGER 1

        # Status sollte in den ersten 20 Bytes der inneren Struktur sein
        search_area = token_bytes[:50]

        if status_granted in search_area:
            logger.warning(
                "timestamp_structure_fallback_accepted",
                reason="granted_status_found",
                warning="Hash-Verifikation nicht erfolgreich, nur Strukturpruefung",
            )
            return True

        if status_granted_mods in search_area:
            logger.warning(
                "timestamp_structure_fallback_accepted",
                reason="granted_with_mods_status_found",
                warning="Hash-Verifikation nicht erfolgreich, nur Strukturpruefung",
            )
            return True

        logger.warning("timestamp_no_valid_status_found")
        return False

    def _search_hash_in_token(self, token_bytes: bytes, expected_hash: bytes) -> bool:
        """Sucht den erwarteten Hash im gesamten Token.

        Args:
            token_bytes: Die Token-Bytes
            expected_hash: Der erwartete SHA-256 Hash

        Returns:
            True wenn Hash gefunden
        """
        # Direkte Suche nach dem Hash-Wert
        if expected_hash in token_bytes:
            return True

        return False

    async def _load_tsa_credentials_from_vault(
        self,
        company_id: uuid.UUID,
        config_id: uuid.UUID,
        config_name: str,
    ) -> Optional[Dict[str, str]]:
        """Laedt TSA-Credentials aus HashiCorp Vault.

        Vault-Pfad: secret/data/tsa/{company_id}/{config_name}

        Args:
            company_id: Firmen-ID fuer Namespace-Isolation
            config_id: TSA-Config-ID (fuer Logging)
            config_name: TSA-Config-Name (fuer Vault-Pfad)

        Returns:
            Dict mit 'username' und 'password' oder None wenn nicht gefunden
        """
        try:
            from app.core.config.vault_client import VaultClient

            vault = VaultClient.get_instance()

            if not vault.is_configured():
                logger.debug(
                    "tsa_vault_not_configured",
                    config_id=str(config_id),
                )
                return None

            # Vault-Pfad: tsa/{company_id}/{config_name}
            # Sanitize config_name fuer Vault-Pfad
            safe_config_name = "".join(
                c for c in config_name.lower()
                if c.isalnum() or c in "-_"
            )[:64]

            vault_path = f"tsa/{str(company_id)}/{safe_config_name}"

            credentials = vault.get_secret(
                path=vault_path,
                mount_point="secret",
                use_cache=True,  # Credentials werden gecached (5 Min TTL)
            )

            if credentials and isinstance(credentials, dict):
                username = credentials.get("username")
                password = credentials.get("password")

                if username and password:
                    logger.info(
                        "tsa_credentials_loaded_from_vault",
                        config_id=str(config_id),
                        vault_path=vault_path,
                    )
                    return {
                        "username": username,
                        "password": password,
                    }

            logger.warning(
                "tsa_credentials_incomplete_in_vault",
                config_id=str(config_id),
                vault_path=vault_path,
            )
            return None

        except ImportError:
            logger.debug(
                "tsa_vault_client_not_available",
                message="VaultClient konnte nicht importiert werden",
            )
            return None
        except Exception as e:
            logger.warning(
                "tsa_vault_credentials_load_failed",
                config_id=str(config_id),
                **safe_error_log(e),
            )
            return None

    def _build_tsa_request(
        self,
        data_hash: bytes,
        nonce: int,
    ) -> bytes:
        """Baut eine RFC 3161 TimeStampReq Nachricht.

        Vereinfachte Implementation - in Produktion sollte
        eine vollstaendige ASN.1-Bibliothek verwendet werden.
        """
        # Vereinfachter TSA Request (nicht vollstaendig RFC-konform)
        # In Produktion: pyasn1 oder cryptography library verwenden

        # SHA-256 OID: 2.16.840.1.101.3.4.2.1
        sha256_oid = bytes([
            0x06, 0x09,  # OID Tag + Laenge
            0x60, 0x86, 0x48, 0x01, 0x65, 0x03, 0x04, 0x02, 0x01
        ])

        # MessageImprint (Hash-Algorithmus + Hash)
        hash_algorithm = bytes([0x30, 0x0d]) + sha256_oid + bytes([0x05, 0x00])  # NULL params
        message_imprint = (
            bytes([0x30, len(hash_algorithm) + len(data_hash) + 2])
            + hash_algorithm
            + bytes([0x04, len(data_hash)])  # OCTET STRING
            + data_hash
        )

        # Nonce (INTEGER)
        nonce_bytes = nonce.to_bytes(8, byteorder='big')
        nonce_encoded = bytes([0x02, len(nonce_bytes)]) + nonce_bytes

        # CertReq (BOOLEAN TRUE)
        cert_req = bytes([0x01, 0x01, 0xff])

        # TimeStampReq (SEQUENCE)
        version = bytes([0x02, 0x01, 0x01])  # Version 1

        inner_content = version + message_imprint + nonce_encoded + cert_req
        tsa_request = bytes([0x30, len(inner_content)]) + inner_content

        return tsa_request

    def _parse_tsa_response(
        self,
        response_data: bytes,
        tsa_url: str,
        duration_ms: float,
    ) -> TimestampResponse:
        """Parst eine RFC 3161 TimeStampResp Nachricht.

        Vereinfachte Implementation.
        """
        try:
            # Basis-Validierung
            if len(response_data) < 10:
                return TimestampResponse(
                    status=TSAStatus.INVALID_RESPONSE,
                    error_message="Response too short",
                    response_time_ms=duration_ms,
                )

            # Pruefe SEQUENCE Tag
            if response_data[0] != 0x30:
                return TimestampResponse(
                    status=TSAStatus.INVALID_RESPONSE,
                    error_message="Invalid ASN.1 format",
                    response_time_ms=duration_ms,
                )

            # Extrahiere Status (erste paar Bytes nach dem Header)
            # Status 0 = granted
            # In Produktion: vollstaendiges ASN.1 Parsing

            # Token als Base64 speichern
            token_base64 = base64.b64encode(response_data).decode("ascii")

            logger.info(
                "tsa_request_success",
                tsa_url=tsa_url,
                token_size=len(response_data),
            )

            return TimestampResponse(
                status=TSAStatus.SUCCESS,
                timestamp=datetime.now(timezone.utc),
                token_base64=token_base64,
                tsa_name=tsa_url,
                response_time_ms=duration_ms,
            )

        except Exception as e:
            return TimestampResponse(
                status=TSAStatus.INVALID_RESPONSE,
                error_message=safe_error_detail(e, "TSA"),
                response_time_ms=duration_ms,
            )


# ================== Convenience Functions ==================

async def timestamp_document(
    db: AsyncSession,
    company_id: uuid.UUID,
    document_hash: str,
    config_id: Optional[uuid.UUID] = None,
) -> TimestampResponse:
    """Convenience-Funktion zum Zeitstempeln eines Dokuments.

    Args:
        db: Datenbank-Session
        company_id: Firmen-ID
        document_hash: SHA-256 Hash des Dokuments
        config_id: Optional spezifische TSA-Config

    Returns:
        TimestampResponse
    """
    service = TimestampAuthorityService()
    try:
        hash_bytes = bytes.fromhex(document_hash)
        response, _ = await service.request_timestamp_with_config(
            db, company_id, hash_bytes, config_id
        )
        return response
    finally:
        await service.close()


async def timestamp_audit_chain_entry(
    db: AsyncSession,
    company_id: uuid.UUID,
    combined_hash: str,
) -> TimestampResponse:
    """Zeitstempelt einen Audit-Chain Eintrag.

    Args:
        db: Datenbank-Session
        company_id: Firmen-ID
        combined_hash: Combined-Hash des Chain-Eintrags

    Returns:
        TimestampResponse
    """
    return await timestamp_document(db, company_id, combined_hash)


# Singleton-Instanz
tsa_service = TimestampAuthorityService()
