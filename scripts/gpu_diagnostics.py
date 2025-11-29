#!/usr/bin/env python
"""
GPU Health Check for Ablage-System OCR Backends.

Validates GPU environment before running GPU tests:
- CUDA availability and version
- GPU name (RTX 4080 verification)
- VRAM total and free
- cuDNN status
- TensorFloat-32 support
- BitsAndBytes availability (for 4-bit quantization)
- Flash Attention availability

Run this script before GPU backend testing:
    python scripts/gpu_diagnostics.py
"""

import sys
from dataclasses import dataclass
from typing import Optional


@dataclass
class GPUCheckResult:
    """Result of a single GPU health check."""
    name: str
    passed: bool
    value: str
    required: bool = True
    message: str = ""


def check_python_version() -> GPUCheckResult:
    """Check Python version is 3.11+."""
    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"
    passed = version.major == 3 and version.minor >= 11
    return GPUCheckResult(
        name="Python Version",
        passed=passed,
        value=version_str,
        required=True,
        message="Python 3.11+ required for optimal performance"
    )


def check_torch_available() -> GPUCheckResult:
    """Check if PyTorch is installed."""
    try:
        import torch
        return GPUCheckResult(
            name="PyTorch",
            passed=True,
            value=torch.__version__,
            required=True
        )
    except ImportError:
        return GPUCheckResult(
            name="PyTorch",
            passed=False,
            value="Not installed",
            required=True,
            message="Install: pip install torch"
        )


def check_cuda_available() -> GPUCheckResult:
    """Check if CUDA is available."""
    try:
        import torch
        available = torch.cuda.is_available()
        if available:
            cuda_version = torch.version.cuda or "Unknown"
            return GPUCheckResult(
                name="CUDA",
                passed=True,
                value=cuda_version,
                required=True
            )
        else:
            return GPUCheckResult(
                name="CUDA",
                passed=False,
                value="Not available",
                required=True,
                message="Check NVIDIA drivers: nvidia-smi"
            )
    except Exception as e:
        return GPUCheckResult(
            name="CUDA",
            passed=False,
            value=f"Error: {e}",
            required=True
        )


def check_gpu_name() -> GPUCheckResult:
    """Check GPU name and verify RTX 4080."""
    try:
        import torch
        if not torch.cuda.is_available():
            return GPUCheckResult(
                name="GPU Name",
                passed=False,
                value="No GPU",
                required=True
            )

        gpu_name = torch.cuda.get_device_name(0)
        is_rtx_4080 = "4080" in gpu_name
        return GPUCheckResult(
            name="GPU Name",
            passed=is_rtx_4080,
            value=gpu_name,
            required=False,  # Other GPUs may work
            message="" if is_rtx_4080 else "Expected RTX 4080, may work with other GPUs"
        )
    except Exception as e:
        return GPUCheckResult(
            name="GPU Name",
            passed=False,
            value=f"Error: {e}",
            required=True
        )


def check_vram() -> GPUCheckResult:
    """Check VRAM total and availability."""
    try:
        import torch
        if not torch.cuda.is_available():
            return GPUCheckResult(
                name="VRAM",
                passed=False,
                value="No GPU",
                required=True
            )

        props = torch.cuda.get_device_properties(0)
        total_gb = props.total_memory / (1024**3)
        allocated = torch.cuda.memory_allocated(0) / (1024**3)
        free_gb = total_gb - allocated

        # Need at least 12GB for DeepSeek
        has_enough = total_gb >= 12

        return GPUCheckResult(
            name="VRAM",
            passed=has_enough,
            value=f"{total_gb:.1f}GB total, {free_gb:.1f}GB free",
            required=True,
            message="" if has_enough else "DeepSeek requires 12GB+ VRAM"
        )
    except Exception as e:
        return GPUCheckResult(
            name="VRAM",
            passed=False,
            value=f"Error: {e}",
            required=True
        )


def check_cudnn() -> GPUCheckResult:
    """Check cuDNN availability and version."""
    try:
        import torch
        cudnn_available = torch.backends.cudnn.is_available()
        if cudnn_available:
            cudnn_version = torch.backends.cudnn.version()
            return GPUCheckResult(
                name="cuDNN",
                passed=True,
                value=str(cudnn_version),
                required=True
            )
        else:
            return GPUCheckResult(
                name="cuDNN",
                passed=False,
                value="Not available",
                required=True,
                message="Install cuDNN for optimal GPU performance"
            )
    except Exception as e:
        return GPUCheckResult(
            name="cuDNN",
            passed=False,
            value=f"Error: {e}",
            required=True
        )


def check_tf32() -> GPUCheckResult:
    """Check TensorFloat-32 support (RTX 30xx/40xx optimization)."""
    try:
        import torch
        if not torch.cuda.is_available():
            return GPUCheckResult(
                name="TF32 Support",
                passed=False,
                value="No GPU",
                required=False
            )

        # Check if TF32 is supported (Ampere+ GPUs)
        props = torch.cuda.get_device_properties(0)
        major, minor = props.major, props.minor

        # TF32 requires compute capability 8.0+ (Ampere)
        tf32_supported = major >= 8

        if tf32_supported:
            # Check current settings
            matmul_tf32 = torch.backends.cuda.matmul.allow_tf32
            cudnn_tf32 = torch.backends.cudnn.allow_tf32
            return GPUCheckResult(
                name="TF32 Support",
                passed=True,
                value=f"Supported (compute {major}.{minor}), matmul={matmul_tf32}, cudnn={cudnn_tf32}",
                required=False
            )
        else:
            return GPUCheckResult(
                name="TF32 Support",
                passed=False,
                value=f"Not supported (compute {major}.{minor}, needs 8.0+)",
                required=False,
                message="TF32 requires Ampere+ GPU (RTX 30xx/40xx)"
            )
    except Exception as e:
        return GPUCheckResult(
            name="TF32 Support",
            passed=False,
            value=f"Error: {e}",
            required=False
        )


