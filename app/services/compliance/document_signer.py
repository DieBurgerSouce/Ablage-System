# -*- coding: utf-8 -*-
"""Selbst-enthaltener interner Dokument-Signierer (GoBD-Unveraenderbarkeit).

Erzeugt/laedt EINMALIG ein internes RSA-Schluesselpaar + selbst-signiertes Zertifikat
(on-premises, KEIN externes Zertifikat / kein Cloud-Dienst noetig) und signiert
beliebige Bytes (z.B. die PDF-Verfahrensdokumentation) mit RSA-PSS/SHA-256. Die
Signatur ist mit dem mitgelieferten Zertifikat (oeffentlicher Schluessel) verifizierbar
-> tamper-evident. Der private Schluessel wird persistent abgelegt, damit Alt-Signaturen
auch nach Neustarts verifizierbar bleiben.
"""
from __future__ import annotations

import base64
import datetime as _dt
import os
from pathlib import Path
from typing import Dict

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID

# Schluessel/Zertifikat muessen PERSISTENT + SCHREIBBAR liegen (sonst gehen Alt-
# Signaturen nach Neustart verloren). /app/certs ist im Deployment read-only (extern
# provisioniert), daher Default auf ein beschreibbares, persistentes Volume; per
# GOBD_SIGNING_DIR ueberschreibbar (Tests nutzen tmp_path). Hinweis: in Produktion
# idealerweise ein dediziertes Secrets-Volume.
DEFAULT_SIGNING_DIR = Path(os.environ.get("GOBD_SIGNING_DIR", "/app/outputs/gobd_signing"))
SIGNATURE_ALG = "RSA-PSS-SHA256"
_KEY_FILE = "gobd_signer_key.pem"
_CERT_FILE = "gobd_signer_cert.pem"
_PSS = padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH)


class DocumentSigner:
    """Internes RSA-PSS-Signieren + Verifizieren von Dokument-Bytes."""

    def __init__(self, signing_dir: Path | str | None = None) -> None:
        self.signing_dir = Path(signing_dir) if signing_dir else DEFAULT_SIGNING_DIR
        self.signing_dir.mkdir(parents=True, exist_ok=True)
        self._key = None
        self._cert: x509.Certificate | None = None

    @property
    def _key_path(self) -> Path:
        return self.signing_dir / _KEY_FILE

    @property
    def _cert_path(self) -> Path:
        return self.signing_dir / _CERT_FILE

    def _ensure(self) -> None:
        if self._key is not None and self._cert is not None:
            return
        if self._key_path.exists() and self._cert_path.exists():
            self._key = serialization.load_pem_private_key(
                self._key_path.read_bytes(), password=None
            )
            self._cert = x509.load_pem_x509_certificate(self._cert_path.read_bytes())
            return
        self._key, self._cert = self._generate_and_persist()

    def _generate_and_persist(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "GoBD Internal Document Signer"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Ablage-System"),
        ])
        now = _dt.datetime.now(_dt.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - _dt.timedelta(minutes=1))
            .not_valid_after(now + _dt.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=True,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(key, hashes.SHA256())
        )
        # Privater Schluessel nur fuer den Besitzer lesbar ablegen.
        self._key_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        try:
            self._key_path.chmod(0o600)
        except OSError:
            pass
        self._cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        return key, cert

    def sign(self, data: bytes) -> Dict[str, str]:
        """Signiert ``data`` und liefert Signatur (b64), Verfahren, Cert-Serial + Cert-PEM."""
        self._ensure()
        signature = self._key.sign(data, _PSS, hashes.SHA256())
        return {
            "signature": base64.b64encode(signature).decode("ascii"),
            "alg": SIGNATURE_ALG,
            "cert_serial": format(self._cert.serial_number, "x"),
            "cert_pem": self._cert.public_bytes(serialization.Encoding.PEM).decode("ascii"),
        }

    def verify(self, data: bytes, signature_b64: str) -> bool:
        """Prueft die Signatur gegen das interne Zertifikat (tamper-evident)."""
        self._ensure()
        try:
            self._cert.public_key().verify(
                base64.b64decode(signature_b64), data, _PSS, hashes.SHA256()
            )
            return True
        except Exception:
            return False

    @property
    def cert_pem(self) -> str:
        self._ensure()
        return self._cert.public_bytes(serialization.Encoding.PEM).decode("ascii")
