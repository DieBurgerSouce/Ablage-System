# -*- coding: utf-8 -*-
"""
Peppol Sender Service - E-Invoice Transmission via Peppol Network.

Implementiert den Versand von E-Rechnungen über das Peppol-Netzwerk:
- SMP (Service Metadata Publisher) Lookup
- AS4 Message Preparation
- Transmission Tracking
- Acknowledgment Handling
- Email Fallback

Referenzen:
- Peppol BIS Billing 3.0
- Peppol AS4 Profile
- EN 16931 (XRechnung)

SECURITY: Credentials werden aus Environment-Variablen geladen.
"""

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID

try:
    import aiohttp
except ImportError:
    aiohttp = None  # type: ignore[assignment]
import structlog
from lxml import etree
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.safe_errors import safe_error_log, safe_error_detail
from app.db.models import EInvoiceDocument

logger = structlog.get_logger(__name__)


# =============================================================================
# CONSTANTS & CONFIGURATION
# =============================================================================

# Peppol Document Type Identifiers (BIS 3.0)
PEPPOL_DOCUMENT_TYPES = {
    "invoice": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2::Invoice##urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0::2.1",
    "credit_note": "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2::CreditNote##urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0::2.1",
    "xrechnung_cii": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100::CrossIndustryInvoice##urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0::D16B",
    "xrechnung_ubl": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2::Invoice##urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0::2.1",
}

# Peppol Process ID
PEPPOL_PROCESS_ID = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"

# German Participant ID Scheme (Leitweg-ID)
LEITWEG_SCHEME_ID = "0204"

# Peppol SML (Service Metadata Locator) - Production vs Test
PEPPOL_SML_PRODUCTION = "edelivery.tech.ec.europa.eu"
PEPPOL_SML_TEST = "acc.edelivery.tech.ec.europa.eu"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class PeppolEndpoint:
    """Peppol Endpoint Information from SMP."""
    participant_id: str
    endpoint_url: str
    certificate: Optional[str] = None
    transport_protocol: str = "peppol-transport-as4-v2_0"
    document_types: List[str] = field(default_factory=list)
    is_active: bool = True
    last_verified: Optional[datetime] = None


@dataclass
class TransmissionResult:
    """Result of a transmission attempt."""
    success: bool
    message_id: Optional[str] = None
    conversation_id: Optional[str] = None
    channel: str = "peppol"
    sent_at: Optional[datetime] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    retry_allowed: bool = True


@dataclass
class PeppolMessage:
    """Prepared Peppol AS4 Message."""
    message_id: str
    conversation_id: str
    sender_id: str
    receiver_id: str
    document_type_id: str
    process_id: str
    payload: bytes
    payload_hash: str
    created_at: datetime


# =============================================================================
# PEPPOL SENDER SERVICE
# =============================================================================

