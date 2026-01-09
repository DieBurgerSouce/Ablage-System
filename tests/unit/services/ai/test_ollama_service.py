"""Tests fuer den Ollama Service.

Testet die lokale LLM Integration:
- Textgenerierung
- Named Entity Recognition (NER)
- Vertragsanalyse
- Kategorisierung
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import HTTPStatusError, Response

from app.services.ai.ollama_service import OllamaService, OllamaConfig


class TestOllamaGeneration:
    """Tests fuer Textgenerierung."""

    @pytest.fixture
    def service(self) -> OllamaService:
        config = OllamaConfig(base_url="http://localhost:11434")
        return OllamaService(config=config)

    @pytest.mark.asyncio
    async def test_generate_basic_text(self, service: OllamaService) -> None:
        """Einfache Textgenerierung funktioniert."""
        mock_response = {
            "message": {
                "content": "Das ist eine Testantwort."
            }
        }

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = MagicMock(
                json=lambda: mock_response,
                raise_for_status=lambda: None
            )

            result = await service.generate("Test prompt")

            assert result == "Das ist eine Testantwort."
            mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_with_system_prompt(self, service: OllamaService) -> None:
        """Generierung mit System-Prompt funktioniert."""
        mock_response = {
            "message": {
                "content": "Strukturierte Antwort"
            }
        }

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = MagicMock(
                json=lambda: mock_response,
                raise_for_status=lambda: None
            )

            result = await service.generate(
                "Test prompt",
                system_prompt="Du bist ein Assistent."
            )

            # Verify system prompt was included
            call_args = mock_post.call_args
            request_body = call_args.kwargs["json"]
            assert len(request_body["messages"]) == 2
            assert request_body["messages"][0]["role"] == "system"

    @pytest.mark.asyncio
    async def test_generate_with_custom_model(self, service: OllamaService) -> None:
        """Generierung mit benutzerdefiniertem Model funktioniert."""
        mock_response = {
            "message": {
                "content": "Antwort vom custom model"
            }
        }

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = MagicMock(
                json=lambda: mock_response,
                raise_for_status=lambda: None
            )

            await service.generate("Test", model="neural-chat")

            call_args = mock_post.call_args
            request_body = call_args.kwargs["json"]
            assert request_body["model"] == "neural-chat"

    @pytest.mark.asyncio
    async def test_generate_with_temperature(self, service: OllamaService) -> None:
        """Temperatur-Parameter wird uebergeben."""
        mock_response = {
            "message": {
                "content": "Antwort"
            }
        }

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = MagicMock(
                json=lambda: mock_response,
                raise_for_status=lambda: None
            )

            await service.generate("Test", temperature=0.1)

            call_args = mock_post.call_args
            request_body = call_args.kwargs["json"]
            assert request_body["options"]["temperature"] == 0.1


class TestEntityExtraction:
    """Tests fuer Named Entity Recognition."""

    @pytest.fixture
    def service(self) -> OllamaService:
        config = OllamaConfig(base_url="http://localhost:11434")
        return OllamaService(config=config)

    @pytest.mark.asyncio
    async def test_extract_entities_person(self, service: OllamaService) -> None:
        """Personen werden erkannt."""
        mock_json_response = json.dumps({
            "persons": ["Max Mustermann", "Erika Musterfrau"],
            "organizations": [],
            "locations": [],
            "money_amounts": [],
            "dates": [],
            "contract_numbers": []
        })

        with patch.object(service, "generate", return_value=mock_json_response):
            result = await service.extract_entities(
                "Max Mustermann und Erika Musterfrau haben den Vertrag unterzeichnet."
            )

            assert "Max Mustermann" in result.persons
            assert "Erika Musterfrau" in result.persons

    @pytest.mark.asyncio
    async def test_extract_entities_organization(self, service: OllamaService) -> None:
        """Organisationen werden erkannt."""
        mock_json_response = json.dumps({
            "persons": [],
            "organizations": ["Deutsche Bank AG", "Telekom"],
            "locations": [],
            "money_amounts": [],
            "dates": [],
            "contract_numbers": []
        })

        with patch.object(service, "generate", return_value=mock_json_response):
            result = await service.extract_entities(
                "Die Deutsche Bank AG und die Telekom haben kooperiert."
            )

            assert "Deutsche Bank AG" in result.organizations

    @pytest.mark.asyncio
    async def test_extract_entities_money(self, service: OllamaService) -> None:
        """Geldbetraege werden erkannt."""
        mock_json_response = json.dumps({
            "persons": [],
            "organizations": [],
            "locations": [],
            "money_amounts": ["50.000 EUR", "1.500,00 €"],
            "dates": [],
            "contract_numbers": []
        })

        with patch.object(service, "generate", return_value=mock_json_response):
            result = await service.extract_entities(
                "Der Betrag von 50.000 EUR wurde ueberwiesen. Restbetrag: 1.500,00 €"
            )

            assert len(result.money_amounts) == 2

    @pytest.mark.asyncio
    async def test_extract_entities_date(self, service: OllamaService) -> None:
        """Datumsangaben werden erkannt."""
        mock_json_response = json.dumps({
            "persons": [],
            "organizations": [],
            "locations": [],
            "money_amounts": [],
            "dates": ["15.03.2024", "Ende 2025"],
            "contract_numbers": []
        })

        with patch.object(service, "generate", return_value=mock_json_response):
            result = await service.extract_entities(
                "Der Vertrag laeuft vom 15.03.2024 bis Ende 2025."
            )

            assert "15.03.2024" in result.dates


class TestContractAnalysis:
    """Tests fuer Vertragsanalyse."""

    @pytest.fixture
    def service(self) -> OllamaService:
        config = OllamaConfig(base_url="http://localhost:11434")
        return OllamaService(config=config)

    @pytest.mark.asyncio
    async def test_analyze_contract_basic(self, service: OllamaService) -> None:
        """Grundlegende Vertragsanalyse funktioniert."""
        mock_json_response = json.dumps({
            "start_date": "2024-01-01",
            "end_date": "2025-12-31",
            "notice_period_days": 90,
            "parties": ["Musterfirma GmbH", "Max Mustermann"],
            "payment_terms": "30 Tage netto",
            "auto_renewal": True
        })

        with patch.object(service, "generate", return_value=mock_json_response):
            result = await service.analyze_contract(
                "Vertrag zwischen Musterfirma GmbH und Max Mustermann..."
            )

            assert result.start_date == "2024-01-01"
            assert result.end_date == "2025-12-31"
            assert result.notice_period_days == 90
            assert result.auto_renewal is True

    @pytest.mark.asyncio
    async def test_analyze_contract_parties(self, service: OllamaService) -> None:
        """Vertragsparteien werden erkannt."""
        mock_json_response = json.dumps({
            "parties": ["ABC GmbH", "XYZ AG"],
            "start_date": None,
            "end_date": None,
            "notice_period_days": None,
            "payment_terms": None,
            "auto_renewal": False
        })

        with patch.object(service, "generate", return_value=mock_json_response):
            result = await service.analyze_contract(
                "Zwischen ABC GmbH (nachfolgend Auftraggeber) und XYZ AG..."
            )

            assert len(result.parties) == 2
            assert "ABC GmbH" in result.parties

    @pytest.mark.asyncio
    async def test_analyze_contract_milestones(self, service: OllamaService) -> None:
        """Meilensteine werden erkannt."""
        mock_json_response = json.dumps({
            "parties": [],
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "notice_period_days": 30,
            "payment_terms": "Bei Meilenstein",
            "milestones": [
                {"date": "2024-03-31", "description": "Phase 1 abgeschlossen"},
                {"date": "2024-06-30", "description": "Phase 2 abgeschlossen"},
            ],
            "auto_renewal": False
        })

        with patch.object(service, "generate", return_value=mock_json_response):
            result = await service.analyze_contract(
                "Meilensteine: Phase 1 bis 31.03.2024, Phase 2 bis 30.06.2024..."
            )

            assert result.milestones is not None
            assert len(result.milestones) == 2


class TestErrorHandling:
    """Tests fuer Fehlerbehandlung."""

    @pytest.fixture
    def service(self) -> OllamaService:
        config = OllamaConfig(base_url="http://localhost:11434")
        return OllamaService(config=config)

    @pytest.mark.asyncio
    async def test_connection_error_handling(self, service: OllamaService) -> None:
        """Verbindungsfehler werden behandelt."""
        import httpx

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.side_effect = httpx.ConnectError("Connection refused")

            with pytest.raises(Exception) as exc_info:
                await service.generate("Test")

            assert "Connection" in str(exc_info.value) or "connect" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_timeout_handling(self, service: OllamaService) -> None:
        """Timeouts werden behandelt."""
        import httpx

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.side_effect = httpx.TimeoutException("Request timeout")

            with pytest.raises(Exception) as exc_info:
                await service.generate("Test")

            assert "timeout" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_invalid_json_response(self, service: OllamaService) -> None:
        """Ungueltige JSON-Antworten werden graceful behandelt."""
        # Mock generate als AsyncMock da es eine async Methode ist
        with patch.object(
            service, "generate", new_callable=AsyncMock, return_value="Das ist kein JSON"
        ):
            result = await service.extract_entities("Test text")

            # Service behandelt ungueltige JSON graceful - leere Ergebnisse
            assert result.persons == []
            assert result.organizations == []
            assert result.locations == []
            assert result.money_amounts == []
            assert result.dates == []
            assert result.contract_numbers == []

    @pytest.mark.asyncio
    async def test_http_error_handling(self, service: OllamaService) -> None:
        """HTTP-Fehler werden behandelt."""
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.raise_for_status.side_effect = HTTPStatusError(
                "Server Error",
                request=MagicMock(),
                response=mock_response
            )
            mock_post.return_value = mock_response

            with pytest.raises(HTTPStatusError):
                await service.generate("Test")


class TestServiceConfiguration:
    """Tests fuer Service-Konfiguration."""

    def test_default_base_url(self) -> None:
        """Standard-URL wird gesetzt."""
        service = OllamaService()
        assert service.config.base_url == "http://localhost:11434"

    def test_custom_base_url(self) -> None:
        """Benutzerdefinierte URL wird verwendet."""
        config = OllamaConfig(base_url="http://custom:11434")
        service = OllamaService(config=config)
        assert service.config.base_url == "http://custom:11434"

    def test_default_model(self) -> None:
        """Standard-Model wird gesetzt."""
        service = OllamaService()
        assert service.config.default_model == "mistral"

    def test_custom_default_model(self) -> None:
        """Benutzerdefiniertes Standard-Model wird verwendet."""
        config = OllamaConfig(default_model="neural-chat")
        service = OllamaService(config=config)
        assert service.config.default_model == "neural-chat"


class TestOllamaServiceIntegration:
    """Integrationstests (mit Mocks)."""

    @pytest.fixture
    def service(self) -> OllamaService:
        return OllamaService()

    @pytest.mark.asyncio
    async def test_full_document_analysis_workflow(self, service: OllamaService) -> None:
        """Vollstaendiger Dokument-Analyse-Workflow."""
        document_text = """
        Rechnung Nr. 2024-001
        Von: ABC GmbH, Musterstrasse 1, 12345 Berlin
        An: Max Mustermann
        Datum: 15.03.2024
        Betrag: 1.500,00 EUR
        Zahlungsziel: 30 Tage
        """

        # Mock entities extraction (mit korrektem Format)
        entities_response = json.dumps({
            "persons": ["Max Mustermann"],
            "organizations": ["ABC GmbH"],
            "locations": ["Musterstrasse 1", "Berlin"],
            "money_amounts": ["1.500,00 EUR"],
            "dates": ["15.03.2024"],
            "contract_numbers": []
        })

        with patch.object(service, "generate", return_value=entities_response):
            entities = await service.extract_entities(document_text)

            assert "ABC GmbH" in entities.organizations
            assert "1.500,00 EUR" in entities.money_amounts
            assert "Max Mustermann" in entities.persons
