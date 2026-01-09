"""LLM-basierter Named Entity Recognition Service.

Verwendet Qwen3-14B via Ollama fuer intelligente Entity-Extraktion
aus deutschen Dokumenten. Extrahiert:
- Fristen/Deadlines
- Geldbetraege
- Vertragspartner (Firmen/Personen)
- Vertragsnummern/Referenzen
- Adressen
- Datumsangaben
"""

import asyncio
import json
import re
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import structlog

from app.core.config import settings
from app.services.rag.llm_service import (
    LLMContextType,
    LLMMessage,
    LLMService,
    get_llm_service,
)

logger = structlog.get_logger(__name__)


class EntityType(str, Enum):
    """Typen von extrahierten Entities."""

    DEADLINE = "deadline"  # Fristen, Termine, Stichtage
    AMOUNT = "amount"  # Geldbetraege
    COMPANY = "company"  # Firmennamen
    PERSON = "person"  # Personennamen
    CONTRACT_NUMBER = "contract_number"  # Vertrags-/Policennummern
    REFERENCE = "reference"  # Aktenzeichen, Referenznummern
    ADDRESS = "address"  # Adressen
    DATE = "date"  # Allgemeine Datumsangaben
    IBAN = "iban"  # Bankverbindungen
    PHONE = "phone"  # Telefonnummern
    EMAIL = "email"  # E-Mail-Adressen


@dataclass
class ExtractedEntity:
    """Eine extrahierte Entity aus dem Dokument."""

    entity_type: EntityType
    value: str
    normalized_value: Optional[str] = None  # Normalisierte Form (z.B. ISO-Datum)
    confidence: float = 0.0  # 0.0 - 1.0
    context: str = ""  # Umgebender Text
    position: Optional[Tuple[int, int]] = None  # Start/End-Position im Text
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NERResult:
    """Ergebnis der NER-Analyse."""

    document_id: Optional[UUID] = None
    entities: List[ExtractedEntity] = field(default_factory=list)
    processing_time_ms: int = 0
    model_used: str = ""
    text_length: int = 0
    error: Optional[str] = None

    @property
    def deadlines(self) -> List[ExtractedEntity]:
        """Alle Fristen-Entities."""
        return [e for e in self.entities if e.entity_type == EntityType.DEADLINE]

    @property
    def amounts(self) -> List[ExtractedEntity]:
        """Alle Geldbetrags-Entities."""
        return [e for e in self.entities if e.entity_type == EntityType.AMOUNT]

    @property
    def companies(self) -> List[ExtractedEntity]:
        """Alle Firmen-Entities."""
        return [e for e in self.entities if e.entity_type == EntityType.COMPANY]

    @property
    def persons(self) -> List[ExtractedEntity]:
        """Alle Personen-Entities."""
        return [e for e in self.entities if e.entity_type == EntityType.PERSON]

    @property
    def contract_numbers(self) -> List[ExtractedEntity]:
        """Alle Vertragsnummern."""
        return [e for e in self.entities if e.entity_type == EntityType.CONTRACT_NUMBER]

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary fuer JSON-Serialisierung."""
        return {
            "document_id": str(self.document_id) if self.document_id else None,
            "entities": [
                {
                    "type": e.entity_type.value,
                    "value": e.value,
                    "normalized_value": e.normalized_value,
                    "confidence": e.confidence,
                    "context": e.context,
                    "metadata": e.metadata,
                }
                for e in self.entities
            ],
            "processing_time_ms": self.processing_time_ms,
            "model_used": self.model_used,
            "text_length": self.text_length,
            "summary": {
                "total_entities": len(self.entities),
                "deadlines": len(self.deadlines),
                "amounts": len(self.amounts),
                "companies": len(self.companies),
                "persons": len(self.persons),
                "contract_numbers": len(self.contract_numbers),
            },
        }


# System-Prompt fuer NER-Extraktion
NER_SYSTEM_PROMPT = """Du bist ein spezialisierter NER-Extraktions-Assistent fuer deutsche Geschaeftsdokumente.

Deine Aufgabe ist es, wichtige Entitaeten aus dem gegebenen Dokumenttext zu extrahieren und als strukturiertes JSON zurueckzugeben.

## Zu extrahierende Entitaeten:

1. **deadline**: Fristen, Termine, Stichtage, Kuendigungsfristen
   - Beispiele: "bis zum 31.12.2024", "innerhalb von 14 Tagen", "Kuendigungsfrist: 3 Monate"
   - normalized_value: ISO-Datum wenn moeglich (YYYY-MM-DD)

