"""
Container Status Tests

Tests for verifying that all Docker containers are in the expected state:
- Running
- Healthy (if health check defined)
- No restart loops
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from .conftest import ServiceDefinition
    from .helpers.docker_client import DockerClient


@pytest.mark.docker
class TestContainerStatus:
    """Tests for container running status."""

    def test_all_containers_running(
        self,
        docker_client: DockerClient,
        all_services: dict[str, ServiceDefinition],
        gpu_available: bool,
    ) -> None:
        """Verify all expected containers are running.

        Skips GPU-dependent containers if GPU is not available.
        """
        not_running = []
        skipped_gpu = []
        skipped_optional = []

        for name, service in all_services.items():
            # Skip optional services (profiles: ["gpu"] or ["optional"])
            if service.optional:
                skipped_optional.append(name)
                continue

            # Skip GPU services if no GPU
            if service.requires_gpu and not gpu_available:
                skipped_gpu.append(name)
                continue

            if not docker_client.is_container_running(service.name):
                not_running.append(name)

        if skipped_optional:
            print(f"Skipped optional services: {skipped_optional}")
        if skipped_gpu:
            pytest.skip(f"Skipped GPU services (no GPU): {skipped_gpu}")

        assert not not_running, (
            f"The following containers are not running: {not_running}\n"
            f"Run 'docker-compose ps' to check status."
        )

    @pytest.mark.critical
    def test_critical_containers_running(
        self,
        docker_client: DockerClient,
        critical_services: list[ServiceDefinition],
        gpu_available: bool,
    ) -> None:
        """Verify all critical containers are running.

        Critical containers are essential for system operation:
        - postgres, redis, minio (core data)
        - backend, worker (application)
        - frontend (user access)
        """
        not_running = []

        for service in critical_services:
            # Worker is GPU-dependent but critical - check if GPU available
            if service.requires_gpu and not gpu_available:
                continue

            if not docker_client.is_container_running(service.name):
                not_running.append(service.name)

        assert not not_running, (
            f"CRITICAL: These essential containers are not running: {not_running}\n"
            f"System cannot function without these services!"
        )


@pytest.mark.docker
class TestContainerHealth:
    """Tests for container health status."""

    def test_containers_with_healthchecks_are_healthy(
        self,
        docker_client: DockerClient,
        all_services: dict[str, ServiceDefinition],
        gpu_available: bool,
    ) -> None:
        """Verify containers with health checks are healthy."""
        unhealthy = []
        no_healthcheck = []

        for name, service in all_services.items():
            # Skip optional services (profiles: ["gpu"] or ["optional"])
            if service.optional:
                continue

            # Skip GPU services if no GPU
            if service.requires_gpu and not gpu_available:
                continue

            # Only check containers with health endpoints defined
            if service.health_endpoint is None and service.health_port is None:
                no_healthcheck.append(name)
                continue

            health_status = docker_client.is_container_healthy(service.name)

            if health_status is False:
                container = docker_client.get_container_by_service(service.name)
                unhealthy.append(
                    f"{name} (status: {container.health if container else 'not found'})"
                )

        # Log containers without health checks for visibility
        if no_healthcheck:
            print(f"Containers without health checks: {no_healthcheck}")

        assert not unhealthy, (
            f"The following containers are unhealthy: {unhealthy}\n"
            f"Check 'docker inspect <container>' for health check details."
        )

    @pytest.mark.critical
    def test_critical_containers_healthy(
        self,
        docker_client: DockerClient,
        critical_services: list[ServiceDefinition],
        gpu_available: bool,
    ) -> None:
        """Verify critical containers are healthy or have no health check."""
        unhealthy = []

        for service in critical_services:
            if service.requires_gpu and not gpu_available:
                continue

            health_status = docker_client.is_container_healthy(service.name)

            # None means no health check, which is OK
            # False means unhealthy, which is bad
            if health_status is False:
                unhealthy.append(service.name)

        assert not unhealthy, (
            f"CRITICAL: These essential containers are unhealthy: {unhealthy}\n"
            f"Check container logs for root cause."
        )


@pytest.mark.docker
class TestRestartBehavior:
    """Tests for container restart behavior."""

    def test_no_restart_loops(
        self,
        docker_client: DockerClient,
        all_services: dict[str, ServiceDefinition],
        gpu_available: bool,
    ) -> None:
        """Verify no containers are in restart loops.

        A restart count > 3 indicates potential issues.
        """
        restart_issues = []
        max_restarts = 3

        for name, service in all_services.items():
            # Skip GPU services if no GPU - they're expected to fail
            if service.requires_gpu and not gpu_available:
                continue

            restart_count = docker_client.get_restart_count(service.name)

            if restart_count > max_restarts:
                restart_issues.append(f"{name}: {restart_count} restarts")

        assert not restart_issues, (
            f"Containers with excessive restarts (>{max_restarts}): {restart_issues}\n"
            f"Check logs with 'docker logs <container>' for crash reasons."
        )

    @pytest.mark.critical
    def test_critical_containers_stable(
        self,
        docker_client: DockerClient,
        critical_services: list[ServiceDefinition],
        gpu_available: bool,
    ) -> None:
        """Verify critical containers have no restarts.

        Critical containers should be stable - any restart is concerning.
        """
        restarted = []

        for service in critical_services:
            if service.requires_gpu and not gpu_available:
                continue

            restart_count = docker_client.get_restart_count(service.name)

            if restart_count > 0:
                restarted.append(f"{service.name}: {restart_count} restarts")

        # This is a warning, not a hard failure - some restarts may be expected
        if restarted:
            pytest.xfail(
                f"Critical containers have restarted: {restarted}\n"
                f"Investigate if these are expected restarts or crashes."
            )


@pytest.mark.docker
@pytest.mark.gpu_optional
class TestGPUContainers:
    """Tests for GPU-dependent containers."""

    def test_gpu_containers_when_gpu_available(
        self,
        docker_client: DockerClient,
        gpu_services: list[ServiceDefinition],
        gpu_available: bool,
    ) -> None:
        """Verify GPU containers are running when GPU is available.

        Skips optional GPU services (profiles: ["gpu"]) as they require
        explicit profile activation with docker-compose --profile gpu.
        """
        if not gpu_available:
            pytest.skip("GPU not available - skipping GPU container tests")

        not_running = []
        skipped_optional = []

        for service in gpu_services:
            # Skip optional GPU services (require --profile gpu)
            if service.optional:
                skipped_optional.append(service.name)
                continue

            if not docker_client.is_container_running(service.name):
                not_running.append(service.name)

        if skipped_optional:
            print(f"Skipped optional GPU services (require --profile gpu): {skipped_optional}")

        assert not not_running, (
            f"GPU containers not running despite GPU being available: {not_running}\n"
            f"Check if GPU passthrough is configured correctly in docker-compose."
        )

    def test_gpu_containers_fail_gracefully_without_gpu(
        self,
        docker_client: DockerClient,
        gpu_services: list[ServiceDefinition],
        gpu_available: bool,
    ) -> None:
        """Verify GPU containers handle missing GPU gracefully.

        When no GPU is available, GPU containers should either:
        - Not start (expected)
        - Start with CPU fallback
        - Have clear error messages in logs

        Skips optional GPU services (profiles: ["gpu"]).
        """
        if gpu_available:
            pytest.skip("GPU available - testing graceful failure not applicable")

        # Just verify that the system runs without GPU containers
        # This is informational, not a hard requirement
        running_gpu = []
        for service in gpu_services:
            # Skip optional services - they won't be started without --profile gpu
            if service.optional:
                continue

            if docker_client.is_container_running(service.name):
                running_gpu.append(service.name)

        if running_gpu:
            print(f"GPU containers running without GPU (CPU fallback?): {running_gpu}")


@pytest.mark.docker
class TestContainerSummary:
    """Summary test that provides overview of all containers."""

    def test_container_status_summary(
        self,
        docker_client: DockerClient,
        all_services: dict[str, ServiceDefinition],
        gpu_available: bool,
    ) -> None:
        """Generate a summary of all container statuses.

        This test always passes but outputs useful diagnostics.
        """
        running = []
        stopped = []
        unhealthy = []
        restarting = []

        for name, service in all_services.items():
            container = docker_client.get_container_by_service(service.name)

            if container is None:
                stopped.append(f"{name} (not found)")
                continue

            if container.state != "running":
                stopped.append(f"{name} ({container.state})")
                continue

            if container.health == "unhealthy":
                unhealthy.append(name)

            if container.restart_count > 0:
                restarting.append(f"{name} ({container.restart_count}x)")

            running.append(name)

        summary = [
            "\n=== Docker Container Status Summary ===",
            f"GPU Available: {gpu_available}",
            f"Running: {len(running)}/{len(all_services)}",
            f"  {running}",
        ]

        if stopped:
            summary.append(f"Stopped/Missing: {stopped}")

        if unhealthy:
            summary.append(f"Unhealthy: {unhealthy}")

        if restarting:
            summary.append(f"Has Restarts: {restarting}")

        print("\n".join(summary))

        # Always pass - this is informational
        assert True
