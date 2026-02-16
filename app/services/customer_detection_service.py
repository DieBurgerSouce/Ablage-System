"""Customer Detection Service.

Automatische Erkennung und Extraktion von Geschäftskontakten aus Dokumenten:
- Kunden und Lieferanten aus Rechnungen
- Vertragsparteien aus Verträgen
- Kontaktpersonen aus Korrespondenz
- Deduplizierung über Name-Matching
- Optionales Auto-Create

Feinpoliert und durchdacht - Intelligente Kontakterkennung.
"""

import re
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, BusinessContact, DocumentContact, ContactType
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# ==================== Name Normalization ====================


def normalize_company_name(name: str) -> str:
    """Normalisiert Firmennamen für Vergleiche.

    - Entfernt Rechtsformen (GmbH, AG, etc.)
    - Konvertiert zu Kleinbuchstaben
    - Entfernt Sonderzeichen
    - Normalisiert Umlaute
    """
    if not name:
        return ""

    # Zu Kleinbuchstaben
    normalized = name.lower().strip()

    # Rechtsformen entfernen
    legal_forms = [
        r"\s+gmbh\s*&\s*co\.?\s*kg",
        r"\s+gmbh\s*&\s*co\.?\s*ohg",
        r"\s+kg",
        r"\s+ohg",
        r"\s+gbr",
        r"\s+gmbh",
        r"\s+ag",
        r"\s+e\.?k\.?",
        r"\s+e\.?v\.?",
        r"\s+ug\s*\(haftungsbeschränkt\)",
        r"\s+ug",
        r"\s+se",
        r"\s+kgaa",
        r"\s+mbh",
        r"\s+inc\.?",
        r"\s+ltd\.?",
        r"\s+limited",
        r"\s+corp\.?",
        r"\s+co\.?",
    ]

    for pattern in legal_forms:
        normalized = re.sub(pattern, "", normalized, flags=re.IGNORECASE)

    # Umlaute normalisieren (ä -> ae, etc.)
    normalized = normalized.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    normalized = normalized.replace("ß", "ss")

    # Akzente entfernen
    normalized = unicodedata.normalize("NFKD", normalized)
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))

    # Nur Buchstaben und Zahlen behalten
    normalized = re.sub(r"[^a-z0-9\s]", "", normalized)

    # Mehrfache Leerzeichen entfernen
    normalized = re.sub(r"\s+", " ", normalized).strip()

    return normalized


def extract_company_form(name: str) -> Optional[str]:
    """Extrahiert die Rechtsform aus dem Firmennamen."""
    forms = [
        (r"GmbH\s*&\s*Co\.?\s*KG", "GmbH & Co. KG"),
        (r"GmbH\s*&\s*Co\.?\s*OHG", "GmbH & Co. OHG"),
        (r"UG\s*\(haftungsbeschränkt\)", "UG (haftungsbeschränkt)"),
        (r"KGaA", "KGaA"),
        (r"GmbH", "GmbH"),
        (r"AG", "AG"),
        (r"KG", "KG"),
        (r"OHG", "OHG"),
        (r"GbR", "GbR"),
        (r"UG", "UG"),
        (r"e\.?K\.?", "e.K."),
        (r"e\.?V\.?", "e.V."),
        (r"SE", "SE"),
        (r"mbH", "mbH"),
    ]

    for pattern, form in forms:
        if re.search(pattern, name, re.IGNORECASE):
            return form

    return None


def calculate_name_similarity(name1: str, name2: str) -> float:
    """Berechnet Ähnlichkeit zwischen zwei Namen (0.0 - 1.0)."""
    norm1 = normalize_company_name(name1)
    norm2 = normalize_company_name(name2)

    if not norm1 or not norm2:
        return 0.0

    # Exakte Übereinstimmung
    if norm1 == norm2:
        return 1.0

    # SequenceMatcher für Ähnlichkeit
    return SequenceMatcher(None, norm1, norm2).ratio()


# ==================== Contact Extraction ====================


