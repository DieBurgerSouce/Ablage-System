"""Ollama Service fuer lokale LLM Integration.

Enterprise Feature: On-Premises KI ohne Cloud-Abhaengigkeiten mit:
- Named Entity Recognition (NER) fuer deutsche Texte
- Vertragsanalyse (Laufzeiten, Kuendigungsfristen)
- Dokumentenkategorisierung
- Textextraktion und -zusammenfassung
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Optional, Union

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class OllamaConfig:
    """Konfiguration fuer Ollama Service."""

    base_url: str = "http://localhost:11434"
    default_model: str = "mistral"
    timeout: float = 120.0
    max_retries: int = 3
    temperature: float = 0.1  # Niedrig fuer konsistente Ergebnisse


@dataclass
class ExtractedEntities:
    """Ergebnis der Named Entity Recognition."""

    persons: list[str]
    organizations: list[str]
    locations: list[str]
    money_amounts: list[str]
    dates: list[str]
    contract_numbers: list[str]
    raw_response: Optional[dict[str, Union[str, list[str], int, float, bool, None]]] = None


@dataclass
class ContractAnalysis:
    """Ergebnis der Vertragsanalyse."""

    start_date: Optional[str] = None
    end_date: Optional[str] = None
    notice_period_days: Optional[int] = None
    parties: list[str] = None
    payment_terms: Optional[str] = None
    milestones: list[dict[str, str]] = None
    auto_renewal: bool = False
    contract_type: Optional[str] = None
    raw_response: Optional[dict[str, Union[str, list[str], int, float, bool, None]]] = None

    def __post_init__(self):
        if self.parties is None:
            self.parties = []
        if self.milestones is None:
            self.milestones = []


class OllamaService:
    """Service fuer lokale LLM-Integration mit Ollama.

    Verwendet lokale Sprachmodelle fuer NER, Vertragsanalyse
    und Dokumentenkategorisierung - komplett ohne Cloud-Abhaengigkeiten.
    """

    def __init__(self, config: Optional[OllamaConfig] = None) -> None:
        """Initialisiert den Ollama Service.

        Args:
            config: Optionale Konfiguration
        """
        self.config = config or OllamaConfig()

        # Versuche aus Settings zu laden
        try:
            self.config.base_url = getattr(
                settings, "OLLAMA_BASE_URL", self.config.base_url
            )
            self.config.default_model = getattr(
                settings, "OLLAMA_MODEL", self.config.default_model
            )
        except Exception as e:
            logger.debug(
                "ollama_settings_override_failed: %s", type(e).__name__
            )

        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Holt oder erstellt den HTTP-Client.

        Returns:
            Async HTTP Client
        """
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=httpx.Timeout(self.config.timeout),
            )
        return self._client

    async def close(self) -> None:
        """Schliesst den HTTP-Client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def is_available(self) -> bool:
        """Prueft ob Ollama verfuegbar ist.

        Returns:
            True wenn Ollama laeuft
        """
        try:
            client = await self._get_client()
            response = await client.get("/api/tags")
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Ollama nicht verfuegbar: {e}")
            return False

    async def list_models(self) -> list[str]:
        """Listet alle verfuegbaren Modelle.

        Returns:
            Liste der Modellnamen
        """
        try:
            client = await self._get_client()
            response = await client.get("/api/tags")
            response.raise_for_status()

            data = response.json()
            return [model["name"] for model in data.get("models", [])]
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Modelle: {e}")
            return []

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        format_json: bool = False,
    ) -> str:
        """Generiert Text mit dem LLM.

        Args:
            prompt: Der Benutzer-Prompt
            model: Modellname (Standard: default_model)
            system_prompt: Optionaler System-Prompt
            temperature: Temperatur fuer Sampling
            format_json: JSON-Ausgabe erzwingen

        Returns:
            Generierter Text

        Raises:
            Exception: Bei Verbindungs- oder Generierungsfehlern
        """
        model = model or self.config.default_model
        temperature = temperature if temperature is not None else self.config.temperature

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "options": {"temperature": temperature},
            "stream": False,
        }

        if format_json:
            payload["format"] = "json"

        client = await self._get_client()

        for attempt in range(self.config.max_retries):
            try:
                response = await client.post("/api/chat", json=payload)
                response.raise_for_status()

                data = response.json()
                return data.get("message", {}).get("content", "")

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP-Fehler bei Ollama (Versuch {attempt + 1}): {e}")
                if attempt == self.config.max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)

            except httpx.RequestError as e:
                logger.error(f"Verbindungsfehler zu Ollama (Versuch {attempt + 1}): {e}")
                if attempt == self.config.max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)

        return ""

    async def extract_entities(self, text: str) -> ExtractedEntities:
        """Extrahiert Named Entities aus deutschem Text.

        Args:
            text: Der zu analysierende Text

        Returns:
            ExtractedEntities mit allen gefundenen Entitaeten
        """
        system_prompt = """Du bist ein NER-System fuer deutsche Texte.
Extrahiere folgende Entitaeten und gib sie als JSON zurueck:

