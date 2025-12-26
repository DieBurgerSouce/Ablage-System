# -*- coding: utf-8 -*-
"""
PaddleOCR-VL 0.9B Benchmark Script.

Führt vollständigen Benchmark-Lauf auf 20 Test-Dokumenten durch und
vergleicht mit bestehenden Backends (PP-OCRv5, Surya, DeepSeek).

Usage:
    python scripts/benchmark_paddleocr_vl.py --experimental
    python scripts/benchmark_paddleocr_vl.py --quick --experimental  # Nur 3 Dokumente
    python scripts/benchmark_paddleocr_vl.py --backends paddle-ocr-vl-09b paddle-ocr-v5 --experimental
"""
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
import uuid

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import argparse
import structlog

from app.services.benchmark_runner_service import (
    BenchmarkRunnerService,
    AVAILABLE_BACKENDS,
    BackendConfig
)
from app.db.schemas import BenchmarkRunRequest
from app.db.database import get_async_session
from app.db.models import OCRTrainingSample, TrainingSampleStatus
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import hashlib

logger = structlog.get_logger(__name__)


async def load_evaluation_dataset() -> List[Dict[str, Any]]:
    """Lädt Evaluierungs-Dataset aus Manifest."""
    manifest_path = PROJECT_ROOT / "tests/fixtures/paddleocr_vl_evaluation/dataset_manifest.json"

    if not manifest_path.exists():
        raise FileNotFoundError(f"Dataset manifest not found: {manifest_path}")

    with open(manifest_path) as f:
        manifest = json.load(f)

    return manifest["documents"]


