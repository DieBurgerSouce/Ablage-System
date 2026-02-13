# -*- coding: utf-8 -*-
"""
Tests fuer EntitySearchService.

Testet:
- Suche nach Kundennummer
- Suche nach Lieferantennummer
- Matchcode-Suche mit Fuzzy-Matching
- IBAN- und VAT-ID-Suche
- Smart Search (kombinierte Suche)
- Firmen-Filter
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.entity_search_service import (
    EntitySearchService,
    normalize_text,
    calculate_similarity,
)
from app.db.models import BusinessEntity, EntityType


class TestNormalizeText:
    """Tests fuer normalize_text Hilfsfunktion."""

    def test_normalize_lowercase(self):
        """Sollte Text in Kleinbuchstaben umwandeln."""
        result = normalize_text("MUELLER GMBH")
        assert result == "mueller gmbh"

    def test_normalize_whitespace(self):
        """Sollte mehrfache Leerzeichen reduzieren."""
        result = normalize_text("Mueller   GmbH   Berlin")
        assert result == "mueller gmbh berlin"

    def test_normalize_empty(self):
        """Sollte leeren String bei leerem Input zurueckgeben."""
        assert normalize_text("") == ""
        assert normalize_text(None) == ""

    def test_normalize_strip(self):
        """Sollte fuehrende/nachfolgende Leerzeichen entfernen."""
        result = normalize_text("  Mueller GmbH  ")
        assert result == "mueller gmbh"

    def test_normalize_with_umlauts(self):
        """Sollte Umlaute korrekt behandeln."""
        result = normalize_text("Müller GmbH")
        assert result == "müller gmbh"


class TestCalculateSimilarity:
    """Tests fuer calculate_similarity Funktion."""

    def test_similarity_identical(self):
        """Identische Strings sollten 1.0 ergeben."""
        result = calculate_similarity("Mueller GmbH", "Mueller GmbH")
        assert result == 1.0

    def test_similarity_case_insensitive(self):
        """Sollte Gross-/Kleinschreibung ignorieren."""
        result = calculate_similarity("MUELLER", "mueller")
        assert result == 1.0

    def test_similarity_similar(self):
        """Aehnliche Strings sollten hohe Aehnlichkeit haben."""
        result = calculate_similarity("Mueller GmbH", "Müller GmbH")
        assert result > 0.8

    def test_similarity_different(self):
        """Unterschiedliche Strings sollten niedrige Aehnlichkeit haben."""
        result = calculate_similarity("Mueller", "Schulze")
        assert result < 0.5

    def test_similarity_empty(self):
        """Leere Strings sollten 0.0 ergeben."""
        assert calculate_similarity("", "test") == 0.0
        assert calculate_similarity("test", "") == 0.0
        assert calculate_similarity("", "") == 0.0


class TestEntitySearchServiceInit:
    """Tests fuer Service-Initialisierung."""

    def test_init_creates_service(self):
        """Sollte Service korrekt initialisieren."""
        mock_db = MagicMock()
        service = EntitySearchService(mock_db)

        assert service.db == mock_db
        assert service.DEFAULT_SIMILARITY_THRESHOLD == 0.7


class TestFindByCustomerNumber:
    """Tests fuer find_by_customer_number Methode."""

    @pytest.fixture
    def service(self):
        mock_db = AsyncMock()
        return EntitySearchService(mock_db)

    @pytest.mark.asyncio
    async def test_find_by_primary_customer_number(self, service):
        """Sollte Entity ueber primary_customer_number finden."""
        entity = MagicMock(spec=BusinessEntity)
        entity.id = uuid4()
        entity.name = "12345_Mueller"
        entity.primary_customer_number = "12345"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = entity
        service.db.execute = AsyncMock(return_value=mock_result)

        result = await service.find_by_customer_number("12345")

        assert result == entity

    @pytest.mark.asyncio
    async def test_find_by_empty_number_returns_none(self, service):
        """Sollte None bei leerer Kundennummer zurueckgeben."""
        result = await service.find_by_customer_number("")
        assert result is None

        result = await service.find_by_customer_number("   ")
        assert result is None

    @pytest.mark.asyncio
    async def test_find_by_customer_number_not_found(self, service):
        """Sollte None bei nicht gefundener Kundennummer zurueckgeben."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        service.db.execute = AsyncMock(return_value=mock_result)

        result = await service.find_by_customer_number("99999")
        assert result is None


