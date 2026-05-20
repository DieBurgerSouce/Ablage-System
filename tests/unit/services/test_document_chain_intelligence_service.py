# -*- coding: utf-8 -*-
"""Unit tests fuer Document Chain Intelligence Service.

Tests fuer:
- _find_gaps_in_chain (Lueckenerkennung in einzelnen Ketten)
- _generate_new_chain_suggestions (Vorschlaege fuer neue Ketten)
- detect_orphan_documents (Verwaiste Dokumente erkennen)
- scan_for_gaps (Gesamtscan aller Ketten)
- suggest_chain_completions (Vervollstaendigungsvorschlaege)
- Severity-Berechnung (info/warning/critical)
- Leere Eingabelisten (keine Crashes)
"""

import pytest
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.document_chain_intelligence_service import (
    DocumentChainIntelligenceService,
    ChainGap,
    ChainIntelligenceReport,
    OrphanDocument,
    EXPECTED_NEXT_TYPE,
    GAP_SEVERITY_THRESHOLDS,
    DOCUMENT_TYPE_LABELS,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def service():
    """Erstellt Intelligence Service mit gemocktem Chain Service."""
    with patch(
        "app.services.document_chain_intelligence_service.ExtendedDocumentChainServiceV2"
    ):
        svc = DocumentChainIntelligenceService()
        svc._chain_service = MagicMock()
        return svc


@pytest.fixture
def company_id():
    """Test-Firmen-ID."""
    return uuid4()


@pytest.fixture
def mock_db():
    """Mock database session."""
    db = AsyncMock()
    return db


def _make_now():
    """Aktueller Zeitpunkt."""
    return datetime.now(timezone.utc)


# =============================================================================
# TESTS: _find_gaps_in_chain
# =============================================================================


class TestFindGapsInChain:
    """Tests fuer die Lueckenerkennung in einer Kette."""

    def test_erkennt_luecke_wenn_naechster_typ_fehlt(self, service):
        """Luecke wird erkannt wenn Auftrag vorhanden aber Lieferschein fehlt."""
        now = _make_now()
        doc_types: Set[str] = {"quote", "order"}
        next_types_map: Dict[str, str] = {
            "quote": "order",
            "order": "delivery_note",
            "delivery_note": "invoice",
        }

        gaps = service._find_gaps_in_chain(
            chain_id="CHAIN-001",
            chain_name="Testkette",
            chain_type="quote_to_invoice",
            doc_types=doc_types,
            next_types_map=next_types_map,
            latest_doc_date=now - timedelta(days=5),
            latest_doc_name="Auftrag-123.pdf",
            now=now,
        )

        # order -> delivery_note fehlt
        assert len(gaps) == 1
        gap = gaps[0]
        assert gap.chain_id == "CHAIN-001"
        assert gap.chain_name == "Testkette"
        assert gap.expected_type == DOCUMENT_TYPE_LABELS.get("delivery_note", "delivery_note")
        assert gap.after_document == "Auftrag-123.pdf"
        assert gap.days_overdue == 5

    def test_keine_luecke_wenn_kette_komplett(self, service):
        """Keine Luecke wenn alle Typen vorhanden."""
        now = _make_now()
        doc_types: Set[str] = {"quote", "order", "delivery_note", "invoice"}
        next_types_map: Dict[str, str] = {
            "quote": "order",
            "order": "delivery_note",
            "delivery_note": "invoice",
        }

        gaps = service._find_gaps_in_chain(
            chain_id="CHAIN-002",
            chain_name="Komplette Kette",
            chain_type="quote_to_invoice",
            doc_types=doc_types,
            next_types_map=next_types_map,
            latest_doc_date=now,
            latest_doc_name="Rechnung-456.pdf",
            now=now,
        )

        assert len(gaps) == 0

    def test_leere_next_types_map_ergibt_keine_luecken(self, service):
        """Leere Zuordnung soll keine Luecken produzieren."""
        now = _make_now()
        gaps = service._find_gaps_in_chain(
            chain_id="CHAIN-003",
            chain_name="Leere Kette",
            chain_type="unknown",
            doc_types={"invoice"},
            next_types_map={},
            latest_doc_date=now,
            latest_doc_name="doc.pdf",
            now=now,
        )

        assert gaps == []

    def test_mehrere_luecken_in_einer_kette(self, service):
        """Mehrere Luecken wenn mehrere Typen fehlen."""
        now = _make_now()
        # Nur quote vorhanden, aber order und delivery_note fehlen
        # quote -> order (order fehlt = Luecke)
        # order -> delivery_note (order nicht da, kein Match)
        # delivery_note -> invoice (delivery_note nicht da, kein Match)
        doc_types: Set[str] = {"quote", "delivery_note"}
        next_types_map: Dict[str, str] = {
            "quote": "order",
            "order": "delivery_note",
            "delivery_note": "invoice",
        }

        gaps = service._find_gaps_in_chain(
            chain_id="CHAIN-004",
            chain_name="Lueckenhafte Kette",
            chain_type="quote_to_invoice",
            doc_types=doc_types,
            next_types_map=next_types_map,
            latest_doc_date=now - timedelta(days=3),
            latest_doc_name="Lieferschein.pdf",
            now=now,
        )

        # quote vorhanden, order fehlt = 1 Luecke
        # delivery_note vorhanden, invoice fehlt = 1 Luecke
        assert len(gaps) == 2
        expected_types = {g.expected_type for g in gaps}
        assert DOCUMENT_TYPE_LABELS["order"] in expected_types
        assert DOCUMENT_TYPE_LABELS["invoice"] in expected_types


# =============================================================================
# TESTS: Severity-Berechnung
# =============================================================================


class TestSeverityBerechnung:
    """Tests fuer die Severity-Zuweisung bei Luecken."""

    def test_severity_info_bei_neuer_luecke(self, service):
        """Severity 'info' wenn wenige Tage ueberfaellig."""
        now = _make_now()
        gaps = service._find_gaps_in_chain(
            chain_id="CHAIN-SEV1",
            chain_name="Info Kette",
            chain_type="quote_to_invoice",
            doc_types={"order"},
            next_types_map={"order": "delivery_note"},
            latest_doc_date=now - timedelta(days=5),
            latest_doc_name="doc.pdf",
            now=now,
        )

        assert len(gaps) == 1
        assert gaps[0].severity == "info"
        assert gaps[0].days_overdue == 5

    def test_severity_warning_bei_14_plus_tagen(self, service):
        """Severity 'warning' wenn > 14 Tage ueberfaellig."""
        now = _make_now()
        gaps = service._find_gaps_in_chain(
            chain_id="CHAIN-SEV2",
            chain_name="Warning Kette",
            chain_type="quote_to_invoice",
            doc_types={"order"},
            next_types_map={"order": "delivery_note"},
            latest_doc_date=now - timedelta(days=20),
            latest_doc_name="doc.pdf",
            now=now,
        )

        assert len(gaps) == 1
        assert gaps[0].severity == "warning"
        assert gaps[0].days_overdue == 20

    def test_severity_critical_bei_30_plus_tagen(self, service):
        """Severity 'critical' wenn > 30 Tage ueberfaellig."""
        now = _make_now()
        gaps = service._find_gaps_in_chain(
            chain_id="CHAIN-SEV3",
            chain_name="Kritische Kette",
            chain_type="quote_to_invoice",
            doc_types={"order"},
            next_types_map={"order": "delivery_note"},
            latest_doc_date=now - timedelta(days=45),
            latest_doc_name="doc.pdf",
            now=now,
        )

        assert len(gaps) == 1
        assert gaps[0].severity == "critical"
        assert gaps[0].days_overdue == 45

    def test_severity_info_ohne_datum(self, service):
        """Severity 'info' wenn kein Datum vorhanden (days_overdue=0)."""
        now = _make_now()
        gaps = service._find_gaps_in_chain(
            chain_id="CHAIN-SEV4",
            chain_name="Ohne Datum",
            chain_type="quote_to_invoice",
            doc_types={"order"},
            next_types_map={"order": "delivery_note"},
            latest_doc_date=None,
            latest_doc_name="doc.pdf",
            now=now,
        )

        assert len(gaps) == 1
        assert gaps[0].severity == "info"
        assert gaps[0].days_overdue == 0


# =============================================================================
# TESTS: _generate_new_chain_suggestions
# =============================================================================


class TestGenerateNewChainSuggestions:
    """Tests fuer Vorschlaege fuer neue Ketten."""

    def test_vorschlag_bei_gemeinsamer_referenz(self, service):
        """Vorschlag wenn 2+ Orphans die gleiche Referenznummer haben."""
        orphans = [
            OrphanDocument(
                document_id="doc-1",
                filename="Angebot.pdf",
                document_type="quote",
                document_date=None,
                reference_numbers={"order_number": "B-2026-001"},
                potential_chain_ids=[],
                match_confidence=0.0,
            ),
            OrphanDocument(
                document_id="doc-2",
                filename="Rechnung.pdf",
                document_type="invoice",
                document_date=None,
                reference_numbers={"order_number": "B-2026-001"},
                potential_chain_ids=[],
                match_confidence=0.0,
            ),
        ]

        suggestions = service._generate_new_chain_suggestions(orphans)

        assert len(suggestions) == 1
        assert suggestions[0]["reference_value"] == "B-2026-001"
        assert suggestions[0]["document_count"] == "2"
        assert "Gemeinsame Referenz" in suggestions[0]["reason"]

    def test_kein_vorschlag_bei_einzelnem_orphan(self, service):
        """Kein Vorschlag wenn nur ein Orphan pro Referenz."""
        orphans = [
            OrphanDocument(
                document_id="doc-1",
                filename="Allein.pdf",
                document_type="invoice",
                document_date=None,
                reference_numbers={"invoice_number": "R-001"},
                potential_chain_ids=[],
                match_confidence=0.0,
            ),
        ]

        suggestions = service._generate_new_chain_suggestions(orphans)
        assert suggestions == []

    def test_leere_orphan_liste(self, service):
        """Leere Liste ergibt keine Vorschlaege."""
        suggestions = service._generate_new_chain_suggestions([])
        assert suggestions == []

    def test_orphans_ohne_referenznummern(self, service):
        """Orphans ohne Referenznummern erzeugen keine Vorschlaege."""
        orphans = [
            OrphanDocument(
                document_id="doc-1",
                filename="Ohne-Ref.pdf",
                document_type="invoice",
                document_date=None,
                reference_numbers={},
                potential_chain_ids=[],
                match_confidence=0.0,
            ),
            OrphanDocument(
                document_id="doc-2",
                filename="Auch-Ohne.pdf",
                document_type="quote",
                document_date=None,
                reference_numbers={},
                potential_chain_ids=[],
                match_confidence=0.0,
            ),
        ]

        suggestions = service._generate_new_chain_suggestions(orphans)
        assert suggestions == []

    def test_max_20_vorschlaege(self, service):
        """Maximal 20 Vorschlaege zurueckgegeben."""
        orphans = []
        for i in range(25):
            ref = f"REF-{i:03d}"
            orphans.append(OrphanDocument(
                document_id=f"doc-a-{i}",
                filename=f"A-{i}.pdf",
                document_type="quote",
                document_date=None,
                reference_numbers={"order_number": ref},
            ))
            orphans.append(OrphanDocument(
                document_id=f"doc-b-{i}",
                filename=f"B-{i}.pdf",
                document_type="invoice",
                document_date=None,
                reference_numbers={"order_number": ref},
            ))

        suggestions = service._generate_new_chain_suggestions(orphans)
        assert len(suggestions) <= 20


# =============================================================================
# TESTS: detect_orphan_documents (async)
# =============================================================================


class TestDetectOrphanDocuments:
    """Tests fuer die Erkennung verwaister Dokumente."""

    @pytest.mark.asyncio
    async def test_erkennt_orphans_ohne_chain(self, service, company_id, mock_db):
        """Dokumente ohne chain_id werden als Orphans erkannt."""
        mock_doc = MagicMock()
        mock_doc.id = uuid4()
        mock_doc.original_filename = "Verwaiste-Rechnung.pdf"
        mock_doc.document_type = "invoice"
        mock_doc.processed_date = None
        mock_doc.document_metadata = {
            "extracted_data": {
                "invoice_number": "R-2026-123"
            }
        }

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_doc]
        mock_db.execute = AsyncMock(return_value=mock_result)

        orphans = await service.detect_orphan_documents(company_id, mock_db)

        assert len(orphans) == 1
        assert orphans[0].filename == "Verwaiste-Rechnung.pdf"
        assert orphans[0].document_type == "invoice"
        assert "invoice_number" in orphans[0].reference_numbers
        assert orphans[0].reference_numbers["invoice_number"] == "R-2026-123"

    @pytest.mark.asyncio
    async def test_leere_ergebnisse_bei_keinen_orphans(self, service, company_id, mock_db):
        """Leere Liste wenn keine verwaisten Dokumente."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        orphans = await service.detect_orphan_documents(company_id, mock_db)

        assert orphans == []

    @pytest.mark.asyncio
    async def test_orphan_ohne_metadata(self, service, company_id, mock_db):
        """Orphan ohne Metadata hat leere Referenznummern."""
        mock_doc = MagicMock()
        mock_doc.id = uuid4()
        mock_doc.original_filename = "Ohne-Meta.pdf"
        mock_doc.document_type = "quote"
        mock_doc.processed_date = None
        mock_doc.document_metadata = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_doc]
        mock_db.execute = AsyncMock(return_value=mock_result)

        orphans = await service.detect_orphan_documents(company_id, mock_db)

        assert len(orphans) == 1
        assert orphans[0].reference_numbers == {}
        assert orphans[0].match_confidence == 0.0

    @pytest.mark.asyncio
    async def test_orphan_mit_potential_chains(self, service, company_id, mock_db):
        """Orphan mit Referenznummern die zu bestehenden Ketten passen."""
        mock_doc = MagicMock()
        mock_doc.id = uuid4()
        mock_doc.original_filename = "Passende-Rechnung.pdf"
        mock_doc.document_type = "invoice"
        mock_doc.processed_date = datetime(2026, 1, 15, tzinfo=timezone.utc)
        mock_doc.document_metadata = {
            "extracted_data": {
                "order_number": "AUF-2026-001"
            }
        }

        # Erste Abfrage: Orphan-Dokumente
        mock_orphan_result = MagicMock()
        mock_orphan_result.scalars.return_value.all.return_value = [mock_doc]

        # Zweite Abfrage: Referenz-Suche findet chain_id
        mock_chain_result = MagicMock()
        mock_chain_result.fetchall.return_value = [("CHAIN-EXISTING-001",)]

        mock_db.execute = AsyncMock(side_effect=[mock_orphan_result, mock_chain_result])

        orphans = await service.detect_orphan_documents(company_id, mock_db)

        assert len(orphans) == 1
        assert orphans[0].potential_chain_ids == ["CHAIN-EXISTING-001"]
        assert orphans[0].match_confidence == 0.7


# =============================================================================
# TESTS: scan_for_gaps (async)
# =============================================================================


class TestScanForGaps:
    """Tests fuer den Gesamtscan aller Ketten."""

    @pytest.mark.asyncio
    async def test_report_bei_leerer_firma(self, service, company_id, mock_db):
        """Report mit Nullwerten wenn keine Ketten vorhanden."""
        # Keine chain_ids gefunden
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        # detect_orphan_documents mocken
        service.detect_orphan_documents = AsyncMock(return_value=[])

        report = await service.scan_for_gaps(company_id, mock_db)

        assert isinstance(report, ChainIntelligenceReport)
        assert report.total_chains == 0
        assert report.complete_chains == 0
        assert report.chains_with_gaps == 0
        assert report.gaps == []
        assert report.orphan_documents == []
        assert report.average_completion == 0.0

    @pytest.mark.asyncio
    async def test_report_mit_kompletter_kette(self, service, company_id, mock_db):
        """Report zaehlt komplette Ketten korrekt."""
        # Eine chain_id gefunden
        mock_chain_ids_result = MagicMock()
        mock_chain_ids_result.fetchall.return_value = [("CHAIN-COMPLETE",)]
        mock_db.execute = AsyncMock(return_value=mock_chain_ids_result)

        # Chain ist komplett
        mock_chain = MagicMock()
        mock_chain.is_complete = True
        mock_chain.completion_percentage = 100.0
        mock_chain.chain_type.value = "quote_to_invoice"
        mock_chain.documents = []
        service._chain_service.get_extended_chain = AsyncMock(return_value=mock_chain)

        # Keine Orphans
        service.detect_orphan_documents = AsyncMock(return_value=[])

        report = await service.scan_for_gaps(company_id, mock_db)

        assert report.total_chains == 1
        assert report.complete_chains == 1
        assert report.chains_with_gaps == 0
        assert report.average_completion == 100.0


# =============================================================================
# TESTS: suggest_chain_completions (async)
# =============================================================================


class TestSuggestChainCompletions:
    """Tests fuer Vervollstaendigungsvorschlaege."""

    @pytest.mark.asyncio
    async def test_keine_vorschlaege_fuer_unbekannte_kette(self, service, mock_db, company_id):
        """Leere Liste wenn Kette nicht gefunden."""
        service._chain_service.get_extended_chain = AsyncMock(return_value=None)

        result = await service.suggest_chain_completions(
            chain_id="NICHT-VORHANDEN",
            db=mock_db,
            company_id=company_id,
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_vorschlaege_fuer_inkomplette_kette(self, service, mock_db, company_id):
        """Vorschlaege werden generiert fuer fehlende Dokumenttypen."""
        # Chain mit nur einem Dokument (order), delivery_note fehlt
        mock_doc = MagicMock()
        mock_doc.document_type = "order"
        mock_doc.sub_type = None
        mock_doc.entity_id = uuid4()
        mock_doc.document_date = datetime(2026, 1, 10, tzinfo=timezone.utc)
        mock_doc.filename = "Auftrag-A.pdf"

        mock_chain = MagicMock()
        mock_chain.chain_type.value = "order_to_delivery"
        mock_chain.is_complete = False
        mock_chain.completion_percentage = 33.0
        mock_chain.project_name = "Projekt Alpha"
        mock_chain.documents = [mock_doc]

        service._chain_service.get_extended_chain = AsyncMock(return_value=mock_chain)

        # Matching documents finden
        mock_match_result = MagicMock()
        mock_match_result.fetchall.return_value = [(uuid4(),)]
        mock_db.execute = AsyncMock(return_value=mock_match_result)

        gaps = await service.suggest_chain_completions(
            chain_id="CHAIN-PARTIAL",
            db=mock_db,
            company_id=company_id,
        )

        assert len(gaps) >= 1
        # Mindestens delivery_note sollte als fehlend erkannt werden
        gap_types = [g.expected_type for g in gaps]
        assert DOCUMENT_TYPE_LABELS["delivery_note"] in gap_types


# =============================================================================
# TESTS: Datenklassen
# =============================================================================


class TestDataClasses:
    """Tests fuer die Datenstrukturen."""

    def test_chain_gap_default_values(self):
        """ChainGap hat leere suggested_matches als Default."""
        gap = ChainGap(
            chain_id="C1",
            chain_name="Test",
            expected_type="Rechnung",
            after_document="doc.pdf",
            days_overdue=0,
            severity="info",
        )
        assert gap.suggested_matches == []

    def test_orphan_document_default_values(self):
        """OrphanDocument hat sinnvolle Defaults."""
        orphan = OrphanDocument(
            document_id="D1",
            filename="test.pdf",
            document_type="invoice",
            document_date=None,
        )
        assert orphan.reference_numbers == {}
        assert orphan.potential_chain_ids == []
        assert orphan.match_confidence == 0.0

    def test_chain_intelligence_report_structure(self):
        """ChainIntelligenceReport enthaelt alle Felder."""
        now = _make_now()
        report = ChainIntelligenceReport(
            total_chains=5,
            complete_chains=3,
            chains_with_gaps=2,
            gaps=[],
            orphan_documents=[],
            suggested_new_chains=[],
            scan_timestamp=now,
            average_completion=75.5,
        )
        assert report.total_chains == 5
        assert report.complete_chains == 3
        assert report.chains_with_gaps == 2
        assert report.average_completion == 75.5


# =============================================================================
# TESTS: Konstanten
# =============================================================================


class TestConstants:
    """Tests fuer die Konfigurationskonstanten."""

    def test_expected_next_type_hat_alle_kettentypen(self):
        """EXPECTED_NEXT_TYPE enthaelt Definitionen fuer alle Kettentypen."""
        assert "quote_to_invoice" in EXPECTED_NEXT_TYPE
        assert "order_to_delivery" in EXPECTED_NEXT_TYPE
        assert "contract_fulfillment" in EXPECTED_NEXT_TYPE
        assert "procurement" in EXPECTED_NEXT_TYPE

    def test_gap_severity_thresholds_sind_aufsteigend(self):
        """Schwellenwerte sind logisch aufsteigend."""
        assert GAP_SEVERITY_THRESHOLDS["info"] < GAP_SEVERITY_THRESHOLDS["warning"]
        assert GAP_SEVERITY_THRESHOLDS["warning"] < GAP_SEVERITY_THRESHOLDS["critical"]

    def test_document_type_labels_in_deutsch(self):
        """Alle Labels sind auf Deutsch."""
        assert DOCUMENT_TYPE_LABELS["invoice"] == "Rechnung"
        assert DOCUMENT_TYPE_LABELS["quote"] == "Angebot"
        assert DOCUMENT_TYPE_LABELS["delivery_note"] == "Lieferschein"
        assert DOCUMENT_TYPE_LABELS["order"] == "Auftrag"
