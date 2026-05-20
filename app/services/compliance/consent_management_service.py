# -*- coding: utf-8 -*-
"""GDPR Consent Management Service - Granulare Einwilligungsverwaltung.

PHASE 7: Compliance & Audit - GDPR Erweiterungen

Verwaltet granulare Einwilligungen nach DSGVO:
- Einwilligungs-Scopes (personal_data, financial_data, document_processing, etc.)
- Versionierte Consent-Texte mit SHA-256 Hash
- Consent-Widerruf mit Audit-Trail
- Historie aller Einwilligungsänderungen

Gesetzliche Grundlagen:
- Art. 6 DSGVO: Rechtmaessigkeit der Verarbeitung
- Art. 7 DSGVO: Bedingungen für die Einwilligung
- Art. 13/14 DSGVO: Informationspflichten
"""

import hashlib
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass, field
from enum import Enum

import structlog
from sqlalchemy import select, func, and_, or_, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums & Constants
# =============================================================================

class ConsentScope(str, Enum):
    """Verfügbare Einwilligungs-Scopes nach DSGVO."""
    PERSONAL_DATA = "personal_data"
    FINANCIAL_DATA = "financial_data"
    DOCUMENT_PROCESSING = "document_processing"
    ANALYTICS = "analytics"
    MARKETING = "marketing"
    THIRD_PARTY_SHARING = "third_party_sharing"
    AUTOMATED_DECISIONS = "automated_decisions"


class ConsentMethod(str, Enum):
    """Methode der Einwilligung."""
    WEB_FORM = "web_form"
    API = "api"
    PAPER = "paper"
    VERBAL = "verbal"
    DOUBLE_OPT_IN = "double_opt_in"


class ConsentHistoryAction(str, Enum):
    """Aktionen in der Consent-Historie."""
    GRANTED = "granted"
    WITHDRAWN = "withdrawn"
    UPDATED = "updated"
    EXPIRED = "expired"
    VERSION_CHANGED = "version_changed"


class ConsentStatus(str, Enum):
    """Status einer Einwilligung."""
    ACTIVE = "active"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"
    PENDING = "pending"
    NOT_GIVEN = "not_given"


# Standard-Consent-Beschreibungen (Deutsch)
DEFAULT_CONSENT_DESCRIPTIONS: Dict[str, Dict[str, str]] = {
    "personal_data": {
        "title": "Verarbeitung personenbezogener Daten",
        "description": "Einwilligung zur Verarbeitung Ihrer personenbezogenen Daten "
                       "(Name, E-Mail, Adresse) für die Erbringung unserer Dienstleistungen.",
    },
    "financial_data": {
        "title": "Verarbeitung finanzieller Daten",
        "description": "Einwilligung zur Verarbeitung Ihrer finanziellen Daten "
                       "(Rechnungen, Zahlungsinformationen, Bankdaten) für die Buchhaltung.",
    },
    "document_processing": {
        "title": "Automatische Dokumentenverarbeitung",
        "description": "Einwilligung zur automatischen Verarbeitung Ihrer Dokumente "
                       "mittels OCR und KI-Analyse zur Datenextraktion.",
    },
    "analytics": {
        "title": "Nutzungsanalyse",
        "description": "Einwilligung zur Analyse Ihres Nutzungsverhaltens "
                       "zur Verbesserung unserer Dienste.",
    },
    "marketing": {
        "title": "Marketing-Kommunikation",
        "description": "Einwilligung zum Erhalt von Marketing-Mitteilungen "
                       "über neue Funktionen und Angebote.",
    },
    "third_party_sharing": {
        "title": "Weitergabe an Dritte",
        "description": "Einwilligung zur Weitergabe Ihrer Daten an "
                       "Drittanbieter (z.B. Steuerberater, DATEV).",
    },
    "automated_decisions": {
        "title": "Automatisierte Entscheidungen",
        "description": "Einwilligung zu automatisierten Entscheidungen "
                       "basierend auf Ihren Daten (z.B. Risiko-Scoring).",
    },
}

