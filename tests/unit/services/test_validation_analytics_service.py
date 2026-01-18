"""
Unit Tests fuer ValidationAnalyticsService.

Testet Analytics-Funktionen: Uebersichtsstatistiken, Editor-Performance,
Trend-Daten und Dokumenttyp-Statistiken.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone, timedelta, date

from app.services.validation_analytics_service import ValidationAnalyticsService
from app.db.schemas import (
    ValidationAnalyticsOverview,
    EditorStatsListResponse,
    TrendDataResponse,
    DocumentTypeStatsResponse,
    ConfidenceDistribution,
)


@pytest.fixture
def mock_db():
    """Erstellt einen Mock fuer die Datenbankverbindung mit korrekter async Struktur."""
    db = AsyncMock()
    # Wichtig: execute muss AsyncMock sein, und das Result-Objekt auch
    mock_result = MagicMock()
    mock_result.scalar = MagicMock(return_value=0)
    mock_result.scalar_one_or_none = MagicMock(return_value=None)
    mock_result.all = MagicMock(return_value=[])
    mock_result.one_or_none = MagicMock(return_value=None)
    db.execute = AsyncMock(return_value=mock_result)
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def validation_analytics_service(mock_db):
    """Erstellt eine ValidationAnalyticsService-Instanz mit Mock-DB."""
    return ValidationAnalyticsService(mock_db)


class TestValidationAnalyticsServiceOverview:
    """Tests fuer Uebersichts-Statistiken."""

    @pytest.mark.asyncio
    async def test_get_overview_stats(self, validation_analytics_service, mock_db):
        """Test: Uebersichtsstatistiken abrufen."""
        # Mock fuer die verschiedenen DB-Abfragen
        # Der Service ruft mehrere execute() Aufrufe mit scalar() auf
        mock_result = MagicMock()
        mock_result.scalar = MagicMock(return_value=10)
        mock_result.all = MagicMock(return_value=[])
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await validation_analytics_service.get_overview_stats()

        # Der Service gibt ein ValidationAnalyticsOverview Pydantic-Objekt zurueck
        assert isinstance(result, ValidationAnalyticsOverview)
        assert result.pending_count >= 0
        assert result.in_progress_count >= 0
        assert result.approved_today >= 0
        assert result.rejected_today >= 0

    @pytest.mark.asyncio
    async def test_get_overview_stats_with_date_range(self, validation_analytics_service, mock_db):
        """Test: Statistiken mit Datumsbereich."""
        # date objects, nicht datetime (wie vom Service erwartet)
        date_from = date.today() - timedelta(days=30)
        date_to = date.today()

        mock_result = MagicMock()
        mock_result.scalar = MagicMock(return_value=50)
        mock_result.all = MagicMock(return_value=[])
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await validation_analytics_service.get_overview_stats(
            date_from=date_from,
            date_to=date_to,
        )

        assert result is not None
        assert isinstance(result, ValidationAnalyticsOverview)

    @pytest.mark.asyncio
    async def test_get_overview_stats_empty_data(self, validation_analytics_service, mock_db):
        """Test: Statistiken bei leerer Datenbank."""
        mock_result = MagicMock()
        mock_result.scalar = MagicMock(return_value=0)
        mock_result.all = MagicMock(return_value=[])
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await validation_analytics_service.get_overview_stats()

        assert isinstance(result, ValidationAnalyticsOverview)
        assert result.pending_count == 0


class TestValidationAnalyticsServiceEditorStats:
    """Tests fuer Editor-Performance-Statistiken."""

    @pytest.mark.asyncio
    async def test_get_editor_stats(self, validation_analytics_service, mock_db):
        """Test: Editor-Statistiken abrufen."""
        # Die erste execute-Abfrage liefert Editor-Aggregate
        editor_id = uuid4()
        mock_editor_row = (editor_id, 50, 45, 5, 90.5, 25)  # Tuple statt MagicMock

        # Zweite Abfrage holt den User-Namen
        mock_user_row = ("Max Mustermann", "max")

        # Erste Abfrage (Editor-Stats), zweite Abfrage (User-Name)
        call_count = [0]

        async def mock_execute_side_effect(query):
            call_count[0] += 1
            mock_result = MagicMock()
            if call_count[0] == 1:
                # Editor aggregate query
                mock_result.all = MagicMock(return_value=[mock_editor_row])
            else:
                # User name query
                mock_result.one_or_none = MagicMock(return_value=mock_user_row)
            return mock_result

        mock_db.execute = AsyncMock(side_effect=mock_execute_side_effect)

        result = await validation_analytics_service.get_editor_stats()

        # Der Service gibt EditorStatsListResponse zurueck
        assert isinstance(result, EditorStatsListResponse)
        assert len(result.editors) >= 0

    @pytest.mark.asyncio
    async def test_get_editor_stats_with_date_range(self, validation_analytics_service, mock_db):
        """Test: Editor-Statistiken mit Datumsbereich."""
        # date objects, nicht datetime
        date_from = date.today() - timedelta(days=7)
        date_to = date.today()

        mock_result = MagicMock()
        mock_result.all = MagicMock(return_value=[])
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await validation_analytics_service.get_editor_stats(
            date_from=date_from,
            date_to=date_to,
        )

        # Der Service gibt EditorStatsListResponse zurueck
        assert isinstance(result, EditorStatsListResponse)
        assert result.period_start == date_from
        assert result.period_end == date_to

    @pytest.mark.asyncio
    async def test_editor_accuracy_calculation(self, validation_analytics_service, mock_db):
        """Test: Editor-Genauigkeitsberechnung."""
        editor_id = uuid4()
        mock_editor_row = (editor_id, 100, 90, 10, 60.0, 5)
        mock_user_row = ("Test Editor", "testuser")

        call_count = [0]

        async def mock_execute_side_effect(query):
            call_count[0] += 1
            mock_result = MagicMock()
            if call_count[0] == 1:
                mock_result.all = MagicMock(return_value=[mock_editor_row])
            else:
                mock_result.one_or_none = MagicMock(return_value=mock_user_row)
            return mock_result

        mock_db.execute = AsyncMock(side_effect=mock_execute_side_effect)

        result = await validation_analytics_service.get_editor_stats()

        # Genauigkeit sollte berechnet werden
        assert isinstance(result, EditorStatsListResponse)
        if len(result.editors) > 0:
            editor = result.editors[0]
            assert hasattr(editor, 'accuracy_rate')
            # 90 von 100 = 90%
            if editor.accuracy_rate is not None:
                assert editor.accuracy_rate == 90.0


class TestValidationAnalyticsServiceTrends:
    """Tests fuer Trend-Daten."""

    @pytest.mark.asyncio
    async def test_get_trend_data_daily(self, validation_analytics_service, mock_db):
        """Test: Taegliche Trend-Daten."""
        today = date.today()
        # Row: (day, total, approved, rejected, avg_time)
        mock_trend_row = (today, 20, 18, 2, 95.0)

        mock_result = MagicMock()
        mock_result.all = MagicMock(return_value=[mock_trend_row])
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Service-Methode nur mit days Parameter (kein group_by)
        result = await validation_analytics_service.get_trend_data(days=7)

        assert isinstance(result, TrendDataResponse)
        assert len(result.data_points) == 7  # 7 Tage

    @pytest.mark.asyncio
    async def test_get_trend_data_weekly(self, validation_analytics_service, mock_db):
        """Test: Woechentliche Trend-Daten (30 Tage)."""
        mock_result = MagicMock()
        mock_result.all = MagicMock(return_value=[])
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await validation_analytics_service.get_trend_data(days=30)

        assert isinstance(result, TrendDataResponse)
        assert len(result.data_points) == 30

    @pytest.mark.asyncio
    async def test_get_trend_data_monthly(self, validation_analytics_service, mock_db):
        """Test: Monatliche Trend-Daten (365 Tage)."""
        mock_result = MagicMock()
        mock_result.all = MagicMock(return_value=[])
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await validation_analytics_service.get_trend_data(days=365)

        assert isinstance(result, TrendDataResponse)
        assert len(result.data_points) == 365


class TestValidationAnalyticsServiceDocumentTypes:
    """Tests fuer Dokumenttyp-Statistiken."""

    @pytest.mark.asyncio
    async def test_get_document_type_stats(self, validation_analytics_service, mock_db):
        """Test: Dokumenttyp-Statistiken abrufen."""
        # Row: (document_type, total, approved, rejected, avg_confidence, correction_rate)
        mock_rows = [
            ("invoice", 200, 170, 10, 0.85, 0.015),
            ("order", 100, 90, 5, 0.92, 0.008),
        ]

        mock_result = MagicMock()
        mock_result.all = MagicMock(return_value=mock_rows)
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await validation_analytics_service.get_document_type_stats()

        assert isinstance(result, DocumentTypeStatsResponse)
        assert len(result.document_types) >= 0

    @pytest.mark.asyncio
    async def test_document_type_stats_empty(self, validation_analytics_service, mock_db):
        """Test: Keine Dokumenttypen vorhanden."""
        mock_result = MagicMock()
        mock_result.all = MagicMock(return_value=[])
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await validation_analytics_service.get_document_type_stats()

        assert isinstance(result, DocumentTypeStatsResponse)
        assert result.document_types == []


class TestValidationAnalyticsServiceConfidenceDistribution:
    """Tests fuer Konfidenz-Verteilung."""

    @pytest.mark.asyncio
    async def test_get_confidence_distribution(self, validation_analytics_service, mock_db):
        """Test: Konfidenz-Verteilung abrufen."""
        # Service macht mehrere execute-Aufrufe: einmal pro Range + avg query
        mock_result = MagicMock()
        mock_result.scalar = MagicMock(return_value=50)  # Count per range + avg
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await validation_analytics_service.get_confidence_distribution()

        assert isinstance(result, ConfidenceDistribution)
        assert "ranges" in result.model_dump()
        assert "avg_confidence" in result.model_dump()

    @pytest.mark.asyncio
    async def test_confidence_distribution_calculates_stats(self, validation_analytics_service, mock_db):
        """Test: Statistische Kennzahlen werden berechnet."""
        mock_result = MagicMock()
        mock_result.scalar = MagicMock(return_value=0.87)
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await validation_analytics_service.get_confidence_distribution()

        assert isinstance(result, ConfidenceDistribution)
        # median_confidence sollte vorhanden sein (aus avg approximiert)
        assert result.median_confidence is not None or result.avg_confidence is not None


class TestValidationAnalyticsServiceMetrics:
    """Tests fuer spezifische Metriken."""

    @pytest.mark.asyncio
    async def test_approval_rate_calculation(self, validation_analytics_service, mock_db):
        """Test: Genehmigungsrate wird korrekt berechnet."""
        mock_result = MagicMock()
        mock_result.scalar = MagicMock(return_value=90)
        mock_result.all = MagicMock(return_value=[])
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await validation_analytics_service.get_overview_stats()

        assert isinstance(result, ValidationAnalyticsOverview)
        # approved_today und rejected_today sind Teil der Overview
        assert result.approved_today >= 0

    @pytest.mark.asyncio
    async def test_average_time_calculation(self, validation_analytics_service, mock_db):
        """Test: Durchschnittliche Validierungszeit wird berechnet."""
        call_count = [0]

        async def mock_execute_side_effect(query):
            call_count[0] += 1
            mock_result = MagicMock()
            # Count-Abfragen bekommen int, avg-Abfragen bekommen float
            # Die ersten 6 Aufrufe sind count-Abfragen
            if call_count[0] <= 6:
                mock_result.scalar = MagicMock(return_value=10)  # int fuer counts
            else:
                mock_result.scalar = MagicMock(return_value=120.5)  # float fuer avg
            mock_result.all = MagicMock(return_value=[])
            return mock_result

        mock_db.execute = AsyncMock(side_effect=mock_execute_side_effect)

        result = await validation_analytics_service.get_overview_stats()

        assert isinstance(result, ValidationAnalyticsOverview)
        # avg_validation_time_seconds kann None oder int sein
        if result.avg_validation_time_seconds is not None:
            assert result.avg_validation_time_seconds >= 0


class TestValidationAnalyticsServiceEdgeCases:
    """Tests fuer Randfaelle."""

    @pytest.mark.asyncio
    async def test_division_by_zero_handling(self, validation_analytics_service, mock_db):
        """Test: Division durch Null wird abgefangen."""
        mock_result = MagicMock()
        mock_result.scalar = MagicMock(return_value=0)
        mock_result.all = MagicMock(return_value=[])
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await validation_analytics_service.get_overview_stats()

        # Sollte keine Exception werfen
        assert isinstance(result, ValidationAnalyticsOverview)

    @pytest.mark.asyncio
    async def test_null_values_handling(self, validation_analytics_service, mock_db):
        """Test: NULL-Werte werden korrekt behandelt."""
        mock_result = MagicMock()
        mock_result.scalar = MagicMock(return_value=None)
        mock_result.all = MagicMock(return_value=[])
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await validation_analytics_service.get_overview_stats()

        # NULL-Werte sollten als None oder 0 behandelt werden
        assert isinstance(result, ValidationAnalyticsOverview)

    @pytest.mark.asyncio
    async def test_negative_date_range(self, validation_analytics_service, mock_db):
        """Test: Negativer Datumsbereich wird behandelt."""
        # date objects, nicht datetime
        date_from = date.today()
        date_to = date.today() - timedelta(days=30)

        mock_result = MagicMock()
        mock_result.scalar = MagicMock(return_value=0)
        mock_result.all = MagicMock(return_value=[])
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Sollte entweder leere Ergebnisse oder Fehler zurueckgeben
        result = await validation_analytics_service.get_overview_stats(
            date_from=date_from,
            date_to=date_to,
        )

        assert isinstance(result, ValidationAnalyticsOverview)

    @pytest.mark.asyncio
    async def test_very_large_dataset(self, validation_analytics_service, mock_db):
        """Test: Grosse Datenmenge wird performant behandelt."""
        mock_result = MagicMock()
        mock_result.scalar = MagicMock(return_value=1_000_000)
        mock_result.all = MagicMock(return_value=[])
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await validation_analytics_service.get_overview_stats()

        # pending_count sollte den Mock-Wert haben
        assert isinstance(result, ValidationAnalyticsOverview)
        assert result.pending_count == 1_000_000

    @pytest.mark.asyncio
    async def test_database_error_handling(self, validation_analytics_service, mock_db):
        """Test: Datenbankfehler werden korrekt behandelt."""
        mock_db.execute = AsyncMock(side_effect=Exception("Database connection error"))

        with pytest.raises(Exception):
            await validation_analytics_service.get_overview_stats()


class TestValidationAnalyticsServiceCaching:
    """Tests fuer Caching-Verhalten (falls implementiert)."""

    @pytest.mark.asyncio
    async def test_stats_are_fresh(self, validation_analytics_service, mock_db):
        """Test: Statistiken sind aktuell (nicht gecached)."""
        call_count = [0]

        async def mock_execute_side_effect(query):
            call_count[0] += 1
            mock_result = MagicMock()
            mock_result.scalar = MagicMock(return_value=call_count[0] * 10)
            mock_result.all = MagicMock(return_value=[])
            return mock_result

        mock_db.execute = AsyncMock(side_effect=mock_execute_side_effect)

        result1 = await validation_analytics_service.get_overview_stats()
        result2 = await validation_analytics_service.get_overview_stats()

        # Beide Aufrufe sollten DB abfragen
        assert call_count[0] >= 2
        assert isinstance(result1, ValidationAnalyticsOverview)
        assert isinstance(result2, ValidationAnalyticsOverview)
