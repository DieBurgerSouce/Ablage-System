# -*- coding: utf-8 -*-
"""Supplier Verification Service.

Automatische Prüfung von Geschäftspartnern gegen externe Register:
- Handelsregister (Firmenexistenz, Geschäftsführer)
- Insolvenzregister (Keine Insolvenz)
- VIES (USt-IdNr Validierung, EU-weit) - ECHTE API-INTEGRATION
- Bundesanzeiger (Jahresabschluesse, Bekanntmachungen)

Features:
- Caching mit 30-Tage TTL
- Risiko-Score Integration
- Batch-Verifizierung
- Audit-Trail
- VIES SOAP API Integration (EU-Kommission)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import unicodedata
import xml.etree.ElementTree as ET  # Für ET.ParseError Exception
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING
from uuid import UUID
from xml.sax.saxutils import escape as xml_escape

import httpx
import structlog
from defusedxml.ElementTree import fromstring as safe_xml_fromstring
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.db.models import BusinessEntity

from app.core.config import settings
from app.services.external.handelsregister_service import (
    HandelsregisterService,
    CompanyRecord,
    CompanyDetails,
)
from app.services.external.bundesanzeiger_service import BundesanzeigerService

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums & Data Classes
# =============================================================================


class VerificationSource(str, Enum):
    """Verifizierungsquellen."""

    HANDELSREGISTER = "handelsregister"
    INSOLVENZREGISTER = "insolvenzregister"
    VIES = "vies"  # VAT Information Exchange System
    BUNDESANZEIGER = "bundesanzeiger"
    CREDITREFORM = "creditreform"  # Optional, kostenpflichtig


class VerificationStatus(str, Enum):
    """Verifizierungsstatus."""

    VERIFIED = "verified"
    NOT_FOUND = "not_found"
    WARNING = "warning"
    CRITICAL = "critical"
    PENDING = "pending"
    ERROR = "error"
    EXPIRED = "expired"


class VerificationSeverity(str, Enum):
    """Schweregrad von Befunden."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class VerificationFinding:
    """Einzelner Befund bei der Verifizierung."""

    source: VerificationSource
    severity: VerificationSeverity
    code: str
    message: str
    details: Dict[str, str | int | float | bool | None] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class HandelsregisterResult:
    """Ergebnis der Handelsregister-Prüfung."""

    found: bool
    company_name: Optional[str] = None
    legal_form: Optional[str] = None
    register_court: Optional[str] = None
    register_number: Optional[str] = None
    registered_address: Optional[str] = None
    managing_directors: Optional[List[str]] = None
    status: str = "unknown"
    founded_date: Optional[str] = None
    capital: Optional[str] = None


@dataclass
class InsolvenzResult:
    """Ergebnis der Insolvenzregister-Prüfung."""

    has_insolvency: bool
    insolvency_type: Optional[str] = None  # "opened", "rejected", "terminated"
    court: Optional[str] = None
    case_number: Optional[str] = None
    published_date: Optional[str] = None
    status: Optional[str] = None


@dataclass
class ViesResult:
    """Ergebnis der VIES-Validierung."""

    valid: bool
    vat_number: Optional[str] = None
    country_code: Optional[str] = None
    company_name: Optional[str] = None
    company_address: Optional[str] = None
    request_date: Optional[str] = None
    consultation_number: Optional[str] = None


@dataclass
class BundesanzeigerAnnouncement:
    """Einzelne Bundesanzeiger-Veröffentlichung."""

    date: Optional[str] = None
    type: Optional[str] = None
    description: Optional[str] = None


@dataclass
class BundesanzeigerResult:
    """Ergebnis der Bundesanzeiger-Prüfung."""

    found: bool
    publications_count: int = 0
    latest_annual_report: Optional[str] = None
    latest_balance_sheet_date: Optional[str] = None
    announcements: List[BundesanzeigerAnnouncement] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class VerificationResult:
    """Gesamtergebnis der Lieferanten-Verifizierung."""

    entity_id: UUID
    entity_name: str
    overall_status: VerificationStatus
    verification_score: int  # 0-100
    sources_checked: List[VerificationSource]
    findings: List[VerificationFinding]
    handelsregister: Optional[HandelsregisterResult] = None
    insolvenzregister: Optional[InsolvenzResult] = None
    vies: Optional[ViesResult] = None
    bundesanzeiger: Optional[BundesanzeigerResult] = None
    verified_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(days=30)
    )
    cached: bool = False


# =============================================================================
# Cache Model (JSONB in AppConfig)
# =============================================================================

VERIFICATION_CACHE_KEY = "supplier_verification_cache"
CACHE_TTL_DAYS = 30


# =============================================================================
# Supplier Verification Service
# =============================================================================


