# -*- coding: utf-8 -*-
"""
Mustang REST Client.

HTTP-Client fuer den Mustang E-Invoice Microservice.
Ermoeglicht XRechnung UBL-Generierung und KoSIT-Validierung.

Mustang-Service laeuft als Docker Container auf Port 8091.
"""

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class MustangError(Exception):
    """Fehler bei Mustang-Operationen."""
    pass


class MustangConnectionError(MustangError):
    """Verbindungsfehler zum Mustang-Service."""
    pass


class MustangValidationError(MustangError):
    """Validierungsfehler von Mustang."""
    pass


class XRechnungFormat(str, Enum):
    """XRechnung XML-Format."""
    CII = "cii"  # UN/CEFACT Cross Industry Invoice
    UBL = "ubl"  # Universal Business Language 2.1


@dataclass
class MustangVersion:
    """Mustang-Versionsinformationen."""
    mustang_version: str
    java_version: str


@dataclass
class ValidationResult:
    """Ergebnis einer Validierung."""
    valid: bool
    output: Optional[str] = None
    errors: Optional[str] = None
    schema_valid: Optional[bool] = None
    schematron_valid: Optional[bool] = None


@dataclass
class ExtractResult:
    """Ergebnis einer XML-Extraktion aus PDF."""
    success: bool
    xml: Optional[str] = None
    output: Optional[str] = None
    errors: Optional[str] = None


