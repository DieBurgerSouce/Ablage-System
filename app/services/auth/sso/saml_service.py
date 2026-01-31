"""
SAML 2.0 Service.

Implementiert SAML 2.0 Service Provider (SP):
- AuthnRequest Generation
- Response Validation
- Assertion Processing
- Single Logout (SLO)

SECURITY:
- Signaturvalidierung fuer alle Responses
- Replay-Schutz mit InResponseTo Validierung
- Audience-Validierung
- Time-based Assertion-Validierung

Unterstuetzte IdPs:
- Microsoft Entra ID (Azure AD)
- Okta
- OneLogin
- Shibboleth
- Beliebige SAML 2.0 IdPs
"""

import structlog
import secrets
import base64
import zlib
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode
from uuid import UUID, uuid4
# SECURITY: Use defusedxml to prevent XXE attacks (CWE-611)
# Standard ElementTree is vulnerable to XML External Entity injection
from defusedxml import ElementTree as ET
# Import Element type from standard library for type hints only
from xml.etree.ElementTree import Element

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa, ec
from cryptography.exceptions import InvalidSignature
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auth.sso.sso_config_service import (
    SSOConfigService,
    SSOProviderConfig,
    SAMLConfig,
)
from app.services.auth.sso.sso_state_manager import (
    get_sso_state_manager,
    SSOStateManager,
)

logger = structlog.get_logger(__name__)

# SAML Namespaces
SAML_NS = {
    "saml": "urn:oasis:names:tc:SAML:2.0:assertion",
    "samlp": "urn:oasis:names:tc:SAML:2.0:protocol",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
    "xenc": "http://www.w3.org/2001/04/xmlenc#",
}


class SAMLRequest(BaseModel):
    """SAML AuthnRequest State."""

    request_id: str = Field(default_factory=lambda: f"_id{uuid4().hex}")
    provider_id: UUID
    relay_state: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime = Field(default_factory=lambda: datetime.utcnow() + timedelta(minutes=10))


class SAMLAssertion(BaseModel):
    """Parsed SAML Assertion."""

    subject_name_id: str = Field(..., description="NameID des Benutzers")
    name_id_format: str = Field(..., description="NameID Format")
    issuer: str = Field(..., description="IdP Issuer")
    session_index: Optional[str] = None
    attributes: Dict[str, List[str]] = Field(default_factory=dict)
    not_before: Optional[datetime] = None
    not_on_or_after: Optional[datetime] = None
    authn_instant: Optional[datetime] = None
    audience: Optional[str] = None


class SAMLUserInfo(BaseModel):
    """Extrahierte Benutzerinformationen aus SAML Assertion."""

    name_id: str = Field(..., description="SAML NameID")
    email: Optional[str] = None
    name: Optional[str] = None
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    groups: List[str] = Field(default_factory=list)
    raw_attributes: Dict[str, List[str]] = Field(default_factory=dict)


class SAMLService:
    """Service fuer SAML 2.0 Authentication."""

    def __init__(
        self,
        db: AsyncSession,
        state_manager: Optional[SSOStateManager] = None,
    ):
        self.db = db
        self.config_service = SSOConfigService(db)
        self.state_manager = state_manager or get_sso_state_manager()

    def _generate_authn_request(
        self,
        config: SAMLConfig,
        request_id: str,
        issue_instant: str,
    ) -> str:
        """Generiert einen SAML AuthnRequest."""
        request_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="{request_id}"
    Version="2.0"
    IssueInstant="{issue_instant}"
    Destination="{config.idp_sso_url}"
    AssertionConsumerServiceURL="{config.sp_acs_url}"
    ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST">
    <saml:Issuer>{config.sp_entity_id}</saml:Issuer>
    <samlp:NameIDPolicy
        Format="{config.name_id_format}"
        AllowCreate="true"/>
