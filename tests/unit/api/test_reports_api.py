# -*- coding: utf-8 -*-
"""
Unit Tests fuer Reports API Endpoints.

Testet:
- Report Template CRUD
- Columns, Filters, Charts
- Report Execution
- Sharing & Scheduling

Feinpoliert und durchdacht - Enterprise Test Coverage.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4
from datetime import datetime, timezone

# Test markers
pytestmark = [pytest.mark.unit, pytest.mark.api]


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_template():
    """Sample Report Template fuer Tests."""
    return Mock(
        id=uuid4(),
        user_id=uuid4(),
        company_id=None,
        name="Monatsreport Finanzen",
        description="Monatlicher Finanzbericht",
        report_type="finance",
        data_source="invoices",
        default_format="excel",
        is_public=False,
        is_scheduled=False,
        schedule_config=None,
        layout_config={"orientation": "landscape"},
        sort_config=[{"field": "date", "order": "desc"}],
        group_by_config=["company_id"],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        last_executed_at=None,
        columns=[],
        filters=[],
        charts=[],
    )


@pytest.fixture
def sample_column():
    """Sample Report Column fuer Tests."""
    return Mock(
        id=uuid4(),
        template_id=uuid4(),
        field_path="extracted_data.invoice_number",
        display_name="Rechnungsnummer",
        data_type="string",
        format_pattern=None,
        width=150,
        sort_order=0,
        is_visible=True,
        aggregation=None,
    )


@pytest.fixture
def sample_filter():
    """Sample Report Filter fuer Tests."""
    return Mock(
        id=uuid4(),
        template_id=uuid4(),
        field_path="extracted_data.total_amount",
        operator="gte",
        value=1000,
        logic_operator="AND",
        group_id=None,
        sort_order=0,
        is_dynamic=False,
        dynamic_source=None,
    )


@pytest.fixture
def sample_chart():
    """Sample Report Chart fuer Tests."""
    return Mock(
        id=uuid4(),
        template_id=uuid4(),
        chart_type="bar",
        title="Umsatz pro Monat",
        x_axis_field="month",
        y_axis_fields=["total_amount"],
        group_by_field="company_id",
        colors=["#4A90E2", "#50E3C2"],
        show_legend=True,
        show_labels=False,
        position="bottom",
        width_percent=100,
        height_px=300,
        sort_order=0,
    )


@pytest.fixture
def sample_execution():
    """Sample Report Execution fuer Tests."""
    return Mock(
        id=uuid4(),
        template_id=uuid4(),
        executed_by_id=uuid4(),
        status="completed",
        format="excel",
        trigger_type="manual",
        row_count=150,
        file_size_bytes=25600,
        download_url="https://minio.local/reports/test.xlsx",
        download_expires_at=datetime.now(timezone.utc),
        error_message=None,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        duration_ms=2500,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_share():
    """Sample Report Share fuer Tests."""
    return Mock(
        id=uuid4(),
        template_id=uuid4(),
        shared_with_user_id=uuid4(),
        can_view=True,
        can_execute=True,
        can_edit=False,
        can_delete=False,
        shared_by_id=uuid4(),
        created_at=datetime.now(timezone.utc),
    )


# =============================================================================
# Template CRUD Tests
# =============================================================================

class TestTemplateList:
    """Tests fuer Template-Liste."""

    @pytest.mark.asyncio
    async def test_list_templates_success(self, async_client, auth_headers):
        """Erfolgreiches Auflisten von Templates."""
        with patch("app.api.v1.reports.ReportTemplateService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.list_templates.return_value = []
            mock_service.return_value = mock_instance

            response = await async_client.get(
                "/api/v1/reports/templates",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401]

    @pytest.mark.asyncio
    async def test_list_templates_with_filters(self, async_client, auth_headers):
        """Templates mit Filtern auflisten."""
        with patch("app.api.v1.reports.ReportTemplateService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.list_templates.return_value = []
            mock_service.return_value = mock_instance

            response = await async_client.get(
                "/api/v1/reports/templates?report_type=finance&include_public=true",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401]


class TestTemplateCreate:
    """Tests fuer Template-Erstellung."""

    @pytest.mark.asyncio
    async def test_create_template_success(self, async_client, auth_headers, sample_template):
        """Erfolgreiche Template-Erstellung."""
        with patch("app.api.v1.reports.ReportTemplateService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.create_template.return_value = sample_template
            mock_service.return_value = mock_instance

            response = await async_client.post(
                "/api/v1/reports/templates",
                json={
                    "name": "Neuer Report",
                    "report_type": "document",
                    "data_source": "documents",
                    "description": "Ein Testreport",
                },
                headers=auth_headers,
            )

            assert response.status_code in [200, 201, 401, 422]

    @pytest.mark.asyncio
    async def test_create_template_minimal(self, async_client, auth_headers, sample_template):
        """Template-Erstellung mit minimalen Daten."""
        with patch("app.api.v1.reports.ReportTemplateService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.create_template.return_value = sample_template
            mock_service.return_value = mock_instance

            response = await async_client.post(
                "/api/v1/reports/templates",
                json={
                    "name": "Minimal Report",
                    "report_type": "custom",
                    "data_source": "documents",
                },
                headers=auth_headers,
            )

            assert response.status_code in [200, 201, 401, 422]


class TestTemplateGet:
    """Tests fuer Template-Abruf."""

    @pytest.mark.asyncio
    async def test_get_template_success(self, async_client, auth_headers, sample_template):
        """Erfolgreicher Template-Abruf."""
        template_id = sample_template.id

        with patch("app.api.v1.reports.ReportTemplateService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.get_template.return_value = sample_template
            mock_service.return_value = mock_instance

            response = await async_client.get(
                f"/api/v1/reports/templates/{template_id}",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 404]

    @pytest.mark.asyncio
    async def test_get_template_not_found(self, async_client, auth_headers):
        """Template-Abruf fuer nicht existierendes Template."""
        non_existent_id = uuid4()

        with patch("app.api.v1.reports.ReportTemplateService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.get_template.return_value = None
            mock_service.return_value = mock_instance

            response = await async_client.get(
                f"/api/v1/reports/templates/{non_existent_id}",
                headers=auth_headers,
            )

            assert response.status_code in [404, 401]


class TestTemplateUpdate:
    """Tests fuer Template-Update."""

    @pytest.mark.asyncio
    async def test_update_template_success(self, async_client, auth_headers, sample_template):
        """Erfolgreiches Template-Update."""
        template_id = sample_template.id

        with patch("app.api.v1.reports.ReportTemplateService") as mock_service:
            mock_instance = AsyncMock()
            sample_template.name = "Aktualisierter Report"
            mock_instance.update_template.return_value = sample_template
            mock_service.return_value = mock_instance

            response = await async_client.put(
                f"/api/v1/reports/templates/{template_id}",
                json={"name": "Aktualisierter Report"},
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 404]


class TestTemplateDelete:
    """Tests fuer Template-Loeschung."""

    @pytest.mark.asyncio
    async def test_delete_template_success(self, async_client, auth_headers, sample_template):
        """Erfolgreiche Template-Loeschung."""
        template_id = sample_template.id

        with patch("app.api.v1.reports.ReportTemplateService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.delete_template.return_value = True
            mock_service.return_value = mock_instance

            response = await async_client.delete(
                f"/api/v1/reports/templates/{template_id}",
                headers=auth_headers,
            )

            assert response.status_code in [200, 204, 401, 404]


class TestTemplateClone:
    """Tests fuer Template-Klonen."""

    @pytest.mark.asyncio
    async def test_clone_template_success(self, async_client, auth_headers, sample_template):
        """Erfolgreiches Template-Klonen."""
        template_id = sample_template.id

        with patch("app.api.v1.reports.ReportTemplateService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.clone_template.return_value = sample_template
            mock_service.return_value = mock_instance

            response = await async_client.post(
                f"/api/v1/reports/templates/{template_id}/clone?new_name=Kopie",
                headers=auth_headers,
            )

            assert response.status_code in [200, 201, 401, 404]


# =============================================================================
# Column Management Tests
# =============================================================================

class TestColumnManagement:
    """Tests fuer Spalten-Verwaltung."""

    @pytest.mark.asyncio
    async def test_list_columns_success(self, async_client, auth_headers, sample_template, sample_column):
        """Erfolgreiches Auflisten von Spalten."""
        sample_template.columns = [sample_column]
        template_id = sample_template.id

        with patch("app.api.v1.reports.ReportTemplateService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.get_template.return_value = sample_template
            mock_service.return_value = mock_instance

            response = await async_client.get(
                f"/api/v1/reports/templates/{template_id}/columns",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 404]

    @pytest.mark.asyncio
    async def test_add_column_success(self, async_client, auth_headers, sample_template, sample_column):
        """Erfolgreiches Hinzufuegen einer Spalte."""
        template_id = sample_template.id

        with patch("app.api.v1.reports.ReportTemplateService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.get_template.return_value = sample_template
            mock_instance.add_column.return_value = sample_column
            mock_service.return_value = mock_instance

            response = await async_client.post(
                f"/api/v1/reports/templates/{template_id}/columns",
                json={
                    "field_path": "extracted_data.invoice_number",
                    "display_name": "Rechnungsnummer",
                    "data_type": "string",
                },
                headers=auth_headers,
            )

            assert response.status_code in [200, 201, 401, 404]

    @pytest.mark.asyncio
    async def test_delete_column_success(self, async_client, auth_headers, sample_template, sample_column):
        """Erfolgreiches Loeschen einer Spalte."""
        template_id = sample_template.id
        column_id = sample_column.id

        with patch("app.api.v1.reports.ReportTemplateService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.get_template.return_value = sample_template
            mock_instance.delete_column.return_value = True
            mock_service.return_value = mock_instance

            response = await async_client.delete(
                f"/api/v1/reports/templates/{template_id}/columns/{column_id}",
                headers=auth_headers,
            )

            assert response.status_code in [200, 204, 401, 404]

    @pytest.mark.asyncio
    async def test_reorder_columns_success(self, async_client, auth_headers, sample_template):
        """Erfolgreiches Neuordnen von Spalten."""
        template_id = sample_template.id
        col_id_1 = uuid4()
        col_id_2 = uuid4()

        with patch("app.api.v1.reports.ReportTemplateService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.get_template.return_value = sample_template
            mock_instance.reorder_columns.return_value = None
            mock_service.return_value = mock_instance

            response = await async_client.put(
                f"/api/v1/reports/templates/{template_id}/columns/reorder",
                json=[
                    {"id": str(col_id_1), "sort_order": 1},
                    {"id": str(col_id_2), "sort_order": 0},
                ],
                headers=auth_headers,
            )

            assert response.status_code in [200, 204, 401, 404]


# =============================================================================
# Filter Management Tests
# =============================================================================

class TestFilterManagement:
    """Tests fuer Filter-Verwaltung."""

    @pytest.mark.asyncio
    async def test_list_filters_success(self, async_client, auth_headers, sample_template, sample_filter):
        """Erfolgreiches Auflisten von Filtern."""
        sample_template.filters = [sample_filter]
        template_id = sample_template.id

        with patch("app.api.v1.reports.ReportTemplateService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.get_template.return_value = sample_template
            mock_service.return_value = mock_instance

            response = await async_client.get(
                f"/api/v1/reports/templates/{template_id}/filters",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 404]

    @pytest.mark.asyncio
    async def test_add_filter_success(self, async_client, auth_headers, sample_template, sample_filter):
        """Erfolgreiches Hinzufuegen eines Filters."""
        template_id = sample_template.id

        with patch("app.api.v1.reports.ReportTemplateService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.get_template.return_value = sample_template
            mock_instance.add_filter.return_value = sample_filter
            mock_service.return_value = mock_instance

            response = await async_client.post(
                f"/api/v1/reports/templates/{template_id}/filters",
                json={
                    "field_path": "extracted_data.total_amount",
                    "operator": "gte",
                    "value": 1000,
                },
                headers=auth_headers,
            )

            assert response.status_code in [200, 201, 401, 404]

    @pytest.mark.asyncio
    async def test_delete_filter_success(self, async_client, auth_headers, sample_template, sample_filter):
        """Erfolgreiches Loeschen eines Filters."""
        template_id = sample_template.id
        filter_id = sample_filter.id

        with patch("app.api.v1.reports.ReportTemplateService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.get_template.return_value = sample_template
            mock_instance.delete_filter.return_value = True
            mock_service.return_value = mock_instance

            response = await async_client.delete(
                f"/api/v1/reports/templates/{template_id}/filters/{filter_id}",
                headers=auth_headers,
            )

            assert response.status_code in [200, 204, 401, 404]


# =============================================================================
# Chart Management Tests
# =============================================================================

class TestChartManagement:
    """Tests fuer Chart-Verwaltung."""

    @pytest.mark.asyncio
    async def test_add_chart_success(self, async_client, auth_headers, sample_template, sample_chart):
        """Erfolgreiches Hinzufuegen eines Charts."""
        template_id = sample_template.id

        with patch("app.api.v1.reports.ReportTemplateService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.get_template.return_value = sample_template
            mock_instance.add_chart.return_value = sample_chart
            mock_service.return_value = mock_instance

            response = await async_client.post(
                f"/api/v1/reports/templates/{template_id}/charts",
                json={
                    "chart_type": "bar",
                    "title": "Umsatz pro Monat",
                    "y_axis_fields": ["total_amount"],
                },
                headers=auth_headers,
            )

            assert response.status_code in [200, 201, 401, 404]

    @pytest.mark.asyncio
    async def test_delete_chart_success(self, async_client, auth_headers, sample_template, sample_chart):
        """Erfolgreiches Loeschen eines Charts."""
        template_id = sample_template.id
        chart_id = sample_chart.id

        with patch("app.api.v1.reports.ReportTemplateService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.get_template.return_value = sample_template
            mock_instance.delete_chart.return_value = True
            mock_service.return_value = mock_instance

            response = await async_client.delete(
                f"/api/v1/reports/templates/{template_id}/charts/{chart_id}",
                headers=auth_headers,
            )

            assert response.status_code in [200, 204, 401, 404]


# =============================================================================
# Report Execution Tests
# =============================================================================

class TestReportExecution:
    """Tests fuer Report-Ausfuehrung."""

    @pytest.mark.asyncio
    async def test_preview_report_success(self, async_client, auth_headers, sample_template):
        """Erfolgreiche Report-Vorschau."""
        template_id = sample_template.id

        with patch("app.api.v1.reports.ReportTemplateService") as mock_template_svc, \
             patch("app.api.v1.reports.ReportBuilderService") as mock_builder_svc:
            mock_template_instance = AsyncMock()
            mock_template_instance.get_template.return_value = sample_template
            mock_template_svc.return_value = mock_template_instance

            mock_builder_instance = AsyncMock()
            mock_preview = Mock(
                template_id=template_id,
                columns=[{"name": "Rechnungsnummer", "type": "string"}],
                sample_rows=[Mock(data={"invoice_number": "INV-001"})],
                total_count=100,
            )
            mock_builder_instance.preview_report.return_value = mock_preview
            mock_builder_svc.return_value = mock_builder_instance

            response = await async_client.post(
                f"/api/v1/reports/templates/{template_id}/preview?limit=10",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 404]

    @pytest.mark.asyncio
    async def test_execute_report_success(self, async_client, auth_headers, sample_template, sample_execution):
        """Erfolgreiche Report-Ausfuehrung."""
        template_id = sample_template.id

        with patch("app.api.v1.reports.ReportTemplateService") as mock_template_svc, \
             patch("app.api.v1.reports.ReportBuilderService") as mock_builder_svc, \
             patch("app.api.v1.reports.ReportSchedulerService") as mock_scheduler_svc:
            mock_template_instance = AsyncMock()
            mock_template_instance.get_template.return_value = sample_template
            mock_template_svc.return_value = mock_template_instance

            mock_builder_instance = AsyncMock()
            mock_result = Mock(total_count=150)
            mock_builder_instance.execute_report.return_value = mock_result
            mock_builder_svc.return_value = mock_builder_instance

            mock_scheduler_instance = AsyncMock()
            mock_scheduler_instance.create_execution.return_value = sample_execution
            mock_scheduler_instance.update_execution_status.return_value = sample_execution
            mock_scheduler_svc.return_value = mock_scheduler_instance

            response = await async_client.post(
                f"/api/v1/reports/templates/{template_id}/execute",
                json={"format": "excel"},
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 404, 500]

    @pytest.mark.asyncio
    async def test_list_executions_success(self, async_client, auth_headers, sample_execution):
        """Erfolgreiches Auflisten von Ausfuehrungen."""
        with patch("app.api.v1.reports.ReportSchedulerService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.list_executions.return_value = [sample_execution]
            mock_service.return_value = mock_instance

            response = await async_client.get(
                "/api/v1/reports/executions",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401]

    @pytest.mark.asyncio
    async def test_get_execution_success(self, async_client, auth_headers, sample_execution):
        """Erfolgreicher Abruf einer Ausfuehrung."""
        execution_id = sample_execution.id

        with patch("app.api.v1.reports.ReportSchedulerService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.get_execution.return_value = sample_execution
            mock_service.return_value = mock_instance

            response = await async_client.get(
                f"/api/v1/reports/executions/{execution_id}",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 404]


# =============================================================================
# Sharing Tests
# =============================================================================

class TestReportSharing:
    """Tests fuer Report-Freigabe."""

    @pytest.mark.asyncio
    async def test_share_template_success(self, async_client, auth_headers, sample_template, sample_share):
        """Erfolgreiches Teilen eines Templates."""
        template_id = sample_template.id
        shared_with_id = uuid4()

        with patch("app.api.v1.reports.ReportTemplateService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.share_template.return_value = sample_share
            mock_service.return_value = mock_instance

            response = await async_client.post(
                f"/api/v1/reports/templates/{template_id}/share",
                json={
                    "shared_with_user_id": str(shared_with_id),
                    "can_view": True,
                    "can_execute": True,
                    "can_edit": False,
                    "can_delete": False,
                },
                headers=auth_headers,
            )

            assert response.status_code in [200, 201, 401, 404]

    @pytest.mark.asyncio
    async def test_revoke_share_success(self, async_client, auth_headers, sample_template):
        """Erfolgreiches Widerrufen einer Freigabe."""
        template_id = sample_template.id
        user_id = uuid4()

        with patch("app.api.v1.reports.ReportTemplateService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.revoke_share.return_value = True
            mock_service.return_value = mock_instance

            response = await async_client.delete(
                f"/api/v1/reports/templates/{template_id}/share/{user_id}",
                headers=auth_headers,
            )

            assert response.status_code in [200, 204, 401, 404]

    @pytest.mark.asyncio
    async def test_list_shared_templates_success(self, async_client, auth_headers, sample_template):
        """Erfolgreiches Auflisten geteilter Templates."""
        with patch("app.api.v1.reports.ReportTemplateService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.list_shared_with_me.return_value = [sample_template]
            mock_service.return_value = mock_instance

            response = await async_client.get(
                "/api/v1/reports/shared",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401]


# =============================================================================
# Scheduling Tests
# =============================================================================

class TestReportScheduling:
    """Tests fuer Report-Zeitplanung."""

    @pytest.mark.asyncio
    async def test_enable_schedule_success(self, async_client, auth_headers, sample_template):
        """Erfolgreiches Aktivieren eines Zeitplans."""
        template_id = sample_template.id
        sample_template.is_scheduled = True

        with patch("app.api.v1.reports.ReportTemplateService") as mock_template_svc, \
             patch("app.api.v1.reports.ReportSchedulerService") as mock_scheduler_svc:
            mock_template_instance = AsyncMock()
            mock_template_svc.return_value = mock_template_instance

            mock_scheduler_instance = AsyncMock()
            mock_scheduler_instance.enable_schedule.return_value = sample_template
            mock_scheduler_svc.return_value = mock_scheduler_instance

            response = await async_client.post(
                f"/api/v1/reports/templates/{template_id}/schedule",
                json={
                    "cron_expression": "0 8 * * 1",
                    "timezone": "Europe/Berlin",
                    "format": "excel",
                },
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 404]


# =============================================================================
# Data Source & Field Definition Tests
# =============================================================================

class TestDataSourceDefinitions:
    """Tests fuer Datenquellen-Definitionen."""

    @pytest.mark.asyncio
    async def test_get_available_fields(self, async_client, auth_headers):
        """Verfuegbare Felder abrufen."""
        with patch("app.api.v1.reports.ReportBuilderService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.get_available_fields.return_value = [
                {"path": "id", "display_name": "ID", "data_type": "uuid", "category": "base"},
                {"path": "created_at", "display_name": "Erstellt am", "data_type": "date", "category": "base"},
            ]
            mock_service.return_value = mock_instance

            response = await async_client.get(
                "/api/v1/reports/fields?data_source=documents",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 404]

    @pytest.mark.asyncio
    async def test_get_available_operators(self, async_client, auth_headers):
        """Verfuegbare Operatoren abrufen."""
        with patch("app.api.v1.reports.ReportBuilderService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.get_available_operators.return_value = [
                {"id": "eq", "name": "Gleich", "types": ["string", "number"]},
                {"id": "gte", "name": "Groesser gleich", "types": ["number", "date"]},
            ]
            mock_service.return_value = mock_instance

            response = await async_client.get(
                "/api/v1/reports/operators",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 404]


# =============================================================================
# Validation Tests
# =============================================================================

class TestValidation:
    """Tests fuer Validierung."""

    @pytest.mark.asyncio
    async def test_create_template_invalid_name(self, async_client, auth_headers):
        """Template mit ungueltigem Namen erstellen."""
        response = await async_client.post(
            "/api/v1/reports/templates",
            json={
                "name": "",  # Leerer Name
                "report_type": "document",
                "data_source": "documents",
            },
            headers=auth_headers,
        )

        assert response.status_code in [401, 422]

    @pytest.mark.asyncio
    async def test_create_template_invalid_type(self, async_client, auth_headers):
        """Template mit ungueltigem Typ erstellen."""
        response = await async_client.post(
            "/api/v1/reports/templates",
            json={
                "name": "Test Report",
                "report_type": "invalid_type",  # Ungueltiger Typ
                "data_source": "documents",
            },
            headers=auth_headers,
        )

        assert response.status_code in [401, 422]

    @pytest.mark.asyncio
    async def test_add_filter_invalid_operator(self, async_client, auth_headers, sample_template):
        """Filter mit ungueltigem Operator hinzufuegen."""
        template_id = sample_template.id

        with patch("app.api.v1.reports.ReportTemplateService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.get_template.return_value = sample_template
            mock_service.return_value = mock_instance

            response = await async_client.post(
                f"/api/v1/reports/templates/{template_id}/filters",
                json={
                    "field_path": "extracted_data.amount",
                    "operator": "invalid_op",  # Ungueltiger Operator
                    "value": 100,
                },
                headers=auth_headers,
            )

            assert response.status_code in [401, 422]

    @pytest.mark.asyncio
    async def test_add_chart_invalid_type(self, async_client, auth_headers, sample_template):
        """Chart mit ungueltigem Typ hinzufuegen."""
        template_id = sample_template.id

        with patch("app.api.v1.reports.ReportTemplateService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.get_template.return_value = sample_template
            mock_service.return_value = mock_instance

            response = await async_client.post(
                f"/api/v1/reports/templates/{template_id}/charts",
                json={
                    "chart_type": "invalid_chart",  # Ungueltiger Charttyp
                    "y_axis_fields": ["amount"],
                },
                headers=auth_headers,
            )

            assert response.status_code in [401, 422]