def extract_vat_id(text: str) -> Optional[str]:
    """Extrahiert USt-IdNr. aus Text."""
    patterns = [
        r"(?:USt-?Id\.?(?:-?Nr\.?)?|VAT\s*(?:ID)?|Umsatzsteuer-?(?:Identifikations)?nummer)[\s:]*([A-Z]{2}\s*\d{9,11})",
        r"\b(DE\s*\d{9})\b",
        r"\b(AT\s*U\d{8})\b",
        r"\b(CH\s*\d{9})\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            vat_id = re.sub(r"\s+", "", match.group(1).upper())
            return vat_id

    return None


def extract_tax_id(text: str) -> Optional[str]:
    """Extrahiert Steuernummer aus Text."""
    patterns = [
        r"(?:Steuer(?:nummer|Nr\.?)|St\.?-?Nr\.?)[\s:]*(\d{2,3}/?\d{3}/?\d{4,5})",
        r"\b(\d{2,3}/\d{3}/\d{4,5})\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)

    return None


def extract_iban(text: str) -> Optional[str]:
    """Extrahiert IBAN aus Text."""
    pattern = r"\b([A-Z]{2}\d{2}\s*(?:\d{4}\s*){4,6}\d{0,2})\b"
    match = re.search(pattern, text.upper())
    if match:
        return re.sub(r"\s+", "", match.group(1))
    return None


def extract_email(text: str) -> Optional[str]:
    """Extrahiert E-Mail-Adresse aus Text."""
    pattern = r"\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b"
    match = re.search(pattern, text)
    if match:
        return match.group(1).lower()
    return None


def extract_phone(text: str) -> Optional[str]:
    """Extrahiert Telefonnummer aus Text."""
    patterns = [
        r"(?:Tel\.?|Telefon|Phone|Fon)[\s:]*([+\d\s/-]{10,20})",
        r"\b(\+49\s*\d{2,4}[\s/-]?\d{3,8}[\s/-]?\d{0,6})\b",
        r"\b(0\d{2,4}[\s/-]?\d{3,8}[\s/-]?\d{0,6})\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            phone = re.sub(r"[\s/-]", "", match.group(1))
            if len(phone) >= 10:
                return phone

    return None


def extract_address_from_text(text: str) -> Dict[str, Optional[str]]:
    """Extrahiert Adresse aus Text.

    Returns:
        Dict mit street, house_number, postal_code, city, country
    """
    result: Dict[str, Optional[str]] = {
        "street": None,
        "house_number": None,
        "postal_code": None,
        "city": None,
        "country": "Deutschland",
    }

    # PLZ und Ort
    plz_city_pattern = r"\b(\d{5})\s+([A-ZÄÖÜa-zäöüß][a-zäöüß]+(?:\s+[A-ZÄÖÜa-zäöüß][a-zäöüß]+)*)\b"
    match = re.search(plz_city_pattern, text)
    if match:
        result["postal_code"] = match.group(1)
        result["city"] = match.group(2)

    # Straße mit Hausnummer
    street_patterns = [
        r"([A-ZÄÖÜa-zäöüß][a-zäöüß]+(?:straße|str\.|weg|platz|allee|ring|gasse|damm))\s+(\d+[a-zA-Z]?)",
        r"([A-ZÄÖÜa-zäöüß][a-zäöüß]+(?:straße|str\.|weg|platz|allee|ring|gasse|damm))",
    ]

    for pattern in street_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["street"] = match.group(1)
            if len(match.groups()) > 1:
                result["house_number"] = match.group(2)
            break

    return result


# Singleton-Pattern für EntityExtractionAgent (spaCy-Model-Caching)
_entity_extraction_agent: Optional["EntityExtractionAgent"] = None  # type: ignore


def _get_entity_extraction_agent() -> "EntityExtractionAgent":
    """Gibt gecachte EntityExtractionAgent-Instanz zurück.

    Verhindert wiederholtes Laden des spaCy-Models (~500MB, ~30s Ladezeit).
    Thread-safe durch GIL bei Python-Objektzuweisung.
    """
    global _entity_extraction_agent
    if _entity_extraction_agent is None:
        from app.agents.postprocessing.entity_extraction_agent import EntityExtractionAgent

        _entity_extraction_agent = EntityExtractionAgent()
        logger.info("entity_extraction_agent_initialized", spacy_loaded=True)
    return _entity_extraction_agent


def extract_name_from_text(text: str) -> Optional[Dict[str, Any]]:
    """Extrahiert Namen (Personen/Organisationen) aus Text via NER.

    Nutzt EntityExtractionAgent mit spaCy (falls verfügbar) oder Pattern-Matching.
    PERFORMANCE: Agent wird als Singleton gecacht (spaCy-Model-Loading ~30s).

    Args:
        text: OCR-Text (begrenzt auf ~5000 Zeichen)

    Returns:
        Dict mit name, entity_type, confidence oder None wenn kein Name gefunden
    """
    try:
        agent = _get_entity_extraction_agent()

        # Text limitieren
        text_limited = text[:5000]

        # Extrahiere Named Entities über öffentliche API
        all_entities = agent.extract_named_entities(text_limited)

        # Zusätzlich: Organisationen via Pattern-Matching
        org_entities = _extract_organizations_pattern(text_limited)
        all_entities.extend(org_entities)

        if not all_entities:
            return None

        # Priorisierung: Organisation vor Person (bei Geschäftsdokumenten)
        orgs = [e for e in all_entities if e.get("type") == "ORGANIZATION"]
        persons = [e for e in all_entities if e.get("type") == "PERSON"]

        # Bevorzuge Organisation (Firmenname), dann Person
        if orgs:
            best = max(orgs, key=lambda e: e.get("confidence", 0))
            return {
                "name": best["value"],
                "entity_type": "organization",
                "confidence": best.get("confidence", 0.7),
            }
        elif persons:
            best = max(persons, key=lambda e: e.get("confidence", 0))
            return {
                "name": best["value"],
                "entity_type": "person",
                "confidence": best.get("confidence", 0.7),
            }

        return None

    except Exception as e:
        logger.warning("name_extraction_error", **safe_error_log(e))
        return None


def _extract_organizations_pattern(text: str) -> List[Dict[str, Any]]:
    """Extrahiert Organisationsnamen via Pattern-Matching.

    Sucht nach typischen deutschen Rechtsformen und Firmennamen.
    """
    entities = []

    # Muster für deutsche Firmen mit Rechtsform
    company_patterns = [
        # GmbH & Co. KG/OHG
        r"\b([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ]?[a-zäöüß]+)*)\s+GmbH\s*&\s*Co\.?\s*(?:KG|OHG)\b",
        # GmbH
        r"\b([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ]?[a-zäöüß]+)*)\s+GmbH\b",
        # AG
        r"\b([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ]?[a-zäöüß]+)*)\s+AG\b",
        # KG/OHG
        r"\b([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ]?[a-zäöüß]+)*)\s+(?:KG|OHG|e\.K\.|e\.G\.)\b",
        # Fa. / Firma
        r"\b(?:Fa\.|Firma)\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ]?[a-zäöüß]+)*)\b",
    ]

    for pattern in company_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            full_match = match.group(0)

            # Vollständigen Firmennamen mit Rechtsform verwenden (Deduplizierung)
            if not any(e["value"] == full_match for e in entities):
                entities.append({
                    "type": "ORGANIZATION",
                    "value": full_match.strip(),
                    "confidence": 0.85,
                    "source": "pattern_org_extraction",
                })

    return entities


# ==================== Document Extraction ====================


def extract_contact_from_invoice(document_metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extrahiert Kontaktinformationen aus Rechnungs-Metadaten.

    Args:
        document_metadata: document_metadata JSON aus Document

    Returns:
        Dict mit extrahierten Kontaktdaten oder None
    """
    # Typische Felder in Rechnungs-Metadaten
    sender_fields = ["sender", "vendor", "supplier", "absender", "lieferant", "rechnungssteller"]
    recipient_fields = ["recipient", "buyer", "customer", "empfänger", "kunde", "rechnungsempfänger"]

    result = {
        "sender": None,
        "recipient": None,
    }

    # Sender extrahieren
    for field in sender_fields:
        if field in document_metadata and document_metadata[field]:
            data = document_metadata[field]
            if isinstance(data, dict):
                result["sender"] = {
                    "name": data.get("name") or data.get("company"),
                    "street": data.get("street") or data.get("address", {}).get("street"),
                    "house_number": data.get("house_number") or data.get("address", {}).get("house_number"),
                    "postal_code": data.get("postal_code") or data.get("address", {}).get("postal_code") or data.get("zip"),
                    "city": data.get("city") or data.get("address", {}).get("city"),
                    "country": data.get("country") or data.get("address", {}).get("country") or "Deutschland",
                    "vat_id": data.get("vat_id") or data.get("ust_id"),
                    "tax_id": data.get("tax_id") or data.get("steuernummer"),
                    "email": data.get("email"),
                    "phone": data.get("phone") or data.get("telefon"),
                    "iban": data.get("iban"),
                    "bic": data.get("bic"),
                }
            elif isinstance(data, str):
                result["sender"] = {"name": data}
            break

    # Recipient extrahieren
    for field in recipient_fields:
        if field in document_metadata and document_metadata[field]:
            data = document_metadata[field]
            if isinstance(data, dict):
                result["recipient"] = {
                    "name": data.get("name") or data.get("company"),
                    "street": data.get("street") or data.get("address", {}).get("street"),
                    "house_number": data.get("house_number") or data.get("address", {}).get("house_number"),
                    "postal_code": data.get("postal_code") or data.get("address", {}).get("postal_code") or data.get("zip"),
                    "city": data.get("city") or data.get("address", {}).get("city"),
                    "country": data.get("country") or data.get("address", {}).get("country") or "Deutschland",
                    "vat_id": data.get("vat_id") or data.get("ust_id"),
                    "email": data.get("email"),
                    "phone": data.get("phone") or data.get("telefon"),
                }
            elif isinstance(data, str):
                result["recipient"] = {"name": data}
            break

    return result if result["sender"] or result["recipient"] else None


def extract_contact_from_contract(document_metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extrahiert Kontaktinformationen aus Vertrags-Metadaten.

    Args:
        document_metadata: document_metadata JSON aus Document

    Returns:
        Dict mit extrahierten Kontaktdaten (parties Liste)
    """
    party_fields = ["parties", "vertragsparteien", "party_a", "party_b", "partei_a", "partei_b"]

    parties = []

    # Direktes parties Array
    if "parties" in document_metadata and isinstance(document_metadata["parties"], list):
        for party in document_metadata["parties"]:
            if isinstance(party, dict) and party.get("name"):
                parties.append({
                    "name": party.get("name"),
                    "role": party.get("role", "party"),
                    "street": party.get("street") or party.get("address", {}).get("street"),
                    "house_number": party.get("house_number") or party.get("address", {}).get("house_number"),
                    "postal_code": party.get("postal_code") or party.get("address", {}).get("postal_code"),
                    "city": party.get("city") or party.get("address", {}).get("city"),
                    "country": party.get("country") or "Deutschland",
                })
            elif isinstance(party, str):
                parties.append({"name": party, "role": "party"})

    # Einzelne Party-Felder
    for field in ["party_a", "partei_a", "auftraggeber", "contractor"]:
        if field in document_metadata and document_metadata[field]:
            data = document_metadata[field]
            if isinstance(data, dict) and data.get("name"):
                parties.append({**data, "role": "contractor"})
            elif isinstance(data, str):
                parties.append({"name": data, "role": "contractor"})

    for field in ["party_b", "partei_b", "auftragnehmer", "client"]:
        if field in document_metadata and document_metadata[field]:
            data = document_metadata[field]
            if isinstance(data, dict) and data.get("name"):
                parties.append({**data, "role": "client"})
            elif isinstance(data, str):
                parties.append({"name": data, "role": "client"})

    return {"parties": parties} if parties else None


# ==================== Service Class ====================


class CustomerDetectionService:
    """Service für automatische Kundenerkennung und -verwaltung."""

    def __init__(self, similarity_threshold: float = 0.85):
        """Initialisiert den Service.

        Args:
            similarity_threshold: Schwellwert für Name-Matching (0.0-1.0)
        """
        self.similarity_threshold = similarity_threshold

    async def find_similar_contacts(
        self,
        db: AsyncSession,
        name: str,
        owner_id: Optional[UUID] = None,
        company_id: Optional[UUID] = None,
        contact_type: Optional[ContactType] = None,
    ) -> List[Tuple[BusinessContact, float]]:
        """Findet ähnliche Kontakte basierend auf Name.

        Args:
            db: Database session
            name: Name zum Suchen
            owner_id: DEPRECATED - nur noch für Abwärtskompatibilität
            company_id: Optional - nur Kontakte dieser Company (Multi-Tenant)
            contact_type: Optional - nur bestimmter Kontakttyp

        Returns:
            Liste von (BusinessContact, similarity_score) Tupeln
        """
        normalized = normalize_company_name(name)
        if not normalized:
            return []

        # Query bauen
        query = select(BusinessContact).where(BusinessContact.is_active == True)

        # Multi-Tenant Isolation via company_id (bevorzugt)
        if company_id:
            query = query.where(BusinessContact.company_id == company_id)
        elif owner_id:
            # DEPRECATED: Fallback für alte Aufrufe
            query = query.where(BusinessContact.owner_id == owner_id)

        if contact_type:
            query = query.where(BusinessContact.contact_type == contact_type.value)

        result = await db.execute(query)
        contacts = result.scalars().all()

        # Ähnlichkeit berechnen
        matches = []
        for contact in contacts:
            similarity = calculate_name_similarity(name, contact.name)
            if similarity >= self.similarity_threshold:
                matches.append((contact, similarity))

        # Nach Ähnlichkeit sortieren
        matches.sort(key=lambda x: x[1], reverse=True)

        return matches

    async def find_or_create_contact(
        self,
        db: AsyncSession,
        contact_data: Dict[str, Any],
        owner_id: UUID,
        company_id: Optional[UUID] = None,
        source: str = "auto_invoice",
        document_id: Optional[UUID] = None,
        auto_create: bool = True,
    ) -> Tuple[Optional[BusinessContact], bool]:
        """Findet einen existierenden Kontakt oder erstellt einen neuen.

        Args:
            db: Database session
            contact_data: Extrahierte Kontaktdaten
            owner_id: User-ID (wird als creator gespeichert)
            company_id: Company-ID (Multi-Tenant Isolation)
            source: Quelle (manual, auto_invoice, auto_contract)
            document_id: Optional - verknüpftes Dokument
            auto_create: Automatisch erstellen wenn nicht gefunden

        Returns:
            Tuple (BusinessContact, created) - created=True wenn neu erstellt
        """
        name = contact_data.get("name")
        if not name or len(name.strip()) < 2:
            logger.debug("contact_name_too_short", name=name)
            return None, False

        name = name.strip()

        # Multi-Tenant: company_id ist erforderlich für sichere Isolation
        # Falls nicht übergeben, Fallback auf owner_id (deprecated)
        isolation_condition = (
            BusinessContact.company_id == company_id if company_id
            else BusinessContact.owner_id == owner_id
        )

        # Zuerst nach exakten Identifikatoren suchen
        vat_id = contact_data.get("vat_id")
        tax_id = contact_data.get("tax_id")
        iban = contact_data.get("iban")

        if vat_id:
            result = await db.execute(
                select(BusinessContact).where(
                    and_(
                        BusinessContact.vat_id == vat_id,
                        isolation_condition,
                        BusinessContact.is_active == True,
                    )
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                # PII-Compliance: NIEMALS VAT-ID loggen (CLAUDE.md Rule 8)
                logger.info("contact_found_by_vat_id", contact_id=str(existing.id))
                return existing, False

        if tax_id:
            result = await db.execute(
                select(BusinessContact).where(
                    and_(
                        BusinessContact.tax_id == tax_id,
                        isolation_condition,
                        BusinessContact.is_active == True,
                    )
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                # PII-Compliance: NIEMALS Tax-ID loggen (CLAUDE.md Rule 8)
                logger.info("contact_found_by_tax_id", contact_id=str(existing.id))
                return existing, False

        # Name-basierte Suche mit company_id
        matches = await self.find_similar_contacts(db, name, owner_id=owner_id, company_id=company_id)

        if matches:
            best_match, similarity = matches[0]
            logger.info(
                "contact_found_by_name_similarity",
                contact_id=str(best_match.id),
                similarity=similarity,
                search_name=name,
                found_name=best_match.name,
            )
            return best_match, False

        # Nicht gefunden - erstellen wenn erlaubt
        if not auto_create:
            logger.debug("contact_not_found_no_auto_create", name=name)
            return None, False

        # Neuen Kontakt erstellen
        contact_type = ContactType.SUPPLIER if source in ("auto_invoice",) else ContactType.OTHER

        new_contact = BusinessContact(
            name=name,
            name_normalized=normalize_company_name(name),
            contact_type=contact_type.value,
            company_form=extract_company_form(name),
            vat_id=vat_id,
            tax_id=tax_id,
            iban=iban,
            bic=contact_data.get("bic"),
            street=contact_data.get("street"),
            house_number=contact_data.get("house_number"),
            postal_code=contact_data.get("postal_code"),
            city=contact_data.get("city"),
            country=contact_data.get("country") or "Deutschland",
            email=contact_data.get("email"),
            phone=contact_data.get("phone"),
            owner_id=owner_id,
            company_id=company_id,  # Multi-Tenant Isolation
            source=source,
            auto_detected=True,
            auto_detection_confidence=0.8,  # Standard-Confidence
            first_document_id=document_id,
            is_verified=False,
        )

        db.add(new_contact)
        await db.flush()

        logger.info(
            "contact_auto_created",
            contact_id=str(new_contact.id),
            name=name,
            source=source,
            document_id=str(document_id) if document_id else None,
        )

        return new_contact, True

    async def process_document(
        self,
        db: AsyncSession,
        document: Document,
        owner_id: UUID,
        company_id: Optional[UUID] = None,
        auto_create: bool = True,
    ) -> List[Dict[str, Any]]:
        """Verarbeitet ein Dokument und extrahiert/verknüpft Kontakte.

        Args:
            db: Database session
            document: Dokument zum Verarbeiten
            owner_id: User-ID (creator)
            company_id: Company-ID (Multi-Tenant Isolation). Falls None, wird document.company_id verwendet.
            auto_create: Automatisch Kontakte erstellen

        Returns:
            Liste von verarbeiteten Kontakten mit Status
        """
        results = []
        metadata = document.document_metadata or {}

        # Multi-Tenant: company_id aus Dokument holen falls nicht übergeben
        effective_company_id = company_id or document.company_id

        # Je nach Dokumenttyp extrahieren
        doc_type = document.document_type

        if doc_type in ("invoice", "rechnung"):
            extracted = extract_contact_from_invoice(metadata)
            if extracted:
                # Sender (Lieferant)
                if extracted.get("sender") and extracted["sender"].get("name"):
                    contact, created = await self.find_or_create_contact(
                        db=db,
                        contact_data=extracted["sender"],
                        owner_id=owner_id,
                        company_id=effective_company_id,
                        source="auto_invoice",
                        document_id=document.id,
                        auto_create=auto_create,
                    )
                    if contact:
                        # Verknüpfung erstellen
                        await self._link_contact_to_document(
                            db, document.id, contact.id, "sender"
                        )
                        results.append({
                            "contact_id": str(contact.id),
                            "name": contact.name,
                            "role": "sender",
                            "created": created,
                            "contact_type": contact.contact_type,
                        })

                # Recipient (Kunde - wir selbst normalerweise, aber trotzdem speichern)
                if extracted.get("recipient") and extracted["recipient"].get("name"):
                    contact, created = await self.find_or_create_contact(
                        db=db,
                        contact_data=extracted["recipient"],
                        owner_id=owner_id,
                        company_id=effective_company_id,
                        source="auto_invoice",
                        document_id=document.id,
                        auto_create=auto_create,
                    )
                    if contact:
                        await self._link_contact_to_document(
                            db, document.id, contact.id, "recipient"
                        )
                        results.append({
                            "contact_id": str(contact.id),
                            "name": contact.name,
                            "role": "recipient",
                            "created": created,
                            "contact_type": contact.contact_type,
                        })

        elif doc_type in ("contract", "vertrag"):
            extracted = extract_contact_from_contract(metadata)
            if extracted and extracted.get("parties"):
                for party_data in extracted["parties"]:
                    if party_data.get("name"):
                        contact, created = await self.find_or_create_contact(
                            db=db,
                            contact_data=party_data,
                            owner_id=owner_id,
                            company_id=effective_company_id,
                            source="auto_contract",
                            document_id=document.id,
                            auto_create=auto_create,
                        )
                        if contact:
                            role = party_data.get("role", "party")
                            await self._link_contact_to_document(
                                db, document.id, contact.id, role
                            )
                            results.append({
                                "contact_id": str(contact.id),
                                "name": contact.name,
                                "role": role,
                                "created": created,
                                "contact_type": contact.contact_type,
                            })

        # Fallback: Aus extracted_text extrahieren wenn keine Metadaten
        if not results and document.extracted_text:
            text = document.extracted_text[:5000]  # Limitieren

            vat_id = extract_vat_id(text)
            email = extract_email(text)
            address = extract_address_from_text(text)

            # Wenn wir mindestens eine VAT-ID oder Adresse haben
            if vat_id or (address.get("postal_code") and address.get("city")):
                # Name via NER extrahieren (spaCy oder Pattern-Matching)
                name_result = extract_name_from_text(text)

                if name_result and name_result.get("name"):
                    # Kontaktdaten zusammenstellen
                    contact_data = {
                        "name": name_result["name"],
                        "vat_id": vat_id,
                        "email": email,
                        **address,
                    }

                    # Kontakttyp basierend auf Entity-Typ
                    contact_type = (
                        "company" if name_result.get("entity_type") == "organization"
                        else "person"
                    )

                    contact, created = await self.find_or_create_contact(
                        db=db,
                        contact_data=contact_data,
                        owner_id=owner_id,
                        company_id=effective_company_id,
                        source="auto_ner_extraction",
                        document_id=document.id,
                        auto_create=auto_create,
                    )

                    if contact:
                        await self._link_contact_to_document(
                            db, document.id, contact.id, "detected"
                        )
                        results.append({
                            "contact_id": str(contact.id),
                            "name": contact.name,
                            "role": "detected",
                            "created": created,
                            "contact_type": contact.contact_type,
                            "extraction_confidence": name_result.get("confidence", 0.7),
                        })

                    logger.info(
                        "contact_ner_extraction_success",
                        document_id=str(document.id),
                        name=name_result["name"][:50],  # Truncate für Log
                        entity_type=name_result.get("entity_type"),
                        confidence=name_result.get("confidence"),
                    )
                else:
                    logger.debug(
                        "contact_extraction_from_text_partial",
                        document_id=str(document.id),
                        vat_id=vat_id,
                        has_address=bool(address.get("city")),
                        name_found=False,
                    )

        if results:
            await db.commit()

        logger.info(
            "document_contact_processing_complete",
            document_id=str(document.id),
            contacts_found=len(results),
            contacts_created=sum(1 for r in results if r["created"]),
        )

        return results

    async def _link_contact_to_document(
        self,
        db: AsyncSession,
        document_id: UUID,
        contact_id: UUID,
        role: str,
    ) -> DocumentContact:
        """Erstellt Verknüpfung zwischen Dokument und Kontakt.

        Prüft ob Verknüpfung bereits existiert.
        """
        # Prüfen ob bereits verknüpft
        existing = await db.execute(
            select(DocumentContact).where(
                and_(
                    DocumentContact.document_id == document_id,
                    DocumentContact.contact_id == contact_id,
                    DocumentContact.role == role,
                )
            )
        )
        if existing.scalar_one_or_none():
            return

        link = DocumentContact(
            document_id=document_id,
            contact_id=contact_id,
            role=role,
            auto_detected=True,
            confidence=0.8,
        )
        db.add(link)

        # Update document_count
        await db.execute(
            select(BusinessContact).where(BusinessContact.id == contact_id).with_for_update()
        )
        contact_result = await db.execute(
            select(BusinessContact).where(BusinessContact.id == contact_id)
        )
        contact = contact_result.scalar_one_or_none()
        if contact:
            contact.document_count = (contact.document_count or 0) + 1
            contact.last_document_date = datetime.now(timezone.utc)

        return link

    async def merge_contacts(
        self,
        db: AsyncSession,
        source_id: UUID,
        target_id: UUID,
        user_id: UUID,
        company_id: Optional[UUID] = None,
    ) -> bool:
        """Merged zwei Kontakte (source -> target).

        Source wird deaktiviert und verweist auf target.
        Alle Dokumentverknüpfungen werden übertragen.

        Args:
            db: Database session
            source_id: Kontakt der gemergt wird
            target_id: Zielkontakt
            user_id: User der die Aktion ausführt
            company_id: Company-ID für Multi-Tenant Isolation (Defense-in-Depth)

        Returns:
            True wenn erfolgreich
        """
        # Multi-Tenant: company_id Filter für Defense-in-Depth
        if company_id:
            source_condition = and_(
                BusinessContact.id == source_id,
                BusinessContact.company_id == company_id,
            )
            target_condition = and_(
                BusinessContact.id == target_id,
                BusinessContact.company_id == company_id,
            )
        else:
            # DEPRECATED: Fallback ohne company_id (Legacy-Kompatibilität)
            source_condition = BusinessContact.id == source_id
            target_condition = BusinessContact.id == target_id

        # Source und Target laden
        source_result = await db.execute(
            select(BusinessContact).where(source_condition)
        )
        source = source_result.scalar_one_or_none()

        target_result = await db.execute(
            select(BusinessContact).where(target_condition)
        )
        target = target_result.scalar_one_or_none()

        if not source or not target:
            if company_id:
                logger.warning(
                    "merge_contact_security_violation",
                    source_id=str(source_id),
                    target_id=str(target_id),
                    company_id=str(company_id),
                    reason="Contact not found or company mismatch",
                )
            logger.error("merge_contact_not_found", source_id=str(source_id), target_id=str(target_id))
            return False

        # Dokumentverknüpfungen übertragen
        links_result = await db.execute(
            select(DocumentContact).where(DocumentContact.contact_id == source_id)
        )
        links = links_result.scalars().all()

        for link in links:
            # Prüfen ob bereits verknüpft
            existing = await db.execute(
                select(DocumentContact).where(
                    and_(
                        DocumentContact.document_id == link.document_id,
                        DocumentContact.contact_id == target_id,
                    )
                )
            )
            if not existing.scalar_one_or_none():
                link.contact_id = target_id
            else:
                await db.delete(link)

        # Source deaktivieren und merged_into setzen
        source.is_active = False
        source.merged_into_id = target_id

        # Target-Statistiken aktualisieren
        target.document_count = (target.document_count or 0) + (source.document_count or 0)
        if source.total_invoice_amount:
            target.total_invoice_amount = (target.total_invoice_amount or 0) + source.total_invoice_amount

        await db.commit()

        logger.info(
            "contacts_merged",
            source_id=str(source_id),
            target_id=str(target_id),
            user_id=str(user_id),
            links_transferred=len(links),
        )

        return True


# Singleton
_customer_detection_service: Optional[CustomerDetectionService] = None


def get_customer_detection_service() -> CustomerDetectionService:
    """Gibt Singleton-Instanz des Services zurück."""
    global _customer_detection_service
    if _customer_detection_service is None:
        _customer_detection_service = CustomerDetectionService()
    return _customer_detection_service
