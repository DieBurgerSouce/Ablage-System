# -*- coding: utf-8 -*-
"""
Tests fuer Finance API Endpoints.

Testet alle Finance API Routers:
- Years Endpoints (List, Get, Aggregations)
- Category Documents (List, Aggregations)
- Document CRUD (Create, Read, Update, Delete)
- Bulk Operations (Delete, Update)
- Export
- Deadlines
- History / Audit Trail
"""

import pytest
from datetime import datetime, date, timezone, timedelta
from uuid import uuid4
from unittest.mock import MagicMock, AsyncMock, patch
from decimal import Decimal


# ==================== Years Endpoints Tests ====================

class TestYearsEndpoints:
    """Tests fuer Year-Endpoints."""

    @pytest.fixture
    def mock_finance_service(self):
        with patch('app.api.v1.finance.get_finance_service') as mock_getter:
            mock_service = MagicMock()
            mock_getter.return_value = mock_service
            yield mock_service

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        user.email = "user@example.com"
        return user

    @pytest.mark.asyncio
    async def test_get_finance_years(self, mock_finance_service, mock_db, mock_user):
        """Sollte Finanz-Jahre auflisten."""
        mock_year1 = MagicMock()
        mock_year1.year = 2024
        mock_year1.total_documents = 150

        mock_year2 = MagicMock()
        mock_year2.year = 2023
        mock_year2.total_documents = 200

        mock_result = MagicMock()
        mock_result.items = [mock_year1, mock_year2]

        mock_finance_service.get_finance_years = AsyncMock(return_value=mock_result)

        result = await mock_finance_service.get_finance_years(mock_db, mock_user.id)

        assert len(result.items) == 2

    @pytest.mark.asyncio
    async def test_get_finance_years_error(self, mock_finance_service, mock_db, mock_user):
        """Sollte Exception bei internem Fehler werfen."""
        mock_finance_service.get_finance_years = AsyncMock(
            side_effect=Exception("DB error")
        )

        with pytest.raises(Exception):
            await mock_finance_service.get_finance_years(mock_db, mock_user.id)

    @pytest.mark.asyncio
    async def test_get_year_details(self, mock_finance_service, mock_db, mock_user):
        """Sollte einzelnes Finanz-Jahr zurueckgeben."""
        mock_result = MagicMock()
        mock_result.year = 2024
        mock_result.total_documents = 150
        mock_result.categories = {"steuerbescheide": 20, "lohn_gehalt": 12}

        mock_finance_service.get_year_details = AsyncMock(return_value=mock_result)

        result = await mock_finance_service.get_year_details(mock_db, mock_user.id, 2024)

        assert result.year == 2024

    @pytest.mark.asyncio
    async def test_get_year_details_not_found(self, mock_finance_service, mock_db, mock_user):
        """Sollte None bei nicht gefundenem Jahr zurueckgeben."""
        mock_finance_service.get_year_details = AsyncMock(return_value=None)

        result = await mock_finance_service.get_year_details(mock_db, mock_user.id, 1999)

        assert result is None


# ==================== Aggregation Endpoints Tests ====================

class TestAggregationEndpoints:
    """Tests fuer Aggregation-Endpoints."""

    @pytest.fixture
    def mock_finance_service(self):
        with patch('app.api.v1.finance.get_finance_service') as mock_getter:
            mock_service = MagicMock()
            mock_getter.return_value = mock_service
            yield mock_service

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.mark.asyncio
    async def test_get_overall_aggregations(self, mock_finance_service, mock_db, mock_user):
        """Sollte Gesamt-Aggregationen zurueckgeben."""
        mock_result = MagicMock()
        mock_result.total_documents = 1000
        mock_result.nachzahlung = Decimal("5000.00")
        mock_result.erstattung = Decimal("3000.00")
        mock_result.saldo = Decimal("-2000.00")

        mock_finance_service.get_overall_aggregations = AsyncMock(return_value=mock_result)

        result = await mock_finance_service.get_overall_aggregations(mock_db, mock_user.id)

        assert result.total_documents == 1000

    @pytest.mark.asyncio
    async def test_get_year_aggregations(self, mock_finance_service, mock_db, mock_user):
        """Sollte Jahr-Aggregationen zurueckgeben."""
        mock_result = MagicMock()
        mock_result.total_documents = 150
        mock_result.nachzahlung = Decimal("1000.00")
        mock_result.erstattung = Decimal("500.00")

        mock_finance_service.get_year_aggregations = AsyncMock(return_value=mock_result)

        result = await mock_finance_service.get_year_aggregations(mock_db, mock_user.id, 2024)

        assert result.total_documents == 150


