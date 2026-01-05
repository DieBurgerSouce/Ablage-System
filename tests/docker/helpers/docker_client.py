"""
Docker CLI wrapper for container management and inspection.

Provides a clean interface to Docker commands without requiring
the docker-py library, using subprocess for maximum compatibility.

Optimized for performance with caching and batch operations.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


@dataclass
class ContainerInfo:
    """Information about a Docker container."""

    name: str
    container_id: str
    status: str
    state: str
    health: str | None
    restart_count: int
    image: str
    ports: dict[str, str]
    networks: list[str]
    created: str
    started: str | None


@dataclass
class ContainerLogs:
    """Container log output."""

    container_name: str
    stdout: str
    stderr: str
    combined: str


class DockerClient:
    """Docker CLI wrapper for container operations.

    Uses caching to minimize Docker CLI calls for better performance.
    """

    def __init__(self, compose_project: str = "ablage_system") -> None:
        """Initialize the Docker client.

        Args:
            compose_project: Docker Compose project name prefix
        """
        self.compose_project = compose_project
        self._container_cache: dict[str, ContainerInfo] | None = None
        self._verify_docker()

    def _verify_docker(self) -> None:
        """Verify Docker is available and running."""
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=10,
                check=False,
            )
            if result.returncode != 0:
                msg = "Docker daemon is not running"
                raise RuntimeError(msg)
        except FileNotFoundError as e:
            msg = "Docker CLI not found in PATH"
            raise RuntimeError(msg) from e

    def _run_command(
        self,
        args: list[str],
        timeout: int = 30,
    ) -> subprocess.CompletedProcess[str]:
        """Run a docker command and return the result."""
        return subprocess.run(
            ["docker", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def refresh_cache(self) -> None:
        """Force refresh of the container cache."""
        self._container_cache = None
        self._load_all_containers()

    def _load_all_containers(self) -> dict[str, ContainerInfo]:
        """Load all containers with a single batch operation.

        Uses docker inspect with JSON format to get all info at once.
        """
        if self._container_cache is not None:
            return self._container_cache

        # Get all container IDs first
        result = self._run_command(["ps", "-a", "-q"])
        if result.returncode != 0 or not result.stdout.strip():
            self._container_cache = {}
            return self._container_cache

        container_ids = result.stdout.strip().split("\n")

        # Batch inspect all containers at once
        result = self._run_command(
            ["inspect", *container_ids],
            timeout=60,
        )

        if result.returncode != 0:
            self._container_cache = {}
            return self._container_cache

        try:
            containers_data = json.loads(result.stdout)
        except json.JSONDecodeError:
            self._container_cache = {}
            return self._container_cache

        self._container_cache = {}
        for data in containers_data:
            name = data.get("Name", "").lstrip("/")

            # Extract health status
            health = None
            state_data = data.get("State", {})
            health_data = state_data.get("Health")
            if health_data:
                health = health_data.get("Status", "none")
            else:
                health = "none"

            # Extract networks
            networks = list(data.get("NetworkSettings", {}).get("Networks", {}).keys())

            # Extract ports
            ports = {}
            port_bindings = data.get("HostConfig", {}).get("PortBindings", {}) or {}
            for container_port, bindings in port_bindings.items():
                if bindings:
                    for binding in bindings:
                        host_port = binding.get("HostPort", "")
                        if host_port:
                            ports[host_port] = container_port.split("/")[0]

            container = ContainerInfo(
                name=name,
                container_id=data.get("Id", "")[:12],
                status=state_data.get("Status", "unknown"),
                state=state_data.get("Status", "unknown"),
                health=health,
                restart_count=data.get("RestartCount", 0),
                image=data.get("Config", {}).get("Image", ""),
                ports=ports,
                networks=networks,
                created=data.get("Created", ""),
                started=state_data.get("StartedAt"),
            )
            self._container_cache[name] = container

        return self._container_cache

    def list_containers(self, all_containers: bool = True) -> list[ContainerInfo]:
        """List all containers with detailed info."""
        containers = self._load_all_containers()
        return list(containers.values())

    def get_container_logs(
        self,
        container_name: str,
        lines: int = 100,
        since: str | None = None,
    ) -> ContainerLogs:
        """Get container logs."""
        # Resolve to actual container name
        container = self.get_container_by_service(container_name)
        actual_name = container.name if container else container_name

        args = ["logs", "--tail", str(lines)]
        if since:
            args.extend(["--since", since])
        args.append(actual_name)

        result = self._run_command(args, timeout=60)

        return ContainerLogs(
            container_name=actual_name,
            stdout=result.stdout,
            stderr=result.stderr,
            combined=result.stdout + result.stderr,
        )

    def exec_in_container(
        self,
        container_name: str,
        command: list[str],
        timeout: int = 30,
    ) -> tuple[int, str, str]:
        """Execute a command inside a container."""
        result = self._run_command(
            ["exec", container_name, *command],
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr

    def check_port_connectivity(
        self,
        from_container: str,
        target_host: str,
        target_port: int,
        timeout: int = 3,
    ) -> bool:
        """Check if a container can reach a target host:port."""
        # Try multiple methods for connectivity check
        commands_to_try = [
            # Python-based check (most reliable, most containers have Python)
            ["python3", "-c", f"import socket; s=socket.socket(); s.settimeout({timeout}); s.connect(('{target_host}', {target_port})); s.close(); print('OK')"],
            ["python", "-c", f"import socket; s=socket.socket(); s.settimeout({timeout}); s.connect(('{target_host}', {target_port})); s.close(); print('OK')"],
            # nc (netcat)
            ["nc", "-z", "-w", str(timeout), target_host, str(target_port)],
            # bash /dev/tcp
            ["bash", "-c", f"timeout {timeout} bash -c 'echo > /dev/tcp/{target_host}/{target_port}' 2>/dev/null"],
        ]

        for cmd in commands_to_try:
            try:
                returncode, stdout, _ = self.exec_in_container(
                    from_container, cmd, timeout=timeout + 5
                )
                if returncode == 0:
                    return True
            except Exception:
                continue

        return False

    def get_container_by_service(self, service_name: str) -> ContainerInfo | None:
        """Get container info by docker-compose service name."""
        containers = self._load_all_containers()

        # Match by common naming patterns
        patterns = [
            f"ablage-{service_name}",
            f"ablage_{service_name}",
            f"{self.compose_project}_{service_name}",
            f"{self.compose_project}-{service_name}",
            service_name,
        ]

        for pattern in patterns:
            if pattern in containers:
                return containers[pattern]
            # Also check with partial match
            for name, container in containers.items():
                if name.startswith(pattern) or pattern in name:
                    return container

        return None

    def is_container_running(self, container_name: str) -> bool:
        """Check if a container is running."""
        container = self.get_container_by_service(container_name)
        return container is not None and container.state == "running"

    def is_container_healthy(self, container_name: str) -> bool | None:
        """Check if a container is healthy."""
        container = self.get_container_by_service(container_name)
        if container is None:
            return False
        if container.health == "none" or container.health is None:
            return None
        return container.health == "healthy"

    def get_restart_count(self, container_name: str) -> int:
        """Get the restart count for a container."""
        container = self.get_container_by_service(container_name)
        return container.restart_count if container else 0

    def get_all_ablage_containers(self) -> list[ContainerInfo]:
        """Get only Ablage-System containers."""
        containers = self._load_all_containers()
        return [c for c in containers.values() if c.name.startswith("ablage-")]