{
    "persons": ["Liste von Personennamen"],
    "organizations": ["Liste von Organisationen/Firmen"],
    "locations": ["Liste von Orten/Adressen"],
    "money_amounts": ["Liste von Geldbetraegen mit Waehrung"],
    "dates": ["Liste von Datumsangaben"],
    "contract_numbers": ["Liste von Vertragsnummern/Referenzen"]
}

Regeln:
- Extrahiere NUR Entitaeten die tatsaechlich im Text vorkommen
- Geldbetraege immer mit Waehrung (z.B. "1.500,00 EUR")
- Daten im deutschen Format (TT.MM.JJJJ)
- Leere Listen fuer nicht gefundene Kategorien

Antworte NUR mit dem JSON-Objekt, keine Erklaerungen."""

        prompt = f"Extrahiere Entitaeten aus folgendem Text:\n\n{text}"

        try:
            response = await self.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.1,
                format_json=True,
            )

            # JSON parsen
            try:
                data = json.loads(response)
            except json.JSONDecodeError:
                # Versuche JSON aus Antwort zu extrahieren
                import re
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group())
                else:
                    data = {}

            return ExtractedEntities(
                persons=data.get("persons", []),
                organizations=data.get("organizations", []),
                locations=data.get("locations", []),
                money_amounts=data.get("money_amounts", []),
                dates=data.get("dates", []),
                contract_numbers=data.get("contract_numbers", []),
                raw_response=data,
            )

        except Exception as e:
            logger.error(f"Fehler bei NER-Extraktion: {e}")
            return ExtractedEntities(
                persons=[],
                organizations=[],
                locations=[],
                money_amounts=[],
                dates=[],
                contract_numbers=[],
            )

    async def analyze_contract(self, text: str) -> ContractAnalysis:
        """Analysiert einen Vertragstext.

        Args:
            text: Der Vertragstext (begrenzt auf ca. 4000 Zeichen)

        Returns:
            ContractAnalysis mit extrahierten Details
        """
        # Text limitieren um Token-Limit zu respektieren
        max_chars = 4000
        if len(text) > max_chars:
            text = text[:max_chars] + "..."

        system_prompt = """Du bist ein Vertragsanalyst. Extrahiere aus dem Vertrag folgende Informationen als JSON:

{
    "start_date": "Vertragsbeginn (TT.MM.JJJJ oder null)",
    "end_date": "Vertragsende (TT.MM.JJJJ oder null)",
    "notice_period_days": "Kuendigungsfrist in Tagen (Zahl oder null)",
    "parties": ["Liste der Vertragsparteien"],
    "payment_terms": "Zahlungsbedingungen als Text oder null",
    "milestones": [{"date": "Datum", "description": "Beschreibung"}],
    "auto_renewal": true/false,
    "contract_type": "Vertragstyp (Mietvertrag, Kaufvertrag, Dienstleistung, etc.)"
}

Regeln:
- Nutze null fuer nicht gefundene Informationen
- Kuendigungsfrist in Tagen umrechnen (3 Monate = 90 Tage)
- auto_renewal auf true wenn automatische Verlaengerung erwaehnt wird
- Leere Listen fuer nicht gefundene Arrays

Antworte NUR mit dem JSON-Objekt."""

        prompt = f"Analysiere folgenden Vertrag:\n\n{text}"

        try:
            response = await self.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.1,
                format_json=True,
            )

            # JSON parsen
            try:
                data = json.loads(response)
            except json.JSONDecodeError:
                import re
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group())
                else:
                    data = {}

            return ContractAnalysis(
                start_date=data.get("start_date"),
                end_date=data.get("end_date"),
                notice_period_days=data.get("notice_period_days"),
                parties=data.get("parties", []),
                payment_terms=data.get("payment_terms"),
                milestones=data.get("milestones", []),
                auto_renewal=data.get("auto_renewal", False),
                contract_type=data.get("contract_type"),
                raw_response=data,
            )

        except Exception as e:
            logger.error(f"Fehler bei Vertragsanalyse: {e}")
            return ContractAnalysis()

    async def categorize_document(
        self,
        text: str,
        available_categories: list[str],
    ) -> tuple[str, float]:
        """Kategorisiert ein Dokument.

        Args:
            text: Der Dokumententext
            available_categories: Liste der moeglichen Kategorien

        Returns:
            Tuple aus (Kategorie, Konfidenz 0.0-1.0)
        """
        if not available_categories:
            return ("unknown", 0.0)

        # Text limitieren
        max_chars = 2000
        if len(text) > max_chars:
            text = text[:max_chars] + "..."

        categories_str = ", ".join(available_categories)

        system_prompt = f"""Du bist ein Dokumenten-Kategorisierer.
Verfuegbare Kategorien: {categories_str}

Waehle die passendste Kategorie fuer das Dokument und gib deine Antwort als JSON:

{{
    "category": "gewaehlte Kategorie",
    "confidence": 0.0 bis 1.0,
    "reasoning": "Kurze Begruendung"
}}

