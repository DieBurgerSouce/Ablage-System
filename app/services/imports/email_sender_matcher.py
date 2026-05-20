"""
Email-Absender zu Entity Matching Service.

KI-gestuetzte Zuordnung von E-Mail-Absendern zu Lexware-BusinessEntities:
- Domain-basiertes Matching
- Fuzzy-Name-Matching
- KI-Klassifikation bei Unsicherheit
- Confidence-basierte Entscheidungen

Feinpoliert und durchdacht - Intelligentes Email-Routing.
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional, List, Tuple
from uuid import UUID, uuid4

import structlog
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BusinessEntity, EntityType
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class EmailMatchResult:
    """Ergebnis eines Email-Absender-Matchings."""

    entity_id: Optional[UUID]
    entity_name: Optional[str]
    entity_type: Optional[str]
    confidence: float
    match_strategy: str
    match_details: str
    suggestions: List["EmailMatchSuggestion"]
    is_whitelisted: bool = False
    is_blacklisted: bool = False


@dataclass
class EmailMatchSuggestion:
    """Ein Match-Vorschlag bei niedrigem Confidence."""

    entity_id: UUID
    entity_name: str
    entity_type: str
    confidence: float
    match_reason: str


@dataclass
class EmailSenderInfo:
    """Extrahierte Informationen aus Email-Absender."""

    full_address: str
    local_part: str
    domain: str
    display_name: Optional[str]
    company_domain: str  # z.B. "mueller-gmbh" aus "info@mueller-gmbh.de"


# ============================================================================
# Email Sender Matcher Service
# ============================================================================


class EmailSenderMatcherService:
    """Service für intelligentes Email-Absender-Matching.

    Strategie-Reihenfolge (nach Confidence):
    1. Whitelist-Match (100%)
    2. Exaktes Domain-Match in entity.email (99%)
    3. Domain-Match in entity.website (95%)
    4. Display-Name-Match gegen entity.name (90%)
    5. Domain-zu-Firmenname-Match (85%)
    6. Fuzzy-Name-Matching (80%)
    7. KI-Klassifikation (variable)

    Konfigurierbar über Admin-Settings:
    - auto_assign_threshold: Schwelle für automatische Zuordnung (default: 85%)
    - suggestion_threshold: Schwelle für Vorschläge (default: 60%)
    """

    DEFAULT_AUTO_ASSIGN_THRESHOLD = 0.85
    DEFAULT_SUGGESTION_THRESHOLD = 0.60

    def __init__(
        self,
        db: AsyncSession,
        auto_assign_threshold: float = DEFAULT_AUTO_ASSIGN_THRESHOLD,
        suggestion_threshold: float = DEFAULT_SUGGESTION_THRESHOLD,
        whitelist: Optional[List[str]] = None,
        blacklist: Optional[List[str]] = None,
    ):
        """Initialisiert den Service.

        Args:
            db: Async Database Session
            auto_assign_threshold: Confidence ab der automatisch zugeordnet wird
            suggestion_threshold: Minimale Confidence für Vorschläge
            whitelist: Liste von Email-Domains die immer akzeptiert werden
            blacklist: Liste von Email-Domains die ignoriert werden
        """
        self.db = db
        self.auto_assign_threshold = auto_assign_threshold
        self.suggestion_threshold = suggestion_threshold
        self.whitelist = [d.lower() for d in (whitelist or [])]
        self.blacklist = [d.lower() for d in (blacklist or [])]

    # ========================================================================
    # Main Matching Method
    # ========================================================================

    async def match_sender(
        self,
        from_address: str,
        subject: Optional[str] = None,
        body_preview: Optional[str] = None,
    ) -> EmailMatchResult:
        """Matcht einen Email-Absender gegen BusinessEntities.

        Args:
            from_address: Vollständige From-Adresse (z.B. "Max Müller <max@mueller-gmbh.de>")
            subject: Optional Betreff für zusätzlichen Kontext
            body_preview: Optional Body-Preview für KI-Analyse

        Returns:
            EmailMatchResult mit Entity-Zuordnung und Confidence
        """
        # 1. Absender-Informationen extrahieren
        sender_info = self._parse_sender(from_address)

        logger.info(
            "matching_email_sender",
            email=sender_info.full_address,
            domain=sender_info.domain,
            display_name=sender_info.display_name,
        )

        # 2. Blacklist prüfen
        if self._is_blacklisted(sender_info.domain):
            logger.debug("sender_blacklisted", domain=sender_info.domain)
            return EmailMatchResult(
                entity_id=None,
                entity_name=None,
                entity_type=None,
                confidence=0.0,
                match_strategy="blacklist",
                match_details=f"Domain {sender_info.domain} ist auf Blacklist",
                suggestions=[],
                is_blacklisted=True,
            )

        # 3. Whitelist prüfen
        if self._is_whitelisted(sender_info.domain):
            logger.debug("sender_whitelisted", domain=sender_info.domain)
            entity = await self._find_by_whitelisted_domain(sender_info.domain)
            if entity:
                return EmailMatchResult(
                    entity_id=entity.id,
                    entity_name=entity.name,
                    entity_type=entity.entity_type,
                    confidence=1.0,
                    match_strategy="whitelist",
                    match_details=f"Domain {sender_info.domain} ist auf Whitelist",
                    suggestions=[],
                    is_whitelisted=True,
                )

        # 4. Multi-Strategie-Matching
        best_match: Optional[Tuple[BusinessEntity, float, str, str]] = None
        suggestions: List[EmailMatchSuggestion] = []

        # 4a. Exaktes Email-Domain-Match
        entity, confidence, details = await self._match_by_email_domain(sender_info)
        if entity and confidence > 0:
            if confidence > (best_match[1] if best_match else 0):
                best_match = (entity, confidence, "email_domain", details)

        # 4b. Website-Domain-Match
        entity, confidence, details = await self._match_by_website_domain(sender_info)
        if entity and confidence > 0:
            if confidence > (best_match[1] if best_match else 0):
                best_match = (entity, confidence, "website_domain", details)

        # 4c. Display-Name-Match (wenn vorhanden)
        if sender_info.display_name:
            matches = await self._match_by_display_name(sender_info)
            for entity, confidence, details in matches:
                if confidence >= self.suggestion_threshold:
                    suggestions.append(
                        EmailMatchSuggestion(
                            entity_id=entity.id,
                            entity_name=entity.name,
                            entity_type=entity.entity_type,
                            confidence=confidence,
                            match_reason=details,
                        )
                    )
                    if confidence > (best_match[1] if best_match else 0):
                        best_match = (entity, confidence, "display_name", details)

        # 4d. Domain-zu-Firmenname-Match
        matches = await self._match_domain_to_company_name(sender_info)
        for entity, confidence, details in matches:
            if confidence >= self.suggestion_threshold:
                suggestions.append(
                    EmailMatchSuggestion(
                        entity_id=entity.id,
                        entity_name=entity.name,
                        entity_type=entity.entity_type,
                        confidence=confidence,
                        match_reason=details,
                    )
                )
                if confidence > (best_match[1] if best_match else 0):
                    best_match = (entity, confidence, "domain_to_name", details)

        # 5. Ergebnis zusammenstellen
        if best_match and best_match[1] >= self.auto_assign_threshold:
            entity, confidence, strategy, details = best_match
            logger.info(
                "sender_matched",
                email=sender_info.full_address,
                entity_name=entity.name,
                confidence=confidence,
                strategy=strategy,
            )
            return EmailMatchResult(
                entity_id=entity.id,
                entity_name=entity.name,
                entity_type=entity.entity_type,
                confidence=confidence,
                match_strategy=strategy,
                match_details=details,
                suggestions=self._deduplicate_suggestions(suggestions, entity.id),
            )

        # 6. Keine sichere Zuordnung - nur Vorschläge zurückgeben
        if suggestions:
            # Beste Suggestion als Haupt-Ergebnis wenn über Threshold
            best_suggestion = max(suggestions, key=lambda s: s.confidence)
            if best_suggestion.confidence >= self.suggestion_threshold:
                return EmailMatchResult(
                    entity_id=None,  # Nicht automatisch zuordnen
                    entity_name=None,
                    entity_type=None,
                    confidence=best_suggestion.confidence,
                    match_strategy="suggestion",
                    match_details="Keine sichere Zuordnung, aber Vorschläge vorhanden",
                    suggestions=self._deduplicate_suggestions(suggestions),
                )

        # 7. Kein Match gefunden
        logger.info(
            "sender_no_match",
            email=sender_info.full_address,
            domain=sender_info.domain,
        )
        return EmailMatchResult(
            entity_id=None,
            entity_name=None,
            entity_type=None,
            confidence=0.0,
            match_strategy="no_match",
            match_details="Keine passende Entity gefunden",
            suggestions=[],
        )

    # ========================================================================
    # Parsing Methods
    # ========================================================================

    def _parse_sender(self, from_address: str) -> EmailSenderInfo:
        """Parst eine From-Adresse in ihre Bestandteile.

        Unterstützte Formate:
        - "user@domain.de"
        - "Max Müller <user@domain.de>"
        - "\"Max Müller GmbH\" <user@domain.de>"
        """
        from_address = from_address.strip()
        display_name: Optional[str] = None
        email_address = from_address

        # Format: "Display Name <email@domain>"
        match = re.match(r'^"?([^"<]+)"?\s*<([^>]+)>$', from_address)
        if match:
            display_name = match.group(1).strip().strip('"')
            email_address = match.group(2).strip()
        else:
            # Einfaches Format: email@domain
            match = re.match(r"^([^@]+)@([^@]+)$", from_address)
            if match:
                email_address = from_address

        # Email-Teile extrahieren
        parts = email_address.split("@")
        if len(parts) == 2:
            local_part = parts[0].strip()
            domain = parts[1].strip().lower()
        else:
            local_part = email_address
            domain = ""

        # Company-Domain extrahieren (ohne TLD)
        company_domain = self._extract_company_domain(domain)

        return EmailSenderInfo(
            full_address=from_address,
            local_part=local_part,
            domain=domain,
            display_name=display_name,
            company_domain=company_domain,
        )

    def _extract_company_domain(self, domain: str) -> str:
        """Extrahiert den Firmennamen aus einer Domain.

        Beispiele:
        - "mueller-gmbh.de" -> "mueller-gmbh"
        - "info.mueller.de" -> "mueller"
        - "mail.mueller-gmbh.co.uk" -> "mueller-gmbh"
        """
        if not domain:
            return ""

        # Bekannte TLDs entfernen
        tlds = [".de", ".com", ".net", ".org", ".at", ".ch", ".co.uk", ".eu"]
        for tld in tlds:
            if domain.endswith(tld):
                domain = domain[: -len(tld)]
                break

        # Subdomains entfernen (mail., www., info.)
        parts = domain.split(".")
        if len(parts) > 1:
            # Letzten Teil nehmen (der vor TLD)
            domain = parts[-1]

        return domain

    # ========================================================================
    # Whitelist/Blacklist Methods
    # ========================================================================

    def _is_whitelisted(self, domain: str) -> bool:
        """Prüft ob eine Domain auf der Whitelist ist."""
        if not self.whitelist:
            return False
        return domain.lower() in self.whitelist

    def _is_blacklisted(self, domain: str) -> bool:
        """Prüft ob eine Domain auf der Blacklist ist.

        Typische Blacklist-Domains:
        - gmail.com, yahoo.com, outlook.com (Freemail)
        - noreply.*, no-reply.*
        """
        if not self.blacklist:
            return False

        domain_lower = domain.lower()

        # Exakter Match
        if domain_lower in self.blacklist:
            return True

        # Pattern Match (z.B. "gmail.*")
        for pattern in self.blacklist:
            if pattern.endswith(".*"):
                prefix = pattern[:-2]
                if domain_lower.startswith(prefix):
                    return True

        return False

    async def _find_by_whitelisted_domain(
        self, domain: str
    ) -> Optional[BusinessEntity]:
        """Findet Entity für eine Whitelist-Domain."""
        # Suche in email-Feld
        stmt = select(BusinessEntity).where(
            and_(
                BusinessEntity.email.ilike(f"%@{domain}"),
                BusinessEntity.deleted_at.is_(None),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    # ========================================================================
    # Matching Strategies
    # ========================================================================

    async def _match_by_email_domain(
        self, sender_info: EmailSenderInfo
    ) -> Tuple[Optional[BusinessEntity], float, str]:
        """Matcht gegen gespeicherte Email-Adressen."""
        if not sender_info.domain:
            return None, 0.0, ""

        stmt = select(BusinessEntity).where(
            and_(
                BusinessEntity.email.ilike(f"%@{sender_info.domain}"),
                BusinessEntity.deleted_at.is_(None),
            )
        )
        result = await self.db.execute(stmt)
        entity = result.scalar_one_or_none()

        if entity:
            return (
                entity,
                0.99,
                f"Email-Domain {sender_info.domain} stimmt mit gespeicherter Email überein",
            )
        return None, 0.0, ""

    async def _match_by_website_domain(
        self, sender_info: EmailSenderInfo
    ) -> Tuple[Optional[BusinessEntity], float, str]:
        """Matcht gegen gespeicherte Website-URLs."""
        if not sender_info.domain:
            return None, 0.0, ""

        # Suche nach Domain in Website-Feld
        stmt = select(BusinessEntity).where(
            and_(
                or_(
                    BusinessEntity.website.ilike(f"%{sender_info.domain}%"),
                    BusinessEntity.website.ilike(f"%{sender_info.company_domain}%"),
                ),
                BusinessEntity.deleted_at.is_(None),
            )
        )
        result = await self.db.execute(stmt)
        entity = result.scalar_one_or_none()

        if entity:
            return (
                entity,
                0.95,
                f"Domain {sender_info.domain} stimmt mit Website überein",
            )
        return None, 0.0, ""

    async def _match_by_display_name(
        self, sender_info: EmailSenderInfo
    ) -> List[Tuple[BusinessEntity, float, str]]:
        """Matcht Display-Name gegen Entity-Namen."""
        if not sender_info.display_name:
            return []

        matches: List[Tuple[BusinessEntity, float, str]] = []

        # Alle Entities laden und fuzzy matchen
        stmt = select(BusinessEntity).where(
            BusinessEntity.deleted_at.is_(None)
        ).limit(500)
        result = await self.db.execute(stmt)
        entities = result.scalars().all()

        display_name_normalized = self._normalize_name(sender_info.display_name)

        for entity in entities:
            best_similarity = 0.0

            # Name prüfen
            if entity.name:
                sim = self._calculate_similarity(
                    display_name_normalized, self._normalize_name(entity.name)
                )
                best_similarity = max(best_similarity, sim)

            # Short name prüfen
            if entity.short_name:
                sim = self._calculate_similarity(
                    display_name_normalized, self._normalize_name(entity.short_name)
                )
                best_similarity = max(best_similarity, sim)

            # Display name prüfen
            if entity.display_name:
                sim = self._calculate_similarity(
                    display_name_normalized, self._normalize_name(entity.display_name)
                )
                best_similarity = max(best_similarity, sim)

            if best_similarity >= self.suggestion_threshold:
                matches.append(
                    (
                        entity,
                        best_similarity * 0.90,  # Max 90% für Name-Match
                        f"Display-Name '{sender_info.display_name}' ähnlich zu '{entity.name}'",
                    )
                )

        # Nach Similarity sortieren
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[:5]  # Top 5

    async def _match_domain_to_company_name(
        self, sender_info: EmailSenderInfo
    ) -> List[Tuple[BusinessEntity, float, str]]:
        """Matcht Company-Domain gegen Entity-Namen.

        Beispiel: mueller-gmbh.de -> Müller GmbH
        """
        if not sender_info.company_domain:
            return []

        matches: List[Tuple[BusinessEntity, float, str]] = []

        # Company-Domain aufbereiten
        company_domain_normalized = self._normalize_domain_for_matching(
            sender_info.company_domain
        )

        # Alle Entities laden
        stmt = select(BusinessEntity).where(
            BusinessEntity.deleted_at.is_(None)
        ).limit(500)
        result = await self.db.execute(stmt)
        entities = result.scalars().all()

        for entity in entities:
            best_similarity = 0.0

            # Name normalisieren und vergleichen
            if entity.name:
                entity_name_normalized = self._normalize_domain_for_matching(entity.name)
                sim = self._calculate_similarity(
                    company_domain_normalized, entity_name_normalized
                )
                best_similarity = max(best_similarity, sim)

            # Short name
            if entity.short_name:
                short_name_normalized = self._normalize_domain_for_matching(
                    entity.short_name
                )
                sim = self._calculate_similarity(
                    company_domain_normalized, short_name_normalized
                )
                best_similarity = max(best_similarity, sim)

            if best_similarity >= self.suggestion_threshold:
                matches.append(
                    (
                        entity,
                        best_similarity * 0.85,  # Max 85% für Domain-zu-Name
                        f"Domain '{sender_info.domain}' ähnlich zu '{entity.name}'",
                    )
                )

        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[:5]

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _normalize_name(self, name: str) -> str:
        """Normalisiert einen Namen für Vergleiche."""
        if not name:
            return ""
        # Kleinbuchstaben, mehrfache Leerzeichen entfernen
        name = name.lower().strip()
        name = re.sub(r"\s+", " ", name)
        return name

    def _normalize_domain_for_matching(self, text: str) -> str:
        """Normalisiert Text für Domain-zu-Name-Matching.

        Entfernt:
        - Umlaute (ue -> u, etc.)
        - Bindestriche
        - Rechtsformen (GmbH, AG, etc.)
        """
        if not text:
            return ""

        text = text.lower().strip()

        # Umlaute ersetzen
        replacements = {
            "ä": "a",
            "ö": "o",
            "ü": "u",
            "ß": "ss",
            "ae": "a",
            "oe": "o",
            "ue": "u",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)

        # Bindestriche und Punkte entfernen
        text = re.sub(r"[-._]", "", text)

        # Rechtsformen entfernen
        legal_forms = [
            "gmbh",
            "mbh",
            "ag",
            "kg",
            "ohg",
            "gbr",
            "ug",
            "co",
            "ltd",
            "inc",
            "e.k.",
            "ek",
        ]
        for form in legal_forms:
            text = re.sub(rf"\b{form}\b", "", text)

        # Leerzeichen normalisieren
        text = re.sub(r"\s+", "", text)

        return text

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Berechnet Ähnlichkeit zwischen zwei Texten (0.0-1.0)."""
        if not text1 or not text2:
            return 0.0
        return SequenceMatcher(None, text1, text2).ratio()

    def _deduplicate_suggestions(
        self,
        suggestions: List[EmailMatchSuggestion],
        exclude_id: Optional[UUID] = None,
    ) -> List[EmailMatchSuggestion]:
        """Entfernt Duplikate aus Vorschlägen."""
        seen_ids = set()
        if exclude_id:
            seen_ids.add(exclude_id)

        unique = []
        for suggestion in sorted(suggestions, key=lambda s: s.confidence, reverse=True):
            if suggestion.entity_id not in seen_ids:
                seen_ids.add(suggestion.entity_id)
                unique.append(suggestion)

        return unique[:5]  # Max 5 Vorschläge


