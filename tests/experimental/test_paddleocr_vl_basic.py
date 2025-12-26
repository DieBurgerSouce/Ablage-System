# -*- coding: utf-8 -*-
"""
Basic Functionality Test for PaddleOCR-VL 0.9B Experimental Agent.

Tests fundamental functionality:
- Model loading
- Text extraction
- Umlaut recognition
- VRAM usage
- Processing time

This is a Go/No-Go test before proceeding to full benchmark.
"""
import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, Any

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pytest
import torch

from app.agents.ocr.paddle_ocr_vl_agent_experimental import PaddleOCRVLAgentExperimental


# Test dataset manifest path
DATASET_MANIFEST = PROJECT_ROOT / "tests/fixtures/paddleocr_vl_evaluation/dataset_manifest.json"


@pytest.fixture
def test_agent():
    """Create test agent instance."""
    return PaddleOCRVLAgentExperimental()


@pytest.fixture
def test_documents():
    """Load test documents from manifest."""
    if not DATASET_MANIFEST.exists():
        pytest.skip(f"Dataset manifest not found: {DATASET_MANIFEST}")

    with open(DATASET_MANIFEST) as f:
        manifest = json.load(f)

    # Use first 3 documents for basic functionality test
    documents = []
    for doc in manifest["documents"][:3]:
        img_path = PROJECT_ROOT / doc["source"]
        gt_path = PROJECT_ROOT / doc["ground_truth"]
        if img_path.exists() and gt_path.exists():
            documents.append({
                "id": doc["id"],
                "image_path": str(img_path),
                "ground_truth_path": str(gt_path),
                "type": doc["type"],
                "has_umlauts": doc.get("has_umlauts", False)
            })

    if not documents:
        pytest.skip("No test documents found")

    return documents


@pytest.mark.asyncio
@pytest.mark.experimental
@pytest.mark.gpu_required
async def test_model_loading(test_agent):
    """Test that model loads successfully."""
    # Check GPU availability
    if not torch.cuda.is_available():
        pytest.skip("CUDA not available - PaddleOCR-VL requires GPU")

    # Load model
    await test_agent._load_model_async()

    assert test_agent._model_loaded, "Model should be loaded"
    assert test_agent._ocr is not None, "OCR instance should be created"

    # Check status
    status = test_agent.get_status()
    assert status["model_loaded"] is True
    assert status["gpu_required"] is True


@pytest.mark.asyncio
@pytest.mark.experimental
@pytest.mark.gpu_required
async def test_text_extraction(test_agent, test_documents):
    """Test basic text extraction."""
    if not torch.cuda.is_available():
        pytest.skip("CUDA not available")

    # Use first document
    doc = test_documents[0]

    result = await test_agent.process({
        "image_path": doc["image_path"],
        "document_id": doc["id"]
    })

    assert result["success"] is True, f"Processing should succeed: {result.get('error')}"
    assert "text" in result, "Result should contain text"
    assert len(result["text"]) > 0, "Text should not be empty"
    assert result["text_length"] > 0, "Text length should be > 0"


@pytest.mark.asyncio
@pytest.mark.experimental
@pytest.mark.gpu_required
async def test_umlaut_recognition(test_agent, test_documents):
    """Test German umlaut recognition (critical for German documents)."""
    if not torch.cuda.is_available():
        pytest.skip("CUDA not available")

    # Find document with umlauts
    umlaut_doc = None
    for doc in test_documents:
        if doc.get("has_umlauts"):
            umlaut_doc = doc
            break

    if not umlaut_doc:
        pytest.skip("No document with umlauts found in test set")

    result = await test_agent.process({
        "image_path": umlaut_doc["image_path"],
        "document_id": umlaut_doc["id"]
    })

    assert result["success"] is True, f"Processing should succeed: {result.get('error')}"
    assert result.get("has_umlauts") is True, "Should detect umlauts"
    assert result.get("umlaut_count", 0) > 0, "Should have umlaut count > 0"

    # Check for specific umlauts in text
    text = result.get("text", "")
    umlauts = ['ä', 'ö', 'ü', 'ß', 'Ä', 'Ö', 'Ü']
    found_umlauts = [char for char in umlauts if char in text]
    assert len(found_umlauts) > 0, f"Should find umlauts in text. Found: {found_umlauts}"


