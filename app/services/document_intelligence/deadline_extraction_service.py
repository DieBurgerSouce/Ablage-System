"""Deadline Extraction Service.

Automatische Extraktion von Fristen aus OCR-Text und Erstellung
von PrivatDeadline-Eintraegen. Nutzt LLM-NER fuer intelligente
Deadline-Erkennung und Klassifizierung.
"""

import re
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    PrivatDeadline,
    PrivatDeadlineType,
    PrivatDocument,
    PrivatSpace,
)
from app.services.document_intelligence.llm_ner_service import (

    EntityType,
    ExtractedEntity,
    LLMNERService,
    get_llm_ner_service,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class ParsedDeadline:
    """Eine geparste Frist aus dem Text."""

    title: str
    due_date: date
    deadline_type: PrivatDeadlineType
    description: Optional[str] = None
    confidence: float = 0.0
    context: str = ""
    is_recurring: bool = False
    recurrence_pattern: Optional[str] = None
    reminder_days: List[int] = field(default_factory=lambda: [30, 7, 1])


@dataclass
class DeadlineExtractionResult:
    """Ergebnis der Deadline-Extraktion."""

    document_id: Optional[UUID] = None
    deadlines: List[ParsedDeadline] = field(default_factory=list)
    created_deadline_ids: List[UUID] = field(default_factory=list)
    processing_time_ms: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        """Anzahl erfolgreich erstellter Deadlines."""
        return len(self.created_deadline_ids)


# ============================================================================
# Deutsche Datum-Parser
# ============================================================================


class GermanDateParser:
    """Parser fuer deutsche Datumsformate."""

    # Monatsnamen Deutsch -> Monatszahl
    MONTHS_DE = {
        "januar": 1, "jan": 1,
        "februar": 2, "feb": 2,
        "maerz": 3, "märz": 3, "mar": 3, "mrz": 3,
        "april": 4, "apr": 4,
        "mai": 5,
        "juni": 6, "jun": 6,
        "juli": 7, "jul": 7,
        "august": 8, "aug": 8,
        "september": 9, "sep": 9, "sept": 9,
        "oktober": 10, "okt": 10,
        "november": 11, "nov": 11,
        "dezember": 12, "dez": 12,
    }

    # Relative Zeitangaben
    RELATIVE_PATTERNS = {
        r"innerhalb\s+von\s+(\d+)\s+tagen?": ("days", 1),
        r"innerhalb\s+von\s+(\d+)\s+wochen?": ("weeks", 1),
        r"innerhalb\s+von\s+(\d+)\s+monaten?": ("months", 1),
        r"(\d+)\s+tage?\s+nach\s+erhalt": ("days", 1),
        r"(\d+)\s+wochen?\s+nach\s+erhalt": ("weeks", 1),
        r"zum\s+monatsende": ("month_end", None),
        r"zum\s+quartalsende": ("quarter_end", None),
        r"zum\s+jahresende": ("year_end", None),
    }

    @classmethod
    def parse(cls, text: str, reference_date: Optional[date] = None) -> Optional[date]:
        """Parst deutsches Datum aus Text.

        Args:
            text: Text mit Datumsangabe
            reference_date: Referenzdatum fuer relative Angaben

        Returns:
            Geparstes Datum oder None
        """
        if not text:
            return None

        text = text.lower().strip()
        reference = reference_date or date.today()

        # ISO-Format (YYYY-MM-DD) - oft von LLM normalisiert
        iso_match = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
        if iso_match:
            try:
                return date(
                    int(iso_match.group(1)),
                    int(iso_match.group(2)),
                    int(iso_match.group(3)),
                )
            except ValueError as e:
                logger.debug("iso_date_parse_failed", text=text, error_type=type(e).__name__)

        # Deutsches Format (DD.MM.YYYY)
        de_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})", text)
        if de_match:
            try:
                day = int(de_match.group(1))
                month = int(de_match.group(2))
                year = int(de_match.group(3))
                if year < 100:
                    year += 2000
                return date(year, month, day)
            except ValueError as e:
                logger.debug("german_date_parse_failed", text=text, error_type=type(e).__name__)

        # Deutsches Format mit Monatsnamen (DD. Monat YYYY)
        month_match = re.search(
            r"(\d{1,2})\.?\s*("
            + "|".join(cls.MONTHS_DE.keys())
            + r")\s*(\d{2,4})?",
            text,
        )
        if month_match:
            try:
                day = int(month_match.group(1))
                month = cls.MONTHS_DE.get(month_match.group(2).lower(), 0)
                year_str = month_match.group(3)
                if year_str:
                    year = int(year_str)
                    if year < 100:
                        year += 2000
                else:
                    year = reference.year
                    # Wenn Datum in Vergangenheit, naechstes Jahr
                    if date(year, month, day) < reference:
                        year += 1
                return date(year, month, day)
            except ValueError as e:
                logger.debug("month_name_date_parse_failed", text=text, error_type=type(e).__name__)

        # Relative Zeitangaben
        for pattern, (unit, multiplier) in cls.RELATIVE_PATTERNS.items():
            match = re.search(pattern, text)
            if match:
                try:
                    if unit == "days":
                        value = int(match.group(1)) if multiplier else 0
                        return reference + timedelta(days=value)
                    elif unit == "weeks":
                        value = int(match.group(1)) if multiplier else 0
                        return reference + timedelta(weeks=value)
                    elif unit == "months":
                        value = int(match.group(1)) if multiplier else 0
                        new_month = reference.month + value
                        new_year = reference.year + (new_month - 1) // 12
                        new_month = ((new_month - 1) % 12) + 1
                        # Letzter Tag des Monats wenn noetig
                        try:
                            return date(new_year, new_month, reference.day)
                        except ValueError:
                            # Tag existiert nicht, letzter Tag des Monats
                            if new_month == 12:
                                return date(new_year + 1, 1, 1) - timedelta(days=1)
                            return date(new_year, new_month + 1, 1) - timedelta(days=1)
                    elif unit == "month_end":
                        if reference.month == 12:
                            return date(reference.year + 1, 1, 1) - timedelta(days=1)
                        return date(reference.year, reference.month + 1, 1) - timedelta(
                            days=1
                        )
                    elif unit == "quarter_end":
                        quarter = (reference.month - 1) // 3 + 1
                        quarter_end_month = quarter * 3
                        if quarter_end_month == 12:
                            return date(reference.year, 12, 31)
                        return date(
                            reference.year, quarter_end_month + 1, 1
                        ) - timedelta(days=1)
                    elif unit == "year_end":
                        return date(reference.year, 12, 31)
                except ValueError as e:
                    logger.debug("relative_date_parse_failed", text=text, unit=unit, error_type=type(e).__name__)

        return None


