# -*- coding: utf-8 -*-
"""
Tests fuer CustomerCardService.

Testet:
- Customer Card Abruf (Cache, DB, Generierung)
- Customer Card Generierung mit LLM
- Kundensuche (Fuzzy Search)
- Card Synchronisation
- Cache Management
"""

import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any

from app.services.rag.customer_card_service import (
    CustomerCardService,
    CustomerCardResult,
    CustomerSearchResult,
    get_customer_card_service,
)
from app.db.models import RAGCustomerCard, RAGCardSyncStatus


class TestCustomerCardResult:
    """Tests fuer CustomerCardResult Dataclass."""

    def test_create_with_card(self):
        """Sollte CustomerCardResult mit Card erstellen."""
        mock_card = MagicMock(spec=RAGCustomerCard)
        mock_card.customer_id = "KD-001"

        result = CustomerCardResult(
            card=mock_card,
            from_cache=True,
            generation_time_ms=50
        )

        assert result.card is not None
        assert result.from_cache is True
        assert result.generation_time_ms == 50

    def test_create_without_card(self):
        """Sollte CustomerCardResult ohne Card erstellen."""
        result = CustomerCardResult(
            card=None,
            from_cache=False
        )

        assert result.card is None
        assert result.from_cache is False
        assert result.generation_time_ms is None


class TestCustomerSearchResult:
    """Tests fuer CustomerSearchResult Dataclass."""

    def test_create_search_result(self):
        """Sollte CustomerSearchResult erstellen."""
        result = CustomerSearchResult(
            customer_id="KD-001",
            customer_name="Test GmbH",
            similarity=0.95,
            document_count=15,
            last_document_date=datetime.now(timezone.utc)
        )

        assert result.customer_id == "KD-001"
        assert result.customer_name == "Test GmbH"
        assert result.similarity == 0.95
        assert result.document_count == 15


class TestCustomerCardServiceInit:
    """Tests fuer Service-Initialisierung."""

    def test_init_with_defaults(self):
        """Sollte Service mit Default-Dependencies initialisieren."""
        with patch('app.services.rag.customer_card_service.get_rag_search_service') as mock_search:
            with patch('app.services.rag.customer_card_service.get_llm_service') as mock_llm:
                mock_search.return_value = MagicMock()
                mock_llm.return_value = MagicMock()

                service = CustomerCardService()

                assert service.search_service is not None
                assert service.llm_service is not None
                assert service._cache == {}

    def test_init_with_custom_services(self):
        """Sollte Service mit Custom-Dependencies initialisieren."""
        mock_search = MagicMock()
        mock_llm = MagicMock()

        service = CustomerCardService(
            search_service=mock_search,
            llm_service=mock_llm
        )

        assert service.search_service == mock_search
        assert service.llm_service == mock_llm


