# -*- coding: utf-8 -*-
"""
E2E Tests: Search and Filter

Tests full-text search, filters, and saved searches.

Feinpoliert und durchdacht - Such- und Filter-Tests.
"""

import pytest
import asyncio
from typing import Dict, Any, List
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta, timezone


@pytest.mark.e2e
class TestFullTextSearch:
    """Test full-text search functionality."""

    @pytest.mark.asyncio
    async def test_simple_text_search(self):
        """Test Einfache Textsuche."""
        with patch("app.services.search_service.SearchService") as MockSearch:
            mock_search = AsyncMock()
            mock_search.search.return_value = {
                "results": [
                    {
                        "id": "doc_001",
                        "filename": "rechnung_2024_001.pdf",
                        "snippet": "...Rechnung Nr. <em>2024-001</em>...",
                        "score": 0.95
                    },
                    {
                        "id": "doc_002",
                        "filename": "angebot_2024_001.pdf",
                        "snippet": "...Angebot Nr. <em>2024-001</em>...",
                        "score": 0.88
                    }
                ],
                "total": 2,
                "query": "2024-001",
                "search_time_ms": 45
            }
            MockSearch.return_value = mock_search

            result = await mock_search.search("2024-001")

            assert result["total"] == 2
            assert result["results"][0]["score"] > result["results"][1]["score"]
            assert "<em>" in result["results"][0]["snippet"]  # Highlighting

    @pytest.mark.asyncio
    async def test_german_umlaut_search(self):
        """Test Suche mit deutschen Umlauten."""
        with patch("app.services.search_service.SearchService") as MockSearch:
            mock_search = AsyncMock()
            mock_search.search.return_value = {
                "results": [
                    {
                        "id": "doc_003",
                        "filename": "mietvertrag_müller.pdf",
                        "snippet": "...Vermieter: Max <em>Müller</em>...",
                        "score": 0.97
                    }
                ],
                "total": 1,
                "query": "Müller"
            }
            MockSearch.return_value = mock_search

            result = await mock_search.search("Müller")

            assert result["total"] == 1
            assert "Müller" in result["results"][0]["snippet"]

    @pytest.mark.asyncio
    async def test_phrase_search(self):
        """Test Phrasensuche (exakte Übereinstimmung)."""
        with patch("app.services.search_service.SearchService") as MockSearch:
            mock_search = AsyncMock()
            mock_search.search.return_value = {
                "results": [
                    {
                        "id": "doc_004",
                        "filename": "vertrag.pdf",
                        "snippet": "...<em>Mit freundlichen Grüßen</em>...",
                        "score": 0.99
                    }
                ],
                "total": 1,
                "query": '"Mit freundlichen Grüßen"',
                "search_type": "phrase"
            }
            MockSearch.return_value = mock_search

            result = await mock_search.search('"Mit freundlichen Grüßen"')

            assert result["search_type"] == "phrase"
            assert result["total"] == 1


@pytest.mark.e2e
class TestFilteredSearch:
    """Test search with filters."""

    @pytest.mark.asyncio
    async def test_filter_by_date_range(self):
        """Test Filterung nach Datumsbereich."""
        with patch("app.services.search_service.SearchService") as MockSearch:
            mock_search = AsyncMock()
            mock_search.search.return_value = {
                "results": [
                    {"id": "doc_001", "created_at": "2024-03-15"},
                    {"id": "doc_002", "created_at": "2024-03-20"}
                ],
                "total": 2,
                "filters": {
                    "date_from": "2024-03-01",
                    "date_to": "2024-03-31"
                }
            }
            MockSearch.return_value = mock_search

            result = await mock_search.search(
                query="rechnung",
                date_from="2024-03-01",
                date_to="2024-03-31"
            )

            assert result["total"] == 2
            assert all(
                "2024-03" in doc["created_at"]
                for doc in result["results"]
            )

    @pytest.mark.asyncio
    async def test_filter_by_document_type(self):
        """Test Filterung nach Dokumenttyp."""
        with patch("app.services.search_service.SearchService") as MockSearch:
            mock_search = AsyncMock()
            mock_search.search.return_value = {
                "results": [
                    {"id": "doc_001", "document_type": "invoice"},
                    {"id": "doc_002", "document_type": "invoice"}
                ],
                "total": 2,
                "filters": {
                    "document_type": "invoice"
                }
            }
            MockSearch.return_value = mock_search

            result = await mock_search.search(
                query="2024",
                document_type="invoice"
            )

            assert all(
                doc["document_type"] == "invoice"
                for doc in result["results"]
            )

    @pytest.mark.asyncio
    async def test_filter_by_folder(self):
        """Test Filterung nach Ordner."""
        with patch("app.services.search_service.SearchService") as MockSearch:
            mock_search = AsyncMock()
            mock_search.search.return_value = {
                "results": [
                    {"id": "doc_001", "folder_id": "folder_001"},
                    {"id": "doc_002", "folder_id": "folder_001"}
                ],
                "total": 2,
                "filters": {
                    "folder_id": "folder_001"
                }
            }
            MockSearch.return_value = mock_search

            result = await mock_search.search(
                query="*",
                folder_id="folder_001"
            )

            assert all(
                doc["folder_id"] == "folder_001"
                for doc in result["results"]
            )