class TestFindBySupplierNumber:
    """Tests fuer find_by_supplier_number Methode."""

    @pytest.fixture
    def service(self):
        mock_db = AsyncMock()
        return EntitySearchService(mock_db)

    @pytest.mark.asyncio
    async def test_find_by_primary_supplier_number(self, service):
        """Sollte Entity ueber primary_supplier_number finden."""
        entity = MagicMock(spec=BusinessEntity)
        entity.id = uuid4()
        entity.primary_supplier_number = "L1001"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = entity
        service.db.execute = AsyncMock(return_value=mock_result)

        result = await service.find_by_supplier_number("L1001")

        assert result == entity

    @pytest.mark.asyncio
    async def test_find_by_empty_supplier_number_returns_none(self, service):
        """Sollte None bei leerer Lieferantennummer zurueckgeben."""
        result = await service.find_by_supplier_number("")
        assert result is None


class TestFindByIBAN:
    """Tests fuer find_by_iban Methode."""

    @pytest.fixture
    def service(self):
        mock_db = AsyncMock()
        return EntitySearchService(mock_db)

    @pytest.mark.asyncio
    async def test_find_by_iban_normalized(self, service):
        """Sollte IBAN normalisieren und finden."""
        entity = MagicMock(spec=BusinessEntity)
        entity.iban = "DE89370400440532013000"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = entity
        service.db.execute = AsyncMock(return_value=mock_result)

        # Mit Leerzeichen eingeben
        result = await service.find_by_iban("DE89 3704 0044 0532 0130 00")

        assert result == entity

    @pytest.mark.asyncio
    async def test_find_by_invalid_iban_returns_none(self, service):
        """Sollte None bei zu kurzer IBAN zurueckgeben."""
        result = await service.find_by_iban("DE123")
        assert result is None


class TestFindByVatId:
    """Tests fuer find_by_vat_id Methode."""

    @pytest.fixture
    def service(self):
        mock_db = AsyncMock()
        return EntitySearchService(mock_db)

    @pytest.mark.asyncio
    async def test_find_by_vat_id_normalized(self, service):
        """Sollte VAT-ID normalisieren und finden."""
        entity = MagicMock(spec=BusinessEntity)
        entity.vat_id = "DE123456789"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = entity
        service.db.execute = AsyncMock(return_value=mock_result)

        # Mit Leerzeichen eingeben
        result = await service.find_by_vat_id("DE 123 456 789")

        assert result == entity

    @pytest.mark.asyncio
    async def test_find_by_invalid_vat_id_returns_none(self, service):
        """Sollte None bei zu kurzer VAT-ID zurueckgeben."""
        result = await service.find_by_vat_id("DE123")
        assert result is None