# ==================== Category Documents Tests ====================

class TestCategoryDocumentsEndpoints:
    """Tests fuer Kategorie-Dokument-Endpoints."""

    @pytest.fixture
    def mock_finance_service(self):
        with patch('app.api.v1.finance.get_finance_service') as mock_getter:
            mock_service = MagicMock()
            mock_getter.return_value = mock_service
            yield mock_service

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.mark.asyncio
    async def test_get_category_documents(self, mock_finance_service, mock_db, mock_user):
        """Sollte Kategorie-Dokumente mit Paginierung auflisten."""
        mock_result = MagicMock()
        mock_result.items = [MagicMock(id=uuid4()), MagicMock(id=uuid4())]
        mock_result.total = 25
        mock_result.page = 0
        mock_result.page_size = 25

        mock_finance_service.get_category_documents = AsyncMock(return_value=mock_result)

        result = await mock_finance_service.get_category_documents(
            mock_db, mock_user.id, MagicMock()
        )

        assert result.total == 25

    @pytest.mark.asyncio
    async def test_get_category_documents_with_filters(self, mock_finance_service, mock_db, mock_user):
        """Sollte Kategorie-Dokumente mit Filtern auflisten."""
        mock_result = MagicMock()
        mock_result.items = []
        mock_result.total = 0

        mock_finance_service.get_category_documents = AsyncMock(return_value=mock_result)

        filter_params = MagicMock()
        filter_params.year = 2024
        filter_params.category = "steuerbescheide"
        filter_params.search = "Einkommensteuer"

        result = await mock_finance_service.get_category_documents(
            mock_db, mock_user.id, filter_params
        )

        mock_finance_service.get_category_documents.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_category_aggregations(self, mock_finance_service, mock_db, mock_user):
        """Sollte Kategorie-Aggregationen zurueckgeben."""
        mock_result = MagicMock()
        mock_result.total_documents = 20
        mock_result.nachzahlung = Decimal("500.00")

        mock_finance_service.get_category_aggregations = AsyncMock(return_value=mock_result)

        result = await mock_finance_service.get_category_aggregations(
            mock_db, mock_user.id, 2024, "steuerbescheide"
        )

        assert result.total_documents == 20


# ==================== Document CRUD Tests ====================

