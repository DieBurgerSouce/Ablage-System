# -*- coding: utf-8 -*-
"""Handelsregister Service.

Bietet Schnittstelle für Handelsregister-Abfragen über das offizielle
Portal handelsregister.de.

IMPLEMENTIERUNG:
- Web-Scraping des offiziellen Portals
- Rate Limiting: Max 60 Requests/Stunde (Portal-Limit)
- Redis Caching: 24h TTL
- Robustes Error Handling

RECHTLICHE HINWEISE:
- Nur für Einzelabfragen bei Lieferanten-Verifizierung
- KEINE Massenabfragen
- Rate Limit STRIKT einhalten
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import time
import unicodedata
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, List, Optional, Tuple
from urllib.parse import quote, urlencode

import httpx
import structlog
from lxml import html
from lxml.html import HTMLParser

from app.core.config import settings
from app.core.safe_errors import safe_error_log

# SECURITY: HTMLParser mit XXE-Praevention (CWE-611)
# - no_network=True: Verhindert das Laden externer DTDs über Netzwerk
# - resolve_entities=False: KRITISCH! Verhindert Entity-Expansion-Attacks
#   (Billion Laughs, Quadratic Blowup) auch bei lokalen Entities
# NOTE: resolve_entities was removed in lxml 5.x, use try/except for compatibility
try:
    _SAFE_HTML_PARSER = HTMLParser(
        recover=True,
        no_network=True,
        resolve_entities=False,
    )
except TypeError:
    # lxml 5.x removed resolve_entities parameter
    _SAFE_HTML_PARSER = HTMLParser(
        recover=True,
        no_network=True,
    )

logger = structlog.get_logger(__name__)


# =============================================================================
# SECURITY: Input Validation Patterns (CWE-20, CWE-80, CWE-918)
# =============================================================================

# Erlaubte Zeichen für Firmennamen (deutsch-freundlich)
NAME_PATTERN = re.compile(r"^[\w\s\-äöüßÄÖÜ\.&,\'\"()]+$", re.UNICODE)
# Max Länge für Firmennamen
MAX_NAME_LENGTH = 255
# Max Länge für Ortsangaben
MAX_LOCATION_LENGTH = 100
# Registernummer-Pattern: HRB/HRA/GnR/PR/VR + Leerzeichen + Nummer
REGISTER_PATTERN = re.compile(r"^(HRB|HRA|GnR|PR|VR)\s+(\d{1,7})$")


def _validate_search_input(name: str, location: Optional[str]) -> None:
    """Validiert Sucheingaben gegen Injection-Attacks.

    SECURITY: Verhindert HTML/XSS Injection (CWE-80), SSRF (CWE-918),
    Null-Byte Injection (CWE-158), und Unicode-Homoglyph-Bypasses (CWE-176).

    Args:
        name: Firmenname
        location: Optional Ort

    Raises:
        ValueError: Bei ungültigen Eingaben
    """
    if not name or not isinstance(name, str):
        raise ValueError("Firmenname ist erforderlich")

    # SECURITY: Unicode-Normalisierung (CWE-176) - Homoglyph-Angriffe verhindern
    name = unicodedata.normalize("NFKC", name.strip())

    # SECURITY: Null-Byte Injection verhindern (CWE-158)
    if "\x00" in name:
        raise ValueError("Firmenname enthält ungültige Zeichen (Null-Byte)")

    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(f"Firmenname zu lang (max {MAX_NAME_LENGTH} Zeichen)")

    if len(name) < 2:
        raise ValueError("Firmenname zu kurz (min 2 Zeichen)")

    if not NAME_PATTERN.match(name):
        raise ValueError("Firmenname enthält ungültige Zeichen")

    if location:
        # SECURITY: Unicode-Normalisierung für Location
        location = unicodedata.normalize("NFKC", location.strip())

        # SECURITY: Null-Byte Injection verhindern (CWE-158)
        if "\x00" in location:
            raise ValueError("Ortsangabe enthält ungültige Zeichen (Null-Byte)")

        if len(location) > MAX_LOCATION_LENGTH:
            raise ValueError(f"Ortsangabe zu lang (max {MAX_LOCATION_LENGTH} Zeichen)")
        if not NAME_PATTERN.match(location):
            raise ValueError("Ortsangabe enthält ungültige Zeichen")


def _validate_register_id(register_id: str) -> Tuple[str, str]:
    """Validiert und parst Registernummer.

    SECURITY: Verhindert Parameter-Injection (CWE-918).

    Args:
        register_id: Registernummer (z.B. "HRB 123456")

    Returns:
        Tuple (register_type, register_number)

    Raises:
        ValueError: Bei ungültiger Registernummer
    """
    if not register_id or not isinstance(register_id, str):
        raise ValueError("Registernummer ist erforderlich")

    register_id = register_id.strip()
    match = REGISTER_PATTERN.match(register_id)

    if not match:
        raise ValueError(
            "Ungültiges Registernummer-Format. "
            "Erwartet: 'HRB 123456' oder 'HRA 12345'"
        )

    return match.group(1), match.group(2)


# ============================================================================
# CONSTANTS
# ============================================================================

HANDELSREGISTER_BASE_URL = "https://www.handelsregister.de"
HANDELSREGISTER_SEARCH_URL = f"{HANDELSREGISTER_BASE_URL}/rp_web/normalesuche.xhtml"
HANDELSREGISTER_TIMEOUT_SECONDS = 30
HANDELSREGISTER_RATE_LIMIT_PER_HOUR = 60
HANDELSREGISTER_CACHE_TTL_HOURS = 24

# W1-011: Verfuegbarkeits-Status der Datenquelle (nutzersichtbar, deutsch)
SOURCE_STATUS_LIVE = "live"
SOURCE_STATUS_MOCK = "mock"
SOURCE_STATUS_MOCK_FALLBACK = "mock_fallback"

# W1-011: Einmaliges WARN-Log pro Prozess, wenn der Mock-Modus aktiv ist.
_MOCK_MODE_WARNED = False


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class CompanyRecord:
    """Handelsregister-Eintrag einer Firma."""

    name: str
    legal_form: Optional[str] = None  # GmbH, AG, UG, etc.
    register_court: Optional[str] = None  # z.B. "Amtsgericht München"
    register_number: Optional[str] = None  # HRB 123456
    registered_address: Optional[str] = None
    founded_date: Optional[str] = None  # ISO format
    capital: Optional[str] = None  # z.B. "25.000 EUR"
    managing_directors: Optional[List[str]] = None
    status: str = "active"  # active, dissolved, in_liquidation
    # W1-011 (additiv): Herkunft des Eintrags - "live", "mock" (Mock-Modus
    # explizit aktiviert) oder "mock_fallback" (Portal-Fehler/Rate-Limit).
    # Das UI kann damit ehrlich anzeigen, ob Daten simuliert sind.
    source_status: str = SOURCE_STATUS_LIVE


@dataclass
class CompanyHistoryEntry:
    """Einzelner Eintrag in der Firmen-Änderungshistorie."""

    date: str
    type: str
    description: str


@dataclass
class CompanyDetails:
    """Detaillierte Firmendaten."""

    record: CompanyRecord
    shareholders: Optional[List[str]] = None
    business_purpose: Optional[str] = None
    history: Optional[List[CompanyHistoryEntry]] = None  # Änderungshistorie


# ============================================================================
# HANDELSREGISTER SERVICE
# ============================================================================


class HandelsregisterService:
    """Service für Handelsregister-Abfragen.

    Implementiert Web-Scraping des offiziellen Portals mit:
    - Sliding Window Rate Limiting (60/Stunde)
    - Redis Caching (24h TTL)
    - Fallback auf Mock bei Fehlern
    """

    def __init__(self) -> None:
        """Initialisiert Service."""
        global _MOCK_MODE_WARNED

        # Rate Limiting: Sliding Window
        self._request_times: Deque[float] = deque(maxlen=HANDELSREGISTER_RATE_LIMIT_PER_HOUR)
        self._lock = asyncio.Lock()

        # Mock-Modus (Fallback oder explizit aktiviert)
        self.mock_enabled = getattr(settings, "HANDELSREGISTER_MOCK_ENABLED", False)

        # W1-011: Einmaliges WARN pro Prozess - Mock-Daten sind SIMULIERT.
        if self.mock_enabled and not _MOCK_MODE_WARNED:
            _MOCK_MODE_WARNED = True
            logger.warning(
                "handelsregister_mock_modus_aktiv",
                message=(
                    "Handelsregister laeuft im Mock-Modus - Registerdaten "
                    "sind SIMULIERT. Fuer echte Daten "
                    "HANDELSREGISTER_MOCK_ENABLED=false setzen."
                ),
            )

        # Redis Cache Key Prefix
        self._cache_prefix = "handelsregister:"

    # ========================================================================
    # RATE LIMITING
    # ========================================================================

    def _can_make_request(self) -> bool:
        """Prüft ob ein Request gemacht werden darf (Rate Limit).

        Returns:
            True wenn Request erlaubt
        """
        now = time.time()
        hour_ago = now - 3600

        # Alte Einträge entfernen
        while self._request_times and self._request_times[0] < hour_ago:
            self._request_times.popleft()

        return len(self._request_times) < HANDELSREGISTER_RATE_LIMIT_PER_HOUR

    def _record_request(self) -> None:
        """Zeichnet einen Request für Rate Limiting auf."""
        self._request_times.append(time.time())

    def _get_wait_time(self) -> float:
        """Berechnet Wartezeit bis nächster Request erlaubt.

        Returns:
            Sekunden bis nächster Request möglich
        """
        if not self._request_times:
            return 0.0

        oldest = self._request_times[0]
        wait_until = oldest + 3600
        now = time.time()

        return max(0.0, wait_until - now)

    # ========================================================================
    # CACHING
    # ========================================================================

    async def _get_from_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Holt Daten aus Redis Cache.

        Args:
            cache_key: Cache-Schlüssel

        Returns:
            Gecachte Daten oder None
        """
        try:
            from app.core.redis import get_redis_client

            redis = await get_redis_client()
            if redis is None:
                return None

            import json
            data = await redis.get(f"{self._cache_prefix}{cache_key}")
            if data:
                return json.loads(data)
        except Exception as e:
            logger.debug("cache_get_error", **safe_error_log(e))

        return None

    async def _set_cache(
        self, cache_key: str, data: Dict[str, Any], ttl_hours: int = HANDELSREGISTER_CACHE_TTL_HOURS
    ) -> None:
        """Speichert Daten in Redis Cache.

        Args:
            cache_key: Cache-Schlüssel
            data: Zu cachende Daten
            ttl_hours: TTL in Stunden
        """
        try:
            from app.core.redis import get_redis_client


            redis = await get_redis_client()
            if redis is None:
                return

            import json
            await redis.set(
                f"{self._cache_prefix}{cache_key}",
                json.dumps(data, default=str),
                ex=ttl_hours * 3600,
            )
        except Exception as e:
            logger.debug("cache_set_error", **safe_error_log(e))

    def _make_cache_key(self, name: str, location: Optional[str] = None) -> str:
        """Erstellt Cache-Schlüssel.

        Args:
            name: Firmenname
            location: Optional Ort

        Returns:
            Cache-Schlüssel
        """
        import hashlib
        key_data = f"{name.lower()}:{(location or '').lower()}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:32]

    # ========================================================================
    # PUBLIC API
    # ========================================================================

    async def search_company(
        self, name: str, location: Optional[str] = None
    ) -> List[CompanyRecord]:
        """Sucht Firmen im Handelsregister.

        Args:
            name: Firmenname (oder Teil davon)
            location: Optional Ort zur Einschränkung

        Returns:
            Liste von CompanyRecord-Objekten

        Raises:
            ValueError: Bei ungültigen Eingaben
        """
        # SECURITY: Input-Validierung (CWE-20, CWE-80)
        _validate_search_input(name, location)

        # SECURITY: Keine PII (Firmennamen) in Logs - nur Länge loggen
        logger.info(
            "handelsregister_search_requested",
            name_length=len(name),
            has_location=location is not None,
            mock=self.mock_enabled,
        )

        # Mock-Modus
        if self.mock_enabled:
            return self._mock_search(name, location)

        # Cache prüfen
        cache_key = self._make_cache_key(name, location)
        cached = await self._get_from_cache(cache_key)
        if cached:
            logger.debug("handelsregister_cache_hit", cache_key=cache_key)
            return [self._dict_to_record(r) for r in cached.get("records", [])]

        # Rate Limit prüfen
        async with self._lock:
            if not self._can_make_request():
                wait_time = self._get_wait_time()
                logger.warning(
                    "handelsregister_rate_limited",
                    wait_seconds=wait_time,
                )
                # Fallback auf Mock bei Rate Limit (W1-011: gekennzeichnet)
                return self._mock_search(
                    name, location, source_status=SOURCE_STATUS_MOCK_FALLBACK
                )

            self._record_request()

        # Portal-Anfrage
        try:
            records = await self._fetch_from_portal(name, location)

            # Cache speichern
            await self._set_cache(
                cache_key,
                {"records": [self._record_to_dict(r) for r in records]},
            )

            return records

        except Exception as e:
            # SECURITY: Keine Firmennamen in Logs (PII)
            logger.error(
                "handelsregister_portal_error",
                **safe_error_log(e),
                name_length=len(name),
            )
            # Fallback auf Mock bei Fehler (W1-011: gekennzeichnet)
            return self._mock_search(
                name, location, source_status=SOURCE_STATUS_MOCK_FALLBACK
            )

    async def get_company_details(self, register_id: str) -> Optional[CompanyDetails]:
        """Ruft detaillierte Firmendaten ab.

        Args:
            register_id: Handelsregister-ID (z.B. "HRB 123456")

        Returns:
            CompanyDetails oder None
        """
        # SECURITY: Registernummer IMMER zuerst validieren (CWE-918).
        # Vorher wurde erst tief im Portal-Fetch validiert — Mock-/Cache-/
        # Rate-Limit-Pfade akzeptierten beliebige (manipulierte) IDs.
        _validate_register_id(register_id)

        # SECURITY: Keine PII (register_id) in Logs - nur Typ loggen
        register_type = register_id.split()[0] if " " in register_id else "unknown"
        logger.info(
            "handelsregister_details_requested",
            register_type=register_type,
            mock=self.mock_enabled,
        )

        if self.mock_enabled:
            return self._mock_details(register_id)

        # SECURITY: Cache-Key hashen um PII zu vermeiden (CWE-760)
        cache_key = f"details:{hashlib.sha256(register_id.encode()).hexdigest()[:16]}"
        cached = await self._get_from_cache(cache_key)
        if cached:
            return self._dict_to_details(cached)

        # Rate Limit prüfen
        async with self._lock:
            if not self._can_make_request():
                logger.warning("handelsregister_rate_limited_details")
                return self._mock_details(
                    register_id, source_status=SOURCE_STATUS_MOCK_FALLBACK
                )

            self._record_request()

        try:
            details = await self._fetch_details_from_portal(register_id)
            if details:
                await self._set_cache(cache_key, self._details_to_dict(details))
            return details

        except Exception as e:
            # SECURITY: Keine PII (register_id) in Logs
            logger.error(
                "handelsregister_details_error",
                **safe_error_log(e),
                register_type=register_type,
            )
            return self._mock_details(
                register_id, source_status=SOURCE_STATUS_MOCK_FALLBACK
            )

    # ========================================================================
    # PORTAL FETCHING
    # ========================================================================

    async def _fetch_from_portal(
        self, name: str, location: Optional[str] = None
    ) -> List[CompanyRecord]:
        """Ruft Daten vom Handelsregister-Portal ab.

        Args:
            name: Firmenname
            location: Optional Ort

        Returns:
            Liste von CompanyRecord-Objekten
        """
        async with httpx.AsyncClient(
            timeout=HANDELSREGISTER_TIMEOUT_SECONDS,
            follow_redirects=True,
        ) as client:
            # Session starten (CSRF-Token holen)
            initial_response = await client.get(HANDELSREGISTER_SEARCH_URL)
            initial_response.raise_for_status()

            # CSRF-Token und ViewState extrahieren
            # SECURITY: Sicherer HTML-Parser mit XXE-Schutz (CWE-611)
            tree = html.fromstring(initial_response.text, parser=_SAFE_HTML_PARSER)
            view_state = self._extract_view_state(tree)

            # Suchformular absenden
            form_data = self._build_search_form(name, location, view_state)

            search_response = await client.post(
                HANDELSREGISTER_SEARCH_URL,
                data=form_data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": HANDELSREGISTER_SEARCH_URL,
                },
            )
            search_response.raise_for_status()

            # Ergebnisse parsen
            # SECURITY: Sicherer HTML-Parser mit XXE-Schutz (CWE-611)
            result_tree = html.fromstring(search_response.text, parser=_SAFE_HTML_PARSER)
            records = self._parse_search_results(result_tree)

            # SECURITY: Keine Firmennamen in Logs (PII)
            logger.info(
                "handelsregister_portal_search_completed",
                results_count=len(records),
            )

            return records

    def _extract_view_state(self, tree: html.HtmlElement) -> str:
        """Extrahiert ViewState aus HTML.

        Args:
            tree: Parsed HTML

        Returns:
            ViewState-Wert
        """
        inputs = tree.xpath("//input[@name='javax.faces.ViewState']/@value")
        return inputs[0] if inputs else ""

    def _build_search_form(
        self, name: str, location: Optional[str], view_state: str
    ) -> Dict[str, str]:
        """Erstellt Formulardaten für Suche.

        Args:
            name: Firmenname
            location: Optional Ort
            view_state: JSF ViewState

        Returns:
            Form-Data Dictionary
        """
        form_data = {
            "form:schlagwoerter": name,
            "form:ort": location or "",
            "form:registerArt_input": "",  # Alle Registerarten
            "form:registerNummer": "",
            "form:suchTyp_input": "0",  # 0 = alle, 1 = aktive
            "form:btnSuche": "",
            "javax.faces.ViewState": view_state,
            "form_SUBMIT": "1",
        }
        return form_data

    def _parse_search_results(self, tree: html.HtmlElement) -> List[CompanyRecord]:
        """Parst Suchergebnisse aus HTML.

        Args:
            tree: Parsed HTML

        Returns:
            Liste von CompanyRecord
        """
        records: List[CompanyRecord] = []

        # Ergebniszeilen finden
        rows = tree.xpath("//table[contains(@class, 'ergebnisListe')]//tr[position()>1]")

        for row in rows:
            try:
                record = self._parse_result_row(row)
                if record:
                    records.append(record)
            except Exception as e:
                logger.debug("parse_row_error", **safe_error_log(e))
                continue

        return records

    def _parse_result_row(self, row: html.HtmlElement) -> Optional[CompanyRecord]:
        """Parst eine Ergebniszeile.

        Args:
            row: HTML TR-Element

        Returns:
            CompanyRecord oder None
        """
        cells = row.xpath(".//td")
        if len(cells) < 4:
            return None

        # Firmenname
        name_elem = cells[0].xpath(".//a/text() | .//span/text()")
        name = name_elem[0].strip() if name_elem else None
        if not name:
            return None

        # Registergericht und Nummer
        register_text = cells[1].text_content().strip()
        register_court, register_number = self._parse_register_info(register_text)

        # Rechtsform aus Namen extrahieren
        legal_form = self._extract_legal_form(name)

        # Status
        status_text = cells[3].text_content().strip().lower() if len(cells) > 3 else ""
        status = "active"
        if "gelöscht" in status_text or "aufgelöst" in status_text:
            status = "dissolved"
        elif "liquidation" in status_text:
            status = "in_liquidation"

        # Adresse (falls vorhanden)
        address_elem = cells[2].text_content().strip() if len(cells) > 2 else None

        return CompanyRecord(
            name=name,
            legal_form=legal_form,
            register_court=register_court,
            register_number=register_number,
            registered_address=address_elem,
            status=status,
        )

    def _parse_register_info(self, text: str) -> tuple[Optional[str], Optional[str]]:
        """Parst Registergericht und Nummer aus Text.

        Args:
            text: z.B. "Amtsgericht München HRB 123456"

        Returns:
            Tuple (court, number)
        """
        # Pattern: "Amtsgericht XYZ HRB/HRA/GnR 123456"
        pattern = r"(Amtsgericht\s+[\w\s]+?)\s+(HRB|HRA|GnR|PR|VR)\s*(\d+)"
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            court = match.group(1).strip()
            register_type = match.group(2).upper()
            number = match.group(3)
            return court, f"{register_type} {number}"

        return None, None

    def _extract_legal_form(self, name: str) -> Optional[str]:
        """Extrahiert Rechtsform aus Firmennamen.

        Args:
            name: Firmenname

        Returns:
            Rechtsform oder None
        """
        name_upper = name.upper()

        legal_forms = [
            ("GMBH & CO. KG", "GmbH & Co. KG"),
            ("GMBH & CO KG", "GmbH & Co. KG"),
            ("UG (HAFTUNGSBESCHRÄNKT) & CO. KG", "UG & Co. KG"),
            ("AG & CO. KG", "AG & Co. KG"),
            ("GMBH", "GmbH"),
            ("UG (HAFTUNGSBESCHRÄNKT)", "UG"),
            ("UG", "UG"),
            ("AG", "AG"),
            ("SE", "SE"),
            ("KG", "KG"),
            ("OHG", "OHG"),
            ("EK", "e.K."),
            ("E.K.", "e.K."),
            ("PARTG", "PartG"),
            ("PARTG MBB", "PartG mbB"),
            ("EV", "e.V."),
            ("E.V.", "e.V."),
            ("EG", "eG"),
            ("E.G.", "eG"),
        ]

        for pattern, form in legal_forms:
            if pattern in name_upper:
                return form

        return None

    async def _fetch_details_from_portal(self, register_id: str) -> Optional[CompanyDetails]:
        """Ruft Detailseite vom Portal ab.

        Args:
            register_id: Registernummer (z.B. "HRB 123456")

        Returns:
            CompanyDetails oder None
        """
        # Für Details brauchen wir eine separate Suche nach Registernummer
        async with httpx.AsyncClient(
            timeout=HANDELSREGISTER_TIMEOUT_SECONDS,
            follow_redirects=True,
        ) as client:
            # Session starten
            initial_response = await client.get(HANDELSREGISTER_SEARCH_URL)
            initial_response.raise_for_status()

            # SECURITY: Sicherer HTML-Parser mit XXE-Schutz (CWE-611)
            tree = html.fromstring(initial_response.text, parser=_SAFE_HTML_PARSER)
            view_state = self._extract_view_state(tree)

            # SECURITY: Registernummer validieren (CWE-918)
            register_type, register_number = _validate_register_id(register_id)

            form_data = {
                "form:schlagwoerter": "",
                "form:ort": "",
                "form:registerArt_input": register_type,
                "form:registerNummer": register_number,
                "form:suchTyp_input": "0",
                "form:btnSuche": "",
                "javax.faces.ViewState": view_state,
                "form_SUBMIT": "1",
            }

            search_response = await client.post(
                HANDELSREGISTER_SEARCH_URL,
                data=form_data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": HANDELSREGISTER_SEARCH_URL,
                },
            )
            search_response.raise_for_status()

            # SECURITY: Sicherer HTML-Parser mit XXE-Schutz (CWE-611)
            result_tree = html.fromstring(search_response.text, parser=_SAFE_HTML_PARSER)
            records = self._parse_search_results(result_tree)

            if not records:
                return None

            # Ersten Treffer als Details verwenden
            record = records[0]

            return CompanyDetails(
                record=record,
                shareholders=None,  # Nur in kostenpflichtiger Abrufung
                business_purpose=None,
                history=None,
            )

    # ========================================================================
    # SERIALIZATION HELPERS
    # ========================================================================

    def _record_to_dict(self, record: CompanyRecord) -> Dict[str, object]:
        """Konvertiert CompanyRecord zu Dict."""
        return {
            "name": record.name,
            "legal_form": record.legal_form,
            "register_court": record.register_court,
            "register_number": record.register_number,
            "registered_address": record.registered_address,
            "founded_date": record.founded_date,
            "capital": record.capital,
            "managing_directors": record.managing_directors,
            "status": record.status,
            # W1-011: Herkunft mit-serialisieren (Cache)
            "source_status": record.source_status,
        }

    def _dict_to_record(self, data: Dict[str, object]) -> CompanyRecord:
        """Konvertiert Dict zu CompanyRecord."""
        managing_directors = data.get("managing_directors")
        if not isinstance(managing_directors, list):
            managing_directors = None
        return CompanyRecord(
            name=str(data.get("name", "")),
            legal_form=str(data.get("legal_form")) if data.get("legal_form") else None,
            register_court=str(data.get("register_court")) if data.get("register_court") else None,
            register_number=str(data.get("register_number")) if data.get("register_number") else None,
            registered_address=str(data.get("registered_address")) if data.get("registered_address") else None,
            founded_date=str(data.get("founded_date")) if data.get("founded_date") else None,
            capital=str(data.get("capital")) if data.get("capital") else None,
            managing_directors=managing_directors,
            status=str(data.get("status", "active")),
            # W1-011: Cache enthaelt nur Live-Ergebnisse -> Default "live"
            source_status=str(data.get("source_status", SOURCE_STATUS_LIVE)),
        )

    def _details_to_dict(self, details: CompanyDetails) -> Dict[str, object]:
        """Konvertiert CompanyDetails zu Dict."""
        history_dicts = None
        if details.history:
            history_dicts = [
                {"date": h.date, "type": h.type, "description": h.description}
                for h in details.history
            ]
        return {
            "record": self._record_to_dict(details.record),
            "shareholders": details.shareholders,
            "business_purpose": details.business_purpose,
            "history": history_dicts,
        }

    def _dict_to_details(self, data: Dict[str, object]) -> CompanyDetails:
        """Konvertiert Dict zu CompanyDetails."""
        history = None
        raw_history = data.get("history")
        if raw_history and isinstance(raw_history, list):
            history = [
                CompanyHistoryEntry(
                    date=str(h.get("date", "")),
                    type=str(h.get("type", "")),
                    description=str(h.get("description", "")),
                )
                for h in raw_history
                if isinstance(h, dict)
            ]
        record_data = data.get("record")
        if not isinstance(record_data, dict):
            record_data = {}
        return CompanyDetails(
            record=self._dict_to_record(record_data),
            shareholders=data.get("shareholders") if isinstance(data.get("shareholders"), list) else None,
            business_purpose=str(data.get("business_purpose", "")) if data.get("business_purpose") else None,
            history=history,
        )

    # ========================================================================
    # MOCK HELPERS (Fallback)
    # ========================================================================

    def _mock_search(
        self,
        name: str,
        location: Optional[str] = None,
        source_status: str = SOURCE_STATUS_MOCK,
    ) -> List[CompanyRecord]:
        """Mock-Suche für Entwicklung/Tests und Fallback.

        W1-011: ``source_status`` kennzeichnet die Herkunft ("mock" bei
        explizit aktiviertem Mock-Modus, "mock_fallback" bei Portal-Fehler
        oder Rate-Limit), damit Consumer/UI simulierte Daten erkennen.
        """
        mock_results: List[CompanyRecord] = []
        name_lower = name.lower()

        # GmbH
        if "gmbh" in name_lower or "gesellschaft" in name_lower:
            mock_results.append(
                CompanyRecord(
                    name=f"{name} GmbH",
                    legal_form="GmbH",
                    register_court="Amtsgericht München",
                    register_number="HRB 234567",
                    registered_address="Musterstraße 123, 80331 München",
                    founded_date="2015-03-15",
                    capital="25.000 EUR",
                    managing_directors=["Max Mustermann"],
                    status="active",
                )
            )

        # AG
        if "ag" in name_lower or len(name) > 20:
            mock_results.append(
                CompanyRecord(
                    name=f"{name} AG",
                    legal_form="AG",
                    register_court="Amtsgericht Frankfurt am Main",
                    register_number="HRB 98765",
                    registered_address="Börsenplatz 1, 60313 Frankfurt",
                    founded_date="2005-06-20",
                    capital="50.000.000 EUR",
                    managing_directors=["Dr. Anna Schmidt", "Thomas Weber"],
                    status="active",
                )
            )

        # UG (haftungsbeschränkt)
        if "ug" in name_lower or "startup" in name_lower:
            mock_results.append(
                CompanyRecord(
                    name=f"{name} UG (haftungsbeschränkt)",
                    legal_form="UG",
                    register_court="Amtsgericht Berlin",
                    register_number="HRB 187654",
                    registered_address="Startupstraße 42, 10115 Berlin",
                    founded_date="2020-01-10",
                    capital="1.000 EUR",
                    managing_directors=["Lisa Müller"],
                    status="active",
                )
            )

        # Einzelunternehmen (Fallback)
        if not mock_results:
            mock_results.append(
                CompanyRecord(
                    name=name,
                    legal_form="Einzelunternehmen",
                    register_court=None,
                    register_number=None,
                    registered_address=f"{location or 'Musterstadt'}",
                    founded_date="2018-08-01",
                    capital=None,
                    managing_directors=[name],
                    status="active",
                )
            )

        # W1-011: Herkunft auf allen Mock-Ergebnissen kennzeichnen
        for record in mock_results:
            record.source_status = source_status

        logger.debug(
            "handelsregister_mock_search_completed",
            results_count=len(mock_results),
        )

        return mock_results

    def _mock_details(
        self,
        register_id: str,
        source_status: str = SOURCE_STATUS_MOCK,
    ) -> Optional[CompanyDetails]:
        """Mock-Details für Entwicklung/Tests und Fallback."""
        record = CompanyRecord(
            name="Muster GmbH",
            legal_form="GmbH",
            register_court="Amtsgericht München",
            register_number=register_id,
            registered_address="Musterstraße 123, 80331 München",
            founded_date="2015-03-15",
            capital="25.000 EUR",
            managing_directors=["Max Mustermann", "Erika Musterfrau"],
            status="active",
            source_status=source_status,
        )

        details = CompanyDetails(
            record=record,
            shareholders=["Holding GmbH (51%)", "Privatpersonen (49%)"],
            business_purpose="Softwareentwicklung und IT-Beratung",
            history=[
                CompanyHistoryEntry(
                    date="2015-03-15",
                    type="Gruendung",
                    description="Eintragung ins Handelsregister",
                ),
                CompanyHistoryEntry(
                    date="2018-06-20",
                    type="Kapitalerhöhung",
                    description="Stammkapital von 10.000 auf 25.000 EUR erhöht",
                ),
                CompanyHistoryEntry(
                    date="2020-11-05",
                    type="Geschäftsführerwechsel",
                    description="Erika Musterfrau zur Geschäftsführerin bestellt",
                ),
            ],
        )

        # SECURITY: Keine PII (register_id) in Logs - nur Typ loggen
        register_type = register_id.split()[0] if " " in register_id else "unknown"
        logger.debug("handelsregister_mock_details_returned", register_type=register_type)

        return details
