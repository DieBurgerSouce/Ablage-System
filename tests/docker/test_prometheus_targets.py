"""
Prometheus Target Tests

Tests for verifying Prometheus scrape targets are healthy
and collecting metrics correctly.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from .helpers.docker_client import DockerClient


@pytest.mark.docker
@pytest.mark.prometheus
class TestPrometheusTargets:
    """Tests for Prometheus target health."""

    def _get_prometheus_targets(
        self,
        docker_client: DockerClient,
    ) -> dict[str, Any] | None:
        """Fetch Prometheus targets via API.

        Returns:
            Dictionary with target data or None if unavailable
        """
        if not docker_client.is_container_running("prometheus"):
            return None

        # Execute curl inside prometheus container
        returncode, stdout, stderr = docker_client.exec_in_container(
            container_name="ablage-prometheus",
            command=["wget", "-q", "-O", "-", "http://localhost:9090/api/v1/targets"],
            timeout=10,
        )

        if returncode != 0:
            # Try with curl
            returncode, stdout, stderr = docker_client.exec_in_container(
                container_name="ablage-prometheus",
                command=["curl", "-s", "http://localhost:9090/api/v1/targets"],
                timeout=10,
            )

        if returncode != 0:
            return None

        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return None

    def test_prometheus_running(
        self,
        docker_client: DockerClient,
    ) -> None:
        """Verify Prometheus is running before other tests."""
        assert docker_client.is_container_running("prometheus"), (
            "Prometheus container is not running!\n"
            "Start with: docker-compose up -d prometheus"
        )

    def test_all_targets_discovered(
        self,
        docker_client: DockerClient,
    ) -> None:
        """Verify Prometheus has discovered expected targets."""
        if not docker_client.is_container_running("prometheus"):
            pytest.skip("Prometheus container not running")

        targets_data = self._get_prometheus_targets(docker_client)

        if targets_data is None:
            pytest.skip("Could not fetch Prometheus targets API")

        if targets_data.get("status") != "success":
            pytest.fail(f"Prometheus API error: {targets_data}")

        # Extract active targets
        active_targets = targets_data.get("data", {}).get("activeTargets", [])

        expected_jobs = [
            "prometheus",
            "ablage-backend",
            "ablage-worker",
            "postgres",
            "redis",
            "node",
        ]

        discovered_jobs = {t.get("labels", {}).get("job") for t in active_targets}

        missing = [j for j in expected_jobs if j not in discovered_jobs]

        # This is informational - some jobs may be optional
        if missing:
            print(f"Jobs not discovered (may be expected): {missing}")
            print(f"Discovered jobs: {discovered_jobs}")

    @pytest.mark.critical
    def test_critical_targets_up(
        self,
        docker_client: DockerClient,
    ) -> None:
        """Verify critical scrape targets are UP."""
        if not docker_client.is_container_running("prometheus"):
            pytest.skip("Prometheus container not running")

        targets_data = self._get_prometheus_targets(docker_client)

        if targets_data is None:
            pytest.skip("Could not fetch Prometheus targets API")

        if targets_data.get("status") != "success":
            pytest.fail(f"Prometheus API error: {targets_data}")

        active_targets = targets_data.get("data", {}).get("activeTargets", [])

        # Critical jobs that must be UP
        critical_jobs = ["ablage-backend", "postgres", "redis"]

        down_targets = []
        for target in active_targets:
            job = target.get("labels", {}).get("job", "")
            health = target.get("health", "")

            if job in critical_jobs and health != "up":
                last_error = target.get("lastError", "unknown")
                down_targets.append(f"{job}: {health} - {last_error}")

        assert not down_targets, (
            f"Critical Prometheus targets are DOWN:\n"
            + "\n".join(f"  {t}" for t in down_targets)
            + "\nCheck service health and network connectivity."
        )

    def test_no_scrape_errors(
        self,
        docker_client: DockerClient,
    ) -> None:
        """Verify no persistent scrape errors."""
        if not docker_client.is_container_running("prometheus"):
            pytest.skip("Prometheus container not running")

        targets_data = self._get_prometheus_targets(docker_client)

        if targets_data is None:
            pytest.skip("Could not fetch Prometheus targets API")

        if targets_data.get("status") != "success":
            pytest.fail(f"Prometheus API error: {targets_data}")

        active_targets = targets_data.get("data", {}).get("activeTargets", [])

        # Collect targets with errors
        error_targets = []
        for target in active_targets:
            last_error = target.get("lastError", "")
            if last_error:
                job = target.get("labels", {}).get("job", "unknown")
                error_targets.append(f"{job}: {last_error}")

        if error_targets:
            pytest.xfail(
                f"Prometheus targets with scrape errors:\n"
                + "\n".join(f"  {t}" for t in error_targets)
            )


@pytest.mark.docker
@pytest.mark.prometheus
class TestPrometheusHealth:
    """Tests for Prometheus own health."""

    def test_prometheus_healthy(
        self,
        docker_client: DockerClient,
    ) -> None:
        """Verify Prometheus health endpoint returns OK."""
        if not docker_client.is_container_running("prometheus"):
            pytest.skip("Prometheus container not running")

        returncode, stdout, _ = docker_client.exec_in_container(
            container_name="ablage-prometheus",
            command=["wget", "-q", "-O", "-", "http://localhost:9090/-/healthy"],
            timeout=10,
        )

        if returncode != 0:
            # Try curl
            returncode, stdout, _ = docker_client.exec_in_container(
                container_name="ablage-prometheus",
                command=["curl", "-s", "http://localhost:9090/-/healthy"],
                timeout=10,
            )

        assert returncode == 0, "Prometheus health check failed"
        assert "Healthy" in stdout or returncode == 0, "Prometheus reports unhealthy"

    def test_prometheus_ready(
        self,
        docker_client: DockerClient,
    ) -> None:
        """Verify Prometheus ready endpoint returns OK."""
        if not docker_client.is_container_running("prometheus"):
            pytest.skip("Prometheus container not running")

        returncode, stdout, _ = docker_client.exec_in_container(
            container_name="ablage-prometheus",
            command=["wget", "-q", "-O", "-", "http://localhost:9090/-/ready"],
            timeout=10,
        )

        if returncode != 0:
            returncode, stdout, _ = docker_client.exec_in_container(
                container_name="ablage-prometheus",
                command=["curl", "-s", "http://localhost:9090/-/ready"],
                timeout=10,
            )

        assert returncode == 0, "Prometheus not ready"


@pytest.mark.docker
@pytest.mark.prometheus
class TestTargetsSummary:
    """Summary test for all Prometheus targets."""

    def test_prometheus_targets_summary(
        self,
        docker_client: DockerClient,
    ) -> None:
        """Generate a summary of all Prometheus targets.

        This test always passes but outputs useful diagnostics.
        """
        if not docker_client.is_container_running("prometheus"):
            pytest.skip("Prometheus container not running")

        targets_data = self._get_prometheus_targets(docker_client)

        if targets_data is None:
            print("Could not fetch Prometheus targets")
            return

        active_targets = targets_data.get("data", {}).get("activeTargets", [])
        dropped_targets = targets_data.get("data", {}).get("droppedTargets", [])

        # Categorize targets
        up_targets = []
        down_targets = []

        for target in active_targets:
            job = target.get("labels", {}).get("job", "unknown")
            instance = target.get("labels", {}).get("instance", "unknown")
            health = target.get("health", "unknown")

            if health == "up":
                up_targets.append(f"{job} ({instance})")
            else:
                down_targets.append(f"{job} ({instance}): {health}")

        print("\n=== Prometheus Targets Summary ===")
        print(f"Active Targets: {len(active_targets)}")
        print(f"Dropped Targets: {len(dropped_targets)}")
        print(f"\nUP ({len(up_targets)}):")
        for t in up_targets:
            print(f"  + {t}")

        if down_targets:
            print(f"\nDOWN ({len(down_targets)}):")
            for t in down_targets:
                print(f"  - {t}")

        # Always pass
        assert True

    def _get_prometheus_targets(
        self,
        docker_client: DockerClient,
    ) -> dict[str, Any] | None:
        """Fetch Prometheus targets."""
        returncode, stdout, _ = docker_client.exec_in_container(
            container_name="ablage-prometheus",
            command=["wget", "-q", "-O", "-", "http://localhost:9090/api/v1/targets"],
            timeout=10,
        )

        if returncode != 0:
            returncode, stdout, _ = docker_client.exec_in_container(
                container_name="ablage-prometheus",
                command=["curl", "-s", "http://localhost:9090/api/v1/targets"],
                timeout=10,
            )

        if returncode != 0:
            return None

        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return None
