"""
Unit Tests fuer LLMNERService.

Testet:
- Service-Initialisierung
- Dataclass-Strukturen
- Enum-Werte
- Methoden-Existenz
"""

import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest_asyncio


class TestLLMNERService:
    """Tests fuer LLM-basierte Named Entity Recognition."""

    @pytest.mark.asyncio
    async def test_service_initialization(self) -> None:
        """Testet Service-Initialisierung."""
        from app.services.document_intelligence.llm_ner_service import (
            LLMNERService,
        )

        service = LLMNERService()
        assert service is not None

    @pytest.mark.asyncio
    async def test_dataclass_and_enum_imports(self) -> None:
        """Testet dass alle Datenklassen und Enums importierbar sind."""
        from app.services.document_intelligence.llm_ner_service import (
            EntityType,
            ExtractedEntity,
            LLMNERService,
            NERResult,
        )

        assert LLMNERService is not None
        assert EntityType is not None
        assert ExtractedEntity is not None
        assert NERResult is not None


class TestEntityTypeEnum:
    """Tests fuer EntityType Enum."""

    @pytest.mark.asyncio
    async def test_entity_type_values(self) -> None:
        """Testet EntityType Enum-Werte."""
        from app.services.document_intelligence.llm_ner_service import (
            EntityType,
        )

        # Pruefe wichtige Entitaetstypen
        assert EntityType.DEADLINE is not None
        assert EntityType.AMOUNT is not None
        assert EntityType.COMPANY is not None
        assert EntityType.PERSON is not None
        assert EntityType.CONTRACT_NUMBER is not None
        assert EntityType.DATE is not None

    @pytest.mark.asyncio
    async def test_entity_type_is_string_enum(self) -> None:
        """Testet dass EntityType ein String-Enum ist."""
        from app.services.document_intelligence.llm_ner_service import (
            EntityType,
        )

        # Sollte String-Werte haben
        assert isinstance(EntityType.DEADLINE.value, str)
        assert isinstance(EntityType.AMOUNT.value, str)


class TestExtractedEntityDataClass:
    """Tests fuer ExtractedEntity Datenstruktur."""

    @pytest.mark.asyncio
    async def test_extracted_entity_dataclass(self) -> None:
        """Testet ExtractedEntity Datenstruktur."""
        from app.services.document_intelligence.llm_ner_service import (
            EntityType,
            ExtractedEntity,
        )

        entity = ExtractedEntity(
            entity_type=EntityType.AMOUNT,
            value="1.500,00 EUR",
            confidence=0.95,
            context="Gesamtbetrag der Rechnung",
            position=(100, 113),
        )

        assert entity.entity_type == EntityType.AMOUNT
        assert entity.value == "1.500,00 EUR"
        assert entity.confidence == 0.95
        assert entity.context == "Gesamtbetrag der Rechnung"
        assert entity.position == (100, 113)

    @pytest.mark.asyncio
    async def test_extracted_entity_deadline(self) -> None:
        """Testet ExtractedEntity fuer Deadline."""
        from app.services.document_intelligence.llm_ner_service import (
            EntityType,
            ExtractedEntity,
        )

        entity = ExtractedEntity(
            entity_type=EntityType.DEADLINE,
            value="2024-12-31",
            normalized_value="2024-12-31",
            confidence=0.92,
            context="Zahlungsziel",
        )

        assert entity.entity_type == EntityType.DEADLINE
        assert entity.confidence > 0.9


class TestNERResultDataClass:
    """Tests fuer NERResult Datenstruktur."""

    @pytest.mark.asyncio
    async def test_ner_result_dataclass(self) -> None:
        """Testet NERResult Datenstruktur."""
        from app.services.document_intelligence.llm_ner_service import (
            EntityType,
            ExtractedEntity,
            NERResult,
        )

        entities = [
            ExtractedEntity(
                entity_type=EntityType.AMOUNT,
                value="1.500,00 EUR",
                confidence=0.95,
                context="Gesamtbetrag",
            ),
            ExtractedEntity(
                entity_type=EntityType.DEADLINE,
                value="2024-12-31",
                confidence=0.92,
                context="Zahlungsziel",
            ),
        ]

        result = NERResult(
            document_id=uuid4(),
            entities=entities,
            processing_time_ms=150,
            model_used="qwen3:14b",
            text_length=500,
        )

        assert len(result.entities) == 2
        assert result.processing_time_ms == 150
        assert result.model_used == "qwen3:14b"
        assert result.text_length == 500

    @pytest.mark.asyncio
    async def test_ner_result_helper_properties(self) -> None:
        """Testet NERResult Helper-Properties."""
        from app.services.document_intelligence.llm_ner_service import (
            EntityType,
            ExtractedEntity,
            NERResult,
        )

        entities = [
            ExtractedEntity(
                entity_type=EntityType.DEADLINE,
                value="2024-12-31",
                confidence=0.92,
                context="Zahlungsziel",
            ),
            ExtractedEntity(
                entity_type=EntityType.AMOUNT,
                value="1.500,00 EUR",
                confidence=0.95,
                context="Gesamtbetrag",
            ),
            ExtractedEntity(
                entity_type=EntityType.COMPANY,
                value="Musterfirma GmbH",
                confidence=0.88,
                context="Absender",
            ),
        ]

        result = NERResult(
            document_id=uuid4(),
            entities=entities,
            processing_time_ms=150,
            model_used="qwen3:14b",
            text_length=500,
        )

        # Teste Helper-Properties
        assert len(result.deadlines) == 1
        assert len(result.amounts) == 1
        assert len(result.companies) == 1

    @pytest.mark.asyncio
    async def test_ner_result_to_dict(self) -> None:
        """Testet NERResult to_dict Methode."""
        from app.services.document_intelligence.llm_ner_service import (
            NERResult,
        )

        result = NERResult(
            document_id=uuid4(),
            entities=[],
            processing_time_ms=150,
            model_used="qwen3:14b",
            text_length=500,
        )

        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert "entities" in result_dict
        assert "processing_time_ms" in result_dict


