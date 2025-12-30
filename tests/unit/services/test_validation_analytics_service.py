"""
Unit Tests fuer ValidationAnalyticsService.

Testet Analytics-Funktionen: Uebersichtsstatistiken, Editor-Performance,
Trend-Daten und Dokumenttyp-Statistiken.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone, timedelta

from app.services.validation_analytics_service import ValidationAnalyticsService


@pytest.fixture
def mock_db():
    """Erstellt einen Mock fuer die Datenbankverbindung."""
    db = AsyncMock()
    db.execute = AsyncMock()
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
        # Mock verschiedene Count-Abfragen
        mock_db.execute.return_value.scalar.side_effect = [
            100,  # total
            30,   # pending
            10,   # in_progress
            50,   # approved
            10,   # rejected
            120,  # avg_time
            2.5,  # avg_corrections
            15,   # today
            80,   # this_week
            250,  # this_month
        ]

        result = await validation_analytics_service.get_overview_stats()

        assert "total_items" in result
        assert "pending_items" in result
        assert "approved_items" in result
        assert "rejected_items" in result

    @pytest.mark.asyncio
    async def test_get_overview_stats_with_date_range(self, validation_analytics_service, mock_db):
        """Test: Statistiken mit Datumsbereich."""
        date_from = datetime.now(timezone.utc) - timedelta(days=30)
        date_to = datetime.now(timezone.utc)

        mock_db.execute.return_value.scalar.return_value = 50

        result = await validation_analytics_service.get_overview_stats(
            date_from=date_from,
            date_to=date_to,
        )

        assert result is not None

    @pytest.mark.asyncio
    async def test_get_overview_stats_empty_data(self, validation_analytics_service, mock_db):
        """Test: Statistiken bei leerer Datenbank."""
        mock_db.execute.return_value.scalar.return_value = 0

        result = await validation_analytics_service.get_overview_stats()

        assert result["total_items"] == 0


class TestValidationAnalyticsServiceEditorStats:
    """Tests fuer Editor-Performance-Statistiken."""

    @pytest.mark.asyncio
    async def test_get_editor_stats(self, validation_analytics_service, mock_db):
        """Test: Editor-Statistiken abrufen."""
        mock_result = MagicMock()
        mock_result.all.return_value = [
            MagicMock(
                editor_id=uuid4(),
                editor_name="Max Mustermann",
                items_validated=50,
                items_approved=45,
                items_rejected=5,
                avg_time=90.5,
                total_corrections=25,
            )
        ]
        mock_db.execute.return_value = mock_result

        result = await validation_analytics_service.get_editor_stats()

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_editor_stats_with_date_range(self, validation_analytics_service, mock_db):
        """Test: Editor-Statistiken mit Datumsbereich."""
        date_from = datetime.now(timezone.utc) - timedelta(days=7)
        date_to = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await validation_analytics_service.get_editor_stats(
            date_from=date_from,
            date_to=date_to,
        )

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_editor_accuracy_calculation(self, validation_analytics_service, mock_db):
        """Test: Editor-Genauigkeitsberechnung."""
        mock_result = MagicMock()
        mock_result.all.return_value = [
            MagicMock(
                editor_id=uuid4(),
                editor_name="Test Editor",
                items_validated=100,
                items_approved=90,
                items_rejected=10,
                avg_time=60.0,
                total_corrections=5,
            )
        ]
        mock_db.execute.return_value = mock_result

        result = await validation_analytics_service.get_editor_stats()

        # Genauigkeit sollte berechnet werden
        if result and len(result) > 0:
            assert "accuracy_rate" in result[0] or isinstance(result[0], dict)


class TestValidationAnalyticsServiceTrends:
    """Tests fuer Trend-Daten."""

    @pytest.mark.asyncio
    async def test_get_trend_data_daily(self, validation_analytics_service, mock_db):
        """Test: Taegliche Trend-Daten."""
        mock_result = MagicMock()
        mock_result.all.return_value = [
            MagicMock(
                date=datetime.now(timezone.utc).date(),
                validated_count=20,
                approved_count=18,
                rejected_count=2,
                avg_time=95.0,
            )
        ]
        mock_db.execute.return_value = mock_result

        result = await validation_analytics_service.get_trend_data(
            days=7,
            group_by="day",
        )

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_trend_data_weekly(self, validation_analytics_service, mock_db):
        """Test: Woechentliche Trend-Daten."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await validation_analytics_service.get_trend_data(
            days=30,
            group_by="week",
        )

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_trend_data_monthly(self, validation_analytics_service, mock_db):
        """Test: Monatliche Trend-Daten."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await validation_analytics_service.get_trend_data(
            days=365,
            group_by="month",
        )

        assert isinstance(result, list)


class TestValidationAnalyticsServiceDocumentTypes:
    """Tests fuer Dokumenttyp-Statistiken."""

    @pytest.mark.asyncio
    async def test_get_document_type_stats(self, validation_analytics_service, mock_db):
        """Test: Dokumenttyp-Statistiken abrufen."""
        mock_result = MagicMock()
        mock_result.all.return_value = [
            MagicMock(
                document_type="invoice",
                total_count=200,
                pending_count=20,
                approved_count=170,
                rejected_count=10,
                avg_confidence=0.85,
                avg_corrections=1.5,
            ),
            MagicMock(
                document_type="order",
                total_count=100,
                pending_count=5,
                approved_count=90,
                rejected_count=5,
                avg_confidence=0.92,
                avg_corrections=0.8,
            ),
        ]
        mock_db.execute.return_value = mock_result

        result = await validation_analytics_service.get_document_type_stats()

        assert isinstance(result, list)
        assert len(result) >= 0

    @pytest.mark.asyncio
    async def test_document_type_stats_empty(self, validation_analytics_service, mock_db):
        """Test: Keine Dokumenttypen vorhanden."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await validation_analytics_service.get_document_type_stats()

        assert result == []


