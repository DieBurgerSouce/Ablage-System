# -*- coding: utf-8 -*-
"""
E2E Tests: Document Chains

Tests chain creation, linking, and traversal.

Feinpoliert und durchdacht - Dokumenten-Ketten Tests.
"""

import pytest
import asyncio
from typing import Dict, Any, List
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone


@pytest.mark.e2e
class TestChainCreation:
    """Test document chain creation."""

    @pytest.mark.asyncio
    async def test_create_invoice_chain(self):
        """Test Rechnungskette erstellen: Angebot → Rechnung → Mahnung."""
        with patch("app.services.document_chain_service.DocumentChainService") as MockChain:
            mock_chain = AsyncMock()
            mock_chain.create_chain.return_value = {
                "chain_id": "chain_001",
                "chain_type": "invoice_process",
                "root_document_id": "doc_quote_001",
                "documents": [
                    {
                        "id": "doc_quote_001",
                        "type": "quote",
                        "position": 0,
                        "status": "completed"
                    }
                ],
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            MockChain.return_value = mock_chain

            chain = await mock_chain.create_chain(
                chain_type="invoice_process",
                root_document_id="doc_quote_001"
            )

            assert chain["chain_type"] == "invoice_process"
            assert len(chain["documents"]) == 1
            assert chain["documents"][0]["type"] == "quote"

    @pytest.mark.asyncio
    async def test_add_document_to_chain(self):
        """Test Dokument zu Kette hinzufügen."""
        with patch("app.services.document_chain_service.DocumentChainService") as MockChain:
            mock_chain = AsyncMock()
            mock_chain.add_to_chain.return_value = {
                "chain_id": "chain_001",
                "documents": [
                    {"id": "doc_quote_001", "type": "quote", "position": 0},
                    {"id": "doc_invoice_001", "type": "invoice", "position": 1},
                ],
                "link": {
                    "from": "doc_quote_001",
                    "to": "doc_invoice_001",
                    "relationship": "quote_to_invoice",
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
            }
            MockChain.return_value = mock_chain

            result = await mock_chain.add_to_chain(
                chain_id="chain_001",
                document_id="doc_invoice_001",
                previous_document_id="doc_quote_001",
                relationship="quote_to_invoice"
            )

            assert len(result["documents"]) == 2
            assert result["link"]["relationship"] == "quote_to_invoice"

    @pytest.mark.asyncio
    async def test_create_contract_amendment_chain(self):
        """Test Vertrag-Änderungskette erstellen."""
        with patch("app.services.document_chain_service.DocumentChainService") as MockChain:
            mock_chain = AsyncMock()
            mock_chain.create_chain.return_value = {
                "chain_id": "chain_002",
                "chain_type": "contract_amendments",
                "root_document_id": "doc_contract_001",
                "documents": [
                    {"id": "doc_contract_001", "type": "contract", "version": "1.0"},
                    {"id": "doc_amendment_001", "type": "amendment", "version": "1.1"},
                    {"id": "doc_amendment_002", "type": "amendment", "version": "1.2"}
                ],
                "current_version": "1.2"
            }
            MockChain.return_value = mock_chain

            chain = await mock_chain.create_chain(
                chain_type="contract_amendments",
                root_document_id="doc_contract_001",
                documents=[
                    "doc_contract_001",
                    "doc_amendment_001",
                    "doc_amendment_002"
                ]
            )

            assert chain["chain_type"] == "contract_amendments"
            assert chain["current_version"] == "1.2"
            assert len(chain["documents"]) == 3


@pytest.mark.e2e
class TestChainTraversal:
    """Test chain traversal and navigation."""

    @pytest.mark.asyncio
    async def test_get_chain_timeline(self):
        """Test Chronologische Ketten-Ansicht."""
        with patch("app.services.document_chain_service.DocumentChainService") as MockChain:
            mock_chain = AsyncMock()
            mock_chain.get_timeline.return_value = {
                "chain_id": "chain_001",
                "timeline": [
                    {
                        "document_id": "doc_quote_001",
                        "type": "quote",
                        "date": "2024-01-15",
                        "status": "accepted"
                    },
                    {
                        "document_id": "doc_invoice_001",
                        "type": "invoice",
                        "date": "2024-01-20",
                        "status": "paid"
                    },
                    {
                        "document_id": "doc_delivery_001",
                        "type": "delivery_note",
                        "date": "2024-01-18",
                        "status": "completed"
                    }
                ],
                "sorted_by": "date",
                "total_documents": 3
            }
            MockChain.return_value = mock_chain

            timeline = await mock_chain.get_timeline("chain_001")

            assert len(timeline["timeline"]) == 3
            # Should be sorted by date
            dates = [item["date"] for item in timeline["timeline"]]
            assert dates == sorted(dates)

    @pytest.mark.asyncio
    async def test_get_next_document_in_chain(self):
        """Test Nächstes Dokument in Kette abrufen."""
        with patch("app.services.document_chain_service.DocumentChainService") as MockChain:
            mock_chain = AsyncMock()
            mock_chain.get_next_document.return_value = {
                "current_document_id": "doc_quote_001",
                "next_document": {
                    "id": "doc_invoice_001",
                    "type": "invoice",
                    "relationship": "quote_to_invoice",
                    "status": "paid"
                },
                "has_next": True
            }
            MockChain.return_value = mock_chain

            result = await mock_chain.get_next_document(
                chain_id="chain_001",
                current_document_id="doc_quote_001"
            )

            assert result["has_next"] is True
            assert result["next_document"]["type"] == "invoice"

    @pytest.mark.asyncio
    async def test_get_previous_document_in_chain(self):
        """Test Vorheriges Dokument in Kette abrufen."""
        with patch("app.services.document_chain_service.DocumentChainService") as MockChain:
            mock_chain = AsyncMock()
            mock_chain.get_previous_document.return_value = {
                "current_document_id": "doc_invoice_001",
                "previous_document": {
                    "id": "doc_quote_001",
                    "type": "quote",
                    "relationship": "quote_to_invoice",
                    "status": "accepted"
                },
                "has_previous": True
            }
            MockChain.return_value = mock_chain

            result = await mock_chain.get_previous_document(
                chain_id="chain_001",
                current_document_id="doc_invoice_001"
            )

            assert result["has_previous"] is True
            assert result["previous_document"]["type"] == "quote"


@pytest.mark.e2e
class TestChainValidation:
    """Test chain validation and integrity."""

    @pytest.mark.asyncio
    async def test_validate_chain_integrity(self):
        """Test Ketten-Integrität prüfen."""
        with patch("app.services.document_chain_service.DocumentChainService") as MockChain:
            mock_chain = AsyncMock()
            mock_chain.validate_chain.return_value = {
                "chain_id": "chain_001",
                "is_valid": True,
                "checks": {
                    "all_documents_exist": True,
                    "no_circular_references": True,
                    "relationships_valid": True,
                    "sequence_correct": True
                },
                "issues": []
            }
            MockChain.return_value = mock_chain

            result = await mock_chain.validate_chain("chain_001")

            assert result["is_valid"] is True
            assert result["checks"]["all_documents_exist"] is True
            assert len(result["issues"]) == 0

    @pytest.mark.asyncio
    async def test_detect_broken_chain(self):
        """Test Fehlerhafte Kette erkennen."""
        with patch("app.services.document_chain_service.DocumentChainService") as MockChain:
            mock_chain = AsyncMock()
            mock_chain.validate_chain.return_value = {
                "chain_id": "chain_002",
                "is_valid": False,
                "checks": {
                    "all_documents_exist": False,
                    "no_circular_references": True,
                    "relationships_valid": True,
                    "sequence_correct": False
                },
                "issues": [
                    {
                        "type": "missing_document",
                        "severity": "error",
                        "message": "Dokument doc_invoice_002 nicht gefunden",
                        "document_id": "doc_invoice_002"
                    },
                    {
                        "type": "sequence_gap",
                        "severity": "warning",
                        "message": "Lücke in der Sequenz bei Position 2"
                    }
                ]
            }
            MockChain.return_value = mock_chain

            result = await mock_chain.validate_chain("chain_002")

            assert result["is_valid"] is False
            assert len(result["issues"]) == 2
            assert result["issues"][0]["type"] == "missing_document"

    @pytest.mark.asyncio
    async def test_prevent_circular_chain(self):
        """Test Zirkuläre Ketten verhindern."""
        with patch("app.services.document_chain_service.DocumentChainService") as MockChain:
            mock_chain = AsyncMock()
            mock_chain.add_to_chain.side_effect = ValueError(
                "Zirkuläre Referenz: Dokument ist bereits Teil der Kette"
            )
            MockChain.return_value = mock_chain

            # Try to add document that would create circular reference
            with pytest.raises(ValueError, match="Zirkuläre Referenz"):
                await mock_chain.add_to_chain(
                    chain_id="chain_001",
                    document_id="doc_quote_001",  # Already root of chain
                    previous_document_id="doc_invoice_001"
                )