class TestGetCard:
    """Tests fuer get_card Methode."""

    @pytest.fixture
    def service(self):
        """Erstelle Service mit gemockten Dependencies."""
        mock_search = MagicMock()
        mock_llm = MagicMock()
        return CustomerCardService(
            search_service=mock_search,
            llm_service=mock_llm
        )

    @pytest.fixture
    def mock_db(self):
        """Mockt AsyncSession."""
        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()
        return db

    @pytest.mark.asyncio
    async def test_get_card_from_cache(self, service: CustomerCardService, mock_db):
        """Sollte Card aus Cache zurueckgeben."""
        mock_card = MagicMock(spec=RAGCustomerCard)
        mock_card.customer_id = "KD-001"
        # Service prueft Cache-Frische via last_full_sync_at (umbenannt von last_sync_at)
        mock_card.last_full_sync_at = datetime.now(timezone.utc)

        # Card in Cache legen
        service._cache["KD-001"] = mock_card

        result = await service.get_card(mock_db, "KD-001")

        assert result.card == mock_card
        assert result.from_cache is True

    @pytest.mark.asyncio
    async def test_get_card_from_db(self, service: CustomerCardService, mock_db):
        """Sollte Card aus Datenbank laden."""
        mock_card = MagicMock(spec=RAGCustomerCard)
        mock_card.customer_id = "KD-001"
        mock_card.last_sync_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_card
        mock_db.execute.return_value = mock_result

        result = await service.get_card(mock_db, "KD-001")

        assert result.card == mock_card
        assert result.from_cache is False
        # Card sollte jetzt im Cache sein
        assert "KD-001" in service._cache

    @pytest.mark.asyncio
    async def test_get_card_not_found_generates(self, service: CustomerCardService, mock_db):
        """Sollte Card generieren wenn nicht vorhanden."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with patch.object(
            service, 'generate_card',
            return_value=MagicMock(spec=RAGCustomerCard)
        ) as mock_generate:
            result = await service.get_card(mock_db, "KD-NEW")

            mock_generate.assert_called_once()
            assert result.from_cache is False

    @pytest.mark.asyncio
    async def test_get_card_force_refresh(self, service: CustomerCardService, mock_db):
        """Sollte Card neu generieren bei force_refresh."""
        mock_card = MagicMock(spec=RAGCustomerCard)
        service._cache["KD-001"] = mock_card

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_card
        mock_db.execute.return_value = mock_result

        with patch.object(
            service, 'generate_card',
            return_value=mock_card
        ) as mock_generate:
            result = await service.get_card(mock_db, "KD-001", force_refresh=True)

            mock_generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_card_cache_expired(self, service: CustomerCardService, mock_db):
        """Sollte Cache ignorieren wenn zu alt."""
        mock_card = MagicMock(spec=RAGCustomerCard)
        mock_card.customer_id = "KD-001"
        # Card ist 2 Stunden alt (Frische-Check liest last_full_sync_at)
        mock_card.last_full_sync_at = datetime.now(timezone.utc) - timedelta(hours=2)

        service._cache["KD-001"] = mock_card

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_card
        mock_db.execute.return_value = mock_result

        result = await service.get_card(mock_db, "KD-001")

        # Sollte aus DB geladen werden, nicht aus Cache
        mock_db.execute.assert_called()


class TestGenerateCard:
    """Tests fuer generate_card Methode."""

    @pytest.fixture
    def service(self):
        """Erstelle Service mit gemockten Dependencies."""
        mock_search = MagicMock()
        # generate_card hat einen Fast-Path: ohne gefundene Dokumente (leere
        # source_document_ids) wird KEINE Card persistiert (return None). Damit der
        # Persistenz-Pfad (db.add/db.commit) getestet wird, muss search_for_context
        # mindestens ein Chunk mit document_id liefern.
        mock_search.search_for_context = AsyncMock(
            return_value=[
                {"text": "Kontext", "document_id": str(uuid4())}
            ]
        )
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value=MagicMock(content="Test Summary"))
        return CustomerCardService(
            search_service=mock_search,
            llm_service=mock_llm
        )

    @pytest.fixture
    def mock_db(self):
        """Mockt AsyncSession."""
        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()
        return db

    @pytest.mark.asyncio
    async def test_generate_card_new(self, service: CustomerCardService, mock_db):
        """Sollte neue Card generieren."""
        # Keine existierende Card
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with patch.object(service, '_extract_quick_facts', return_value={}):
            card = await service.generate_card(mock_db, "KD-001", "Test Kunde")

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        assert "KD-001" in service._cache

    @pytest.mark.asyncio
    async def test_generate_card_update_existing(self, service: CustomerCardService, mock_db):
        """Sollte existierende Card aktualisieren."""
        mock_card = MagicMock(spec=RAGCustomerCard)
        mock_card.customer_id = "KD-001"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_card
        mock_db.execute.return_value = mock_result

        with patch.object(service, '_extract_quick_facts', return_value={}):
            card = await service.generate_card(mock_db, "KD-001", "Test Kunde")

        # Sollte nicht add aufrufen, nur commit
        mock_db.add.assert_not_called()
        mock_db.commit.assert_called_once()


class TestSearchCustomers:
    """Tests fuer search_customers Methode."""

    @pytest.fixture
    def service(self):
        """Erstelle Service."""
        mock_search = MagicMock()
        mock_llm = MagicMock()
        return CustomerCardService(
            search_service=mock_search,
            llm_service=mock_llm
        )

    @pytest.fixture
    def mock_db(self):
        """Mockt AsyncSession."""
        db = AsyncMock()
        db.execute = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_search_customers_with_pg_trgm(self, service: CustomerCardService, mock_db):
        """Sollte Kunden mit pg_trgm suchen."""
        mock_row = MagicMock()
        mock_row.customer_id = "KD-001"
        mock_row.customer_name = "Test GmbH"
        mock_row.sim = 0.85
        mock_row.doc_count = 10
        mock_row.last_sync_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]
        mock_db.execute.return_value = mock_result

        results = await service.search_customers(mock_db, "Test")

        assert len(results) == 1
        assert results[0].customer_id == "KD-001"
        assert results[0].similarity == 0.85

    @pytest.mark.asyncio
    async def test_search_customers_fallback(self, service: CustomerCardService, mock_db):
        """Sollte auf ILIKE zurueckfallen wenn pg_trgm fehlt."""
        # Erster Aufruf wirft Exception (pg_trgm nicht verfuegbar)
        # Zweiter Aufruf ist Fallback
        mock_card = MagicMock()
        mock_card.customer_id = "KD-001"
        mock_card.customer_name = "Test GmbH"
        mock_card.source_document_ids = ["doc1", "doc2"]
        mock_card.last_sync_at = datetime.now(timezone.utc)

        def execute_side_effect(*args, **kwargs):
            # Beim ersten Aufruf Exception werfen
            if execute_side_effect.call_count == 1:
                execute_side_effect.call_count += 1
                raise Exception("pg_trgm not available")
            else:
                result = MagicMock()
                result.scalars.return_value.all.return_value = [mock_card]
                return result

        execute_side_effect.call_count = 1
        mock_db.execute.side_effect = execute_side_effect

        results = await service.search_customers(mock_db, "Test")

        assert len(results) == 1
        assert results[0].similarity == 0.5  # Default similarity

    @pytest.mark.asyncio
    async def test_search_customers_empty(self, service: CustomerCardService, mock_db):
        """Sollte leere Liste bei keinen Ergebnissen zurueckgeben."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        results = await service.search_customers(mock_db, "NonExistent")

        assert len(results) == 0


