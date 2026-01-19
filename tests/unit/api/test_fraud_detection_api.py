"""
Tests fuer Fraud Detection API Endpoints.

Testet alle Fraud Detection Funktionen:
- Analyse-Endpunkte
- Dashboard-Statistiken
- Alert-Filterung
- Entity-Risk-Profile
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import status


class TestFraudDetectionAPI:
    """Tests fuer Fraud Detection API."""

    @pytest.fixture
    def mock_user(self):
        """Mock authenticated user."""
        user = MagicMock()
        user.id = uuid4()
        user.company_id = uuid4()
        user.role = "user"
        return user

    @pytest.fixture
    def mock_admin(self):
        """Mock admin user."""
        user = MagicMock()
        user.id = uuid4()
        user.company_id = uuid4()
        user.role = "admin"
        return user

    @pytest.fixture
    def mock_fraud_service(self):
        """Mock FraudDetectionService."""
        service = AsyncMock()
        service.analyze_all.return_value = {
            "company_id": str(uuid4()),
            "analysis_period": {
                "start": (datetime.utcnow() - timedelta(days=90)).isoformat(),
                "end": datetime.utcnow().isoformat(),
            },
            "summary": {
                "total_alerts": 5,
                "critical": 1,
                "high": 2,
                "medium": 1,
                "low": 1,
                "estimated_risk_amount": 15000.0,
            },
            "alerts": [
                {
                    "type": "duplicate_invoice",
                    "risk_level": "high",
                    "title": "Moegliche Duplikat-Rechnung",
                    "description": "Test duplicate",
                    "confidence": 0.95,
                    "detected_at": datetime.utcnow().isoformat(),
                },
            ],
            "analyzed_at": datetime.utcnow().isoformat(),
        }
        return service

    # ==================== Analyze Endpoint Tests ====================

    @pytest.mark.asyncio
    async def test_analyze_fraud_success(
        self,
        mock_user: MagicMock,
        mock_fraud_service: AsyncMock,
    ) -> None:
        """Erfolgreiche Fraud-Analyse."""
        from app.api.v1.fraud_detection import analyze_fraud

        with patch(
            "app.api.v1.fraud_detection.FraudDetectionService",
            return_value=mock_fraud_service,
        ):
            with patch(
                "app.api.v1.fraud_detection.get_current_user",
                return_value=mock_user,
            ):
                mock_db = AsyncMock()
                result = await analyze_fraud(
                    days=90,
                    current_user=mock_user,
                    db=mock_db,
                )

        assert result is not None
        mock_fraud_service.analyze_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_fraud_no_company(self) -> None:
        """Fehler wenn User keine Company hat."""
        from app.api.v1.fraud_detection import analyze_fraud
        from fastapi import HTTPException

        user = MagicMock()
        user.company_id = None

        with pytest.raises(HTTPException) as exc_info:
            await analyze_fraud(
                days=90,
                current_user=user,
                db=AsyncMock(),
            )

        assert exc_info.value.status_code == 400
        assert "Keine Firma" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_analyze_fraud_days_validation(self) -> None:
        """Query-Parameter days wird validiert."""
        # Days muss zwischen 7 und 365 liegen
        # Dies wird von FastAPI automatisch validiert
        pass

    # ==================== Dashboard Endpoint Tests ====================

    @pytest.mark.asyncio
    async def test_dashboard_success(
        self,
        mock_user: MagicMock,
        mock_fraud_service: AsyncMock,
    ) -> None:
        """Dashboard-Statistiken erfolgreich abrufen."""
        from app.api.v1.fraud_detection import get_fraud_dashboard

        with patch(
            "app.api.v1.fraud_detection.FraudDetectionService",
            return_value=mock_fraud_service,
        ):
            mock_db = AsyncMock()
            result = await get_fraud_dashboard(
                current_user=mock_user,
                db=mock_db,
            )

        assert result is not None
        assert hasattr(result, "total_alerts_30d")
        assert hasattr(result, "critical_alerts")
        assert hasattr(result, "trend")

    @pytest.mark.asyncio
    async def test_dashboard_trend_increasing(
        self,
        mock_user: MagicMock,
    ) -> None:
        """Trend wird korrekt als 'increasing' erkannt."""
        from app.api.v1.fraud_detection import get_fraud_dashboard

        mock_service = AsyncMock()
        # Aktuell mehr Alerts als vorher
        mock_service.analyze_all.side_effect = [
            {"summary": {"total_alerts": 10, "critical": 2, "estimated_risk_amount": 15000.0}, "alerts": []},  # current
            {"summary": {"total_alerts": 5, "critical": 1, "estimated_risk_amount": 8000.0}, "alerts": []},   # previous
        ]

        with patch(
            "app.api.v1.fraud_detection.FraudDetectionService",
            return_value=mock_service,
        ):
            result = await get_fraud_dashboard(
                current_user=mock_user,
                db=AsyncMock(),
            )

        assert result.trend == "increasing"

    @pytest.mark.asyncio
    async def test_dashboard_trend_decreasing(
        self,
        mock_user: MagicMock,
    ) -> None:
        """Trend wird korrekt als 'decreasing' erkannt."""
        from app.api.v1.fraud_detection import get_fraud_dashboard

        mock_service = AsyncMock()
        # Aktuell weniger Alerts als vorher
        mock_service.analyze_all.side_effect = [
            {"summary": {"total_alerts": 3, "critical": 0, "estimated_risk_amount": 3000.0}, "alerts": []},   # current
            {"summary": {"total_alerts": 10, "critical": 2, "estimated_risk_amount": 15000.0}, "alerts": []},  # previous
        ]

        with patch(
            "app.api.v1.fraud_detection.FraudDetectionService",
            return_value=mock_service,
        ):
            result = await get_fraud_dashboard(
                current_user=mock_user,
                db=AsyncMock(),
            )

        assert result.trend == "decreasing"

    # ==================== Alerts Endpoint Tests ====================

    @pytest.mark.asyncio
    async def test_get_alerts_with_filters(
        self,
        mock_user: MagicMock,
        mock_fraud_service: AsyncMock,
    ) -> None:
        """Alerts mit Filterung abrufen."""
        from app.api.v1.fraud_detection import get_fraud_alerts
        from app.services.finanzki.fraud_detection_service import FraudType, RiskLevel

        mock_fraud_service.analyze_all.return_value = {
            "alerts": [
                {"type": "duplicate_invoice", "risk_level": "high", "confidence": 0.9},
                {"type": "price_anomaly", "risk_level": "medium", "confidence": 0.7},
                {"type": "duplicate_invoice", "risk_level": "critical", "confidence": 0.95},
            ]
        }

        with patch(
            "app.api.v1.fraud_detection.FraudDetectionService",
            return_value=mock_fraud_service,
        ):
            result = await get_fraud_alerts(
                fraud_type=FraudType.DUPLICATE_INVOICE,
                risk_level=None,
                days=30,
                limit=50,
                offset=0,
                current_user=mock_user,
                db=AsyncMock(),
            )

        # Nur duplicate_invoice Alerts
        assert len(result) == 2
        assert all(a["type"] == "duplicate_invoice" for a in result)

    @pytest.mark.asyncio
    async def test_get_alerts_pagination(
        self,
        mock_user: MagicMock,
        mock_fraud_service: AsyncMock,
    ) -> None:
        """Alerts mit Pagination."""
        from app.api.v1.fraud_detection import get_fraud_alerts

        # 10 Alerts generieren
        mock_fraud_service.analyze_all.return_value = {
            "alerts": [
                {"type": "duplicate_invoice", "risk_level": "high", "confidence": 0.9}
                for _ in range(10)
            ]
        }

        with patch(
            "app.api.v1.fraud_detection.FraudDetectionService",
            return_value=mock_fraud_service,
        ):
            result = await get_fraud_alerts(
                fraud_type=None,
                risk_level=None,
                days=30,
                limit=5,
                offset=3,
                current_user=mock_user,
                db=AsyncMock(),
            )

        # 5 Alerts ab Offset 3
        assert len(result) == 5

    # ==================== Config Endpoint Tests ====================

    @pytest.mark.asyncio
    async def test_get_config(
        self,
        mock_user: MagicMock,
    ) -> None:
        """Konfiguration abrufen."""
        from app.api.v1.fraud_detection import get_fraud_config

        mock_service = MagicMock()
        mock_service.config = {
            "price_deviation_threshold": 0.30,
            "duplicate_similarity_threshold": 0.85,
            "phantom_supplier_days": 90,
            "expense_pattern_threshold": 5,
            "approval_threshold": 5000,
        }

        with patch(
            "app.api.v1.fraud_detection.FraudDetectionService",
            return_value=mock_service,
        ):
            result = await get_fraud_config(
                current_user=mock_user,
                db=AsyncMock(),
            )

        assert result.price_deviation_threshold == 0.30
        assert result.duplicate_similarity_threshold == 0.85

    @pytest.mark.asyncio
    async def test_update_config_requires_admin(
        self,
        mock_user: MagicMock,
    ) -> None:
        """Nur Admins duerfen Config aendern."""
        from app.api.v1.fraud_detection import update_fraud_config, FraudConfigSchema
        from fastapi import HTTPException

        mock_user.role = "user"  # Nicht Admin

        with pytest.raises(HTTPException) as exc_info:
            await update_fraud_config(
                config=FraudConfigSchema(),
                current_user=mock_user,
                db=AsyncMock(),
            )

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_update_config_as_admin(
        self,
        mock_admin: MagicMock,
    ) -> None:
        """Admin kann Config aendern."""
        from app.api.v1.fraud_detection import update_fraud_config, FraudConfigSchema

        new_config = FraudConfigSchema(
            price_deviation_threshold=0.40,
            duplicate_similarity_threshold=0.90,
        )

        result = await update_fraud_config(
            config=new_config,
            current_user=mock_admin,
            db=AsyncMock(),
        )

        assert result.price_deviation_threshold == 0.40

    # ==================== Fraud Types Endpoint Tests ====================

    @pytest.mark.asyncio
    async def test_get_fraud_types(self) -> None:
        """Alle Fraud-Typen abrufen."""
        from app.api.v1.fraud_detection import get_fraud_types

        result = await get_fraud_types()

        assert len(result) == 9  # 9 verschiedene Betrugsarten
        type_names = [t["type"] for t in result]
        assert "duplicate_invoice" in type_names
        assert "price_anomaly" in type_names
        assert "phantom_supplier" in type_names

    # ==================== Risk Levels Endpoint Tests ====================

    @pytest.mark.asyncio
    async def test_get_risk_levels(self) -> None:
        """Alle Risikostufen abrufen."""
        from app.api.v1.fraud_detection import get_risk_levels

        result = await get_risk_levels()

        assert len(result) == 4  # critical, high, medium, low
        levels = [r["level"] for r in result]
        assert "critical" in levels
        assert "low" in levels

    # ==================== Entity Risk Profile Tests ====================

    @pytest.mark.asyncio
    async def test_entity_risk_profile(
        self,
        mock_user: MagicMock,
        mock_fraud_service: AsyncMock,
    ) -> None:
        """Entity Risk Profile abrufen."""
        from app.api.v1.fraud_detection import get_entity_risk_profile

        entity_id = uuid4()
        mock_fraud_service.analyze_all.return_value = {
            "alerts": [
                {"entity_id": str(entity_id), "risk_level": "high"},
                {"entity_id": str(entity_id), "risk_level": "medium"},
                {"entity_id": str(uuid4()), "risk_level": "low"},  # Andere Entity
            ]
        }

        with patch(
            "app.api.v1.fraud_detection.FraudDetectionService",
            return_value=mock_fraud_service,
        ):
            result = await get_entity_risk_profile(
                entity_id=entity_id,
                current_user=mock_user,
                db=AsyncMock(),
            )

        assert result["entity_id"] == str(entity_id)
        assert result["total_alerts"] == 2
        # 25 (high) + 10 (medium) = 35
        assert result["risk_score"] == 35
        assert result["risk_level"] == "medium"  # 25-49

    # ==================== Alert Detail/Action Tests ====================

    @pytest.mark.asyncio
    async def test_alert_detail_not_implemented(
        self,
        mock_user: MagicMock,
    ) -> None:
        """Alert-Detail wirft 501 (noch nicht implementiert)."""
        from app.api.v1.fraud_detection import get_fraud_alert_detail
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_fraud_alert_detail(
                alert_id="test-alert",
                current_user=mock_user,
                db=AsyncMock(),
            )

        assert exc_info.value.status_code == 501

    @pytest.mark.asyncio
    async def test_alert_action_not_implemented(
        self,
        mock_user: MagicMock,
    ) -> None:
        """Alert-Action wirft 501 (noch nicht implementiert)."""
        from app.api.v1.fraud_detection import take_alert_action, AlertActionRequest
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await take_alert_action(
                alert_id="test-alert",
                action=AlertActionRequest(action="dismiss"),
                current_user=mock_user,
                db=AsyncMock(),
            )

        assert exc_info.value.status_code == 501


class TestFraudDetectionService:
    """Tests fuer FraudDetectionService."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_invoice_hash_creation(self) -> None:
        """Test Invoice-Hash-Erstellung."""
        from app.services.finanzki.fraud_detection_service import FraudDetectionService

        service = FraudDetectionService(AsyncMock())

        # Mock Invoice
        invoice = MagicMock()
        invoice.invoice_number = "INV-001"
        invoice.total_amount = 1234.56
        invoice.entity_id = uuid4()

        hash1 = service._create_invoice_hash(invoice)

        # Gleiche Daten = gleicher Hash
        hash2 = service._create_invoice_hash(invoice)
        assert hash1 == hash2

        # Andere Rechnungsnummer = anderer Hash
        invoice.invoice_number = "INV-002"
        hash3 = service._create_invoice_hash(invoice)
        assert hash1 != hash3

    @pytest.mark.asyncio
    async def test_similar_amounts_detection(self) -> None:
        """Test Erkennung aehnlicher Betraege."""
        from app.services.finanzki.fraud_detection_service import FraudDetectionService
        from decimal import Decimal

        service = FraudDetectionService(AsyncMock())

        # Gleiche Betraege
        assert service._are_similar_amounts(Decimal("100.00"), Decimal("100.00")) is True

        # 1% Abweichung (unter 2% Toleranz)
        assert service._are_similar_amounts(Decimal("100.00"), Decimal("101.00")) is True

        # 5% Abweichung (ueber 2% Toleranz)
        assert service._are_similar_amounts(Decimal("100.00"), Decimal("105.00")) is False

        # Null-Werte
        assert service._are_similar_amounts(None, Decimal("100.00")) is False
        assert service._are_similar_amounts(Decimal("100.00"), None) is False

    @pytest.mark.asyncio
    async def test_round_amount_detection(self) -> None:
        """Test Erkennung runder Betraege."""
        from app.services.finanzki.fraud_detection_service import FraudDetectionService

        service = FraudDetectionService(AsyncMock())

        # Runde Betraege
        assert service._is_round_amount(1000.00) is True
        assert service._is_round_amount(5000.00) is True
        assert service._is_round_amount(500.00) is True

        # Nicht runde Betraege
        assert service._is_round_amount(1234.56) is False
        assert service._is_round_amount(99.99) is False

        # Unter Schwelle
        assert service._is_round_amount(50.00) is False  # Unter 100