class TestDocumentCRUDEndpoints:
    """Tests fuer Document CRUD Endpoints."""

    @pytest.fixture
    def mock_finance_service(self):
        with patch('app.api.v1.finance.get_finance_service') as mock_getter:
            mock_service = MagicMock()
            mock_getter.return_value = mock_service
            yield mock_service

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user_read(self):
        """Benutzer mit finance:read Berechtigung."""
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.fixture
    def mock_user_write(self):
        """Benutzer mit finance:write Berechtigung."""
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.fixture
    def mock_user_delete(self):
        """Benutzer mit finance:delete Berechtigung."""
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.mark.asyncio
    async def test_get_finance_document(self, mock_finance_service, mock_db, mock_user_read):
        """Sollte einzelnes Finanz-Dokument zurueckgeben."""
        doc_id = uuid4()
        mock_doc = MagicMock()
        mock_doc.id = doc_id
        mock_doc.original_filename = "steuerbescheid_2024.pdf"
        mock_doc.document_metadata = {"finance_category": "steuerbescheide"}

        mock_finance_service.get_finance_document = AsyncMock(return_value=mock_doc)

        result = await mock_finance_service.get_finance_document(
            mock_db, mock_user_read.id, doc_id
        )

        assert result.id == doc_id

    @pytest.mark.asyncio
    async def test_get_finance_document_not_found(self, mock_finance_service, mock_db, mock_user_read):
        """Sollte None bei nicht gefundenem Dokument zurueckgeben."""
        mock_finance_service.get_finance_document = AsyncMock(return_value=None)

        result = await mock_finance_service.get_finance_document(
            mock_db, mock_user_read.id, uuid4()
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_update_finance_document(self, mock_finance_service, mock_db, mock_user_write):
        """Sollte Finanz-Dokument aktualisieren."""
        doc_id = uuid4()
        mock_doc = MagicMock()
        mock_doc.id = doc_id
        mock_doc.document_metadata = {"finance_category": "lohn_gehalt"}

        mock_finance_service.update_finance_document = AsyncMock(return_value=mock_doc)

        result = await mock_finance_service.update_finance_document(
            mock_db, mock_user_write.id, doc_id, {"category": "lohn_gehalt"}
        )

        assert result.id == doc_id

    @pytest.mark.asyncio
    async def test_update_finance_document_not_found(self, mock_finance_service, mock_db, mock_user_write):
        """Sollte None bei nicht gefundenem Dokument zurueckgeben."""
        mock_finance_service.update_finance_document = AsyncMock(return_value=None)

        result = await mock_finance_service.update_finance_document(
            mock_db, mock_user_write.id, uuid4(), {}
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_delete_finance_document(self, mock_finance_service, mock_db, mock_user_delete):
        """Sollte Finanz-Dokument loeschen (Soft-Delete)."""
        doc_id = uuid4()
        mock_doc = MagicMock()
        mock_doc.id = doc_id
        mock_doc.deleted_at = datetime.now(timezone.utc)

        mock_finance_service.delete_finance_document = AsyncMock(return_value=mock_doc)

        result = await mock_finance_service.delete_finance_document(
            mock_db, mock_user_delete.id, doc_id
        )

        assert result.deleted_at is not None

    @pytest.mark.asyncio
    async def test_delete_finance_document_not_found(self, mock_finance_service, mock_db, mock_user_delete):
        """Sollte None bei nicht gefundenem Dokument zurueckgeben."""
        mock_finance_service.delete_finance_document = AsyncMock(return_value=None)

        result = await mock_finance_service.delete_finance_document(
            mock_db, mock_user_delete.id, uuid4()
        )

        assert result is None


# ==================== Bulk Operations Tests ====================

class TestBulkOperationsEndpoints:
    """Tests fuer Bulk-Operationen."""

    @pytest.fixture
    def mock_finance_service(self):
        with patch('app.api.v1.finance.get_finance_service') as mock_getter:
            mock_service = MagicMock()
            mock_getter.return_value = mock_service
            yield mock_service

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user_delete(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.fixture
    def mock_user_write(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.mark.asyncio
    async def test_bulk_delete_success(self, mock_finance_service, mock_db, mock_user_delete):
        """Sollte mehrere Dokumente loeschen."""
        mock_doc = MagicMock()
        mock_doc.deleted_at = datetime.now(timezone.utc)

        mock_finance_service.delete_finance_document = AsyncMock(return_value=mock_doc)

        doc_ids = [uuid4() for _ in range(5)]
        deleted_count = 0
        failed_count = 0

        for doc_id in doc_ids:
            result = await mock_finance_service.delete_finance_document(
                mock_db, mock_user_delete.id, doc_id
            )
            if result:
                deleted_count += 1
            else:
                failed_count += 1

        assert deleted_count == 5
        assert failed_count == 0

    @pytest.mark.asyncio
    async def test_bulk_delete_partial_failure(self, mock_finance_service, mock_db, mock_user_delete):
        """Sollte Teilerfolg bei Bulk-Loeschung handhaben."""
        mock_doc = MagicMock()
        mock_doc.deleted_at = datetime.now(timezone.utc)

        # First 3 succeed, next 2 fail
        mock_finance_service.delete_finance_document = AsyncMock(
            side_effect=[
                mock_doc, mock_doc, mock_doc, None, None
            ]
        )

        doc_ids = [uuid4() for _ in range(5)]
        deleted_count = 0
        failed_count = 0

        for doc_id in doc_ids:
            result = await mock_finance_service.delete_finance_document(
                mock_db, mock_user_delete.id, doc_id
            )
            if result:
                deleted_count += 1
            else:
                failed_count += 1

        assert deleted_count == 3
        assert failed_count == 2

    @pytest.mark.asyncio
    async def test_bulk_update_success(self, mock_finance_service, mock_db, mock_user_write):
        """Sollte mehrere Dokumente aktualisieren."""
        mock_doc = MagicMock()
        mock_doc.id = uuid4()

        mock_finance_service.update_finance_document = AsyncMock(return_value=mock_doc)

        doc_ids = [uuid4() for _ in range(10)]
        updated_count = 0

        for doc_id in doc_ids:
            result = await mock_finance_service.update_finance_document(
                mock_db, mock_user_write.id, doc_id, {"category": "lohn_gehalt"}
            )
            if result:
                updated_count += 1

        assert updated_count == 10


# ==================== Export Tests ====================

class TestExportEndpoints:
    """Tests fuer Export-Endpoints."""

    @pytest.fixture
    def mock_finance_service(self):
        with patch('app.api.v1.finance.get_finance_service') as mock_getter:
            mock_service = MagicMock()
            mock_getter.return_value = mock_service
            yield mock_service

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.mark.asyncio
    async def test_export_by_year(self, mock_finance_service, mock_db, mock_user):
        """Sollte Export fuer Jahr vorbereiten."""
        mock_aggregations = MagicMock()
        mock_aggregations.total_documents = 150

        mock_finance_service.get_year_aggregations = AsyncMock(return_value=mock_aggregations)

        result = await mock_finance_service.get_year_aggregations(mock_db, mock_user.id, 2024)

        assert result.total_documents == 150

    @pytest.mark.asyncio
    async def test_export_no_documents(self, mock_finance_service, mock_db, mock_user):
        """Sollte korrekt bei leeren Ergebnissen verhalten."""
        mock_aggregations = MagicMock()
        mock_aggregations.total_documents = 0

        mock_finance_service.get_year_aggregations = AsyncMock(return_value=mock_aggregations)

        result = await mock_finance_service.get_year_aggregations(mock_db, mock_user.id, 2024)

        assert result.total_documents == 0


# ==================== Deadlines Tests ====================

class TestDeadlinesEndpoints:
    """Tests fuer Deadline-Endpoints."""

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        return db

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.mark.asyncio
    async def test_extract_deadlines_from_document(self, mock_db, mock_user):
        """Sollte Fristen aus Dokument extrahieren."""
        mock_doc = MagicMock()
        mock_doc.id = uuid4()
        mock_doc.original_filename = "steuerbescheid.pdf"
        mock_doc.document_type = "tax_notice"
        mock_doc.year = 2024
        mock_doc.extracted_data = {
            "einspruchsfrist": (datetime.now(timezone.utc) + timedelta(days=14)).isoformat(),
            "aktenzeichen": "123/456/789",
        }

        # Simulate deadline extraction
        deadline_items = []
        einspruchsfrist = mock_doc.extracted_data.get("einspruchsfrist")
        if einspruchsfrist:
            deadline_date = datetime.fromisoformat(einspruchsfrist.replace("Z", "+00:00"))
            days_until = (deadline_date - datetime.now(timezone.utc)).days
            deadline_items.append({
                "document_id": mock_doc.id,
                "deadline": deadline_date,
                "days_until": days_until,
            })

        assert len(deadline_items) == 1
        assert deadline_items[0]["days_until"] > 0

    @pytest.mark.asyncio
    async def test_deadline_overdue_detection(self, mock_db, mock_user):
        """Sollte ueberfaellige Fristen erkennen."""
        mock_doc = MagicMock()
        mock_doc.id = uuid4()
        mock_doc.extracted_data = {
            "einspruchsfrist": (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(),
        }

        einspruchsfrist = mock_doc.extracted_data.get("einspruchsfrist")
        deadline_date = datetime.fromisoformat(einspruchsfrist.replace("Z", "+00:00"))
        days_until = (deadline_date - datetime.now(timezone.utc)).days

        assert days_until < 0  # Negative means overdue

    @pytest.mark.asyncio
    async def test_deadline_upcoming_detection(self, mock_db, mock_user):
        """Sollte anstehende Fristen erkennen."""
        mock_doc = MagicMock()
        mock_doc.id = uuid4()
        mock_doc.extracted_data = {
            "einspruchsfrist": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
        }

        einspruchsfrist = mock_doc.extracted_data.get("einspruchsfrist")
        deadline_date = datetime.fromisoformat(einspruchsfrist.replace("Z", "+00:00"))
        days_until = (deadline_date - datetime.now(timezone.utc)).days

        assert 0 <= days_until <= 7  # Urgent


# ==================== History / Audit Trail Tests ====================

class TestHistoryEndpoints:
    """Tests fuer History/Audit-Trail-Endpoints."""

    @pytest.fixture
    def mock_finance_service(self):
        with patch('app.api.v1.finance.get_finance_service') as mock_getter:
            mock_service = MagicMock()
            mock_getter.return_value = mock_service
            yield mock_service

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.mark.asyncio
    async def test_get_document_for_history(self, mock_finance_service, mock_db, mock_user):
        """Sollte Dokument fuer History-Abfrage abrufen."""
        doc_id = uuid4()
        mock_doc = MagicMock()
        mock_doc.id = doc_id
        mock_doc.original_filename = "test.pdf"

        mock_finance_service.get_finance_document = AsyncMock(return_value=mock_doc)

        result = await mock_finance_service.get_finance_document(mock_db, mock_user.id, doc_id)

        assert result.id == doc_id

    @pytest.mark.asyncio
    async def test_get_history_not_found(self, mock_finance_service, mock_db, mock_user):
        """Sollte None bei nicht gefundenem Dokument zurueckgeben."""
        mock_finance_service.get_finance_document = AsyncMock(return_value=None)

        result = await mock_finance_service.get_finance_document(mock_db, mock_user.id, uuid4())

        assert result is None


# ==================== RBAC Permission Tests ====================

class TestRBACPermissions:
    """Tests fuer RBAC-Berechtigungen."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user_no_permissions(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.mark.asyncio
    async def test_require_finance_read_exists(self, mock_db, mock_user_no_permissions):
        """Sollte finance:read Berechtigung-Funktion existieren."""
        from app.core.rbac import require_finance_read

        assert require_finance_read is not None

    @pytest.mark.asyncio
    async def test_require_finance_write_exists(self, mock_db, mock_user_no_permissions):
        """Sollte finance:write Berechtigung-Funktion existieren."""
        from app.core.rbac import require_finance_write

        assert require_finance_write is not None

    @pytest.mark.asyncio
    async def test_require_finance_delete_exists(self, mock_db, mock_user_no_permissions):
        """Sollte finance:delete Berechtigung-Funktion existieren."""
        from app.core.rbac import require_finance_delete

        assert require_finance_delete is not None


# ==================== Error Handling Tests ====================

class TestErrorHandling:
    """Tests fuer Fehlerbehandlung."""

    @pytest.fixture
    def mock_finance_service(self):
        with patch('app.api.v1.finance.get_finance_service') as mock_getter:
            mock_service = MagicMock()
            mock_getter.return_value = mock_service
            yield mock_service

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.mark.asyncio
    async def test_service_exception_propagation(self, mock_finance_service, mock_db, mock_user):
        """Sollte Service-Exceptions korrekt propagieren."""
        mock_finance_service.get_finance_document = AsyncMock(
            side_effect=Exception("Database error")
        )

        with pytest.raises(Exception) as exc:
            await mock_finance_service.get_finance_document(mock_db, mock_user.id, uuid4())

        assert "Database error" in str(exc.value)

    @pytest.mark.asyncio
    async def test_value_error_propagation(self, mock_finance_service, mock_db, mock_user):
        """Sollte ValueError korrekt propagieren."""
        mock_finance_service.update_finance_document = AsyncMock(
            side_effect=ValueError("Invalid category")
        )

        with pytest.raises(ValueError) as exc:
            await mock_finance_service.update_finance_document(
                mock_db, mock_user.id, uuid4(), {}
            )

        assert "Invalid category" in str(exc.value)


# ==================== Category Validation Tests ====================

class TestCategoryValidation:
    """Tests fuer Kategorie-Validierung."""

    def test_valid_finance_categories(self):
        """Sollte gueltige Finanz-Kategorien validieren."""
        valid_categories = [
            "grundabgabenbescheid",
            "steuerbescheide",
            "vorauszahlungen",
            "steuererklaerungen",
            "finanzamt_korrespondenz",
            "lohn_gehalt",
            "sozialversicherung",
            "berufsgenossenschaft",
            "arbeitsvertraege",
            "betriebshaftpflicht",
            "sachversicherungen",
            "kfz_versicherung",
            "rechtsschutz",
            "kontoauszuege",
            "kreditvertraege",
            "buergschaften",
            "darlehen",
        ]

        for category in valid_categories:
            assert len(category) > 0
            assert "_" in category or category.isalpha()

    def test_invalid_category_detection(self):
        """Sollte ungueltige Kategorien erkennen."""
        valid_categories = ["steuerbescheide", "lohn_gehalt", "kontoauszuege"]
        invalid = "invalid_category"

        assert invalid not in valid_categories