# ============================================================================
# Deadline Type Classifier
# ============================================================================


class DeadlineTypeClassifier:
    """Klassifiziert Fristen basierend auf Kontext."""

    # Keywords fuer Deadline-Typen
    TYPE_KEYWORDS = {
        PrivatDeadlineType.CANCELLATION: [
            "kuendigung",
            "kuendig",
            "widerspruch",
            "widerruf",
            "kuendigungsfrist",
            "vertragsende",
        ],
        PrivatDeadlineType.PAYMENT: [
            "zahlung",
            "faellig",
            "zahlungsziel",
            "rechnung",
            "beitrag",
            "rate",
            "ueberweis",
            "einzug",
        ],
        PrivatDeadlineType.RENEWAL: [
            "verlaenger",
            "erneuer",
            "aktualisier",
            "update",
            "refresh",
        ],
        PrivatDeadlineType.EXPIRY: [
            "ablauf",
            "gueltig",
            "verfallen",
            "auslauf",
            "ende",
            "endet",
            "befristet",
        ],
        PrivatDeadlineType.REVIEW: [
            "pruef",
            "check",
            "kontroll",
            "ueberpruef",
            "besichtig",
            "wartung",
            "inspektion",
        ],
    }

    # Wiederholungsmuster
    RECURRENCE_PATTERNS = {
        r"j[aä]hrlich|einmal\s+(im\s+)?jahr|jedes\s+jahr": "yearly",
        r"monatlich|jeden\s+monat|einmal\s+(im\s+)?monat": "monthly",
        r"quartalsweise|viertelj[aä]hrlich|alle\s+3\s+monate": "quarterly",
        r"halbjährlich|alle\s+6\s+monate": "half-yearly",
        r"w[öo]chentlich|jede\s+woche": "weekly",
    }

    @classmethod
    def classify(cls, text: str, context: str = "") -> PrivatDeadlineType:
        """Klassifiziert Deadline-Typ basierend auf Text und Kontext.

        Args:
            text: Deadline-Text (Titel oder Value)
            context: Umgebender Kontext

        Returns:
            PrivatDeadlineType
        """
        combined = f"{text} {context}".lower()

        # Zaehle Keyword-Matches pro Typ
        scores: Dict[PrivatDeadlineType, int] = {}

        for deadline_type, keywords in cls.TYPE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in combined)
            if score > 0:
                scores[deadline_type] = score

        if scores:
            # Typ mit hoechstem Score
            return max(scores.keys(), key=lambda t: scores[t])

        return PrivatDeadlineType.CUSTOM

    @classmethod
    def detect_recurrence(cls, text: str, context: str = "") -> Tuple[bool, Optional[str]]:
        """Erkennt Wiederholungsmuster.

        Args:
            text: Deadline-Text
            context: Umgebender Kontext

        Returns:
            Tuple von (is_recurring, recurrence_pattern)
        """
        combined = f"{text} {context}".lower()

        for pattern, recurrence in cls.RECURRENCE_PATTERNS.items():
            if re.search(pattern, combined):
                return True, recurrence

        return False, None


