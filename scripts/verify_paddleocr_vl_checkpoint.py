#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Checkpoint Verification Script for PaddleOCR-VL Evaluation.

This script verifies that the isolated test environment is ready:
1. All tests pass
2. Docker container can be built and runs with GPU access
3. Experimental Agent initializes correctly

Usage:
    python scripts/verify_paddleocr_vl_checkpoint.py
"""

import subprocess
import sys
import json
from pathlib import Path
from typing import Dict, Any, List, Tuple


def run_command(cmd: List[str], cwd: Path = None) -> Tuple[int, str, str]:
    """Run a command and return exit code, stdout, stderr."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out after 300 seconds"
    except Exception as e:
        return -1, "", str(e)


def check_tests() -> Dict[str, Any]:
    """Verify all tests pass."""
    print("=" * 60)
    print("CHECKPOINT 1: Verifying Tests")
    print("=" * 60)

    results = {
        "passed": False,
        "tests": []
    }

    # Test files to check
    test_files = [
        "tests/unit/agents/ocr/test_paddle_ocr_vl_agent_experimental.py",
        "tests/unit/services/test_benchmark_runner.py",
        "tests/unit/services/evaluation/test_availability_checker.py"
    ]

    all_passed = True

    for test_file in test_files:
        print(f"\nRunning: {test_file}")
        exit_code, stdout, stderr = run_command([
            "python", "-m", "pytest", test_file, "-v", "--tb=short"
        ])

        test_result = {
            "file": test_file,
            "passed": exit_code == 0,
            "exit_code": exit_code
        }

        if exit_code == 0:
            print(f"✅ PASSED: {test_file}")
        else:
            print(f"❌ FAILED: {test_file}")
            print(f"   Exit code: {exit_code}")
            if stderr:
                print(f"   Error: {stderr[:500]}")
            all_passed = False

        results["tests"].append(test_result)

    results["passed"] = all_passed

    if all_passed:
        print("\n✅ All tests passed!")
    else:
        print("\n❌ Some tests failed!")

    return results


def check_docker_build() -> Dict[str, Any]:
    """Verify Docker container can be built."""
    print("\n" + "=" * 60)
    print("CHECKPOINT 2: Verifying Docker Container Build")
    print("=" * 60)

    results = {
        "passed": False,
        "build_successful": False,
        "dockerfile_exists": False
    }

    # Check if Dockerfile exists
    dockerfile_path = Path("docker/Dockerfile.paddleocr-vl-test")
    if not dockerfile_path.exists():
        print(f"❌ Dockerfile not found: {dockerfile_path}")
        return results

    results["dockerfile_exists"] = True
    print(f"✅ Dockerfile exists: {dockerfile_path}")

    # Try to build the Docker image
    print("\nAttempting to build Docker image...")
    print("Note: This may take several minutes on first build...")

    exit_code, stdout, stderr = run_command([
        "docker", "build",
        "-f", str(dockerfile_path),
        "-t", "ablage-paddleocr-vl-test:latest",
        "."
    ])

    if exit_code == 0:
        print("✅ Docker image built successfully!")
        results["build_successful"] = True
        results["passed"] = True
    else:
        print("❌ Docker build failed!")
        print(f"   Exit code: {exit_code}")
        if stderr:
            print(f"   Error: {stderr[:1000]}")

    return results