@pytest.mark.asyncio
@pytest.mark.experimental
@pytest.mark.gpu_required
async def test_vram_usage(test_agent, test_documents):
    """Test VRAM usage stays within limits."""
    if not torch.cuda.is_available():
        pytest.skip("CUDA not available")

    # Get initial VRAM
    initial_vram = torch.cuda.memory_reserved(0) / 1024**3

    # Process document
    doc = test_documents[0]
    result = await test_agent.process({
        "image_path": doc["image_path"],
        "document_id": doc["id"]
    })

    assert result["success"] is True, f"Processing should succeed: {result.get('error')}"

    # Get peak VRAM
    peak_vram = result.get("vram_peak_gb", 0.0)

    # Check VRAM limit (14GB for RTX 4080 with buffer)
    assert peak_vram < 14.0, f"VRAM usage {peak_vram:.2f} GB exceeds 14GB limit"

    print(f"\nVRAM Usage: {initial_vram:.2f} GB initial, {peak_vram:.2f} GB peak")


@pytest.mark.asyncio
@pytest.mark.experimental
@pytest.mark.gpu_required
async def test_processing_time(test_agent, test_documents):
    """Test processing time is reasonable."""
    if not torch.cuda.is_available():
        pytest.skip("CUDA not available")

    doc = test_documents[0]
    result = await test_agent.process({
        "image_path": doc["image_path"],
        "document_id": doc["id"]
    })

    assert result["success"] is True, f"Processing should succeed: {result.get('error')}"

    processing_time_s = result.get("processing_time_ms", 0) / 1000.0

    # Target: <5s per page
    assert processing_time_s < 5.0, f"Processing time {processing_time_s:.2f}s exceeds 5s limit"

    print(f"\nProcessing Time: {processing_time_s:.2f}s")


@pytest.mark.asyncio
@pytest.mark.experimental
@pytest.mark.gpu_required
async def test_no_oom_error(test_agent, test_documents):
    """Test that no OOM errors occur."""
    if not torch.cuda.is_available():
        pytest.skip("CUDA not available")

    # Process all test documents
    errors = []
    for doc in test_documents:
        try:
            result = await test_agent.process({
                "image_path": doc["image_path"],
                "document_id": doc["id"]
            })

            if not result["success"]:
                error = result.get("error", "Unknown error")
                if "OOM" in error or "Out of Memory" in error:
                    errors.append(f"{doc['id']}: {error}")
        except RuntimeError as e:
            if "OOM" in str(e) or "Out of Memory" in str(e):
                errors.append(f"{doc['id']}: {e}")

    assert len(errors) == 0, f"OOM errors occurred: {errors}"


@pytest.mark.asyncio
@pytest.mark.experimental
@pytest.mark.gpu_required
async def test_go_no_go_decision(test_agent, test_documents):
    """Make Go/No-Go decision based on all tests."""
    if not torch.cuda.is_available():
        pytest.skip("CUDA not available")

    # Run all critical tests
    results = []
    for doc in test_documents:
        result = await test_agent.process({
            "image_path": doc["image_path"],
            "document_id": doc["id"]
        })
        results.append(result)

    # Calculate metrics
    successful = sum(1 for r in results if r["success"])
    avg_vram = sum(r.get("vram_peak_gb", 0) for r in results if r["success"]) / successful if successful > 0 else 0
    avg_time = sum(r.get("processing_time_ms", 0) for r in results if r["success"]) / successful / 1000.0 if successful > 0 else 0
    total_umlauts = sum(r.get("umlaut_count", 0) for r in results if r["success"])

    # Go/No-Go criteria
    go_criteria = {
        "all_tests_successful": successful == len(test_documents),
        "vram_under_limit": avg_vram < 14.0,
        "processing_time_acceptable": avg_time < 5.0,
        "umlauts_detected": total_umlauts > 0
    }

    should_go = all(go_criteria.values())

    print("\n" + "="*60)
    print("GO/NO-GO DECISION")
    print("="*60)
    print(f"Successful tests: {successful}/{len(test_documents)}")
    print(f"Avg VRAM: {avg_vram:.2f} GB (limit: <14GB)")
    print(f"Avg processing time: {avg_time:.2f}s (limit: <5s)")
    print(f"Total umlauts detected: {total_umlauts}")
    print()
    print("Criteria:")
    for criterion, passed in go_criteria.items():
        status = "✅" if passed else "❌"
        print(f"  {status} {criterion}: {passed}")
    print()

    if should_go:
        print("✅ GO: All criteria met - Proceed to Benchmark Phase")
    else:
        print("❌ NO-GO: Some criteria not met - Stop evaluation")

    print("="*60)

    # Assert Go criteria
    assert go_criteria["all_tests_successful"], "All tests must succeed"
    assert go_criteria["vram_under_limit"], f"VRAM {avg_vram:.2f} GB must be <14GB"
    assert go_criteria["processing_time_acceptable"], f"Processing time {avg_time:.2f}s must be <5s"
    assert go_criteria["umlauts_detected"], "Umlauts must be detected"


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])