class MustangClient:
    """
    Async HTTP-Client fuer den Mustang E-Invoice Service.

    Der Mustang-Service bietet:
    - XRechnung UBL-Generierung (nicht moeglich mit factur-x)
    - KoSIT-Validierung fuer XRechnung
    - ZUGFeRD XML-Extraktion aus PDF
    - Format-Konvertierung

    Usage:
        async with MustangClient() as client:
            version = await client.get_version()
            result = await client.validate_xml(xml_content)
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 60.0,
    ):
        """
        Initialisiert den Mustang-Client.

        Args:
            base_url: Basis-URL des Mustang-Service (default: aus settings)
            timeout: Timeout fuer HTTP-Anfragen in Sekunden
        """
        self.base_url = base_url or getattr(
            settings, "MUSTANG_SERVICE_URL", "http://einvoice-mustang:8091"
        )
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "MustangClient":
        """Context-Manager Eintritt."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context-Manager Austritt."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        """Gibt den HTTP-Client zurueck oder erstellt einen neuen."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    async def is_available(self) -> bool:
        """
        Prueft ob der Mustang-Service erreichbar ist.

        Returns:
            True wenn Service erreichbar
        """
        try:
            client = self._get_client()
            response = await client.get("/health")
            return response.status_code == 200
        except (httpx.RequestError, httpx.TimeoutException):
            return False

    async def get_version(self) -> MustangVersion:
        """
        Ruft Versionsinformationen vom Mustang-Service ab.

        Returns:
            MustangVersion mit Mustang- und Java-Version

        Raises:
            MustangConnectionError: Bei Verbindungsproblemen
        """
        try:
            client = self._get_client()
            response = await client.get("/version")
            response.raise_for_status()
            data = response.json()

            return MustangVersion(
                mustang_version=data.get("mustang_version", "unbekannt"),
                java_version=data.get("java_version", "unbekannt"),
            )

        except httpx.RequestError as e:
            logger.error("mustang_connection_error", extra={"error": str(e)})
            raise MustangConnectionError(
                f"Verbindung zum Mustang-Service fehlgeschlagen: {e}"
            ) from e

    async def get_supported_formats(self) -> dict:
        """
        Ruft unterstuetzte Formate vom Service ab.

        Returns:
            Dictionary mit Formaten und Profilen
        """
        try:
            client = self._get_client()
            response = await client.get("/formats")
            response.raise_for_status()
            return response.json()

        except httpx.RequestError as e:
            logger.error("mustang_formats_error", extra={"error": str(e)})
            raise MustangConnectionError(
                f"Fehler beim Abrufen der Formate: {e}"
            ) from e

    async def validate_xml(
        self,
        xml_content: str,
        format_type: Optional[str] = None,
    ) -> ValidationResult:
        """
        Validiert XML mit dem KoSIT-Validator.

        Args:
            xml_content: XML-Inhalt als String
            format_type: Optional - Format-Hint (zugferd/xrechnung)

        Returns:
            ValidationResult mit Validierungsergebnis

        Raises:
            MustangConnectionError: Bei Verbindungsproblemen
        """
        try:
            client = self._get_client()

            headers = {"Content-Type": "application/xml"}
            if format_type:
                headers["X-Format-Type"] = format_type

            response = await client.post(
                "/validate",
                content=xml_content.encode("utf-8"),
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

            return ValidationResult(
                valid=data.get("valid", False),
                output=data.get("output"),
                errors=data.get("errors"),
                schema_valid=data.get("schema_valid"),
                schematron_valid=data.get("schematron_valid"),
            )

        except httpx.RequestError as e:
            logger.error("mustang_validate_error", extra={"error": str(e)})
            raise MustangConnectionError(
                f"Fehler bei der Validierung: {e}"
            ) from e

    async def extract_xml_from_pdf(
        self,
        pdf_content: bytes,
    ) -> ExtractResult:
        """
        Extrahiert XML aus einem ZUGFeRD-PDF.

        Args:
            pdf_content: PDF-Datei als Bytes

        Returns:
            ExtractResult mit extrahiertem XML

        Raises:
            MustangConnectionError: Bei Verbindungsproblemen
        """
        try:
            client = self._get_client()

            response = await client.post(
                "/extract",
                content=pdf_content,
                headers={"Content-Type": "application/pdf"},
            )
            response.raise_for_status()
            data = response.json()

            return ExtractResult(
                success=data.get("success", False),
                xml=data.get("xml"),
                output=data.get("output"),
                errors=data.get("errors"),
            )

        except httpx.RequestError as e:
            logger.error("mustang_extract_error", extra={"error": str(e)})
            raise MustangConnectionError(
                f"Fehler bei der Extraktion: {e}"
            ) from e

    async def generate_xrechnung_ubl(
        self,
        invoice_data: dict,
        leitweg_id: str,
    ) -> str:
        """
        Generiert XRechnung im UBL-Format.

        Dies ist die Hauptfunktion fuer B2G-Rechnungen,
        da UBL nur ueber Mustang generiert werden kann.

        Args:
            invoice_data: Rechnungsdaten als Dictionary
            leitweg_id: Leitweg-ID (BT-10) - Pflichtfeld fuer B2G

        Returns:
            XRechnung XML im UBL-Format

        Raises:
            MustangConnectionError: Bei Verbindungsproblemen
            MustangValidationError: Bei ungültigen Daten
        """
        try:
            client = self._get_client()

            # Leitweg-ID in Daten sicherstellen
            invoice_data["buyer_reference"] = leitweg_id

            response = await client.post(
                "/generate/xrechnung",
                json={
                    "format": "ubl",
                    "invoice_data": invoice_data,
                },
            )

            if response.status_code == 501:
                # Service noch nicht vollstaendig implementiert
                data = response.json()
                raise MustangError(data.get("message", "UBL-Generierung nicht verfügbar"))

            response.raise_for_status()
            data = response.json()

            if not data.get("success"):
                raise MustangValidationError(
                    data.get("message", "XRechnung-Generierung fehlgeschlagen")
                )

            return data.get("xml", "")

        except httpx.RequestError as e:
            logger.error("mustang_generate_ubl_error", extra={"error": str(e)})
            raise MustangConnectionError(
                f"Fehler bei der UBL-Generierung: {e}"
            ) from e

    async def convert_format(
        self,
        xml_content: str,
        source_format: XRechnungFormat,
        target_format: XRechnungFormat,
    ) -> str:
        """
        Konvertiert zwischen CII und UBL Format.

        Args:
            xml_content: Quell-XML
            source_format: Ausgangsformat (CII/UBL)
            target_format: Zielformat (CII/UBL)

        Returns:
            Konvertiertes XML

        Raises:
            MustangConnectionError: Bei Verbindungsproblemen
            MustangError: Bei Konvertierungsfehlern
        """
        try:
            client = self._get_client()

            response = await client.post(
                "/convert",
                json={
                    "xml": xml_content,
                    "source_format": source_format.value,
                    "target_format": target_format.value,
                },
            )

            if response.status_code == 501:
                data = response.json()
                raise MustangError(data.get("message", "Konvertierung nicht implementiert"))

            response.raise_for_status()
            data = response.json()

            if not data.get("success"):
                raise MustangError(
                    data.get("message", "Konvertierung fehlgeschlagen")
                )

            return data.get("xml", "")

        except httpx.RequestError as e:
            logger.error("mustang_convert_error", extra={"error": str(e)})
            raise MustangConnectionError(
                f"Fehler bei der Konvertierung: {e}"
            ) from e


# Singleton-Instanz fuer einfachen Zugriff
_mustang_client: Optional[MustangClient] = None


def get_mustang_client() -> MustangClient:
    """
    Gibt eine Singleton-Instanz des Mustang-Clients zurueck.

    Usage:
        client = get_mustang_client()
        async with client:
            result = await client.validate_xml(xml)
    """
    global _mustang_client
    if _mustang_client is None:
        _mustang_client = MustangClient()
    return _mustang_client


async def check_mustang_availability() -> bool:
    """
    Prueft ob der Mustang-Service verfuegbar ist.

    Utility-Funktion fuer Health-Checks.

    Returns:
        True wenn Service erreichbar
    """
    client = get_mustang_client()
    try:
        async with client:
            return await client.is_available()
    except Exception:
        return False