def check_gpu_access() -> Dict[str, Any]:
    """Verify GPU access in Docker container."""
    print("\n" + "=" * 60)
    print("CHECKPOINT 3: Verifying GPU Access")
    print("=" * 60)

    results = {
        "passed": False,
        "nvidia_smi_available": False,
        "cuda_available": False,
        "gpu_info": {}
    }

    # Check if nvidia-smi is available on host
    print("\nChecking nvidia-smi on host...")
    exit_code, stdout, stderr = run_command(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"])

    if exit_code == 0:
        print("✅ nvidia-smi available on host")
        results["nvidia_smi_available"] = True
        gpu_info = stdout.strip()
        print(f"   GPU: {gpu_info}")
        results["gpu_info"]["host"] = gpu_info
    else:
        print("❌ nvidia-smi not available on host")
        print("   GPU access cannot be verified without nvidia-smi")
        return results

    # Try to run GPU verification in Docker container
    print("\nVerifying GPU access in Docker container...")
    print("Note: This requires the Docker image to be built...")

    exit_code, stdout, stderr = run_command([
        "docker", "run", "--rm", "--gpus", "all",
        "ablage-paddleocr-vl-test:latest",
        "/app/verify_gpu.sh"
    ])

    if exit_code == 0:
        print("✅ GPU accessible in Docker container!")
        results["cuda_available"] = True
        results["passed"] = True
        print("\nGPU Verification Output:")
        print(stdout[:1000])
    else:
        print("❌ GPU not accessible in Docker container!")
        print(f"   Exit code: {exit_code}")
        if stderr:
            print(f"   Error: {stderr[:500]}")
        print("\nNote: This may fail if:")
        print("  - Docker image is not built yet")
        print("  - nvidia-docker runtime is not installed")
        print("  - GPU is not available")

    return results


def check_experimental_agent() -> Dict[str, Any]:
    """Verify Experimental Agent initializes correctly."""
    print("\n" + "=" * 60)
    print("CHECKPOINT 4: Verifying Experimental Agent")
    print("=" * 60)

    results = {
        "passed": False,
        "agent_file_exists": False,
        "experimental_flag_set": False,
        "initialization_works": False
    }

    # Check if agent file exists
    agent_path = Path("app/agents/ocr/paddle_ocr_vl_agent_experimental.py")
    if not agent_path.exists():
        print(f"❌ Agent file not found: {agent_path}")
        return results

    results["agent_file_exists"] = True
    print(f"✅ Agent file exists: {agent_path}")

    # Check if experimental flag is set
    agent_code = agent_path.read_text(encoding="utf-8")
    if "experimental: bool = True" in agent_code or "experimental = True" in agent_code:
        print("✅ Experimental flag is set in agent")
        results["experimental_flag_set"] = True
    else:
        print("❌ Experimental flag not found in agent")
        return results

    # Try to import and initialize the agent
    print("\nAttempting to initialize agent...")
    test_script = """
import sys
sys.path.insert(0, '.')
try:
    from app.agents.ocr.paddle_ocr_vl_agent_experimental import PaddleOCRVLAgentExperimental
    agent = PaddleOCRVLAgentExperimental()
    status = agent.get_status()
    print(f"Agent initialized: {status['name']}")
    print(f"Experimental: {status['experimental']}")
    print(f"GPU required: {status['gpu_required']}")
    print(f"VRAM GB: {status['vram_gb']}")
    sys.exit(0)
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
"""

    exit_code, stdout, stderr = run_command(["python", "-c", test_script])

    if exit_code == 0:
        print("✅ Agent initialized successfully!")
        results["initialization_works"] = True
        results["passed"] = True
        print(f"\n{stdout}")
    else:
        print("❌ Agent initialization failed!")
        print(f"   Exit code: {exit_code}")
        if stderr:
            print(f"   Error: {stderr[:500]}")

    return results


def generate_report(results: Dict[str, Dict[str, Any]]) -> None:
    """Generate checkpoint verification report."""
    print("\n" + "=" * 60)
    print("CHECKPOINT VERIFICATION REPORT")
    print("=" * 60)

    all_passed = all(r["passed"] for r in results.values())

    print("\nSummary:")
    print(f"  1. Tests: {'✅ PASSED' if results['tests']['passed'] else '❌ FAILED'}")
    print(f"  2. Docker Build: {'✅ PASSED' if results['docker']['passed'] else '❌ FAILED'}")
    print(f"  3. GPU Access: {'✅ PASSED' if results['gpu']['passed'] else '❌ FAILED'}")
    print(f"  4. Experimental Agent: {'✅ PASSED' if results['agent']['passed'] else '❌ FAILED'}")

    print("\n" + "=" * 60)
    if all_passed:
        print("✅ CHECKPOINT PASSED: Isolated test environment is ready!")
        print("=" * 60)
        print("\nNext Steps:")
        print("  - Proceed to Phase 5: Test-Dataset and Ground Truth")
        print("  - Run: python scripts/verify_dataset_manifest.py")
    else:
        print("❌ CHECKPOINT FAILED: Some checks did not pass")
        print("=" * 60)
        print("\nRequired Actions:")
        if not results['tests']['passed']:
            print("  - Fix failing tests")
        if not results['docker']['passed']:
            print("  - Fix Docker build issues")
        if not results['gpu']['passed']:
            print("  - Verify GPU access and nvidia-docker runtime")
        if not results['agent']['passed']:
            print("  - Fix agent initialization issues")

    # Save report to file
    report_path = Path("docs/OCR/PADDLEOCR_VL_CHECKPOINT_4_REPORT.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# PaddleOCR-VL Evaluation - Checkpoint 4 Report\n\n")
        f.write("## Isolierte Testumgebung Bereit\n\n")
        f.write(f"**Status:** {'✅ PASSED' if all_passed else '❌ FAILED'}\n\n")
        f.write("### Verification Results\n\n")

        for check_name, check_results in results.items():
            f.write(f"#### {check_name.title()}\n\n")
            f.write(f"- **Passed:** {check_results['passed']}\n")
            for key, value in check_results.items():
                if key != "passed":
                    f.write(f"- **{key}:** {value}\n")
            f.write("\n")

        f.write("### Next Steps\n\n")
        if all_passed:
            f.write("- ✅ Proceed to Phase 5: Test-Dataset and Ground Truth\n")
            f.write("- Run dataset verification: `python scripts/verify_dataset_manifest.py`\n")
        else:
            f.write("- ❌ Fix failing checks before proceeding\n")
            f.write("- Re-run verification: `python scripts/verify_paddleocr_vl_checkpoint.py`\n")

    print(f"\nReport saved to: {report_path}")


def main():
    """Main checkpoint verification function."""
    print("PaddleOCR-VL Evaluation - Checkpoint 4 Verification")
    print("Isolierte Testumgebung Bereit")
    print()

    results = {
        "tests": check_tests(),
        "docker": check_docker_build(),
        "gpu": check_gpu_access(),
        "agent": check_experimental_agent()
    }

    generate_report(results)

    # Exit with appropriate code
    all_passed = all(r["passed"] for r in results.values())
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