# ============================================================================
# Deadline Extraction Service
# ============================================================================


class DeadlineExtractionService:
    """Service fuer automatische Deadline-Extraktion aus Dokumenten.

    Extrahiert Fristen aus OCR-Text mittels LLM-NER und erstellt
    automatisch PrivatDeadline-Eintraege.
    """

    def __init__(
        self,
        ner_service: Optional[LLMNERService] = None,
    ) -> None:
        """Initialisiert den Service.

        Args:
            ner_service: Optional LLM NER Service
        """
        self._ner_service = ner_service or get_llm_ner_service()
        self._date_parser = GermanDateParser()
        self._type_classifier = DeadlineTypeClassifier()

    def _generate_title(
        self,
        entity: ExtractedEntity,
        deadline_type: PrivatDeadlineType,
    ) -> str:
        """Generiert einen Titel fuer die Deadline.

        Args:
            entity: Extrahierte Entity
            deadline_type: Klassifizierter Typ

        Returns:
            Generierter Titel
        """
        # Basis-Praefixe pro Typ
        prefixes = {
            PrivatDeadlineType.CANCELLATION: "Kuendigungsfrist",
            PrivatDeadlineType.PAYMENT: "Zahlungsfrist",
            PrivatDeadlineType.RENEWAL: "Verlaengerungsfrist",
            PrivatDeadlineType.EXPIRY: "Ablaufdatum",
            PrivatDeadlineType.REVIEW: "Ueberpruefungstermin",
            PrivatDeadlineType.CUSTOM: "Frist",
        }

        prefix = prefixes.get(deadline_type, "Frist")

        # Versuche Kontext hinzuzufuegen
        if entity.context:
            # Kuerze Kontext auf max 50 Zeichen
            short_context = entity.context[:50].strip()
            if len(entity.context) > 50:
                short_context = short_context.rsplit(" ", 1)[0] + "..."
            return f"{prefix}: {short_context}"

        return f"{prefix}: {entity.value}"

    def _determine_reminder_days(
        self,
        deadline_type: PrivatDeadlineType,
        due_date: date,
    ) -> List[int]:
        """Bestimmt sinnvolle Erinnerungstage basierend auf Typ.

        Args:
            deadline_type: Typ der Deadline
            due_date: Faelligkeitsdatum

        Returns:
            Liste von Tagen vor Frist fuer Erinnerungen
        """
        days_until = (due_date - date.today()).days

        # Basis-Erinnerungen pro Typ
        type_reminders = {
            PrivatDeadlineType.CANCELLATION: [90, 30, 14, 7],  # Wichtig: Frueh erinnern
            PrivatDeadlineType.PAYMENT: [14, 7, 3, 1],  # Zahlungsfristen: Naeher dran
            PrivatDeadlineType.RENEWAL: [60, 30, 7],  # Verlaengerungen: Mittelfristig
            PrivatDeadlineType.EXPIRY: [30, 14, 7, 1],  # Ablauf: Standard
            PrivatDeadlineType.REVIEW: [14, 7, 1],  # Reviews: Kurz vorher
            PrivatDeadlineType.CUSTOM: [30, 7, 1],  # Standard
        }

        reminders = type_reminders.get(deadline_type, [30, 7, 1])

        # Filtere Erinnerungen, die nach dem heutigen Datum liegen
        return [r for r in reminders if r < days_until]

    async def extract_deadlines(
        self,
        text: str,
        document_id: Optional[UUID] = None,
        reference_date: Optional[date] = None,
    ) -> List[ParsedDeadline]:
        """Extrahiert Deadlines aus Text.

        Args:
            text: Zu analysierender Text
            document_id: Optionale Dokument-ID
            reference_date: Referenzdatum fuer relative Angaben

        Returns:
            Liste von ParsedDeadline-Objekten
        """
        if not text or not text.strip():
            return []

        reference = reference_date or date.today()

        logger.info(
            "deadline_extraction_start",
            document_id=str(document_id) if document_id else None,
            text_length=len(text),
        )

        # NER-Extraktion
        ner_result = await self._ner_service.extract_entities(
            text=text,
            document_id=document_id,
            entity_types=[EntityType.DEADLINE, EntityType.DATE],
        )

        parsed_deadlines: List[ParsedDeadline] = []

        for entity in ner_result.entities:
            # Datum parsen
            date_to_parse = entity.normalized_value or entity.value
            due_date = GermanDateParser.parse(date_to_parse, reference)

            if not due_date:
                logger.debug(
                    "unparseable_date",
                    value=entity.value,
                    normalized=entity.normalized_value,
                )
                continue

            # Nur zukuenftige Deadlines (oder heute)
            if due_date < reference:
                logger.debug(
                    "past_deadline_skipped",
                    due_date=due_date.isoformat(),
                    value=entity.value,
                )
                continue

            # Typ klassifizieren
            deadline_type = DeadlineTypeClassifier.classify(
                entity.value, entity.context
            )

            # Wiederholung erkennen
            is_recurring, recurrence_pattern = DeadlineTypeClassifier.detect_recurrence(
                entity.value, entity.context
            )

            # Titel generieren
            title = self._generate_title(entity, deadline_type)

            # Erinnerungstage bestimmen
            reminder_days = self._determine_reminder_days(deadline_type, due_date)

            parsed = ParsedDeadline(
                title=title,
                due_date=due_date,
                deadline_type=deadline_type,
                description=entity.context if len(entity.context) > 20 else None,
                confidence=entity.confidence,
                context=entity.context,
                is_recurring=is_recurring,
                recurrence_pattern=recurrence_pattern,
                reminder_days=reminder_days if reminder_days else [7, 1],
            )

            parsed_deadlines.append(parsed)

        logger.info(
            "deadline_extraction_complete",
            document_id=str(document_id) if document_id else None,
            deadlines_found=len(parsed_deadlines),
        )

        return parsed_deadlines

    async def extract_and_create_deadlines(
        self,
        db: AsyncSession,
        text: str,
        space_id: UUID,
        document_id: Optional[UUID] = None,
        property_id: Optional[UUID] = None,
        vehicle_id: Optional[UUID] = None,
        insurance_id: Optional[UUID] = None,
        loan_id: Optional[UUID] = None,
        created_by_id: Optional[UUID] = None,
        reference_date: Optional[date] = None,
        min_confidence: float = 0.6,
    ) -> DeadlineExtractionResult:
        """Extrahiert Deadlines und erstellt PrivatDeadline-Eintraege.

        Args:
            db: Datenbank-Session
            text: Zu analysierender Text
            space_id: ID des PrivatSpace
            document_id: Optionale Dokument-ID
            property_id: Optionale Property-ID
            vehicle_id: Optionale Vehicle-ID
            insurance_id: Optionale Insurance-ID
            loan_id: Optionale Loan-ID
            created_by_id: Optionale User-ID des Erstellers
            reference_date: Referenzdatum fuer relative Angaben
            min_confidence: Minimale Confidence fuer Erstellung

        Returns:
            DeadlineExtractionResult mit erstellten Deadline-IDs
        """
        start_time = datetime.now(timezone.utc)
        result = DeadlineExtractionResult(document_id=document_id)

        try:
            # Space verifizieren
            space = await db.get(PrivatSpace, space_id)
            if not space:
                result.errors.append(f"Space {space_id} nicht gefunden")
                return result

            # Deadlines extrahieren
            parsed_deadlines = await self.extract_deadlines(
                text=text,
                document_id=document_id,
                reference_date=reference_date,
            )

            result.deadlines = parsed_deadlines

            # Deadlines erstellen (nur mit ausreichender Confidence)
            for parsed in parsed_deadlines:
                if parsed.confidence < min_confidence:
                    logger.debug(
                        "deadline_skipped_low_confidence",
                        title=parsed.title,
                        confidence=parsed.confidence,
                        min_required=min_confidence,
                    )
                    continue

                try:
                    deadline = PrivatDeadline(
                        space_id=space_id,
                        document_id=document_id,
                        property_id=property_id,
                        vehicle_id=vehicle_id,
                        insurance_id=insurance_id,
                        loan_id=loan_id,
                        title=parsed.title[:255],  # Max 255 Zeichen
                        description=parsed.description,
                        deadline_type=parsed.deadline_type.value,
                        due_date=parsed.due_date,
                        reminder_days=parsed.reminder_days,
                        is_recurring=parsed.is_recurring,
                        recurrence_pattern=parsed.recurrence_pattern,
                        is_active=True,
                        is_completed=False,
                        created_by_id=created_by_id,
                    )

                    db.add(deadline)
                    await db.flush()

                    result.created_deadline_ids.append(deadline.id)

                    logger.info(
                        "deadline_created",
                        deadline_id=str(deadline.id),
                        title=parsed.title,
                        due_date=parsed.due_date.isoformat(),
                        deadline_type=parsed.deadline_type.value,
                    )

                except Exception as e:
                    error_msg = f"Fehler beim Erstellen von Deadline '{parsed.title}': {e}"
                    result.errors.append(error_msg)
                    logger.warning("deadline_creation_error", **safe_error_log(e))

            # Commit wird von Aufrufer erwartet

        except Exception as e:
            result.errors.append(f"Allgemeiner Fehler: {e}")
            logger.exception("deadline_extraction_error", **safe_error_log(e))

        finally:
            result.processing_time_ms = int(
                (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            )

        return result


# ============================================================================
# Singleton Pattern
# ============================================================================

_deadline_extraction_service: Optional[DeadlineExtractionService] = None
_deadline_extraction_service_lock = threading.Lock()


def get_deadline_extraction_service() -> DeadlineExtractionService:
    """Gibt die Singleton-Instanz des Deadline Extraction Service zurueck.

    Returns:
        DeadlineExtractionService Singleton-Instanz
    """
    global _deadline_extraction_service

    if _deadline_extraction_service is None:
        with _deadline_extraction_service_lock:
            if _deadline_extraction_service is None:
                _deadline_extraction_service = DeadlineExtractionService()

    return _deadline_extraction_service