class TestGetAllCustomers:
    """Tests fuer get_all_customers Methode."""

    @pytest.fixture
    def service(self):
        """Erstelle Service."""
        mock_search = MagicMock()
        mock_llm = MagicMock()
        return CustomerCardService(
            search_service=mock_search,
            llm_service=mock_llm
        )

    @pytest.fixture
    def mock_db(self):
        """Mockt AsyncSession."""
        db = AsyncMock()
        db.execute = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_get_all_customers_with_pagination(
        self, service: CustomerCardService, mock_db
    ):
        """Sollte alle Kunden mit Pagination abrufen."""
        mock_cards = [MagicMock(spec=RAGCustomerCard) for _ in range(5)]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_cards
        mock_db.execute.return_value = mock_result

        results = await service.get_all_customers(mock_db, limit=10, offset=0)

        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_get_all_customers_empty(self, service: CustomerCardService, mock_db):
        """Sollte leere Liste zurueckgeben wenn keine Cards."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        results = await service.get_all_customers(mock_db)

        assert len(results) == 0


class TestSyncAllCards:
    """Tests fuer sync_all_cards Methode."""

    @pytest.fixture
    def service(self):
        """Erstelle Service."""
        mock_search = MagicMock()
        mock_llm = MagicMock()
        return CustomerCardService(
            search_service=mock_search,
            llm_service=mock_llm
        )

    @pytest.fixture
    def mock_db(self):
        """Mockt AsyncSession."""
        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_sync_all_cards_empty(self, service: CustomerCardService, mock_db):
        """Sollte leere Stats bei keinen Kunden zurueckgeben."""
        with patch.object(service, '_discover_customers', return_value=[]):
            stats = await service.sync_all_cards(mock_db)

        assert stats["total"] == 0
        assert stats["updated"] == 0
        assert stats["created"] == 0
        assert stats["failed"] == 0

    @pytest.mark.asyncio
    async def test_sync_all_cards_with_customers(self, service: CustomerCardService, mock_db):
        """Sollte Kunden synchronisieren."""
        customers = [
            ("KD-001", "Kunde 1"),
            ("KD-002", "Kunde 2"),
        ]

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # Keine existierende Card
        mock_db.execute.return_value = mock_result

        with patch.object(service, '_discover_customers', return_value=customers):
            with patch.object(service, 'generate_card', return_value=MagicMock()):
                stats = await service.sync_all_cards(mock_db, batch_size=10)

        assert stats["total"] == 2
        assert stats["created"] == 2


class TestClearCache:
    """Tests fuer clear_cache Methode."""

    @pytest.fixture
    def service(self):
        """Erstelle Service."""
        mock_search = MagicMock()
        mock_llm = MagicMock()
        return CustomerCardService(
            search_service=mock_search,
            llm_service=mock_llm
        )

    def test_clear_specific_customer(self, service: CustomerCardService):
        """Sollte spezifischen Kunden aus Cache entfernen."""
        service._cache["KD-001"] = MagicMock()
        service._cache["KD-002"] = MagicMock()

        service.clear_cache("KD-001")

        assert "KD-001" not in service._cache
        assert "KD-002" in service._cache

    def test_clear_all_cache(self, service: CustomerCardService):
        """Sollte gesamten Cache leeren."""
        service._cache["KD-001"] = MagicMock()
        service._cache["KD-002"] = MagicMock()

        service.clear_cache()

        assert len(service._cache) == 0

    def test_clear_nonexistent_customer(self, service: CustomerCardService):
        """Sollte keinen Fehler werfen bei nicht existierendem Kunden."""
        service._cache["KD-001"] = MagicMock()

        service.clear_cache("KD-999")  # Existiert nicht

        assert "KD-001" in service._cache


class TestExtractQuickFacts:
    """Tests fuer _extract_quick_facts Methode."""

    @pytest.fixture
    def service(self):
        """Erstelle Service."""
        mock_search = MagicMock()
        mock_llm = MagicMock()
        return CustomerCardService(
            search_service=mock_search,
            llm_service=mock_llm
        )

    @pytest.fixture
    def mock_db(self):
        """Mockt AsyncSession."""
        db = AsyncMock()
        db.execute = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_extract_quick_facts_empty_ids(
        self, service: CustomerCardService, mock_db
    ):
        """Sollte leeres Dict bei leeren IDs zurueckgeben."""
        result = await service._extract_quick_facts(mock_db, [])

        assert result == {}

    @pytest.mark.asyncio
    async def test_extract_quick_facts_with_documents(
        self, service: CustomerCardService, mock_db
    ):
        """Sollte Quick Facts aus Dokumenten extrahieren."""
        doc_id = str(uuid4())

        mock_doc = MagicMock()
        mock_doc.doc_type = "invoice"
        mock_doc.created_at = datetime(2024, 1, 15, tzinfo=timezone.utc)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_doc]
        mock_db.execute.return_value = mock_result

        result = await service._extract_quick_facts(mock_db, [doc_id])

        assert result["document_count"] == 1
        assert "invoice" in result["document_types"]


class TestSingleton:
    """Tests fuer Singleton-Pattern."""

    def test_get_customer_card_service_singleton(self):
        """Sollte immer gleiche Instanz zurueckgeben."""
        with patch('app.services.rag.customer_card_service.get_rag_search_service'):
            with patch('app.services.rag.customer_card_service.get_llm_service'):
                # Reset singleton
                import app.services.rag.customer_card_service as module
                module._customer_card_service = None

                service1 = get_customer_card_service()
                service2 = get_customer_card_service()

                assert service1 is service2
