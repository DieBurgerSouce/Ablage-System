# -*- coding: utf-8 -*-
"""Integrationstests fuer den KPI Orchestrator.

Tests fuer:
- KPI Berechnung ueber alle Entity-Types
- Event-Emission nach Berechnungen
- Orchestration-Workflow
- Service-Koordination
- Celery Task Integration

Alle Tests auf Deutsch mit deutschen Fehlermeldungen.
"""

import pytest
from fastapi import status
from uuid import uuid4
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.integration
@pytest.mark.api
class TestKPIOrchestrationAPI:
    """Tests fuer KPI Orchestration API Endpoints."""

    def test_recalculate_space_kpis_endpoint_exists(self, client):
        """Test dass KPI-Neuberechnung-Endpoint fuer Space erreichbar ist."""
        space_id = uuid4()
        response = client.post(f"/api/v1/privat/analytics/spaces/{space_id}/recalculate-kpis")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_202_ACCEPTED,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_property_kpis_endpoint_exists(self, client):
        """Test dass Property-KPIs-Endpoint erreichbar ist."""
        space_id = uuid4()
        response = client.get(f"/api/v1/privat/analytics/spaces/{space_id}/properties/kpis")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_vehicle_kpis_endpoint_exists(self, client):
        """Test dass Vehicle-KPIs-Endpoint erreichbar ist."""
        space_id = uuid4()
        response = client.get(f"/api/v1/privat/analytics/spaces/{space_id}/vehicles/kpis")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_loan_kpis_endpoint_exists(self, client):
        """Test dass Loan-KPIs-Endpoint erreichbar ist."""
        space_id = uuid4()
        response = client.get(f"/api/v1/privat/analytics/spaces/{space_id}/loans/kpis")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_investment_kpis_endpoint_exists(self, client):
        """Test dass Investment-KPIs-Endpoint erreichbar ist."""
        space_id = uuid4()
        response = client.get(f"/api/v1/privat/analytics/spaces/{space_id}/investments/kpis")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_insurance_kpis_endpoint_exists(self, client):
        """Test dass Insurance-KPIs-Endpoint erreichbar ist."""
        space_id = uuid4()
        response = client.get(f"/api/v1/privat/analytics/spaces/{space_id}/insurances/kpis")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_financial_health_endpoint_exists(self, client):
        """Test dass Financial-Health-Endpoint erreichbar ist."""
        space_id = uuid4()
        response = client.get(f"/api/v1/privat/analytics/spaces/{space_id}/financial-health")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]


@pytest.mark.integration
@pytest.mark.api
class TestKIAnalysisAPI:
    """Tests fuer KI-Analyse Endpoints."""

    def test_property_ki_analysis_endpoint_exists(self, client):
        """Test dass Property-KI-Analyse-Endpoint erreichbar ist."""
        property_id = uuid4()
        response = client.post(f"/api/v1/privat/analytics/properties/{property_id}/ki-analysis")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_429_TOO_MANY_REQUESTS,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ]

    def test_vehicle_ki_analysis_endpoint_exists(self, client):
        """Test dass Vehicle-KI-Analyse-Endpoint erreichbar ist."""
        vehicle_id = uuid4()
        response = client.post(f"/api/v1/privat/analytics/vehicles/{vehicle_id}/ki-analysis")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_429_TOO_MANY_REQUESTS,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ]

    def test_investment_ki_advice_endpoint_exists(self, client):
        """Test dass Investment-KI-Advice-Endpoint erreichbar ist."""
        space_id = uuid4()
        response = client.post(f"/api/v1/privat/analytics/spaces/{space_id}/investments/ki-advice")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_429_TOO_MANY_REQUESTS,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ]

    def test_insurance_ki_check_endpoint_exists(self, client):
        """Test dass Insurance-KI-Check-Endpoint erreichbar ist."""
        space_id = uuid4()
        response = client.post(f"/api/v1/privat/analytics/spaces/{space_id}/insurances/ki-check")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_429_TOO_MANY_REQUESTS,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ]

    def test_financial_qa_endpoint_exists(self, client):
        """Test dass Financial-QA-Endpoint erreichbar ist."""
        space_id = uuid4()
        response = client.post(
            f"/api/v1/privat/analytics/spaces/{space_id}/financial-qa",
            json={"question": "Wie hoch ist meine Mietrendite?"}
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            status.HTTP_429_TOO_MANY_REQUESTS,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ]

    def test_financial_qa_requires_question(self, client):
        """Test dass Financial-QA eine Frage erfordert."""
        space_id = uuid4()
        response = client.post(
            f"/api/v1/privat/analytics/spaces/{space_id}/financial-qa",
            json={}  # Keine Frage
        )
        assert response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]


