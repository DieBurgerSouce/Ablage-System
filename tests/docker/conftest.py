"""
Docker Health Test Suite - Configuration and Fixtures

This module defines all service configurations and pytest fixtures
for comprehensive Docker container health testing.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest

from .helpers.docker_client import DockerClient
from .helpers.log_scanner import LogScanner

if TYPE_CHECKING:
    from collections.abc import Generator


# =============================================================================
# Service Definitions
# =============================================================================


@dataclass
class ServiceDefinition:
    """Definition of a Docker service with its expected configuration."""

    name: str
    container_name: str
    category: str
    critical: bool = False
    requires_gpu: bool = False
    optional: bool = False  # Services mit profiles: ["gpu"] oder ["optional"]
    health_endpoint: str | None = None
    health_port: int | None = None
    expected_networks: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    known_error_patterns: list[str] = field(default_factory=list)


# All services defined in docker-compose.yml
SERVICES: dict[str, ServiceDefinition] = {
    # === Core Services (Critical) ===
    "postgres": ServiceDefinition(
        name="postgres",
        container_name="ablage-postgres",
        category="core",
        critical=True,
        health_port=5432,
        expected_networks=["data-network"],
        known_error_patterns=[
            "database system was not properly shut down",
            "recovery",
        ],
    ),
    "pgbouncer": ServiceDefinition(
        name="pgbouncer",
        container_name="ablage-pgbouncer",
        category="core",
        critical=True,
        health_port=6432,
        expected_networks=["data-network"],
        depends_on=["postgres"],
    ),
    "redis": ServiceDefinition(
        name="redis",
        container_name="ablage-redis",
        category="core",
        critical=True,
        health_port=6379,
        expected_networks=["data-network"],
    ),
    "minio": ServiceDefinition(
        name="minio",
        container_name="ablage-minio",
        category="core",
        critical=True,
        health_port=9000,
        health_endpoint="/minio/health/live",
        expected_networks=["data-network"],
    ),
    # === Backend Services (Critical) ===
    "backend": ServiceDefinition(
        name="backend",
        container_name="ablage-backend",
        category="backend",
        critical=True,
        health_port=8000,
        health_endpoint="/health",
        expected_networks=["data-network", "monitoring-network"],
        depends_on=["postgres", "redis", "minio"],
    ),
    "worker": ServiceDefinition(
        name="worker",
        container_name="ablage-worker",
        category="backend",
        critical=True,
        requires_gpu=True,
        expected_networks=["data-network"],
        depends_on=["redis", "backend"],
        known_error_patterns=[
            "GPU not available",
            "CUDA out of memory",
        ],
    ),
    "worker-cpu": ServiceDefinition(
        name="worker-cpu",
        container_name="ablage-worker-cpu",
        category="backend",
        critical=False,
        expected_networks=["data-network"],
        depends_on=["redis", "backend"],
    ),
    # === Frontend (Critical) ===
    "frontend": ServiceDefinition(
        name="frontend",
        container_name="ablage-frontend",
        category="frontend",
        critical=True,
        health_port=80,
        expected_networks=["monitoring-network"],
        depends_on=["backend"],
    ),
    # === Monitoring Services ===
    "prometheus": ServiceDefinition(
        name="prometheus",
        container_name="ablage-prometheus",
        category="monitoring",
        critical=False,
        health_port=9090,
        health_endpoint="/-/healthy",
        expected_networks=["monitoring-network"],
    ),
    "grafana": ServiceDefinition(
        name="grafana",
        container_name="ablage-grafana",
        category="monitoring",
        critical=False,
        health_port=3000,
        health_endpoint="/api/health",
        expected_networks=["monitoring-network"],
        known_error_patterns=[
            "database is locked",
            "UNIQUE constraint failed",
        ],
    ),
    "loki": ServiceDefinition(
        name="loki",
        container_name="ablage-loki",
        category="monitoring",
        critical=False,
        health_port=3100,
        health_endpoint="/ready",
        expected_networks=["monitoring-network"],
    ),
    "promtail": ServiceDefinition(
        name="promtail",
        container_name="ablage-promtail",
        category="monitoring",
        critical=False,
        expected_networks=["monitoring-network"],
        depends_on=["loki"],
    ),
    "alertmanager": ServiceDefinition(
        name="alertmanager",
        container_name="ablage-alertmanager",
        category="monitoring",
        critical=False,
        health_port=9093,
        health_endpoint="/-/healthy",
        expected_networks=["monitoring-network"],
        known_error_patterns=[
            "unsupported scheme",
            "invalid URL",
        ],
    ),
    # === Exporters ===
    # Note: Service names use underscore in docker-compose.yml but container names use hyphen
    "postgres-exporter": ServiceDefinition(
        name="postgres-exporter",
        container_name="ablage-postgres-exporter",
        category="exporter",
        critical=False,
        health_port=9187,
        expected_networks=["data-network", "monitoring-network"],
        depends_on=["postgres"],
    ),
    "redis-exporter": ServiceDefinition(
        name="redis-exporter",
        container_name="ablage-redis-exporter",
        category="exporter",
        critical=False,
        health_port=9121,
        expected_networks=["data-network", "monitoring-network"],
        depends_on=["redis"],
    ),
    "node-exporter": ServiceDefinition(
        name="node-exporter",
        container_name="ablage-node-exporter",
        category="exporter",
        critical=False,
        health_port=9100,
        expected_networks=["monitoring-network"],
    ),
    "dcgm-exporter": ServiceDefinition(
        name="dcgm-exporter",
        container_name="ablage-dcgm-exporter",
        category="exporter",
        critical=False,
        requires_gpu=True,
        optional=True,  # profiles: ["gpu"]
        health_port=9400,
        expected_networks=["monitoring-network"],
        known_error_patterns=[
            "no GPU",
            "NVML",
            "libcuda",
        ],
    ),
    # === Vector DB ===
    "qdrant": ServiceDefinition(
        name="qdrant",
        container_name="ablage-qdrant",
        category="core",
        critical=False,
        health_port=6333,
        health_endpoint="/healthz",
        expected_networks=["data-network"],
    ),
    # === Security ===
    "clamav": ServiceDefinition(
        name="clamav",
        container_name="ablage-clamav",
        category="security",
        critical=False,
        health_port=3310,
        expected_networks=["data-network"],
        known_error_patterns=[
            "outdated database",
            "freshclam",
        ],
    ),
    "vault": ServiceDefinition(
        name="vault",
        container_name="ablage-vault",
        category="security",
        critical=False,
        health_port=8200,
        health_endpoint="/v1/sys/health",
        expected_networks=["data-network"],
        known_error_patterns=[
            "sealed",
            "not initialized",
        ],
    ),
    # === GPU Services ===
    "reranker": ServiceDefinition(
        name="reranker",
        container_name="ablage-reranker",
        category="gpu",
        critical=False,
        requires_gpu=True,
        optional=True,  # profiles: ["gpu"]
        health_port=8080,
        expected_networks=["data-network"],
        known_error_patterns=[
            "libcuda",
            "GPU not found",
        ],
    ),
}

# Categorize services
OPTIONAL_SERVICES = [s for s in SERVICES.values() if s.optional]

# Categorize services
CRITICAL_SERVICES = [s for s in SERVICES.values() if s.critical]
GPU_SERVICES = [s for s in SERVICES.values() if s.requires_gpu]
MONITORING_SERVICES = [s for s in SERVICES.values() if s.category == "monitoring"]
EXPORTER_SERVICES = [s for s in SERVICES.values() if s.category == "exporter"]


# =============================================================================
# Error Patterns
# =============================================================================

CRITICAL_ERROR_PATTERNS = [
    r"CRITICAL",
    r"FATAL",
    r"panic:",
    r"Traceback \(most recent call last\)",
    r"OOMKilled",
    r"out of memory",
    r"OutOfMemoryError",
    r"ECONNREFUSED",
    r"connection refused",
    r"no route to host",
    r"ETIMEDOUT",
]

IGNORE_PATTERNS = [
    r"level=warning",
    r"level=warn",
    r"WARNING",
    r"retry",
    r"retrying",
    r"deprecated",
    r"DEPRECATED",
    r"healthcheck",
    r"health check",
]


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="session")
def docker_client() -> Generator[DockerClient, None, None]:
    """Provide a DockerClient instance for the test session."""
    client = DockerClient()
    yield client


@pytest.fixture(scope="session")
def log_scanner() -> LogScanner:
    """Provide a LogScanner instance for the test session."""
    return LogScanner(
        error_patterns=CRITICAL_ERROR_PATTERNS,
        ignore_patterns=IGNORE_PATTERNS,
    )


@pytest.fixture(scope="session")
def all_services() -> dict[str, ServiceDefinition]:
    """Return all service definitions."""
    return SERVICES


@pytest.fixture(scope="session")
def critical_services() -> list[ServiceDefinition]:
    """Return only critical services."""
    return CRITICAL_SERVICES


@pytest.fixture(scope="session")
def gpu_services() -> list[ServiceDefinition]:
    """Return only GPU-dependent services."""
    return GPU_SERVICES


@pytest.fixture(scope="session")
def gpu_available() -> bool:
    """Check if GPU is available on the host."""
    try:
        result = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# =============================================================================
# Pytest Configuration
# =============================================================================


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line("markers", "docker: Docker container tests")
    config.addinivalue_line("markers", "critical: Critical service tests (must pass)")
    config.addinivalue_line("markers", "gpu_optional: GPU tests (skip if no GPU)")
    config.addinivalue_line("markers", "connectivity: Service connectivity tests")
    config.addinivalue_line("markers", "prometheus: Prometheus target tests")
    config.addinivalue_line("markers", "logs: Log scanning tests")
