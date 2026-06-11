# -*- coding: utf-8 -*-
"""Unit-Tests fuer ehrliche Risikodatenquellen-Status (W1-011).

Testet:
- RiskScoringService: external_source_status statt stillem None,
  is_complete/missing_sources in Factors + DetailedResponse, Einmal-WARN
- BundesanzeigerService: source_status (mock/live/fehler) + Einmal-WARN
- HandelsregisterService: source_status auf CompanyRecord (mock/mock_fallback)
- CreditreformService: source_status auf CreditCheckResult (mock/fehler)
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

import app.services.external.bundesanzeiger_service as ba_module
import app.services.external.creditreform_service as cr_module
import app.services.external.handelsregister_service as hr_module
import app.services.risk_scoring_service as rs_module
from app.services.external.bundesanzeiger_service import BundesanzeigerService
from app.services.external.creditreform_service import CreditreformService
from app.services.external.handelsregister_service import HandelsregisterService
from app.services.risk_scoring_service import (
    SOURCE_STATUS_FEHLER,
    SOURCE_STATUS_KEINE_DATEN,
    SOURCE_STATUS_NICHT_ABGEFRAGT,
    SOURCE_STATUS_NICHT_KONFIGURIERT,
    SOURCE_STATUS_VERFUEGBAR,
    ExternalData,
    ExternalDataProvider,
    RiskFactor,
    RiskFactors,
    RiskLevel,
    RiskScoreDetailedResponse,
    RiskScoringService,
    TrendDirection,
)

TEST_ENTITY_UUID = UUID("00000000-0000-0000-0000-000000000003")

pytestmark = [pytest.mark.unit]


# ========================= Fake Provider =========================


class _FakeProvider(ExternalDataProvider):
    """Konfigurierbarer Fake-Provider fuer Tests."""

    def __init__(
        self,
        name: str,
        available: bool,
        data: Optional[ExternalData] = None,
        raise_error: bool = False,
    ) -> None:
        self._name = name
        self._available = available
        self._data = data
        self._raise = raise_error

    @property
    def provider_name(self) -> str:
        return self._name

    async def get_company_data(
        self, entity_id: UUID, vat_id: Optional[str] = None
    ) -> Optional[ExternalData]:
        if self._raise:
            raise RuntimeError("API nicht erreichbar")
        return self._data

    async def is_available(self) -> bool:
        return self._available


# ========================= RiskScoringService =========================


class TestRiskSourceStatus:
    """Tests fuer external_source_status im Risk Scoring."""

    @pytest.mark.asyncio
    async def test_default_stubs_report_nicht_konfiguriert(self) -> None:
        """Die 3 Default-Stubs (NorthData/Schufa/Creditreform) melden Status."""
        service = RiskScoringService()
        factors = RiskFactors()

        await service._fetch_external_data(TEST_ENTITY_UUID, None, factors)

        assert factors.external_source_status == {
            "north_data": SOURCE_STATUS_NICHT_KONFIGURIERT,
            "schufa_b2b": SOURCE_STATUS_NICHT_KONFIGURIERT,
            "creditreform": SOURCE_STATUS_NICHT_KONFIGURIERT,
        }
        assert factors.external_data is None
        assert factors.external_data_complete is False
        assert sorted(factors.external_missing_sources) == [
            "creditreform",
            "north_data",
            "schufa_b2b",
        ]

    @pytest.mark.asyncio
    async def test_provider_with_data_reports_verfuegbar(self) -> None:
        """Konfigurierter Provider mit Daten -> verfuegbar; Rest nicht_abgefragt."""
        data = ExternalData(provider="fake_a", credit_score=42)
        service = RiskScoringService(
            external_providers=[
                _FakeProvider("fake_a", available=True, data=data),
                _FakeProvider("fake_b", available=True, data=None),
            ]
        )
        factors = RiskFactors()

        await service._fetch_external_data(TEST_ENTITY_UUID, "DE123", factors)

        assert factors.external_source_status["fake_a"] == SOURCE_STATUS_VERFUEGBAR
        # First-Hit-Semantik: fake_b wird nicht mehr abgefragt
        assert factors.external_source_status["fake_b"] == SOURCE_STATUS_NICHT_ABGEFRAGT
        assert factors.external_data is data
        assert factors.economic_indicator_score == 42.0

    @pytest.mark.asyncio
    async def test_provider_without_data_reports_keine_daten(self) -> None:
        """Konfigurierter Provider ohne Daten -> keine_daten."""
        service = RiskScoringService(
            external_providers=[_FakeProvider("fake_a", available=True, data=None)]
        )
        factors = RiskFactors()

        await service._fetch_external_data(TEST_ENTITY_UUID, None, factors)

        assert factors.external_source_status["fake_a"] == SOURCE_STATUS_KEINE_DATEN
        assert factors.external_data_complete is False

    @pytest.mark.asyncio
    async def test_provider_error_reports_fehler(self) -> None:
        """Provider-Exception -> fehler (kein Crash, kein stilles None)."""
        service = RiskScoringService(
            external_providers=[
                _FakeProvider("fake_err", available=True, raise_error=True)
            ]
        )
        factors = RiskFactors()

        await service._fetch_external_data(TEST_ENTITY_UUID, None, factors)

        assert factors.external_source_status["fake_err"] == SOURCE_STATUS_FEHLER

    @pytest.mark.asyncio
    async def test_unconfigured_warned_only_once(self, monkeypatch) -> None:
        """WARN-Log fuer unkonfigurierte Quellen erscheint nur einmal pro Prozess."""
        monkeypatch.setattr(rs_module, "_UNCONFIGURED_SOURCES_WARNED", False)
        service = RiskScoringService()

        with patch.object(rs_module, "logger") as mock_logger:
            await service._fetch_external_data(TEST_ENTITY_UUID, None, RiskFactors())
            await service._fetch_external_data(TEST_ENTITY_UUID, None, RiskFactors())

        warn_calls = [
            c
            for c in mock_logger.warning.call_args_list
            if c.args and c.args[0] == "risk_datenquellen_nicht_konfiguriert"
        ]
        assert len(warn_calls) == 1

    def test_factors_to_dict_contains_source_status(self) -> None:
        """to_dict kennzeichnet Datenquellen-Luecken (additiv)."""
        factors = RiskFactors()
        factors.external_source_status = {
            "north_data": SOURCE_STATUS_NICHT_KONFIGURIERT,
        }

        result = factors.to_dict()

        assert result["external_sources"] == {
            "north_data": SOURCE_STATUS_NICHT_KONFIGURIERT
        }
        assert result["external_data_complete"] is False
        assert result["external_missing_sources"] == ["north_data"]

    def test_factors_to_dict_without_status_stays_compatible(self) -> None:
        """Ohne Status-Daten bleibt to_dict abwaertskompatibel (keine Keys)."""
        result = RiskFactors().to_dict()

        assert "external_sources" not in result
        assert "external_data_complete" not in result

    def test_detailed_response_to_dict_contains_completeness(self) -> None:
        """DetailedResponse traegt is_complete/missing_sources (additiv)."""
        response = RiskScoreDetailedResponse(
            entity_id=uuid4(),
            overall_score=42,
            risk_level=RiskLevel.MEDIUM,
            factors={
                "payment_delay": RiskFactor(
                    name="payment_delay",
                    value=5.0,
                    score=16.7,
                    weight=0.2,
                    weighted_score=3.3,
                    description="Zahlungsverzoegerung: 5.0 Tage",
                )
            },
            trend=TrendDirection.STABLE,
            trend_score_adjustment=0,
            last_calculated=datetime.now(timezone.utc),
            recommendations=["Keine besonderen Massnahmen erforderlich"],
            payment_behavior_score=80.0,
            external_sources={"north_data": SOURCE_STATUS_NICHT_KONFIGURIERT},
            is_complete=False,
            missing_sources=["north_data"],
        )

        result = response.to_dict()

        assert result["is_complete"] is False
        assert result["missing_sources"] == ["north_data"]
        assert result["external_sources"] == {
            "north_data": SOURCE_STATUS_NICHT_KONFIGURIERT
        }


# ========================= BundesanzeigerService =========================


class TestBundesanzeigerSourceStatus:
    """Tests fuer source_status im Bundesanzeiger-Service."""

    @pytest.mark.asyncio
    async def test_mock_result_is_marked(self, monkeypatch) -> None:
        """Mock-Modus kennzeichnet das Ergebnis als 'mock'."""
        service = BundesanzeigerService()
        service.mock_enabled = True

        result = await service.check_insolvency("Beispiel GmbH")

        assert result.source_status == ba_module.SOURCE_STATUS_MOCK

    @pytest.mark.asyncio
    async def test_live_error_is_marked_fehler(self) -> None:
        """Fehler im Live-Pfad -> source_status 'fehler' (keine Entwarnung)."""
        service = BundesanzeigerService()
        service.mock_enabled = False

        with patch.object(
            service,
            "_search_bundesanzeiger",
            AsyncMock(side_effect=RuntimeError("Portal nicht erreichbar")),
        ):
            result = await service.check_insolvency("Beispiel GmbH")

        assert result.source_status == ba_module.SOURCE_STATUS_FEHLER
        assert result.has_insolvency is False

    @pytest.mark.asyncio
    async def test_live_success_is_marked_live(self) -> None:
        """Erfolgreicher Live-Pfad -> source_status 'live'."""
        service = BundesanzeigerService()
        service.mock_enabled = False

        with patch.object(
            service, "_search_bundesanzeiger", AsyncMock(return_value=[])
        ):
            result = await service.check_insolvency("Beispiel GmbH")

        assert result.source_status == ba_module.SOURCE_STATUS_LIVE

    def test_mock_warned_only_once(self, monkeypatch) -> None:
        """Mock-Modus-WARN erscheint nur einmal pro Prozess."""
        monkeypatch.setattr(ba_module, "_MOCK_MODE_WARNED", False)
        # Settings-Ersatz: BUNDESANZEIGER_MOCK=True (pydantic verbietet
        # das Setzen unbekannter Felder auf dem echten Settings-Objekt)
        monkeypatch.setattr(
            ba_module, "settings", SimpleNamespace(BUNDESANZEIGER_MOCK=True)
        )

        with patch.object(ba_module, "logger") as mock_logger:
            BundesanzeigerService()
            BundesanzeigerService()

        warn_calls = [
            c
            for c in mock_logger.warning.call_args_list
            if c.args and c.args[0] == "bundesanzeiger_mock_modus_aktiv"
        ]
        assert len(warn_calls) == 1

    def test_mock_search_publications_marked(self) -> None:
        """Mock-Publikations-Dicts tragen source_status 'mock'."""
        service = BundesanzeigerService()

        publications = service._mock_search_publications("Insolvenz Test GmbH")

        assert publications  # Szenario "insolvenz" liefert Eintraege
        assert all(
            p["source_status"] == ba_module.SOURCE_STATUS_MOCK for p in publications
        )


# ========================= HandelsregisterService =========================


class TestHandelsregisterSourceStatus:
    """Tests fuer source_status im Handelsregister-Service."""

    @pytest.mark.asyncio
    async def test_mock_mode_marks_records(self) -> None:
        """Expliziter Mock-Modus kennzeichnet Records als 'mock'."""
        service = HandelsregisterService()
        service.mock_enabled = True

        records = await service.search_company("Testfirma GmbH")

        assert records
        assert all(
            r.source_status == hr_module.SOURCE_STATUS_MOCK for r in records
        )

    @pytest.mark.asyncio
    async def test_portal_error_marks_fallback(self) -> None:
        """Portal-Fehler -> Fallback-Records als 'mock_fallback' gekennzeichnet."""
        service = HandelsregisterService()
        service.mock_enabled = False

        with patch.object(
            service, "_get_from_cache", AsyncMock(return_value=None)
        ), patch.object(
            service,
            "_fetch_from_portal",
            AsyncMock(side_effect=RuntimeError("Portal nicht erreichbar")),
        ):
            records = await service.search_company("Testfirma GmbH")

        assert records
        assert all(
            r.source_status == hr_module.SOURCE_STATUS_MOCK_FALLBACK for r in records
        )

    def test_record_dict_roundtrip_keeps_status(self) -> None:
        """source_status uebersteht die Cache-Serialisierung."""
        service = HandelsregisterService()
        records = service._mock_search("Testfirma GmbH")
        record = records[0]

        roundtripped = service._dict_to_record(service._record_to_dict(record))

        assert roundtripped.source_status == hr_module.SOURCE_STATUS_MOCK

    def test_old_cache_entry_defaults_to_live(self) -> None:
        """Alt-Cache-Eintraege ohne Feld -> 'live' (Cache enthaelt nur Live-Daten)."""
        service = HandelsregisterService()

        record = service._dict_to_record({"name": "Testfirma GmbH"})

        assert record.source_status == hr_module.SOURCE_STATUS_LIVE

    def test_mock_warned_only_once(self, monkeypatch) -> None:
        """Mock-Modus-WARN erscheint nur einmal pro Prozess."""
        monkeypatch.setattr(hr_module, "_MOCK_MODE_WARNED", False)
        monkeypatch.setattr(
            hr_module,
            "settings",
            SimpleNamespace(HANDELSREGISTER_MOCK_ENABLED=True),
        )

        with patch.object(hr_module, "logger") as mock_logger:
            HandelsregisterService()
            HandelsregisterService()

        warn_calls = [
            c
            for c in mock_logger.warning.call_args_list
            if c.args and c.args[0] == "handelsregister_mock_modus_aktiv"
        ]
        assert len(warn_calls) == 1


# ========================= CreditreformService =========================


class TestCreditreformSourceStatus:
    """Tests fuer source_status im Creditreform-Service."""

    @pytest.mark.asyncio
    async def test_mock_mode_marks_result(self, monkeypatch) -> None:
        """Ohne Credentials -> Mock-Modus -> source_status 'mock'."""
        monkeypatch.setattr(cr_module, "settings", SimpleNamespace())
        service = CreditreformService(redis_client=None)
        assert service.mock_mode is True

        result = await service.check_credit(company_name="Beispiel GmbH")

        assert result.source_status == cr_module.SOURCE_STATUS_MOCK

    def test_error_result_marked_fehler(self) -> None:
        """Fehler-Ergebnis traegt source_status 'fehler'."""
        service = CreditreformService(redis_client=None)

        result = service._generate_error_result(
            {"company_name": "Beispiel GmbH"}, "Abfrage fehlgeschlagen"
        )

        assert result.source_status == cr_module.SOURCE_STATUS_FEHLER

    @pytest.mark.asyncio
    async def test_mock_insolvency_status_marked(self, monkeypatch) -> None:
        """Mock-Insolvenz-Status traegt source_status 'mock' (additiv)."""
        monkeypatch.setattr(cr_module, "settings", SimpleNamespace())
        service = CreditreformService(redis_client=None)

        status = await service.get_insolvency_status("CREFO-123")

        assert status["source_status"] == cr_module.SOURCE_STATUS_MOCK

    def test_mock_warned_only_once(self, monkeypatch) -> None:
        """Mock-Modus-WARN erscheint nur einmal pro Prozess (deutsch)."""
        monkeypatch.setattr(cr_module, "_MOCK_MODE_WARNED", False)
        monkeypatch.setattr(cr_module, "settings", SimpleNamespace())

        with patch.object(cr_module, "logger") as mock_logger:
            CreditreformService(redis_client=None)
            CreditreformService(redis_client=None)

        warn_calls = [
            c
            for c in mock_logger.warning.call_args_list
            if c.args and c.args[0] == "creditreform_mock_modus_aktiv"
        ]
        assert len(warn_calls) == 1
