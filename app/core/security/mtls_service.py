# -*- coding: utf-8 -*-
"""
mTLS (Mutual TLS) Service for Inter-Service Authentication.

Provides secure service-to-service communication using mutual TLS.
All communication between internal services is authenticated and encrypted.

Features:
- SPIFFE-compatible service identities
- Automatic certificate rotation (30-day expiry)
- Service authentication middleware
- Audit logging for all mTLS events
- On-premises only (no cloud dependencies)

Feinpoliert und durchdacht - Sichere Service-Kommunikation.
"""

import asyncio
import ssl
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
import functools

import structlog
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.safe_errors import safe_error_log
from app.core.security.certificate_authority import (
    CertificateAuthority,
    CertificateRequest,
    CertificateInfo,
    CertificateType,
    KeyAlgorithm,
    get_certificate_authority,
    ALLOWED_SERVICE_TYPES,
    SERVICE_CERT_VALIDITY_DAYS,
    MIN_CERT_VALIDITY_DAYS,
    SPIFFE_TRUST_DOMAIN,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Certificate directory structure
DEFAULT_CERTS_DIR = Path("/app/certs/mtls")

# Service identity headers (set by nginx/reverse proxy)
HEADER_SSL_CLIENT_DN = "X-SSL-Client-S-DN"
HEADER_SSL_CLIENT_VERIFY = "X-SSL-Client-Verify"
HEADER_SSL_CLIENT_SERIAL = "X-SSL-Client-Serial"
HEADER_SSL_CLIENT_FINGERPRINT = "X-SSL-Client-Fingerprint"
HEADER_SSL_CLIENT_EXPIRY = "X-SSL-Client-V-End"

# Service registry cache TTL
SERVICE_REGISTRY_TTL_SECONDS = 300  # 5 minutes


class MTLSAuthResult(str, Enum):
    """Result of mTLS authentication."""
    SUCCESS = "success"
    MISSING_CERTIFICATE = "missing_certificate"
    INVALID_CERTIFICATE = "invalid_certificate"
    REVOKED_CERTIFICATE = "revoked_certificate"
    EXPIRED_CERTIFICATE = "expired_certificate"
    UNKNOWN_SERVICE = "unknown_service"
    VERIFICATION_FAILED = "verification_failed"


@dataclass
class ServiceIdentity:
    """Identity of an authenticated service."""
    service_name: str
    service_type: str
    spiffe_id: str
    serial_number: int
    fingerprint: str
    not_after: datetime
    subject_dn: str
    verified: bool = True
    auth_result: MTLSAuthResult = MTLSAuthResult.SUCCESS


@dataclass
class ServiceCertificate:
    """Service certificate with metadata."""
    service_name: str
    service_type: str
    cert_pem: bytes
    key_pem: bytes
    cert_info: CertificateInfo
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    rotated_at: Optional[datetime] = None
    rotation_count: int = 0


@dataclass
class MTLSAuditEvent:
    """Audit event for mTLS operations."""
    timestamp: datetime
    event_type: str
    service_name: Optional[str]
    service_type: Optional[str]
    source_ip: Optional[str]
    result: MTLSAuthResult
    details: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# mTLS Service Implementation
# =============================================================================

class MTLSService:
    """
    Service for managing mTLS authentication and certificates.

    Provides:
    - Service certificate management
    - Certificate rotation
    - Service authentication
    - SSL context creation
    - Audit logging
    """

    def __init__(
        self,
        certs_dir: Optional[Path] = None,
        trust_domain: str = SPIFFE_TRUST_DOMAIN,
        auto_init_ca: bool = True,
    ):
        """
        Initialize the mTLS service.

        Args:
            certs_dir: Directory for certificates
            trust_domain: SPIFFE trust domain
            auto_init_ca: Automatically initialize CA if not exists
        """
        self.certs_dir = certs_dir or DEFAULT_CERTS_DIR
        self.trust_domain = trust_domain

        # Certificate Authority
        self._ca: Optional[CertificateAuthority] = None
        self._auto_init_ca = auto_init_ca

        # Service certificate registry
        self._service_certs: Dict[str, ServiceCertificate] = {}
        self._registry_updated_at: Optional[datetime] = None

        # Audit log (in-memory, flushed periodically)
        self._audit_log: List[MTLSAuditEvent] = []
        self._max_audit_log_size = 1000

        logger.info(
            "mtls_service_initialized",
            certs_dir=str(self.certs_dir),
            trust_domain=self.trust_domain,
        )

    @property
    def ca(self) -> CertificateAuthority:
        """Get the Certificate Authority instance."""
        if self._ca is None:
            self._ca = get_certificate_authority(
                certs_dir=self.certs_dir,
                trust_domain=self.trust_domain,
            )

            # Auto-initialize CA if needed
            if self._auto_init_ca and not self._ca.is_initialized():
                logger.info("auto_initializing_certificate_authority")
                self._ca.initialize_ca()
            elif self._ca.is_initialized():
                self._ca.load_ca()

        return self._ca

    def _log_audit_event(
        self,
        event_type: str,
        result: MTLSAuthResult,
        service_name: Optional[str] = None,
        service_type: Optional[str] = None,
        source_ip: Optional[str] = None,
        **details: Any,
    ) -> None:
        """
        Log an audit event.

        Args:
            event_type: Type of event (auth, issue, revoke, rotate)
            result: Result of the operation
            service_name: Service name if applicable
            service_type: Service type if applicable
            source_ip: Source IP address
            **details: Additional event details
        """
        event = MTLSAuditEvent(
            timestamp=datetime.now(timezone.utc),
            event_type=event_type,
            service_name=service_name,
            service_type=service_type,
            source_ip=source_ip,
            result=result,
            details=details,
        )

        self._audit_log.append(event)

        # Trim audit log if too large
        if len(self._audit_log) > self._max_audit_log_size:
            self._audit_log = self._audit_log[-self._max_audit_log_size:]

        # Also log to structured logger
        logger.info(
            f"mtls_audit_{event_type}",
            result=result.value,
            service_name=service_name,
            service_type=service_type,
            source_ip=source_ip,
            **{k: v for k, v in details.items() if not k.startswith("_")},
        )

    # =========================================================================
    # Certificate Issuance
    # =========================================================================

    def issue_service_certificate(
        self,
        service_name: str,
        service_type: str,
        validity_days: int = SERVICE_CERT_VALIDITY_DAYS,
        certificate_type: CertificateType = CertificateType.BOTH,
        san_dns: Optional[List[str]] = None,
        san_ips: Optional[List[str]] = None,
        save_to_disk: bool = True,
    ) -> ServiceCertificate:
        """
        Issue a new certificate for a service.

        Args:
            service_name: Name of the service
            service_type: Type of service (backend, worker, etc.)
            validity_days: Certificate validity in days
            certificate_type: Server, Client, or Both
            san_dns: Additional DNS names for SAN
            san_ips: Additional IP addresses for SAN
            save_to_disk: Save certificate to disk

        Returns:
            ServiceCertificate with certificate and key

        Raises:
            ValueError: If service type is not allowed
        """
        if service_type not in ALLOWED_SERVICE_TYPES:
            raise ValueError(
                f"Unbekannter Service-Typ: {service_type}. "
                f"Erlaubt: {', '.join(sorted(ALLOWED_SERVICE_TYPES))}"
            )

        request = CertificateRequest(
            service_name=service_name,
            service_type=service_type,
            validity_days=validity_days,
            certificate_type=certificate_type,
            san_dns=san_dns or [],
            san_ips=san_ips or [],
        )

        if save_to_disk:
            cert_info = self.ca.issue_and_save_certificate(request)
            # Read back the PEM data
            cert_pem = cert_info.cert_path.read_bytes()
            key_pem = cert_info.key_path.read_bytes()
        else:
            cert_pem, key_pem, cert_info = self.ca.issue_certificate(request)

        service_cert = ServiceCertificate(
            service_name=service_name,
            service_type=service_type,
            cert_pem=cert_pem,
            key_pem=key_pem,
            cert_info=cert_info,
        )

        # Register certificate
        registry_key = f"{service_type}/{service_name}"
        self._service_certs[registry_key] = service_cert

        self._log_audit_event(
            event_type="certificate_issued",
            result=MTLSAuthResult.SUCCESS,
            service_name=service_name,
            service_type=service_type,
            serial_number=cert_info.serial_number,
            fingerprint=cert_info.fingerprint_sha256[:16] + "...",
            not_after=cert_info.not_after.isoformat(),
        )

        return service_cert

    def get_service_certificate(
        self,
        service_name: str,
        service_type: str,
    ) -> Optional[ServiceCertificate]:
        """
        Get a service certificate from the registry.

        Args:
            service_name: Name of the service
            service_type: Type of service

        Returns:
            ServiceCertificate if found, None otherwise
        """
        registry_key = f"{service_type}/{service_name}"
        return self._service_certs.get(registry_key)

    def load_service_certificate(
        self,
        service_name: str,
        service_type: str,
    ) -> Optional[ServiceCertificate]:
        """
        Load a service certificate from disk.

        Args:
            service_name: Name of the service
            service_type: Type of service

        Returns:
            ServiceCertificate if found, None otherwise
        """
        cert_dir = self.certs_dir / service_type / service_name
        cert_path = cert_dir / "cert.pem"
        key_path = cert_dir / "key.pem"

        if not cert_path.exists() or not key_path.exists():
            return None

        cert_pem = cert_path.read_bytes()
        key_pem = key_path.read_bytes()
        cert_info = self.ca.get_certificate_info(cert_pem)
        cert_info.cert_path = cert_path
        cert_info.key_path = key_path

        service_cert = ServiceCertificate(
            service_name=service_name,
            service_type=service_type,
            cert_pem=cert_pem,
            key_pem=key_pem,
            cert_info=cert_info,
        )

        # Register certificate
        registry_key = f"{service_type}/{service_name}"
        self._service_certs[registry_key] = service_cert

        logger.debug(
            "service_certificate_loaded",
            service_name=service_name,
            service_type=service_type,
            fingerprint=cert_info.fingerprint_sha256[:16] + "...",
        )

        return service_cert

    def ensure_service_certificate(
        self,
        service_name: str,
        service_type: str,
        **kwargs: Any,
    ) -> ServiceCertificate:
        """
        Ensure a service has a valid certificate.

        Loads existing certificate or issues a new one.

        Args:
            service_name: Name of the service
            service_type: Type of service
            **kwargs: Additional arguments for issue_service_certificate

        Returns:
            ServiceCertificate
        """
        # Check in-memory registry first
        cert = self.get_service_certificate(service_name, service_type)

        # Try loading from disk
        if cert is None:
            cert = self.load_service_certificate(service_name, service_type)

        # Issue new certificate if needed
        if cert is None:
            cert = self.issue_service_certificate(
                service_name=service_name,
                service_type=service_type,
                **kwargs,
            )

        # Check if renewal is needed
        if self.ca.needs_renewal(cert.cert_pem):
            logger.info(
                "certificate_needs_renewal",
                service_name=service_name,
                service_type=service_type,
            )
            cert = self.rotate_service_certificate(service_name, service_type)

        return cert

    # =========================================================================
    # Certificate Rotation
    # =========================================================================

    def rotate_service_certificate(
        self,
        service_name: str,
        service_type: str,
        revoke_old: bool = True,
    ) -> ServiceCertificate:
        """
        Rotate a service certificate.

        Issues a new certificate and optionally revokes the old one.

        Args:
            service_name: Name of the service
            service_type: Type of service
            revoke_old: Revoke the old certificate

        Returns:
            New ServiceCertificate
        """
        old_cert = self.get_service_certificate(service_name, service_type)

        # Issue new certificate
        new_cert = self.issue_service_certificate(
            service_name=service_name,
            service_type=service_type,
        )

        # Update rotation metadata
        new_cert.rotated_at = datetime.now(timezone.utc)
        if old_cert:
            new_cert.rotation_count = old_cert.rotation_count + 1

            # Revoke old certificate
            if revoke_old:
                self.ca.revoke_certificate(
                    old_cert.cert_info.serial_number,
                    reason="key_rotation",
                )

        self._log_audit_event(
            event_type="certificate_rotated",
            result=MTLSAuthResult.SUCCESS,
            service_name=service_name,
            service_type=service_type,
            old_serial=old_cert.cert_info.serial_number if old_cert else None,
            new_serial=new_cert.cert_info.serial_number,
            rotation_count=new_cert.rotation_count,
        )

        return new_cert

    def get_certificates_needing_rotation(
        self,
        threshold_days: int = MIN_CERT_VALIDITY_DAYS,
    ) -> List[Tuple[str, str, CertificateInfo]]:
        """
        Get list of certificates that need rotation.

        Args:
            threshold_days: Days before expiry to trigger rotation

        Returns:
            List of (service_name, service_type, cert_info) tuples
        """
        needs_rotation = []

        for registry_key, service_cert in self._service_certs.items():
            if self.ca.needs_renewal(service_cert.cert_pem, threshold_days):
                service_type, service_name = registry_key.split("/", 1)
                needs_rotation.append((
                    service_name,
                    service_type,
                    service_cert.cert_info,
                ))

        return needs_rotation

    # =========================================================================
    # Service Authentication
    # =========================================================================

    def authenticate_request(
        self,
        request: Request,
    ) -> ServiceIdentity:
        """
        Authenticate a request using mTLS headers.

        The reverse proxy (nginx) performs TLS termination and sets
        headers with client certificate information.

        Args:
            request: FastAPI request

        Returns:
            ServiceIdentity of the authenticated service

        Raises:
            HTTPException: If authentication fails
        """
        source_ip = request.client.host if request.client else "unknown"

        # Check verification status
        verify_status = request.headers.get(HEADER_SSL_CLIENT_VERIFY, "NONE")

        if verify_status == "NONE":
            self._log_audit_event(
                event_type="auth_attempt",
                result=MTLSAuthResult.MISSING_CERTIFICATE,
                source_ip=source_ip,
            )
            raise HTTPException(
                status_code=401,
                detail="Client-Zertifikat erforderlich für Service-Authentifizierung",
            )

        if verify_status != "SUCCESS":
            self._log_audit_event(
                event_type="auth_attempt",
                result=MTLSAuthResult.VERIFICATION_FAILED,
                source_ip=source_ip,
                verify_status=verify_status,
            )
            raise HTTPException(
                status_code=401,
                detail=f"Client-Zertifikat-Verifizierung fehlgeschlagen: {verify_status}",
            )

        # Extract certificate information from headers
        subject_dn = request.headers.get(HEADER_SSL_CLIENT_DN, "")
        serial_str = request.headers.get(HEADER_SSL_CLIENT_SERIAL, "")
        fingerprint = request.headers.get(HEADER_SSL_CLIENT_FINGERPRINT, "")
        expiry_str = request.headers.get(HEADER_SSL_CLIENT_EXPIRY, "")

        if not subject_dn:
            self._log_audit_event(
                event_type="auth_attempt",
                result=MTLSAuthResult.INVALID_CERTIFICATE,
                source_ip=source_ip,
                reason="missing_subject_dn",
            )
            raise HTTPException(
                status_code=401,
                detail="Ungültiges Client-Zertifikat: Subject DN fehlt",
            )

        # Parse subject DN to extract service information
        # Expected format: CN=ablage-<service_name>,OU=<service_type>,O=Ablage-System,C=DE
        service_name, service_type = self._parse_subject_dn(subject_dn)

        if not service_name or not service_type:
            self._log_audit_event(
                event_type="auth_attempt",
                result=MTLSAuthResult.UNKNOWN_SERVICE,
                source_ip=source_ip,
                subject_dn=subject_dn,
            )
            raise HTTPException(
                status_code=401,
                detail="Unbekannter Service im Client-Zertifikat",
            )

        # Parse serial number
        try:
            serial_number = int(serial_str, 16) if serial_str else 0
        except ValueError:
            serial_number = 0

        # Parse expiry date
        try:
            # Format: "Jan  1 00:00:00 2026 GMT"
            not_after = datetime.strptime(
                expiry_str.strip(), "%b %d %H:%M:%S %Y %Z"
            ).replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError):
            not_after = datetime.now(timezone.utc) + timedelta(days=30)

        # Build SPIFFE ID
        spiffe_id = f"spiffe://{self.trust_domain}/{service_type}/{service_name}"

        identity = ServiceIdentity(
            service_name=service_name,
            service_type=service_type,
            spiffe_id=spiffe_id,
            serial_number=serial_number,
            fingerprint=fingerprint,
            not_after=not_after,
            subject_dn=subject_dn,
            verified=True,
            auth_result=MTLSAuthResult.SUCCESS,
        )

        self._log_audit_event(
            event_type="auth_success",
            result=MTLSAuthResult.SUCCESS,
            service_name=service_name,
            service_type=service_type,
            source_ip=source_ip,
            spiffe_id=spiffe_id,
            fingerprint=fingerprint[:16] + "..." if fingerprint else None,
        )

        return identity

    def _parse_subject_dn(self, subject_dn: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Parse subject DN to extract service name and type.

        Args:
            subject_dn: Subject Distinguished Name

        Returns:
            Tuple of (service_name, service_type) or (None, None)
        """
        # Format: CN=ablage-<service_name>,OU=<service_type>,O=Ablage-System,C=DE
        service_name = None
        service_type = None

        for part in subject_dn.split(","):
            part = part.strip()
            if part.startswith("CN="):
                cn_value = part[3:]
                if cn_value.startswith("ablage-"):
                    service_name = cn_value[7:]  # Remove "ablage-" prefix
            elif part.startswith("OU="):
                service_type = part[3:]

        return service_name, service_type

    # =========================================================================
    # SSL Context Creation
    # =========================================================================

    def create_ssl_context(
        self,
        service_name: str,
        service_type: str,
        purpose: ssl.Purpose = ssl.Purpose.CLIENT_AUTH,
        verify_mode: ssl.VerifyMode = ssl.CERT_REQUIRED,
    ) -> ssl.SSLContext:
        """
        Create an SSL context for a service.

        Args:
            service_name: Name of the service
            service_type: Type of service
            purpose: SSL purpose (CLIENT_AUTH or SERVER_AUTH)
            verify_mode: Certificate verification mode

        Returns:
            Configured SSLContext
        """
        service_cert = self.ensure_service_certificate(service_name, service_type)

        # Create context
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT if purpose == ssl.Purpose.SERVER_AUTH else ssl.PROTOCOL_TLS_SERVER)

        # Set minimum TLS version
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2

        # Load service certificate and key
        ctx.load_cert_chain(
            certfile=service_cert.cert_info.cert_path,
            keyfile=service_cert.cert_info.key_path,
        )

        # Load CA for verification
        ctx.load_verify_locations(cafile=self.ca.ca_cert_path)

        # Set verification mode
        ctx.verify_mode = verify_mode
        ctx.check_hostname = False  # We use SPIFFE IDs, not hostnames

        # Restrict cipher suites
        ctx.set_ciphers(
            "ECDHE+AESGCM:DHE+AESGCM:ECDHE+CHACHA20:DHE+CHACHA20"
        )

        logger.debug(
            "ssl_context_created",
            service_name=service_name,
            service_type=service_type,
            purpose=purpose.name,
        )

        return ctx

    # =========================================================================
    # Audit Log Access
    # =========================================================================

    def get_audit_log(
        self,
        limit: int = 100,
        event_type: Optional[str] = None,
        service_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get audit log entries.

        Args:
            limit: Maximum number of entries to return
            event_type: Filter by event type
            service_name: Filter by service name

        Returns:
            List of audit log entries as dicts
        """
        entries = self._audit_log[-limit:]

        if event_type:
            entries = [e for e in entries if e.event_type == event_type]

        if service_name:
            entries = [e for e in entries if e.service_name == service_name]

        return [
            {
                "timestamp": e.timestamp.isoformat(),
                "event_type": e.event_type,
                "service_name": e.service_name,
                "service_type": e.service_type,
                "source_ip": e.source_ip,
                "result": e.result.value,
                "details": e.details,
            }
            for e in entries
        ]

    def get_service_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about registered services.

        Returns:
            Dictionary with service statistics
        """
        now = datetime.now(timezone.utc)
        stats = {
            "total_services": len(self._service_certs),
            "services": [],
            "expiring_soon": 0,
            "expired": 0,
        }

        for registry_key, service_cert in self._service_certs.items():
            service_type, service_name = registry_key.split("/", 1)
            not_after = service_cert.cert_info.not_after
            days_until_expiry = (not_after - now).days

            service_info = {
                "name": service_name,
                "type": service_type,
                "fingerprint": service_cert.cert_info.fingerprint_sha256[:16] + "...",
                "not_after": not_after.isoformat(),
                "days_until_expiry": days_until_expiry,
                "rotation_count": service_cert.rotation_count,
            }

            stats["services"].append(service_info)

            if days_until_expiry < 0:
                stats["expired"] += 1
            elif days_until_expiry <= MIN_CERT_VALIDITY_DAYS:
                stats["expiring_soon"] += 1

        return stats


# =============================================================================
# FastAPI Middleware
# =============================================================================

class MTLSAuthMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for mTLS authentication.

    Authenticates requests using mTLS headers and adds
    ServiceIdentity to request state.
    """

    def __init__(
        self,
        app,
        mtls_service: MTLSService,
        exclude_paths: Optional[List[str]] = None,
        require_auth: bool = True,
    ):
        """
        Initialize the middleware.

        Args:
            app: FastAPI application
            mtls_service: MTLSService instance
            exclude_paths: Paths to exclude from authentication
            require_auth: Whether authentication is required
        """
        super().__init__(app)
        self.mtls_service = mtls_service
        self.exclude_paths = exclude_paths or [
            "/health",
            "/ready",
            "/metrics",
            "/docs",
            "/openapi.json",
        ]
        self.require_auth = require_auth

    async def dispatch(self, request: Request, call_next):
        """Process the request."""
        # Check if path is excluded
        if any(request.url.path.startswith(p) for p in self.exclude_paths):
            return await call_next(request)

        try:
            # Authenticate request
            identity = self.mtls_service.authenticate_request(request)

            # Add identity to request state
            request.state.service_identity = identity

        except HTTPException as e:
            if self.require_auth:
                raise
            # If auth not required, continue without identity
            request.state.service_identity = None

        return await call_next(request)


# =============================================================================
# Dependency Injection
# =============================================================================

def get_service_identity(request: Request) -> ServiceIdentity:
    """
    FastAPI dependency to get authenticated service identity.

    Usage:
        @app.get("/internal/data")
        def get_data(identity: ServiceIdentity = Depends(get_service_identity)):
            ...
    """
    identity = getattr(request.state, "service_identity", None)

    if identity is None:
        raise HTTPException(
            status_code=401,
            detail="Service-Authentifizierung erforderlich",
        )

    return identity


def require_service_type(*allowed_types: str):
    """
    FastAPI dependency factory to require specific service types.

    Usage:
        @app.get("/internal/admin")
        def admin_endpoint(
            identity: ServiceIdentity = Depends(require_service_type("backend", "admin"))
        ):
            ...
    """
    def dependency(identity: ServiceIdentity = functools.partial(get_service_identity)):
        if identity.service_type not in allowed_types:
            raise HTTPException(
                status_code=403,
                detail=f"Zugriff nur für Service-Typen: {', '.join(allowed_types)}",
            )
        return identity

    return dependency


# =============================================================================
# Module-Level Instance
# =============================================================================

_mtls_service_instance: Optional[MTLSService] = None


def get_mtls_service(
    certs_dir: Optional[Path] = None,
    trust_domain: str = SPIFFE_TRUST_DOMAIN,
) -> MTLSService:
    """
    Get or create the mTLS service instance.

    Args:
        certs_dir: Directory for certificates
        trust_domain: SPIFFE trust domain

    Returns:
        MTLSService instance
    """
    global _mtls_service_instance

    if _mtls_service_instance is None:
        _mtls_service_instance = MTLSService(
            certs_dir=certs_dir,
            trust_domain=trust_domain,
        )

    return _mtls_service_instance
