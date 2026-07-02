# -*- coding: utf-8 -*-
"""
Certificate Authority (CA) Management for Internal mTLS.

Manages the internal Certificate Authority for service-to-service
authentication using mutual TLS (mTLS).

Features:
- SPIFFE-compatible service identities
- Automatic certificate generation
- Certificate validation and revocation
- On-premises only (no cloud dependencies)

Feinpoliert und durchdacht - Sichere Zertifikatsverwaltung.
"""

import os
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

import structlog
from cryptography import x509
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ec
from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes
from cryptography.hazmat.backends import default_backend

from app.core.config import settings
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# Constants and Configuration
# =============================================================================

# Default certificate paths
DEFAULT_CERTS_DIR = Path("/app/certs/mtls")
CA_KEY_FILE = "ca.key"
CA_CERT_FILE = "ca.crt"
CA_CRL_FILE = "ca.crl"

# Certificate validity periods
CA_VALIDITY_DAYS = 3650  # 10 years for CA
SERVICE_CERT_VALIDITY_DAYS = 30  # 30 days for service certificates
MIN_CERT_VALIDITY_DAYS = 7  # Minimum days before renewal

# Key sizes
CA_KEY_SIZE = 4096  # RSA key size for CA
SERVICE_KEY_SIZE = 2048  # RSA key size for service certificates

# SPIFFE Trust Domain
SPIFFE_TRUST_DOMAIN = "ablage-system.local"

# Allowed service types for certificate generation
ALLOWED_SERVICE_TYPES = frozenset({
    "backend",
    "worker",
    "celery-beat",
    "redis",
    "postgres",
    "minio",
    "frontend",
    "admin",
    "monitoring",
    "vault",
})


class CertificateType(str, Enum):
    """Type of certificate."""
    CA = "ca"
    SERVER = "server"
    CLIENT = "client"
    BOTH = "both"  # Server + Client auth


class KeyAlgorithm(str, Enum):
    """Supported key algorithms."""
    RSA_2048 = "rsa_2048"
    RSA_4096 = "rsa_4096"
    ECDSA_P256 = "ecdsa_p256"
    ECDSA_P384 = "ecdsa_p384"


@dataclass
class CertificateInfo:
    """Information about a generated certificate."""
    serial_number: int
    subject: str
    issuer: str
    not_before: datetime
    not_after: datetime
    fingerprint_sha256: str
    spiffe_id: Optional[str] = None
    certificate_type: CertificateType = CertificateType.CLIENT
    key_algorithm: KeyAlgorithm = KeyAlgorithm.RSA_2048
    cert_path: Optional[Path] = None
    key_path: Optional[Path] = None


@dataclass
class CertificateRequest:
    """Request for a new service certificate."""
    service_name: str
    service_type: str
    validity_days: int = SERVICE_CERT_VALIDITY_DAYS
    certificate_type: CertificateType = CertificateType.BOTH
    key_algorithm: KeyAlgorithm = KeyAlgorithm.RSA_2048
    san_dns: List[str] = field(default_factory=list)
    san_ips: List[str] = field(default_factory=list)


class CertificateAuthorityError(Exception):
    """Exception for CA-related errors."""
    pass


# =============================================================================
# Certificate Authority Implementation
# =============================================================================

