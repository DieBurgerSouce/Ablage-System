# -*- coding: utf-8 -*-
"""
Tests für A/B Testing Metrics API Endpoints.

Testet:
- GET /api/v1/metrics/ab-testing
- POST /api/v1/metrics/ab-testing/traffic-split
- POST /api/v1/metrics/ab-testing/reset-metrics

WICHTIG: API Response Keys sind auf Deutsch (German Language First).
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4
import httpx

from fastapi import HTTPException


# ==================== A/B Testing Metrics Tests ====================


class TestABTestingMetrics:
    """Tests für GET /metrics/ab-testing."""

    @pytest.mark.asyncio
    async def test_ab_testing_metrics_returns_dict(self):
        """A/B Testing Metrics gibt Dict mit deutschen Keys zurück."""
        from app.api.v1.metrics import get_ab_testing_metrics

        mock_router = Mock()
        mock_router.get_status.return_value = {
            "enabled": True,
            "traffic_split": 10,
            "control": {"backend": "pgvector", "embedding_model": "e5"},
            "treatment": {"backend": "qdrant", "embedding_model": "e5"},
            "metrics": {
                "control": {"total_requests": 100, "avg_latency_ms": 45.0, "errors": 0},
                "treatment": {"total_requests": 10, "avg_latency_ms": 28.0, "errors": 0}
            }
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "points_count": 674,
                "vectors_count": 674,
                "status": "green",
                "config": {"params": {"vectors": {"size": 1024, "distance": "Cosine"}}}
            }
        }

        with patch('app.api.v1.metrics.get_ab_testing_router', return_value=mock_router), \
             patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

            result = await get_ab_testing_metrics()

            # Deutsche Keys prüfen
            assert isinstance(result, dict)
            assert "zeitstempel" in result
            assert "konfiguration" in result
            assert "metriken" in result
            assert "qdrant_status" in result
            assert "empfehlungen" in result

    @pytest.mark.asyncio
    async def test_ab_testing_metrics_configuration(self):
        """A/B Testing Metrics enthalten korrekte deutsche Konfiguration."""
        from app.api.v1.metrics import get_ab_testing_metrics

        mock_router = Mock()
        mock_router.get_status.return_value = {
            "enabled": True,
            "traffic_split": 25,
            "control": {"backend": "pgvector", "embedding_model": "e5"},
            "treatment": {"backend": "qdrant", "embedding_model": "e5"},
            "metrics": {}
        }

        with patch('app.api.v1.metrics.get_ab_testing_router', return_value=mock_router), \
             patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=MagicMock(status_code=404)
            )

            result = await get_ab_testing_metrics()

            # Deutsche Keys in Konfiguration
            assert result["konfiguration"]["aktiviert"] is True
            assert result["konfiguration"]["traffic_split_prozent"] == 25
            assert "kontrolle" in result["konfiguration"]
            assert "behandlung" in result["konfiguration"]

    @pytest.mark.asyncio
    async def test_ab_testing_metrics_handles_router_error(self):
        """A/B Testing Metrics behandelt Router-Fehler mit deutschem Fehlertext."""
        from app.api.v1.metrics import get_ab_testing_metrics

        with patch('app.api.v1.metrics.get_ab_testing_router') as mock_get_router, \
             patch('httpx.AsyncClient') as mock_client:
            mock_get_router.side_effect = Exception("Router nicht initialisiert")
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=MagicMock(status_code=404)
            )

            result = await get_ab_testing_metrics()

            # Deutscher Fehler-Key
            assert "fehler" in result["konfiguration"]

    @pytest.mark.asyncio
    async def test_ab_testing_metrics_handles_qdrant_timeout(self):
        """A/B Testing Metrics behandelt Qdrant-Timeout graceful."""
        from app.api.v1.metrics import get_ab_testing_metrics

        mock_router = Mock()
        mock_router.get_status.return_value = {
            "enabled": True,
            "traffic_split": 10,
            "control": {},
            "treatment": {},
            "metrics": {}
        }

        with patch('app.api.v1.metrics.get_ab_testing_router', return_value=mock_router), \
             patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.TimeoutException("Timeout")
            )

            result = await get_ab_testing_metrics()

            # Deutsche Fehler-Keys
            assert result["qdrant_status"]["verfuegbar"] is False
            assert "Timeout" in result["qdrant_status"]["fehler"]

    @pytest.mark.asyncio
    async def test_ab_testing_metrics_handles_qdrant_connection_error(self):
        """A/B Testing Metrics behandelt Qdrant-Connection-Error graceful."""
        from app.api.v1.metrics import get_ab_testing_metrics

        mock_router = Mock()
        mock_router.get_status.return_value = {
            "enabled": True,
            "traffic_split": 10,
            "control": {},
            "treatment": {},
            "metrics": {}
        }

        with patch('app.api.v1.metrics.get_ab_testing_router', return_value=mock_router), \
             patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )

            result = await get_ab_testing_metrics()

            assert result["qdrant_status"]["verfuegbar"] is False
            assert "Verbindung" in result["qdrant_status"]["fehler"]

    @pytest.mark.asyncio
    async def test_ab_testing_metrics_qdrant_success(self):
        """A/B Testing Metrics zeigt Qdrant-Status korrekt an."""
        from app.api.v1.metrics import get_ab_testing_metrics

        mock_router = Mock()
        mock_router.get_status.return_value = {
            "enabled": True,
            "traffic_split": 10,
            "control": {},
            "treatment": {},
            "metrics": {"control": {"total_requests": 50}, "treatment": {"total_requests": 5}}
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "points_count": 674,
                "vectors_count": 674,
                "status": "green",
                "config": {"params": {"vectors": {"size": 1024, "distance": "Cosine"}}}
            }
        }

        with patch('app.api.v1.metrics.get_ab_testing_router', return_value=mock_router), \
             patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

            result = await get_ab_testing_metrics()

            # Deutsche Qdrant Status Keys
            assert result["qdrant_status"]["verfuegbar"] is True
            assert result["qdrant_status"]["punkte_anzahl"] == 674
            assert result["qdrant_status"]["vektoren_anzahl"] == 674


class TestABTestingTrafficSplit:
    """Tests für POST /metrics/ab-testing/traffic-split."""

    @pytest.mark.asyncio
    async def test_traffic_split_valid_value(self):
        """Traffic Split mit gültigem Wert (0-100) funktioniert."""
        from app.api.v1.metrics import update_ab_testing_traffic_split

        mock_router = Mock()
        mock_router._traffic_split = 10

        mock_user = Mock()
        mock_user.id = uuid4()
        mock_user.email = "admin@test.de"

        with patch('app.api.v1.metrics.get_ab_testing_router', return_value=mock_router):
            result = await update_ab_testing_traffic_split(25, mock_user)

            assert result["status"] == "erfolg"
            assert result["alter_split"] == 10
            assert result["neuer_split"] == 25
            mock_router.update_traffic_split.assert_called_once_with(25)

    @pytest.mark.asyncio
    async def test_traffic_split_invalid_negative(self):
        """Traffic Split mit negativem Wert wird abgelehnt."""
        from app.api.v1.metrics import update_ab_testing_traffic_split

        mock_user = Mock()
        mock_user.id = uuid4()

        with pytest.raises(HTTPException) as exc_info:
            await update_ab_testing_traffic_split(-5, mock_user)

        assert exc_info.value.status_code == 400
        assert "zwischen 0 und 100" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_traffic_split_invalid_over_100(self):
        """Traffic Split über 100 wird abgelehnt."""
        from app.api.v1.metrics import update_ab_testing_traffic_split

        mock_user = Mock()
        mock_user.id = uuid4()

        with pytest.raises(HTTPException) as exc_info:
            await update_ab_testing_traffic_split(150, mock_user)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_traffic_split_edge_cases(self):
        """Traffic Split mit Randwerten (0 und 100) funktioniert."""
        from app.api.v1.metrics import update_ab_testing_traffic_split

        mock_router = Mock()
        mock_router._traffic_split = 50

        mock_user = Mock()
        mock_user.id = uuid4()
        mock_user.email = "admin@test.de"

        with patch('app.api.v1.metrics.get_ab_testing_router', return_value=mock_router):
            # Test 0%
            result = await update_ab_testing_traffic_split(0, mock_user)
            assert result["neuer_split"] == 0

            # Test 100%
            result = await update_ab_testing_traffic_split(100, mock_user)
            assert result["neuer_split"] == 100


class TestABTestingResetMetrics:
    """Tests für POST /metrics/ab-testing/reset-metrics."""

    @pytest.mark.asyncio
    async def test_reset_metrics_success(self):
        """Reset Metrics funktioniert und gibt Bestätigung zurück."""
        from app.api.v1.metrics import reset_ab_testing_metrics

        mock_router = Mock()

        mock_user = Mock()
        mock_user.id = uuid4()
        mock_user.email = "admin@test.de"

        with patch('app.api.v1.metrics.get_ab_testing_router', return_value=mock_router):
            result = await reset_ab_testing_metrics(mock_user)

            assert result["status"] == "erfolg"
            assert "zurueckgesetzt" in result["nachricht"]
            mock_router.reset_metrics.assert_called_once()

    @pytest.mark.asyncio
    async def test_reset_metrics_includes_user_id(self):
        """Reset Metrics enthält User-ID für Audit."""
        from app.api.v1.metrics import reset_ab_testing_metrics

        mock_router = Mock()

        mock_user = Mock()
        test_user_id = uuid4()
        mock_user.id = test_user_id
        mock_user.email = "admin@test.de"

        with patch('app.api.v1.metrics.get_ab_testing_router', return_value=mock_router):
            result = await reset_ab_testing_metrics(mock_user)

            assert "durchgeführt_von" in result
            assert str(test_user_id) in result["durchgeführt_von"]


class TestABTestingRecommendations:
    """Tests für A/B Testing Empfehlungen (deutsche Keys)."""

    @pytest.mark.asyncio
    async def test_recommendation_no_requests_yet(self):
        """Empfehlung wenn noch keine Requests gesammelt."""
        from app.api.v1.metrics import get_ab_testing_metrics

        mock_router = Mock()
        mock_router.get_status.return_value = {
            "enabled": True,
            "traffic_split": 10,
            "control": {},
            "treatment": {},
            "metrics": {
                "control": {"total_requests": 0},
                "treatment": {"total_requests": 0}
            }
        }

        with patch('app.api.v1.metrics.get_ab_testing_router', return_value=mock_router), \
             patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=MagicMock(status_code=200, json=lambda: {"result": {"points_count": 674}})
            )

            result = await get_ab_testing_metrics()

            # Deutsche Keys in Empfehlungen
            empfehlungen = result["empfehlungen"]
            assert any("noch keine Anfragen" in r["nachricht"] for r in empfehlungen)
            assert all("typ" in r for r in empfehlungen)

    @pytest.mark.asyncio
    async def test_recommendation_empty_qdrant_collection(self):
        """Kritische Empfehlung wenn Qdrant Collection leer."""
        from app.api.v1.metrics import get_ab_testing_metrics

        mock_router = Mock()
        mock_router.get_status.return_value = {
            "enabled": True,
            "traffic_split": 10,
            "control": {},
            "treatment": {},
            "metrics": {}
        }

        with patch('app.api.v1.metrics.get_ab_testing_router', return_value=mock_router), \
             patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=MagicMock(
                    status_code=200,
                    json=lambda: {"result": {"points_count": 0, "status": "green"}}
                )
            )

            result = await get_ab_testing_metrics()

            # Deutsche Keys - "kritisch" statt "critical"
            empfehlungen = result["empfehlungen"]
            assert any(r["typ"] == "kritisch" for r in empfehlungen)
            assert any("Collection ist leer" in r["nachricht"] for r in empfehlungen)

    @pytest.mark.asyncio
    async def test_recommendation_qdrant_faster(self):
        """Erfolgs-Empfehlung wenn Qdrant schneller ist."""
        from app.api.v1.metrics import get_ab_testing_metrics

        mock_router = Mock()
        mock_router.get_status.return_value = {
            "enabled": True,
            "traffic_split": 10,
            "control": {},
            "treatment": {},
            "metrics": {
                "control": {"total_requests": 100, "avg_latency_ms": 100.0, "error_rate": 0},
                "treatment": {"total_requests": 50, "avg_latency_ms": 50.0, "error_rate": 0}
            }
        }

        with patch('app.api.v1.metrics.get_ab_testing_router', return_value=mock_router), \
             patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=MagicMock(status_code=200, json=lambda: {"result": {"points_count": 674}})
            )

            result = await get_ab_testing_metrics()

            # "erfolg" statt "success"
            empfehlungen = result["empfehlungen"]
            assert any(r["typ"] == "erfolg" for r in empfehlungen)
            assert any("schneller" in r["nachricht"] for r in empfehlungen)


class TestABTestingConcurrency:
    """Tests für Thread-Safety und Concurrent Access."""

    @pytest.mark.asyncio
    async def test_concurrent_traffic_split_updates(self):
        """Mehrere Traffic Split Updates gleichzeitig."""
        from app.api.v1.metrics import update_ab_testing_traffic_split
        import asyncio

        mock_router = Mock()
        mock_router._traffic_split = 10

        mock_user = Mock()
        mock_user.id = uuid4()
        mock_user.email = "admin@test.de"

        with patch('app.api.v1.metrics.get_ab_testing_router', return_value=mock_router):
            # Mehrere Updates parallel
            tasks = [
                update_ab_testing_traffic_split(20, mock_user),
                update_ab_testing_traffic_split(30, mock_user),
                update_ab_testing_traffic_split(40, mock_user),
            ]

            results = await asyncio.gather(*tasks)

            # Alle sollten erfolgreich sein
            assert all(r["status"] == "erfolg" for r in results)
            # update_traffic_split sollte 3x aufgerufen worden sein
            assert mock_router.update_traffic_split.call_count == 3