class SupplierVerificationService:
    """Service für Lieferanten-Verifizierung.

    Prüft Geschäftspartner gegen externe Register und berechnet
    einen Verifizierungs-Score.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Service.

        Args:
            db: AsyncSession für Datenbankoperationen
        """
        self.db = db
        self.handelsregister = HandelsregisterService()
        self.bundesanzeiger = BundesanzeigerService()

    # =========================================================================
    # Public API
    # =========================================================================

    async def verify_entity(
        self,
        entity_id: UUID,
        company_id: UUID,
        force_refresh: bool = False,
        sources: Optional[List[VerificationSource]] = None,
    ) -> VerificationResult:
        """Verifiziert einen Geschäftspartner.

        Args:
            entity_id: ID des zu verifizierenden Entity
            company_id: Company-ID für Multi-Tenant
            force_refresh: Cache ignorieren
            sources: Optionale Liste zu prüfender Quellen

        Returns:
            VerificationResult mit allen Befunden
        """
        # Entity laden
        from app.db.models import BusinessEntity

        query = select(BusinessEntity).where(
            and_(
                BusinessEntity.id == entity_id,
                BusinessEntity.company_id == company_id,
            )
        )
        result = await self.db.execute(query)
        entity = result.scalar_one_or_none()

        if not entity:
            logger.warning(
                "verification_entity_not_found",
                entity_id=str(entity_id),
            )
            return self._create_error_result(entity_id, "Entity nicht gefunden")

        # Cache prüfen
        if not force_refresh:
            cached_result = await self._get_cached_result(entity_id, company_id)
            if cached_result:
                cached_result.cached = True
                return cached_result

        # Quellen bestimmen
        if sources is None:
            sources = [
                VerificationSource.HANDELSREGISTER,
                VerificationSource.INSOLVENZREGISTER,
                VerificationSource.VIES,
                VerificationSource.BUNDESANZEIGER,
            ]

        # Verifizierung durchführen
        findings: List[VerificationFinding] = []
        sources_checked: List[VerificationSource] = []

        handelsregister_result: Optional[HandelsregisterResult] = None
        insolvenz_result: Optional[InsolvenzResult] = None
        vies_result: Optional[ViesResult] = None
        bundesanzeiger_result: Optional[BundesanzeigerResult] = None

        entity_name = entity.name or entity.display_name or "Unbekannt"

        # Handelsregister
        if VerificationSource.HANDELSREGISTER in sources:
            sources_checked.append(VerificationSource.HANDELSREGISTER)
            try:
                handelsregister_result, hr_findings = await self._check_handelsregister(
                    entity_name,
                    getattr(entity, "address_city", None),
                )
                findings.extend(hr_findings)
            except Exception as e:
                # SECURITY: Nur error_type loggen, nicht str(e) - könnte PII enthalten (CWE-532)
                logger.warning(
                    "handelsregister_check_error",
                    entity_id=str(entity_id),
                    error_type=type(e).__name__,
                )
                findings.append(
                    VerificationFinding(
                        source=VerificationSource.HANDELSREGISTER,
                        severity=VerificationSeverity.WARNING,
                        code="HR_CHECK_ERROR",
                        message="Handelsregister-Prüfung fehlgeschlagen",
                        # SECURITY: Keine Exception-Details in User-Facing Data (CWE-209)
                        details={"error_type": type(e).__name__},
                    )
                )

        # Insolvenzregister
        if VerificationSource.INSOLVENZREGISTER in sources:
            sources_checked.append(VerificationSource.INSOLVENZREGISTER)
            try:
                insolvenz_result, insolvenz_findings = await self._check_insolvenzregister(
                    entity_name,
                    getattr(entity, "address_city", None),
                )
                findings.extend(insolvenz_findings)
            except Exception as e:
                # SECURITY: Nur error_type loggen, nicht str(e) - könnte PII enthalten (CWE-532)
                logger.warning(
                    "insolvenzregister_check_error",
                    entity_id=str(entity_id),
                    error_type=type(e).__name__,
                )
                findings.append(
                    VerificationFinding(
                        source=VerificationSource.INSOLVENZREGISTER,
                        severity=VerificationSeverity.WARNING,
                        code="INSO_CHECK_ERROR",
                        message="Insolvenzregister-Prüfung fehlgeschlagen",
                        # SECURITY: Keine Exception-Details in User-Facing Data (CWE-209)
                        details={"error_type": type(e).__name__},
                    )
                )

        # VIES (USt-ID)
        if VerificationSource.VIES in sources:
            sources_checked.append(VerificationSource.VIES)
            vat_id = getattr(entity, "vat_id", None) or getattr(entity, "tax_id", None)
            if vat_id:
                try:
                    vies_result, vies_findings = await self._check_vies(vat_id)
                    findings.extend(vies_findings)
                except Exception as e:
                    # SECURITY: Nur error_type loggen, nicht str(e) - könnte PII enthalten (CWE-532)
                    logger.warning(
                        "vies_check_error",
                        entity_id=str(entity_id),
                        error_type=type(e).__name__,
                    )
                    findings.append(
                        VerificationFinding(
                            source=VerificationSource.VIES,
                            severity=VerificationSeverity.WARNING,
                            code="VIES_CHECK_ERROR",
                            message="VIES-Prüfung fehlgeschlagen",
                            # SECURITY: Keine Exception-Details in User-Facing Data (CWE-209)
                            details={"error_type": type(e).__name__},
                        )
                    )
            else:
                findings.append(
                    VerificationFinding(
                        source=VerificationSource.VIES,
                        severity=VerificationSeverity.WARNING,
                        code="VIES_NO_VAT_ID",
                        message="Keine USt-IdNr hinterlegt",
                    )
                )

        # Bundesanzeiger
        if VerificationSource.BUNDESANZEIGER in sources:
            sources_checked.append(VerificationSource.BUNDESANZEIGER)
            try:
                bundesanzeiger_result, ba_findings = await self._check_bundesanzeiger(
                    entity_name
                )
                findings.extend(ba_findings)
            except Exception as e:
                # SECURITY: Nur error_type loggen, nicht str(e) - könnte PII enthalten (CWE-532)
                logger.warning(
                    "bundesanzeiger_check_error",
                    entity_id=str(entity_id),
                    error_type=type(e).__name__,
                )
                findings.append(
                    VerificationFinding(
                        source=VerificationSource.BUNDESANZEIGER,
                        severity=VerificationSeverity.WARNING,
                        code="BA_CHECK_ERROR",
                        message="Bundesanzeiger-Prüfung fehlgeschlagen",
                        # SECURITY: Keine Exception-Details in User-Facing Data (CWE-209)
                        details={"error_type": type(e).__name__},
                    )
                )

        # Score berechnen
        verification_score = self._calculate_verification_score(findings)

        # Status bestimmen
        overall_status = self._determine_overall_status(findings, verification_score)

        # Ergebnis erstellen
        verification_result = VerificationResult(
            entity_id=entity_id,
            entity_name=entity_name,
            overall_status=overall_status,
            verification_score=verification_score,
            sources_checked=sources_checked,
            findings=findings,
            handelsregister=handelsregister_result,
            insolvenzregister=insolvenz_result,
            vies=vies_result,
            bundesanzeiger=bundesanzeiger_result,
        )

        # Ergebnis cachen
        await self._cache_result(entity_id, company_id, verification_result)

        # Entity updaten
        await self._update_entity_verification_status(entity, verification_result)

        logger.info(
            "entity_verified",
            entity_id=str(entity_id),
            status=overall_status.value,
            score=verification_score,
            findings_count=len(findings),
        )

        return verification_result

    async def batch_verify(
        self,
        entity_ids: List[UUID],
        company_id: UUID,
        force_refresh: bool = False,
    ) -> Dict[str, VerificationResult]:
        """Verifiziert mehrere Entities.

        Args:
            entity_ids: Liste der Entity-IDs
            company_id: Company-ID
            force_refresh: Cache ignorieren

        Returns:
            Dict mit entity_id -> VerificationResult
        """
        results: Dict[str, VerificationResult] = {}

        for entity_id in entity_ids:
            try:
                result = await self.verify_entity(
                    entity_id=entity_id,
                    company_id=company_id,
                    force_refresh=force_refresh,
                )
                results[str(entity_id)] = result
            except Exception as e:
                # SECURITY: Nur error_type loggen, nicht str(e) - könnte PII enthalten (CWE-532)
                logger.error(
                    "batch_verify_entity_failed",
                    entity_id=str(entity_id),
                    error_type=type(e).__name__,
                )
                # SECURITY: Keine Exception-Details in User-Facing Errors (CWE-209)
                results[str(entity_id)] = self._create_error_result(
                    entity_id, "Verifizierung fehlgeschlagen"
                )

        return results

    async def get_verification_status(
        self,
        entity_id: UUID,
        company_id: UUID,
    ) -> Optional[VerificationResult]:
        """Holt den aktuellen Verifizierungsstatus.

        Args:
            entity_id: Entity-ID
            company_id: Company-ID für Multi-Tenant Isolation

        Returns:
            Cached VerificationResult oder None
        """
        return await self._get_cached_result(entity_id, company_id)

    async def get_entities_needing_verification(
        self,
        company_id: UUID,
        limit: int = 50,
    ) -> List[UUID]:
        """Findet Entities die verifiziert werden sollten.

        Args:
            company_id: Company-ID
            limit: Max Anzahl

        Returns:
            Liste von Entity-IDs
        """
        from app.db.models import BusinessEntity

        # Entities ohne Verifizierung oder mit abgelaufener Verifizierung
        query = (
            select(BusinessEntity.id)
            .where(
                and_(
                    BusinessEntity.company_id == company_id,
                    BusinessEntity.entity_type == "supplier",
                )
            )
            .order_by(BusinessEntity.created_at.desc())
            .limit(limit)
        )

        result = await self.db.execute(query)
        entity_ids = [row[0] for row in result.all()]

        # Filtern nach fehlender/abgelaufener Verifizierung
        needs_verification = []
        for entity_id in entity_ids:
            cached = await self._get_cached_result(entity_id, company_id)
            if not cached or cached.expires_at < datetime.now(timezone.utc):
                needs_verification.append(entity_id)

        return needs_verification

    # =========================================================================
    # Source-spezifische Prüfungen
    # =========================================================================

    async def _check_handelsregister(
        self,
        company_name: str,
        city: Optional[str],
    ) -> Tuple[HandelsregisterResult, List[VerificationFinding]]:
        """Prüft Handelsregister.

        Args:
            company_name: Firmenname
            city: Optional Stadt

        Returns:
            Tuple aus (Result, Findings)
        """
        findings: List[VerificationFinding] = []

        try:
            records = await self.handelsregister.search_company(company_name, city)

            if not records:
                # SECURITY: Keine PII (Firmennamen) in Findings (CWE-532)
                findings.append(
                    VerificationFinding(
                        source=VerificationSource.HANDELSREGISTER,
                        severity=VerificationSeverity.WARNING,
                        code="HR_NOT_FOUND",
                        message="Firma nicht im Handelsregister gefunden",
                    )
                )
                return HandelsregisterResult(found=False), findings

            # Erste Übereinstimmung nehmen
            record = records[0]

            result = HandelsregisterResult(
                found=True,
                company_name=record.name,
                legal_form=record.legal_form,
                register_court=record.register_court,
                register_number=record.register_number,
                registered_address=record.registered_address,
                managing_directors=record.managing_directors,
                status=record.status,
                founded_date=record.founded_date,
                capital=record.capital,
            )

            # Status prüfen
            if record.status != "active":
                findings.append(
                    VerificationFinding(
                        source=VerificationSource.HANDELSREGISTER,
                        severity=VerificationSeverity.CRITICAL,
                        code="HR_NOT_ACTIVE",
                        message=f"Firma ist nicht aktiv (Status: {record.status})",
                        details={"status": record.status},
                    )
                )
            else:
                findings.append(
                    VerificationFinding(
                        source=VerificationSource.HANDELSREGISTER,
                        severity=VerificationSeverity.INFO,
                        code="HR_VERIFIED",
                        message="Firma im Handelsregister gefunden und aktiv",
                        details={
                            "register_number": record.register_number,
                            "register_court": record.register_court,
                        },
                    )
                )

            return result, findings

        except Exception as e:
            # SECURITY: Keine Exception-Details loggen (CWE-209) - könnte PII enthalten
            logger.error(
                "handelsregister_check_failed",
                error_type=type(e).__name__,
            )
            findings.append(
                VerificationFinding(
                    source=VerificationSource.HANDELSREGISTER,
                    severity=VerificationSeverity.WARNING,
                    code="HR_ERROR",
                    # SECURITY: Keine Exception-Details in User-Facing Message (CWE-209)
                    message="Handelsregister-Prüfung fehlgeschlagen",
                )
            )
            return HandelsregisterResult(found=False), findings

    # =========================================================================
    # Insolvenzregister Constants
    # =========================================================================

    INSOLVENZREGISTER_SEARCH_URL = "https://www.insolvenzbekanntmachungen.de/cgi-bin/bl_suche.pl"
    INSOLVENZREGISTER_TIMEOUT_SECONDS = 30
    # Whitelist erlaubter Suchfelder für HTML-Formular
    _INSOLVENZ_ALLOWED_FIELDS = frozenset({"Name", "Ort", "Aktenzeichen", "Gericht", "Reg-Datum-von", "Reg-Datum-bis"})

    async def _check_insolvenzregister(
        self,
        company_name: str,
        city: Optional[str],
    ) -> Tuple[InsolvenzResult, List[VerificationFinding]]:
        """Prüft Insolvenzregister via insolvenzbekanntmachungen.de.

        Nutzt das öffentliche Suchformular des Bundesministeriums der Justiz.
        Fallback auf "unbekannt" bei API-Fehlern (keine false negatives).

        SECURITY:
        - Input-Validierung gegen XSS/Injection (CWE-79)
        - Timeout-Protection gegen DoS
        - HTML-Parsing mit Fehlertoleranz

        Args:
            company_name: Firmenname (wird sanitized)
            city: Optional Stadt (wird sanitized)

        Returns:
            Tuple aus (InsolvenzResult, Findings)
        """
        findings: List[VerificationFinding] = []

        # SECURITY: Sanitize inputs zur Vermeidung von Injection (CWE-20)
        safe_name = self._sanitize_company_name(company_name)
        safe_city = self._sanitize_company_name(city) if city else ""

        if not safe_name:
            findings.append(
                VerificationFinding(
                    source=VerificationSource.INSOLVENZREGISTER,
                    severity=VerificationSeverity.WARNING,
                    code="INSOLVENZ_INVALID_INPUT",
                    message="Firmenname für Insolvenzprüfung ungültig",
                )
            )
            return InsolvenzResult(has_insolvency=False), findings

        try:
            async with httpx.AsyncClient(timeout=self.INSOLVENZREGISTER_TIMEOUT_SECONDS) as client:
                # POST-Request an Suchformular
                response = await client.post(
                    self.INSOLVENZREGISTER_SEARCH_URL,
                    data={
                        "Ession": "",
                        "Name": safe_name,
                        "Ort": safe_city,
                        "Aktenzeichen": "",
                        "Gericht": "",
                        "Reg-Datum-von": "",
                        "Reg-Datum-bis": "",
                        "such": "Suchen",
                    },
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "User-Agent": "Ablage-System/1.0 (Business-Verification)",
                        "Accept": "text/html,application/xhtml+xml",
                        "Accept-Language": "de-DE,de;q=0.9",
                    },
                )

                if response.status_code == 200:
                    # Parse HTML response
                    insolvencies = self._parse_insolvenzregister_html(response.text)

                    if insolvencies:
                        # Insolvenz gefunden
                        first_entry = insolvencies[0]
                        result = InsolvenzResult(
                            has_insolvency=True,
                            insolvency_type=first_entry.get("type", "unbekannt"),
                            court=first_entry.get("court"),
                            case_number=first_entry.get("case_number"),
                            published_date=first_entry.get("date"),
                            status="active",
                        )
                        findings.append(
                            VerificationFinding(
                                source=VerificationSource.INSOLVENZREGISTER,
                                severity=VerificationSeverity.CRITICAL,
                                code="INSOLVENZ_FOUND",
                                message="Insolvenzverfahren gefunden",
                                details={"count": len(insolvencies)},
                            )
                        )
                        logger.warning(
                            "insolvency_found",
                            count=len(insolvencies),
                        )
                        return result, findings

                    # Keine Insolvenz gefunden
                    result = InsolvenzResult(has_insolvency=False)
                    findings.append(
                        VerificationFinding(
                            source=VerificationSource.INSOLVENZREGISTER,
                            severity=VerificationSeverity.INFO,
                            code="INSOLVENZ_CLEAR",
                            message="Keine Insolvenz gefunden",
                        )
                    )
                    return result, findings

                # HTTP-Fehler
                logger.warning(
                    "insolvenzregister_http_error",
                    status_code=response.status_code,
                )

        except httpx.TimeoutException:
            logger.warning("insolvenzregister_timeout")
        except Exception as e:
            # SECURITY: Nur error_type loggen, keine Details (CWE-532)
            logger.warning(
                "insolvenzregister_api_error",
                error_type=type(e).__name__,
            )

        # Fallback: Bei API-Fehler "unbekannt" zurückgeben (keine false negatives)
        findings.append(
            VerificationFinding(
                source=VerificationSource.INSOLVENZREGISTER,
                severity=VerificationSeverity.WARNING,
                code="INSOLVENZ_CHECK_UNAVAILABLE",
                message="Insolvenzregister-Prüfung nicht verfügbar",
            )
        )
        return InsolvenzResult(has_insolvency=False), findings

    def _sanitize_company_name(self, name: str) -> str:
        """Sanitize Firmenname für sichere Suche.

        SECURITY: Entfernt potentiell gefaehrliche Zeichen (CWE-20).

        Args:
            name: Roher Firmenname

        Returns:
            Bereinigter Name (max 100 Zeichen, nur sichere Zeichen)
        """
        if not name:
            return ""

        # Normalisiere Unicode (NFC)
        safe = unicodedata.normalize("NFC", name)
        # Entferne alles ausser: Alphanumerisch, Leerzeichen, deutsche Umlaute, Bindestrich
        # SECURITY: Whitelist-Ansatz gegen Injection (CWE-20)
        safe = re.sub(r"[^\w\s\-äöüÄÖÜß]", "", safe, flags=re.UNICODE)
        # Entferne mehrfache Leerzeichen
        safe = re.sub(r"\s+", " ", safe).strip()
        # Begrenze Länge
        return safe[:100]

    def _parse_insolvenzregister_html(self, html: str) -> List[Dict[str, str]]:
        """Parse insolvenzbekanntmachungen.de HTML Response.

        Extrahiert Insolvenzeinträge aus der Ergebnistabelle.

        Args:
            html: HTML-Response vom Suchformular

        Returns:
            Liste von Dict mit Insolvenz-Details
        """
        results: List[Dict[str, str]] = []

        try:
            # Einfaches Regex-basiertes Parsing (robuster als BS4 bei sich änderndem HTML)
            # Suche nach typischen Mustern in der Ergebnisliste

            # Pattern für Aktenzeichen (z.B. "IN 123/24", "IK 456/23")
            aktenzeichen_pattern = r"(?:IN|IK|IE)\s*\d+/\d+"
            # Pattern für Amtsgericht
            gericht_pattern = r"Amtsgericht\s+[\w\-]+"
            # Pattern für Datum (DD.MM.YYYY)
            datum_pattern = r"\d{2}\.\d{2}\.\d{4}"

            # Finde alle Aktenzeichen
            aktenzeichen_matches = re.findall(aktenzeichen_pattern, html)
            gerichte_matches = re.findall(gericht_pattern, html)
            datum_matches = re.findall(datum_pattern, html)

            # Wenn Aktenzeichen gefunden, haben wir Treffer
            if aktenzeichen_matches:
                for i, az in enumerate(aktenzeichen_matches[:10]):  # Max 10 Einträge
                    entry = {
                        "case_number": az,
                        "court": gerichte_matches[i] if i < len(gerichte_matches) else None,
                        "date": datum_matches[i] if i < len(datum_matches) else None,
                        "type": self._determine_insolvency_type(az),
                        "status": "active",
                    }
                    results.append(entry)

            # Prüfe auch auf "Keine Ergebnisse" Meldung
            if "keine Ergebnisse" in html.lower() or "keine Treffer" in html.lower():
                return []

        except Exception as e:
            # SECURITY: Nur error_type loggen (CWE-532)
            logger.warning(
                "insolvenzregister_parse_error",
                error_type=type(e).__name__,
            )

        return results

    def _determine_insolvency_type(self, case_number: str) -> str:
        """Bestimmt Insolvenztyp aus Aktenzeichen.

        Args:
            case_number: Aktenzeichen (z.B. "IN 123/24")

        Returns:
            Insolvenztyp (opened, rejected, terminated)
        """
        case_upper = case_number.upper()
        if case_upper.startswith("IN"):
            return "opened"  # Regelinsolvenz
        elif case_upper.startswith("IK"):
            return "consumer"  # Verbraucherinsolvenz
        elif case_upper.startswith("IE"):
            return "terminated"  # Eingestellt
        return "unknown"

    # =========================================================================
    # VIES Constants
    # =========================================================================

    VIES_SOAP_ENDPOINT = "https://ec.europa.eu/taxation_customs/vies/services/checkVatService"
    VIES_TIMEOUT_SECONDS = 30
    VIES_MAX_RETRIES = 3
    VIES_RETRY_DELAY_SECONDS = 1.0

    async def _check_vies(
        self,
        vat_id: str,
    ) -> Tuple[ViesResult, List[VerificationFinding]]:
        """Validiert USt-IdNr über VIES SOAP API.

        Nutzt die offizielle EU-Kommission VIES API:
        https://ec.europa.eu/taxation_customs/vies/checkVatService.wsdl

        Args:
            vat_id: USt-IdNr (z.B. DE123456789)

        Returns:
            Tuple aus (Result, Findings)
        """
        findings: List[VerificationFinding] = []

        # VAT-ID bereinigen und Format validieren
        vat_pattern = r"^[A-Z]{2}[0-9A-Z]{2,12}$"
        cleaned_vat = vat_id.upper().replace(" ", "").replace("-", "")

        if not re.match(vat_pattern, cleaned_vat):
            findings.append(
                VerificationFinding(
                    source=VerificationSource.VIES,
                    severity=VerificationSeverity.WARNING,
                    code="VIES_INVALID_FORMAT",
                    # SECURITY: Keine PII (VAT-Nummer) in Message (CWE-532/GDPR)
                    message="USt-IdNr hat ungültiges Format",
                )
            )
            return ViesResult(valid=False, vat_number=vat_id), findings

        country_code = cleaned_vat[:2]
        vat_number = cleaned_vat[2:]

        # SOAP Request erstellen
        soap_envelope = self._build_vies_soap_request(country_code, vat_number)

        # API Request mit Retry-Logik
        for attempt in range(self.VIES_MAX_RETRIES):
            try:
                result, api_findings = await self._call_vies_api(
                    soap_envelope, cleaned_vat, country_code, vat_number
                )
                findings.extend(api_findings)
                return result, findings

            except httpx.TimeoutException:
                logger.warning(
                    "vies_api_timeout",
                    attempt=attempt + 1,
                    max_retries=self.VIES_MAX_RETRIES,
                )
                if attempt == self.VIES_MAX_RETRIES - 1:
                    # Fallback auf Format-Check bei Timeout
                    return self._vies_format_fallback(
                        cleaned_vat, country_code, vat_number, findings,
                        "VIES-Service nicht erreichbar (Timeout)"
                    )

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    # Rate Limit - warten und retry mit EXPONENTIELLEM Backoff
                    logger.warning(
                        "vies_rate_limited",
                        attempt=attempt + 1,
                        status_code=e.response.status_code,
                    )
                    if attempt < self.VIES_MAX_RETRIES - 1:
                        # SECURITY: Exponential Backoff (2^attempt) statt linear
                        await asyncio.sleep(self.VIES_RETRY_DELAY_SECONDS * (2 ** attempt))
                        continue
                elif e.response.status_code in (503, 502, 504):
                    # Service Unavailable - Fallback
                    logger.warning(
                        "vies_service_unavailable",
                        status_code=e.response.status_code,
                    )
                    return self._vies_format_fallback(
                        cleaned_vat, country_code, vat_number, findings,
                        f"VIES-Service nicht verfügbar (HTTP {e.response.status_code})"
                    )
                raise

            except Exception as e:
                # SECURITY: Keine Exception-Details in Logs/User-Responses (CWE-532/209)
                logger.error(
                    "vies_api_error",
                    error_type=type(e).__name__,
                    attempt=attempt + 1,
                )
                if attempt == self.VIES_MAX_RETRIES - 1:
                    # SECURITY: Generische Fehlermeldung für User (keine PII/Exception-Details)
                    return self._vies_format_fallback(
                        cleaned_vat, country_code, vat_number, findings,
                        "VIES-Service vorübergehend nicht verfügbar"
                    )

        # Sollte nicht erreicht werden
        return self._vies_format_fallback(
            cleaned_vat, country_code, vat_number, findings,
            "VIES-Validierung fehlgeschlagen"
        )

    def _build_vies_soap_request(self, country_code: str, vat_number: str) -> str:
        """Erstellt SOAP-Envelope für VIES checkVat Request.

        SECURITY: XML-Escape aller Eingaben zur Vermeidung von XML Injection (CWE-91).

        Args:
            country_code: Ländercode (z.B. DE)
            vat_number: VAT-Nummer ohne Ländercode

        Returns:
            SOAP XML Envelope als String
        """
        # SECURITY: XML-Escape zur Vermeidung von XML Injection (CWE-91)
        # Begrenzen auf erlaubte Länge + escape
        country_safe = xml_escape(country_code[:2].upper())
        vat_safe = xml_escape(vat_number[:20])  # Max 20 Zeichen für EU VAT

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:urn="urn:ec.europa.eu:taxud:vies:services:checkVat:types">
   <soapenv:Header/>
   <soapenv:Body>
      <urn:checkVat>
         <urn:countryCode>{country_safe}</urn:countryCode>
         <urn:vatNumber>{vat_safe}</urn:vatNumber>
      </urn:checkVat>
   </soapenv:Body>