class TestServiceMethodsExist:
    """Tests dass alle wichtigen Service-Methoden existieren."""

    @pytest.mark.asyncio
    async def test_service_has_extract_entities_method(self) -> None:
        """Testet dass Service extract_entities Methode hat."""
        from app.services.document_intelligence.llm_ner_service import (
            LLMNERService,
        )

        service = LLMNERService()

        assert hasattr(service, "extract_entities")
        assert callable(getattr(service, "extract_entities"))

    @pytest.mark.asyncio
    async def test_service_has_extract_deadlines_method(self) -> None:
        """Testet dass Service extract_deadlines Methode hat."""
        from app.services.document_intelligence.llm_ner_service import (
            LLMNERService,
        )

        service = LLMNERService()

        assert hasattr(service, "extract_deadlines")
        assert callable(getattr(service, "extract_deadlines"))

    @pytest.mark.asyncio
    async def test_service_has_extract_financial_info_method(self) -> None:
        """Testet dass Service extract_financial_info Methode hat."""
        from app.services.document_intelligence.llm_ner_service import (
            LLMNERService,
        )

        service = LLMNERService()

        assert hasattr(service, "extract_financial_info")
        assert callable(getattr(service, "extract_financial_info"))

    @pytest.mark.asyncio
    async def test_service_has_extract_contact_info_method(self) -> None:
        """Testet dass Service extract_contact_info Methode hat."""
        from app.services.document_intelligence.llm_ner_service import (
            LLMNERService,
        )

        service = LLMNERService()

        assert hasattr(service, "extract_contact_info")
        assert callable(getattr(service, "extract_contact_info"))


class TestGetServiceFunction:
    """Tests fuer get_llm_ner_service Factory."""

    @pytest.mark.asyncio
    async def test_get_service_function_exists(self) -> None:
        """Testet dass get_llm_ner_service existiert."""
        from app.services.document_intelligence.llm_ner_service import (
            get_llm_ner_service,
        )

        assert get_llm_ner_service is not None
        assert callable(get_llm_ner_service)

    @pytest.mark.asyncio
    async def test_get_service_returns_instance(self) -> None:
        """Testet dass get_llm_ner_service eine Instanz zurueckgibt."""
        from app.services.document_intelligence.llm_ner_service import (
            LLMNERService,
            get_llm_ner_service,
        )

        service = get_llm_ner_service()

        assert isinstance(service, LLMNERService)


class TestInternalMethods:
    """Tests fuer interne Service-Methoden."""

    @pytest.mark.asyncio
    async def test_chunk_text_method_exists(self) -> None:
        """Testet dass _chunk_text Methode existiert."""
        from app.services.document_intelligence.llm_ner_service import (
            LLMNERService,
        )

        service = LLMNERService()

        assert hasattr(service, "_chunk_text")
        assert callable(getattr(service, "_chunk_text"))

    @pytest.mark.asyncio
    async def test_parse_llm_response_method_exists(self) -> None:
        """Testet dass _parse_llm_response Methode existiert."""
        from app.services.document_intelligence.llm_ner_service import (
            LLMNERService,
        )

        service = LLMNERService()

        assert hasattr(service, "_parse_llm_response")
        assert callable(getattr(service, "_parse_llm_response"))

    @pytest.mark.asyncio
    async def test_create_entity_method_exists(self) -> None:
        """Testet dass _create_entity Methode existiert."""
        from app.services.document_intelligence.llm_ner_service import (
            LLMNERService,
        )

        service = LLMNERService()

        assert hasattr(service, "_create_entity")
        assert callable(getattr(service, "_create_entity"))

    @pytest.mark.asyncio
    async def test_merge_chunk_entities_method_exists(self) -> None:
        """Testet dass _merge_chunk_entities Methode existiert."""
        from app.services.document_intelligence.llm_ner_service import (
            LLMNERService,
        )

        service = LLMNERService()

        assert hasattr(service, "_merge_chunk_entities")
        assert callable(getattr(service, "_merge_chunk_entities"))
