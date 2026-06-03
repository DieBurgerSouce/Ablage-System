"""
Unit Tests fuer ValidationFieldService.

Testet Feld-Reviews, Umlaut-Validierung, Format-Validierung
und Cross-Field-Konsistenzpruefungen.

Hinweis zum Mock-Setup:
    ``db.execute`` ist ein AsyncMock (``await db.execute(...)`` wird awaited),
    waehrend das zurueckgegebene Result-Objekt synchrone Methoden hat
    (``result.scalar_one_or_none()`` und ``result.scalars().all()``).
    Deshalb wird ``db.execute`` als AsyncMock mit einem MagicMock-Result
    konfiguriert.

    Feld-Objekte werden als ``SimpleNamespace`` gebaut (nicht als echte
    ORM-Instanz), damit keine SQLAlchemy-Mapper-Konfiguration ausgeloest
    wird. Der Service greift nur per Attribut-Zugriff auf die Felder zu.
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.db.schemas import ValidationFieldValidateResult
from app.services.validation_field_service import ValidationFieldService


@pytest.fixture
def mock_db():
    """Erstellt einen Mock fuer die Datenbankverbindung."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def validation_field_service(mock_db):
    """Erstellt eine ValidationFieldService-Instanz mit Mock-DB."""
    return ValidationFieldService(mock_db)


@pytest.fixture
def sample_field_review():
    """Erstellt ein Beispiel-Field-Review als SimpleNamespace.

    Bewusst KEINE echte ORM-Instanz, um die Konfiguration der
    SQLAlchemy-Mapper (und damit unabhaengige Mapper-Fehler) zu vermeiden.
    Synthetische Werte ohne echte IBAN/USt-IdNr./Kundennummer.
    """
    return SimpleNamespace(
        id=uuid4(),
        queue_item_id=uuid4(),
        field_key="invoice_number",
        field_label="Rechnungsnummer",
        field_type="text",
        original_value="RE-2024-001",
        corrected_value=None,
        was_corrected=False,
        confidence_score=0.85,
        confidence_threshold=0.7,
        is_below_threshold=False,
        validation_errors=[],
        umlaut_issues=[],
        format_issues=[],
        validation_status=None,
        reviewed_by_id=None,
        reviewed_at=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _scalar_result(value):
    """Result-Mock fuer ``result.scalar_one_or_none()`` (synchron)."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalars_list_result(items):
    """Result-Mock fuer ``result.scalars().all()`` (synchron)."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = items
    return result


class TestValidationFieldServiceRead:
    """Tests fuer Feld-Abfragen."""

    @pytest.mark.asyncio
    async def test_get_fields_for_review(self, validation_field_service, mock_db, sample_field_review):
        """Test: Felder fuer Review abrufen."""
        mock_db.execute.return_value = _scalars_list_result([sample_field_review])

        result = await validation_field_service.get_fields_for_review(sample_field_review.queue_item_id)

        assert isinstance(result, list)
        assert result == [sample_field_review]

    @pytest.mark.asyncio
    async def test_get_field_by_id(self, validation_field_service, mock_db, sample_field_review):
        """Test: Einzelnes Feld abrufen."""
        mock_db.execute.return_value = _scalar_result(sample_field_review)

        result = await validation_field_service.get_field(sample_field_review.id)

        assert result is sample_field_review


class TestValidationFieldServiceUpdate:
    """Tests fuer Feld-Aktualisierungen."""

    @pytest.mark.asyncio
    async def test_update_field_value(self, validation_field_service, mock_db, sample_field_review):
        """Test: Feldwert korrigieren (mit reviewed_by_id fuer Audit-Logging)."""
        mock_db.execute.return_value = _scalar_result(sample_field_review)
        reviewer_id = uuid4()

        result = await validation_field_service.update_field(
            field_id=sample_field_review.id,
            corrected_value="RE-2024-002",
            reviewed_by_id=reviewer_id,
        )

        assert result is sample_field_review
        assert result.corrected_value == "RE-2024-002"
        assert result.was_corrected is True
        assert result.reviewed_by_id == reviewer_id
        assert result.reviewed_at is not None
        assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_update_field_not_found(self, validation_field_service, mock_db):
        """Test: Update auf nicht existierendes Feld gibt None zurueck.

        Der Service wirft KEINE ValueError, sondern liefert None,
        wenn das Feld nicht gefunden wird.
        """
        mock_db.execute.return_value = _scalar_result(None)

        result = await validation_field_service.update_field(
            field_id=uuid4(),
            corrected_value="test",
            reviewed_by_id=uuid4(),
        )

        assert result is None
        assert not mock_db.commit.called


class TestValidationFieldServiceValidation:
    """Tests fuer Feld-Validierung."""

    @pytest.mark.asyncio
    async def test_validate_field_valid(self, validation_field_service, mock_db, sample_field_review):
        """Test: Gueltiges Feld validieren.

        ``validate_field()`` liefert ein ``ValidationFieldValidateResult``
        (Pydantic-Modell), nicht ein Dict.
        """
        mock_db.execute.return_value = _scalar_result(sample_field_review)

        result = await validation_field_service.validate_field(sample_field_review.id)

        assert isinstance(result, ValidationFieldValidateResult)
        assert result.is_valid is True
        assert result.errors == []
        assert result.field_key == "invoice_number"

    @pytest.mark.asyncio
    async def test_validate_all_fields(self, validation_field_service, mock_db, sample_field_review):
        """Test: Alle Felder eines Items validieren."""
        # get_fields_for_review -> scalars().all(); validate_field -> scalar_one_or_none()
        list_result = _scalars_list_result([sample_field_review])
        single_result = _scalar_result(sample_field_review)
        mock_db.execute.side_effect = [list_result, single_result]

        result = await validation_field_service.validate_all_fields(sample_field_review.queue_item_id)

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], ValidationFieldValidateResult)
        assert result[0].is_valid is True


class TestValidationFieldServiceEdgeCases:
    """Tests fuer Randfaelle."""

    @pytest.mark.asyncio
    async def test_empty_value_handling(self, validation_field_service, mock_db, sample_field_review):
        """Test: Leere Werte werden korrekt behandelt.

        Bei leerem Wert liefert der Service ein gueltiges Ergebnis ohne Fehler.
        """
        sample_field_review.original_value = None
        sample_field_review.corrected_value = None
        mock_db.execute.return_value = _scalar_result(sample_field_review)

        result = await validation_field_service.validate_field(sample_field_review.id)

        assert isinstance(result, ValidationFieldValidateResult)
        assert result.is_valid is True
        assert result.errors == []
        assert result.umlaut_issues == []
        assert result.format_issues == []

    @pytest.mark.asyncio
    async def test_very_long_value(self, validation_field_service, mock_db, sample_field_review):
        """Test: Sehr lange Werte werden korrekt behandelt."""
        sample_field_review.original_value = "A" * 10000
        mock_db.execute.return_value = _scalar_result(sample_field_review)

        result = await validation_field_service.validate_field(sample_field_review.id)

        assert isinstance(result, ValidationFieldValidateResult)
        # Text-Feld ohne Format-Regeln -> keine Format-Fehler trotz Laenge
        assert result.is_valid is True