def check_bitsandbytes() -> GPUCheckResult:
    """Check BitsAndBytes for 4-bit quantization."""
    try:
        import bitsandbytes as bnb
        # Try to verify CUDA is accessible to bnb
        try:
            # This will fail if CUDA libs not found
            bnb.cuda_setup.main()
            return GPUCheckResult(
                name="BitsAndBytes",
                passed=True,
                value=f"v{bnb.__version__}",
                required=True,
                message="4-bit quantization available for DeepSeek"
            )
        except Exception as e:
            return GPUCheckResult(
                name="BitsAndBytes",
                passed=False,
                value=f"CUDA setup failed: {e}",
                required=True,
                message="BitsAndBytes CUDA integration issue - run in WSL2/Linux"
            )
    except ImportError:
        return GPUCheckResult(
            name="BitsAndBytes",
            passed=False,
            value="Not installed",
            required=True,
            message="Install: pip install bitsandbytes (Linux/WSL2 recommended)"
        )


def check_flash_attention() -> GPUCheckResult:
    """Check Flash Attention 2 availability."""
    try:
        from flash_attn import flash_attn_func
        return GPUCheckResult(
            name="Flash Attention 2",
            passed=True,
            value="Available",
            required=False,
            message="Enables faster attention for large models"
        )
    except ImportError:
        return GPUCheckResult(
            name="Flash Attention 2",
            passed=False,
            value="Not installed",
            required=False,
            message="Optional: pip install flash-attn (improves speed)"
        )


def check_transformers() -> GPUCheckResult:
    """Check Transformers library version."""
    try:
        import transformers
        version = transformers.__version__
        # Need 4.36+ for GOT-OCR
        major, minor = version.split(".")[:2]
        passed = int(major) >= 4 and int(minor) >= 36
        return GPUCheckResult(
            name="Transformers",
            passed=passed,
            value=version,
            required=True,
            message="" if passed else "Need transformers >= 4.36 for GOT-OCR"
        )
    except ImportError:
        return GPUCheckResult(
            name="Transformers",
            passed=False,
            value="Not installed",
            required=True,
            message="Install: pip install transformers>=4.36.0"
        )


def check_accelerate() -> GPUCheckResult:
    """Check Accelerate library for model loading."""
    try:
        import accelerate
        return GPUCheckResult(
            name="Accelerate",
            passed=True,
            value=accelerate.__version__,
            required=True
        )
    except ImportError:
        return GPUCheckResult(
            name="Accelerate",
            passed=False,
            value="Not installed",
            required=True,
            message="Install: pip install accelerate"
        )


def check_surya() -> GPUCheckResult:
    """Check Surya OCR library."""
    try:
        import surya
        version = getattr(surya, "__version__", "unknown")
        return GPUCheckResult(
            name="Surya OCR",
            passed=True,
            value=version,
            required=True
        )
    except ImportError:
        return GPUCheckResult(
            name="Surya OCR",
            passed=False,
            value="Not installed",
            required=True,
            message="Install: pip install surya-ocr"
        )


def run_all_checks() -> list[GPUCheckResult]:
    """Run all GPU health checks."""
    checks = [
        check_python_version(),
        check_torch_available(),
        check_cuda_available(),
        check_gpu_name(),
        check_vram(),
        check_cudnn(),
        check_tf32(),
        check_bitsandbytes(),
        check_flash_attention(),
        check_transformers(),
        check_accelerate(),
        check_surya(),
    ]
    return checks


def print_results(results: list[GPUCheckResult]) -> bool:
    """Print check results and return overall status."""
    print("\n" + "=" * 60)
    print("GPU DIAGNOSTICS FOR ABLAGE-SYSTEM OCR BACKENDS")
    print("=" * 60 + "\n")

    all_required_passed = True

    for result in results:
        status = "[OK]" if result.passed else "[FAIL]" if result.required else "[WARN]"
        req_marker = "*" if result.required else " "

        print(f"{status} {result.name}{req_marker}: {result.value}")
        if result.message:
            print(f"     -> {result.message}")

        if result.required and not result.passed:
            all_required_passed = False

    print("\n" + "-" * 60)
    print("* = Required for full GPU backend testing")
    print("-" * 60)

    if all_required_passed:
        print("\n[SUCCESS] All required checks passed!")
        print("GPU backends are ready for testing.\n")
    else:
        print("\n[WARNING] Some required checks failed.")
        print("Fix the issues above before running GPU tests.\n")
        print("Tip: Run GPU tests in WSL2 or Docker for best compatibility.\n")

    return all_required_passed


def main():
    """Main entry point."""
    results = run_all_checks()
    success = print_results(results)

    # Return appropriate exit code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