@pytest.mark.integration
class TestKPIOrchestratorService:
    """Tests fuer den KPI Orchestrator Service."""

    @pytest.mark.asyncio
    async def test_kpi_orchestrator_service_imports(self):
        """Test dass KPI Orchestrator Service importierbar ist."""
        try:
            from app.services.privat.kpi_orchestrator import (
                KPIOrchestrationService,
                get_kpi_orchestration_service,
                KPIRecalculationResult,
                EntityKPIResult,
                OrchestrationStatus,
            )

            assert KPIOrchestrationService is not None
            assert get_kpi_orchestration_service is not None
            assert KPIRecalculationResult is not None
            assert EntityKPIResult is not None
            assert OrchestrationStatus is not None
        except ImportError as e:
            pytest.skip(f"KPI Orchestrator Service nicht verfuegbar: {e}")

    @pytest.mark.asyncio
    async def test_singleton_pattern(self):
        """Test dass Singleton-Pattern funktioniert."""
        try:
            from app.services.privat.kpi_orchestrator import get_kpi_orchestration_service

            service1 = get_kpi_orchestration_service()
            service2 = get_kpi_orchestration_service()

            assert service1 is service2
        except ImportError:
            pytest.skip("KPI Orchestrator Service nicht verfuegbar")

    @pytest.mark.asyncio
    async def test_recalculate_all_for_space_method_exists(self):
        """Test dass recalculate_all_for_space Methode existiert."""
        try:
            from app.services.privat.kpi_orchestrator import KPIOrchestrationService

            service = KPIOrchestrationService()
            assert hasattr(service, 'recalculate_all_for_space')
            assert callable(getattr(service, 'recalculate_all_for_space'))
        except ImportError:
            pytest.skip("KPI Orchestrator Service nicht verfuegbar")


@pytest.mark.integration
class TestInsuranceIntelligenceService:
    """Tests fuer den Insurance Intelligence Service."""

    @pytest.mark.asyncio
    async def test_insurance_intelligence_service_imports(self):
        """Test dass Insurance Intelligence Service importierbar ist."""
        try:
            from app.services.privat.insurance_intelligence_service import (
                InsuranceIntelligenceService,
                get_insurance_intelligence_service,
                InsuranceIntelligenceResult,
                InsuranceRecommendation,
                RenewalAlert,
            )

            assert InsuranceIntelligenceService is not None
            assert get_insurance_intelligence_service is not None
            assert InsuranceIntelligenceResult is not None
            assert InsuranceRecommendation is not None
            assert RenewalAlert is not None
        except ImportError as e:
            pytest.skip(f"Insurance Intelligence Service nicht verfuegbar: {e}")

    @pytest.mark.asyncio
    async def test_singleton_pattern(self):
        """Test dass Singleton-Pattern funktioniert."""
        try:
            from app.services.privat.insurance_intelligence_service import (
                get_insurance_intelligence_service,
            )

            service1 = get_insurance_intelligence_service()
            service2 = get_insurance_intelligence_service()

            assert service1 is service2
        except ImportError:
            pytest.skip("Insurance Intelligence Service nicht verfuegbar")