class PeppolSenderService:
    """
    Service für den Versand von E-Rechnungen über Peppol.

    Usage:
        sender = PeppolSenderService()

        # Peppol-Fähigkeit prüfen
        can_send = await sender.check_peppol_capability(leitweg_id)

        # E-Rechnung senden
        result = await sender.send_einvoice(einvoice_id, db)

        # Status abfragen
        status = await sender.check_transmission_status(message_id)
    """

    def __init__(self) -> None:
        """Initialisiere Peppol Sender Service."""
        self._access_point_url: Optional[str] = None
        self._sender_id: Optional[str] = None
        self._client_certificate: Optional[str] = None
        self._is_production: bool = False
        self._load_config()

    def _load_config(self) -> None:
        """Laedt Peppol-Konfiguration aus Settings."""
        # Access Point URL (Peppol Service Provider)
        self._access_point_url = getattr(settings, "PEPPOL_ACCESS_POINT_URL", None)

        # Eigene Peppol Participant ID
        self._sender_id = getattr(settings, "PEPPOL_SENDER_ID", None)

        # Client Certificate für AS4
        self._client_certificate = getattr(settings, "PEPPOL_CLIENT_CERTIFICATE", None)

        # Production vs Test
        self._is_production = getattr(settings, "PEPPOL_PRODUCTION", False)

        if self._access_point_url:
            logger.info(
                "peppol_sender_initialized",
                access_point=self._access_point_url[:50] + "..." if len(self._access_point_url) > 50 else self._access_point_url,
                production=self._is_production,
            )
        else:
            logger.warning("peppol_sender_not_configured")

    @property
    def is_configured(self) -> bool:
        """Prüft ob Peppol konfiguriert ist."""
        return bool(self._access_point_url and self._sender_id)

    async def check_peppol_capability(
        self,
        leitweg_id: str,
        document_type: str = "invoice"
    ) -> Tuple[bool, Optional[PeppolEndpoint]]:
        """
        Prüft ob ein Empfänger Peppol-fähig ist (SMP Lookup).

        Args:
            leitweg_id: Leitweg-ID des Empfängers (BT-10)
            document_type: Dokumenttyp (invoice, credit_note, xrechnung_cii)

        Returns:
            Tuple aus (can_receive, endpoint_info)
        """
        if not leitweg_id:
            return False, None

        # Participant ID konstruieren
        participant_id = f"{LEITWEG_SCHEME_ID}:{leitweg_id}"

        try:
            endpoint = await self._lookup_smp(participant_id, document_type)
            if endpoint and endpoint.is_active:
                logger.info(
                    "peppol_capability_found",
                    leitweg_id=leitweg_id,
                    endpoint=endpoint.endpoint_url[:50] if endpoint.endpoint_url else None,
                )
                return True, endpoint
            return False, None

        except Exception as e:
            logger.warning(
                "peppol_capability_check_failed",
                leitweg_id=leitweg_id,
                **safe_error_log(e)
            )
            return False, None

    async def _lookup_smp(
        self,
        participant_id: str,
        document_type: str
    ) -> Optional[PeppolEndpoint]:
        """
        SMP (Service Metadata Publisher) Lookup.

        Verwendet den offiziellen Peppol SMP DNS-basierten Discovery.
        """
        # Hash für DNS Lookup
        participant_hash = hashlib.md5(participant_id.lower().encode()).hexdigest()

        # SML Domain
        sml_domain = PEPPOL_SML_PRODUCTION if self._is_production else PEPPOL_SML_TEST

        # SMP URL konstruieren
        smp_url = f"https://B-{participant_hash}.iso6523-actorid-upis.{sml_domain}"

        # Document Type ID
        doc_type_id = PEPPOL_DOCUMENT_TYPES.get(document_type)
        if not doc_type_id:
            doc_type_id = PEPPOL_DOCUMENT_TYPES["invoice"]

        # URL-encoded document type
        import urllib.parse
        doc_type_encoded = urllib.parse.quote(doc_type_id, safe="")

        # Service Metadata URL
        metadata_url = f"{smp_url}/services/{doc_type_encoded}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    metadata_url,
                    timeout=aiohttp.ClientTimeout(total=30),
                    headers={"Accept": "application/xml"}
                ) as response:
                    if response.status == 200:
                        xml_content = await response.text()
                        return self._parse_smp_response(xml_content, participant_id)
                    elif response.status == 404:
                        logger.debug(
                            "peppol_participant_not_found",
                            participant_id=participant_id,
                        )
                        return None
                    else:
                        logger.warning(
                            "peppol_smp_lookup_error",
                            status=response.status,
                            participant_id=participant_id,
                        )
                        return None

        except aiohttp.ClientError as e:
            logger.warning(
                "peppol_smp_connection_error",
                **safe_error_log(e)
            )
            return None

    def _parse_smp_response(
        self,
        xml_content: str,
        participant_id: str
    ) -> Optional[PeppolEndpoint]:
        """Parst SMP Response und extrahiert Endpoint-Informationen."""
        try:
            # Sichere XML-Parsing
            parser = etree.XMLParser(resolve_entities=False, no_network=True)
            root = etree.fromstring(xml_content.encode(), parser=parser)

            # Namespace handling
            nsmap = {
                "smp": "http://docs.oasis-open.org/bdxr/ns/SMP/2016/05",
                "ds": "http://www.w3.org/2000/09/xmldsig#"
            }

            # Endpoint extrahieren
            endpoint_elem = root.find(".//smp:Endpoint", nsmap)
            if endpoint_elem is None:
                # Alternativer Namespace
                endpoint_elem = root.find(".//{*}Endpoint")

            if endpoint_elem is not None:
                endpoint_url = endpoint_elem.get("endpointURI") or endpoint_elem.find(".//{*}EndpointURI")
                if hasattr(endpoint_url, 'text'):
                    endpoint_url = endpoint_url.text

                # Certificate extrahieren
                cert_elem = root.find(".//smp:Certificate", nsmap) or root.find(".//{*}Certificate")
                certificate = cert_elem.text if cert_elem is not None else None

                return PeppolEndpoint(
                    participant_id=participant_id,
                    endpoint_url=str(endpoint_url) if endpoint_url else "",
                    certificate=certificate,
                    is_active=True,
                    last_verified=datetime.now(timezone.utc),
                )

            return None

        except Exception as e:
            logger.warning("peppol_smp_parse_error", **safe_error_log(e))
            return None

    async def send_einvoice(
        self,
        einvoice_id: UUID,
        db: AsyncSession,
        fallback_email: Optional[str] = None,
    ) -> TransmissionResult:
        """
        Sendet eine E-Rechnung über Peppol oder Email-Fallback.

        Args:
            einvoice_id: EInvoiceDocument ID
            db: Database Session
            fallback_email: Email für Fallback wenn Peppol nicht möglich

        Returns:
            TransmissionResult mit Status
        """
        from app.db.models_einvoice import EInvoiceTransmission, EInvoiceTransmissionStatus, EInvoiceTransmissionChannel

        # E-Invoice laden
        query = select(EInvoiceDocument).where(EInvoiceDocument.id == einvoice_id)
        result = await db.execute(query)
        einvoice = result.scalar_one_or_none()

        if not einvoice:
            return TransmissionResult(
                success=False,
                error="E-Rechnung nicht gefunden",
                error_code="EINVOICE_NOT_FOUND",
                retry_allowed=False
            )

        if not einvoice.xml_content:
            return TransmissionResult(
                success=False,
                error="Kein XML-Inhalt vorhanden",
                error_code="NO_XML_CONTENT",
                retry_allowed=False
            )

        # Leitweg-ID ermitteln
        leitweg_id = einvoice.leitweg_id
        if not leitweg_id:
            # Versuche aus XML zu extrahieren
            leitweg_id = self._extract_leitweg_id(einvoice.xml_content)

        # Peppol-Fähigkeit prüfen
        can_peppol, endpoint = await self.check_peppol_capability(leitweg_id) if leitweg_id else (False, None)

        # Transmission Record erstellen
        transmission = EInvoiceTransmission(
            einvoice_id=einvoice_id,
            channel=EInvoiceTransmissionChannel.PEPPOL.value if can_peppol else EInvoiceTransmissionChannel.EMAIL.value,
            status=EInvoiceTransmissionStatus.QUEUED.value,
            queued_at=datetime.now(timezone.utc),
            company_id=einvoice.document.owner_id if einvoice.document else None,  # Company aus Document
        )
        db.add(transmission)
        await db.flush()

        try:
            if can_peppol and endpoint and self.is_configured:
                # Peppol-Versand
                result = await self._send_via_peppol(einvoice, endpoint, transmission)
            elif fallback_email:
                # Email-Fallback
                result = await self._send_via_email(einvoice, fallback_email, transmission)
            else:
                return TransmissionResult(
                    success=False,
                    error="Weder Peppol noch Email-Fallback verfügbar",
                    error_code="NO_CHANNEL_AVAILABLE",
                    retry_allowed=False
                )

            # Transmission Status aktualisieren
            if result.success:
                transmission.status = EInvoiceTransmissionStatus.SENT.value
                transmission.sent_at = result.sent_at
                transmission.peppol_message_id = result.message_id
                transmission.peppol_conversation_id = result.conversation_id
            else:
                transmission.mark_failed(result.error or "Unbekannter Fehler", result.error_code)

            await db.commit()
            return result

        except Exception as e:
            transmission.mark_failed(safe_error_detail(e, "Versand"), "TRANSMISSION_ERROR")
            await db.commit()

            logger.error("peppol_send_failed", **safe_error_log(e))
            return TransmissionResult(
                success=False,
                error=safe_error_detail(e, "Versand"),
                error_code="TRANSMISSION_ERROR",
                retry_allowed=True
            )

    async def _send_via_peppol(
        self,
        einvoice: EInvoiceDocument,
        endpoint: PeppolEndpoint,
        transmission
    ) -> TransmissionResult:
        """Sendet E-Rechnung via Peppol AS4."""
        # Message vorbereiten
        message = self._prepare_as4_message(einvoice, endpoint)

        # Transmission Details setzen
        transmission.peppol_endpoint_id = endpoint.participant_id
        transmission.peppol_document_type = message.document_type_id
        transmission.peppol_process_id = message.process_id

        if not self._access_point_url:
            return TransmissionResult(
                success=False,
                error="Peppol Access Point nicht konfiguriert",
                error_code="AP_NOT_CONFIGURED",
                retry_allowed=False
            )

        try:
            # HTTP Request an Access Point
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Content-Type": "application/soap+xml; charset=utf-8",
                    "X-Peppol-MessageID": message.message_id,
                    "X-Peppol-ConversationID": message.conversation_id,
                    "X-Peppol-SenderID": message.sender_id,
                    "X-Peppol-ReceiverID": message.receiver_id,
                    "X-Peppol-DocumentTypeID": message.document_type_id,
                    "X-Peppol-ProcessID": message.process_id,
                }

                # AS4 Envelope erstellen (vereinfacht)
                soap_envelope = self._create_as4_envelope(message)

                async with session.post(
                    self._access_point_url,
                    data=soap_envelope,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as response:
                    if response.status in (200, 201, 202):
                        logger.info(
                            "peppol_message_sent",
                            message_id=message.message_id,
                            receiver=endpoint.participant_id,
                        )
                        return TransmissionResult(
                            success=True,
                            message_id=message.message_id,
                            conversation_id=message.conversation_id,
                            channel="peppol",
                            sent_at=datetime.now(timezone.utc),
                        )
                    else:
                        error_body = await response.text()
                        return TransmissionResult(
                            success=False,
                            error=f"AS4 Fehler: HTTP {response.status}",
                            error_code=f"AS4_HTTP_{response.status}",
                            retry_allowed=response.status >= 500,
                        )

        except aiohttp.ClientError as e:
            return TransmissionResult(
                success=False,
                error=safe_error_detail(e, "Peppol-Versand"),
                error_code="CONNECTION_ERROR",
                retry_allowed=True,
            )

    def _prepare_as4_message(
        self,
        einvoice: EInvoiceDocument,
        endpoint: PeppolEndpoint
    ) -> PeppolMessage:
        """Bereitet AS4 Message vor."""
        xml_bytes = einvoice.xml_content.encode("utf-8") if einvoice.xml_content else b""

        # Document Type basierend auf Format
        format_str = einvoice.format or "invoice"
        document_type = PEPPOL_DOCUMENT_TYPES.get(
            format_str,
            PEPPOL_DOCUMENT_TYPES["invoice"]
        )

        return PeppolMessage(
            message_id=str(uuid.uuid4()),
            conversation_id=str(uuid.uuid4()),
            sender_id=self._sender_id or "",
            receiver_id=endpoint.participant_id,
            document_type_id=document_type,
            process_id=PEPPOL_PROCESS_ID,
            payload=xml_bytes,
            payload_hash=hashlib.sha256(xml_bytes).hexdigest(),
            created_at=datetime.now(timezone.utc),
        )

    def _create_as4_envelope(self, message: PeppolMessage) -> bytes:
        """Erstellt AS4 SOAP Envelope (vereinfacht)."""
        # Dies ist eine vereinfachte Version
        # In Produktion wuerde ein vollständiges AS4 Message mit WS-Security verwendet
        soap_envelope = f'''<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
               xmlns:eb="http://docs.oasis-open.org/ebxml-msg/ebms/v3.0/ns/core/200704/">
    <soap:Header>
        <eb:Messaging>
            <eb:UserMessage>
                <eb:MessageInfo>
                    <eb:Timestamp>{message.created_at.isoformat()}</eb:Timestamp>
                    <eb:MessageId>{message.message_id}</eb:MessageId>
                </eb:MessageInfo>
                <eb:PartyInfo>
                    <eb:From>
                        <eb:PartyId type="urn:oasis:names:tc:ebcore:partyid-type:iso6523">{message.sender_id}</eb:PartyId>
                        <eb:Role>http://docs.oasis-open.org/ebxml-msg/ebms/v3.0/ns/core/200704/initiator</eb:Role>
                    </eb:From>
                    <eb:To>
                        <eb:PartyId type="urn:oasis:names:tc:ebcore:partyid-type:iso6523">{message.receiver_id}</eb:PartyId>
                        <eb:Role>http://docs.oasis-open.org/ebxml-msg/ebms/v3.0/ns/core/200704/responder</eb:Role>
                    </eb:To>
                </eb:PartyInfo>
                <eb:CollaborationInfo>
                    <eb:AgreementRef>urn:fdc:peppol.eu:2017:agreements:tia:ap_provider</eb:AgreementRef>
                    <eb:Service type="cenbii-procid-ubl">{message.process_id}</eb:Service>
                    <eb:Action>{message.document_type_id}</eb:Action>
                    <eb:ConversationId>{message.conversation_id}</eb:ConversationId>
                </eb:CollaborationInfo>
                <eb:PayloadInfo>
                    <eb:PartInfo href="cid:payload@peppol.eu">
                        <eb:PartProperties>
                            <eb:Property name="MimeType">application/xml</eb:Property>
                            <eb:Property name="CompressionType">application/gzip</eb:Property>
                        </eb:PartProperties>
                    </eb:PartInfo>
                </eb:PayloadInfo>
            </eb:UserMessage>
        </eb:Messaging>
    </soap:Header>
    <soap:Body/>
</soap:Envelope>'''.encode("utf-8")

        return soap_envelope

    async def _send_via_email(
        self,
        einvoice: EInvoiceDocument,
        recipient_email: str,
        transmission
    ) -> TransmissionResult:
        """Sendet E-Rechnung als Email-Fallback."""
        from app.services.email_service import get_email_service

        try:
            email_service = get_email_service()

            # Betreff und Body
            invoice_number = self._extract_invoice_number(einvoice.xml_content or "")
            subject = f"E-Rechnung {invoice_number or einvoice.id}"
            body = f"""Sehr geehrte Damen und Herren,

anbei erhalten Sie eine E-Rechnung im XRechnung-Format.

Diese Rechnung wurde automatisch aus unserem Rechnungssystem generiert
und entspricht dem deutschen Standard für elektronische Rechnungen (XRechnung 3.0).

Rechnungsnummer: {invoice_number or "siehe Anhang"}
Format: {einvoice.format or "XRechnung"}
Profil: {einvoice.profile or "EN16931"}

Die XML-Datei im Anhang kann mit einer XRechnung-fähigen Software
verarbeitet werden.

Mit freundlichen Gruessen
Ihr Rechnungssystem
"""

            # XML als Attachment
            xml_content = einvoice.xml_content or ""
            attachment_name = f"xrechnung_{invoice_number or einvoice.id}.xml"

            # Email senden
            message_id = await email_service.send_email(
                to=recipient_email,
                subject=subject,
                body=body,
                attachments=[{
                    "filename": attachment_name,
                    "content": xml_content.encode("utf-8"),
                    "content_type": "application/xml",
                }]
            )

            # Transmission Details aktualisieren
            transmission.email_recipient = recipient_email
            transmission.email_message_id = message_id
            transmission.email_subject = subject

            logger.info(
                "einvoice_sent_via_email",
                recipient=recipient_email,
                invoice_number=invoice_number,
            )

            return TransmissionResult(
                success=True,
                message_id=message_id,
                channel="email",
                sent_at=datetime.now(timezone.utc),
            )

        except Exception as e:
            return TransmissionResult(
                success=False,
                error=safe_error_detail(e, "Email-Versand"),
                error_code="EMAIL_SEND_ERROR",
                retry_allowed=True,
            )

    async def check_transmission_status(
        self,
        message_id: str
    ) -> Dict[str, Any]:
        """
        Prüft Status einer Peppol-Übertragung.

        In einer vollständigen Implementierung wuerde dies:
        - Access Point API abfragen
        - MDN (Message Disposition Notification) prüfen
        - Delivery Status aktualisieren
        """
        if not self._access_point_url:
            return {"status": "unknown", "error": "Access Point nicht konfiguriert"}

        try:
            async with aiohttp.ClientSession() as session:
                # Status-Endpoint des Access Points (AP-spezifisch)
                status_url = f"{self._access_point_url}/status/{message_id}"

                async with session.get(
                    status_url,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        return {"status": "unknown", "http_status": response.status}

        except Exception as e:
            logger.warning("peppol_status_check_failed", **safe_error_log(e))
            return {"status": "error", "error": safe_error_detail(e, "Statusabfrage")}

    def _extract_leitweg_id(self, xml_content: str) -> Optional[str]:
        """Extrahiert Leitweg-ID (BT-10) aus XML."""
        try:
            parser = etree.XMLParser(resolve_entities=False, no_network=True)
            root = etree.fromstring(xml_content.encode("utf-8"), parser=parser)

            # CII Format
            buyer_ref = root.find(".//{*}BuyerReference")
            if buyer_ref is not None and buyer_ref.text:
                return buyer_ref.text.strip()

            # UBL Format
            buyer_ref = root.find(".//{*}BuyerReference")
            if buyer_ref is not None and buyer_ref.text:
                return buyer_ref.text.strip()

            return None

        except Exception:
            return None

    def _extract_invoice_number(self, xml_content: str) -> Optional[str]:
        """Extrahiert Rechnungsnummer aus XML."""
        try:
            parser = etree.XMLParser(resolve_entities=False, no_network=True)
            root = etree.fromstring(xml_content.encode("utf-8"), parser=parser)

            # Versuche verschiedene Pfade
            for path in [".//{*}ID", ".//{*}InvoiceNumber", ".//{*}DocumentNumber"]:
                elem = root.find(path)
                if elem is not None and elem.text:
                    return elem.text.strip()

            return None

        except Exception:
            return None


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

_peppol_sender_instance: Optional[PeppolSenderService] = None


def get_peppol_sender() -> PeppolSenderService:
    """
    Factory-Funktion für PeppolSenderService (Singleton).

    Returns:
        PeppolSenderService: Globale Instanz
    """
    global _peppol_sender_instance
    if _peppol_sender_instance is None:
        _peppol_sender_instance = PeppolSenderService()
    return _peppol_sender_instance
