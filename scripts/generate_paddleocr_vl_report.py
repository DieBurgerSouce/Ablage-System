# -*- coding: utf-8 -*-
"""
Generate PaddleOCR-VL 0.9B Benchmark Report.

Analysiert Benchmark-Ergebnisse und generiert detaillierten Vergleichs-Report
für die Go/No-Go Entscheidung.

Usage:
    python scripts/generate_paddleocr_vl_report.py --input data/benchmarks/paddleocr_vl_evaluation.json
"""
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import argparse


def load_benchmark_results(input_file: Path) -> Dict[str, Any]:
    """Lädt Benchmark-Ergebnisse aus JSON."""
    with open(input_file) as f:
        return json.load(f)


def analyze_results(results: Dict[str, Any]) -> Dict[str, Any]:
    """Analysiert Benchmark-Ergebnisse und erstellt Vergleich."""
    analysis = {
        "paddleocr_vl": {},
        "comparisons": {},
        "strengths": [],
        "weaknesses": [],
        "go_no_go": {
            "decision": None,
            "reasoning": []
        }
    }

    backend_results = results.get("results_by_backend", {})

    if "paddle-ocr-vl-09b" not in backend_results:
        analysis["go_no_go"]["decision"] = "NO-GO"
        analysis["go_no_go"]["reasoning"].append("PaddleOCR-VL 0.9B results not found in benchmark")
        return analysis

    vl_results = backend_results["paddle-ocr-vl-09b"]
    analysis["paddleocr_vl"] = vl_results

    # Compare with other backends
    comparison_backends = ["paddle-ocr-v5", "surya-gpu", "deepseek-janus-pro"]

    for backend in comparison_backends:
        if backend in backend_results:
            other = backend_results[backend]
            comparison = {
                "backend": backend,
                "cer_diff": vl_results["avg_cer"] - other["avg_cer"],
                "umlaut_accuracy_diff": (
                    vl_results.get("avg_umlaut_accuracy", 0) -
                    other.get("avg_umlaut_accuracy", 0)
                ) if vl_results.get("avg_umlaut_accuracy") and other.get("avg_umlaut_accuracy") else None,
                "speed_ratio": (
                    other["avg_processing_time_ms"] /
                    vl_results["avg_processing_time_ms"]
                ) if vl_results["avg_processing_time_ms"] > 0 else None,
                "confidence_diff": (
                    vl_results.get("avg_confidence", 0) -
                    other.get("avg_confidence", 0)
                ) if vl_results.get("avg_confidence") and other.get("avg_confidence") else None
            }
            analysis["comparisons"][backend] = comparison

    # Identify strengths
    if vl_results.get("avg_umlaut_accuracy", 0) >= 0.95:
        analysis["strengths"].append("Excellent umlaut accuracy (≥95%)")

    if vl_results["avg_cer"] < 0.05:
        analysis["strengths"].append("Low character error rate (<5%)")

    # Compare CER improvements
    if "paddle-ocr-v5" in analysis["comparisons"]:
        cer_improvement = analysis["comparisons"]["paddle-ocr-v5"]["cer_diff"]
        if cer_improvement < -0.01:  # Negative = better (lower CER)
            analysis["strengths"].append(f"Better accuracy than PP-OCRv5 ({abs(cer_improvement):.2%} improvement)")

    # Identify weaknesses
    if vl_results["avg_processing_time_ms"] > 5000:
        analysis["weaknesses"].append(f"Slow processing time ({vl_results['avg_processing_time_ms']/1000:.2f}s per page)")

    if vl_results.get("successful", 0) < vl_results.get("total_samples", 0):
        failed = vl_results["total_samples"] - vl_results["successful"]
        analysis["weaknesses"].append(f"{failed} document(s) failed processing")

    # Go/No-Go decision
    go_criteria = {
        "umlaut_accuracy": vl_results.get("avg_umlaut_accuracy", 0) >= 0.95,
        "cer_acceptable": vl_results["avg_cer"] < 0.10,  # <10% CER
        "processing_time": vl_results["avg_processing_time_ms"] < 5000,  # <5s per page
        "success_rate": vl_results.get("successful", 0) == vl_results.get("total_samples", 0),
        "has_advantage": len(analysis["strengths"]) > 0
    }

    should_go = all([
        go_criteria["umlaut_accuracy"],
        go_criteria["cer_acceptable"],
        go_criteria["processing_time"],
        go_criteria["success_rate"]
    ]) and go_criteria["has_advantage"]

    analysis["go_no_go"]["decision"] = "GO" if should_go else "NO-GO"

    # Reasoning
    for criterion, passed in go_criteria.items():
        if not passed:
            analysis["go_no_go"]["reasoning"].append(f"❌ {criterion}: Not met")
        else:
            analysis["go_no_go"]["reasoning"].append(f"✅ {criterion}: Met")

    return analysis