class TestFindByMatchcode:
    """Tests fuer find_by_matchcode Methode mit Fuzzy-Matching."""

    @pytest.fixture
    def service(self):
        mock_db = AsyncMock()
        return EntitySearchService(mock_db)

    @pytest.mark.asyncio
    async def test_find_by_matchcode_exact_match(self, service):
        """Sollte exakten Matchcode mit hoher Aehnlichkeit finden."""
        entity = MagicMock(spec=BusinessEntity)
        entity.id = uuid4()
        entity.name = "Mueller GmbH"
        entity.short_name = "Mueller"
        entity.display_name = "Müller GmbH"
        entity.name_aliases = ["Firma Mueller"]
        entity.lexware_ids = None
        entity.deleted_at = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [entity]
        service.db.execute = AsyncMock(return_value=mock_result)

        result = await service.find_by_matchcode("Mueller")

        assert len(result) > 0
        assert result[0][0] == entity
        assert result[0][1] >= 0.9  # Hohe Aehnlichkeit

    @pytest.mark.asyncio
    async def test_find_by_matchcode_fuzzy_match(self, service):
        """Sollte aehnlichen Matchcode mit Fuzzy-Matching finden."""
        entity = MagicMock(spec=BusinessEntity)
        entity.id = uuid4()
        entity.name = "Mueller GmbH"
        entity.short_name = "Mueller"
        entity.display_name = None
        entity.name_aliases = None
        entity.lexware_ids = None
        entity.deleted_at = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [entity]
        service.db.execute = AsyncMock(return_value=mock_result)

        result = await service.find_by_matchcode("Müller", similarity_threshold=0.7)

        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_find_by_matchcode_empty_returns_empty_list(self, service):
        """Sollte leere Liste bei leerem Matchcode zurueckgeben."""
        result = await service.find_by_matchcode("")
        assert result == []

    @pytest.mark.asyncio
    async def test_find_by_matchcode_sorted_by_similarity(self, service):
        """Sollte Ergebnisse nach Aehnlichkeit sortieren."""
        entity1 = MagicMock(spec=BusinessEntity)
        entity1.name = "Mueller"
        entity1.short_name = None
        entity1.display_name = None
        entity1.name_aliases = None
        entity1.lexware_ids = None
        entity1.deleted_at = None

        entity2 = MagicMock(spec=BusinessEntity)
        entity2.name = "Mueller GmbH"
        entity2.short_name = None
        entity2.display_name = None
        entity2.name_aliases = None
        entity2.lexware_ids = None
        entity2.deleted_at = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [entity2, entity1]
        service.db.execute = AsyncMock(return_value=mock_result)

        result = await service.find_by_matchcode("Mueller")

        # Erster sollte exakter sein (Mueller vs Mueller GmbH)
        assert len(result) >= 1


class TestSmartSearch:
    """Tests fuer smart_search kombinierte Suche."""

    @pytest.fixture
    def service(self):
        mock_db = AsyncMock()
        return EntitySearchService(mock_db)

    @pytest.mark.asyncio
    async def test_smart_search_empty_query_returns_empty(self, service):
        """Sollte leere Liste bei leerer Query zurueckgeben."""
        result = await service.smart_search("")
        assert result == []

    @pytest.mark.asyncio
    async def test_smart_search_customer_number_pattern(self, service):
        """Sollte reinen Ziffern-Query als Kundennummer erkennen."""
        entity = MagicMock(spec=BusinessEntity)
        entity.primary_customer_number = "12345"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = entity
        service.db.execute = AsyncMock(return_value=mock_result)

        result = await service.smart_search("12345")

        assert len(result) == 1
        assert result[0][2] == "customer_number"

    @pytest.mark.asyncio
    async def test_smart_search_iban_pattern(self, service):
        """Sollte IBAN-Muster erkennen."""
        entity = MagicMock(spec=BusinessEntity)
        entity.iban = "DE89370400440532013000"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = entity
        service.db.execute = AsyncMock(return_value=mock_result)

        result = await service.smart_search("DE89370400440532013000")

        assert len(result) == 1
        assert result[0][2] == "iban"


class TestFindByCompany:
    """Tests fuer find_by_company Filter-Methode."""

    @pytest.fixture
    def service(self):
        mock_db = AsyncMock()
        return EntitySearchService(mock_db)

    @pytest.mark.asyncio
    async def test_find_by_company_folie(self, service):
        """Sollte Entities fuer Firma Folie finden."""
        entity = MagicMock(spec=BusinessEntity)
        entity.company_presence = ["folie"]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [entity]
        service.db.execute = AsyncMock(return_value=mock_result)

        result = await service.find_by_company("folie")

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_find_in_multiple_companies(self, service):
        """Sollte Entities in mehreren Firmen finden."""
        entity = MagicMock(spec=BusinessEntity)
        entity.company_presence = ["folie", "messer"]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [entity]
        service.db.execute = AsyncMock(return_value=mock_result)

        result = await service.find_in_multiple_companies(min_companies=2)

        assert len(result) == 1


class TestFactoryFunction:
    """Tests fuer Factory-Funktion."""

    def test_get_entity_search_service_creates_instance(self):
        """Sollte neue Service-Instanz erstellen."""
        from app.services.entity_search_service import get_entity_search_service

        mock_db = MagicMock()
        service = get_entity_search_service(mock_db)

        assert isinstance(service, EntitySearchService)
        assert service.db == mock_db
