"""Advanced API tests for OCR system - PDFs and performance testing."""

import requests
import time
from pathlib import Path
import json
from typing import Dict, Any

# API configuration
API_URL = "http://localhost:8000"

def test_single_image(file_path: Path) -> Dict[str, Any]:
    """Test single image OCR."""
    print(f"\n[IMAGE] Testing: {file_path.name}")
    print("-" * 60)

    if not file_path.exists():
        print(f"[ERROR] File not found: {file_path}")
        return {}

    start_time = time.time()

    with open(file_path, "rb") as f:
        files = {"file": (file_path.name, f, "image/png")}
        data = {
            "backend": "surya",
            "language": "de",
            "detect_layout": "true"
        }

        response = requests.post(f"{API_URL}/ocr/process", files=files, data=data)

    processing_time = time.time() - start_time

    if response.status_code == 200:
        result = response.json()
        print(f"[OK] SUCCESS in {processing_time:.2f}s")
        print(f"   Confidence: {result.get('confidence', 0):.1%}")
        print(f"   Text length: {len(result.get('text', ''))} chars")
        print(f"   Backend: {result.get('backend', 'unknown')}")

        # Check for German characters
        text = result.get('text', '')
        german_chars = ['ä', 'ö', 'ü', 'Ä', 'Ö', 'Ü', 'ß']
        found_chars = [char for char in german_chars if char in text]
        if found_chars:
            print(f"   German chars: {', '.join(found_chars)}")

        return {
            "success": True,
            "time": processing_time,
            "confidence": result.get('confidence', 0),
            "text_length": len(text),
            "file": file_path.name
        }
    else:
        print(f"[ERROR] FAILED ({response.status_code}): {response.text[:200]}")
        return {
            "success": False,
            "time": processing_time,
            "error": response.text[:200],
            "file": file_path.name
        }

def test_pdf_document(pdf_path: Path) -> Dict[str, Any]:
    """Test PDF OCR processing."""
    print(f"\n[PDF] Testing PDF: {pdf_path.name}")
    print("-" * 60)

    if not pdf_path.exists():
        print(f"[ERROR] PDF not found: {pdf_path}")
        return {}

    start_time = time.time()

    with open(pdf_path, "rb") as f:
        files = {"file": (pdf_path.name, f, "application/pdf")}
        data = {
            "backend": "surya",
            "language": "de",
            "detect_layout": "false"
        }

        response = requests.post(f"{API_URL}/ocr/process", files=files, data=data)

    processing_time = time.time() - start_time

    if response.status_code == 200:
        result = response.json()
        print(f"[OK] PDF processed in {processing_time:.2f}s")
        print(f"   Pages: {result.get('page_count', 0)}")
        print(f"   Total text: {len(result.get('text', ''))} chars")
        print(f"   Confidence: {result.get('confidence', 0):.1%}")
        return {
            "success": True,
            "time": processing_time,
            "pages": result.get('page_count', 0),
            "text_length": len(result.get('text', '')),
            "file": pdf_path.name
        }
    else:
        print(f"[ERROR] PDF failed ({response.status_code}): {response.text[:200]}")
        return {
            "success": False,
            "time": processing_time,
            "error": response.text[:200],
            "file": pdf_path.name
        }

def test_batch_endpoint():
    """Test batch processing endpoint."""
    print("\n[BATCH] Testing Batch Processing")
    print("-" * 60)

    # Prepare multiple test images
    test_files = [
        Path("test_documents/test_umlauts.png"),
        Path("test_documents/test_invoice.png"),
    ]

    existing_files = [f for f in test_files if f.exists()]

    if not existing_files:
        print("[ERROR] No test files found for batch processing")
        return {}

    print(f"Batch processing {len(existing_files)} files...")

    # Open all files and create multipart data
    files_data = []
    for file_path in existing_files:
        with open(file_path, "rb") as f:
            files_data.append(
                ("files", (file_path.name, f.read(), "image/png"))
            )

    data = {
        "backend": "surya",
        "language": "de"
    }

    start_time = time.time()
    response = requests.post(f"{API_URL}/ocr/batch", files=files_data, data=data)
    batch_time = time.time() - start_time

    if response.status_code == 200:
        results = response.json()
        print(f"[OK] Batch processed in {batch_time:.2f}s")
        print(f"   Documents: {len(results.get('results', []))}")
        print(f"   Avg time per doc: {batch_time/len(existing_files):.2f}s")
        return {
            "success": True,
            "time": batch_time,
            "documents": len(results.get('results', []))
        }
    else:
        print(f"[ERROR] Batch failed ({response.status_code}): {response.text[:200]}")
        return {
            "success": False,
            "time": batch_time,
            "error": response.text[:200]
        }