class CertificateAuthority:
    """
    Internal Certificate Authority for mTLS.

    Manages certificate generation, validation, and revocation for
    service-to-service authentication.
    """

    def __init__(
        self,
        certs_dir: Optional[Path] = None,
        trust_domain: str = SPIFFE_TRUST_DOMAIN,
    ):
        """
        Initialize the Certificate Authority.

        Args:
            certs_dir: Directory for storing certificates
            trust_domain: SPIFFE trust domain
        """
        self.certs_dir = certs_dir or DEFAULT_CERTS_DIR
        self.trust_domain = trust_domain
        self._ca_key: Optional[PrivateKeyTypes] = None
        self._ca_cert: Optional[x509.Certificate] = None
        self._revoked_serials: set = set()

        # Ensure certs directory exists
        self.certs_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "certificate_authority_initialized",
            certs_dir=str(self.certs_dir),
            trust_domain=self.trust_domain,
        )

    @property
    def ca_key_path(self) -> Path:
        """Path to CA private key."""
        return self.certs_dir / CA_KEY_FILE

    @property
    def ca_cert_path(self) -> Path:
        """Path to CA certificate."""
        return self.certs_dir / CA_CERT_FILE

    @property
    def ca_crl_path(self) -> Path:
        """Path to Certificate Revocation List."""
        return self.certs_dir / CA_CRL_FILE

    def is_initialized(self) -> bool:
        """Check if CA is initialized (has key and cert)."""
        return self.ca_key_path.exists() and self.ca_cert_path.exists()

    def _generate_private_key(
        self,
        algorithm: KeyAlgorithm = KeyAlgorithm.RSA_2048,
    ) -> PrivateKeyTypes:
        """
        Generate a private key.

        Args:
            algorithm: Key algorithm to use

        Returns:
            Generated private key
        """
        if algorithm == KeyAlgorithm.RSA_2048:
            return rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend(),
            )
        elif algorithm == KeyAlgorithm.RSA_4096:
            return rsa.generate_private_key(
                public_exponent=65537,
                key_size=4096,
                backend=default_backend(),
            )
        elif algorithm == KeyAlgorithm.ECDSA_P256:
            return ec.generate_private_key(
                ec.SECP256R1(),
                backend=default_backend(),
            )
        elif algorithm == KeyAlgorithm.ECDSA_P384:
            return ec.generate_private_key(
                ec.SECP384R1(),
                backend=default_backend(),
            )
        else:
            raise CertificateAuthorityError(
                f"Nicht unterstützter Algorithmus: {algorithm}"
            )

    def _save_private_key(
        self,
        key: PrivateKeyTypes,
        path: Path,
        password: Optional[bytes] = None,
    ) -> None:
        """
        Save private key to file with restricted permissions.

        Args:
            key: Private key to save
            path: File path
            password: Optional password for encryption
        """
        encryption = (
            serialization.BestAvailableEncryption(password)
            if password
            else serialization.NoEncryption()
        )

        pem_data = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=encryption,
        )

        # Write with restricted permissions (owner read/write only)
        path.write_bytes(pem_data)
        os.chmod(path, 0o600)

        logger.debug("private_key_saved", path=str(path))

    def _save_certificate(self, cert: x509.Certificate, path: Path) -> None:
        """
        Save certificate to file.

        Args:
            cert: Certificate to save
            path: File path
        """
        pem_data = cert.public_bytes(serialization.Encoding.PEM)
        path.write_bytes(pem_data)
        os.chmod(path, 0o644)

        logger.debug("certificate_saved", path=str(path))

    def _load_private_key(
        self,
        path: Path,
        password: Optional[bytes] = None,
    ) -> PrivateKeyTypes:
        """
        Load private key from file.

        Args:
            path: File path
            password: Optional password for decryption

        Returns:
            Loaded private key
        """
        pem_data = path.read_bytes()
        return serialization.load_pem_private_key(
            pem_data,
            password=password,
            backend=default_backend(),
        )

    def _load_certificate(self, path: Path) -> x509.Certificate:
        """
        Load certificate from file.

        Args:
            path: File path

        Returns:
            Loaded certificate
        """
        pem_data = path.read_bytes()
        return x509.load_pem_x509_certificate(pem_data, default_backend())

    def _get_certificate_fingerprint(self, cert: x509.Certificate) -> str:
        """
        Get SHA-256 fingerprint of certificate.

        Args:
            cert: Certificate

        Returns:
            Hex-encoded fingerprint
        """
        cert_der = cert.public_bytes(serialization.Encoding.DER)
        return hashlib.sha256(cert_der).hexdigest()

    def _generate_serial_number(self) -> int:
        """Generate a cryptographically secure serial number."""
        return secrets.randbits(128)

    def _build_spiffe_id(self, service_name: str, service_type: str) -> str:
        """
        Build SPIFFE ID for a service.

        Args:
            service_name: Name of the service
            service_type: Type of the service

        Returns:
            SPIFFE ID URI
        """
        return f"spiffe://{self.trust_domain}/{service_type}/{service_name}"

    def initialize_ca(
        self,
        validity_days: int = CA_VALIDITY_DAYS,
        force: bool = False,
    ) -> CertificateInfo:
        """
        Initialize the Certificate Authority.

        Creates a new CA key pair and self-signed certificate.

        Args:
            validity_days: CA certificate validity in days
            force: Overwrite existing CA if True

        Returns:
            Information about the created CA certificate

        Raises:
            CertificateAuthorityError: If CA exists and force=False
        """
        if self.is_initialized() and not force:
            raise CertificateAuthorityError(
                "CA existiert bereits. Verwende force=True zum Überschreiben."
            )

        logger.info(
            "initializing_certificate_authority",
            validity_days=validity_days,
            force=force,
        )

        # Generate CA private key (RSA 4096 for CA)
        ca_key = self._generate_private_key(KeyAlgorithm.RSA_4096)

        # Build CA certificate
        now = datetime.now(timezone.utc)
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "DE"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Ablage-System"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Internal CA"),
            x509.NameAttribute(NameOID.COMMON_NAME, f"{self.trust_domain} Internal CA"),
        ])

        serial_number = self._generate_serial_number()

        cert_builder = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(ca_key.public_key())
            .serial_number(serial_number)
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=validity_days))
            # CA extensions
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=0),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=True,
                    crl_sign=True,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),
                critical=False,
            )
        )

        ca_cert = cert_builder.sign(ca_key, hashes.SHA256(), default_backend())

        # Save CA key and certificate
        self._save_private_key(ca_key, self.ca_key_path)
        self._save_certificate(ca_cert, self.ca_cert_path)

        # Cache in memory
        self._ca_key = ca_key
        self._ca_cert = ca_cert

        # Create empty CRL
        self._create_empty_crl()

        fingerprint = self._get_certificate_fingerprint(ca_cert)

        logger.info(
            "certificate_authority_created",
            serial_number=serial_number,
            fingerprint=fingerprint[:16] + "...",
            not_after=ca_cert.not_valid_after_utc.isoformat(),
        )

        return CertificateInfo(
            serial_number=serial_number,
            subject=subject.rfc4514_string(),
            issuer=issuer.rfc4514_string(),
            not_before=ca_cert.not_valid_before_utc,
            not_after=ca_cert.not_valid_after_utc,
            fingerprint_sha256=fingerprint,
            certificate_type=CertificateType.CA,
            key_algorithm=KeyAlgorithm.RSA_4096,
            cert_path=self.ca_cert_path,
            key_path=self.ca_key_path,
        )

    def _create_empty_crl(self) -> None:
        """Create an empty Certificate Revocation List."""
        if self._ca_key is None or self._ca_cert is None:
            raise CertificateAuthorityError("CA nicht initialisiert")

        now = datetime.now(timezone.utc)
        crl_builder = (
            x509.CertificateRevocationListBuilder()
            .issuer_name(self._ca_cert.subject)
            .last_update(now)
            .next_update(now + timedelta(days=7))
        )

        crl = crl_builder.sign(self._ca_key, hashes.SHA256(), default_backend())

        crl_pem = crl.public_bytes(serialization.Encoding.PEM)
        self.ca_crl_path.write_bytes(crl_pem)

        logger.debug("empty_crl_created", path=str(self.ca_crl_path))

    def load_ca(self) -> None:
        """
        Load CA key and certificate from disk.

        Raises:
            CertificateAuthorityError: If CA files don't exist
        """
        if not self.is_initialized():
            raise CertificateAuthorityError(
                "CA nicht initialisiert. Verwende initialize_ca() zuerst."
            )

        self._ca_key = self._load_private_key(self.ca_key_path)
        self._ca_cert = self._load_certificate(self.ca_cert_path)

        # Load revoked serials from CRL
        if self.ca_crl_path.exists():
            crl_pem = self.ca_crl_path.read_bytes()
            crl = x509.load_pem_x509_crl(crl_pem, default_backend())
            for revoked_cert in crl:
                self._revoked_serials.add(revoked_cert.serial_number)

        logger.info(
            "certificate_authority_loaded",
            fingerprint=self._get_certificate_fingerprint(self._ca_cert)[:16] + "...",
            not_after=self._ca_cert.not_valid_after_utc.isoformat(),
            revoked_count=len(self._revoked_serials),
        )

    def ensure_loaded(self) -> None:
        """Ensure CA is loaded, loading from disk if necessary."""
        if self._ca_key is None or self._ca_cert is None:
            self.load_ca()

    def issue_certificate(
        self,
        request: CertificateRequest,
    ) -> Tuple[bytes, bytes, CertificateInfo]:
        """
        Issue a new service certificate.

        Args:
            request: Certificate request parameters

        Returns:
            Tuple of (certificate_pem, key_pem, certificate_info)

        Raises:
            CertificateAuthorityError: If request is invalid
        """
        self.ensure_loaded()

        # Validate service type
        if request.service_type not in ALLOWED_SERVICE_TYPES:
            raise CertificateAuthorityError(
                f"Unbekannter Service-Typ: {request.service_type}. "
                f"Erlaubt: {', '.join(sorted(ALLOWED_SERVICE_TYPES))}"
            )

        # Validate validity period
        if request.validity_days < 1 or request.validity_days > 365:
            raise CertificateAuthorityError(
                f"Ungültige Gültigkeit: {request.validity_days} Tage. "
                "Muss zwischen 1 und 365 Tagen liegen."
            )

        logger.info(
            "issuing_certificate",
            service_name=request.service_name,
            service_type=request.service_type,
            validity_days=request.validity_days,
            cert_type=request.certificate_type.value,
        )

        # Generate service key
        service_key = self._generate_private_key(request.key_algorithm)

        # Build subject name
        now = datetime.now(timezone.utc)
        spiffe_id = self._build_spiffe_id(request.service_name, request.service_type)

        subject = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "DE"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Ablage-System"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, request.service_type),
            x509.NameAttribute(NameOID.COMMON_NAME, f"ablage-{request.service_name}"),
        ])

        serial_number = self._generate_serial_number()

        # Build SAN (Subject Alternative Name)
        san_entries = [
            x509.DNSName("localhost"),
            x509.DNSName(f"ablage-{request.service_name}"),
            x509.DNSName(f"{request.service_name}.ablage.local"),
        ]

        # Add custom DNS entries
        for dns in request.san_dns:
            if dns and dns not in [e.value for e in san_entries if isinstance(e, x509.DNSName)]:
                san_entries.append(x509.DNSName(dns))

        # Add IP addresses
        import ipaddress
        san_entries.append(x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")))
        san_entries.append(x509.IPAddress(ipaddress.IPv6Address("::1")))

        for ip_str in request.san_ips:
            try:
                ip = ipaddress.ip_address(ip_str)
                san_entries.append(x509.IPAddress(ip))
            except ValueError:
                logger.warning("invalid_ip_in_san", ip=ip_str)

        # Add SPIFFE ID as URI
        san_entries.append(x509.UniformResourceIdentifier(spiffe_id))

        # Determine key usage based on certificate type
        if request.certificate_type == CertificateType.SERVER:
            extended_key_usage = [ExtendedKeyUsageOID.SERVER_AUTH]
        elif request.certificate_type == CertificateType.CLIENT:
            extended_key_usage = [ExtendedKeyUsageOID.CLIENT_AUTH]
        else:  # BOTH
            extended_key_usage = [
                ExtendedKeyUsageOID.SERVER_AUTH,
                ExtendedKeyUsageOID.CLIENT_AUTH,
            ]

        # Build certificate
        cert_builder = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(self._ca_cert.subject)
            .public_key(service_key.public_key())
            .serial_number(serial_number)
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=request.validity_days))
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=True,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage(extended_key_usage),
                critical=False,
            )
            .add_extension(
                x509.SubjectAlternativeName(san_entries),
                critical=False,
            )
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(service_key.public_key()),
                critical=False,
            )
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(
                    self._ca_cert.public_key()
                ),
                critical=False,
            )
        )

        # Sign with CA key
        service_cert = cert_builder.sign(self._ca_key, hashes.SHA256(), default_backend())

        # Serialize to PEM
        cert_pem = service_cert.public_bytes(serialization.Encoding.PEM)
        key_pem = service_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )

        fingerprint = self._get_certificate_fingerprint(service_cert)

        logger.info(
            "certificate_issued",
            serial_number=serial_number,
            service_name=request.service_name,
            fingerprint=fingerprint[:16] + "...",
            not_after=service_cert.not_valid_after_utc.isoformat(),
            spiffe_id=spiffe_id,
        )

        cert_info = CertificateInfo(
            serial_number=serial_number,
            subject=subject.rfc4514_string(),
            issuer=self._ca_cert.subject.rfc4514_string(),
            not_before=service_cert.not_valid_before_utc,
            not_after=service_cert.not_valid_after_utc,
            fingerprint_sha256=fingerprint,
            spiffe_id=spiffe_id,
            certificate_type=request.certificate_type,
            key_algorithm=request.key_algorithm,
        )

        return cert_pem, key_pem, cert_info

    def issue_and_save_certificate(
        self,
        request: CertificateRequest,
        output_dir: Optional[Path] = None,
    ) -> CertificateInfo:
        """
        Issue a certificate and save it to disk.

        Args:
            request: Certificate request
            output_dir: Directory to save certificate (default: certs_dir/service_name)

        Returns:
            Certificate information with file paths
        """
        cert_pem, key_pem, cert_info = self.issue_certificate(request)

        # Determine output directory
        if output_dir is None:
            output_dir = self.certs_dir / request.service_type / request.service_name

        output_dir.mkdir(parents=True, exist_ok=True)

        cert_path = output_dir / "cert.pem"
        key_path = output_dir / "key.pem"

        # Save certificate
        cert_path.write_bytes(cert_pem)
        os.chmod(cert_path, 0o644)

        # Save key with restricted permissions
        key_path.write_bytes(key_pem)
        os.chmod(key_path, 0o600)

        # Update cert_info with paths
        cert_info.cert_path = cert_path
        cert_info.key_path = key_path

        logger.info(
            "certificate_saved",
            service_name=request.service_name,
            cert_path=str(cert_path),
            key_path=str(key_path),
        )

        return cert_info

    def revoke_certificate(self, serial_number: int, reason: str = "unspecified") -> None:
        """
        Revoke a certificate by serial number.

        Args:
            serial_number: Certificate serial number to revoke
            reason: Revocation reason
        """
        self.ensure_loaded()

        if serial_number in self._revoked_serials:
            logger.warning("certificate_already_revoked", serial_number=serial_number)
            return

        self._revoked_serials.add(serial_number)

        # Update CRL
        now = datetime.now(timezone.utc)
        crl_builder = (
            x509.CertificateRevocationListBuilder()
            .issuer_name(self._ca_cert.subject)
            .last_update(now)
            .next_update(now + timedelta(days=7))
        )

        # Add all revoked certificates
        for revoked_serial in self._revoked_serials:
            revoked_cert = (
                x509.RevokedCertificateBuilder()
                .serial_number(revoked_serial)
                .revocation_date(now)
                .build()
            )
            crl_builder = crl_builder.add_revoked_certificate(revoked_cert)

        crl = crl_builder.sign(self._ca_key, hashes.SHA256(), default_backend())

        crl_pem = crl.public_bytes(serialization.Encoding.PEM)
        self.ca_crl_path.write_bytes(crl_pem)

        logger.info(
            "certificate_revoked",
            serial_number=serial_number,
            reason=reason,
            total_revoked=len(self._revoked_serials),
        )

    def verify_certificate(
        self,
        cert_pem: bytes,
        check_revocation: bool = True,
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify a certificate against this CA.

        Args:
            cert_pem: Certificate in PEM format
            check_revocation: Check if certificate is revoked

        Returns:
            Tuple of (is_valid, error_message)
        """
        self.ensure_loaded()

        try:
            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
        except Exception as e:
            return False, f"Zertifikat konnte nicht geladen werden: {e}"

        now = datetime.now(timezone.utc)

        # Check validity period
        if cert.not_valid_before_utc > now:
            return False, "Zertifikat ist noch nicht gültig"

        if cert.not_valid_after_utc < now:
            return False, "Zertifikat ist abgelaufen"

        # Check issuer
        if cert.issuer != self._ca_cert.subject:
            return False, "Zertifikat wurde nicht von dieser CA ausgestellt"

        # Check revocation
        if check_revocation and cert.serial_number in self._revoked_serials:
            return False, "Zertifikat wurde widerrufen"

        # Verify signature (simplified - in production use proper chain validation)
        try:
            self._ca_cert.public_key().verify(
                cert.signature,
                cert.tbs_certificate_bytes,
                cert.signature_algorithm_parameters,
            )
        except Exception:
            return False, "Zertifikat-Signatur ungültig"

        return True, None

    def get_ca_certificate_pem(self) -> bytes:
        """Get CA certificate in PEM format."""
        self.ensure_loaded()
        return self._ca_cert.public_bytes(serialization.Encoding.PEM)

    def get_ca_info(self) -> CertificateInfo:
        """Get information about the CA certificate."""
        self.ensure_loaded()

        return CertificateInfo(
            serial_number=self._ca_cert.serial_number,
            subject=self._ca_cert.subject.rfc4514_string(),
            issuer=self._ca_cert.issuer.rfc4514_string(),
            not_before=self._ca_cert.not_valid_before_utc,
            not_after=self._ca_cert.not_valid_after_utc,
            fingerprint_sha256=self._get_certificate_fingerprint(self._ca_cert),
            certificate_type=CertificateType.CA,
            key_algorithm=KeyAlgorithm.RSA_4096,
            cert_path=self.ca_cert_path,
            key_path=self.ca_key_path,
        )

    def get_certificate_info(self, cert_pem: bytes) -> CertificateInfo:
        """
        Parse certificate and return its information.

        Args:
            cert_pem: Certificate in PEM format

        Returns:
            Certificate information
        """
        cert = x509.load_pem_x509_certificate(cert_pem, default_backend())

        # Extract SPIFFE ID from SAN
        spiffe_id = None
        try:
            san_ext = cert.extensions.get_extension_for_class(
                x509.SubjectAlternativeName
            )
            for name in san_ext.value:
                if isinstance(name, x509.UniformResourceIdentifier):
                    if name.value.startswith("spiffe://"):
                        spiffe_id = name.value
                        break
        except x509.ExtensionNotFound:
            pass  # Kein SAN im Zertifikat -> spiffe_id bleibt None

        # Determine certificate type from extended key usage
        cert_type = CertificateType.CLIENT
        try:
            eku_ext = cert.extensions.get_extension_for_class(
                x509.ExtendedKeyUsage
            )
            has_server = ExtendedKeyUsageOID.SERVER_AUTH in eku_ext.value
            has_client = ExtendedKeyUsageOID.CLIENT_AUTH in eku_ext.value

            if has_server and has_client:
                cert_type = CertificateType.BOTH
            elif has_server:
                cert_type = CertificateType.SERVER
            else:
                cert_type = CertificateType.CLIENT
        except x509.ExtensionNotFound:
            pass  # Kein ExtendedKeyUsage -> Default-Typ CLIENT bleibt bestehen

        return CertificateInfo(
            serial_number=cert.serial_number,
            subject=cert.subject.rfc4514_string(),
            issuer=cert.issuer.rfc4514_string(),
            not_before=cert.not_valid_before_utc,
            not_after=cert.not_valid_after_utc,
            fingerprint_sha256=self._get_certificate_fingerprint(cert),
            spiffe_id=spiffe_id,
            certificate_type=cert_type,
        )

    def needs_renewal(
        self,
        cert_pem: bytes,
        threshold_days: int = MIN_CERT_VALIDITY_DAYS,
    ) -> bool:
        """
        Check if a certificate needs renewal.

        Args:
            cert_pem: Certificate in PEM format
            threshold_days: Days before expiry to trigger renewal

        Returns:
            True if certificate needs renewal
        """
        cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
        now = datetime.now(timezone.utc)
        threshold = now + timedelta(days=threshold_days)

        return cert.not_valid_after_utc <= threshold


# =============================================================================
# Module-Level Instance
# =============================================================================

_ca_instance: Optional[CertificateAuthority] = None


def get_certificate_authority(
    certs_dir: Optional[Path] = None,
    trust_domain: str = SPIFFE_TRUST_DOMAIN,
) -> CertificateAuthority:
    """
    Get or create the Certificate Authority instance.

    Args:
        certs_dir: Directory for certificates
        trust_domain: SPIFFE trust domain

    Returns:
        CertificateAuthority instance
    """
    global _ca_instance

    if _ca_instance is None:
        _ca_instance = CertificateAuthority(
            certs_dir=certs_dir,
            trust_domain=trust_domain,
        )

    return _ca_instance
