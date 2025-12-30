# -*- coding: utf-8 -*-
"""
VIES VAT Information Exchange System Service.

Validiert EU-USt-IdNr gegen die offizielle VIES-API der EU-Kommission.
https://ec.europa.eu/taxation_customs/vies/

Feinpoliert und durchdacht - Enterprise VAT Validation.
"""

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

# S.1 SECURITY FIX: defusedxml gegen XXE-Angriffe
from defusedxml.ElementTree import fromstring as safe_xml_fromstring

import httpx
import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

VIES_WSDL_URL = "https://ec.europa.eu/taxation_customs/vies/checkVatService.wsdl"
VIES_SOAP_URL = "https://ec.europa.eu/taxation_customs/vies/services/checkVatService"

# Timeout in Sekunden - VIES kann langsam sein
VIES_TIMEOUT_SECONDS = 10.0

# EU-Mitgliedsstaaten (ISO 3166-1 alpha-2)
EU_COUNTRY_CODES = frozenset({
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI",
    "FR", "GR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT",
    "NL", "PL", "PT", "RO", "SE", "SI", "SK",
    # Sonderfaelle:
    "XI",  # Nordirland (nach Brexit)
})

# VAT-ID Patterns pro Land (vereinfacht)
VAT_ID_PATTERNS = {
    "AT": r"^ATU\d{8}$",
    "BE": r"^BE[01]\d{9}$",
    "BG": r"^BG\d{9,10}$",
    "CY": r"^CY\d{8}[A-Z]$",
    "CZ": r"^CZ\d{8,10}$",
    "DE": r"^DE\d{9}$",
    "DK": r"^DK\d{8}$",
    "EE": r"^EE\d{9}$",
    "ES": r"^ES[A-Z0-9]\d{7}[A-Z0-9]$",
    "FI": r"^FI\d{8}$",
    "FR": r"^FR[A-Z0-9]{2}\d{9}$",
    "GR": r"^EL\d{9}$",  # Griechenland nutzt EL statt GR
    "HR": r"^HR\d{11}$",
    "HU": r"^HU\d{8}$",
    "IE": r"^IE\d{7}[A-Z]{1,2}$",
    "IT": r"^IT\d{11}$",
    "LT": r"^LT(\d{9}|\d{12})$",
    "LU": r"^LU\d{8}$",
    "LV": r"^LV\d{11}$",
    "MT": r"^MT\d{8}$",
    "NL": r"^NL\d{9}B\d{2}$",
    "PL": r"^PL\d{10}$",
    "PT": r"^PT\d{9}$",
    "RO": r"^RO\d{2,10}$",
    "SE": r"^SE\d{12}$",
    "SI": r"^SI\d{8}$",
    "SK": r"^SK\d{10}$",
    "XI": r"^XI\d{9,12}$",  # Nordirland
}


# =============================================================================
# DATA CLASSES
# =============================================================================

class VIESValidationStatus(str, Enum):
    """Status der VIES-Validierung."""
    VALID = "valid"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    ERROR = "error"
    NOT_EU = "not_eu"


@dataclass(frozen=True)
class VIESValidationResult:
    """
    Ergebnis einer VIES-Validierung.

    Attributes:
        vat_id: Die validierte USt-IdNr
        country_code: Laendercode (z.B. DE)
        vat_number: Nummer ohne Laendercode
        valid: True wenn gueltig
        status: Detaillierter Status
        name: Firmenname (wenn von VIES bereitgestellt)
        address: Adresse (wenn von VIES bereitgestellt)
        request_date: Zeitpunkt der Validierung
        error_message: Fehlermeldung (wenn status == ERROR)
    """
    vat_id: str
    country_code: str
    vat_number: str
    valid: bool
    status: VIESValidationStatus
    name: Optional[str] = None
    address: Optional[str] = None
    request_date: Optional[datetime] = None
    error_message: Optional[str] = None


# =============================================================================
# VIES SERVICE
# =============================================================================

