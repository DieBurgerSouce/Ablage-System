#!/usr/bin/env python
"""
Validate Docker GPU configuration for Ablage-System OCR backends.

Checks:
1. NVIDIA driver installation
2. Docker GPU support (--gpus flag)
3. docker-compose.yml GPU configuration
4. GPU access from within containers

Usage:
    python scripts/validate_docker_gpu.py
    python scripts/validate_docker_gpu.py --verbose
    python scripts/validate_docker_gpu.py --test-container
"""

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Try to import yaml for docker-compose parsing
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


@dataclass
class ValidationResult:
    """Result of a validation check."""
    name: str
    passed: bool
    message: str
    details: dict = field(default_factory=dict)


@dataclass
class ValidationReport:
    """Complete validation report."""
    results: list[ValidationResult] = field(default_factory=list)
    overall_passed: bool = True

    def add(self, result: ValidationResult):
        self.results.append(result)
        if not result.passed:
            self.overall_passed = False


class DockerGPUValidator:
    """Validate Docker GPU configuration."""

    def __init__(self, compose_file: Path = Path("docker-compose.yml")):
        self.compose_file = compose_file
        self.report = ValidationReport()

    def run_command(
        self,
        cmd: list[str],
        timeout: int = 30,
        capture_output: bool = True,
    ) -> tuple[int, str, str]:
        """Run a command and return exit code, stdout, stderr."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=capture_output,
                text=True,
                timeout=timeout,
                shell=True if sys.platform == "win32" else False,
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Command timed out"
        except FileNotFoundError:
            return -1, "", f"Command not found: {cmd[0]}"
        except Exception as e:
            return -1, "", str(e)

    def check_nvidia_driver(self) -> ValidationResult:
        """Check if NVIDIA driver is installed and working."""
        print("Checking NVIDIA driver...")

        cmd = ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"]
        code, stdout, stderr = self.run_command(cmd)

        if code != 0:
            return ValidationResult(
                name="NVIDIA Driver",
                passed=False,
                message="NVIDIA driver not found or not working",
                details={"error": stderr or "nvidia-smi not found"},
            )

        # Parse output
        lines = stdout.strip().split("\n")
        gpus = []
        for line in lines:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                gpus.append({
                    "name": parts[0],
                    "memory": parts[1],
                    "driver": parts[2],
                })

        return ValidationResult(
            name="NVIDIA Driver",
            passed=True,
            message=f"Found {len(gpus)} GPU(s)",
            details={"gpus": gpus},
        )

    def check_cuda_version(self) -> ValidationResult:
        """Check CUDA version."""
        print("Checking CUDA version...")

        cmd = ["nvidia-smi", "--query-gpu=compute_cap", "--format=csv,noheader"]
        code, stdout, stderr = self.run_command(cmd)

        # Also try nvcc
        nvcc_cmd = ["nvcc", "--version"]
        nvcc_code, nvcc_stdout, nvcc_stderr = self.run_command(nvcc_cmd)

        cuda_info = {}
        if code == 0:
            cuda_info["compute_capability"] = stdout.strip()

        if nvcc_code == 0:
            # Parse nvcc output for version
            for line in nvcc_stdout.split("\n"):
                if "release" in line.lower():
                    cuda_info["nvcc_version"] = line.strip()
                    break

        if cuda_info:
            return ValidationResult(
                name="CUDA",
                passed=True,
                message="CUDA available",
                details=cuda_info,
            )

        return ValidationResult(
            name="CUDA",
            passed=False,
            message="CUDA not detected",
            details={"error": "nvcc not found"},
        )

    def check_docker_installed(self) -> ValidationResult:
        """Check if Docker is installed."""
        print("Checking Docker installation...")

        cmd = ["docker", "--version"]
        code, stdout, stderr = self.run_command(cmd)

        if code != 0:
            return ValidationResult(
                name="Docker Installation",
                passed=False,
                message="Docker not found",
                details={"error": stderr},
            )

        return ValidationResult(
            name="Docker Installation",
            passed=True,
            message=stdout.strip(),
            details={"version": stdout.strip()},
        )

    def check_docker_gpu_support(self) -> ValidationResult:
        """Check if Docker has GPU support via --gpus flag."""
        print("Checking Docker GPU support...")

        # Try to run nvidia-smi in a container
        cmd = [
            "docker", "run", "--rm", "--gpus", "all",
            "nvidia/cuda:12.1.0-base-ubuntu22.04",
            "nvidia-smi", "--query-gpu=name", "--format=csv,noheader"
        ]

        code, stdout, stderr = self.run_command(cmd, timeout=120)

        if code != 0:
            # Check if it's a missing image vs GPU issue
            if "manifest unknown" in stderr.lower() or "not found" in stderr.lower():
                return ValidationResult(
                    name="Docker GPU Support",
                    passed=False,
                    message="CUDA base image not found - pulling may be needed",
                    details={"error": stderr, "suggestion": "Run: docker pull nvidia/cuda:12.1.0-base-ubuntu22.04"},
                )

            return ValidationResult(
                name="Docker GPU Support",
                passed=False,
                message="Docker GPU access failed",
                details={
                    "error": stderr,
                    "suggestion": "Install NVIDIA Container Toolkit: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
                },
            )

        return ValidationResult(
            name="Docker GPU Support",
            passed=True,
            message=f"GPU accessible in containers: {stdout.strip()}",
            details={"gpu_in_container": stdout.strip()},
        )

    def check_compose_file(self) -> ValidationResult:
        """Check docker-compose.yml for GPU configuration."""
        print("Checking docker-compose.yml...")

        if not self.compose_file.exists():
            return ValidationResult(
                name="Docker Compose File",
                passed=False,
                message=f"File not found: {self.compose_file}",
                details={"path": str(self.compose_file)},
            )

        if not YAML_AVAILABLE:
            return ValidationResult(
                name="Docker Compose File",
                passed=True,
                message="File exists (install PyYAML for detailed analysis)",
                details={"path": str(self.compose_file), "yaml_available": False},
            )

        try:
            with open(self.compose_file) as f:
                compose = yaml.safe_load(f)
        except Exception as e:
            return ValidationResult(
                name="Docker Compose File",
                passed=False,
                message=f"Failed to parse: {e}",
                details={"error": str(e)},
            )

        # Check for GPU configuration in services
        services = compose.get("services", {})
        gpu_services = []
        non_gpu_services = []

        for name, config in services.items():
            has_gpu = False

            # Check deploy.resources.reservations.devices
            deploy = config.get("deploy", {})
            resources = deploy.get("resources", {})
            reservations = resources.get("reservations", {})
            devices = reservations.get("devices", [])

            for device in devices:
                if device.get("driver") == "nvidia":
                    has_gpu = True
                    break

            # Also check runtime: nvidia (older method)
            if config.get("runtime") == "nvidia":
                has_gpu = True

            # Check environment for CUDA
            env = config.get("environment", {})
            if isinstance(env, list):
                env = dict(e.split("=", 1) for e in env if "=" in e)

            if "CUDA_VISIBLE_DEVICES" in env or "NVIDIA_VISIBLE_DEVICES" in env:
                has_gpu = True

            if has_gpu:
                gpu_services.append(name)
            else:
                non_gpu_services.append(name)

        # Expected GPU services for Ablage-System
        expected_gpu_services = ["backend", "worker", "celery-worker"]
        missing_gpu = [s for s in expected_gpu_services if s in non_gpu_services]

        passed = len(missing_gpu) == 0 and len(gpu_services) > 0

        return ValidationResult(
            name="Docker Compose GPU Config",
            passed=passed,
            message=f"GPU services: {gpu_services}" if passed else f"Missing GPU config: {missing_gpu}",
            details={
                "gpu_services": gpu_services,
                "non_gpu_services": non_gpu_services,
                "missing_expected": missing_gpu,
            },
        )

    def check_torch_cuda_in_container(self) -> ValidationResult:
        """Check if PyTorch can access GPU in the Ablage container."""
        print("Checking PyTorch CUDA in container...")

        # Try to run a quick PyTorch check in the backend container
        cmd = [
            "docker-compose", "run", "--rm", "backend",
            "python", "-c",
            "import torch; print(f'CUDA:{torch.cuda.is_available()},GPU:{torch.cuda.get_device_name(0) if torch.cuda.is_available() else None}')"
        ]

        code, stdout, stderr = self.run_command(cmd, timeout=120)

        if code != 0:
            return ValidationResult(
                name="PyTorch CUDA in Container",
                passed=False,
                message="Failed to check PyTorch CUDA",
                details={"error": stderr, "stdout": stdout},
            )

        # Parse output
        cuda_available = "CUDA:True" in stdout

        return ValidationResult(
            name="PyTorch CUDA in Container",
            passed=cuda_available,
            message=stdout.strip() if cuda_available else "CUDA not available in container",
            details={"output": stdout.strip()},
        )

    def validate_all(self, test_container: bool = False) -> ValidationReport:
        """Run all validation checks."""
        print("\n" + "=" * 60)
        print("DOCKER GPU VALIDATION FOR ABLAGE-SYSTEM")
        print("=" * 60 + "\n")

        # Run checks
        self.report.add(self.check_nvidia_driver())
        self.report.add(self.check_cuda_version())
        self.report.add(self.check_docker_installed())
        self.report.add(self.check_docker_gpu_support())
        self.report.add(self.check_compose_file())

        if test_container:
            self.report.add(self.check_torch_cuda_in_container())

        return self.report

    def print_report(self):
        """Print validation report."""
        print("\n" + "=" * 60)
        print("VALIDATION REPORT")
        print("=" * 60 + "\n")

        for result in self.report.results:
            status = "[PASS]" if result.passed else "[FAIL]"
            print(f"{status} {result.name}")
            print(f"       {result.message}")

            if result.details and not result.passed:
                for key, value in result.details.items():
                    if key == "suggestion":
                        print(f"       Suggestion: {value}")

            print()

        print("=" * 60)
        if self.report.overall_passed:
            print("[SUCCESS] All checks passed!")
        else:
            print("[FAILED] Some checks failed. Please fix the issues above.")
        print("=" * 60 + "\n")

    def export_json(self, filepath: Path):
        """Export report to JSON."""
        data = {
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "overall_passed": self.report.overall_passed,
            "results": [
                {
                    "name": r.name,
                    "passed": r.passed,
                    "message": r.message,
                    "details": r.details,
                }
                for r in self.report.results
            ],
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        print(f"Report exported to: {filepath}")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Validate Docker GPU configuration for Ablage-System"
    )
    parser.add_argument(
        "--compose-file", "-f",
        type=Path,
        default=Path("docker-compose.yml"),
        help="Path to docker-compose.yml (default: docker-compose.yml)"
    )
    parser.add_argument(
        "--test-container", "-t",
        action="store_true",
        help="Also test PyTorch CUDA in the actual container"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Export report to JSON file"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show verbose output"
    )
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    validator = DockerGPUValidator(compose_file=args.compose_file)
    validator.validate_all(test_container=args.test_container)
    validator.print_report()

    if args.output:
        validator.export_json(args.output)

    # Exit with error code if validation failed
    sys.exit(0 if validator.report.overall_passed else 1)


if __name__ == "__main__":
    main()