WICHTIG: Die Kategorie MUSS eine aus der Liste sein!
Antworte NUR mit dem JSON-Objekt."""

        prompt = f"Kategorisiere folgendes Dokument:\n\n{text}"

        try:
            response = await self.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.1,
                format_json=True,
            )

            try:
                data = json.loads(response)
            except json.JSONDecodeError:
                import re
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group())
                else:
                    return (available_categories[0], 0.5)

            category = data.get("category", available_categories[0])
            confidence = float(data.get("confidence", 0.5))

            # Validieren dass Kategorie in Liste ist
            if category not in available_categories:
                # Fuzzy match versuchen
                category_lower = category.lower()
                for cat in available_categories:
                    if cat.lower() in category_lower or category_lower in cat.lower():
                        category = cat
                        break
                else:
                    category = available_categories[0]
                    confidence = 0.3

            return (category, min(max(confidence, 0.0), 1.0))

        except Exception as e:
            logger.error(f"Fehler bei Dokumentenkategorisierung: {e}")
            return (available_categories[0], 0.3)

    async def summarize(
        self,
        text: str,
        max_sentences: int = 3,
        language: str = "de",
    ) -> str:
        """Fasst einen Text zusammen.

        Args:
            text: Der zu zusammenfassende Text
            max_sentences: Maximale Anzahl Saetze
            language: Sprache der Zusammenfassung

        Returns:
            Zusammenfassung als String
        """
        # Text limitieren
        max_chars = 4000
        if len(text) > max_chars:
            text = text[:max_chars] + "..."

        lang_instruction = "auf Deutsch" if language == "de" else "in English"

        system_prompt = f"""Du fasst Texte {lang_instruction} zusammen.
Erstelle eine praegnante Zusammenfassung in maximal {max_sentences} Saetzen.
Behalte die wichtigsten Informationen bei.
Antworte NUR mit der Zusammenfassung, keine Einleitung."""

        prompt = f"Fasse folgenden Text zusammen:\n\n{text}"

        try:
            response = await self.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.3,
            )
            return response.strip()

        except Exception as e:
            logger.error(f"Fehler bei Textzusammenfassung: {e}")
            # Fallback: Erste X Zeichen
            return text[:200] + "..." if len(text) > 200 else text

    async def extract_key_value_pairs(
        self,
        text: str,
        expected_keys: Optional[list[str]] = None,
    ) -> dict[str, str]:
        """Extrahiert Schluessel-Wert-Paare aus Text.

        Args:
            text: Der zu analysierende Text
            expected_keys: Optionale Liste erwarteter Schluessel

        Returns:
            Dict mit extrahierten Schluessel-Wert-Paaren
        """
        max_chars = 3000
        if len(text) > max_chars:
            text = text[:max_chars] + "..."

        keys_hint = ""
        if expected_keys:
            keys_hint = f"\nErwartete Schluessel (falls vorhanden): {', '.join(expected_keys)}"

        system_prompt = f"""Du extrahierst Schluessel-Wert-Paare aus Dokumenten.
{keys_hint}

Gib das Ergebnis als JSON-Objekt zurueck:
{{
    "schluessel1": "wert1",
    "schluessel2": "wert2"
}}

Regeln:
- Verwende deutsche Schluesselnamen
- Werte als Strings
- Leeres Objekt {{}} wenn nichts gefunden
- Extrahiere nur explizit genannte Werte

Antworte NUR mit dem JSON-Objekt."""

        prompt = f"Extrahiere Schluessel-Wert-Paare:\n\n{text}"

        try:
            response = await self.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.1,
                format_json=True,
            )

            try:
                return json.loads(response)
            except json.JSONDecodeError:
                import re
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
                return {}

        except Exception as e:
            logger.error(f"Fehler bei Key-Value-Extraktion: {e}")
            return {}

    async def answer_question(
        self,
        context: str,
        question: str,
    ) -> str:
        """Beantwortet eine Frage basierend auf Kontext.

        Args:
            context: Der Kontext/Dokumenteninhalt
            question: Die zu beantwortende Frage

        Returns:
            Antwort als String
        """
        max_chars = 4000
        if len(context) > max_chars:
            context = context[:max_chars] + "..."

        system_prompt = """Du beantwortest Fragen basierend auf dem gegebenen Kontext.

Regeln:
- Antworte NUR basierend auf dem Kontext
- Sage "Diese Information ist im Dokument nicht enthalten" wenn die Antwort nicht im Kontext steht
- Antworte auf Deutsch
- Sei praezise und direkt"""

        prompt = f"""Kontext:
{context}

Frage: {question}

Antwort:"""

        try:
            response = await self.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.3,
            )
            return response.strip()

        except Exception as e:
            logger.error(f"Fehler bei Fragebeantwortung: {e}")
            return "Entschuldigung, die Frage konnte nicht beantwortet werden."


# Singleton-Instanz
_ollama_service: Optional[OllamaService] = None


def get_ollama_service() -> OllamaService:
    """Holt oder erstellt die Singleton-Instanz.

    Returns:
        OllamaService Instanz
    """
    global _ollama_service
    if _ollama_service is None:
        _ollama_service = OllamaService()
    return _ollama_service
