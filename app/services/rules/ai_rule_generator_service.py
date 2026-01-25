# -*- coding: utf-8 -*-
"""KI-Regelgenerierung aus natuerlicher Sprache.

Vision 2.0 - Phase 2 (Januar 2026)

Generiert Business Rules aus natuerlichsprachlichen Beschreibungen
unter Verwendung von Ollama (lokaler LLM).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.ai.ollama_service import OllamaService, get_ollama_service

logger = logging.getLogger(__name__)


class GeneratedRule(BaseModel):
    """Eine KI-generierte Regel."""
    name: str
    description: str
    code: Optional[str] = None
    category: str = "custom"
    priority: int = 50
    condition: Dict[str, Any]
    actions: List[Dict[str, Any]]
    else_actions: Optional[List[Dict[str, Any]]] = None
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str  # Erklaerung warum diese Regel generiert wurde


class AIRuleGeneratorService:
    """Service zur KI-basierten Regelgenerierung.

    Nutzt Ollama (lokaler LLM) um aus natuerlichsprachlichen
    Beschreibungen strukturierte Business Rules zu generieren.
    """

    SYSTEM_PROMPT = """Du bist ein Experte fuer Geschaeftsregeln in einem deutschen Dokumentenmanagement-System.
Generiere JSON-Regeln basierend auf natuerlichsprachlichen Beschreibungen.

VERFUEGBARE FELDER fuer Bedingungen:
- amount: Betrag (numerisch, in EUR)
- document_type: Dokumenttyp (invoice, contract, receipt, order, delivery_note, quote, etc.)
- supplier.name: Lieferantenname (String)
- supplier.is_new: Ist neuer Lieferant (boolean)
- customer.name: Kundenname (String)
- due_date: Faelligkeitsdatum (ISO-Datum)
- invoice_date: Rechnungsdatum (ISO-Datum)
- created_at: Erstellungsdatum (ISO-Datum)
- status: Status (pending, approved, rejected, processed)
- tags: Tags (Liste von Strings)
- ocr_confidence: OCR-Konfidenz (0.0 bis 1.0)
- has_skonto: Hat Skonto-Bedingungen (boolean)
- skonto_deadline: Skonto-Frist (ISO-Datum)
- is_duplicate: Ist Duplikat (boolean)
- payment_terms: Zahlungsbedingungen (String)

VERFUEGBARE OPERATOREN:
- "==" (gleich), "!=" (ungleich)
- ">" (groesser), ">=" (groesser-gleich)
- "<" (kleiner), "<=" (kleiner-gleich)
- "contains", "not_contains" (String-Suche)
- "starts_with", "ends_with" (String-Anfang/Ende)
- "matches" (Regex-Pattern)
- "in", "not_in" (Liste-Zugehoerigkeit)
- "is_empty", "is_not_empty" (Leer-Pruefung)
- "is_null", "is_not_null" (Null-Pruefung)
- "before", "after" (Datum-Vergleich)
- "between" (Bereichs-Pruefung)
- "has_tag", "has_any_tag", "has_all_tags" (Tag-Pruefung)

VERFUEGBARE AKTIONEN:
- require_approval: Genehmigung anfordern
- require_cfo_approval: CFO-Genehmigung erforderlich
- require_manager_approval: Manager-Genehmigung erforderlich
- flag_for_review: Zur Pruefung markieren
- manual_review_required: Manuelle Pruefung erforderlich
- notify_user: Benutzer benachrichtigen (params: {"user_id": "uuid"})
- notify_team: Team benachrichtigen (params: {"team_id": "uuid"})
- notify_admin: Admin benachrichtigen
- send_email: E-Mail senden (params: {"to": "email", "subject": "...", "body": "..."})
- send_slack: Slack-Nachricht (params: {"channel": "...", "message": "..."})
- add_tag: Tag hinzufuegen (params: {"tag": "name"})
- remove_tag: Tag entfernen (params: {"tag": "name"})
- set_status: Status setzen (params: {"status": "pending|approved|rejected"})
- set_priority: Prioritaet setzen (params: {"priority": 1-5})
- start_workflow: Workflow starten (params: {"workflow_id": "uuid"})
- assign_to_user: Benutzer zuweisen (params: {"user_id": "uuid"})
- block_processing: Verarbeitung blockieren

KATEGORIEN: approval, compliance, fraud, workflow, notification, data_quality, custom

BEISPIELE:

