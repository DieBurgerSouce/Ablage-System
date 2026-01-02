# -*- coding: utf-8 -*-
"""
Isolated test script for PaddleOCR-VL 0.9B evaluation.

This script can be run locally (outside Docker) for development,
or inside Docker container for isolated testing.

Usage:
    # Local (requires GPU and dependencies)
    python scripts/test_paddleocr_vl_isolated.py --image path/to/image.png

    # Docker
    docker build -f docker/Dockerfile.paddleocr-vl-test -t paddleocr-vl-test .
    docker run --gpus all -v /path/to/images:/app/test_images -v /path/to/results:/app/results paddleocr-vl-test
"""
import argparse
import json
import sys
import time
import warnings
from pathlib import Path
from typing import Dict, Any, Optional

warnings.filterwarnings("ignore")

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import after path setup
try:
    import torch
    from PIL import Image
    import numpy as np
except ImportError as e:
    print(f"❌ Missing dependencies: {e}")
    print("   Install: pip install torch pillow numpy")
    sys.exit(1)


def get_vram_usage() -> Dict[str, float]:
    """Get current VRAM usage in GB."""
    try:
        if torch.cuda.is_available():
            allocated = torch.cuda.memory_allocated(0) / 1024**3
            reserved = torch.cuda.memory_reserved(0) / 1024**3
            total = torch.cuda.get_device_properties(0).total_memory / 1024**3
            return {
                "allocated_gb": round(allocated, 2),
                "reserved_gb": round(reserved, 2),
                "total_gb": round(total, 2),
                "usage_percent": round((reserved / total) * 100, 1)
            }
    except Exception:
        pass
    return {"error": "VRAM info not available"}


def test_paddleocr_vl(image_path: Path) -> Dict[str, Any]:
    """Test PaddleOCR-VL 0.9B on a single image.

    Args:
        image_path: Path to test image

    Returns:
        Dictionary with test results
    """
    result = {
        "backend": "paddleocr-vl-0.9b",
        "image_path": str(image_path),
        "success": False,
        "error": None,
        "processing_time_s": 0.0,
        "vram_before": {},
        "vram_after": {},
        "vram_peak_gb": 0.0,
        "text": "",
        "text_length": 0,
        "confidence": 0.0,
        "has_umlauts": False,
        "umlaut_count": 0
    }

    try:
        # Check GPU availability
        if not torch.cuda.is_available():
            result["error"] = "CUDA not available - PaddleOCR-VL requires GPU"
            return result

        print(f"   GPU: {torch.cuda.get_device_name(0)}")
        print(f"   CUDA: {torch.version.cuda}")

        # Get VRAM before
        result["vram_before"] = get_vram_usage()
        print(f"   VRAM before: {result['vram_before'].get('reserved_gb', 0):.2f} GB")

        start_time = time.perf_counter()

        # Try to import PaddleOCR-VL
        # Note: API might differ from PP-OCRv5
        try:
            # Option 1: Direct import if available
            from paddleocr_vl import PaddleOCRVL
            ocr = PaddleOCRVL(
                model_name='PaddleOCR-VL-0.9B',
                device='cuda',
                language='german'
            )
            print("   Using PaddleOCR-VL direct import")
        except ImportError:
            try:
                # Option 2: Via paddleocr with VL flag
                from paddleocr import PaddleOCR
                ocr = PaddleOCR(
                    use_gpu=True,
                    lang='german',
                    use_vl=True,  # Enable VL mode if available
                    model_dir=None  # Auto-download
                )
                print("   Using PaddleOCR with VL flag")
            except Exception as e:
                result["error"] = f"Failed to import PaddleOCR-VL: {e}"
                return result

        # Load image
        img = Image.open(image_path).convert('RGB')
        img_np = np.array(img)

        print(f"   Image size: {img.size[0]}x{img.size[1]}")

        # Process with PaddleOCR-VL
        # API might return structured output (JSON/Markdown)
        ocr_result = ocr.process(img_np) if hasattr(ocr, 'process') else ocr.ocr(img_np)

        # Extract text based on API format
        # PaddleOCR-VL might return structured output
        if isinstance(ocr_result, dict):
            # Structured output format
            text = ocr_result.get('text', '')
            if not text and 'pages' in ocr_result:
                # Multi-page document
                pages_text = []
                for page in ocr_result['pages']:
                    pages_text.append(page.get('text', ''))
                text = '\n'.join(pages_text)

            confidence = ocr_result.get('confidence', 0.0)
            if not confidence and 'pages' in ocr_result:
                confidences = [p.get('confidence', 0.0) for p in ocr_result['pages']]
                confidence = sum(confidences) / len(confidences) if confidences else 0.0
        elif isinstance(ocr_result, list):
            # List format (similar to PP-OCRv5)
            text_lines = []
            confidences = []
            for line in ocr_result:
                if isinstance(line, (list, tuple)) and len(line) >= 2:
                    text_data = line[1]
                    if isinstance(text_data, (list, tuple)) and len(text_data) >= 2:
                        text_lines.append(str(text_data[0]))
                        confidences.append(float(text_data[1]))
            text = '\n'.join(text_lines)
            confidence = sum(confidences) / len(confidences) if confidences else 0.0
        else:
            text = str(ocr_result)
            confidence = 0.0

        processing_time = time.perf_counter() - start_time

        # Get VRAM after
        result["vram_after"] = get_vram_usage()
        result["vram_peak_gb"] = result["vram_after"].get("reserved_gb", 0.0)

        # Check for German umlauts
        umlauts = ['ä', 'ö', 'ü', 'ß', 'Ä', 'Ö', 'Ü']
        umlaut_count = sum(1 for char in text if char in umlauts)

        result.update({
            "success": True,
            "processing_time_s": round(processing_time, 2),
            "text": text,
            "text_length": len(text),
            "confidence": round(confidence, 3),
            "has_umlauts": umlaut_count > 0,
            "umlaut_count": umlaut_count
        })

        print(f"   ✅ Success: {processing_time:.2f}s, {len(text)} chars, {confidence:.1%} conf")
        print(f"   Umlauts: {umlaut_count}")
        print(f"   VRAM peak: {result['vram_peak_gb']:.2f} GB")

    except Exception as e:
        result["error"] = str(e)
        result["vram_after"] = get_vram_usage()
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()

    return result