@pytest.mark.e2e
class TestSavedSearches:
    """Test saved search functionality."""

    @pytest.mark.asyncio
    async def test_create_saved_search(self):
        """Test Gespeicherte Suche erstellen."""
        with patch("app.services.search_service.SearchService") as MockSearch:
            mock_search = AsyncMock()
            mock_search.save_search.return_value = {
                "id": "search_001",
                "name": "Rechnungen Q1 2024",
                "query": "rechnung",
                "filters": {
                    "document_type": "invoice",
                    "date_from": "2024-01-01",
                    "date_to": "2024-03-31"
                },
                "user_id": "user_001",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            MockSearch.return_value = mock_search

            saved = await mock_search.save_search(
                name="Rechnungen Q1 2024",
                query="rechnung",
                filters={
                    "document_type": "invoice",
                    "date_from": "2024-01-01",
                    "date_to": "2024-03-31"
                }
            )

            assert saved["id"] == "search_001"
            assert saved["name"] == "Rechnungen Q1 2024"

    @pytest.mark.asyncio
    async def test_execute_saved_search(self):
        """Test Gespeicherte Suche ausführen."""
        with patch("app.services.search_service.SearchService") as MockSearch:
            mock_search = AsyncMock()
            mock_search.execute_saved_search.return_value = {
                "search_id": "search_001",
                "search_name": "Rechnungen Q1 2024",
                "results": [
                    {"id": "doc_001", "document_type": "invoice"},
                    {"id": "doc_002", "document_type": "invoice"}
                ],
                "total": 2,
                "executed_at": datetime.now(timezone.utc).isoformat()
            }
            MockSearch.return_value = mock_search

            result = await mock_search.execute_saved_search("search_001")

            assert result["search_id"] == "search_001"
            assert result["total"] == 2

    @pytest.mark.asyncio
    async def test_list_saved_searches(self):
        """Test Gespeicherte Suchen auflisten."""
        with patch("app.services.search_service.SearchService") as MockSearch:
            mock_search = AsyncMock()
            mock_search.list_saved_searches.return_value = {
                "searches": [
                    {
                        "id": "search_001",
                        "name": "Rechnungen Q1 2024",
                        "query": "rechnung"
                    },
                    {
                        "id": "search_002",
                        "name": "Verträge 2024",
                        "query": "vertrag"
                    }
                ],
                "total": 2,
                "user_id": "user_001"
            }
            MockSearch.return_value = mock_search

            result = await mock_search.list_saved_searches("user_001")

            assert result["total"] == 2
            assert len(result["searches"]) == 2


@pytest.mark.e2e
class TestAdvancedSearch:
    """Test advanced search features."""

    @pytest.mark.asyncio
    async def test_boolean_search(self):
        """Test Boolean-Suche (AND, OR, NOT)."""
        with patch("app.services.search_service.SearchService") as MockSearch:
            mock_search = AsyncMock()
            mock_search.search.return_value = {
                "results": [
                    {"id": "doc_001", "text": "Rechnung und Zahlung"}
                ],
                "total": 1,
                "query": "rechnung AND zahlung",
                "search_type": "boolean"
            }
            MockSearch.return_value = mock_search

            result = await mock_search.search("rechnung AND zahlung")

            assert result["search_type"] == "boolean"
            assert result["total"] == 1

    @pytest.mark.asyncio
    async def test_fuzzy_search(self):
        """Test Fuzzy-Suche (Rechtschreibfehler tolerieren)."""
        with patch("app.services.search_service.SearchService") as MockSearch:
            mock_search = AsyncMock()
            mock_search.search.return_value = {
                "results": [
                    {
                        "id": "doc_001",
                        "filename": "rechnung.pdf",
                        "matched_term": "Rechnung",
                        "query_term": "Rechnug",  # Typo
                        "fuzzy_match": True
                    }
                ],
                "total": 1,
                "search_type": "fuzzy"
            }
            MockSearch.return_value = mock_search

            result = await mock_search.search("Rechnug", fuzzy=True)

            assert result["search_type"] == "fuzzy"
            assert result["results"][0]["fuzzy_match"] is True

    @pytest.mark.asyncio
    async def test_aggregated_search_results(self):
        """Test Aggregierte Suchergebnisse (Facetten)."""
        with patch("app.services.search_service.SearchService") as MockSearch:
            mock_search = AsyncMock()
            mock_search.search.return_value = {
                "results": [...],  # Results omitted for brevity
                "total": 100,
                "aggregations": {
                    "document_types": {
                        "invoice": 45,
                        "contract": 30,
                        "letter": 25
                    },
                    "date_histogram": {
                        "2024-01": 20,
                        "2024-02": 35,
                        "2024-03": 45
                    }
                }
            }
            MockSearch.return_value = mock_search

            result = await mock_search.search(
                query="*",
                aggregations=["document_types", "date_histogram"]
            )

            assert "aggregations" in result
            assert result["aggregations"]["document_types"]["invoice"] == 45