# Pflicht-Scopes die für die Nutzung erforderlich sind
MANDATORY_SCOPES = [ConsentScope.PERSONAL_DATA, ConsentScope.DOCUMENT_PROCESSING]


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ConsentRecord:
    """Repraesentation eines Einwilligungs-Eintrags."""
    id: uuid.UUID
    user_id: uuid.UUID
    scope: ConsentScope
    consent_given: bool
    consent_version_id: Optional[uuid.UUID]
    consent_text_hash: Optional[str]
    granted_at: Optional[datetime]
    withdrawn_at: Optional[datetime]
    valid_from: datetime
    valid_until: Optional[datetime]
    consent_method: Optional[ConsentMethod]
    status: ConsentStatus

    @classmethod
    def from_db_model(cls, model: "GDPRConsentLog") -> "ConsentRecord":
        """Erstellt ConsentRecord aus DB-Model."""
        # Bestimme Status
        if model.withdrawn_at:
            status = ConsentStatus.WITHDRAWN
        elif model.valid_until and model.valid_until < datetime.now(timezone.utc):
            status = ConsentStatus.EXPIRED
        elif model.consent_given:
            status = ConsentStatus.ACTIVE
        else:
            status = ConsentStatus.NOT_GIVEN

        return cls(
            id=model.id,
            user_id=model.user_id,
            scope=ConsentScope(model.scope),
            consent_given=model.consent_given,
            consent_version_id=model.consent_version_id,
            consent_text_hash=model.consent_text_hash,
            granted_at=model.granted_at,
            withdrawn_at=model.withdrawn_at,
            valid_from=model.valid_from,
            valid_until=model.valid_until,
            consent_method=ConsentMethod(model.consent_method) if model.consent_method else None,
            status=status,
        )


@dataclass
class ConsentVersionInfo:
    """Information über eine Consent-Version."""
    id: uuid.UUID
    scope: str
    version: str
    title: str
    description: str
    text_hash: str
    language: str
    is_active: bool
    effective_from: datetime
    effective_until: Optional[datetime]


@dataclass
class ConsentGrantResult:
    """Ergebnis einer Consent-Erteilung."""
    success: bool
    consent_id: uuid.UUID
    scope: ConsentScope
    version_id: Optional[uuid.UUID]
    text_hash: str
    granted_at: datetime
    message: str


@dataclass
class ConsentWithdrawalResult:
    """Ergebnis eines Consent-Widerrufs."""
    success: bool
    consent_id: uuid.UUID
    scope: ConsentScope
    withdrawn_at: datetime
    was_active: bool
    message: str
    impacts: List[str] = field(default_factory=list)


@dataclass
class ConsentCheckResult:
    """Ergebnis einer Consent-Prüfung."""
    scope: ConsentScope
    status: ConsentStatus
    consent_given: bool
    version_current: bool
    granted_at: Optional[datetime]
    withdrawn_at: Optional[datetime]
    requires_renewal: bool
    message: str


@dataclass
class ConsentHistoryEntry:
    """Eintrag in der Consent-Historie."""
    id: uuid.UUID
    consent_scope_id: uuid.UUID
    action: ConsentHistoryAction
    previous_value: Optional[bool]
    new_value: bool
    consent_version_id: Optional[uuid.UUID]
    ip_address: Optional[str]
    user_agent: Optional[str]
    reason: Optional[str]
    created_at: datetime


@dataclass
class ConsentSummary:
    """Zusammenfassung des Consent-Status eines Users."""
    user_id: uuid.UUID
    total_scopes: int
    active_consents: int
    withdrawn_consents: int
    pending_consents: int
    mandatory_complete: bool
    last_update: Optional[datetime]
    by_scope: Dict[str, ConsentStatus]


# =============================================================================
# Service Implementation
# =============================================================================