Prompt: "Erstelle Regel fuer Skonto-Ueberwachung"
Antwort:
{
    "name": "Skonto-Frist Warnung",
    "description": "Benachrichtigt bei ablaufenden Skonto-Fristen",
    "category": "notification",
    "priority": 75,
    "condition": {
        "and": [
            {"field": "has_skonto", "op": "==", "value": true},
            {"field": "skonto_deadline", "op": "between", "value": ["today", "today+3d"]}
        ]
    },
    "actions": [
        {"type": "notify_admin", "params": {}},
        {"type": "add_tag", "params": {"tag": "skonto-ablauf"}}
    ],
    "confidence": 0.9,
    "explanation": "Warnt rechtzeitig vor Skonto-Ablauf (3 Tage Vorlauf)"
}

Prompt: "Rechnungen ueber 10000 EUR muessen vom CFO genehmigt werden"
Antwort:
{
    "name": "Hohe Rechnungen CFO-Genehmigung",
    "description": "Rechnungen ab 10.000 EUR erfordern CFO-Freigabe",
    "category": "approval",
    "priority": 90,
    "condition": {
        "and": [
            {"field": "document_type", "op": "==", "value": "invoice"},
            {"field": "amount", "op": ">=", "value": 10000}
        ]
    },
    "actions": [
        {"type": "require_cfo_approval", "params": {}},
        {"type": "set_priority", "params": {"priority": 5}}
    ],
    "confidence": 0.95,
    "explanation": "Vier-Augen-Prinzip fuer hohe Betraege"
}

WICHTIG:
- Antworte NUR mit validem JSON im gegebenen Format
- Verwende deutsche Beschreibungen
- Waehle realistische confidence-Werte
- Bei komplexen Bedingungen nutze "and" / "or" Komposition
- Erklaere IMMER warum die Regel sinnvoll ist
"""

    def __init__(self, ollama_service: OllamaService):
        """Initialisiert den AI Rule Generator.

        Args:
            ollama_service: Ollama Service Instanz
        """
        self.ollama = ollama_service

    async def generate_rule(self, prompt: str) -> GeneratedRule:
        """Generiert eine Regel aus natuerlicher Sprache.

        Args:
            prompt: Natuerlichsprachliche Beschreibung der gewuenschten Regel

        Returns:
            GeneratedRule mit strukturierter Regel-Definition

        Raises:
            ValueError: Wenn kein gueltiges JSON generiert werden konnte
            Exception: Bei Ollama-Service-Fehlern
        """
        logger.info(f"Generiere Regel aus Prompt: {prompt[:100]}...")

        user_message = f"Erstelle eine Geschaeftsregel fuer: {prompt}"

        try:
            # Ollama mit niedriger Temperatur fuer konsistente Struktur
            response = await self.ollama.generate(
                prompt=user_message,
                system_prompt=self.SYSTEM_PROMPT,
                temperature=0.3,
                format_json=True,
            )

            logger.debug(f"Ollama Response: {response[:200]}...")

            # JSON aus Antwort extrahieren
            rule_json = self._extract_json(response)

            # Validieren und zurueckgeben
            generated = GeneratedRule(**rule_json)

            logger.info(
                f"Regel erfolgreich generiert: {generated.name} "
                f"(Confidence: {generated.confidence:.2f})"
            )

            return generated

        except Exception as e:
            logger.error(f"Fehler bei Regel-Generierung: {e}", exc_info=True)
            raise

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """Extrahiert JSON aus LLM-Antwort.

        Args:
            text: Ollama Response-Text

        Returns:
            Geparste JSON-Struktur

        Raises:
            ValueError: Wenn kein gueltiges JSON gefunden wurde
        """
        # Versuche direktes Parsing
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass

        # Suche nach JSON-Block in Markdown
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Suche nach erstem { bis letztem }
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end+1])
            except json.JSONDecodeError:
                pass

        # Letzte Option: Multi-Line Matching
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        raise ValueError(
            f"Konnte kein gueltiges JSON aus Antwort extrahieren. "
            f"Response: {text[:200]}..."
        )


async def get_ai_rule_generator_service() -> AIRuleGeneratorService:
    """Factory fuer AIRuleGeneratorService.

    Returns:
        AIRuleGeneratorService Instanz
    """
    ollama = get_ollama_service()

    # Verfuegbarkeit pruefen
    if not await ollama.is_available():
        logger.warning("Ollama nicht verfuegbar - Rule Generator wird fehlschlagen")

    return AIRuleGeneratorService(ollama)