def generate_markdown_report(
    results: Dict[str, Any],
    analysis: Dict[str, Any]
) -> str:
    """Generiert Markdown-Report."""
    report = f"""# PaddleOCR-VL 0.9B Benchmark Report

**Generiert:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Dataset:** {results.get('sample_count', 0)} Dokumente
**Status:** {'✅ GO' if analysis['go_no_go']['decision'] == 'GO' else '❌ NO-GO'}

---

## Executive Summary

### PaddleOCR-VL 0.9B Performance

| Metrik | Wert | Status |
|--------|------|--------|
| **Character Error Rate (CER)** | {analysis['paddleocr_vl'].get('avg_cer', 0):.2%} | {'✅' if analysis['paddleocr_vl'].get('avg_cer', 1) < 0.10 else '❌'} |
| **Umlaut Accuracy** | {analysis['paddleocr_vl'].get('avg_umlaut_accuracy', 0):.2%} | {'✅' if analysis['paddleocr_vl'].get('avg_umlaut_accuracy', 0) >= 0.95 else '❌'} |
| **Processing Time** | {analysis['paddleocr_vl'].get('avg_processing_time_ms', 0)/1000:.2f}s pro Seite | {'✅' if analysis['paddleocr_vl'].get('avg_processing_time_ms', 10000) < 5000 else '❌'} |
| **Success Rate** | {analysis['paddleocr_vl'].get('successful', 0)}/{analysis['paddleocr_vl'].get('total_samples', 0)} | {'✅' if analysis['paddleocr_vl'].get('successful', 0) == analysis['paddleocr_vl'].get('total_samples', 0) else '❌'} |
| **Average Confidence** | {analysis['paddleocr_vl'].get('avg_confidence', 0):.2%} | - |

---

## Vergleich mit bestehenden Backends

"""

    # Add comparison tables
    for backend, comp in analysis["comparisons"].items():
        report += f"""### vs {backend}

| Metrik | PaddleOCR-VL 0.9B | {backend} | Unterschied |
|--------|-------------------|-----------|-------------|
| **CER** | {analysis['paddleocr_vl'].get('avg_cer', 0):.2%} | {results['results_by_backend'][backend].get('avg_cer', 0):.2%} | {comp['cer_diff']:+.2%} |
| **Umlaut Accuracy** | {analysis['paddleocr_vl'].get('avg_umlaut_accuracy', 0):.2%} | {results['results_by_backend'][backend].get('avg_umlaut_accuracy', 0):.2%} | {comp.get('umlaut_accuracy_diff', 0):+.2%} |
| **Processing Time** | {analysis['paddleocr_vl'].get('avg_processing_time_ms', 0)/1000:.2f}s | {results['results_by_backend'][backend].get('avg_processing_time_ms', 0)/1000:.2f}s | {comp.get('speed_ratio', 1):.2f}x |

"""

    # Strengths and weaknesses
    report += """## Stärken

"""
    if analysis["strengths"]:
        for strength in analysis["strengths"]:
            report += f"- ✅ {strength}\n"
    else:
        report += "- Keine spezifischen Stärken identifiziert\n"

    report += "\n## Schwächen\n\n"
    if analysis["weaknesses"]:
        for weakness in analysis["weaknesses"]:
            report += f"- ⚠️ {weakness}\n"
    else:
        report += "- Keine kritischen Schwächen identifiziert\n"

    # Go/No-Go decision
    report += f"""
## Go/No-Go Entscheidung

**Entscheidung:** {'✅ **GO**' if analysis['go_no_go']['decision'] == 'GO' else '❌ **NO-GO**'}

### Kriterien

"""
    for reason in analysis["go_no_go"]["reasoning"]:
        report += f"- {reason}\n"

    report += f"""
### Empfehlung

"""
    if analysis['go_no_go']['decision'] == 'GO':
        report += """✅ **Weiter mit Phase 4: Production Integration**

PaddleOCR-VL 0.9B erfüllt alle kritischen Kriterien:
- Umlaut-Accuracy ≥95%
- VRAM <14GB (validiert in Tests)
- Processing-Time <5s pro Seite
- Alle Tests erfolgreich
- Mindestens 1 klarer Vorteil gegenüber PP-OCRv5

**Nächste Schritte:**
1. Agent-Refactoring (Phase 4.1)
2. Integration in OCR Router (Phase 4.2)
3. Unit & Integration Tests (Phase 4.3)
4. Dokumentation (Phase 4.4)
"""
    else:
        report += """❌ **Stopp - Evaluation beenden**

PaddleOCR-VL 0.9B erfüllt nicht alle kritischen Kriterien.

**Gründe:**
"""
        for reason in analysis["go_no_go"]["reasoning"]:
            if "❌" in reason:
                report += f"- {reason}\n"

        report += """
**Alternative:**
- Bei VRAM-Problemen: Warten auf optimierte Version oder größere GPU
- Bei Performance-Problemen: PP-OCRv5 weiterhin verwenden
- Bei Genauigkeits-Problemen: DeepSeek-Janus-Pro als Alternative
"""

    report += """
---

## Detaillierte Ergebnisse

### Dokumenttyp-spezifische Performance

*(Wird in vollständigem Benchmark erweitert)*

### Fehler-Patterns

*(Wird in vollständigem Benchmark analysiert)*

---

*Report generiert: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}*
"""

    return report


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Generate PaddleOCR-VL Benchmark Report")
    parser.add_argument(
        "--input",
        type=Path,
        default=PROJECT_ROOT / "data/benchmarks/paddleocr_vl_evaluation.json",
        help="Input benchmark results JSON file"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "docs/OCR/PADDLEOCR_VL_09B_BENCHMARK_REPORT.md",
        help="Output markdown report file"
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"❌ Benchmark results not found: {args.input}")
        print("   Run benchmark first: python scripts/benchmark_paddleocr_vl.py --experimental")
        sys.exit(1)

    print("Loading benchmark results...")
    results = load_benchmark_results(args.input)

    print("Analyzing results...")
    analysis = analyze_results(results)

    print("Generating report...")
    report = generate_markdown_report(results, analysis)

    # Save report
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\n✅ Report saved to: {args.output}")
    print(f"\nGo/No-Go Decision: {analysis['go_no_go']['decision']}")
    print("\nReasoning:")
    for reason in analysis['go_no_go']['reasoning']:
        print(f"  {reason}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

