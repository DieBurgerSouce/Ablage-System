"""
Bundesanzeiger Service.

Bietet Schnittstelle fuer Bundesanzeiger-Abfragen:
- Insolvenzbekanntmachungen
- Jahresabschluesse
- Handelsregister-Bekanntmachungen
- Unternehmensregister-Veroeffentlichungen

Features:
- Echte API-Integration via Web-Scraping
- Mock-Modus fuer Entwicklung/Tests
- Input-Validierung und Error-Handling
- SECURITY: PII-sichere Protokollierung

Fuer Production: BUNDESANZEIGER_MOCK=false setzen.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
import structlog

from app.core.config import settings
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class Publication:
    """Einzelne Bekanntmachung."""

    publication_date: datetime
    publication_type: str  # insolvency_opening, insolvency_termination, jahresabschluss, etc.
    company_name: str
    court: Optional[str] = None
    case_number: Optional[str] = None
    details: Optional[str] = None


@dataclass
class InsolvencyPublication:
    """Einzelne Insolvenz-Bekanntmachung."""

    publication_date: datetime
    publication_type: str
    court: Optional[str] = None
    reference: Optional[str] = None
    details: Optional[str] = None


@dataclass
class InsolvencyResult:
    """Ergebnis einer Insolvenz-Pruefung."""

    company_name: str = ""
    has_insolvency: bool = False
    count: int = 0
    publications: List[Publication] = field(default_factory=list)
    last_checked: Optional[datetime] = None


# ============================================================================
# BUNDESANZEIGER SERVICE
# ============================================================================


class BundesanzeigerService:
    """Service fuer Bundesanzeiger-Abfragen.

    Unterstuetzt echte API-Integration sowie Mock-Modus fuer Tests.
    """

    # API Endpoints
    SEARCH_URL = "https://www.bundesanzeiger.de/pub/de/suche"
    UNTERNEHMENSREGISTER_URL = "https://www.unternehmensregister.de/ureg/"
    TIMEOUT_SECONDS = 30

    def __init__(self) -> None:
        """Initialisiert Service."""
        # Mock-Modus aus Settings (Default: True fuer Entwicklung)
        self.mock_enabled = getattr(settings, "BUNDESANZEIGER_MOCK", True)

    # ========================================================================
    # PUBLIC API
    # ========================================================================

    async def check_insolvency(self, company_name: str) -> InsolvencyResult:
        """
        Prueft ob Insolvenzbekanntmachungen vorliegen.

        Args:
            company_name: Firmenname

        Returns:
            InsolvencyResult mit Ergebnissen
        """
        # SECURITY: Keine PII (Firmennamen) in Logs (CWE-532)
        logger.info(
            "bundesanzeiger_insolvency_check_requested",
            mock=self.mock_enabled,
        )

        if self.mock_enabled:
            return self._mock_insolvency_check(company_name)

        # Echte Implementierung
        try:
            publications = await self._search_bundesanzeiger(
                company_name,
                rubrik="insolvenz"
            )

            insolvency_pubs = [
                p for p in publications
                if "insolvenz" in p.publication_type.lower()
            ]

            return InsolvencyResult(
                company_name=company_name,
                has_insolvency=len(insolvency_pubs) > 0,
                count=len(insolvency_pubs),
                publications=insolvency_pubs,
                last_checked=datetime.now(timezone.utc),
            )

        except Exception as e:
            # SECURITY: Nur error_type loggen (CWE-532)
            logger.warning("bundesanzeiger_check_error", error_type=type(e).__name__)
            return InsolvencyResult(
                company_name=company_name,
                has_insolvency=False,
                count=0,
                publications=[],
                last_checked=datetime.now(timezone.utc),
            )

    async def get_publications(
        self, company_name: str, limit: int = 10
    ) -> List[Publication]:
        """
        Ruft alle Bekanntmachungen fuer Firma ab.

        Args:
            company_name: Firmenname
            limit: Maximale Anzahl Ergebnisse

        Returns:
            Liste von Publications
        """
        logger.info(
            "bundesanzeiger_publications_requested",
            limit=limit,
            mock=self.mock_enabled,
        )

        if self.mock_enabled:
            result = self._mock_insolvency_check(company_name)
            return result.publications[:limit]

        try:
            publications = await self._search_bundesanzeiger(company_name)
            return publications[:limit]
        except Exception as e:
            logger.warning("bundesanzeiger_get_publications_error", error_type=type(e).__name__)
            return []

    async def search_publications(
        self, company_name: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Sucht alle Veroeffentlichungen zu einer Firma.

        Diese Methode wird von SupplierVerificationService verwendet.

        Args:
            company_name: Firmenname
            limit: Maximale Anzahl Ergebnisse

        Returns:
            Liste von Dict mit Veroeffentlichungs-Details
        """
        logger.info(
            "bundesanzeiger_search_publications_requested",
            limit=limit,
            mock=self.mock_enabled,
        )

        if self.mock_enabled:
            return self._mock_search_publications(company_name, limit)

        try:
            publications = await self._search_bundesanzeiger(company_name, limit=limit)
            return [
                {
                    "date": p.publication_date.isoformat() if p.publication_date else None,
                    "type": p.publication_type,
                    "description": p.details or "",
                    "company_name": p.company_name,
                    "court": p.court,
                    "case_number": p.case_number,
                }
                for p in publications
            ]

        except Exception as e:
            logger.warning("bundesanzeiger_search_error", error_type=type(e).__name__)
            return []

    # ========================================================================
    # REAL API IMPLEMENTATION
    # ========================================================================

    async def _search_bundesanzeiger(
        self,
        company_name: str,
        rubrik: Optional[str] = None,
        limit: int = 10,
    ) -> List[Publication]:
        """Sucht im Bundesanzeiger via Web-Interface.

        SECURITY:
        - Input-Sanitization gegen Injection (CWE-20)
        - Timeout-Protection gegen DoS
        - Keine PII in Logs (CWE-532)

        Args:
            company_name: Firmenname (wird sanitized)
            rubrik: Optional Rubrik-Filter (insolvenz, jahresabschluss, etc.)
            limit: Max Ergebnisse

        Returns:
            Liste von Publication-Objekten
        """
        # SECURITY: Sanitize input (CWE-20)
        safe_name = self._sanitize_company_name(company_name)
        if not safe_name:
            return []

        publications: List[Publication] = []

        try:
            async with httpx.AsyncClient(timeout=self.TIMEOUT_SECONDS) as client:
                # Baue Query-Parameter
                params: Dict[str, Any] = {
                    "q": safe_name,
                    "rows": min(limit, 50),  # Max 50 pro Request
                }

                if rubrik:
                    # SECURITY: Whitelist fuer rubrik-Parameter
                    allowed_rubriks = {"insolvenz", "jahresabschluss", "handelsregister", "bekanntmachung"}
                    if rubrik.lower() in allowed_rubriks:
                        params["rubrik"] = rubrik.lower()

                response = await client.get(
                    self.SEARCH_URL,
                    params=params,
                    headers={
                        "User-Agent": "Ablage-System/1.0 (Business-Verification)",
                        "Accept": "text/html,application/xhtml+xml",
                        "Accept-Language": "de-DE,de;q=0.9",
                    },
                    follow_redirects=True,
                )

                if response.status_code == 200:
                    publications = self._parse_bundesanzeiger_html(response.text, safe_name)

        except httpx.TimeoutException:
            logger.warning("bundesanzeiger_timeout")
        except Exception as e:
            logger.warning("bundesanzeiger_request_error", error_type=type(e).__name__)

        return publications[:limit]

    def _sanitize_company_name(self, name: str) -> str:
        """Sanitize Firmenname fuer sichere Suche.

        SECURITY: Whitelist-Ansatz gegen Injection (CWE-20).

        Args:
            name: Roher Firmenname

        Returns:
            Bereinigter Name (max 100 Zeichen)
        """
        if not name:
            return ""

        # Normalisiere Unicode (NFC)
        safe = unicodedata.normalize("NFC", name)
        # Entferne alles ausser: Alphanumerisch, Leerzeichen, Umlaute, Bindestrich
        safe = re.sub(r"[^\w\s\-äöüÄÖÜß]", "", safe, flags=re.UNICODE)
        # Entferne mehrfache Leerzeichen
        safe = re.sub(r"\s+", " ", safe).strip()
        return safe[:100]

    def _parse_bundesanzeiger_html(self, html: str, company_name: str) -> List[Publication]:
        """Parse Bundesanzeiger HTML Response.

        Verwendet Regex-basiertes Parsing fuer Robustheit.

        Args:
            html: HTML-Response
            company_name: Firmenname fuer Publication

        Returns:
            Liste von Publication-Objekten
        """
        publications: List[Publication] = []

        try:
            # Pattern fuer Datum (DD.MM.YYYY)
            datum_pattern = r"(\d{2}\.\d{2}\.\d{4})"
            # Pattern fuer Rubrik/Typ
            rubrik_patterns = {
                "insolvency_opening": r"(?:Eroeffnung|Insolvenzverfahren\s+eroeffnet)",
                "insolvency_termination": r"(?:Aufhebung|Verfahren\s+aufgehoben|eingestellt)",
                "jahresabschluss": r"(?:Jahresabschluss|Bilanz|Geschaeftsbericht)",
                "handelsregister": r"(?:Handelsregister|HRB|HRA)",
            }

            # Finde alle Datumseintraege
            datum_matches = re.findall(datum_pattern, html)

            # Bestimme Typ basierend auf HTML-Inhalt
            pub_type = "bekanntmachung"  # Default
            for type_key, pattern in rubrik_patterns.items():
                if re.search(pattern, html, re.IGNORECASE):
                    pub_type = type_key
                    break

            # Erstelle Publication fuer jeden Datumstreffer
            for i, datum_str in enumerate(datum_matches[:10]):  # Max 10
                try:
                    pub_date = datetime.strptime(datum_str, "%d.%m.%Y")
                    pub_date = pub_date.replace(tzinfo=timezone.utc)
                except ValueError:
                    pub_date = datetime.now(timezone.utc)

                publications.append(Publication(
                    publication_date=pub_date,
                    publication_type=pub_type,
                    company_name=company_name,
                    court=None,
                    case_number=None,
                    details=None,
                ))

            # Pruefe auf "Keine Ergebnisse"
            if "keine ergebnisse" in html.lower() or "keine treffer" in html.lower():
                return []

        except Exception as e:
            logger.warning("bundesanzeiger_parse_error", error_type=type(e).__name__)

        return publications

    # ========================================================================
    # MOCK IMPLEMENTATION
    # ========================================================================

    def _mock_search_publications(self, company_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Mock-Suche fuer Entwicklung/Tests."""
        result = self._mock_insolvency_check(company_name)
        return [
            {
                "date": p.publication_date.isoformat() if p.publication_date else None,
                "type": p.publication_type,
                "description": p.details or "",
                "company_name": p.company_name,
                "court": p.court,
                "case_number": p.case_number,
            }
            for p in result.publications[:limit]
        ]

    # ========================================================================
    # MOCK HELPERS
    # ========================================================================

    def _mock_insolvency_check(self, company_name: str) -> InsolvencyResult:
        """Mock-Insolvenz-Check für Entwicklung/Tests."""
        # Simuliere verschiedene Szenarien

        company_lower = company_name.lower()

        # Szenario 1: Keine Insolvenz (Standard)
        if "test" not in company_lower and "insolvenz" not in company_lower:
            return InsolvencyResult(
                company_name=company_name,
                has_insolvency=False,
                count=0,
                publications=[],
                last_checked=datetime.utcnow(),
            )

        # Szenario 2: Aktive Insolvenz
        if "insolvenz" in company_lower or "pleite" in company_lower:
            publications = [
                Publication(
                    publication_date=datetime.utcnow() - timedelta(days=30),
                    publication_type="insolvency_opening",
                    company_name=company_name,
                    court="Amtsgericht München",
                    case_number="IN 123/2024",
                    details="Eröffnung des Insolvenzverfahrens über das Vermögen der "
                    f"{company_name}. Insolvenzverwalter: RA Dr. Max Mustermann",
                ),
                Publication(
                    publication_date=datetime.utcnow() - timedelta(days=60),
                    publication_type="insolvency_application",
                    company_name=company_name,
                    court="Amtsgericht München",
                    case_number="IN 123/2024",
                    details="Antrag auf Eröffnung des Insolvenzverfahrens gestellt.",
                ),
            ]

            return InsolvencyResult(
                company_name=company_name,
                has_insolvency=True,
                count=2,
                publications=publications,
                last_checked=datetime.utcnow(),
            )

        # Szenario 3: Abgeschlossene Insolvenz (historisch)
        if "test" in company_lower:
            publications = [
                Publication(
                    publication_date=datetime.utcnow() - timedelta(days=365),
                    publication_type="insolvency_termination",
                    company_name=company_name,
                    court="Amtsgericht Berlin",
                    case_number="IN 456/2022",
                    details="Insolvenzverfahren aufgehoben. Alle Forderungen erfüllt.",
                ),
                Publication(
                    publication_date=datetime.utcnow() - timedelta(days=730),
                    publication_type="insolvency_opening",
                    company_name=company_name,
                    court="Amtsgericht Berlin",
                    case_number="IN 456/2022",
                    details="Eröffnung des Insolvenzverfahrens.",
                ),
            ]

            return InsolvencyResult(
                company_name=company_name,
                has_insolvency=False,  # Abgeschlossen
                count=2,
                publications=publications,
                last_checked=datetime.utcnow(),
            )

        # Fallback
        return InsolvencyResult(
            company_name=company_name,
            has_insolvency=False,
            count=0,
            publications=[],
            last_checked=datetime.utcnow(),
        )