def main():
    """Main test function."""
    parser = argparse.ArgumentParser(description="Test PaddleOCR-VL 0.9B")
    parser.add_argument(
        "--image",
        type=Path,
        help="Path to test image"
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=PROJECT_ROOT / "tests/fixtures/paddleocr_vl_evaluation",
        help="Path to evaluation dataset directory"
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Path to output results JSON file"
    )
    args = parser.parse_args()

    print("="*60)
    print("PADDLEOCR-VL 0.9B ISOLATED TEST")
    print("="*60)

    # Check GPU
    if not torch.cuda.is_available():
        print("❌ CUDA not available - PaddleOCR-VL requires GPU")
        sys.exit(1)

    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"CUDA: {torch.version.cuda}")
    print()

    # Determine test images
    if args.image:
        test_images = [args.image]
    else:
        # Load from dataset manifest
        manifest_path = args.dataset / "dataset_manifest.json"
        if manifest_path.exists():
            with open(manifest_path) as f:
                manifest = json.load(f)
            # Use first 3 documents for basic functionality test
            test_images = []
            for doc in manifest["documents"][:3]:
                img_path = PROJECT_ROOT / doc["source"]
                if img_path.exists():
                    test_images.append(img_path)
        else:
            print(f"⚠️  Dataset manifest not found: {manifest_path}")
            print("   Use --image to specify a test image")
            sys.exit(1)

    if not test_images:
        print("❌ No test images found")
        sys.exit(1)

    print(f"Testing {len(test_images)} image(s)")
    print()

    results = []
    for i, image_path in enumerate(test_images, 1):
        print(f"[{i}/{len(test_images)}] {image_path.name}")
        result = test_paddleocr_vl(image_path)
        results.append(result)
        print()

    # Save results
    output_file = args.output or (PROJECT_ROOT / "data/benchmarks/paddleocr_vl_basic_test.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "test_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "backend": "paddleocr-vl-0.9b",
            "test_images_count": len(test_images),
            "results": results,
            "summary": {
                "successful": sum(1 for r in results if r["success"]),
                "failed": sum(1 for r in results if not r["success"]),
                "avg_processing_time": sum(r["processing_time_s"] for r in results) / len(results) if results else 0,
                "avg_vram_gb": sum(r["vram_peak_gb"] for r in results) / len(results) if results else 0,
                "total_umlauts": sum(r["umlaut_count"] for r in results)
            }
        }, f, indent=2, ensure_ascii=False)

    print("="*60)
    print("TEST SUMMARY")
    print("="*60)
    successful = sum(1 for r in results if r["success"])
    print(f"Successful: {successful}/{len(results)}")
    if successful > 0:
        avg_time = sum(r["processing_time_s"] for r in results if r["success"]) / successful
        avg_vram = sum(r["vram_peak_gb"] for r in results if r["success"]) / successful
        total_umlauts = sum(r["umlaut_count"] for r in results if r["success"])
        print(f"Avg processing time: {avg_time:.2f}s")
        print(f"Avg VRAM usage: {avg_vram:.2f} GB")
        print(f"Total umlauts detected: {total_umlauts}")

        # Go/No-Go decision
        print()
        print("="*60)
        print("GO/NO-GO DECISION")
        print("="*60)
        if avg_vram < 14.0 and successful == len(results):
            print("✅ GO: VRAM <14GB and all tests successful")
            print("   → Proceed to Benchmark Phase")
        else:
            print("❌ NO-GO:")
            if avg_vram >= 14.0:
                print(f"   - VRAM usage too high: {avg_vram:.2f} GB (target: <14GB)")
            if successful < len(results):
                print(f"   - {len(results) - successful} test(s) failed")
            print("   → Stop evaluation, document findings")
    print(f"\nResults saved to: {output_file}")
    print("="*60)


if __name__ == "__main__":
    main()