2. **amount**: Geldbetraege mit Waehrung
   - Beispiele: "1.234,56 EUR", "5.000 Euro", "15,99 Euro monatlich"
   - normalized_value: Numerischer Wert ohne Formatierung

3. **company**: Firmennamen
   - Beispiele: "Allianz Versicherungs-AG", "Deutsche Bank AG"
   - Achte auf GmbH, AG, SE, KG, etc.

4. **person**: Personennamen
   - Beispiele: "Dr. Max Mustermann", "Herr Mueller"
   - Achte auf Titel und Anreden

5. **contract_number**: Vertrags-, Policen-, Kundennummern
   - Beispiele: "Vertragsnummer: 12345678", "Police: DE-2024-001234"
   - normalized_value: Nur die Nummer

6. **reference**: Aktenzeichen, Vorgangsnummern
   - Beispiele: "Az.: 123/24", "Ihr Zeichen: ABC-2024"

7. **address**: Vollstaendige Adressen
   - Beispiele: "Musterstrasse 123, 12345 Berlin"

8. **date**: Allgemeine Datumsangaben (keine Fristen)
   - Beispiele: "Versicherungsbeginn: 01.01.2024"
   - normalized_value: ISO-Datum (YYYY-MM-DD)

9. **iban**: Bankverbindungen
   - Beispiele: "DE89 3704 0044 0532 0130 00"
   - normalized_value: IBAN ohne Leerzeichen

10. **phone**: Telefonnummern
    - Beispiele: "+49 30 12345678", "0800-123456"

11. **email**: E-Mail-Adressen
    - Beispiele: "info@example.de"

## Ausgabeformat:

Antworte NUR mit validem JSON in diesem Format:
```json
{
  "entities": [
    {
      "type": "deadline",
      "value": "bis zum 31.12.2024",
      "normalized_value": "2024-12-31",
      "confidence": 0.95,
      "context": "Die Kuendigungsfrist endet bis zum 31.12.2024."
    }
  ]
}
```

## Wichtige Regeln:

