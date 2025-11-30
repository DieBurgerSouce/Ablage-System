#!/usr/bin/env python
"""
GPU Benchmark Suite for Ablage-System OCR Backends.

Runs comprehensive benchmarks on all OCR backends and generates reports.

Usage:
    python scripts/run_benchmark_suite.py
    python scripts/run_benchmark_suite.py --backend deepseek
    python scripts/run_benchmark_suite.py --output results.json --html-report report.html
    python scripts/run_benchmark_suite.py --quick  # Fewer documents
"""

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import torch


@dataclass
class BenchmarkResult:
    """Result from a single benchmark run."""
    backend: str
    document_type: str
    document_name: str
    success: bool
    processing_time_ms: int
    vram_before_gb: float
    vram_peak_gb: float
    vram_after_gb: float
    text_length: int
    confidence: float
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class BackendSummary:
    """Summary statistics for a backend."""
    backend: str
    total_documents: int
    successful: int
    failed: int
    avg_processing_time_ms: float
    min_processing_time_ms: float
    max_processing_time_ms: float
    avg_vram_peak_gb: float
    max_vram_peak_gb: float
    throughput_pages_per_sec: float
    avg_confidence: float


class BenchmarkSuite:
    """Complete benchmark suite for OCR backends."""

    # Available backends
    BACKENDS = {
        "deepseek": {
            "module": "app.agents.ocr.deepseek_agent",
            "class": "DeepSeekAgent",
            "gpu_required": True,
        },
        "got_ocr": {
            "module": "app.agents.ocr.got_ocr_agent",
            "class": "GOTOCRAgent",
            "gpu_required": True,
        },
        "surya_gpu": {
            "module": "app.agents.ocr.surya_gpu_agent",
            "class": "SuryaGPUAgent",
            "gpu_required": True,
        },
        "surya_docling": {
            "module": "app.agents.ocr.surya_docling_agent",
            "class": "SuryaDoclingAgent",
            "gpu_required": False,
        },
    }

    def __init__(
        self,
        test_docs_dir: Path,
        output_dir: Path,
        quick_mode: bool = False,
    ):
        self.test_docs_dir = test_docs_dir
        self.output_dir = output_dir
        self.quick_mode = quick_mode
        self.results: List[BenchmarkResult] = []

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def get_test_documents(self) -> Dict[str, List[Path]]:
        """Get test documents organized by category."""
        documents = {}

        categories = [
            "invoices", "fraktur", "tables", "contracts",
            "forms", "handwritten", "mixed"
        ]

        for category in categories:
            cat_dir = self.test_docs_dir / category
            if cat_dir.exists():
                images = list(cat_dir.glob("*.png"))
                if self.quick_mode:
                    images = images[:2]  # Only 2 per category in quick mode
                documents[category] = images

        return documents

    def get_vram_info(self) -> Dict[str, float]:
        """Get current VRAM information."""
        if not torch.cuda.is_available():
            return {"available": False}

        return {
            "allocated_gb": torch.cuda.memory_allocated() / (1024**3),
            "reserved_gb": torch.cuda.memory_reserved() / (1024**3),
            "peak_gb": torch.cuda.max_memory_allocated() / (1024**3),
        }

    async def load_backend(self, backend_name: str):
        """Load and initialize a backend."""
        backend_info = self.BACKENDS.get(backend_name)
        if not backend_info:
            raise ValueError(f"Unknown backend: {backend_name}")

        # Check GPU requirement
        if backend_info["gpu_required"] and not torch.cuda.is_available():
            raise RuntimeError(f"{backend_name} requires GPU but CUDA not available")

        # Import and instantiate
        module = __import__(backend_info["module"], fromlist=[backend_info["class"]])
        agent_class = getattr(module, backend_info["class"])
        return agent_class()

    async def benchmark_document(
        self,
        agent,
        backend_name: str,
        image_path: Path,
        category: str,
    ) -> BenchmarkResult:
        """Benchmark a single document."""
        # Record VRAM before
        vram_before = 0.0
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
            vram_before = torch.cuda.memory_allocated() / (1024**3)

        # Process document
        start_time = time.perf_counter()
        error = None
        text_length = 0
        confidence = 0.0
        success = False

        try:
            result = await agent.process({
                "document_id": f"bench_{image_path.stem}",
                "image_path": str(image_path),
                "language": "de",
            })

            success = True
            text_length = len(result.get("text", ""))
            confidence = result.get("confidence", 0.0)

        except Exception as e:
            error = str(e)
            success = False

        # Record timing and VRAM
        processing_time_ms = int((time.perf_counter() - start_time) * 1000)

        vram_peak = 0.0
        vram_after = 0.0
        if torch.cuda.is_available():
            vram_peak = torch.cuda.max_memory_allocated() / (1024**3)
            vram_after = torch.cuda.memory_allocated() / (1024**3)

        return BenchmarkResult(
            backend=backend_name,
            document_type=category,
            document_name=image_path.name,
            success=success,
            processing_time_ms=processing_time_ms,
            vram_before_gb=round(vram_before, 2),
            vram_peak_gb=round(vram_peak, 2),
            vram_after_gb=round(vram_after, 2),
            text_length=text_length,
            confidence=round(confidence, 3),
            error=error,
        )

    async def benchmark_backend(
        self,
        backend_name: str,
        documents: Dict[str, List[Path]],
    ) -> List[BenchmarkResult]:
        """Benchmark a single backend with all documents."""
        results = []

        print(f"\n{'=' * 60}")
        print(f"BENCHMARKING: {backend_name.upper()}")
        print(f"{'=' * 60}")

        try:
            agent = await self.load_backend(backend_name)
        except Exception as e:
            print(f"  [ERROR] Failed to load backend: {e}")
            return results

        try:
            for category, images in documents.items():
                print(f"\n  {category.upper()} ({len(images)} documents):")

                for image_path in images:
                    result = await self.benchmark_document(
                        agent, backend_name, image_path, category
                    )
                    results.append(result)

                    status = "[OK]" if result.success else "[FAIL]"
                    print(
                        f"    {status} {image_path.name}: "
                        f"{result.processing_time_ms}ms, "
                        f"VRAM: {result.vram_peak_gb:.2f}GB"
                    )

                    # Clear cache between documents
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()

        finally:
            await agent.cleanup()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        return results

    def calculate_summary(
        self,
        backend_name: str,
        results: List[BenchmarkResult],
    ) -> BackendSummary:
        """Calculate summary statistics for a backend."""
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        if not successful:
            return BackendSummary(
                backend=backend_name,
                total_documents=len(results),
                successful=0,
                failed=len(failed),
                avg_processing_time_ms=0,
                min_processing_time_ms=0,
                max_processing_time_ms=0,
                avg_vram_peak_gb=0,
                max_vram_peak_gb=0,
                throughput_pages_per_sec=0,
                avg_confidence=0,
            )

        times = [r.processing_time_ms for r in successful]
        vram_peaks = [r.vram_peak_gb for r in successful]
        confidences = [r.confidence for r in successful]

        total_time_sec = sum(times) / 1000
        throughput = len(successful) / total_time_sec if total_time_sec > 0 else 0

        return BackendSummary(
            backend=backend_name,
            total_documents=len(results),
            successful=len(successful),
            failed=len(failed),
            avg_processing_time_ms=round(sum(times) / len(times), 1),
            min_processing_time_ms=min(times),
            max_processing_time_ms=max(times),
            avg_vram_peak_gb=round(sum(vram_peaks) / len(vram_peaks), 2),
            max_vram_peak_gb=round(max(vram_peaks), 2),
            throughput_pages_per_sec=round(throughput, 3),
            avg_confidence=round(sum(confidences) / len(confidences), 3),
        )

    async def run_full_benchmark(
        self,
        backends: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Run complete benchmark suite."""
        print("\n" + "=" * 60)
        print("ABLAGE-SYSTEM OCR BENCHMARK SUITE")
        print("=" * 60)

        # Get system info
        system_info = {
            "timestamp": datetime.now().isoformat(),
            "cuda_available": torch.cuda.is_available(),
            "quick_mode": self.quick_mode,
        }

        if torch.cuda.is_available():
            system_info["gpu_name"] = torch.cuda.get_device_name(0)
            system_info["gpu_memory_gb"] = torch.cuda.get_device_properties(0).total_memory / (1024**3)

        print(f"\nSystem: {system_info.get('gpu_name', 'No GPU')}")
        print(f"CUDA: {system_info['cuda_available']}")
        print(f"Mode: {'Quick' if self.quick_mode else 'Full'}")

        # Get test documents
        documents = self.get_test_documents()
        total_docs = sum(len(docs) for docs in documents.values())
        print(f"Test Documents: {total_docs}")

        # Determine backends to benchmark
        if backends is None:
            backends = list(self.BACKENDS.keys())

        # Run benchmarks
        all_results = []
        summaries = []

        for backend_name in backends:
            backend_info = self.BACKENDS.get(backend_name)
            if not backend_info:
                print(f"\n[SKIP] Unknown backend: {backend_name}")
                continue

            if backend_info["gpu_required"] and not torch.cuda.is_available():
                print(f"\n[SKIP] {backend_name}: Requires GPU")
                continue

            results = await self.benchmark_backend(backend_name, documents)
            all_results.extend(results)

            summary = self.calculate_summary(backend_name, results)
            summaries.append(summary)

        self.results = all_results

        return {
            "system_info": system_info,
            "results": [asdict(r) for r in all_results],
            "summaries": [asdict(s) for s in summaries],
        }

    def export_json(self, data: Dict[str, Any], filepath: Path) -> None:
        """Export results to JSON file."""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"\nResults exported to: {filepath}")

    def export_html_report(self, data: Dict[str, Any], filepath: Path) -> None:
        """Generate HTML benchmark report."""
        summaries = data.get("summaries", [])
        system_info = data.get("system_info", {})

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Ablage-System OCR Benchmark Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
        h1 {{ color: #333; }}
        .card {{ background: white; padding: 20px; margin: 20px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #4a9eff; color: white; }}
        tr:hover {{ background: #f5f5f5; }}
        .success {{ color: green; }}
        .fail {{ color: red; }}
        .metric {{ font-size: 24px; font-weight: bold; color: #333; }}
        .metric-label {{ font-size: 14px; color: #666; }}
        .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; }}
    </style>
</head>
<body>
    <h1>Ablage-System OCR Benchmark Report</h1>

    <div class="card">
        <h2>System Information</h2>
        <p><strong>GPU:</strong> {system_info.get('gpu_name', 'N/A')}</p>
        <p><strong>VRAM:</strong> {system_info.get('gpu_memory_gb', 0):.1f} GB</p>
        <p><strong>CUDA:</strong> {'Available' if system_info.get('cuda_available') else 'Not Available'}</p>
        <p><strong>Timestamp:</strong> {system_info.get('timestamp', 'N/A')}</p>
    </div>

    <div class="card">
        <h2>Backend Comparison</h2>
        <table>
            <tr>
                <th>Backend</th>
                <th>Success Rate</th>
                <th>Avg Time (ms)</th>
                <th>Throughput (p/s)</th>
                <th>Peak VRAM (GB)</th>
                <th>Avg Confidence</th>
            </tr>
"""

        for summary in summaries:
            success_rate = summary['successful'] / summary['total_documents'] * 100 if summary['total_documents'] > 0 else 0
            html += f"""
            <tr>
                <td><strong>{summary['backend']}</strong></td>
                <td class="{'success' if success_rate > 90 else 'fail'}">{success_rate:.0f}%</td>
                <td>{summary['avg_processing_time_ms']:.0f}</td>
                <td>{summary['throughput_pages_per_sec']:.2f}</td>
                <td>{summary['max_vram_peak_gb']:.2f}</td>
                <td>{summary['avg_confidence']:.2%}</td>
            </tr>
"""

        html += """
        </table>
    </div>

    <div class="card">
        <h2>Performance Summary</h2>
        <div class="grid">
"""

        # Find best performers
        if summaries:
            fastest = min(summaries, key=lambda s: s['avg_processing_time_ms'] if s['avg_processing_time_ms'] > 0 else float('inf'))
            most_accurate = max(summaries, key=lambda s: s['avg_confidence'])

            html += f"""
            <div>
                <div class="metric">{fastest['backend']}</div>
                <div class="metric-label">Fastest Backend</div>
            </div>
            <div>
                <div class="metric">{most_accurate['backend']}</div>
                <div class="metric-label">Most Accurate</div>
            </div>
"""

        html += """
        </div>
    </div>

</body>
</html>
"""

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"HTML report exported to: {filepath}")

    def print_summary(self, data: Dict[str, Any]) -> None:
        """Print benchmark summary to console."""
        summaries = data.get("summaries", [])

        print("\n" + "=" * 60)
        print("BENCHMARK SUMMARY")
        print("=" * 60)

        for summary in summaries:
            print(f"\n{summary['backend'].upper()}:")
            print(f"  Documents: {summary['successful']}/{summary['total_documents']} successful")
            print(f"  Avg Time: {summary['avg_processing_time_ms']:.0f}ms")
            print(f"  Throughput: {summary['throughput_pages_per_sec']:.2f} pages/sec")
            print(f"  Peak VRAM: {summary['max_vram_peak_gb']:.2f}GB")
            print(f"  Avg Confidence: {summary['avg_confidence']:.1%}")

        print("\n" + "=" * 60)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run GPU benchmark suite for Ablage-System OCR backends"
    )
    parser.add_argument(
        "--backend", "-b",
        type=str,
        default=None,
        help="Specific backend to benchmark (default: all)"
    )
    parser.add_argument(
        "--test-docs", "-t",
        type=Path,
        default=Path("tests/fixtures/german_docs"),
        help="Path to test documents directory"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("benchmark_results/results.json"),
        help="Output JSON file path"
    )
    parser.add_argument(
        "--html-report", "-r",
        type=Path,
        default=None,
        help="Output HTML report path"
    )
    parser.add_argument(
        "--quick", "-q",
        action="store_true",
        help="Quick mode (fewer documents per category)"
    )
    return parser.parse_args()


async def main():
    """Main entry point."""
    args = parse_args()

    # Create output directory
    args.output.parent.mkdir(parents=True, exist_ok=True)

    # Initialize benchmark suite
    suite = BenchmarkSuite(
        test_docs_dir=args.test_docs,
        output_dir=args.output.parent,
        quick_mode=args.quick,
    )

    # Determine backends
    backends = [args.backend] if args.backend else None

    # Run benchmarks
    data = await suite.run_full_benchmark(backends=backends)

    # Export results
    suite.export_json(data, args.output)

    if args.html_report:
        suite.export_html_report(data, args.html_report)

    # Print summary
    suite.print_summary(data)


if __name__ == "__main__":
    asyncio.run(main())