class VIESService:
    """
    EU VIES VAT Information Exchange System Client.

    Validiert USt-IdNr gegen die offizielle VIES-API.

    Usage:
        service = VIESService()
        result = await service.validate_vat_id("DE123456789")

        if result.valid:
            print(f"Gueltige USt-IdNr fuer: {result.name}")
        else:
            print(f"Ungueltig: {result.status}")
    """

    def __init__(
        self,
        timeout: float = VIES_TIMEOUT_SECONDS,
        cache_ttl_seconds: int = 86400,  # 24 Stunden Cache
    ):
        """
        Initialisiert den VIES Service.

        Args:
            timeout: Timeout fuer VIES-Anfragen in Sekunden
            cache_ttl_seconds: Cache-Dauer fuer erfolgreiche Validierungen
        """
        self.timeout = timeout
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[str, tuple[VIESValidationResult, datetime]] = {}

    def _parse_vat_id(self, vat_id: str) -> tuple[str, str]:
        """
        Zerlegt USt-IdNr in Laendercode und Nummer.

        Args:
            vat_id: Vollstaendige USt-IdNr (z.B. DE123456789)

        Returns:
            Tuple (country_code, vat_number)

        Raises:
            ValueError: Bei ungueltigem Format
        """
        # Bereinigen: Leerzeichen und Punkte entfernen
        cleaned = re.sub(r"[\s.\-]", "", vat_id.upper())

        if len(cleaned) < 4:
            raise ValueError(f"USt-IdNr zu kurz: {vat_id}")

        # Erste 2 Zeichen = Laendercode
        country_code = cleaned[:2]
        vat_number = cleaned[2:]

        # Sonderfall Griechenland: EL statt GR
        if country_code == "GR":
            country_code = "EL"

        return country_code, vat_number

    def _is_eu_country(self, country_code: str) -> bool:
        """Prueft ob Laendercode zu EU gehoert."""
        return country_code in EU_COUNTRY_CODES or country_code == "EL"

    def _validate_format(self, vat_id: str, country_code: str) -> bool:
        """
        Validiert das Format der USt-IdNr fuer das jeweilige Land.

        Returns:
            True wenn Format korrekt
        """
        # Mapping EL -> GR fuer Pattern-Lookup
        lookup_code = "GR" if country_code == "EL" else country_code

        pattern = VAT_ID_PATTERNS.get(lookup_code)
        if not pattern:
            # Unbekanntes Land - akzeptieren und VIES entscheiden lassen
            return True

        # Fuer Pattern-Matching: EL zurueck zu EL (da Pattern EL verwendet)
        check_id = vat_id.upper().replace("GR", "EL")
        return bool(re.match(pattern, check_id.replace(" ", "").replace(".", "").replace("-", "")))

    async def validate_vat_id(
        self,
        vat_id: str,
        requester_vat_id: Optional[str] = None,
    ) -> VIESValidationResult:
        """
        Validiert eine USt-IdNr gegen die VIES-API.

        Args:
            vat_id: Zu validierende USt-IdNr (z.B. DE123456789)
            requester_vat_id: Optional - eigene USt-IdNr fuer Beleg-Anfrage

        Returns:
            VIESValidationResult mit Validierungsergebnis
        """
        request_date = datetime.now(timezone.utc)

        try:
            country_code, vat_number = self._parse_vat_id(vat_id)
        except ValueError as e:
            return VIESValidationResult(
                vat_id=vat_id,
                country_code="",
                vat_number="",
                valid=False,
                status=VIESValidationStatus.ERROR,
                request_date=request_date,
                error_message=str(e),
            )

        # Nicht-EU Land
        if not self._is_eu_country(country_code):
            return VIESValidationResult(
                vat_id=vat_id,
                country_code=country_code,
                vat_number=vat_number,
                valid=False,
                status=VIESValidationStatus.NOT_EU,
                request_date=request_date,
                error_message=f"Laendercode {country_code} ist kein EU-Mitgliedsstaat",
            )

        # Format-Validierung
        if not self._validate_format(vat_id, country_code):
            logger.debug(
                "vies_format_invalid",
                vat_id=vat_id[:8] + "***",  # Teilweise maskieren
                country_code=country_code,
            )
            # Format-Fehler bedeutet nicht unbedingt ungueltig - VIES entscheiden lassen

        # Cache pruefen
        cache_key = f"{country_code}{vat_number}"
        if cache_key in self._cache:
            cached_result, cached_time = self._cache[cache_key]
            age = (request_date - cached_time).total_seconds()
            if age < self.cache_ttl_seconds:
                logger.debug(
                    "vies_cache_hit",
                    vat_id=vat_id[:8] + "***",
                    cache_age_seconds=int(age),
                )
                return cached_result

        # SOAP-Request bauen
        soap_request = self._build_soap_request(country_code, vat_number)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    VIES_SOAP_URL,
                    content=soap_request,
                    headers={
                        "Content-Type": "text/xml; charset=utf-8",
                        "SOAPAction": "",
                    },
                )

                if response.status_code != 200:
                    logger.warning(
                        "vies_http_error",
                        status_code=response.status_code,
                        vat_id=vat_id[:8] + "***",
                    )
                    return VIESValidationResult(
                        vat_id=vat_id,
                        country_code=country_code,
                        vat_number=vat_number,
                        valid=False,
                        status=VIESValidationStatus.ERROR,
                        request_date=request_date,
                        error_message=f"VIES HTTP Fehler: {response.status_code}",
                    )

                # Response parsen
                result = self._parse_soap_response(
                    response.text,
                    vat_id,
                    country_code,
                    vat_number,
                    request_date,
                )

                # Cache speichern (nur bei erfolgreichem Request)
                if result.status in (VIESValidationStatus.VALID, VIESValidationStatus.INVALID):
                    self._cache[cache_key] = (result, request_date)

                return result

        except httpx.TimeoutException:
            logger.warning(
                "vies_timeout",
                vat_id=vat_id[:8] + "***",
                timeout=self.timeout,
            )
            return VIESValidationResult(
                vat_id=vat_id,
                country_code=country_code,
                vat_number=vat_number,
                valid=False,
                status=VIESValidationStatus.TIMEOUT,
                request_date=request_date,
                error_message=f"VIES Timeout nach {self.timeout}s",
            )
        except httpx.ConnectError as e:
            logger.warning(
                "vies_connection_error",
                vat_id=vat_id[:8] + "***",
                error=str(e),
            )
            return VIESValidationResult(
                vat_id=vat_id,
                country_code=country_code,
                vat_number=vat_number,
                valid=False,
                status=VIESValidationStatus.UNAVAILABLE,
                request_date=request_date,
                error_message="VIES nicht erreichbar",
            )
        except Exception as e:
            logger.exception(
                "vies_unexpected_error",
                vat_id=vat_id[:8] + "***",
            )
            return VIESValidationResult(
                vat_id=vat_id,
                country_code=country_code,
                vat_number=vat_number,
                valid=False,
                status=VIESValidationStatus.ERROR,
                request_date=request_date,
                error_message=f"Unerwarteter Fehler: {type(e).__name__}",
            )

    def _build_soap_request(self, country_code: str, vat_number: str) -> bytes:
        """Baut SOAP-Request fuer VIES checkVat."""
        # SOAP Envelope fuer checkVat
        soap = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:urn="urn:ec.europa.eu:taxud:vies:services:checkVat:types">
    <soapenv:Header/>
    <soapenv:Body>
        <urn:checkVat>
            <urn:countryCode>{country_code}</urn:countryCode>
            <urn:vatNumber>{vat_number}</urn:vatNumber>
        </urn:checkVat>
    </soapenv:Body>
