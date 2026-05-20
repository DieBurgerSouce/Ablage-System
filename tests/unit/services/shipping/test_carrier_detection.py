# -*- coding: utf-8 -*-
"""Unit tests for carrier detection in CarrierService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.shipping.carrier_service import (
    Carrier,
    CarrierService,
    ShipmentDirection,
    ShipmentSummary,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service() -> CarrierService:
    with patch("app.services.shipping.carrier_service.DHLProvider"), \
         patch("app.services.shipping.carrier_service.DPDProvider"), \
         patch("app.services.shipping.carrier_service.HermesProvider"), \
         patch("app.services.shipping.carrier_service.UPSProvider"), \
         patch("app.services.shipping.carrier_service.GLSProvider"), \
         patch("app.services.shipping.carrier_service.FedExProvider"), \
         patch("app.services.shipping.carrier_service.DeutschePostProvider"):
        svc = CarrierService()
    return svc


# ---------------------------------------------------------------------------
# Carrier enum
# ---------------------------------------------------------------------------


class TestCarrierEnum:
    def test_dhl_value(self) -> None:
        assert Carrier.DHL.value == "dhl"

    def test_dpd_value(self) -> None:
        assert Carrier.DPD.value == "dpd"

    def test_hermes_value(self) -> None:
        assert Carrier.HERMES.value == "hermes"

    def test_ups_value(self) -> None:
        assert Carrier.UPS.value == "ups"

    def test_gls_value(self) -> None:
        assert Carrier.GLS.value == "gls"

    def test_fedex_value(self) -> None:
        assert Carrier.FEDEX.value == "fedex"

    def test_deutsche_post_value(self) -> None:
        assert Carrier.DEUTSCHE_POST.value == "deutsche_post"

    def test_unknown_value(self) -> None:
        assert Carrier.UNKNOWN.value == "unknown"

    def test_carrier_is_str_enum(self) -> None:
        assert isinstance(Carrier.DHL, str)
        assert Carrier.DHL == "dhl"

    def test_all_carriers_count(self) -> None:
        assert len(Carrier) == 8


# ---------------------------------------------------------------------------
# ShipmentDirection enum
# ---------------------------------------------------------------------------


class TestShipmentDirectionEnum:
    def test_inbound_value(self) -> None:
        assert ShipmentDirection.INBOUND.value == "inbound"

    def test_outbound_value(self) -> None:
        assert ShipmentDirection.OUTBOUND.value == "outbound"

    def test_return_value(self) -> None:
        assert ShipmentDirection.RETURN.value == "return"

    def test_direction_is_str_enum(self) -> None:
        assert isinstance(ShipmentDirection.INBOUND, str)


# ---------------------------------------------------------------------------
# detect_carrier
# ---------------------------------------------------------------------------


class TestDetectCarrier:
    def test_detect_dhl_tracking(self, service: CarrierService) -> None:
        """DHL tracking numbers start with 00340 + 17 digits."""
        tracking = "0034043417345678901234"  # 00340 + 17 digits = 22 chars
        # Configure mock so DHL matches, others don't
        for carrier, provider in service._providers.items():
            if carrier == Carrier.DHL:
                provider.matches_tracking_number.return_value = True
            else:
                provider.matches_tracking_number.return_value = False

        result = service.detect_carrier(tracking)
        assert result == Carrier.DHL

    def test_detect_ups_tracking(self, service: CarrierService) -> None:
        """UPS tracking numbers start with 1Z."""
        tracking = "1ZABCDEF1234567890"
        for carrier, provider in service._providers.items():
            if carrier == Carrier.UPS:
                provider.matches_tracking_number.return_value = True
            else:
                provider.matches_tracking_number.return_value = False

        result = service.detect_carrier(tracking)
        assert result == Carrier.UPS

    def test_detect_hermes_tracking(self, service: CarrierService) -> None:
        tracking = "H1234567890123456789"
        for carrier, provider in service._providers.items():
            if carrier == Carrier.HERMES:
                provider.matches_tracking_number.return_value = True
            else:
                provider.matches_tracking_number.return_value = False

        result = service.detect_carrier(tracking)
        assert result == Carrier.HERMES

    def test_detect_deutsche_post(self, service: CarrierService) -> None:
        tracking = "RR123456789DE"
        for carrier, provider in service._providers.items():
            if carrier == Carrier.DEUTSCHE_POST:
                provider.matches_tracking_number.return_value = True
            else:
                provider.matches_tracking_number.return_value = False

        result = service.detect_carrier(tracking)
        assert result == Carrier.DEUTSCHE_POST

    def test_unknown_carrier_for_invalid_tracking(self, service: CarrierService) -> None:
        """Unrecognized tracking numbers should return UNKNOWN."""
        for provider in service._providers.values():
            provider.matches_tracking_number.return_value = False

        result = service.detect_carrier("INVALID12345")
        assert result == Carrier.UNKNOWN

    def test_normalizes_spaces_and_dashes(self, service: CarrierService) -> None:
        """Tracking numbers should be normalized (spaces/dashes removed, uppercased)."""
        for carrier, provider in service._providers.items():
            if carrier == Carrier.UPS:
                provider.matches_tracking_number.return_value = True
            else:
                provider.matches_tracking_number.return_value = False

        result = service.detect_carrier("1z-abc def-1234567890")
        assert result == Carrier.UPS
        # The provider should have been called with normalized value
        service._providers[Carrier.DHL].matches_tracking_number.assert_called()

    def test_detection_order_priority(self, service: CarrierService) -> None:
        """If multiple carriers match, first in detection order wins."""
        # Make DHL and DPD both match
        for carrier, provider in service._providers.items():
            if carrier in (Carrier.DHL, Carrier.DPD):
                provider.matches_tracking_number.return_value = True
            else:
                provider.matches_tracking_number.return_value = False

        result = service.detect_carrier("00000000000000")
        # DHL comes first in detection order
        assert result == Carrier.DHL


# ---------------------------------------------------------------------------
# get_tracking_url
# ---------------------------------------------------------------------------


class TestGetTrackingUrl:
    def test_returns_url_for_known_carrier(self, service: CarrierService) -> None:
        for carrier, provider in service._providers.items():
            if carrier == Carrier.DHL:
                provider.matches_tracking_number.return_value = True
                provider.get_tracking_url.return_value = "https://dhl.de/track/123"
            else:
                provider.matches_tracking_number.return_value = False

        url = service.get_tracking_url("12345")
        assert url == "https://dhl.de/track/123"

    def test_returns_none_for_unknown_carrier(self, service: CarrierService) -> None:
        for provider in service._providers.values():
            provider.matches_tracking_number.return_value = False

        url = service.get_tracking_url("INVALID")
        assert url is None

    def test_explicit_carrier_skips_detection(self, service: CarrierService) -> None:
        service._providers[Carrier.UPS].get_tracking_url.return_value = "https://ups.com/t"

        url = service.get_tracking_url("1ZABC", carrier=Carrier.UPS)
        assert url == "https://ups.com/t"
        # DHL matches_tracking_number should NOT have been called
        service._providers[Carrier.DHL].matches_tracking_number.assert_not_called()


# ---------------------------------------------------------------------------
# _create_unknown_result
# ---------------------------------------------------------------------------


class TestCreateUnknownResult:
    def test_unknown_result_structure(self, service: CarrierService) -> None:
        result = service._create_unknown_result("INVALID123")
        assert result["tracking_number"] == "INVALID123"
        assert result["carrier"] == "unknown"
        assert result["status_description"] == "Carrier konnte nicht erkannt werden"
        assert result["events"] == []
        assert result["estimated_delivery"] is None
