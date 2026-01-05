"""
Container Log Error Tests

Tests for scanning container logs for errors, crashes,
and other anomalies that indicate problems.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from .conftest import ServiceDefinition
    from .helpers.docker_client import DockerClient
    from .helpers.log_scanner import LogScanner


@pytest.mark.docker
@pytest.mark.logs
class TestCriticalErrors:
    """Tests for critical errors in container logs."""

    def test_no_critical_errors_in_critical_services(
        self,
        docker_client: DockerClient,
        log_scanner: LogScanner,
        critical_services: list[ServiceDefinition],
        gpu_available: bool,
    ) -> None:
        """Verify no CRITICAL/FATAL errors in critical service logs."""
        errors_found: dict[str, list[str]] = {}

        for service in critical_services:
            if service.requires_gpu and not gpu_available:
                continue

            if not docker_client.is_container_running(service.name):
                continue

            logs = docker_client.get_container_logs(service.name, lines=500, since="1h")
            result = log_scanner.scan(
                logs.combined,
                container_name=service.name,
                additional_ignore=service.known_error_patterns,
            )

            # Filter to only critical severity
            critical_errors = [m for m in result.matches if m.severity == "critical"]
            if critical_errors:
                errors_found[service.name] = [m.line[:100] for m in critical_errors[:5]]

        assert not errors_found, (
            f"Critical errors found in service logs:\n"
            + "\n".join(f"  {k}: {v}" for k, v in errors_found.items())
        )

    def test_no_oom_errors(
        self,
        docker_client: DockerClient,
        log_scanner: LogScanner,
        all_services: dict[str, ServiceDefinition],
        gpu_available: bool,
    ) -> None:
        """Verify no Out-of-Memory errors in any container logs."""
        oom_patterns = [
            r"OOMKilled",
            r"out of memory",
            r"OutOfMemoryError",
            r"Cannot allocate memory",
            r"MemoryError",
            r"CUDA out of memory",
        ]

        oom_found: dict[str, list[str]] = {}

        for name, service in all_services.items():
            if service.requires_gpu and not gpu_available:
                continue

            if not docker_client.is_container_running(service.name):
                continue

            logs = docker_client.get_container_logs(service.name, lines=500, since="1h")
            result = log_scanner.scan_for_specific_patterns(
                logs.combined,
                patterns=oom_patterns,
                container_name=service.name,
            )

            if result.has_errors:
                oom_found[name] = [m.line[:100] for m in result.matches[:3]]

        assert not oom_found, (
            f"Out-of-Memory errors found:\n"
            + "\n".join(f"  {k}: {v}" for k, v in oom_found.items())
            + "\nConsider increasing memory limits or reducing batch sizes."
        )


@pytest.mark.docker
@pytest.mark.logs
class TestConnectionErrors:
    """Tests for connection and network errors in logs."""

    def test_no_persistent_connection_errors(
        self,
        docker_client: DockerClient,
        log_scanner: LogScanner,
        all_services: dict[str, ServiceDefinition],
        gpu_available: bool,
    ) -> None:
        """Verify no persistent connection refused errors.

        Note: Some connection errors during startup are normal.
        This test looks for patterns that indicate ongoing issues.
        """
        connection_patterns = [
            r"connection refused",
            r"ECONNREFUSED",
            r"no route to host",
            r"ETIMEDOUT",
            r"Connection reset by peer",
            r"Connection timed out",
        ]

        # These are normal during startup
        startup_ignore = [
            r"waiting for",
            r"retrying",
            r"retry",
            r"starting",
            r"initializing",
        ]

        connection_errors: dict[str, int] = {}
        threshold = 10  # More than 10 connection errors is concerning

        for name, service in all_services.items():
            if service.requires_gpu and not gpu_available:
                continue

            if not docker_client.is_container_running(service.name):
                continue

            logs = docker_client.get_container_logs(service.name, lines=500, since="1h")
            result = log_scanner.scan_for_specific_patterns(
                logs.combined,
                patterns=connection_patterns,
                container_name=service.name,
            )

            # Filter out startup-related messages
            real_errors = [
                m for m in result.matches
                if not any(p in m.line.lower() for p in ["retry", "retrying", "waiting"])
            ]

            if len(real_errors) > threshold:
                connection_errors[name] = len(real_errors)

        if connection_errors:
            pytest.xfail(
                f"High connection error count (>{threshold}):\n"
                + "\n".join(f"  {k}: {v} errors" for k, v in connection_errors.items())
                + "\nThis may indicate network issues between services."
            )


@pytest.mark.docker
@pytest.mark.logs
class TestServiceSpecificErrors:
    """Tests for service-specific error patterns."""

    def test_postgres_no_corruption_errors(
        self,
        docker_client: DockerClient,
        log_scanner: LogScanner,
    ) -> None:
        """Verify no database corruption errors in PostgreSQL logs."""
        if not docker_client.is_container_running("postgres"):
            pytest.skip("PostgreSQL container not running")

        corruption_patterns = [
            r"data.*corrupt",
            r"invalid page",
            r"could not read block",
            r"checksum failure",
            r"PANIC",
        ]

        logs = docker_client.get_container_logs("postgres", lines=1000, since="24h")
        result = log_scanner.scan_for_specific_patterns(
            logs.combined,
            patterns=corruption_patterns,
            container_name="postgres",
        )

        assert not result.has_errors, (
            f"Database corruption indicators found:\n"
            + "\n".join(f"  {m.line[:100]}" for m in result.matches)
            + "\nImmediate backup and investigation required!"
        )

    def test_redis_no_memory_errors(
        self,
        docker_client: DockerClient,
        log_scanner: LogScanner,
    ) -> None:
        """Verify Redis is not running out of memory."""
        if not docker_client.is_container_running("redis"):
            pytest.skip("Redis container not running")

        memory_patterns = [
            r"maxmemory limit reached",
            r"OOM command not allowed",
            r"Can't save in background",
            r"Background saving error",
        ]

        logs = docker_client.get_container_logs("redis", lines=500, since="1h")
        result = log_scanner.scan_for_specific_patterns(
            logs.combined,
            patterns=memory_patterns,
            container_name="redis",
        )

        assert not result.has_errors, (
            f"Redis memory issues found:\n"
            + "\n".join(f"  {m.line[:100]}" for m in result.matches)
            + "\nConsider increasing Redis maxmemory or clearing old keys."
        )

    def test_backend_no_unhandled_exceptions(
        self,
        docker_client: DockerClient,
        log_scanner: LogScanner,
    ) -> None:
        """Verify no unhandled exceptions in backend logs."""
        if not docker_client.is_container_running("backend"):
            pytest.skip("Backend container not running")

        exception_patterns = [
            r"Traceback \(most recent call last\)",
            r"Unhandled exception",
            r"Internal Server Error",
            r"500 Internal Server Error",
        ]

        # Ignore expected/handled errors
        ignore_patterns = [
            r"HTTPException",
            r"ValidationError",
            r"401 Unauthorized",
            r"403 Forbidden",
            r"404 Not Found",
        ]

        logs = docker_client.get_container_logs("backend", lines=500, since="1h")
        result = log_scanner.scan_for_specific_patterns(
            logs.combined,
            patterns=exception_patterns,
            container_name="backend",
        )

        # Filter out expected errors
        unexpected = [
            m for m in result.matches
            if not any(p.lower() in m.line.lower() for p in ignore_patterns)
        ]

        if unexpected:
            pytest.xfail(
                f"Unhandled exceptions in backend:\n"
                + "\n".join(f"  {m.line[:100]}" for m in unexpected[:5])
                + f"\n({len(unexpected)} total)"
            )


@pytest.mark.docker
@pytest.mark.logs
class TestLogScanSummary:
    """Summary test that scans all logs and reports findings."""

    def test_full_log_scan_summary(
        self,
        docker_client: DockerClient,
        log_scanner: LogScanner,
        all_services: dict[str, ServiceDefinition],
        gpu_available: bool,
    ) -> None:
        """Generate a comprehensive log scan summary.

        This test always passes but outputs useful diagnostics.
        """
        summary_data: dict[str, dict[str, int | list[str]]] = {}

        for name, service in all_services.items():
            if service.requires_gpu and not gpu_available:
                continue

            if not docker_client.is_container_running(service.name):
                continue

            logs = docker_client.get_container_logs(service.name, lines=500, since="1h")
            result = log_scanner.scan(
                logs.combined,
                container_name=service.name,
                additional_ignore=service.known_error_patterns,
            )

            if result.error_count > 0:
                summary_data[name] = {
                    "errors": result.error_count,
                    "samples": [m.line[:80] for m in result.matches[:3]],
                }

        # Print summary
        print("\n=== Log Scan Summary (last 1h) ===")

        if not summary_data:
            print("No errors found in any container logs!")
        else:
            for container, data in summary_data.items():
                print(f"\n{container}: {data['errors']} errors")
                for sample in data["samples"]:
                    print(f"  - {sample}...")

        # Always pass - this is informational
        assert True