def test_api_endpoints():
    """Test various API endpoints."""
    print("\n[API] Testing API Endpoints")
    print("-" * 60)

    endpoints = [
        ("/health", "GET", "Health check"),
        ("/ocr/backends", "GET", "List backends"),
        ("/ocr/status", "GET", "OCR status"),
    ]

    results = []
    for endpoint, method, description in endpoints:
        print(f"Testing {endpoint} ({description})...", end=" ")
        try:
            if method == "GET":
                response = requests.get(f"{API_URL}{endpoint}", timeout=5)

            if response.status_code == 200:
                print(f"[OK] {response.status_code}")
                results.append({"endpoint": endpoint, "success": True})
            else:
                print(f"[ERROR] {response.status_code}")
                results.append({"endpoint": endpoint, "success": False})
        except Exception as e:
            print(f"[ERROR] Error: {e}")
            results.append({"endpoint": endpoint, "success": False, "error": str(e)})

    return results

def main():
    """Run all advanced tests."""
    print("=" * 70)
    print("ABLAGE-SYSTEM ADVANCED API TESTS")
    print("=" * 70)

    all_results = {}

    # Test 1: Health and status endpoints
    print("\n[1] API ENDPOINTS")
    all_results["endpoints"] = test_api_endpoints()

    # Test 2: Single image files
    print("\n[2] SINGLE IMAGE PROCESSING")
    test_images = [
        Path("test_documents/test_umlauts.png"),
        Path("test_documents/test_invoice.png"),
    ]

    image_results = []
    for img_path in test_images:
        if img_path.exists():
            result = test_single_image(img_path)
            if result:
                image_results.append(result)
    all_results["images"] = image_results

    # Test 3: PDF processing (if available)
    print("\n[3] PDF PROCESSING")
    pdf_path = Path("test_documents/sample.pdf")
    if pdf_path.exists():
        all_results["pdf"] = test_pdf_document(pdf_path)
    else:
        print(f"[WARNING]  No PDF found at {pdf_path}")
        # Create a simple test PDF
        try:
            from PIL import Image
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import A4

            pdf_path = Path("test_documents/test_generated.pdf")
            c = canvas.Canvas(str(pdf_path), pagesize=A4)
            c.drawString(100, 750, "Test PDF für Ablage-System")
            c.drawString(100, 730, "Enthält deutsche Umlaute: ä ö ü Ä Ö Ü ß")
            c.drawString(100, 710, "Firma: Müller GmbH")
            c.drawString(100, 690, "Straße: Hauptstraße 123")
            c.save()
            print(f"[INFO] Generated test PDF: {pdf_path}")
            all_results["pdf"] = test_pdf_document(pdf_path)
        except ImportError:
            print("[WARNING]  reportlab not installed - skipping PDF generation")

    # Test 4: Batch processing
    print("\n[4] BATCH PROCESSING")
    all_results["batch"] = test_batch_endpoint()

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    # Calculate statistics
    total_tests = 0
    successful_tests = 0
    total_time = 0

    # Count endpoint tests
    if "endpoints" in all_results:
        for endpoint in all_results["endpoints"]:
            total_tests += 1
            if endpoint.get("success", False):
                successful_tests += 1

    # Count image tests
    if "images" in all_results:
        for img in all_results["images"]:
            total_tests += 1
            if img.get("success", False):
                successful_tests += 1
            total_time += img.get("time", 0)

    # Count PDF test
    if "pdf" in all_results and all_results["pdf"]:
        total_tests += 1
        if all_results["pdf"].get("success", False):
            successful_tests += 1
        total_time += all_results["pdf"].get("time", 0)

    # Count batch test
    if "batch" in all_results and all_results["batch"]:
        total_tests += 1
        if all_results["batch"].get("success", False):
            successful_tests += 1
        total_time += all_results["batch"].get("time", 0)

    print(f"Total tests run: {total_tests}")
    print(f"Successful: {successful_tests}/{total_tests} ({successful_tests/total_tests*100:.0f}%)")
    print(f"Total processing time: {total_time:.2f}s")
    if total_time > 0 and len(all_results.get("images", [])) > 0:
        avg_time = total_time / len(all_results.get("images", []))
        print(f"Average time per document: {avg_time:.2f}s")

    # Performance metrics
    print("\nPERFORMANCE METRICS")
    print("-" * 40)
    if "images" in all_results and all_results["images"]:
        for img_result in all_results["images"]:
            if img_result.get("success"):
                chars_per_second = img_result["text_length"] / img_result["time"]
                print(f"{img_result['file']}: {chars_per_second:.0f} chars/sec")

    print("\n" + "=" * 70)
    print("[OK] TESTS COMPLETED")
    print("=" * 70)

    # Save results to JSON
    results_file = Path("test_results.json")
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\n[SAVED] Results saved to: {results_file}")

if __name__ == "__main__":
    main()