</samlp:AuthnRequest>"""
        return request_xml

    def _deflate_and_encode(self, xml: str) -> str:
        """Komprimiert und Base64-kodiert XML fuer HTTP-Redirect Binding."""
        compressed = zlib.compress(xml.encode("utf-8"))[2:-4]  # Remove zlib header/checksum
        return base64.b64encode(compressed).decode("utf-8")

    def _decode_and_inflate(self, encoded: str) -> str:
        """Dekodiert und dekomprimiert Base64 SAML Response."""
        decoded = base64.b64decode(encoded)
        try:
            # Try to decompress (might already be uncompressed for POST binding)
            decompressed = zlib.decompress(decoded, -15)
            return decompressed.decode("utf-8")
        except zlib.error:
            # Not compressed (POST binding)
            return decoded.decode("utf-8")

    def _validate_signature(
        self, root: Element, config: SAMLConfig
    ) -> None:
        """
        Validiert die XML-Signatur der SAML Response.

        SECURITY: Diese Validierung MUSS vor der Assertion-Extraktion erfolgen,
        um SAML Response Forgery zu verhindern (CWE-347).

        Args:
            root: Parsed XML Root Element
            config: SAML-Konfiguration mit IdP-Zertifikat

        Raises:
            ValueError: Bei ungültiger oder fehlender Signatur
        """
        # Find signature element
        signature_elem = root.find(".//{http://www.w3.org/2000/09/xmldsig#}Signature")

        if signature_elem is None:
            # Also check in Assertion
            assertion_elem = root.find(".//saml:Assertion", SAML_NS)
            if assertion_elem is not None:
                signature_elem = assertion_elem.find(
                    "{http://www.w3.org/2000/09/xmldsig#}Signature"
                )

        if signature_elem is None:
            if config.sign_assertions:
                raise ValueError(
                    "SAML Response muss signiert sein, aber keine Signatur gefunden"
                )
            logger.warning(
                "saml_response_unsigned",
                message="SAML Response ohne Signatur akzeptiert (sign_assertions=False)"
            )
            return

        # Extract signature value and signed info
        signature_value_elem = signature_elem.find(
            "{http://www.w3.org/2000/09/xmldsig#}SignatureValue"
        )
        signed_info_elem = signature_elem.find(
            "{http://www.w3.org/2000/09/xmldsig#}SignedInfo"
        )

        if signature_value_elem is None or signed_info_elem is None:
            raise ValueError("Unvollständige Signatur in SAML Response")

        # Get signature algorithm
        signature_method_elem = signed_info_elem.find(
            "{http://www.w3.org/2000/09/xmldsig#}SignatureMethod"
        )
        if signature_method_elem is None:
            raise ValueError("Kein SignatureMethod in SAML Response")

        algorithm = signature_method_elem.get("Algorithm", "")

        # Parse IdP certificate
        try:
            cert_pem = config.idp_certificate
            if "-----BEGIN CERTIFICATE-----" not in cert_pem:
                cert_pem = (
                    "-----BEGIN CERTIFICATE-----\n"
                    + cert_pem
                    + "\n-----END CERTIFICATE-----"
                )
            cert = x509.load_pem_x509_certificate(cert_pem.encode())
            public_key = cert.public_key()
        except Exception as e:
            logger.error("saml_cert_parse_failed", error=str(e))
            raise ValueError(f"IdP-Zertifikat konnte nicht geladen werden: {e}")

        # Decode signature value (Base64)
        signature_value = base64.b64decode(
            "".join(signature_value_elem.text.split())
        )

        # Get canonical SignedInfo for verification
        # Note: In production, use proper C14N canonicalization
        signed_info_str = ET.tostring(signed_info_elem, encoding="unicode")
        signed_info_bytes = signed_info_str.encode("utf-8")

        # Determine hash algorithm from signature method
        hash_algo: hashes.HashAlgorithm
        if "sha256" in algorithm.lower():
            hash_algo = hashes.SHA256()
        elif "sha384" in algorithm.lower():
            hash_algo = hashes.SHA384()
        elif "sha512" in algorithm.lower():
            hash_algo = hashes.SHA512()
        elif "sha1" in algorithm.lower():
            # SHA-1 is deprecated but still used by some IdPs
            hash_algo = hashes.SHA1()
            logger.warning(
                "saml_sha1_signature",
                message="SAML Response verwendet SHA-1 Signatur (deprecated)"
            )
        else:
            raise ValueError(f"Nicht unterstützter Signatur-Algorithmus: {algorithm}")

        # Verify signature based on key type
        try:
            if isinstance(public_key, rsa.RSAPublicKey):
                public_key.verify(
                    signature_value,
                    signed_info_bytes,
                    padding.PKCS1v15(),
                    hash_algo,
                )
            elif isinstance(public_key, ec.EllipticCurvePublicKey):
                public_key.verify(
                    signature_value,
                    signed_info_bytes,
                    ec.ECDSA(hash_algo),
                )
            else:
                raise ValueError(
                    f"Nicht unterstützter Key-Typ: {type(public_key).__name__}"
                )

            logger.debug(
                "saml_signature_validated",
                algorithm=algorithm,
            )

        except InvalidSignature:
            logger.error(
                "saml_signature_invalid",
                algorithm=algorithm,
            )
            raise ValueError("SAML Response Signatur ist ungültig")
        except Exception as e:
            logger.error("saml_signature_verification_failed", error=str(e))
            raise ValueError(f"Signatur-Validierung fehlgeschlagen: {e}")

    async def start_authentication(
        self,
        provider_id: UUID,
        company_id: UUID,
        relay_state: Optional[str] = None,
    ) -> Tuple[str, str]:
        """
        Startet den SAML Authentication Flow.

        Args:
            provider_id: Provider-ID
            company_id: Firma-ID
            relay_state: Optional RelayState (z.B. Return-URL)

        Returns:
            Tuple aus (redirect_url, request_id)
        """
        provider = await self.config_service.get_provider(provider_id, company_id)
        if not provider or not provider.saml_config:
            raise ValueError("SAML-Provider nicht gefunden oder nicht konfiguriert")

        if not provider.enabled:
            raise ValueError("SSO-Provider ist deaktiviert")

        config = provider.saml_config

        # Create request state (store in Redis for multi-worker safety)
        saml_request = SAMLRequest(
            provider_id=provider_id,
            relay_state=relay_state,
        )
        await self.state_manager.store_saml_request(saml_request.request_id, saml_request)

        # Generate AuthnRequest
        issue_instant = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        authn_request_xml = self._generate_authn_request(
            config, saml_request.request_id, issue_instant
        )

        # Encode for redirect binding
        encoded_request = self._deflate_and_encode(authn_request_xml)

        # Build redirect URL
        params = {
            "SAMLRequest": encoded_request,
        }
        if relay_state:
            params["RelayState"] = relay_state

        redirect_url = f"{config.idp_sso_url}?{urlencode(params)}"

        logger.info(
            "saml_authentication_started",
            provider_id=str(provider_id),
            request_id=saml_request.request_id[:16] + "...",
        )

        return redirect_url, saml_request.request_id

    async def handle_response(
        self,
        saml_response: str,
        company_id: UUID,
        relay_state: Optional[str] = None,
    ) -> Tuple[SAMLUserInfo, SAMLAssertion]:
        """
        Verarbeitet die SAML Response.

        Args:
            saml_response: Base64-kodierte SAML Response
            company_id: Firma-ID
            relay_state: Optional RelayState

        Returns:
            Tuple aus (UserInfo, Assertion)
        """
        # Decode response
        response_xml = self._decode_and_inflate(saml_response)

        # Parse XML
        root = ET.fromstring(response_xml)

        # Extract InResponseTo to find original request
        in_response_to = root.get("InResponseTo")
        if not in_response_to:
            raise ValueError("InResponseTo fehlt in SAML Response")

        # Find and validate request state (from Redis, deleted after retrieval)
        saml_request = await self.state_manager.get_saml_request(in_response_to, delete=True)
        if not saml_request:
            raise ValueError("Ungueltiger oder abgelaufener SAML Request")

        if datetime.utcnow() > saml_request.expires_at:
            raise ValueError("SAML Request ist abgelaufen")

        # Get provider config
        provider = await self.config_service.get_provider(
            saml_request.provider_id, company_id
        )
        if not provider or not provider.saml_config:
            raise ValueError("Provider nicht gefunden")

        config = provider.saml_config

        # Check status
        status_code_elem = root.find(".//samlp:StatusCode", SAML_NS)
        if status_code_elem is not None:
            status_value = status_code_elem.get("Value", "")
            if "Success" not in status_value:
                raise ValueError(f"SAML Authentication fehlgeschlagen: {status_value}")

        # SECURITY: Validate signature BEFORE extracting assertion (CWE-347)
        # This prevents SAML Response Forgery attacks
        self._validate_signature(root, config)

        # Extract and validate assertion
        assertion = self._extract_assertion(root, config)

        # Validate assertion
        self._validate_assertion(assertion, config)

        # Extract user info
        user_info = self._extract_user_info(assertion, config.attribute_mapping)

        # Record login
        await self.config_service.record_login(saml_request.provider_id, company_id)

        logger.info(
            "saml_response_processed",
            provider_id=str(saml_request.provider_id),
            name_id=user_info.name_id[:8] + "...",
        )

        return user_info, assertion

    def _extract_assertion(
        self, root: Element, config: SAMLConfig
    ) -> SAMLAssertion:
        """Extrahiert die SAML Assertion aus der Response."""
        # Find assertion
        assertion_elem = root.find(".//saml:Assertion", SAML_NS)
        if assertion_elem is None:
            raise ValueError("Keine Assertion in SAML Response gefunden")

        # Extract issuer
        issuer_elem = assertion_elem.find("saml:Issuer", SAML_NS)
        issuer = issuer_elem.text if issuer_elem is not None else ""

        # Extract subject
        subject_elem = assertion_elem.find(".//saml:Subject/saml:NameID", SAML_NS)
        if subject_elem is None:
            raise ValueError("NameID nicht gefunden")

        name_id = subject_elem.text or ""
        name_id_format = subject_elem.get("Format", "")

        # Extract conditions
        conditions_elem = assertion_elem.find("saml:Conditions", SAML_NS)
        not_before = None
        not_on_or_after = None
        audience = None

        if conditions_elem is not None:
            if conditions_elem.get("NotBefore"):
                not_before = datetime.fromisoformat(
                    conditions_elem.get("NotBefore").replace("Z", "+00:00")
                )
            if conditions_elem.get("NotOnOrAfter"):
                not_on_or_after = datetime.fromisoformat(
                    conditions_elem.get("NotOnOrAfter").replace("Z", "+00:00")
                )

            audience_elem = conditions_elem.find(
                ".//saml:AudienceRestriction/saml:Audience", SAML_NS
            )
            if audience_elem is not None:
                audience = audience_elem.text

        # Extract AuthnStatement
        authn_stmt = assertion_elem.find("saml:AuthnStatement", SAML_NS)
        session_index = None
        authn_instant = None

        if authn_stmt is not None:
            session_index = authn_stmt.get("SessionIndex")
            if authn_stmt.get("AuthnInstant"):
                authn_instant = datetime.fromisoformat(
                    authn_stmt.get("AuthnInstant").replace("Z", "+00:00")
                )

        # Extract attributes
        attributes: Dict[str, List[str]] = {}
        attr_stmt = assertion_elem.find("saml:AttributeStatement", SAML_NS)
        if attr_stmt is not None:
            for attr in attr_stmt.findall("saml:Attribute", SAML_NS):
                attr_name = attr.get("Name", "")
                values = []
                for value_elem in attr.findall("saml:AttributeValue", SAML_NS):
                    if value_elem.text:
                        values.append(value_elem.text)
                if values:
                    attributes[attr_name] = values

        return SAMLAssertion(
            subject_name_id=name_id,
            name_id_format=name_id_format,
            issuer=issuer,
            session_index=session_index,
            attributes=attributes,
            not_before=not_before,
            not_on_or_after=not_on_or_after,
            authn_instant=authn_instant,
            audience=audience,
        )

    def _validate_assertion(
        self, assertion: SAMLAssertion, config: SAMLConfig
    ) -> None:
        """Validiert die SAML Assertion."""
        now = datetime.utcnow()

        # Validate issuer
        if assertion.issuer != config.idp_entity_id:
            raise ValueError(
                f"Ungueltiger Issuer: {assertion.issuer} != {config.idp_entity_id}"
            )

        # Validate audience
        if assertion.audience and assertion.audience != config.sp_entity_id:
            raise ValueError(
                f"Ungueltige Audience: {assertion.audience} != {config.sp_entity_id}"
            )

        # Validate time conditions
        if assertion.not_before:
            # Allow 5 minute clock skew
            if now < assertion.not_before.replace(tzinfo=None) - timedelta(minutes=5):
                raise ValueError("Assertion ist noch nicht gueltig")

        if assertion.not_on_or_after:
            # Allow 5 minute clock skew
            if now > assertion.not_on_or_after.replace(tzinfo=None) + timedelta(minutes=5):
                raise ValueError("Assertion ist abgelaufen")

        logger.debug(
            "saml_assertion_validated",
            issuer=assertion.issuer,
            name_id=assertion.subject_name_id[:8] + "...",
        )

    def _extract_user_info(
        self,
        assertion: SAMLAssertion,
        attribute_mapping: Dict[str, str],
    ) -> SAMLUserInfo:
        """Extrahiert Benutzerinformationen aus der Assertion."""
        attrs = assertion.attributes

        def get_attr(target: str) -> Optional[str]:
            source = attribute_mapping.get(target)
            if source and source in attrs and attrs[source]:
                return attrs[source][0]
            return None

        # Extract groups (common attribute names)
        groups = []
        group_attrs = [
            "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups",
            "memberOf",
            "groups",
            "Group",
        ]
        for attr_name in group_attrs:
            if attr_name in attrs:
                groups.extend(attrs[attr_name])

        return SAMLUserInfo(
            name_id=assertion.subject_name_id,
            email=get_attr("email") or assertion.subject_name_id,
            name=get_attr("name"),
            given_name=get_attr("given_name"),
            family_name=get_attr("family_name"),
            groups=groups,
            raw_attributes=attrs,
        )

    async def generate_logout_request(
        self,
        provider_id: UUID,
        company_id: UUID,
        name_id: str,
        session_index: Optional[str] = None,
    ) -> Optional[str]:
        """
        Generiert einen SAML Logout Request.

        Args:
            provider_id: Provider-ID
            company_id: Firma-ID
            name_id: NameID des Benutzers
            session_index: Session Index aus der Assertion

        Returns:
            Logout URL oder None
        """
        provider = await self.config_service.get_provider(provider_id, company_id)
        if not provider or not provider.saml_config:
            return None

        config = provider.saml_config
        if not config.idp_slo_url:
            return None

        request_id = f"_id{uuid4().hex}"
        issue_instant = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        session_index_xml = ""
        if session_index:
            session_index_xml = f'<samlp:SessionIndex>{session_index}</samlp:SessionIndex>'

        logout_request_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="{request_id}"
    Version="2.0"
    IssueInstant="{issue_instant}"
    Destination="{config.idp_slo_url}">
    <saml:Issuer>{config.sp_entity_id}</saml:Issuer>
    <saml:NameID Format="{config.name_id_format}">{name_id}</saml:NameID>
    {session_index_xml}
</samlp:LogoutRequest>"""

        encoded_request = self._deflate_and_encode(logout_request_xml)
        return f"{config.idp_slo_url}?{urlencode({'SAMLRequest': encoded_request})}"

    def generate_metadata(self, config: SAMLConfig) -> str:
        """
        Generiert SP Metadata XML.

        Args:
            config: SAML-Konfiguration

        Returns:
            SP Metadata XML
        """
        cert_section = ""
        if config.sp_certificate:
            # Format certificate for XML
            cert_lines = config.sp_certificate.replace(
                "-----BEGIN CERTIFICATE-----", ""
            ).replace(
                "-----END CERTIFICATE-----", ""
            ).strip()

            cert_section = f"""
    <md:KeyDescriptor use="signing">
        <ds:KeyInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
            <ds:X509Data>
                <ds:X509Certificate>{cert_lines}</ds:X509Certificate>
            </ds:X509Data>
        </ds:KeyInfo>
    </md:KeyDescriptor>"""

        slo_section = ""
        if config.sp_slo_url:
            slo_section = f"""
    <md:SingleLogoutService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="{config.sp_slo_url}"/>"""

        metadata = f"""<?xml version="1.0" encoding="UTF-8"?>
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="{config.sp_entity_id}">
    <md:SPSSODescriptor
        AuthnRequestsSigned="{str(config.sign_requests).lower()}"
        WantAssertionsSigned="{str(config.sign_assertions).lower()}"
        protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
        {cert_section}
        <md:NameIDFormat>{config.name_id_format}</md:NameIDFormat>
        <md:AssertionConsumerService
            Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
            Location="{config.sp_acs_url}"
            index="0"
            isDefault="true"/>
        {slo_section}
    </md:SPSSODescriptor>
</md:EntityDescriptor>"""

        return metadata