async def create_training_samples_from_dataset(
    db: AsyncSession,
    documents: List[Dict[str, Any]]
) -> List[str]:
    """Erstellt OCRTrainingSample Einträge aus Dataset-Manifest.

    Returns:
        List of sample UUIDs
    """
    sample_ids = []

    for doc in documents:
        image_path = PROJECT_ROOT / doc["source"]
        gt_path = PROJECT_ROOT / doc["ground_truth"]

        if not image_path.exists():
            logger.warning("dataset_image_not_found", image_path=str(image_path))
            continue

        # Load ground truth
        with open(gt_path) as f:
            gt_data = json.load(f)

        ground_truth_text = gt_data.get("expected_text", "")
        if not ground_truth_text:
            logger.warning("dataset_no_ground_truth", doc_id=doc["id"])
            continue

        # Calculate file hash
        with open(image_path, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()

        # Check if sample already exists
        result = await db.execute(
            select(OCRTrainingSample).where(OCRTrainingSample.file_hash == file_hash)
        )
        existing = result.scalar_one_or_none()

        if existing:
            sample_ids.append(str(existing.id))
            continue

        # Create new sample
        sample = OCRTrainingSample(
            file_path=str(image_path),
            file_hash=file_hash,
            ground_truth_text=ground_truth_text,
            language="de",
            document_type=doc["type"],
            difficulty=doc.get("quality", "medium"),
            has_umlauts=doc.get("has_umlauts", False),
            has_tables=doc.get("has_tables", False),
            status=TrainingSampleStatus.VERIFIED.value  # Mark as verified for evaluation
        )

        db.add(sample)
        await db.flush()
        sample_ids.append(str(sample.id))

        logger.info(
            "evaluation_sample_created",
            sample_id=str(sample.id)[:8],
            doc_id=doc["id"]
        )

    await db.commit()
    return sample_ids


async def run_benchmark(
    sample_ids: List[str],
    backends: List[str],
    quick: bool = False
) -> Dict[str, Any]:
    """Führt Benchmark-Lauf durch."""
    # Limit to 3 documents for quick mode
    if quick:
        sample_ids = sample_ids[:3]
        logger.info("quick_mode_enabled", sample_count=len(sample_ids))

    logger.info(
        "benchmark_starting",
        sample_count=len(sample_ids),
        backends=backends
    )

    async for db in get_async_session():
        try:
            service = BenchmarkRunnerService()

            request = BenchmarkRunRequest(
                sample_ids=[uuid.UUID(sid) for sid in sample_ids],
                backends=backends,
                force_rerun=True  # Always rerun for evaluation
            )

            response = await service.run_benchmark(db, request)

            return {
                "success": response.success,
                "samples_processed": response.samples_processed,
                "samples_failed": response.samples_failed,
                "backends_used": response.backends_used,
                "total_time_ms": response.total_time_ms
            }
        finally:
            await db.close()


async def generate_comparison_report(
    sample_ids: List[str],
    backends: List[str]
) -> Dict[str, Any]:
    """Generiert Vergleichs-Report aus Benchmark-Ergebnissen."""
    from app.db.models import OCRBackendBenchmark
    from sqlalchemy import select, func

    report = {
        "generated_at": datetime.now().isoformat(),
        "sample_count": len(sample_ids),
        "backends": backends,
        "results_by_backend": {},
        "summary": {}
    }

    async for db in get_async_session():
        try:
            for backend in backends:
                # Get all benchmarks for this backend
                result = await db.execute(
                    select(OCRBackendBenchmark)
                    .where(OCRBackendBenchmark.backend_name == backend)
                    .where(OCRBackendBenchmark.sample_id.in_([uuid.UUID(sid) for sid in sample_ids]))
                )
                benchmarks = result.scalars().all()

                if not benchmarks:
                    continue

                # Calculate averages
                successful = [b for b in benchmarks if b.cer is not None]

                if successful:
                    report["results_by_backend"][backend] = {
                        "total_samples": len(benchmarks),
                        "successful": len(successful),
                        "avg_cer": float(sum(b.cer for b in successful) / len(successful)),
                        "avg_wer": float(sum(b.wer for b in successful) / len(successful)) if any(b.wer for b in successful) else None,
                        "avg_umlaut_accuracy": float(sum(b.umlaut_accuracy for b in successful) / len(successful)) if any(b.umlaut_accuracy for b in successful) else None,
                        "avg_processing_time_ms": float(sum(b.processing_time_ms for b in successful) / len(successful)),
                        "avg_confidence": float(sum(b.confidence for b in successful) / len(successful)) if any(b.confidence for b in successful) else None,
                    }

            # Summary comparison
            if "paddle-ocr-vl-09b" in report["results_by_backend"]:
                vl_results = report["results_by_backend"]["paddle-ocr-vl-09b"]
                report["summary"] = {
                    "paddleocr_vl": vl_results,
                    "comparison": {}
                }

                # Compare with other backends
                for backend in ["paddle-ocr-v5", "surya-gpu", "deepseek-janus-pro"]:
                    if backend in report["results_by_backend"]:
                        other_results = report["results_by_backend"][backend]
                        report["summary"]["comparison"][backend] = {
                            "cer_improvement": vl_results["avg_cer"] - other_results["avg_cer"],
                            "umlaut_accuracy_diff": (
                                vl_results.get("avg_umlaut_accuracy", 0) -
                                other_results.get("avg_umlaut_accuracy", 0)
                            ) if vl_results.get("avg_umlaut_accuracy") and other_results.get("avg_umlaut_accuracy") else None,
                            "speed_ratio": (
                                other_results["avg_processing_time_ms"] /
                                vl_results["avg_processing_time_ms"]
                            ) if vl_results["avg_processing_time_ms"] > 0 else None
                        }
        finally:
            await db.close()

    return report


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Benchmark PaddleOCR-VL 0.9B")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick mode: only test 3 documents"
    )
    parser.add_argument(
        "--backends",
        nargs="+",
        help="Backends to test (default: paddle-ocr-vl-09b, paddle-ocr-v5, surya-gpu, deepseek-janus-pro)"
    )
    parser.add_argument(
        "--experimental",
        action="store_true",
        help="Enable experimental backends (required for paddle-ocr-vl-09b)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "data/benchmarks/paddleocr_vl_evaluation.json",
        help="Output file for results"
    )
    args = parser.parse_args()

    print("="*60)
    print("PADDLEOCR-VL 0.9B BENCHMARK")
    print("="*60)
    print()

    # Load dataset
    print("Loading evaluation dataset...")
    documents = await load_evaluation_dataset()
    print(f"Loaded {len(documents)} documents from dataset")

    # Create training samples
    print("\nCreating training samples...")
    async for db in get_async_session():
        try:
            sample_ids = await create_training_samples_from_dataset(db, documents)
            print(f"Created/Found {len(sample_ids)} training samples")
        finally:
            await db.close()

    # Determine backends
    backends = args.backends
    if backends is None:
        backends = [
            "paddle-ocr-vl-09b",
            "paddle-ocr-v5",
            "surya-gpu",
            "deepseek-janus-pro"
        ]

    # Check for experimental backends
    has_experimental = any(
        AVAILABLE_BACKENDS.get(b, BackendConfig(name="", display_name="", requires_gpu=False, vram_gb=0.0)).experimental
        for b in backends
    )

    if has_experimental and not args.experimental:
        print("\n⚠️  Some backends are experimental. Use --experimental to enable.")
        print("   Experimental backends will be skipped.")
        backends = [b for b in backends if not AVAILABLE_BACKENDS.get(b, BackendConfig(name="", display_name="", requires_gpu=False, vram_gb=0.0)).experimental]

    print(f"\nTesting backends: {', '.join(backends)}")
    print()

    # Run benchmark
    print("Running benchmark...")
    benchmark_result = await run_benchmark(
        sample_ids=sample_ids,
        backends=backends,
        quick=args.quick
    )

    print(f"\nBenchmark completed:")
    print(f"  Processed: {benchmark_result['samples_processed']}")
    print(f"  Failed: {benchmark_result['samples_failed']}")
    print(f"  Total time: {benchmark_result['total_time_ms']/1000:.1f}s")

    # Generate comparison report
    print("\nGenerating comparison report...")
    report = await generate_comparison_report(sample_ids, backends)

    # Save report
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\nReport saved to: {args.output}")

    # Print summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    if "paddle-ocr-vl-09b" in report["results_by_backend"]:
        vl = report["results_by_backend"]["paddle-ocr-vl-09b"]
        print(f"\nPaddleOCR-VL 0.9B:")
        print(f"  CER: {vl['avg_cer']:.2%}")
        print(f"  Umlaut Accuracy: {vl.get('avg_umlaut_accuracy', 0):.2%}")
        print(f"  Processing Time: {vl['avg_processing_time_ms']/1000:.2f}s per document")

        if "comparison" in report["summary"]:
            print(f"\nComparison:")
            for backend, comp in report["summary"]["comparison"].items():
                print(f"  vs {backend}:")
                if comp.get("cer_improvement") is not None:
                    improvement = comp["cer_improvement"]
                    sign = "+" if improvement < 0 else ""
                    print(f"    CER: {sign}{improvement:.2%} improvement")
                if comp.get("umlaut_accuracy_diff") is not None:
                    diff = comp["umlaut_accuracy_diff"]
                    sign = "+" if diff > 0 else ""
                    print(f"    Umlaut Accuracy: {sign}{diff:.2%}")

    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
