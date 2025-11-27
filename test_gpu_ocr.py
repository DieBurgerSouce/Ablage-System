"""Test GPU-accelerated OCR performance."""

import time
import requests
from pathlib import Path
import torch
import sys

# Check GPU availability
def check_gpu():
    """Check if GPU is available and report details."""
    print("\n" + "="*60)
    print("GPU STATUS CHECK")
    print("="*60)

    if torch.cuda.is_available():
        print(f"[OK] CUDA available: {torch.version.cuda}")
        print(f"[OK] GPU: {torch.cuda.get_device_name(0)}")
        print(f"[OK] VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")

        # Test tensor operations on GPU
        test_tensor = torch.randn(1000, 1000).cuda()
        print(f"[OK] GPU tensor test successful")
        return True
    else:
        print("[ERROR] CUDA not available - running on CPU")
        print("Make sure PyTorch CUDA is installed:")
        print("pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121")
        return False

def test_api_with_gpu():
    """Test OCR API with GPU backend."""
    print("\n" + "="*60)
    print("API GPU OCR TEST")
    print("="*60)

    API_URL = "http://localhost:8000"

    # Check available backends
    response = requests.get(f"{API_URL}/ocr/backends")
    if response.status_code == 200:
        backends = response.json()
        print(f"Available backends: {backends.get('available_backends', [])}")

        has_gpu = "surya_gpu" in backends.get('available_backends', [])
        if has_gpu:
            print("[OK] GPU backend 'surya_gpu' is available!")
        else:
            print("[WARNING] GPU backend not available, using CPU")

    # Test with sample image
    test_file = Path("test_documents/test_umlauts.png")
    if not test_file.exists():
        print(f"[ERROR] Test file not found: {test_file}")
        return

    print(f"\nTesting OCR with: {test_file}")

    # Test CPU backend first
    print("\n1. Testing CPU backend (surya)...")
    start_time = time.time()

    with open(test_file, "rb") as f:
        files = {"file": (test_file.name, f, "image/png")}
        data = {
            "backend": "surya",
            "language": "de",
            "detect_layout": "true"
        }
        response = requests.post(f"{API_URL}/ocr/process", files=files, data=data)

    cpu_time = time.time() - start_time

    if response.status_code == 200:
        result = response.json()
        print(f"[OK] CPU processing time: {cpu_time:.2f}s")
        print(f"    Confidence: {result.get('confidence', 0):.1%}")
        print(f"    Text length: {len(result.get('text', ''))} chars")
    else:
        print(f"[ERROR] CPU test failed: {response.status_code}")

    # Test GPU backend if available
    print("\n2. Testing GPU backend (surya_gpu)...")
    start_time = time.time()

    with open(test_file, "rb") as f:
        files = {"file": (test_file.name, f, "image/png")}
        data = {
            "backend": "surya_gpu",  # Request GPU backend specifically
            "language": "de",
            "detect_layout": "true"
        }
        response = requests.post(f"{API_URL}/ocr/process", files=files, data=data)

    gpu_time = time.time() - start_time

    if response.status_code == 200:
        result = response.json()
        print(f"[OK] GPU processing time: {gpu_time:.2f}s")
        print(f"    Confidence: {result.get('confidence', 0):.1%}")
        print(f"    Text length: {len(result.get('text', ''))} chars")
        print(f"    Backend used: {result.get('backend', 'unknown')}")

        # Calculate speedup
        if cpu_time > 0:
            speedup = cpu_time / gpu_time
            print(f"\n[PERFORMANCE] GPU speedup: {speedup:.1f}x faster than CPU")
    else:
        print(f"[WARNING] GPU backend not available, falling back to CPU")
        # Try auto selection
        print("\n3. Testing auto backend selection...")
        with open(test_file, "rb") as f:
            files = {"file": (test_file.name, f, "image/png")}
            data = {
                "backend": "auto",  # Let system choose best backend
                "language": "de",
                "detect_layout": "true"
            }
            response = requests.post(f"{API_URL}/ocr/process", files=files, data=data)

        if response.status_code == 200:
            result = response.json()
            print(f"[OK] Auto selected backend: {result.get('backend', 'unknown')}")

def test_batch_performance():
    """Test batch processing performance."""
    print("\n" + "="*60)
    print("BATCH PROCESSING TEST")
    print("="*60)

    API_URL = "http://localhost:8000"

    test_files = [
        Path("test_documents/test_umlauts.png"),
        Path("test_documents/test_invoice.png"),
    ]

    existing_files = [f for f in test_files if f.exists()]

    if not existing_files:
        print("[ERROR] No test files found")
        return

    print(f"Testing batch processing with {len(existing_files)} files...")

    # Prepare files
    files_data = []
    for file_path in existing_files:
        with open(file_path, "rb") as f:
            files_data.append(
                ("files", (file_path.name, f.read(), "image/png"))
            )

    # Test with GPU backend
    data = {
        "backend": "surya_gpu",  # Try GPU backend
        "language": "de"
    }

    start_time = time.time()
    response = requests.post(f"{API_URL}/ocr/batch", files=files_data, data=data)
    batch_time = time.time() - start_time

    if response.status_code == 200:
        results = response.json()
        print(f"[OK] Batch processed in {batch_time:.2f}s")
        print(f"    Documents: {results.get('total', 0)}")
        print(f"    Successful: {results.get('successful', 0)}")
        print(f"    Avg time per doc: {batch_time/len(existing_files):.2f}s")
    else:
        print(f"[ERROR] Batch processing failed: {response.status_code}")

def main():
    """Run all GPU tests."""
    print("="*70)
    print("ABLAGE-SYSTEM GPU OCR TEST")
    print("="*70)

    # Check GPU first
    gpu_available = check_gpu()

    if not gpu_available:
        print("\n[WARNING] GPU not detected. Tests will run on CPU only.")
        print("To enable GPU acceleration:")
        print("1. Ensure NVIDIA drivers are installed")
        print("2. Install CUDA toolkit")
        print("3. Install PyTorch with CUDA support:")
        print("   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121")

    # Test API
    test_api_with_gpu()

    # Test batch processing
    test_batch_performance()

    print("\n" + "="*70)
    print("[COMPLETE] GPU OCR tests finished")
    print("="*70)

if __name__ == "__main__":
    main()