</soapenv:Envelope>"""

    async def _call_vies_api(
        self,
        soap_envelope: str,
        cleaned_vat: str,
        country_code: str,
        vat_number: str,
    ) -> Tuple[ViesResult, List[VerificationFinding]]:
        """Ruft VIES SOAP API auf und parst Response.

        Args:
            soap_envelope: SOAP Request XML
            cleaned_vat: Bereinigte VAT-ID
            country_code: Ländercode
            vat_number: VAT-Nummer ohne Ländercode

        Returns:
            Tuple aus (ViesResult, Findings)
        """
        findings: List[VerificationFinding] = []

        async with httpx.AsyncClient(timeout=self.VIES_TIMEOUT_SECONDS) as client:
            response = await client.post(
                self.VIES_SOAP_ENDPOINT,
                content=soap_envelope,
                headers={
                    "Content-Type": "text/xml; charset=utf-8",
                    "SOAPAction": "",
                },
            )
            response.raise_for_status()

        # XML Response parsen
        # SECURITY: defusedxml zur Vermeidung von XXE-Angriffen (CWE-611)
        try:
            root = safe_xml_fromstring(response.text)

            # Namespaces
            ns = {
                "soap": "http://schemas.xmlsoap.org/soap/envelope/",
                "vies": "urn:ec.europa.eu:taxud:vies:services:checkVat:types",
            }

            # Response-Elemente extrahieren
            body = root.find(".//soap:Body", ns)
            if body is None:
                raise ValueError("SOAP Body nicht gefunden")

            vies_response = body.find(".//vies:checkVatResponse", ns)
            if vies_response is None:
                # Fault prüfen
                fault = body.find(".//soap:Fault", ns)
                if fault is not None:
                    fault_string = fault.findtext("faultstring", "Unbekannter Fehler")
                    raise ValueError(f"VIES SOAP Fault: {fault_string}")
                raise ValueError("checkVatResponse nicht gefunden")

            # Felder extrahieren
            valid_elem = vies_response.find("vies:valid", ns)
            is_valid = valid_elem is not None and valid_elem.text == "true"

            name_elem = vies_response.find("vies:name", ns)
            company_name = name_elem.text if name_elem is not None else None

            address_elem = vies_response.find("vies:address", ns)
            company_address = address_elem.text if address_elem is not None else None

            request_date_elem = vies_response.find("vies:requestDate", ns)
            request_date = request_date_elem.text if request_date_elem is not None else None

            # Result erstellen
            result = ViesResult(
                valid=is_valid,
                vat_number=cleaned_vat,
                country_code=country_code,
                company_name=company_name,
                company_address=company_address,
                request_date=request_date or datetime.now(timezone.utc).isoformat(),
                consultation_number=None,  # Nicht in Standard-Response
            )

            if is_valid:
                findings.append(
                    VerificationFinding(
                        source=VerificationSource.VIES,
                        severity=VerificationSeverity.INFO,
                        code="VIES_VALID",
                        message="USt-IdNr ist gültig (VIES verifiziert)",
                        details={
                            # SECURITY: Keine PII in details (company_name, address entfernt)
                            "verified_via": "EU-VIES-API",
                            "country_code": country_code,
                        },
                    )
                )
                # SECURITY: Keine VAT-Nummern oder Firmennamen in Logs (PII/GDPR)
                logger.info(
                    "vies_validation_success",
                    country_code=country_code[:2],
                    valid=True,
                )
            else:
                findings.append(
                    VerificationFinding(
                        source=VerificationSource.VIES,
                        severity=VerificationSeverity.WARNING,
                        code="VIES_INVALID",
                        message="USt-IdNr ist ungültig (VIES abgelehnt)",
                        details={
                            # SECURITY: Keine VAT-Nummer in details
                            "verified_via": "EU-VIES-API",
                            "country_code": country_code,
                        },
                    )
                )
                # SECURITY: Keine VAT-Nummern in Logs (PII/GDPR)
                logger.info(
                    "vies_validation_failed",
                    country_code=country_code[:2],
                    valid=False,
                )

            return result, findings

        except ET.ParseError as e:
            # SECURITY: Keine Details aus Exception loggen (könnte PII enthalten)
            logger.warning(
                "vies_xml_parse_error",
                error_type=type(e).__name__,
            )
            raise ValueError("VIES XML-Parsing fehlgeschlagen")
        except Exception as e:
            # SECURITY: defusedxml kann verschiedene Exceptions werfen (CWE-755)
            # z.B. DTDForbidden, EntitiesForbidden, ExternalReferenceForbidden
            error_type = type(e).__name__
            if "Forbidden" in error_type or "defused" in str(type(e).__module__):
                logger.warning(
                    "vies_xml_security_violation",
                    error_type=error_type,
                )
                raise ValueError("VIES XML-Sicherheitsverletzung erkannt")
            raise

    def _vies_format_fallback(
        self,
        cleaned_vat: str,
        country_code: str,
        vat_number: str,
        findings: List[VerificationFinding],
        warning_message: str,
    ) -> Tuple[ViesResult, List[VerificationFinding]]:
        """Fallback auf Format-Validierung wenn VIES nicht erreichbar.

        Args:
            cleaned_vat: Bereinigte VAT-ID
            country_code: Ländercode
            vat_number: VAT-Nummer ohne Ländercode
            findings: Bestehende Findings
            warning_message: Warnmeldung

        Returns:
            Tuple aus (ViesResult, Findings)
        """
        # Format-spezifische Validierung je nach Land
        format_valid = self._validate_vat_format(country_code, vat_number)

        result = ViesResult(
            valid=format_valid,
            vat_number=cleaned_vat,
            country_code=country_code,
            request_date=datetime.now(timezone.utc).isoformat(),
        )

        # SECURITY: Keine PII (VAT-Nummern) in Findings.details (CWE-532)
        findings.append(
            VerificationFinding(
                source=VerificationSource.VIES,
                severity=VerificationSeverity.WARNING,
                code="VIES_FALLBACK",
                message=f"{warning_message}. Nur Format geprüft.",
                details={
                    "country_code": country_code,
                    "format_valid": format_valid,
                    "verified_via": "format-check-only",
                },
            )
        )

        logger.warning(
            "vies_fallback_to_format_check",
            reason=warning_message,
            format_valid=format_valid,
        )

        return result, findings

    def _validate_vat_format(self, country_code: str, vat_number: str) -> bool:
        """Validiert VAT-Format je nach Land.

        Args:
            country_code: Ländercode
            vat_number: VAT-Nummer ohne Ländercode

        Returns:
            True wenn Format korrekt
        """
        # Länderspezifische Formate (wichtigste EU-Länder)
        formats = {
            "DE": r"^\d{9}$",  # Deutschland: 9 Ziffern
            "AT": r"^U\d{8}$",  # Oesterreich: U + 8 Ziffern
            "FR": r"^[0-9A-Z]{2}\d{9}$",  # Frankreich: 2 Zeichen + 9 Ziffern
            "IT": r"^\d{11}$",  # Italien: 11 Ziffern
            "ES": r"^[A-Z0-9]\d{7}[A-Z0-9]$",  # Spanien: Buchst/Ziffer + 7 Ziffern + Buchst/Ziffer
            "NL": r"^\d{9}B\d{2}$",  # Niederlande: 9 Ziffern + B + 2 Ziffern
            "BE": r"^0\d{9}$",  # Belgien: 0 + 9 Ziffern
            "PL": r"^\d{10}$",  # Polen: 10 Ziffern
            "CZ": r"^\d{8,10}$",  # Tschechien: 8-10 Ziffern
            "GB": r"^\d{9}$|^\d{12}$|^GD\d{3}$|^HA\d{3}$",  # UK (historisch)
        }

        pattern = formats.get(country_code)
        if pattern:
            return bool(re.match(pattern, vat_number))

        # Fallback: Mindestens 2 Zeichen
        return len(vat_number) >= 2

    async def _check_bundesanzeiger(
        self,
        company_name: str,
    ) -> Tuple[BundesanzeigerResult, List[VerificationFinding]]:
        """Prüft Bundesanzeiger.

        Args:
            company_name: Firmenname

        Returns:
            Tuple aus (Result, Findings)
        """
        findings: List[VerificationFinding] = []

        try:
            # Bundesanzeiger-Service nutzen
            publications = await self.bundesanzeiger.search_publications(company_name)

            if not publications:
                findings.append(
                    VerificationFinding(
                        source=VerificationSource.BUNDESANZEIGER,
                        severity=VerificationSeverity.INFO,
                        code="BA_NO_PUBLICATIONS",
                        message="Keine Veröffentlichungen im Bundesanzeiger gefunden",
                    )
                )
                return BundesanzeigerResult(found=False), findings

            # Konvertiere zu typisierter Struktur
            typed_announcements = [
                BundesanzeigerAnnouncement(
                    date=pub.get("date"),
                    type=pub.get("type"),
                    description=pub.get("description"),
                )
                for pub in publications[:5]  # Letzte 5
            ]

            result = BundesanzeigerResult(
                found=True,
                publications_count=len(publications),
                announcements=typed_announcements,
            )

            # Jahresabschluss suchen
            for pub in publications:
                if "jahresabschluss" in pub.get("type", "").lower():
                    result.latest_annual_report = pub.get("date")
                    break

            findings.append(
                VerificationFinding(
                    source=VerificationSource.BUNDESANZEIGER,
                    severity=VerificationSeverity.INFO,
                    code="BA_FOUND",
                    message=f"{len(publications)} Veröffentlichung(en) gefunden",
                    details={"count": len(publications)},
                )
            )

            return result, findings

        except Exception as e:
            # SECURITY: Keine Exception-Details loggen (CWE-209) - könnte PII enthalten
            logger.error(
                "bundesanzeiger_check_failed",
                error_type=type(e).__name__,
            )
            findings.append(
                VerificationFinding(
                    source=VerificationSource.BUNDESANZEIGER,
                    severity=VerificationSeverity.WARNING,
                    code="BA_ERROR",
                    # SECURITY: Keine Exception-Details in User-Facing Message (CWE-209)
                    message="Bundesanzeiger-Prüfung fehlgeschlagen",
                )
            )
            return BundesanzeigerResult(found=False), findings

    # =========================================================================
    # Score & Status Berechnung
    # =========================================================================

    def _calculate_verification_score(
        self,
        findings: List[VerificationFinding],
    ) -> int:
        """Berechnet Verifizierungs-Score.

        Args:
            findings: Liste der Befunde

        Returns:
            Score 0-100
        """
        score = 100

        for finding in findings:
            if finding.severity == VerificationSeverity.CRITICAL:
                score -= 40
            elif finding.severity == VerificationSeverity.WARNING:
                score -= 15
            # INFO erhöht nicht und verringert nicht

        return max(0, min(100, score))

    def _determine_overall_status(
        self,
        findings: List[VerificationFinding],
        score: int,
    ) -> VerificationStatus:
        """Bestimmt Gesamtstatus.

        Args:
            findings: Liste der Befunde
            score: Verifizierungs-Score

        Returns:
            VerificationStatus
        """
        has_critical = any(
            f.severity == VerificationSeverity.CRITICAL for f in findings
        )
        has_warning = any(
            f.severity == VerificationSeverity.WARNING for f in findings
        )

        if has_critical:
            return VerificationStatus.CRITICAL
        elif has_warning and score < 70:
            return VerificationStatus.WARNING
        elif score >= 80:
            return VerificationStatus.VERIFIED
        elif score >= 50:
            return VerificationStatus.WARNING
        else:
            return VerificationStatus.CRITICAL

    # =========================================================================
    # Caching
    # =========================================================================

    async def _get_cached_result(
        self,
        entity_id: UUID,
        company_id: UUID,
    ) -> Optional[VerificationResult]:
        """Holt gecachtes Ergebnis.

        SECURITY: Multi-Tenant Cache Isolation (CWE-200)
        Der Cache-Key beinhaltet company_id um Cross-Tenant Data Leaks zu verhindern.

        Args:
            entity_id: Entity-ID
            company_id: Company-ID für Multi-Tenant Isolation

        Returns:
            Cached Result oder None
        """
        from app.db.models import AppConfig

        query = select(AppConfig).where(AppConfig.key == VERIFICATION_CACHE_KEY)
        result = await self.db.execute(query)
        config = result.scalar_one_or_none()

        if not config or not config.value:
            return None

        cache = config.value
        # SECURITY: Multi-Tenant Cache Isolation - Cache-Key mit company_id (CWE-200)
        entity_key = f"{company_id}:{entity_id}"

        if entity_key not in cache:
            return None

        cached_data = cache[entity_key]

        # Ablauf prüfen
        expires_at = datetime.fromisoformat(cached_data.get("expires_at", "2000-01-01"))
        if expires_at < datetime.now(timezone.utc):
            return None

        # Result rekonstruieren
        return self._deserialize_result(cached_data)

    async def _cache_result(
        self,
        entity_id: UUID,
        company_id: UUID,
        result: VerificationResult,
    ) -> None:
        """Cached Verifizierungsergebnis.

        SECURITY: Multi-Tenant Cache Isolation (CWE-200)
        Der Cache-Key beinhaltet company_id um Cross-Tenant Data Leaks zu verhindern.

        Args:
            entity_id: Entity-ID
            company_id: Company-ID für Multi-Tenant Isolation
            result: VerificationResult

        Raises:
            ValueError: Bei entity_id Mismatch (Cache-Poisoning Prevention)
        """
        # SECURITY: Cache-Poisoning Prevention (CWE-345)
        # Verhindert dass Ergebnisse unter falscher entity_id gecacht werden
        if str(entity_id) != str(result.entity_id):
            logger.error(
                "cache_poisoning_attempt_detected",
                cache_key_entity_id=str(entity_id)[:8],  # Nur Prefix loggen
                result_entity_id=str(result.entity_id)[:8],
            )
            raise ValueError("Entity ID mismatch in cache operation - possible cache poisoning attempt")

        from app.db.models import AppConfig

        query = select(AppConfig).where(AppConfig.key == VERIFICATION_CACHE_KEY)
        db_result = await self.db.execute(query)
        config = db_result.scalar_one_or_none()

        cache = config.value if config else {}
        # SECURITY: Multi-Tenant Cache Isolation - Cache-Key mit company_id (CWE-200)
        cache_key = f"{company_id}:{entity_id}"
        cache[cache_key] = self._serialize_result(result)

        if config:
            config.value = cache
        else:
            config = AppConfig(key=VERIFICATION_CACHE_KEY, value=cache)
            self.db.add(config)

        await self.db.commit()

    def _serialize_result(self, result: VerificationResult) -> Dict[str, Any]:
        """Serialisiert Result für Cache.

        Args:
            result: VerificationResult

        Returns:
            Dict für JSON-Speicherung
        """
        return {
            "entity_id": str(result.entity_id),
            "entity_name": result.entity_name,
            "overall_status": result.overall_status.value,
            "verification_score": result.verification_score,
            "sources_checked": [s.value for s in result.sources_checked],
            "findings": [
                {
                    "source": f.source.value,
                    "severity": f.severity.value,
                    "code": f.code,
                    "message": f.message,
                    "details": f.details,
                    "timestamp": f.timestamp.isoformat(),
                }
                for f in result.findings
            ],
            "verified_at": result.verified_at.isoformat(),
            "expires_at": result.expires_at.isoformat(),
        }

    def _deserialize_result(self, data: Dict[str, Any]) -> VerificationResult:
        """Deserialisiert Result aus Cache.

        Args:
            data: Cached Data

        Returns:
            VerificationResult
        """
        return VerificationResult(
            entity_id=UUID(data["entity_id"]),
            entity_name=data["entity_name"],
            overall_status=VerificationStatus(data["overall_status"]),
            verification_score=data["verification_score"],
            sources_checked=[VerificationSource(s) for s in data["sources_checked"]],
            findings=[
                VerificationFinding(
                    source=VerificationSource(f["source"]),
                    severity=VerificationSeverity(f["severity"]),
                    code=f["code"],
                    message=f["message"],
                    details=f.get("details", {}),
                    timestamp=datetime.fromisoformat(f["timestamp"]),
                )
                for f in data.get("findings", [])
            ],
            verified_at=datetime.fromisoformat(data["verified_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
            cached=True,
        )

    async def _update_entity_verification_status(
        self,
        entity: "BusinessEntity",
        result: VerificationResult,
    ) -> None:
        """Aktualisiert Entity mit Verifizierungsstatus.

        Args:
            entity: BusinessEntity
            result: VerificationResult
        """
        # Metadata aktualisieren
        if not hasattr(entity, "metadata") or entity.metadata is None:
            entity.metadata = {}

        entity.metadata["verification"] = {
            "status": result.overall_status.value,
            "score": result.verification_score,
            "verified_at": result.verified_at.isoformat(),
            "expires_at": result.expires_at.isoformat(),
        }

        await self.db.commit()

    def _create_error_result(
        self,
        entity_id: UUID,
        error_message: str,
    ) -> VerificationResult:
        """Erstellt Fehler-Result.

        Args:
            entity_id: Entity-ID
            error_message: Fehlermeldung

        Returns:
            VerificationResult mit Error-Status
        """
        return VerificationResult(
            entity_id=entity_id,
            entity_name="Unbekannt",
            overall_status=VerificationStatus.ERROR,
            verification_score=0,
            sources_checked=[],
            findings=[
                VerificationFinding(
                    source=VerificationSource.HANDELSREGISTER,
                    severity=VerificationSeverity.CRITICAL,
                    code="VERIFICATION_ERROR",
                    message=error_message,
                )
            ],
        )