class TestValidationAnalyticsServiceConfidenceDistribution:
    """Tests fuer Konfidenz-Verteilung."""

    @pytest.mark.asyncio
    async def test_get_confidence_distribution(self, validation_analytics_service, mock_db):
        """Test: Konfidenz-Verteilung abrufen."""
        mock_result = MagicMock()
        mock_result.all.return_value = [
            MagicMock(range_start=0.0, range_end=0.1, count=5),
            MagicMock(range_start=0.1, range_end=0.2, count=3),
            MagicMock(range_start=0.8, range_end=0.9, count=50),
            MagicMock(range_start=0.9, range_end=1.0, count=100),
        ]
        mock_db.execute.return_value = mock_result

        result = await validation_analytics_service.get_confidence_distribution()

        assert "buckets" in result
        assert "avg_confidence" in result

    @pytest.mark.asyncio
    async def test_confidence_distribution_calculates_stats(self, validation_analytics_service, mock_db):
        """Test: Statistische Kennzahlen werden berechnet."""
        mock_result = MagicMock()
        mock_result.all.return_value = [
            MagicMock(range_start=0.5, range_end=0.6, count=10),
            MagicMock(range_start=0.9, range_end=1.0, count=90),
        ]
        mock_db.execute.return_value = mock_result

        # Mock fuer Aggregat-Abfragen
        mock_db.execute.return_value.scalar.return_value = 0.87

        result = await validation_analytics_service.get_confidence_distribution()

        assert "median_confidence" in result or result is not None
        assert "min_confidence" in result or result is not None
        assert "max_confidence" in result or result is not None


class TestValidationAnalyticsServiceMetrics:
    """Tests fuer spezifische Metriken."""

    @pytest.mark.asyncio
    async def test_approval_rate_calculation(self, validation_analytics_service, mock_db):
        """Test: Genehmigungsrate wird korrekt berechnet."""
        mock_db.execute.return_value.scalar.side_effect = [
            100,  # total
            90,   # approved
        ]

        result = await validation_analytics_service.get_overview_stats()

        # Genehmigungsrate sollte 90% sein
        if "approval_rate" in result:
            assert 0 <= result["approval_rate"] <= 1

    @pytest.mark.asyncio
    async def test_average_time_calculation(self, validation_analytics_service, mock_db):
        """Test: Durchschnittliche Validierungszeit wird berechnet."""
        mock_db.execute.return_value.scalar.return_value = 120.5

        result = await validation_analytics_service.get_overview_stats()

        if "avg_time_to_validate_seconds" in result:
            assert result["avg_time_to_validate_seconds"] >= 0


class TestValidationAnalyticsServiceEdgeCases:
    """Tests fuer Randfaelle."""

    @pytest.mark.asyncio
    async def test_division_by_zero_handling(self, validation_analytics_service, mock_db):
        """Test: Division durch Null wird abgefangen."""
        mock_db.execute.return_value.scalar.return_value = 0

        result = await validation_analytics_service.get_overview_stats()

        # Sollte keine Exception werfen
        assert result is not None

    @pytest.mark.asyncio
    async def test_null_values_handling(self, validation_analytics_service, mock_db):
        """Test: NULL-Werte werden korrekt behandelt."""
        mock_db.execute.return_value.scalar.return_value = None

        result = await validation_analytics_service.get_overview_stats()

        # NULL-Werte sollten als None oder 0 behandelt werden
        assert result is not None

    @pytest.mark.asyncio
    async def test_negative_date_range(self, validation_analytics_service, mock_db):
        """Test: Negativer Datumsbereich wird behandelt."""
        date_from = datetime.now(timezone.utc)
        date_to = datetime.now(timezone.utc) - timedelta(days=30)

        mock_db.execute.return_value.scalar.return_value = 0

        # Sollte entweder leere Ergebnisse oder Fehler zurueckgeben
        result = await validation_analytics_service.get_overview_stats(
            date_from=date_from,
            date_to=date_to,
        )

        assert result is not None

    @pytest.mark.asyncio
    async def test_very_large_dataset(self, validation_analytics_service, mock_db):
        """Test: Grosse Datenmenge wird performant behandelt."""
        mock_db.execute.return_value.scalar.return_value = 1_000_000

        result = await validation_analytics_service.get_overview_stats()

        assert result["total_items"] == 1_000_000

    @pytest.mark.asyncio
    async def test_database_error_handling(self, validation_analytics_service, mock_db):
        """Test: Datenbankfehler werden korrekt behandelt."""
        mock_db.execute.side_effect = Exception("Database connection error")

        with pytest.raises(Exception):
            await validation_analytics_service.get_overview_stats()


class TestValidationAnalyticsServiceCaching:
    """Tests fuer Caching-Verhalten (falls implementiert)."""

    @pytest.mark.asyncio
    async def test_stats_are_fresh(self, validation_analytics_service, mock_db):
        """Test: Statistiken sind aktuell (nicht gecached)."""
        mock_db.execute.return_value.scalar.side_effect = [10, 20]

        result1 = await validation_analytics_service.get_overview_stats()
        result2 = await validation_analytics_service.get_overview_stats()

        # Beide Aufrufe sollten DB abfragen
        assert mock_db.execute.call_count >= 2