# ============================================================================
# Standalone Functions
# ============================================================================


async def get_email_sender_matcher(
    db: AsyncSession,
    user_id: Optional[UUID] = None,
) -> EmailSenderMatcherService:
    """Factory-Funktion die User-spezifische Settings laedt.

    Args:
        db: Async Database Session
        user_id: Optional User-ID für personalisierte Settings

    Returns:
        Konfigurierter EmailSenderMatcherService
    """
    # Default Settings
    auto_assign_threshold = 0.85
    suggestion_threshold = 0.60
    whitelist: List[str] = []
    blacklist = [
        "gmail.com",
        "googlemail.com",
        "yahoo.com",
        "yahoo.de",
        "outlook.com",
        "hotmail.com",
        "hotmail.de",
        "web.de",
        "gmx.de",
        "gmx.net",
        "t-online.de",
        "freenet.de",
        "noreply.*",
        "no-reply.*",
    ]

    # User-spezifische Settings laden wenn vorhanden
    if user_id:
        try:
            from app.db.models import UserPreferences


            stmt = select(UserPreferences).where(
                UserPreferences.user_id == user_id
            )
            result = await db.execute(stmt)
            prefs = result.scalar_one_or_none()

            if prefs and prefs.preferences:
                email_settings = prefs.preferences.get("email_import", {})
                auto_assign_threshold = email_settings.get(
                    "auto_assign_threshold", auto_assign_threshold
                )
                suggestion_threshold = email_settings.get(
                    "suggestion_threshold", suggestion_threshold
                )
                whitelist = email_settings.get("domain_whitelist", whitelist)
                blacklist = email_settings.get("domain_blacklist", blacklist)

        except Exception as e:
            logger.warning(
                "failed_to_load_user_email_settings",
                user_id=str(user_id),
                **safe_error_log(e),
            )

    return EmailSenderMatcherService(
        db=db,
        auto_assign_threshold=auto_assign_threshold,
        suggestion_threshold=suggestion_threshold,
        whitelist=whitelist,
        blacklist=blacklist,
    )