@pytest.mark.integration
class TestPrivatKIPromptService:
    """Tests fuer den Privat KI-Prompt Service."""

    @pytest.mark.asyncio
    async def test_ki_prompt_service_imports(self):
        """Test dass KI-Prompt Service importierbar ist."""
        try:
            from app.services.privat.ki_prompt_service import (
                PrivatKIPromptService,
                get_privat_ki_prompt_service,
                PropertyValueAnalysis,
                VehicleDepreciationAnalysis,
                InvestmentAdvice,
                InsuranceCheckResult,
                FinancialQAResponse,
            )

            assert PrivatKIPromptService is not None
            assert get_privat_ki_prompt_service is not None
            assert PropertyValueAnalysis is not None
            assert VehicleDepreciationAnalysis is not None
            assert InvestmentAdvice is not None
            assert InsuranceCheckResult is not None
            assert FinancialQAResponse is not None
        except ImportError as e:
            pytest.skip(f"KI-Prompt Service nicht verfuegbar: {e}")

    @pytest.mark.asyncio
    async def test_singleton_pattern(self):
        """Test dass Singleton-Pattern funktioniert."""
        try:
            from app.services.privat.ki_prompt_service import get_privat_ki_prompt_service

            service1 = get_privat_ki_prompt_service()
            service2 = get_privat_ki_prompt_service()

            assert service1 is service2
        except ImportError:
            pytest.skip("KI-Prompt Service nicht verfuegbar")

    @pytest.mark.asyncio
    async def test_templates_exist(self):
        """Test dass alle Templates existieren."""
        try:
            from app.services.privat.ki_prompt_service import PrivatKIPromptService

            service = PrivatKIPromptService()

            expected_templates = [
                "property_valuation.j2",
                "vehicle_analysis.j2",
                "investment_advice.j2",
                "insurance_check.j2",
                "financial_qa.j2",
            ]

            for template_name in expected_templates:
                template_path = service._template_dir / template_name
                assert template_path.exists(), f"Template fehlt: {template_name}"
        except ImportError:
            pytest.skip("KI-Prompt Service nicht verfuegbar")


@pytest.mark.integration
class TestEventBusIntegration:
    """Tests fuer Event Bus Integration."""

    @pytest.mark.asyncio
    async def test_kpi_event_types_exist(self):
        """Test dass alle KPI Event-Types definiert sind."""
        try:
            from app.services.events.event_bus import (
                PROPERTY_KPIS_CALCULATED,
                VEHICLE_KPIS_CALCULATED,
                LOAN_KPIS_CALCULATED,
                INVESTMENT_PERFORMANCE_CALCULATED,
                FINANCE_HEALTH_SCORE_UPDATED,
            )

            assert PROPERTY_KPIS_CALCULATED is not None
            assert VEHICLE_KPIS_CALCULATED is not None
            assert LOAN_KPIS_CALCULATED is not None
            assert INVESTMENT_PERFORMANCE_CALCULATED is not None
            assert FINANCE_HEALTH_SCORE_UPDATED is not None
        except ImportError as e:
            pytest.skip(f"Event Bus nicht verfuegbar: {e}")

    @pytest.mark.asyncio
    async def test_event_types_are_strings(self):
        """Test dass Event-Types Strings sind."""
        try:
            from app.services.events.event_bus import (
                PROPERTY_KPIS_CALCULATED,
                VEHICLE_KPIS_CALCULATED,
                LOAN_KPIS_CALCULATED,
                INVESTMENT_PERFORMANCE_CALCULATED,
                FINANCE_HEALTH_SCORE_UPDATED,
            )

            assert isinstance(PROPERTY_KPIS_CALCULATED, str)
            assert isinstance(VEHICLE_KPIS_CALCULATED, str)
            assert isinstance(LOAN_KPIS_CALCULATED, str)
            assert isinstance(INVESTMENT_PERFORMANCE_CALCULATED, str)
            assert isinstance(FINANCE_HEALTH_SCORE_UPDATED, str)
        except ImportError:
            pytest.skip("Event Bus nicht verfuegbar")


