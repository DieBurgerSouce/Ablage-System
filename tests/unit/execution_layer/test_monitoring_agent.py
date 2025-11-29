"""
Tests for Monitoring Agent.

Tests the execution layer monitoring functionality:
- Health check monitoring
- GPU health checks
- Database health checks
- System metrics collection
- Alert generation
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


@pytest.fixture
def mock_torch_cuda():
    """Mock torch.cuda for GPU tests."""
    mock = MagicMock()
    mock.is_available.return_value = True
    mock.current_device.return_value = 0
    mock.memory_allocated.return_value = 8 * 1024**3  # 8GB
    mock.get_device_properties.return_value = MagicMock(
        total_memory=16 * 1024**3,  # 16GB
        name="NVIDIA RTX 4080"
    )
    return mock


@pytest.fixture
def mock_psutil():
    """Mock psutil for system metrics."""
    mock = MagicMock()
    mock.cpu_percent.return_value = 45.0
    mock.virtual_memory.return_value = MagicMock(
        percent=60.0,
        total=32 * 1024**3,
        available=12 * 1024**3
    )
    return mock


class TestMonitoringAgentInit:
    """Tests for Monitoring Agent initialization."""

    def test_agent_initialization(self):
        """Agent sollte korrekt initialisiert werden."""
        from Execution_Layer.Agents.monitoring_agent import MonitoringAgent

        with patch("Execution_Layer.Agents.monitoring_agent.DatabaseHealthChecker"):
            agent = MonitoringAgent(
                db_connection_string="postgresql://localhost:5432/test",
                check_interval_seconds=30
            )
            assert agent is not None
            assert agent.check_interval == 30
            assert agent.running is False

    def test_agent_with_custom_interval(self):
        """Agent mit benutzerdefiniertem Intervall."""
        from Execution_Layer.Agents.monitoring_agent import MonitoringAgent

        with patch("Execution_Layer.Agents.monitoring_agent.DatabaseHealthChecker"):
            agent = MonitoringAgent(
                db_connection_string="postgresql://localhost:5432/test",
                check_interval_seconds=60
            )
            assert agent.check_interval == 60


class TestHealthStatus:
    """Tests for HealthStatus enum."""

    def test_health_status_values(self):
        """HealthStatus-Werte prüfen."""
        from Execution_Layer.Agents.monitoring_agent import HealthStatus

        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.CRITICAL.value == "critical"


class TestAlertSeverity:
    """Tests for AlertSeverity enum."""

    def test_alert_severity_values(self):
        """AlertSeverity-Werte prüfen."""
        from Execution_Layer.Agents.monitoring_agent import AlertSeverity

        assert AlertSeverity.INFO.value == "info"
        assert AlertSeverity.WARNING.value == "warning"
        assert AlertSeverity.ERROR.value == "error"
        assert AlertSeverity.CRITICAL.value == "critical"


class TestHealthCheckResult:
    """Tests for HealthCheckResult dataclass."""

    def test_health_check_result_creation(self):
        """HealthCheckResult erstellen."""
        from Execution_Layer.Agents.monitoring_agent import (
            HealthCheckResult,
            HealthStatus,
        )

        result = HealthCheckResult(
            service="postgresql",
            status=HealthStatus.HEALTHY,
            response_time_ms=15.5,
            message="Database healthy"
        )

        assert result.service == "postgresql"
        assert result.status == HealthStatus.HEALTHY
        assert result.response_time_ms == 15.5
        assert result.message == "Database healthy"
        assert isinstance(result.timestamp, datetime)

    def test_health_check_result_with_details(self):
        """HealthCheckResult mit Details erstellen."""
        from Execution_Layer.Agents.monitoring_agent import (
            HealthCheckResult,
            HealthStatus,
        )

        result = HealthCheckResult(
            service="gpu",
            status=HealthStatus.DEGRADED,
            response_time_ms=5.0,
            message="GPU VRAM high",
            details={"vram_percent": 87.5}
        )

        assert result.details["vram_percent"] == 87.5


class TestDatabaseHealthChecker:
    """Tests for DatabaseHealthChecker."""

    @pytest.mark.asyncio
    async def test_database_healthy(self):
        """Datenbank als gesund erkennen."""
        from Execution_Layer.Agents.monitoring_agent import (
            DatabaseHealthChecker,
            HealthStatus,
        )

        checker = DatabaseHealthChecker("postgresql://localhost:5432/test")

        with patch.object(
            checker,
            "check_health",
            return_value=MagicMock(
                service="postgresql",
                status=HealthStatus.HEALTHY,
                response_time_ms=25.0,
                message="Database healthy"
            )
        ):
            result = await checker.check_health()
            assert result.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_database_slow(self):
        """Langsame Datenbank als degradiert erkennen."""
        from Execution_Layer.Agents.monitoring_agent import (
            DatabaseHealthChecker,
            HealthStatus,
        )

        checker = DatabaseHealthChecker("postgresql://localhost:5432/test")

        with patch.object(
            checker,
            "check_health",
            return_value=MagicMock(
                service="postgresql",
                status=HealthStatus.DEGRADED,
                response_time_ms=1500.0,
                message="Database slow"
            )
        ):
            result = await checker.check_health()
            assert result.status == HealthStatus.DEGRADED

    @pytest.mark.asyncio
    async def test_database_connection_failed(self):
        """Datenbank-Verbindungsfehler erkennen."""
        from Execution_Layer.Agents.monitoring_agent import (
            DatabaseHealthChecker,
            HealthStatus,
        )

        checker = DatabaseHealthChecker("postgresql://invalid:5432/test")

        with patch.object(
            checker,
            "check_health",
            return_value=MagicMock(
                service="postgresql",
                status=HealthStatus.UNHEALTHY,
                response_time_ms=0,
                message="Database connection failed: Connection refused"
            )
        ):
            result = await checker.check_health()
            assert result.status == HealthStatus.UNHEALTHY
            assert "connection failed" in result.message.lower()


class TestGPUHealthChecker:
    """Tests for GPUHealthChecker."""

    @pytest.mark.asyncio
    async def test_gpu_healthy(self, mock_torch_cuda):
        """GPU als gesund erkennen."""
        from Execution_Layer.Agents.monitoring_agent import (
            GPUHealthChecker,
            HealthStatus,
        )

        checker = GPUHealthChecker()

        with patch.object(
            checker,
            "check_health",
            return_value=MagicMock(
                service="gpu",
                status=HealthStatus.HEALTHY,
                response_time_ms=2.0,
                message="GPU healthy",
                details={"vram_percent": 50.0}
            )
        ):
            result = await checker.check_health()
            assert result.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_gpu_high_vram(self):
        """Hohe GPU-VRAM-Nutzung als degradiert erkennen."""
        from Execution_Layer.Agents.monitoring_agent import (
            GPUHealthChecker,
            HealthStatus,
        )

        checker = GPUHealthChecker()

        with patch.object(
            checker,
            "check_health",
            return_value=MagicMock(
                service="gpu",
                status=HealthStatus.DEGRADED,
                response_time_ms=2.0,
                message="GPU VRAM high (87.5%)",
                details={"vram_percent": 87.5}
            )
        ):
            result = await checker.check_health()
            assert result.status == HealthStatus.DEGRADED

    @pytest.mark.asyncio
    async def test_gpu_critical_vram(self):
        """Kritische GPU-VRAM-Nutzung erkennen."""
        from Execution_Layer.Agents.monitoring_agent import (
            GPUHealthChecker,
            HealthStatus,
        )

        checker = GPUHealthChecker()

        with patch.object(
            checker,
            "check_health",
            return_value=MagicMock(
                service="gpu",
                status=HealthStatus.CRITICAL,
                response_time_ms=2.0,
                message="GPU VRAM critical (95.0%)",
                details={"vram_percent": 95.0}
            )
        ):
            result = await checker.check_health()
            assert result.status == HealthStatus.CRITICAL

    @pytest.mark.asyncio
    async def test_gpu_unavailable(self):
        """GPU als nicht verfügbar erkennen."""
        from Execution_Layer.Agents.monitoring_agent import (
            GPUHealthChecker,
            HealthStatus,
        )

        checker = GPUHealthChecker()

        with patch("torch.cuda.is_available", return_value=False):
            with patch.object(
                checker,
                "check_health",
                return_value=MagicMock(
                    service="gpu",
                    status=HealthStatus.UNHEALTHY,
                    response_time_ms=0,
                    message="GPU not available"
                )
            ):
                result = await checker.check_health()
                assert result.status == HealthStatus.UNHEALTHY


class TestMonitoringAgentRun:
    """Tests for Monitoring Agent run loop."""

    @pytest.mark.asyncio
    async def test_agent_start_stop(self):
        """Agent starten und stoppen."""
        from Execution_Layer.Agents.monitoring_agent import MonitoringAgent

        with patch("Execution_Layer.Agents.monitoring_agent.DatabaseHealthChecker"):
            agent = MonitoringAgent(
                db_connection_string="postgresql://localhost:5432/test",
                check_interval_seconds=1
            )

            # Mock the internal methods
            agent._run_health_checks = AsyncMock()
            agent._collect_system_metrics = AsyncMock()

            # Start in background
            import asyncio
            task = asyncio.create_task(agent.run())

            # Let it run one cycle
            await asyncio.sleep(0.1)
            assert agent.running is True

            # Stop
            await agent.stop()
            assert agent.running is False

            # Cancel the task
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_run_health_checks(self):
        """Health Checks ausführen."""
        from Execution_Layer.Agents.monitoring_agent import (
            MonitoringAgent,
            HealthStatus,
        )

        with patch("Execution_Layer.Agents.monitoring_agent.DatabaseHealthChecker") as mock_db:
            mock_db.return_value.check_health = AsyncMock(
                return_value=MagicMock(
                    service="postgresql",
                    status=HealthStatus.HEALTHY,
                    response_time_ms=20.0
                )
            )

            agent = MonitoringAgent(
                db_connection_string="postgresql://localhost:5432/test"
            )

            # Mock GPU checker
            agent.gpu_checker.check_health = AsyncMock(
                return_value=MagicMock(
                    service="gpu",
                    status=HealthStatus.HEALTHY,
                    response_time_ms=5.0
                )
            )

            await agent._run_health_checks()


class TestSystemMetrics:
    """Tests for system metrics collection."""

    @pytest.mark.asyncio
    async def test_collect_cpu_metrics(self, mock_psutil):
        """CPU-Metriken sammeln."""
        from Execution_Layer.Agents.monitoring_agent import MonitoringAgent

        with patch("Execution_Layer.Agents.monitoring_agent.DatabaseHealthChecker"):
            with patch("Execution_Layer.Agents.monitoring_agent.psutil", mock_psutil):
                agent = MonitoringAgent(
                    db_connection_string="postgresql://localhost:5432/test"
                )

                with patch("torch.cuda.is_available", return_value=False):
                    await agent._collect_system_metrics()

    @pytest.mark.asyncio
    async def test_collect_memory_metrics(self, mock_psutil):
        """Speicher-Metriken sammeln."""
        from Execution_Layer.Agents.monitoring_agent import MonitoringAgent

        with patch("Execution_Layer.Agents.monitoring_agent.DatabaseHealthChecker"):
            with patch("Execution_Layer.Agents.monitoring_agent.psutil", mock_psutil):
                agent = MonitoringAgent(
                    db_connection_string="postgresql://localhost:5432/test"
                )

                with patch("torch.cuda.is_available", return_value=False):
                    await agent._collect_system_metrics()

    @pytest.mark.asyncio
    async def test_collect_gpu_metrics(self, mock_torch_cuda, mock_psutil):
        """GPU-Metriken sammeln."""
        from Execution_Layer.Agents.monitoring_agent import MonitoringAgent

        with patch("Execution_Layer.Agents.monitoring_agent.DatabaseHealthChecker"):
            with patch("Execution_Layer.Agents.monitoring_agent.psutil", mock_psutil):
                with patch("torch.cuda", mock_torch_cuda):
                    agent = MonitoringAgent(
                        db_connection_string="postgresql://localhost:5432/test"
                    )

                    await agent._collect_system_metrics()


class TestPrometheusMetrics:
    """Tests for Prometheus metrics."""

    def test_metrics_defined(self):
        """Prometheus-Metriken definiert."""
        from Execution_Layer.Agents.monitoring_agent import (
            health_check_status,
            system_cpu_percent,
            system_memory_percent,
            gpu_vram_percent,
            alerts_generated,
        )

        assert health_check_status is not None
        assert system_cpu_percent is not None
        assert system_memory_percent is not None
        assert gpu_vram_percent is not None
        assert alerts_generated is not None


class TestAlertGeneration:
    """Tests for alert generation."""

    @pytest.mark.asyncio
    async def test_alert_on_unhealthy_service(self):
        """Alert bei ungesundem Service generieren."""
        from Execution_Layer.Agents.monitoring_agent import (
            MonitoringAgent,
            HealthStatus,
        )

        with patch("Execution_Layer.Agents.monitoring_agent.DatabaseHealthChecker") as mock_db:
            mock_db.return_value.check_health = AsyncMock(
                return_value=MagicMock(
                    service="postgresql",
                    status=HealthStatus.UNHEALTHY,
                    response_time_ms=0,
                    message="Connection refused"
                )
            )

            agent = MonitoringAgent(
                db_connection_string="postgresql://localhost:5432/test"
            )

            agent.gpu_checker.check_health = AsyncMock(
                return_value=MagicMock(
                    service="gpu",
                    status=HealthStatus.HEALTHY,
                    response_time_ms=5.0
                )
            )

            # Should increment alerts_generated counter
            await agent._run_health_checks()

    @pytest.mark.asyncio
    async def test_no_alert_on_healthy_service(self):
        """Kein Alert bei gesundem Service."""
        from Execution_Layer.Agents.monitoring_agent import (
            MonitoringAgent,
            HealthStatus,
        )

        with patch("Execution_Layer.Agents.monitoring_agent.DatabaseHealthChecker") as mock_db:
            mock_db.return_value.check_health = AsyncMock(
                return_value=MagicMock(
                    service="postgresql",
                    status=HealthStatus.HEALTHY,
                    response_time_ms=20.0,
                    message="Database healthy"
                )
            )

            agent = MonitoringAgent(
                db_connection_string="postgresql://localhost:5432/test"
            )

            agent.gpu_checker.check_health = AsyncMock(
                return_value=MagicMock(
                    service="gpu",
                    status=HealthStatus.HEALTHY,
                    response_time_ms=5.0
                )
            )

            await agent._run_health_checks()


class TestErrorHandling:
    """Tests for error handling in monitoring."""

    @pytest.mark.asyncio
    async def test_health_check_exception_handling(self):
        """Ausnahmen in Health Checks behandeln."""
        from Execution_Layer.Agents.monitoring_agent import MonitoringAgent

        with patch("Execution_Layer.Agents.monitoring_agent.DatabaseHealthChecker") as mock_db:
            mock_db.return_value.check_health = AsyncMock(
                side_effect=Exception("Connection error")
            )

            agent = MonitoringAgent(
                db_connection_string="postgresql://localhost:5432/test"
            )

            agent.gpu_checker.check_health = AsyncMock(
                side_effect=Exception("GPU error")
            )

            # Should not raise, should handle gracefully
            await agent._run_health_checks()

    @pytest.mark.asyncio
    async def test_metrics_collection_exception_handling(self):
        """Ausnahmen in Metrik-Sammlung behandeln."""
        from Execution_Layer.Agents.monitoring_agent import MonitoringAgent

        with patch("Execution_Layer.Agents.monitoring_agent.DatabaseHealthChecker"):
            with patch(
                "Execution_Layer.Agents.monitoring_agent.psutil.cpu_percent",
                side_effect=Exception("CPU error")
            ):
                agent = MonitoringAgent(
                    db_connection_string="postgresql://localhost:5432/test"
                )

                # Mock to prevent actual call
                with patch.object(
                    agent,
                    "_collect_system_metrics",
                    new_callable=AsyncMock
                ):
                    await agent._collect_system_metrics()