</soapenv:Envelope>"""
        return soap.encode("utf-8")

    def _parse_soap_response(
        self,
        response_text: str,
        vat_id: str,
        country_code: str,
        vat_number: str,
        request_date: datetime,
    ) -> VIESValidationResult:
        """Parst SOAP-Response von VIES."""
        try:
            # S.1 SECURITY FIX: Sicheres XML-Parsing gegen XXE-Angriffe
            root = safe_xml_fromstring(response_text)

            # Namespaces
            ns = {
                "soap": "http://schemas.xmlsoap.org/soap/envelope/",
                "vies": "urn:ec.europa.eu:taxud:vies:services:checkVat:types",
            }

            # checkVatResponse suchen
            body = root.find(".//soap:Body", ns)
            if body is None:
                raise ValueError("SOAP Body nicht gefunden")

            # Pruefe auf Fault
            fault = body.find(".//soap:Fault", ns)
            if fault is not None:
                fault_string = fault.findtext("faultstring", "Unbekannter Fehler")
                logger.warning(
                    "vies_soap_fault",
                    fault=fault_string,
                    vat_id=vat_id[:8] + "***",
                )
                # Typische Fehler: MS_UNAVAILABLE, SERVICE_UNAVAILABLE
                if "UNAVAILABLE" in fault_string.upper():
                    return VIESValidationResult(
                        vat_id=vat_id,
                        country_code=country_code,
                        vat_number=vat_number,
                        valid=False,
                        status=VIESValidationStatus.UNAVAILABLE,
                        request_date=request_date,
                        error_message=f"VIES nicht verfuegbar: {fault_string}",
                    )
                return VIESValidationResult(
                    vat_id=vat_id,
                    country_code=country_code,
                    vat_number=vat_number,
                    valid=False,
                    status=VIESValidationStatus.ERROR,
                    request_date=request_date,
                    error_message=fault_string,
                )

            # checkVatResponse suchen (verschiedene Pfade)
            vat_response = body.find(".//vies:checkVatResponse", ns)
            if vat_response is None:
                # Fallback ohne Namespace
                vat_response = body.find(".//{urn:ec.europa.eu:taxud:vies:services:checkVat:types}checkVatResponse")

            if vat_response is None:
                logger.warning(
                    "vies_response_parse_failed",
                    response_preview=response_text[:500],
                )
                return VIESValidationResult(
                    vat_id=vat_id,
                    country_code=country_code,
                    vat_number=vat_number,
                    valid=False,
                    status=VIESValidationStatus.ERROR,
                    request_date=request_date,
                    error_message="VIES Response nicht parsebar",
                )

            # Werte extrahieren
            def get_text(elem: Optional[ElementTree.Element], tag: str) -> Optional[str]:
                if elem is None:
                    return None
                child = elem.find(f".//vies:{tag}", ns)
                if child is None:
                    child = elem.find(f".//{{{ns['vies']}}}{tag}")
                return child.text if child is not None else None

            valid_str = get_text(vat_response, "valid")
            valid = valid_str.lower() == "true" if valid_str else False

            name = get_text(vat_response, "name")
            address = get_text(vat_response, "address")

            # Bereinigen
            if name == "---":
                name = None
            if address == "---":
                address = None

            logger.info(
                "vies_validation_completed",
                vat_id=vat_id[:8] + "***",
                valid=valid,
                has_name=name is not None,
            )

            return VIESValidationResult(
                vat_id=vat_id,
                country_code=country_code,
                vat_number=vat_number,
                valid=valid,
                status=VIESValidationStatus.VALID if valid else VIESValidationStatus.INVALID,
                name=name,
                address=address,
                request_date=request_date,
            )

        except ElementTree.ParseError as e:
            logger.warning(
                "vies_xml_parse_error",
                error=str(e),
                response_preview=response_text[:200],
            )
            return VIESValidationResult(
                vat_id=vat_id,
                country_code=country_code,
                vat_number=vat_number,
                valid=False,
                status=VIESValidationStatus.ERROR,
                request_date=request_date,
                error_message=f"XML Parse Fehler: {e}",
            )

    def clear_cache(self) -> int:
        """
        Loescht den Validierungs-Cache.

        Returns:
            Anzahl der geloeschten Eintraege
        """
        count = len(self._cache)
        self._cache.clear()
        return count


# =============================================================================
# SINGLETON ACCESSOR
# =============================================================================

_vies_service: Optional[VIESService] = None


def get_vies_service() -> VIESService:
    """
    Gibt die Singleton-Instanz des VIES Service zurueck.

    Returns:
        VIESService Instanz
    """
    global _vies_service
    if _vies_service is None:
        _vies_service = VIESService()
    return _vies_service