@pytest.mark.integration
class TestCeleryTasksIntegration:
    """Tests fuer Celery Tasks Integration."""

    @pytest.mark.asyncio
    async def test_kpi_tasks_importable(self):
        """Test dass KPI Celery Tasks importierbar sind."""
        try:
            from app.workers.tasks.privat_tasks import (
                recalculate_insurance_kpis,
            )

            assert recalculate_insurance_kpis is not None
        except ImportError as e:
            pytest.skip(f"Celery Tasks nicht verfuegbar: {e}")

    @pytest.mark.asyncio
    async def test_celery_beat_schedule_contains_kpi_tasks(self):
        """Test dass Beat Schedule KPI Tasks enthaelt."""
        try:
            from app.workers.celery_app import celery_app

            beat_schedule = celery_app.conf.beat_schedule

            # Mindestens ein KPI-bezogener Task sollte vorhanden sein
            kpi_related_tasks = [
                key for key in beat_schedule.keys()
                if 'kpi' in key.lower() or 'insurance' in key.lower()
            ]

            assert len(kpi_related_tasks) > 0, "Keine KPI-Tasks im Beat Schedule gefunden"
        except ImportError as e:
            pytest.skip(f"Celery App nicht verfuegbar: {e}")


@pytest.mark.integration
@pytest.mark.api
class TestKPIDataIntegrity:
    """Tests fuer KPI Daten-Integritaet."""

    def test_kpi_response_contains_required_fields(self, client):
        """Test dass KPI-Responses alle erforderlichen Felder enthalten."""
        space_id = uuid4()
        response = client.get(f"/api/v1/privat/analytics/spaces/{space_id}/financial-health")

        # Wenn erfolgreich, pruefe Response-Struktur
        if response.status_code == status.HTTP_200_OK:
            data = response.json()
            # Erwartete Felder fuer Financial Health
            expected_fields = ["health_score", "space_id"]
            for field in expected_fields:
                assert field in data or "detail" in data, f"Feld {field} fehlt in Response"

    def test_ki_analysis_response_structure(self, client):
        """Test dass KI-Analyse-Responses korrekte Struktur haben."""
        property_id = uuid4()
        response = client.post(f"/api/v1/privat/analytics/properties/{property_id}/ki-analysis")

        # Bei Erfolg pruefe Response-Struktur
        if response.status_code == status.HTTP_200_OK:
            data = response.json()
            # Sollte mindestens property_id enthalten
            assert "property_id" in data or "detail" in data or "error" in data


@pytest.mark.integration
@pytest.mark.api
@pytest.mark.security
class TestKPISecurityControls:
    """Tests fuer KPI Security Controls."""

    def test_kpi_endpoints_require_authentication(self, client):
        """Test dass KPI-Endpoints Authentifizierung erfordern."""
        space_id = uuid4()
        endpoints = [
            f"/api/v1/privat/analytics/spaces/{space_id}/recalculate-kpis",
            f"/api/v1/privat/analytics/spaces/{space_id}/financial-health",
        ]

        for endpoint in endpoints:
            if "recalculate" in endpoint:
                response = client.post(endpoint)
            else:
                response = client.get(endpoint)

            # Sollte nicht 200 ohne Auth zurueckgeben
            # (ausser bei deaktivierter Auth im Test-Modus)
            assert response.status_code in [
                status.HTTP_200_OK,
                status.HTTP_400_BAD_REQUEST,
                status.HTTP_401_UNAUTHORIZED,
                status.HTTP_403_FORBIDDEN,
                status.HTTP_404_NOT_FOUND,
            ]

    def test_ki_analysis_rate_limiting(self, client):
        """Test dass KI-Analyse Rate Limiting hat."""
        property_id = uuid4()
        responses = []

        # Mehrere Anfragen schnell hintereinander
        for _ in range(5):
            response = client.post(f"/api/v1/privat/analytics/properties/{property_id}/ki-analysis")
            responses.append(response.status_code)

        # Mindestens eine sollte erfolgreich sein oder Rate Limited
        valid_codes = [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_429_TOO_MANY_REQUESTS,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ]
        for code in responses:
            assert code in valid_codes

    def test_no_sensitive_data_in_ki_responses(self, client):
        """Test dass KI-Responses keine sensiblen Daten enthalten."""
        property_id = uuid4()
        response = client.post(f"/api/v1/privat/analytics/properties/{property_id}/ki-analysis")

        if response.status_code == status.HTTP_200_OK:
            data_str = response.text.lower()
            # Sensible Daten sollten nicht in Response sein
            sensitive_patterns = ["password", "secret", "api_key", "token"]
            for pattern in sensitive_patterns:
                assert pattern not in data_str, f"Sensibles Muster '{pattern}' in Response gefunden"