1. Extrahiere NUR tatsaechlich im Text vorhandene Informationen
2. Setze confidence zwischen 0.0 und 1.0 basierend auf Klarheit
3. Liefere context: ca. 50-100 Zeichen um die Entity herum
4. Bei Unsicherheit lieber weglassen als raten
5. Antworte NUR mit JSON, keine Erklaerungen
6. Wenn keine Entities gefunden: {"entities": []}
"""


class LLMNERService:
    """Service fuer LLM-basierte Named Entity Recognition.

    Verwendet Qwen3-14B via Ollama fuer praezise Entity-Extraktion
    aus deutschen Dokumenten mit strukturierter JSON-Ausgabe.
    """

    def __init__(
        self,
        llm_service: Optional[LLMService] = None,
        model: Optional[str] = None,
    ) -> None:
        """Initialisiert den NER-Service.

        Args:
            llm_service: Optional LLM-Service Instanz
            model: Optionales spezifisches Modell (default: qwen3:14b)
        """
        self._llm_service = llm_service or get_llm_service()
        self._model = model or getattr(
            settings, "DEFAULT_LLM_ANALYSIS", "qwen3:14b"
        )
        self._max_text_length = 8000  # Maximale Textlaenge pro Anfrage
        self._chunk_overlap = 200  # Ueberlappung bei Chunking

    def _chunk_text(self, text: str) -> List[str]:
        """Teilt langen Text in Chunks.

        Args:
            text: Zu teilender Text

        Returns:
            Liste von Text-Chunks
        """
        if len(text) <= self._max_text_length:
            return [text]

        chunks = []
        start = 0

        while start < len(text):
            end = start + self._max_text_length

            # Versuche an Satzende oder Absatz zu splitten
            if end < len(text):
                # Suche nach Satzende
                for sep in ["\n\n", "\n", ". ", "! ", "? "]:
                    last_sep = text[start:end].rfind(sep)
                    if last_sep > self._max_text_length // 2:
                        end = start + last_sep + len(sep)
                        break

            chunks.append(text[start:end])
            start = end - self._chunk_overlap

        logger.debug(
            "text_chunked",
            total_length=len(text),
            chunk_count=len(chunks),
            max_chunk_size=self._max_text_length,
        )

        return chunks

    def _parse_llm_response(self, response_text: str) -> List[Dict[str, Any]]:
        """Parst die LLM-Antwort zu Entities.

        Args:
            response_text: Rohe LLM-Antwort

        Returns:
            Liste von Entity-Dictionaries
        """
        # Versuche JSON zu extrahieren
        json_match = re.search(r"\{[\s\S]*\}", response_text)
        if not json_match:
            logger.warning("no_json_in_response", response_preview=response_text[:200])
            return []

        try:
            data = json.loads(json_match.group())
            entities = data.get("entities", [])

            if not isinstance(entities, list):
                logger.warning("invalid_entities_format", data=data)
                return []

            return entities

        except json.JSONDecodeError as e:
            logger.warning(
                "json_parse_error",
                error=str(e),
                response_preview=response_text[:200],
            )
            return []

    def _create_entity(
        self,
        entity_data: Dict[str, Any],
        text: str,
    ) -> Optional[ExtractedEntity]:
        """Erstellt ein ExtractedEntity aus LLM-Daten.

        Args:
            entity_data: Dictionary aus LLM-Antwort
            text: Originaltext fuer Position

        Returns:
            ExtractedEntity oder None bei Fehlern
        """
        try:
            entity_type_str = entity_data.get("type", "").lower()

            # Validiere Entity-Typ
            try:
                entity_type = EntityType(entity_type_str)
            except ValueError:
                logger.debug("unknown_entity_type", type=entity_type_str)
                return None

            value = entity_data.get("value", "")
            if not value:
                return None

            # Position im Text finden
            position = None
            value_lower = value.lower()
            text_lower = text.lower()
            idx = text_lower.find(value_lower)
            if idx >= 0:
                position = (idx, idx + len(value))

            return ExtractedEntity(
                entity_type=entity_type,
                value=value,
                normalized_value=entity_data.get("normalized_value"),
                confidence=float(entity_data.get("confidence", 0.8)),
                context=entity_data.get("context", ""),
                position=position,
                metadata={},
            )

        except Exception as e:
            logger.warning("entity_creation_error", error=str(e), data=entity_data)
            return None

    def _merge_chunk_entities(
        self,
        all_entities: List[ExtractedEntity],
    ) -> List[ExtractedEntity]:
        """Merged und dedupliziert Entities aus mehreren Chunks.

        Args:
            all_entities: Alle Entities aus allen Chunks

        Returns:
            Deduplizierte Entity-Liste
        """
        if not all_entities:
            return []

        # Gruppiere nach (type, normalized_value oder value)
        seen: Dict[Tuple[EntityType, str], ExtractedEntity] = {}

        for entity in all_entities:
            key = (entity.entity_type, entity.normalized_value or entity.value)

            if key in seen:
                # Behalte Entity mit hoeherer Confidence
                if entity.confidence > seen[key].confidence:
                    seen[key] = entity
            else:
                seen[key] = entity

        return list(seen.values())

    async def extract_entities(
        self,
        text: str,
        document_id: Optional[UUID] = None,
        entity_types: Optional[List[EntityType]] = None,
    ) -> NERResult:
        """Extrahiert Named Entities aus Text.

        Args:
            text: Zu analysierender Text
            document_id: Optionale Dokument-ID
            entity_types: Optionale Filterung auf bestimmte Entity-Typen

        Returns:
            NERResult mit extrahierten Entities
        """
        start_time = datetime.now(timezone.utc)

        if not text or not text.strip():
            return NERResult(
                document_id=document_id,
                entities=[],
                processing_time_ms=0,
                model_used=self._model,
                text_length=0,
            )

        logger.info(
            "ner_extraction_start",
            document_id=str(document_id) if document_id else None,
            text_length=len(text),
            model=self._model,
        )

        try:
            # Text in Chunks teilen wenn noetig
            chunks = self._chunk_text(text)
            all_entities: List[ExtractedEntity] = []

            for i, chunk in enumerate(chunks):
                # LLM-Anfrage vorbereiten
                messages = [
                    LLMMessage(role="system", content=NER_SYSTEM_PROMPT),
                    LLMMessage(
                        role="user",
                        content=f"Extrahiere alle relevanten Entitaeten aus diesem Text:\n\n{chunk}",
                    ),
                ]

                # LLM-Anfrage mit EXTRACTION-Kontext
                response = await self._llm_service.generate(
                    messages=messages,
                    model=self._model,
                    context_type=LLMContextType.EXTRACTION,
                    enable_thinking=False,  # Kein Thinking fuer strukturierte Ausgabe
                    temperature=0.1,  # Niedrig fuer konsistente Extraktion
                )

                # Response parsen
                entity_dicts = self._parse_llm_response(response.content)

                # Entities erstellen
                for entity_data in entity_dicts:
                    entity = self._create_entity(entity_data, chunk)
                    if entity:
                        all_entities.append(entity)

                logger.debug(
                    "chunk_processed",
                    chunk_index=i,
                    chunk_length=len(chunk),
                    entities_found=len(entity_dicts),
                )

            # Entities mergen und deduplizieren
            merged_entities = self._merge_chunk_entities(all_entities)

            # Optional: Nach Entity-Typ filtern
            if entity_types:
                merged_entities = [
                    e for e in merged_entities if e.entity_type in entity_types
                ]

            # Sortieren nach Position (falls vorhanden) oder Confidence
            merged_entities.sort(
                key=lambda e: (
                    e.position[0] if e.position else float("inf"),
                    -e.confidence,
                )
            )

            processing_time = int(
                (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            )

            result = NERResult(
                document_id=document_id,
                entities=merged_entities,
                processing_time_ms=processing_time,
                model_used=self._model,
                text_length=len(text),
            )

            logger.info(
                "ner_extraction_complete",
                document_id=str(document_id) if document_id else None,
                total_entities=len(merged_entities),
                processing_time_ms=processing_time,
                entity_breakdown={
                    "deadlines": len(result.deadlines),
                    "amounts": len(result.amounts),
                    "companies": len(result.companies),
                    "persons": len(result.persons),
                    "contract_numbers": len(result.contract_numbers),
                },
            )

            return result

        except Exception as e:
            processing_time = int(
                (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            )

            logger.exception(
                "ner_extraction_error",
                document_id=str(document_id) if document_id else None,
                error=str(e),
            )

            return NERResult(
                document_id=document_id,
                entities=[],
                processing_time_ms=processing_time,
                model_used=self._model,
                text_length=len(text),
                error=str(e),
            )

    async def extract_deadlines(
        self,
        text: str,
        document_id: Optional[UUID] = None,
    ) -> List[ExtractedEntity]:
        """Extrahiert nur Fristen/Deadlines aus Text.

        Convenience-Methode fuer Deadline-fokussierte Extraktion.

        Args:
            text: Zu analysierender Text
            document_id: Optionale Dokument-ID

        Returns:
            Liste von Deadline-Entities
        """
        result = await self.extract_entities(
            text=text,
            document_id=document_id,
            entity_types=[EntityType.DEADLINE, EntityType.DATE],
        )
        return result.deadlines

    async def extract_financial_info(
        self,
        text: str,
        document_id: Optional[UUID] = None,
    ) -> Dict[str, List[ExtractedEntity]]:
        """Extrahiert finanzrelevante Informationen.

        Args:
            text: Zu analysierender Text
            document_id: Optionale Dokument-ID

        Returns:
            Dictionary mit amounts, contract_numbers, ibans
        """
        result = await self.extract_entities(
            text=text,
            document_id=document_id,
            entity_types=[
                EntityType.AMOUNT,
                EntityType.CONTRACT_NUMBER,
                EntityType.IBAN,
            ],
        )

        return {
            "amounts": result.amounts,
            "contract_numbers": result.contract_numbers,
            "ibans": [e for e in result.entities if e.entity_type == EntityType.IBAN],
        }

    async def extract_contact_info(
        self,
        text: str,
        document_id: Optional[UUID] = None,
    ) -> Dict[str, List[ExtractedEntity]]:
        """Extrahiert Kontaktinformationen.

        Args:
            text: Zu analysierender Text
            document_id: Optionale Dokument-ID

        Returns:
            Dictionary mit companies, persons, addresses, phones, emails
        """
        result = await self.extract_entities(
            text=text,
            document_id=document_id,
            entity_types=[
                EntityType.COMPANY,
                EntityType.PERSON,
                EntityType.ADDRESS,
                EntityType.PHONE,
                EntityType.EMAIL,
            ],
        )

        return {
            "companies": result.companies,
            "persons": result.persons,
            "addresses": [
                e for e in result.entities if e.entity_type == EntityType.ADDRESS
            ],
            "phones": [
                e for e in result.entities if e.entity_type == EntityType.PHONE
            ],
            "emails": [
                e for e in result.entities if e.entity_type == EntityType.EMAIL
            ],
        }


# ============================================================================
# Singleton Pattern
# ============================================================================

_llm_ner_service: Optional[LLMNERService] = None
_llm_ner_service_lock = threading.Lock()


def get_llm_ner_service() -> LLMNERService:
    """Gibt die Singleton-Instanz des LLM NER Service zurueck.

    Returns:
        LLMNERService Singleton-Instanz
    """
    global _llm_ner_service

    if _llm_ner_service is None:
        with _llm_ner_service_lock:
            if _llm_ner_service is None:
                _llm_ner_service = LLMNERService()

    return _llm_ner_service
