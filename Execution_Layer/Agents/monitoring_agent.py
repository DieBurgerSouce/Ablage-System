"""
Monitoring Agent - Ablage-System

Continuously monitors system health, collects metrics, and triggers alerts.

Key Responsibilities:
- Health check monitoring (database, Redis, MinIO, GPU)
- Performance metric collection (response time, throughput, error rate)
- Resource utilization tracking (CPU, RAM, VRAM, disk)
- Alert generation and escalation
- Automatic remediation for common issues

Related Documents:
- Troubleshooting Index: ../../Meta_Layer/Indexes/troubleshooting_index.yaml
- Celery Worker Crash Log: ../../Dynamic_Knowledge/Logs/celery_worker_crash_log.md
"""

import asyncio
import psutil
import torch
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum

import redis
import psycopg
from prometheus_client import Counter, Gauge, Histogram

import structlog
logger = structlog.get_logger(__name__)


class HealthStatus(str, Enum):
    """Health status levels."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    CRITICAL = "critical"


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class HealthCheckResult:
    """Result of a health check."""
    service: str
    status: HealthStatus
    response_time_ms: float
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


# Prometheus Metrics
health_check_status = Gauge('health_check_status', 'Health check status', ['service'])
system_cpu_percent = Gauge('system_cpu_percent', 'System CPU usage percentage')
system_memory_percent = Gauge('system_memory_percent', 'System memory usage')
gpu_vram_percent = Gauge('gpu_vram_percent', 'GPU VRAM usage', ['gpu_id'])
alerts_generated = Counter('alerts_generated_total', 'Total alerts', ['severity'])


class DatabaseHealthChecker:
    """Check PostgreSQL database health."""

    def __init__(self, connection_string: str):
        self.connection_string = connection_string

    async def check_health(self) -> HealthCheckResult:
        """Check database connectivity and performance."""
        start_time = datetime.utcnow()

        try:
            conn = await psycopg.AsyncConnection.connect(self.connection_string)
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
                await cur.fetchone()
            await conn.close()

            response_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            status = HealthStatus.DEGRADED if response_time_ms > 1000 else HealthStatus.HEALTHY
            message = "Database slow" if response_time_ms > 1000 else "Database healthy"

            return HealthCheckResult(
                service="postgresql",
                status=status,
                response_time_ms=response_time_ms,
                message=message
            )

        except Exception as e:
            logger.exception("database_health_check_failed", error=str(e))
            return HealthCheckResult(
                service="postgresql",
                status=HealthStatus.UNHEALTHY,
                response_time_ms=0,
                message=f"Database connection failed: {str(e)}"
            )


class GPUHealthChecker:
    """Check GPU health and availability."""

    async def check_health(self) -> HealthCheckResult:
        """Check GPU availability and resource usage."""
        start_time = datetime.utcnow()

        try:
            if not torch.cuda.is_available():
                return HealthCheckResult(
                    service="gpu",
                    status=HealthStatus.UNHEALTHY,
                    response_time_ms=0,
                    message="GPU not available"
                )

            device = torch.cuda.current_device()
            props = torch.cuda.get_device_properties(device)
            total_memory = props.total_memory / 1024**3
            allocated_memory = torch.cuda.memory_allocated(device) / 1024**3
            vram_percent = (allocated_memory / total_memory) * 100

            response_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            if vram_percent > 90:
                status = HealthStatus.CRITICAL
                message = f"GPU VRAM critical ({vram_percent:.1f}%)"
            elif vram_percent > 85:
                status = HealthStatus.DEGRADED
                message = f"GPU VRAM high ({vram_percent:.1f}%)"
            else:
                status = HealthStatus.HEALTHY
                message = "GPU healthy"

            return HealthCheckResult(
                service="gpu",
                status=status,
                response_time_ms=response_time_ms,
                message=message,
                details={"vram_percent": vram_percent}
            )

        except Exception as e:
            logger.exception("gpu_health_check_failed", error=str(e))
            return HealthCheckResult(
                service="gpu",
                status=HealthStatus.UNHEALTHY,
                response_time_ms=0,
                message=f"GPU check failed: {str(e)}"
            )


class MonitoringAgent:
    """Main monitoring agent orchestrating health checks and metrics."""

    def __init__(self, db_connection_string: str, check_interval_seconds: int = 30):
        self.check_interval = check_interval_seconds
        self.db_checker = DatabaseHealthChecker(db_connection_string)
        self.gpu_checker = GPUHealthChecker()
        self.running = False

    async def run(self):
        """Main monitoring loop."""
        self.running = True
        logger.info("monitoring_agent_started", interval=self.check_interval)

        while self.running:
            try:
                await self._run_health_checks()
                await self._collect_system_metrics()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.exception("monitoring_cycle_error", error=str(e))
                await asyncio.sleep(self.check_interval)

    async def stop(self):
        """Stop the monitoring agent."""
        self.running = False
        logger.info("monitoring_agent_stopped")

    async def _run_health_checks(self):
        """Run all health checks."""
        results = await asyncio.gather(
            self.db_checker.check_health(),
            self.gpu_checker.check_health(),
            return_exceptions=True
        )

        for result in results:
            if isinstance(result, Exception):
                continue

            status_value = {
                HealthStatus.HEALTHY: 1.0,
                HealthStatus.DEGRADED: 0.5,
                HealthStatus.UNHEALTHY: 0.0,
            }.get(result.status, 0.0)

            health_check_status.labels(service=result.service).set(status_value)

            if result.status in [HealthStatus.UNHEALTHY, HealthStatus.CRITICAL]:
                alerts_generated.labels(severity="critical").inc()
                logger.error("service_unhealthy", service=result.service, message=result.message)

    async def _collect_system_metrics(self):
        """Collect system resource metrics."""
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()

        system_cpu_percent.set(cpu_percent)
        system_memory_percent.set(memory.percent)

        if torch.cuda.is_available():
            device = torch.cuda.current_device()
            total = torch.cuda.get_device_properties(device).total_memory
            allocated = torch.cuda.memory_allocated(device)
            vram_pct = (allocated / total) * 100
            gpu_vram_percent.labels(gpu_id=0).set(vram_pct)


async def main():
    """Main entry point."""
    import os
    db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/ablage")
    agent = MonitoringAgent(db_connection_string=db_url)

    try:
        await agent.run()
    except KeyboardInterrupt:
        await agent.stop()


if __name__ == "__main__":
    asyncio.run(main())
