# -*- coding: utf-8 -*-
"""Tests fuer AI Rule Generator Service.

Vision 2.0 - Phase 2 (Januar 2026)
"""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.services.rules.ai_rule_generator_service import (
    AIRuleGeneratorService,
    GeneratedRule,
)


class TestAIRuleGeneratorService:
    """Tests fuer AIRuleGeneratorService."""

    @pytest.fixture
    def mock_ollama_service(self):
        """Mock Ollama Service."""
        mock = AsyncMock()
        mock.generate = AsyncMock()
        return mock

    @pytest.fixture
    def service(self, mock_ollama_service):
        """Service-Instanz mit Mock Ollama."""
        return AIRuleGeneratorService(mock_ollama_service)

    @pytest.mark.asyncio
    async def test_generate_rule_success(self, service, mock_ollama_service):
        """Test: Erfolgreiche Regel-Generierung."""
        # Arrange
        prompt = "Rechnungen ueber 10000 EUR muessen vom CFO genehmigt werden"

        ollama_response = json.dumps({
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
        })

        mock_ollama_service.generate.return_value = ollama_response

        # Act
        result = await service.generate_rule(prompt)

        # Assert
        assert isinstance(result, GeneratedRule)
        assert result.name == "Hohe Rechnungen CFO-Genehmigung"
        assert result.category == "approval"
        assert result.priority == 90
        assert result.confidence == 0.95
        assert "and" in result.condition
        assert len(result.actions) == 2

        # Ollama wurde korrekt aufgerufen
        mock_ollama_service.generate.assert_called_once()
        call_args = mock_ollama_service.generate.call_args
        assert "Erstelle eine Geschaeftsregel fuer" in call_args.kwargs["prompt"]
        assert call_args.kwargs["temperature"] == 0.3
        assert call_args.kwargs["format_json"] is True

    @pytest.mark.asyncio
    async def test_generate_rule_with_markdown_json(self, service, mock_ollama_service):
        """Test: JSON-Extraktion aus Markdown-Block."""
        # Arrange
        prompt = "Skonto-Warnung"

        # LLM gibt JSON in Markdown-Block zurueck
        ollama_response = """
Hier ist die generierte Regel:

```json
{
    "name": "Skonto-Frist Warnung",
    "description": "Benachrichtigt bei ablaufenden Skonto-Fristen",
    "category": "notification",
    "priority": 75,
    "condition": {"field": "has_skonto", "op": "==", "value": true},
    "actions": [{"type": "notify_admin", "params": {}}],
    "confidence": 0.85,
    "explanation": "Rechtzeitige Warnung vor Ablauf"
}
```
"""

        mock_ollama_service.generate.return_value = ollama_response

        # Act
        result = await service.generate_rule(prompt)

        # Assert
        assert result.name == "Skonto-Frist Warnung"
        assert result.category == "notification"
        assert result.confidence == 0.85

    @pytest.mark.asyncio
    async def test_generate_rule_with_else_actions(self, service, mock_ollama_service):
        """Test: Regel mit else_actions."""
        # Arrange
        prompt = "Neue Lieferanten zur Pruefung"

        ollama_response = json.dumps({
            "name": "Neue Lieferanten Review",
            "description": "Neue Lieferanten zur manuellen Pruefung",
            "category": "compliance",
            "priority": 80,
            "condition": {"field": "supplier.is_new", "op": "==", "value": True},
            "actions": [
                {"type": "flag_for_review", "params": {}},
                {"type": "add_tag", "params": {"tag": "neuer-lieferant"}}
            ],
            "else_actions": [
                {"type": "add_tag", "params": {"tag": "bekannter-lieferant"}}
            ],
            "confidence": 0.88,
            "explanation": "KYC fuer neue Geschaeftspartner"
        })

        mock_ollama_service.generate.return_value = ollama_response

        # Act
        result = await service.generate_rule(prompt)

        # Assert
        assert result.name == "Neue Lieferanten Review"
        assert len(result.actions) == 2
        assert result.else_actions is not None
        assert len(result.else_actions) == 1
        assert result.else_actions[0]["type"] == "add_tag"

    @pytest.mark.asyncio
    async def test_generate_rule_invalid_json(self, service, mock_ollama_service):
        """Test: Fehlerbehandlung bei ungueltigem JSON."""
        # Arrange
        prompt = "Test"
        mock_ollama_service.generate.return_value = "Das ist kein JSON!"

        # Act & Assert
        with pytest.raises(ValueError, match="Konnte kein gueltiges JSON"):
            await service.generate_rule(prompt)

    @pytest.mark.asyncio
    async def test_generate_rule_complex_condition(self, service, mock_ollama_service):
        """Test: Komplexe verschachtelte Bedingung."""
        # Arrange
        prompt = "Duplikate mit niedriger OCR-Konfidenz blockieren"

        ollama_response = json.dumps({
            "name": "Duplikat-Blocker",
            "description": "Blockiert verdaechtige Duplikate",
            "category": "fraud",
            "priority": 100,
            "condition": {
                "and": [
                    {"field": "is_duplicate", "op": "==", "value": True},
                    {
                        "or": [
                            {"field": "ocr_confidence", "op": "<", "value": 0.8},
                            {"field": "supplier.is_new", "op": "==", "value": True}
                        ]
                    }
                ]
            },
            "actions": [
                {"type": "block_processing", "params": {}},
                {"type": "manual_review_required", "params": {}}
            ],
            "confidence": 0.92,
            "explanation": "Schutz vor Duplikat-Betrug mit niedriger OCR-Qualitaet"
        })

        mock_ollama_service.generate.return_value = ollama_response

        # Act
        result = await service.generate_rule(prompt)

        # Assert
        assert result.category == "fraud"
        assert result.priority == 100
        assert "and" in result.condition
        assert "or" in result.condition["and"][1]

    @pytest.mark.asyncio
    async def test_extract_json_direct(self, service):
        """Test: _extract_json direktes JSON."""
        # Arrange
        json_text = '{"name": "Test", "value": 123}'

        # Act
        result = service._extract_json(json_text)

        # Assert
        assert result["name"] == "Test"
        assert result["value"] == 123

    @pytest.mark.asyncio
    async def test_extract_json_with_whitespace(self, service):
        """Test: _extract_json mit Whitespace."""
        # Arrange
        json_text = '\n\n  {"name": "Test"}  \n'

        # Act
        result = service._extract_json(json_text)

        # Assert
        assert result["name"] == "Test"

    @pytest.mark.asyncio
    async def test_extract_json_from_text(self, service):
        """Test: _extract_json aus Text extrahieren."""
        # Arrange
        text = 'Hier ist das Ergebnis: {"name": "Test", "ok": true} und mehr Text'

        # Act
        result = service._extract_json(text)

        # Assert
        assert result["name"] == "Test"
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_extract_json_multiline(self, service):
        """Test: _extract_json mehrzeilig."""
        # Arrange
        text = """
        Antwort:
        {
            "name": "Multi",
            "nested": {
                "value": 42
            }
        }
        Ende
        """

        # Act
        result = service._extract_json(text)

        # Assert
        assert result["name"] == "Multi"
        assert result["nested"]["value"] == 42

    @pytest.mark.asyncio
    async def test_generate_rule_ollama_error(self, service, mock_ollama_service):
        """Test: Ollama Service Fehler."""
        # Arrange
        prompt = "Test"
        mock_ollama_service.generate.side_effect = Exception("Ollama nicht erreichbar")

        # Act & Assert
        with pytest.raises(Exception, match="Ollama nicht erreichbar"):
            await service.generate_rule(prompt)

    @pytest.mark.asyncio
    async def test_generate_rule_confidence_validation(self, service, mock_ollama_service):
        """Test: Confidence wird validiert (0.0-1.0)."""
        # Arrange
        prompt = "Test"

        # Ungueltige Confidence (>1.0)
        ollama_response = json.dumps({
            "name": "Test",
            "description": "Test",
            "category": "custom",
            "priority": 50,
            "condition": {"field": "amount", "op": ">", "value": 100},
            "actions": [{"type": "notify_admin", "params": {}}],
            "confidence": 1.5,  # UNGUELTIG
            "explanation": "Test"
        })

        mock_ollama_service.generate.return_value = ollama_response

        # Act & Assert
        with pytest.raises(Exception):  # Pydantic ValidationError
            await service.generate_rule(prompt)
