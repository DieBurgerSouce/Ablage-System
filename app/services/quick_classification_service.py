# -*- coding: utf-8 -*-
"""
QuickClassificationService - Schnelle Dokumenten-Klassifizierung.

Ziel: Innerhalb von 2-5 Sekunden erkennen ob Eingangs- oder Ausgangsrechnung.
Methode: Nur erste Seite mit schnellem OCR, dann Pattern-Matching.

Feinpoliert und durchdacht - fuer sofortiges Tag-Assignment im Upload-Flow.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Tuple, Dict, Any

import structlog
from prometheus_client import Counter, Histogram
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.extracted_data import InvoiceDirection
from app.core.audit_logger import get_audit_logger, SecurityEventType
from app.db.models import CompanySettings, Document, Tag

logger = structlog.get_logger(__name__)

# =============================================================================
# Prometheus Metriken - Enterprise Refined Monitoring
# =============================================================================

QUICK_CLASSIFICATION_REQUESTS = Counter(
    "quick_classification_requests_total",
    "Anzahl der Quick Classification Anfragen",
    ["direction", "tag_assigned"]
)

QUICK_CLASSIFICATION_DURATION = Histogram(
    "quick_classification_duration_seconds",
    "Dauer der Quick Classification in Sekunden",
    buckets=[0.1, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0]
)

QUICK_CLASSIFICATION_CONFIDENCE = Histogram(
    "quick_classification_confidence",
    "Confidence-Werte der Quick Classification",
    buckets=[0.0, 0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 1.0]
)

QUICK_CLASSIFICATION_MATCH_TYPE = Counter(
    "quick_classification_match_type_total",
    "Typ des erfolgreichen Matchings",
    ["match_type"]  # vat_id, iban, company_name, none
)

# Fixed UUIDs fuer System-Tags (aus Migration 038)
EINGANGSRECHNUNG_TAG_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
AUSGANGSRECHNUNG_TAG_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")

# Cache fuer CompanySettings (1 Minute TTL)
# Enterprise Refined: Vermeidet wiederholte DB-Abfragen bei Batch-Uploads
_company_settings_cache: Tuple[Optional[CompanySettings], datetime] = (None, datetime.min)
_CACHE_TTL = timedelta(minutes=1)


@dataclass
class ExtractedIdentifier:
    """Extrahierter Identifier mit Position im Text."""
    value: str
    position: int  # Character-Position im Text
    relative_position: float  # 0.0-1.0 (Anfang-Ende des Texts)
    context: str  # Umgebender Text


@dataclass
class QuickClassificationResult:
    """Ergebnis der schnellen Klassifizierung."""
    direction: InvoiceDirection
    confidence: float
    reason: str
    tag_assigned: bool = False
    tag_name: Optional[str] = None
    extracted_vat_ids: List[str] = field(default_factory=list)
    extracted_ibans: List[str] = field(default_factory=list)
    matched_identifier: Optional[str] = None


class QuickClassificationService:
    """
    Schnelle Klassifizierung fuer Upload-Flow.

    Erkennt Eingangs-/Ausgangsrechnungen in 2-5 Sekunden durch:
    1. USt-IdNr Matching (hoechste Prioritaet)
    2. IBAN Matching
    3. Firmenname Matching

    Weist automatisch Tags zu wenn Confidence >= 70%.
    """

    # Confidence-Schwellenwert fuer automatische Tag-Zuweisung
    AUTO_TAG_CONFIDENCE_THRESHOLD = 0.70

    # Regex-Patterns fuer Identifier-Extraktion
    VAT_ID_PATTERNS = [
        # Deutsche USt-IdNr: DE123456789
        r'(?:USt[.-]?Id(?:Nr)?[.:\s]*|VAT[.:\s]*ID[.:\s]*|Steuernummer[.:\s]*)?(DE\s*\d{9})',
        # Allgemeines EU-Format: XX123456789
        r'(?:USt[.-]?Id(?:Nr)?[.:\s]*|VAT[.:\s]*ID[.:\s]*)([A-Z]{2}\s*\d{9,12})',
        # Freistehend (DE gefolgt von 9 Ziffern)
        r'\b(DE\s*\d{9})\b',
        # Niederlaendisch/Belgisch: NL/BE mit Buchstaben
        r'\b((?:NL|BE)[A-Z0-9]{9,12})\b',
        # Oesterreichisch: ATU + 8 Ziffern
        r'\b(ATU\d{8})\b',
    ]

    IBAN_PATTERNS = [
        # Universelles IBAN-Pattern mit optionalen Leerzeichen
        # Format: 2 Buchstaben (Land) + 2 Ziffern (Prüfung) + 11-30 alphanumerische Zeichen
        # Unterstützt alle EU-Länder inkl. NL/BE mit Buchstaben im Bankcode (z.B. NL51 INGB...)
        r'(?:IBAN[.:\s]*)?([A-Z]{2}\d{2}\s*[A-Z0-9]{4}\s*[A-Z0-9]{4}\s*[A-Z0-9]{2,4}(?:\s*[A-Z0-9]{4})*)',
        # Kompakte IBAN ohne Leerzeichen (alle Formate)
        r'\b([A-Z]{2}\d{2}[A-Z0-9]{11,27})\b',
    ]

    COMPANY_PATTERNS = [
        # Zeilen mit Rechtsformen
        r'^(.+?(?:GmbH\s*&\s*Co\.?\s*KG|GmbH|AG|KG|OHG|UG|e\.K\.|SE|Ltd|Inc|B\.V\.|N\.V\.|S\.A\.)).*$',
    ]

    # Rechtsformen fuer Normalisierung
    LEGAL_SUFFIXES = [
        r"\s*gmbh\s*&\s*co\.?\s*kg\s*$",
        r"\s*gmbh\s*$",
        r"\s*ag\s*$",
        r"\s*kg\s*$",
        r"\s*ohg\s*$",
        r"\s*ug\s*(?:\(haftungsbeschraenkt\))?\s*$",
        r"\s*se\s*$",
        r"\s*e\.?\s*k\.?\s*$",
        r"\s*b\.?\s*v\.?\s*$",
        r"\s*n\.?\s*v\.?\s*$",
        r"\s*s\.?\s*a\.?\s*$",
        r"\s*ltd\.?\s*$",
        r"\s*inc\.?\s*$",
    ]

    # Maximale Textlaenge fuer Performance
    MAX_TEXT_LENGTH = 50000

    # Kontext-Keywords fuer Empfaenger-Erkennung (unsere Firma dort = Eingangsrechnung)
    # Unterstuetzt sowohl Umlaute (ä/ö/ü) als auch ASCII-Ersetzungen (ae/oe/ue)
    RECIPIENT_CONTEXT_PATTERNS = [
        r'rechnungsempf(?:ae|ä)nger\s*:?',
        r'lieferanschrift\s*:?',
        r'empf(?:ae|ä)nger\s*:',
        r'^\s*an\s*:\s*$',  # "An:" als eigene Zeile
        r'z\.?\s*h(?:ae|ä)n?d?\.?',  # "z.Hd.", "z.Händen", "z.Haenden"
        r'rechnung\s+an\s*:?',
        r'kunde\s*:',
        r'bill\s*to\s*:?',  # Englisch
        r'ship\s*to\s*:?',  # Englisch
        r'rechnungsadresse\s*:?',
        r'lieferadresse\s*:?',
    ]

    # Kontext-Keywords fuer Absender-Erkennung (unsere Firma dort = Ausgangsrechnung)
    # Unterstuetzt sowohl Umlaute (ä/ö/ü) als auch ASCII-Ersetzungen (ae/oe/ue)
    SENDER_CONTEXT_PATTERNS = [
        r'gesch(?:ae|ä)ftsf(?:ue|ü)hr',  # Geschaeftsfuehrer / Geschäftsführer
        r'handelsregister',
        r'amtsgericht',
        r'hrb\s*\d+',  # HRB 12345
        r'steuer[.-]?nr\.?\s*:',
        r'bank\s*:',  # Bankverbindung im Footer
        r'iban\s*:',
        r'bic\s*:',
        r'swift\s*:',
        r'bankverbindung',
        r'registergericht',
        r'sitz\s+der\s+gesellschaft',
        r'f(?:ue|ü)r\s+r(?:ue|ü)ckfragen',  # "Fuer Rueckfragen" / "Für Rückfragen"
    ]

    async def classify_document(
        self,
        document_id: uuid.UUID,
        ocr_text: str,
        db: AsyncSession,
        auto_assign_tag: bool = True
    ) -> QuickClassificationResult:
        """
        Schnelle Klassifizierung eines Dokuments.

        Args:
            document_id: UUID des Dokuments
            ocr_text: OCR-Text der ersten Seite
            db: Datenbank-Session
            auto_assign_tag: Automatisch Tag zuweisen wenn Confidence >= 70%

        Returns:
            QuickClassificationResult mit Direction, Confidence, Reason
        """
        # Input-Validierung
        if not ocr_text or not ocr_text.strip():
            logger.debug(
                "quick_classification_skipped",
                document_id=str(document_id),
                reason="empty_text"
            )
            return QuickClassificationResult(
                direction=InvoiceDirection.UNKNOWN,
                confidence=0.0,
                reason="Kein Text zur Klassifizierung"
            )

        # Maximale Textlaenge begrenzen (Performance)
        if len(ocr_text) > self.MAX_TEXT_LENGTH:
            logger.warning(
                "quick_classification_text_truncated",
                document_id=str(document_id),
                original_length=len(ocr_text),
                truncated_to=self.MAX_TEXT_LENGTH
            )
            ocr_text = ocr_text[:self.MAX_TEXT_LENGTH]

        # Encoding validieren (UTF-8)
        try:
            ocr_text.encode('utf-8')
        except UnicodeEncodeError:
            ocr_text = ocr_text.encode('utf-8', errors='replace').decode('utf-8')

        start_time = time.time()

        logger.debug(
            "quick_classification_started",
            document_id=str(document_id),
            text_length=len(ocr_text)
        )

        # 1. Firmeneinstellungen laden
        company = await self._get_company_settings(db)
        if not company:
            logger.debug("quick_classification_skipped", reason="no_company_settings")
            return QuickClassificationResult(
                direction=InvoiceDirection.UNKNOWN,
                confidence=0.0,
                reason="Keine Firmendaten konfiguriert"
            )

        # 2. Identifier aus Text extrahieren
        vat_ids = self._extract_vat_ids(ocr_text)
        ibans = self._extract_ibans(ocr_text)
        company_names = self._extract_company_names(ocr_text)

        logger.debug(
            "quick_classification_extracted",
            vat_ids_count=len(vat_ids),
            ibans_count=len(ibans),
            company_names_count=len(company_names)
        )

        # 3. USt-IdNr Check (hoechste Prioritaet)
        if company.vat_id:
            vat_result = self._match_vat_id(vat_ids, company.vat_id, ocr_text)
            if vat_result:
                result = QuickClassificationResult(
                    direction=vat_result[0],
                    confidence=vat_result[1],
                    reason=vat_result[2],
                    extracted_vat_ids=[v.value for v in vat_ids],
                    matched_identifier=company.vat_id
                )
                if auto_assign_tag and result.confidence >= self.AUTO_TAG_CONFIDENCE_THRESHOLD:
                    await self._assign_tag(db, document_id, result)
                self._record_metrics(result, start_time, "vat_id")
                return result

        # 4. IBAN Check
        if company.iban:
            iban_result = self._match_iban(ibans, company.iban)
            if iban_result:
                result = QuickClassificationResult(
                    direction=iban_result[0],
                    confidence=iban_result[1],
                    reason=iban_result[2],
                    extracted_ibans=[i.value for i in ibans],
                    matched_identifier=company.iban
                )
                if auto_assign_tag and result.confidence >= self.AUTO_TAG_CONFIDENCE_THRESHOLD:
                    await self._assign_tag(db, document_id, result)
                self._record_metrics(result, start_time, "iban")
                return result

        # 5. Firmenname Check
        if company.company_name:
            all_company_names = [company.company_name]
            if company.alternative_names:
                all_company_names.extend(company.alternative_names)

            name_result = self._match_company_name(company_names, all_company_names, ocr_text, ibans)
            if name_result:
                result = QuickClassificationResult(
                    direction=name_result[0],
                    confidence=name_result[1],
                    reason=name_result[2],
                    matched_identifier=company.company_name
                )
                if auto_assign_tag and result.confidence >= self.AUTO_TAG_CONFIDENCE_THRESHOLD:
                    await self._assign_tag(db, document_id, result)
                self._record_metrics(result, start_time, "company_name")
                return result

        # 6. Keine eindeutige Zuordnung
        logger.debug("quick_classification_unknown", document_id=str(document_id))
        result = QuickClassificationResult(
            direction=InvoiceDirection.UNKNOWN,
            confidence=0.0,
            reason="Keine eindeutige Zuordnung moeglich",
            extracted_vat_ids=[v.value for v in vat_ids],
            extracted_ibans=[i.value for i in ibans]
        )
        self._record_metrics(result, start_time, "none")
        return result

    def _record_metrics(
        self,
        result: QuickClassificationResult,
        start_time: float,
        match_type: str
    ) -> None:
        """
        Zeichnet Prometheus-Metriken fuer die Klassifizierung auf.

        Enterprise Refined: Vollstaendiges Monitoring fuer Grafana-Dashboards.

        Args:
            result: Klassifizierungsergebnis
            match_type: vat_id, iban, company_name, oder none
        """
        # Dauer aufzeichnen
        duration = time.time() - start_time
        QUICK_CLASSIFICATION_DURATION.observe(duration)

        # Request-Counter mit Labels
        direction_value = result.direction.value if isinstance(result.direction, InvoiceDirection) else str(result.direction)
        QUICK_CLASSIFICATION_REQUESTS.labels(
            direction=direction_value,
            tag_assigned=str(result.tag_assigned).lower()
        ).inc()

        # Confidence aufzeichnen
        QUICK_CLASSIFICATION_CONFIDENCE.observe(result.confidence)

        # Match-Typ aufzeichnen
        QUICK_CLASSIFICATION_MATCH_TYPE.labels(match_type=match_type).inc()

        logger.debug(
            "quick_classification_metrics_recorded",
            duration_seconds=duration,
            match_type=match_type,
            direction=direction_value,
            confidence=result.confidence
        )

    async def _get_company_settings(self, db: AsyncSession) -> Optional[CompanySettings]:
        """
        Laedt die Admin-Firmendaten aus der Datenbank (mit Caching).

        Enterprise Refined: 1-Minuten-Cache um DB-Last bei Batch-Uploads zu reduzieren.
        """
        global _company_settings_cache

        cached_settings, cache_time = _company_settings_cache
        if cached_settings is not None and datetime.now() - cache_time < _CACHE_TTL:
            logger.debug("company_settings_cache_hit")
            return cached_settings

        logger.debug("company_settings_cache_miss")
        result = await db.execute(
            select(CompanySettings).limit(1)
        )
        settings = result.scalar_one_or_none()

        # Cache aktualisieren
        _company_settings_cache = (settings, datetime.now())
        return settings

    async def _assign_tag(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        result: QuickClassificationResult
    ) -> None:
        """
        Weist dem Dokument automatisch den passenden Tag zu.

        Args:
            db: Datenbank-Session
            document_id: UUID des Dokuments
            result: Klassifizierungsergebnis (wird modifiziert)
        """
        if result.direction == InvoiceDirection.UNKNOWN:
            return

        # Tag bestimmen
        tag_id = EINGANGSRECHNUNG_TAG_ID if result.direction == InvoiceDirection.INCOMING else AUSGANGSRECHNUNG_TAG_ID
        tag_name = "Eingangsrechnung" if result.direction == InvoiceDirection.INCOMING else "Ausgangsrechnung"

        try:
            # Dokument laden mit tags (eager loading verhindert greenlet_spawn error)
            from sqlalchemy.orm import selectinload
            doc_result = await db.execute(
                select(Document)
                .options(selectinload(Document.tags))
                .where(Document.id == document_id)
            )
            doc = doc_result.scalar_one_or_none()

            if not doc:
                logger.warning("quick_classification_tag_failed", reason="document_not_found")
                return

            # Tag laden
            tag_result = await db.execute(
                select(Tag).where(Tag.id == tag_id)
            )
            tag = tag_result.scalar_one_or_none()

            if not tag:
                # Fallback: Tag nach Name suchen
                tag_result = await db.execute(
                    select(Tag).where(Tag.name == tag_name)
                )
                tag = tag_result.scalar_one_or_none()

            if not tag:
                logger.warning("quick_classification_tag_failed", reason="tag_not_found", tag_name=tag_name)
                return

            # Alte Richtungs-Tags entfernen (falls vorhanden)
            # Tags sind jetzt eager-loaded, keine greenlet_spawn errors mehr
            doc.tags = [t for t in doc.tags if t.name not in ["Eingangsrechnung", "Ausgangsrechnung"]]

            # Neuen Tag hinzufuegen
            doc.tags.append(tag)

            result.tag_assigned = True
            result.tag_name = tag_name

            logger.info(
                "quick_classification_tag_assigned",
                document_id=str(document_id),
                tag_name=tag_name,
                confidence=result.confidence
            )

            # GDPR Audit Logging - Enterprise Refined
            try:
                audit_logger = get_audit_logger(db)
                await audit_logger.log_event(
                    event_type=SecurityEventType.DOCUMENT_TAG_AUTO_ASSIGNED,
                    resource_type="document",
                    resource_id=str(document_id),
                    details={
                        "tag_name": tag_name,
                        "confidence": result.confidence,
                        "reason": result.reason,
                        "auto_assigned": True,
                        "source": "quick_classification",
                        "matched_identifier_type": "vat_id" if result.matched_identifier and "DE" in str(result.matched_identifier) else "iban" if result.matched_identifier else None,
                    },
                    severity="info",
                )
            except Exception as audit_error:
                # Audit-Fehler sollten Tag-Zuweisung nicht blockieren
                logger.warning(
                    "quick_classification_audit_log_failed",
                    document_id=str(document_id),
                    error=str(audit_error)
                )

        except Exception as e:
            logger.error(
                "quick_classification_tag_error",
                document_id=str(document_id),
                error=str(e)
            )

    def _extract_vat_ids(self, text: str) -> List[ExtractedIdentifier]:
        """Extrahiert alle USt-IdNr aus dem Text."""
        results = []
        text_length = len(text)

        for pattern in self.VAT_ID_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE):
                vat_id = match.group(1) if match.lastindex else match.group(0)
                vat_id = self._normalize_vat_id(vat_id)

                # Duplikate vermeiden
                if any(r.value == vat_id for r in results):
                    continue

                position = match.start()
                relative_pos = position / text_length if text_length > 0 else 0

                # Kontext extrahieren (50 Zeichen vor und nach)
                ctx_start = max(0, position - 50)
                ctx_end = min(text_length, match.end() + 50)
                context = text[ctx_start:ctx_end].replace('\n', ' ')

                results.append(ExtractedIdentifier(
                    value=vat_id,
                    position=position,
                    relative_position=relative_pos,
                    context=context
                ))

        return results

    def _extract_ibans(self, text: str) -> List[ExtractedIdentifier]:
        """Extrahiert alle IBANs aus dem Text."""
        results = []
        text_length = len(text)

        for pattern in self.IBAN_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                iban = match.group(1) if match.lastindex else match.group(0)
                iban = self._normalize_iban(iban)

                # Duplikate vermeiden
                if any(r.value == iban for r in results):
                    continue

                position = match.start()
                relative_pos = position / text_length if text_length > 0 else 0

                ctx_start = max(0, position - 50)
                ctx_end = min(text_length, match.end() + 50)
                context = text[ctx_start:ctx_end].replace('\n', ' ')

                results.append(ExtractedIdentifier(
                    value=iban,
                    position=position,
                    relative_position=relative_pos,
                    context=context
                ))

        return results

    def _extract_company_names(self, text: str) -> List[ExtractedIdentifier]:
        """Extrahiert potenzielle Firmennamen aus dem Text."""
        results = []
        text_length = len(text)

        for pattern in self.COMPANY_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE):
                name = match.group(1).strip()

                # Zu kurze Namen ignorieren
                if len(name) < 5:
                    continue

                position = match.start()
                relative_pos = position / text_length if text_length > 0 else 0

                results.append(ExtractedIdentifier(
                    value=name,
                    position=position,
                    relative_position=relative_pos,
                    context=match.group(0)
                ))

        return results

    def _match_vat_id(
        self,
        extracted: List[ExtractedIdentifier],
        company_vat_id: str,
        full_text: str
    ) -> Optional[Tuple[InvoiceDirection, float, str]]:
        """
        Matched USt-IdNr gegen Firmendaten.

        Bestimmt anhand der Position im Dokument ob wir Sender oder Empfaenger sind.
        """
        normalized_company = self._normalize_vat_id(company_vat_id)

        for vat in extracted:
            if vat.value == normalized_company:
                # Position analysieren: oberes Drittel = Sender, mittleres = Empfaenger
                direction = self._determine_direction_by_position(vat.relative_position, full_text)

                if direction == InvoiceDirection.OUTGOING:
                    return (
                        InvoiceDirection.OUTGOING,
                        0.95,
                        f"Firmen-USt-IdNr im Absenderbereich gefunden"
                    )
                elif direction == InvoiceDirection.INCOMING:
                    return (
                        InvoiceDirection.INCOMING,
                        0.95,
                        f"Firmen-USt-IdNr im Empfaengerbereich gefunden"
                    )
                else:
                    # Position unklar, aber USt-IdNr stimmt
                    # Heuristik: Wenn unsere USt-IdNr vorkommt, sind wir vermutlich Empfaenger
                    return (
                        InvoiceDirection.INCOMING,
                        0.75,
                        f"Firmen-USt-IdNr gefunden (Position unklar)"
                    )

        return None

    def _match_iban(
        self,
        extracted: List[ExtractedIdentifier],
        company_iban: str
    ) -> Optional[Tuple[InvoiceDirection, float, str]]:
        """
        Matched IBAN gegen Firmendaten.

        Wenn unsere IBAN auf einer Rechnung steht, ist es eine Ausgangsrechnung
        (wir geben unsere Bankverbindung fuer Zahlungen an).
        """
        normalized_company = self._normalize_iban(company_iban)

        for iban in extracted:
            if iban.value == normalized_company:
                return (
                    InvoiceDirection.OUTGOING,
                    0.90,
                    "Firmen-IBAN gefunden (Ausgangsrechnung)"
                )

        return None

    def _match_company_name(
        self,
        extracted: List[ExtractedIdentifier],
        company_names: List[str],
        full_text: str,
        ibans: List[ExtractedIdentifier]
    ) -> Optional[Tuple[InvoiceDirection, float, str]]:
        """
        Matched Firmennamen gegen Firmendaten.

        Priorisierung:
        1. IBAN-Distanz-Analyse (hoechste Prioritaet)
        2. Kontext-basierte Erkennung (Empfaenger/Absender-Keywords)
        3. Pattern-basierte Extraktion (mit Rechtsform-Suffix)
        4. Fallback: unknown (NICHT mehr Position-Heuristik)
        """
        # 1. IBAN-Distanz-Analyse (hoechste Prioritaet)
        # Logik: Der Absender einer Rechnung gibt seine IBAN an.
        # Wenn unser Firmenname nahe der IBAN steht → wir sind Absender → Ausgangsrechnung
        # Wenn unser Firmenname weit von der IBAN steht → wir sind Empfaenger → Eingangsrechnung
        iban_result = self._determine_direction_by_iban_proximity(full_text, company_names, ibans)
        if iban_result:
            QUICK_CLASSIFICATION_MATCH_TYPE.labels(match_type="iban_proximity").inc()
            return iban_result

        # 2. Kontext-basierte Erkennung
        # Sucht nach Empfaenger/Absender-Keywords und prueft ob Firmenname in der Naehe
        context_result = self._find_company_in_context(full_text, company_names)
        if context_result:
            QUICK_CLASSIFICATION_MATCH_TYPE.labels(match_type="context").inc()
            return context_result

        # 3. Pattern-basierte Extraktion pruefen (extrahierte Firmennamen mit Rechtsform)
        for extracted_name in extracted:
            for company_name in company_names:
                similarity = self._calculate_name_similarity(extracted_name.value, company_name)

                if similarity >= 0.85:
                    # Nutze Position-Heuristik als Fallback (mit niedrigerer Confidence)
                    direction = self._determine_direction_by_position(
                        extracted_name.relative_position,
                        full_text
                    )

                    if direction == InvoiceDirection.OUTGOING:
                        return (
                            InvoiceDirection.OUTGOING,
                            0.70,  # Niedrigere Confidence fuer Position-Heuristik
                            f"Firmenname im Absenderbereich gefunden ({similarity:.0%} Uebereinstimmung, Position-basiert)"
                        )
                    elif direction == InvoiceDirection.INCOMING:
                        return (
                            InvoiceDirection.INCOMING,
                            0.70,  # Niedrigere Confidence fuer Position-Heuristik
                            f"Firmenname im Empfaengerbereich gefunden ({similarity:.0%} Uebereinstimmung, Position-basiert)"
                        )

        # 4. Direkte Suche: Firmenname gefunden, aber kein eindeutiger Kontext
        # In diesem Fall KEIN automatischer Match - lieber "unknown" als falsch raten
        text_lower = full_text.lower()

        for company_name in company_names:
            normalized_name = self._normalize_company_name(company_name)

            if len(normalized_name) < 5:
                continue

            if normalized_name in text_lower:
                logger.debug(
                    "quick_classification_name_found_no_context",
                    company_name=company_name,
                    normalized=normalized_name,
                    message="Firmenname gefunden aber kein eindeutiger Kontext"
                )
                # Kein Return hier - lieber "unknown" als falsch raten
                # Der User muss manuell pruefen

        return None

    def _determine_direction_by_position(
        self,
        relative_position: float,
        full_text: str
    ) -> InvoiceDirection:
        """
        Bestimmt die Dokumentrichtung anhand der Position eines Identifiers.

        Heuristik fuer deutsche Geschaeftsbriefe:
        - Oberes Drittel (0.0-0.33): Absenderbereich (Logo, Absenderadresse)
        - Mittleres Drittel (0.33-0.66): Empfaengerbereich (Anschrift)
        - Unteres Drittel (0.66-1.0): Inhalt (oft Bankverbindung des Absenders)

        Bei Rechnungen:
        - Unsere Daten oben = Wir sind Absender = Ausgangsrechnung
        - Unsere Daten in der Mitte = Wir sind Empfaenger = Eingangsrechnung
        """
        # Position-basierte Heuristik
        if relative_position < 0.30:
            # Oberer Bereich: Wahrscheinlich Absender
            return InvoiceDirection.OUTGOING
        elif relative_position < 0.55:
            # Mittlerer Bereich: Wahrscheinlich Empfaenger
            return InvoiceDirection.INCOMING
        else:
            # Unterer Bereich: Koennte Bankdaten sein
            # Bankdaten am Ende = Absender gibt Konto fuer Zahlung an
            return InvoiceDirection.OUTGOING

    def _normalize_vat_id(self, vat_id: str) -> str:
        """Normalisiert eine USt-IdNr fuer den Vergleich."""
        return vat_id.replace(" ", "").replace(".", "").replace("-", "").upper()

    def _normalize_iban(self, iban: str) -> str:
        """Normalisiert eine IBAN fuer den Vergleich."""
        return iban.replace(" ", "").upper()

    def _normalize_company_name(self, name: str) -> str:
        """Normalisiert einen Firmennamen fuer den Vergleich."""
        normalized = name.lower().strip()

        for suffix_pattern in self.LEGAL_SUFFIXES:
            normalized = re.sub(suffix_pattern, "", normalized, flags=re.IGNORECASE)

        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _contains_company_name(self, text: str, company_name: str) -> bool:
        """
        Prueft ob ein Text den Firmennamen enthaelt (case-insensitive, normalisiert).

        Args:
            text: Text-Ausschnitt zum Pruefen
            company_name: Zu suchender Firmenname

        Returns:
            True wenn der Firmenname im Text gefunden wurde
        """
        if not text or not company_name:
            return False

        normalized_name = self._normalize_company_name(company_name)
        if len(normalized_name) < 4:
            return False

        return normalized_name in text.lower()

    # Pattern fuer Adressblock-Erkennung (Strasse + PLZ + Ort)
    # Wenn nach dem Firmennamen eine Adresse kommt, ist es wahrscheinlich der Empfaenger
    ADDRESS_BLOCK_PATTERNS = [
        # Deutsche PLZ + Ort: "12345 Berlin" oder "D-12345 Berlin"
        r'(?:d-?)?\d{5}\s+[a-zäöüß]+',
        # Strasse mit Hausnummer: "Musterstr. 123" oder "Musterstraße 12a"
        r'(?:str(?:aße|asse)?|weg|platz|allee|ring|damm|gasse)[.\s]*\d+[a-z]?',
        # Postfach
        r'postfach\s*\d+',
    ]

    def _has_address_after_company(self, text: str, company_position: int) -> bool:
        """
        Prueft ob nach dem Firmennamen ein Adressblock folgt.

        Wenn ja, ist dies sehr wahrscheinlich der Empfaenger-Bereich,
        unabhaengig von der IBAN-Naehe.
        """
        # Pruefe die naechsten 300 Zeichen nach dem Firmennamen
        context_end = min(len(text), company_position + 300)
        context_after = text[company_position:context_end].lower()

        for pattern in self.ADDRESS_BLOCK_PATTERNS:
            if re.search(pattern, context_after, re.IGNORECASE):
                return True
        return False

    def _determine_direction_by_iban_proximity(
        self,
        text: str,
        company_names: List[str],
        ibans: List[ExtractedIdentifier]
    ) -> Optional[Tuple[InvoiceDirection, float, str]]:
        """
        Bestimmt Richtung basierend auf Distanz zwischen Firmenname und IBAN.

        Logik: Auf Rechnungen gibt der ABSENDER seine IBAN an.
        - Firmenname nahe IBAN → Wir sind Absender → Ausgangsrechnung
        - Firmenname weit von IBAN → Wir sind Empfänger → Eingangsrechnung

        ABER: Wenn nach dem Firmennamen eine Adresse folgt (Strasse, PLZ, Ort),
        dann ist es wahrscheinlich der Empfaenger-Block, auch wenn IBAN nah ist.

        Args:
            text: OCR-Text
            company_names: Liste konfigurierter Firmennamen
            ibans: Extrahierte IBANs mit Positionen

        Returns:
            (direction, confidence, reason) oder None
        """
        if not ibans:
            return None

        text_lower = text.lower()

        # Finde alle Positionen unseres Firmennamens
        company_positions: List[int] = []
        for company_name in company_names:
            normalized = self._normalize_company_name(company_name)
            if len(normalized) < 4:
                continue

            start = 0
            while True:
                pos = text_lower.find(normalized, start)
                if pos == -1:
                    break
                company_positions.append(pos)
                start = pos + 1

        if not company_positions:
            logger.debug(
                "quick_classification_iban_proximity_no_company",
                message="Firmenname nicht im Text gefunden"
            )
            return None

        # NEUE LOGIK: Pruefe zuerst ob nach dem Firmennamen eine Adresse folgt
        # Wenn ja, ist dies der Empfaenger-Block (Eingangsrechnung)
        for company_pos in company_positions:
            if self._has_address_after_company(text, company_pos):
                logger.info(
                    "quick_classification_address_block_detected",
                    company_position=company_pos,
                    message="Adresse nach Firmenname gefunden - Empfaengerblock"
                )
                return (
                    InvoiceDirection.INCOMING,
                    0.88,
                    "Firmenname mit Adresse gefunden (Empfaengerblock) - Eingangsrechnung"
                )

        # Berechne minimalen Abstand zu irgendeiner IBAN
        min_distance = float('inf')
        closest_iban = ""
        closest_company_pos = 0
        for company_pos in company_positions:
            for iban in ibans:
                distance = abs(company_pos - iban.position)
                if distance < min_distance:
                    min_distance = distance
                    closest_iban = iban.value
                    closest_company_pos = company_pos

        # Schwellenwert: 500 Zeichen
        # Typische Rechnungsstruktur: Absender + IBAN sind im gleichen Block (Header/Footer)
        # Empfaenger steht im Adressblock, weit von der IBAN entfernt
        PROXIMITY_THRESHOLD = 500

        logger.info(
            "quick_classification_iban_proximity",
            min_distance=int(min_distance),
            threshold=PROXIMITY_THRESHOLD,
            closest_iban=closest_iban[:8] + "..." if closest_iban else None,
            company_position=closest_company_pos
        )

        if min_distance <= PROXIMITY_THRESHOLD:
            return (
                InvoiceDirection.OUTGOING,
                0.85,
                f"Firmenname nahe Bankverbindung ({int(min_distance)} Zeichen) - Ausgangsrechnung"
            )
        else:
            return (
                InvoiceDirection.INCOMING,
                0.85,
                f"Firmenname weit von Bankverbindung ({int(min_distance)} Zeichen) - Eingangsrechnung"
            )

    def _find_company_in_context(
        self,
        text: str,
        company_names: List[str]
    ) -> Optional[Tuple[InvoiceDirection, float, str]]:
        """
        Findet den Firmennamen im Text und bestimmt anhand des Kontexts die Richtung.

        Diese Methode analysiert den umgebenden Text um gefundene Firmennamen
        und erkennt ob sie im Empfaenger- oder Absender-Bereich stehen.

        Args:
            text: Vollstaendiger OCR-Text
            company_names: Liste der konfigurierten Firmennamen

        Returns:
            (InvoiceDirection, confidence, reason) oder None wenn kein Match
        """
        text_lower = text.lower()

        # 1. Suche nach Empfaenger-Kontext-Keywords
        for pattern in self.RECIPIENT_CONTEXT_PATTERNS:
            matches = list(re.finditer(pattern, text_lower, re.IGNORECASE | re.MULTILINE))
            for match in matches:
                # Pruefe die naechsten 300 Zeichen nach dem Keyword
                context_start = match.end()
                context_end = min(len(text_lower), context_start + 300)
                context_after = text_lower[context_start:context_end]

                for company_name in company_names:
                    if self._contains_company_name(context_after, company_name):
                        logger.info(
                            "quick_classification_context_match",
                            match_type="recipient_context",
                            keyword=match.group(),
                            company_name=company_name
                        )
                        return (
                            InvoiceDirection.INCOMING,
                            0.92,
                            f"Firmenname im Empfaengerbereich gefunden (nach '{match.group().strip()}')"
                        )

        # 2. Suche nach Absender-Kontext-Keywords (Footer-Bereich)
        for pattern in self.SENDER_CONTEXT_PATTERNS:
            matches = list(re.finditer(pattern, text_lower, re.IGNORECASE))
            for match in matches:
                # Pruefe 250 Zeichen vor und nach dem Keyword
                context_start = max(0, match.start() - 250)
                context_end = min(len(text_lower), match.end() + 250)
                context = text_lower[context_start:context_end]

                for company_name in company_names:
                    if self._contains_company_name(context, company_name):
                        logger.info(
                            "quick_classification_context_match",
                            match_type="sender_context",
                            keyword=match.group(),
                            company_name=company_name
                        )
                        return (
                            InvoiceDirection.OUTGOING,
                            0.88,
                            f"Firmenname im Absender-/Footerbereich gefunden (nahe '{match.group().strip()}')"
                        )

        # 3. NICHT mehr: Briefkopf-Position als Ausgangsrechnung interpretieren
        # GRUND: Der Briefkopf zeigt den ABSENDER der Rechnung an.
        # - Bei Eingangsrechnung: Lieferant steht im Briefkopf (nicht wir!)
        # - Bei Ausgangsrechnung: Wir stehen im Briefkopf
        # OHNE Kontext-Keywords koennen wir nicht unterscheiden!
        #
        # Stattdessen: Wenn Firmenname gefunden aber kein Kontext -> UNKNOWN
        # Das ist besser als falsch raten.

        return None

    def _calculate_name_similarity(self, name1: str, name2: str) -> float:
        """Berechnet die Aehnlichkeit zweier Firmennamen (0.0-1.0)."""
        n1 = self._normalize_company_name(name1)
        n2 = self._normalize_company_name(name2)

        if n1 == n2:
            return 1.0

        if not n1 or not n2:
            return 0.0

        # Levenshtein-Distanz
        distance = self._levenshtein_distance(n1, n2)
        max_len = max(len(n1), len(n2))

        return max(0.0, 1.0 - (distance / max_len))

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Berechnet die Levenshtein-Distanz zwischen zwei Strings."""
        if len(s1) < len(s2):
            s1, s2 = s2, s1

        if len(s2) == 0:
            return len(s1)

        previous_row = list(range(len(s2) + 1))

        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    def to_dict(self, result: QuickClassificationResult) -> Dict[str, Any]:
        """Konvertiert das Ergebnis in ein Dictionary fuer JSON-Speicherung."""
        return {
            "direction": result.direction.value if isinstance(result.direction, InvoiceDirection) else result.direction,
            "confidence": result.confidence,
            "reason": result.reason,
            "tag_assigned": result.tag_assigned,
            "tag_name": result.tag_name,
            "extracted_vat_ids": result.extracted_vat_ids,
            "extracted_ibans": result.extracted_ibans,
            "matched_identifier": result.matched_identifier
        }


# Singleton-Instanz fuer Performance
_quick_classification_service: Optional[QuickClassificationService] = None


def get_quick_classification_service() -> QuickClassificationService:
    """Gibt die Singleton-Instanz des QuickClassificationService zurueck."""
    global _quick_classification_service
    if _quick_classification_service is None:
        _quick_classification_service = QuickClassificationService()
    return _quick_classification_service