class ConsentManagementService:
    """Service für DSGVO-konforme Einwilligungsverwaltung.

    Implementiert:
    - Granulare Consent-Scopes
    - Versionierte Consent-Texte
    - Vollständiger Audit-Trail
    - Consent-Widerruf mit Impact-Analyse
    """

    _instance: Optional["ConsentManagementService"] = None

    def __new__(cls) -> "ConsentManagementService":
        """Singleton Pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialisiert den Service."""
        if self._initialized:
            return
        self._initialized = True
        self.default_descriptions = DEFAULT_CONSENT_DESCRIPTIONS
        self.mandatory_scopes = MANDATORY_SCOPES
        logger.info("consent_management_service_initialized")

    # =========================================================================
    # Consent Version Management
    # =========================================================================

    @staticmethod
    def calculate_text_hash(text: str) -> str:
        """Berechnet SHA-256 Hash eines Consent-Textes.

        Args:
            text: Der Consent-Text

        Returns:
            SHA-256 Hash als Hex-String
        """
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    async def create_consent_version(
        self,
        db: AsyncSession,
        scope: ConsentScope,
        version: str,
        title: str,
        description: str,
        full_text: str,
        language: str = "de",
        effective_from: Optional[datetime] = None,
        created_by_id: Optional[uuid.UUID] = None,
    ) -> ConsentVersionInfo:
        """Erstellt eine neue Consent-Text-Version.

        Args:
            db: Datenbank-Session
            scope: Consent-Scope
            version: Versionsnummer (z.B. "1.0", "2.0")
            title: Titel der Einwilligung
            description: Kurzbeschreibung
            full_text: Vollständiger Consent-Text
            language: Sprache (default: "de")
            effective_from: Ab wann gültig (default: jetzt)
            created_by_id: ID des Erstellers

        Returns:
            ConsentVersionInfo mit der erstellten Version
        """
        # Import hier um zirkuläre Imports zu vermeiden
        from app.db.models import GDPRConsentVersion

        text_hash = self.calculate_text_hash(full_text)
        effective = effective_from or datetime.now(timezone.utc)

        # Deaktiviere vorherige aktive Versionen für diesen Scope
        await db.execute(
            update(GDPRConsentVersion)
            .where(
                and_(
                    GDPRConsentVersion.scope == scope.value,
                    GDPRConsentVersion.is_active == True,
                )
            )
            .values(
                is_active=False,
                effective_until=effective,
            )
        )

        # Erstelle neue Version
        version_obj = GDPRConsentVersion(
            id=uuid.uuid4(),
            scope=scope.value,
            version=version,
            title=title,
            description=description,
            full_text=full_text,
            text_hash=text_hash,
            language=language,
            is_active=True,
            effective_from=effective,
            created_by_id=created_by_id,
        )

        db.add(version_obj)
        await db.flush()

        logger.info(
            "consent_version_created",
            scope=scope.value,
            version=version,
            text_hash=text_hash[:16],
        )

        return ConsentVersionInfo(
            id=version_obj.id,
            scope=version_obj.scope,
            version=version_obj.version,
            title=version_obj.title,
            description=version_obj.description,
            text_hash=version_obj.text_hash,
            language=version_obj.language,
            is_active=version_obj.is_active,
            effective_from=version_obj.effective_from,
            effective_until=version_obj.effective_until,
        )

    async def get_active_consent_version(
        self,
        db: AsyncSession,
        scope: ConsentScope,
        language: str = "de",
    ) -> Optional[ConsentVersionInfo]:
        """Holt die aktive Consent-Version für einen Scope.

        Args:
            db: Datenbank-Session
            scope: Consent-Scope
            language: Gewünschte Sprache

        Returns:
            ConsentVersionInfo oder None
        """
        from app.db.models import GDPRConsentVersion

        result = await db.execute(
            select(GDPRConsentVersion)
            .where(
                and_(
                    GDPRConsentVersion.scope == scope.value,
                    GDPRConsentVersion.is_active == True,
                    GDPRConsentVersion.language == language,
                )
            )
        )
        version = result.scalar_one_or_none()

        if not version:
            return None

        return ConsentVersionInfo(
            id=version.id,
            scope=version.scope,
            version=version.version,
            title=version.title,
            description=version.description,
            text_hash=version.text_hash,
            language=version.language,
            is_active=version.is_active,
            effective_from=version.effective_from,
            effective_until=version.effective_until,
        )

    async def get_all_consent_versions(
        self,
        db: AsyncSession,
        scope: Optional[ConsentScope] = None,
        active_only: bool = True,
    ) -> List[ConsentVersionInfo]:
        """Holt alle Consent-Versionen.

        Args:
            db: Datenbank-Session
            scope: Optional - Filter nach Scope
            active_only: Nur aktive Versionen

        Returns:
            Liste von ConsentVersionInfo
        """
        from app.db.models import GDPRConsentVersion

        query = select(GDPRConsentVersion)
        conditions = []

        if scope:
            conditions.append(GDPRConsentVersion.scope == scope.value)
        if active_only:
            conditions.append(GDPRConsentVersion.is_active == True)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(GDPRConsentVersion.scope, GDPRConsentVersion.effective_from.desc())

        result = await db.execute(query)
        versions = result.scalars().all()

        return [
            ConsentVersionInfo(
                id=v.id,
                scope=v.scope,
                version=v.version,
                title=v.title,
                description=v.description,
                text_hash=v.text_hash,
                language=v.language,
                is_active=v.is_active,
                effective_from=v.effective_from,
                effective_until=v.effective_until,
            )
            for v in versions
        ]

    # =========================================================================
    # Consent Recording
    # =========================================================================

    async def record_consent(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        scope: ConsentScope,
        consent_given: bool,
        company_id: Optional[uuid.UUID] = None,
        consent_version_id: Optional[uuid.UUID] = None,
        consent_method: ConsentMethod = ConsentMethod.WEB_FORM,
        valid_until: Optional[datetime] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> ConsentGrantResult:
        """Zeichnet eine Einwilligung auf.

        Args:
            db: Datenbank-Session
            user_id: User-ID
            scope: Consent-Scope
            consent_given: True wenn Einwilligung erteilt
            company_id: Optional - Company-ID für Multi-Tenant
            consent_version_id: Optional - Version des Consent-Textes
            consent_method: Methode der Einwilligung
            valid_until: Optional - Ablaufdatum
            ip_address: IP-Adresse des Users (für Audit)
            user_agent: User-Agent (für Audit)

        Returns:
            ConsentGrantResult
        """
        from app.db.models import GDPRConsentScope, GDPRConsentVersion, GDPRConsentHistory

        now = datetime.now(timezone.utc)

        # Hole aktive Version wenn keine angegeben
        text_hash = ""
        if consent_version_id:
            version_result = await db.execute(
                select(GDPRConsentVersion).where(GDPRConsentVersion.id == consent_version_id)
            )
            version = version_result.scalar_one_or_none()
            if version:
                text_hash = version.text_hash
        else:
            active_version = await self.get_active_consent_version(db, scope)
            if active_version:
                consent_version_id = active_version.id
                text_hash = active_version.text_hash

        # Prüfe ob bereits ein Consent-Eintrag existiert
        existing_result = await db.execute(
            select(GDPRConsentScope)
            .where(
                and_(
                    GDPRConsentScope.user_id == user_id,
                    GDPRConsentScope.scope == scope.value,
                    or_(
                        GDPRConsentScope.company_id == company_id,
                        GDPRConsentScope.company_id.is_(None),
                    ) if company_id else GDPRConsentScope.company_id.is_(None),
                )
            )
        )
        existing = existing_result.scalar_one_or_none()

        consent_id = uuid.uuid4()
        previous_value = None

        if existing:
            # Update existierenden Eintrag
            consent_id = existing.id
            previous_value = existing.consent_given

            existing.consent_given = consent_given
            existing.consent_version_id = consent_version_id
            existing.consent_text_hash = text_hash
            existing.consent_method = consent_method.value
            existing.ip_address = ip_address
            existing.user_agent = user_agent
            existing.valid_until = valid_until
            existing.updated_at = now

            if consent_given:
                existing.granted_at = now
                existing.withdrawn_at = None
            else:
                existing.withdrawn_at = now
        else:
            # Neuer Eintrag
            consent_obj = GDPRConsentScope(
                id=consent_id,
                user_id=user_id,
                company_id=company_id,
                scope=scope.value,
                consent_given=consent_given,
                consent_version_id=consent_version_id,
                consent_text_hash=text_hash,
                granted_at=now if consent_given else None,
                withdrawn_at=None if consent_given else now,
                valid_from=now,
                valid_until=valid_until,
                consent_method=consent_method.value,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            db.add(consent_obj)

        # Erstelle History-Eintrag
        history_entry = GDPRConsentHistory(
            id=uuid.uuid4(),
            consent_scope_id=consent_id,
            user_id=user_id,
            action=ConsentHistoryAction.GRANTED.value if consent_given else ConsentHistoryAction.WITHDRAWN.value,
            previous_value=previous_value,
            new_value=consent_given,
            consent_version_id=consent_version_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.add(history_entry)

        await db.flush()

        logger.info(
            "consent_recorded",
            user_id=str(user_id),
            scope=scope.value,
            consent_given=consent_given,
            method=consent_method.value,
        )

        message = "Einwilligung erfolgreich erteilt" if consent_given else "Einwilligung verweigert"

        return ConsentGrantResult(
            success=True,
            consent_id=consent_id,
            scope=scope,
            version_id=consent_version_id,
            text_hash=text_hash,
            granted_at=now,
            message=message,
        )

    async def grant_consent(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        scope: ConsentScope,
        company_id: Optional[uuid.UUID] = None,
        consent_version_id: Optional[uuid.UUID] = None,
        consent_method: ConsentMethod = ConsentMethod.WEB_FORM,
        valid_until: Optional[datetime] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> ConsentGrantResult:
        """Erteilt eine Einwilligung (Convenience-Wrapper).

        Args:
            db: Datenbank-Session
            user_id: User-ID
            scope: Consent-Scope
            company_id: Optional - Company-ID
            consent_version_id: Optional - Version-ID
            consent_method: Einwilligungsmethode
            valid_until: Optional - Ablaufdatum
            ip_address: IP-Adresse
            user_agent: User-Agent

        Returns:
            ConsentGrantResult
        """
        return await self.record_consent(
            db=db,
            user_id=user_id,
            scope=scope,
            consent_given=True,
            company_id=company_id,
            consent_version_id=consent_version_id,
            consent_method=consent_method,
            valid_until=valid_until,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def grant_multiple_consents(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        scopes: List[ConsentScope],
        company_id: Optional[uuid.UUID] = None,
        consent_method: ConsentMethod = ConsentMethod.WEB_FORM,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> List[ConsentGrantResult]:
        """Erteilt mehrere Einwilligungen auf einmal.

        Args:
            db: Datenbank-Session
            user_id: User-ID
            scopes: Liste von Consent-Scopes
            company_id: Optional - Company-ID
            consent_method: Einwilligungsmethode
            ip_address: IP-Adresse
            user_agent: User-Agent

        Returns:
            Liste von ConsentGrantResult
        """
        results = []
        for scope in scopes:
            result = await self.grant_consent(
                db=db,
                user_id=user_id,
                scope=scope,
                company_id=company_id,
                consent_method=consent_method,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            results.append(result)
        return results

    # =========================================================================
    # Consent Checking
    # =========================================================================

    async def check_consent(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        scope: ConsentScope,
        company_id: Optional[uuid.UUID] = None,
    ) -> ConsentCheckResult:
        """Prüft den Consent-Status für einen Scope.

        Args:
            db: Datenbank-Session
            user_id: User-ID
            scope: Consent-Scope
            company_id: Optional - Company-ID

        Returns:
            ConsentCheckResult
        """
        from app.db.models import GDPRConsentScope

        now = datetime.now(timezone.utc)

        # Hole Consent-Eintrag
        query = select(GDPRConsentScope).where(
            and_(
                GDPRConsentScope.user_id == user_id,
                GDPRConsentScope.scope == scope.value,
            )
        )
        if company_id:
            query = query.where(
                or_(
                    GDPRConsentScope.company_id == company_id,
                    GDPRConsentScope.company_id.is_(None),
                )
            )

        result = await db.execute(query)
        consent = result.scalar_one_or_none()

        if not consent:
            return ConsentCheckResult(
                scope=scope,
                status=ConsentStatus.NOT_GIVEN,
                consent_given=False,
                version_current=False,
                granted_at=None,
                withdrawn_at=None,
                requires_renewal=True,
                message="Keine Einwilligung vorhanden",
            )

        # Bestimme Status
        status = ConsentStatus.NOT_GIVEN
        requires_renewal = False
        message = ""

        if consent.withdrawn_at:
            status = ConsentStatus.WITHDRAWN
            message = "Einwilligung wurde widerrufen"
        elif consent.valid_until and consent.valid_until < now:
            status = ConsentStatus.EXPIRED
            requires_renewal = True
            message = "Einwilligung ist abgelaufen"
        elif consent.consent_given:
            status = ConsentStatus.ACTIVE
            message = "Einwilligung ist aktiv"
        else:
            status = ConsentStatus.NOT_GIVEN
            message = "Einwilligung wurde nicht erteilt"

        # Prüfe ob Version aktuell ist
        version_current = True
        active_version = await self.get_active_consent_version(db, scope)
        if active_version and consent.consent_text_hash != active_version.text_hash:
            version_current = False
            requires_renewal = True
            message += " (neue Version verfügbar)"

        return ConsentCheckResult(
            scope=scope,
            status=status,
            consent_given=consent.consent_given and status == ConsentStatus.ACTIVE,
            version_current=version_current,
            granted_at=consent.granted_at,
            withdrawn_at=consent.withdrawn_at,
            requires_renewal=requires_renewal,
            message=message,
        )

    async def check_all_consents(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        company_id: Optional[uuid.UUID] = None,
    ) -> Dict[ConsentScope, ConsentCheckResult]:
        """Prüft alle Consent-Scopes für einen User.

        Args:
            db: Datenbank-Session
            user_id: User-ID
            company_id: Optional - Company-ID

        Returns:
            Dict mit Scope -> ConsentCheckResult
        """
        results = {}
        for scope in ConsentScope:
            results[scope] = await self.check_consent(db, user_id, scope, company_id)
        return results

    async def has_required_consents(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        company_id: Optional[uuid.UUID] = None,
    ) -> Tuple[bool, List[ConsentScope]]:
        """Prüft ob alle Pflicht-Einwilligungen vorliegen.

        Args:
            db: Datenbank-Session
            user_id: User-ID
            company_id: Optional - Company-ID

        Returns:
            Tuple (alle_vorhanden, fehlende_scopes)
        """
        missing = []
        for scope in self.mandatory_scopes:
            check = await self.check_consent(db, user_id, scope, company_id)
            if not check.consent_given:
                missing.append(scope)

        return len(missing) == 0, missing

    # =========================================================================
    # Consent Withdrawal
    # =========================================================================

    async def withdraw_consent(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        scope: ConsentScope,
        company_id: Optional[uuid.UUID] = None,
        reason: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> ConsentWithdrawalResult:
        """Widerruft eine Einwilligung.

        Args:
            db: Datenbank-Session
            user_id: User-ID
            scope: Consent-Scope
            company_id: Optional - Company-ID
            reason: Optional - Grund für Widerruf
            ip_address: IP-Adresse
            user_agent: User-Agent

        Returns:
            ConsentWithdrawalResult
        """
        from app.db.models import GDPRConsentScope, GDPRConsentHistory

        now = datetime.now(timezone.utc)

        # Hole existierenden Consent
        query = select(GDPRConsentScope).where(
            and_(
                GDPRConsentScope.user_id == user_id,
                GDPRConsentScope.scope == scope.value,
            )
        )
        if company_id:
            query = query.where(
                or_(
                    GDPRConsentScope.company_id == company_id,
                    GDPRConsentScope.company_id.is_(None),
                )
            )

        result = await db.execute(query)
        consent = result.scalar_one_or_none()

        if not consent:
            return ConsentWithdrawalResult(
                success=False,
                consent_id=uuid.UUID(int=0),
                scope=scope,
                withdrawn_at=now,
                was_active=False,
                message="Keine Einwilligung für diesen Scope gefunden",
            )

        was_active = consent.consent_given and not consent.withdrawn_at

        # Aktualisiere Consent
        consent.consent_given = False
        consent.withdrawn_at = now
        consent.updated_at = now

        # Erstelle History-Eintrag
        history_entry = GDPRConsentHistory(
            id=uuid.uuid4(),
            consent_scope_id=consent.id,
            user_id=user_id,
            action=ConsentHistoryAction.WITHDRAWN.value,
            previous_value=True,
            new_value=False,
            ip_address=ip_address,
            user_agent=user_agent,
            reason=reason,
        )
        db.add(history_entry)

        await db.flush()

        # Bestimme Auswirkungen
        impacts = self._get_withdrawal_impacts(scope)

        logger.info(
            "consent_withdrawn",
            user_id=str(user_id),
            scope=scope.value,
            reason=reason,
        )

        return ConsentWithdrawalResult(
            success=True,
            consent_id=consent.id,
            scope=scope,
            withdrawn_at=now,
            was_active=was_active,
            message="Einwilligung erfolgreich widerrufen",
            impacts=impacts,
        )

    def _get_withdrawal_impacts(self, scope: ConsentScope) -> List[str]:
        """Ermittelt die Auswirkungen eines Consent-Widerrufs.

        Args:
            scope: Der widerrufene Scope

        Returns:
            Liste von Auswirkungs-Beschreibungen
        """
        impacts_map = {
            ConsentScope.PERSONAL_DATA: [
                "Zugriff auf personenbezogene Daten wird eingeschraenkt",
                "Account-Funktionen könnten eingeschraenkt sein",
            ],
            ConsentScope.FINANCIAL_DATA: [
                "Finanzauswertungen werden deaktiviert",
                "Automatische Buchungsvorschläge werden gestoppt",
            ],
            ConsentScope.DOCUMENT_PROCESSING: [
                "Automatische OCR-Verarbeitung wird gestoppt",
                "Neue Dokumente werden nicht mehr analysiert",
            ],
            ConsentScope.ANALYTICS: [
                "Nutzungsanalysen werden gestoppt",
                "Personalisierte Empfehlungen werden deaktiviert",
            ],
            ConsentScope.MARKETING: [
                "Marketing-Emails werden gestoppt",
                "Newsletter-Abonnement wird beendet",
            ],
            ConsentScope.THIRD_PARTY_SHARING: [
                "Datenweitergabe an Dritte wird gestoppt",
                "DATEV-Export wird deaktiviert",
            ],
            ConsentScope.AUTOMATED_DECISIONS: [
                "Automatische Entscheidungen werden deaktiviert",
                "Risiko-Scoring wird gestoppt",
            ],
        }
        return impacts_map.get(scope, [])

    # =========================================================================
    # Consent History
    # =========================================================================

    async def get_consent_history(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        scope: Optional[ConsentScope] = None,
        limit: int = 100,
    ) -> List[ConsentHistoryEntry]:
        """Holt die Consent-Historie eines Users.

        Args:
            db: Datenbank-Session
            user_id: User-ID
            scope: Optional - Filter nach Scope
            limit: Maximale Anzahl Einträge

        Returns:
            Liste von ConsentHistoryEntry
        """
        from app.db.models import GDPRConsentHistory, GDPRConsentScope

        query = (
            select(GDPRConsentHistory)
            .join(GDPRConsentScope, GDPRConsentHistory.consent_scope_id == GDPRConsentScope.id)
            .where(GDPRConsentHistory.user_id == user_id)
        )

        if scope:
            query = query.where(GDPRConsentScope.scope == scope.value)

        query = query.order_by(GDPRConsentHistory.created_at.desc()).limit(limit)

        result = await db.execute(query)
        entries = result.scalars().all()

        return [
            ConsentHistoryEntry(
                id=e.id,
                consent_scope_id=e.consent_scope_id,
                action=ConsentHistoryAction(e.action),
                previous_value=e.previous_value,
                new_value=e.new_value,
                consent_version_id=e.consent_version_id,
                ip_address=e.ip_address,
                user_agent=e.user_agent,
                reason=e.reason,
                created_at=e.created_at,
            )
            for e in entries
        ]

    # =========================================================================
    # Consent Summary & Statistics
    # =========================================================================

    async def get_consent_summary(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        company_id: Optional[uuid.UUID] = None,
    ) -> ConsentSummary:
        """Erstellt eine Zusammenfassung des Consent-Status.

        Args:
            db: Datenbank-Session
            user_id: User-ID
            company_id: Optional - Company-ID

        Returns:
            ConsentSummary
        """
        all_checks = await self.check_all_consents(db, user_id, company_id)

        by_scope = {scope.value: check.status for scope, check in all_checks.items()}
        active = sum(1 for c in all_checks.values() if c.status == ConsentStatus.ACTIVE)
        withdrawn = sum(1 for c in all_checks.values() if c.status == ConsentStatus.WITHDRAWN)
        pending = sum(1 for c in all_checks.values() if c.status in [ConsentStatus.NOT_GIVEN, ConsentStatus.EXPIRED])

        mandatory_complete, _ = await self.has_required_consents(db, user_id, company_id)

        # Finde letztes Update
        history = await self.get_consent_history(db, user_id, limit=1)
        last_update = history[0].created_at if history else None

        return ConsentSummary(
            user_id=user_id,
            total_scopes=len(ConsentScope),
            active_consents=active,
            withdrawn_consents=withdrawn,
            pending_consents=pending,
            mandatory_complete=mandatory_complete,
            last_update=last_update,
            by_scope=by_scope,
        )

    async def get_users_requiring_consent_renewal(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        scope: Optional[ConsentScope] = None,
    ) -> List[uuid.UUID]:
        """Findet User die ihre Einwilligung erneuern müssen.

        Args:
            db: Datenbank-Session
            company_id: Company-ID
            scope: Optional - Filter nach Scope

        Returns:
            Liste von User-IDs
        """
        from app.db.models import GDPRConsentScope, GDPRConsentVersion

        now = datetime.now(timezone.utc)

        # Subquery für aktuelle Versionen
        active_versions_subq = (
            select(GDPRConsentVersion.scope, GDPRConsentVersion.text_hash)
            .where(GDPRConsentVersion.is_active == True)
            .subquery()
        )

        # Finde Consents mit veralteten Versionen oder abgelaufene
        query = (
            select(GDPRConsentScope.user_id)
            .distinct()
            .outerjoin(
                active_versions_subq,
                GDPRConsentScope.scope == active_versions_subq.c.scope,
            )
            .where(
                and_(
                    GDPRConsentScope.company_id == company_id,
                    GDPRConsentScope.consent_given == True,
                    GDPRConsentScope.withdrawn_at.is_(None),
                    or_(
                        GDPRConsentScope.consent_text_hash != active_versions_subq.c.text_hash,
                        GDPRConsentScope.valid_until < now,
                    ),
                )
            )
        )

        if scope:
            query = query.where(GDPRConsentScope.scope == scope.value)

        result = await db.execute(query)
        return [row[0] for row in result.all()]

    # =========================================================================
    # Initialization & Defaults
    # =========================================================================

    async def initialize_default_consent_versions(
        self,
        db: AsyncSession,
        created_by_id: Optional[uuid.UUID] = None,
    ) -> List[ConsentVersionInfo]:
        """Initialisiert Standard-Consent-Versionen.

        Args:
            db: Datenbank-Session
            created_by_id: Optional - Ersteller

        Returns:
            Liste der erstellten Versionen
        """
        created = []

        for scope in ConsentScope:
            # Prüfe ob bereits aktive Version existiert
            existing = await self.get_active_consent_version(db, scope)
            if existing:
                continue

            defaults = self.default_descriptions.get(scope.value, {})
            title = defaults.get("title", scope.value)
            description = defaults.get("description", f"Einwilligung für {scope.value}")

            # Erstelle vollständigen Consent-Text
            full_text = f"""
{title}

{description}

Diese Einwilligung kann jederzeit widerrufen werden. Der Widerruf beruehrt
nicht die Rechtmaessigkeit der aufgrund der Einwilligung bis zum Widerruf
erfolgten Verarbeitung.

Rechtsgrundlage: Art. 6 Abs. 1 lit. a DSGVO
            """.strip()

            version = await self.create_consent_version(
                db=db,
                scope=scope,
                version="1.0",
                title=title,
                description=description,
                full_text=full_text,
                created_by_id=created_by_id,
            )
            created.append(version)

        logger.info(
            "default_consent_versions_initialized",
            count=len(created),
        )

        return created


# =============================================================================
# Singleton & Factory
# =============================================================================

def get_consent_management_service() -> ConsentManagementService:
    """Factory-Funktion für ConsentManagementService."""
    return ConsentManagementService()


# Singleton-Instanz
consent_management_service = ConsentManagementService()
