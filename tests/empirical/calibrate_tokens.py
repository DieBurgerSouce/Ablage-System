#!/usr/bin/env python3
"""Token estimation calibration using actual Claude API responses.

Samples real Claude API calls to measure actual token usage vs estimates,
then builds correction factors to improve TokenCounter accuracy.

IMPORTANT: This script makes actual API calls to Claude and incurs costs.
Use sparingly and with appropriate sample sizes.

Usage:
    python tests/empirical/calibrate_tokens.py --samples 50
    python tests/empirical/calibrate_tokens.py --samples 20 --model opus
    python tests/empirical/calibrate_tokens.py --report-only  # View existing calibration
"""

import asyncio
import argparse
import sys
import json
import os
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import logging

# Add orchestration to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / ".claude" / "orchestration"))

try:
    from anthropic import AsyncAnthropic
except ImportError:
    print("❌ anthropic package not installed")
    print("   Install with: pip install anthropic")
    sys.exit(1)

from token_counter import TokenCounter, ContentType

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class CalibrationSample:
    """Single token estimation calibration sample."""
    sample_id: str
    text: str
    content_type: str
    model: str
    estimated_tokens: int
    actual_input_tokens: int
    actual_output_tokens: int
    actual_total_tokens: int
    error_pct: float
    timestamp: str

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class CalibrationReport:
    """Aggregated calibration statistics."""
    total_samples: int
    by_content_type: Dict[str, Dict]
    by_model: Dict[str, Dict]
    overall_stats: Dict
    timestamp: str

    def to_dict(self) -> Dict:
        return asdict(self)


class TokenCalibrator:
    """Calibrates token estimation against actual Claude API usage."""

    CALIBRATION_FILE = Path(".claude/cache/token_calibration.json")

    def __init__(self, api_key: Optional[str] = None):
        """Initialize calibrator with API key."""
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not found. Set environment variable or pass api_key parameter."
            )

        self.client = AsyncAnthropic(api_key=self.api_key)
        self.counter = TokenCounter()
        self.samples: List[CalibrationSample] = self._load_samples()

    def _load_samples(self) -> List[CalibrationSample]:
        """Load existing calibration samples from file."""
        if not self.CALIBRATION_FILE.exists():
            return []

        try:
            with open(self.CALIBRATION_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

            samples = [
                CalibrationSample(**sample)
                for sample in data.get("samples", [])
            ]
            logger.info(f"Loaded {len(samples)} existing calibration samples")
            return samples

        except Exception as e:
            logger.warning(f"Could not load calibration file: {e}")
            return []

    def _save_samples(self):
        """Save calibration samples to file."""
        self.CALIBRATION_FILE.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "samples": [sample.to_dict() for sample in self.samples],
            "last_updated": datetime.now().isoformat()
        }

        with open(self.CALIBRATION_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved {len(self.samples)} calibration samples")

    async def calibrate_sample(
        self,
        text: str,
        content_type: ContentType,
        model: str = "claude-sonnet-4-5-20250929"
    ) -> CalibrationSample:
        """Calibrate single text sample against actual API usage.

        Makes real API call to Claude to get actual token counts.
        """

        # Estimate tokens
        estimated = self.counter.count_tokens(text, content_type=content_type)

        logger.info(f"Estimated {estimated} tokens for {content_type.value} sample")

        # Make actual API call
        try:
            response = await self.client.messages.create(
                model=model,
                max_tokens=10,  # Minimal output to reduce cost
                messages=[{
                    "role": "user",
                    "content": f"Count to 5: {text[:100]}"  # Minimal task
                }]
            )

            # Extract actual token counts
            actual_input = response.usage.input_tokens
            actual_output = response.usage.output_tokens
            actual_total = actual_input + actual_output

            # Calculate error
            error_pct = abs(estimated - actual_input) / actual_input if actual_input > 0 else 0.0

            logger.info(
                f"Actual: {actual_input} input, {actual_output} output "
                f"(Error: {error_pct:.1%})"
            )

            sample = CalibrationSample(
                sample_id=f"{model}_{content_type.value}_{len(self.samples)}",
                text=text[:200],  # Store snippet only
                content_type=content_type.value,
                model=model,
                estimated_tokens=estimated,
                actual_input_tokens=actual_input,
                actual_output_tokens=actual_output,
                actual_total_tokens=actual_total,
                error_pct=error_pct,
                timestamp=datetime.now().isoformat()
            )

            self.samples.append(sample)
            self._save_samples()

            return sample

        except Exception as e:
            logger.error(f"API call failed: {e}")
            raise

    async def calibrate_batch(
        self,
        samples_per_type: int = 10,
        model: str = "claude-sonnet-4-5-20250929"
    ):
        """Calibrate multiple samples across content types.

        Args:
            samples_per_type: Number of samples per content type
            model: Claude model to use for calibration
        """

        # Sample texts for each content type
        sample_texts = {
            ContentType.PROSE: [
                "The quick brown fox jumps over the lazy dog.",
                "In a hole in the ground there lived a hobbit. Not a nasty, dirty, wet hole.",
                "It was the best of times, it was the worst of times.",
                "Call me Ishmael. Some years ago—never mind how long precisely—having little or no money in my purse.",
                "All happy families are alike; each unhappy family is unhappy in its own way.",
                "It is a truth universally acknowledged, that a single man in possession of a good fortune, must be in want of a wife.",
                "Whether I shall turn out to be the hero of my own life, or whether that station will be held by anybody else.",
                "The sun shone, having no alternative, on the nothing new.",
                "Someone must have slandered Josef K., for one morning, without having done anything truly wrong, he was arrested.",
                "Stately, plump Buck Mulligan came from the stairhead, bearing a bowl of lather on which a mirror and a razor lay crossed."
            ][:samples_per_type],

            ContentType.CODE: [
                "async def process_document(doc_id: str) -> Dict[str, Any]:\n    return await db.get(doc_id)",
                "class UserService:\n    def __init__(self, db: Database):\n        self.db = db",
                "for item in items:\n    if item.valid:\n        results.append(process(item))",
                "def calculate_score(data: List[float]) -> float:\n    return sum(data) / len(data) if data else 0.0",
                "import asyncio\nimport json\nfrom pathlib import Path\n\nasync def main():\n    pass",
                "@dataclass\nclass User:\n    id: str\n    name: str\n    email: str",
                "try:\n    result = process()\nexcept Exception as e:\n    logger.error(f'Failed: {e}')",
                "return [\n    {\"id\": i, \"value\": v}\n    for i, v in enumerate(values)\n]",
                "if __name__ == '__main__':\n    asyncio.run(main())",
                "logger.info('task_completed', task_id=task_id, duration=duration)"
            ][:samples_per_type],

            ContentType.JSON: [
                '{"name": "John", "age": 30, "city": "New York"}',
                '{"status": "success", "data": {"count": 42, "items": []}}',
                '{"error": null, "result": {"id": "abc123", "timestamp": "2024-01-01T00:00:00Z"}}',
                '{"users": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]}',
                '{"config": {"debug": true, "timeout": 30, "retries": 3}}',
                '{"metrics": {"requests": 1000, "errors": 5, "latency_ms": 250}}',
                '{"items": [1, 2, 3, 4, 5], "total": 5, "page": 1}',
                '{"auth": {"token": "xyz", "expires": 3600}, "user": {"id": "u123"}}',
                '{"type": "notification", "message": "Task complete", "level": "info"}',
                '{"query": {"filters": [], "sort": "asc", "limit": 100}}'
            ][:samples_per_type],

            ContentType.MARKDOWN: [
                "# Heading\n\nThis is a paragraph with **bold** and *italic* text.",
                "## Installation\n\n```bash\npip install package\n```\n\nDone!",
                "- Item 1\n- Item 2\n  - Nested item\n- Item 3",
                "1. First step\n2. Second step\n3. Third step\n\nAll done.",
                "> This is a quote\n>\n> -- Author",
                "[Link text](https://example.com) and ![Image](image.png)",
                "| Column 1 | Column 2 |\n|----------|----------|\n| Value 1  | Value 2  |",
                "---\n\nHorizontal rule above.",
                "<!-- Comment -->\n\nVisible text below.",
                "`inline code` and [reference][1]\n\n[1]: https://example.com"
            ][:samples_per_type]
        }

        logger.info(f"Starting calibration with {samples_per_type} samples per type")

        # Calibrate each content type
        for content_type, texts in sample_texts.items():
            logger.info(f"\nCalibrating {content_type.value} samples...")

            for idx, text in enumerate(texts, 1):
                try:
                    logger.info(f"  [{idx}/{len(texts)}] Processing sample...")
                    sample = await self.calibrate_sample(text, content_type, model)

                    if sample.error_pct > 0.20:  # >20% error
                        logger.warning(
                            f"    High error: {sample.error_pct:.1%} "
                            f"(Est: {sample.estimated_tokens}, Actual: {sample.actual_input_tokens})"
                        )

                    # Small delay to avoid rate limits
                    await asyncio.sleep(1)

                except Exception as e:
                    logger.error(f"  Sample {idx} failed: {e}")
                    continue

        logger.info(f"\n✅ Calibration complete: {len(self.samples)} total samples")

    def generate_report(self) -> CalibrationReport:
        """Generate calibration statistics report."""

        if not self.samples:
            logger.warning("No calibration samples available")
            return CalibrationReport(
                total_samples=0,
                by_content_type={},
                by_model={},
                overall_stats={},
                timestamp=datetime.now().isoformat()
            )

        # Overall statistics
        all_errors = [s.error_pct for s in self.samples]
        overall_stats = {
            "mean_error": sum(all_errors) / len(all_errors),
            "max_error": max(all_errors),
            "min_error": min(all_errors),
            "samples_count": len(self.samples)
        }

        # Statistics by content type
        by_content_type = {}
        for content_type in ["prose", "code", "json", "markdown"]:
            type_samples = [s for s in self.samples if s.content_type == content_type]
            if not type_samples:
                continue

            errors = [s.error_pct for s in type_samples]
            by_content_type[content_type] = {
                "sample_count": len(type_samples),
                "mean_error": sum(errors) / len(errors),
                "max_error": max(errors),
                "mean_estimated": sum(s.estimated_tokens for s in type_samples) / len(type_samples),
                "mean_actual": sum(s.actual_input_tokens for s in type_samples) / len(type_samples)
            }

        # Statistics by model
        by_model = {}
        for model in set(s.model for s in self.samples):
            model_samples = [s for s in self.samples if s.model == model]
            errors = [s.error_pct for s in model_samples]

            by_model[model] = {
                "sample_count": len(model_samples),
                "mean_error": sum(errors) / len(errors),
                "max_error": max(errors)
            }

        return CalibrationReport(
            total_samples=len(self.samples),
            by_content_type=by_content_type,
            by_model=by_model,
            overall_stats=overall_stats,
            timestamp=datetime.now().isoformat()
        )

    def print_report(self):
        """Print formatted calibration report."""

        report = self.generate_report()

        if report.total_samples == 0:
            print("\n❌ No calibration data available")
            print("   Run calibration first: python calibrate_tokens.py --samples 10")
            return

        print("\n" + "="*70)
        print("TOKEN ESTIMATION CALIBRATION REPORT")
        print("="*70)
        print(f"\nTotal Samples: {report.total_samples}")
        print(f"Overall Mean Error: {report.overall_stats['mean_error']:.1%}")
        print(f"Overall Max Error: {report.overall_stats['max_error']:.1%}")

        print("\n" + "-"*70)
        print("BY CONTENT TYPE")
        print("-"*70)

        for content_type, stats in report.by_content_type.items():
            print(f"\n{content_type.upper()}")
            print(f"  Samples: {stats['sample_count']}")
            print(f"  Mean Error: {stats['mean_error']:.1%}")
            print(f"  Max Error: {stats['max_error']:.1%}")
            print(f"  Mean Estimated: {stats['mean_estimated']:.0f} tokens")
            print(f"  Mean Actual: {stats['mean_actual']:.0f} tokens")

        print("\n" + "-"*70)
        print("BY MODEL")
        print("-"*70)

        for model, stats in report.by_model.items():
            print(f"\n{model}")
            print(f"  Samples: {stats['sample_count']}")
            print(f"  Mean Error: {stats['mean_error']:.1%}")
            print(f"  Max Error: {stats['max_error']:.1%}")

        print("\n" + "-"*70)
        print("TARGET ACCURACY")
        print("-"*70)

        mean_error = report.overall_stats['mean_error']
        status = "✅" if mean_error < 0.10 else "⚠️" if mean_error < 0.20 else "❌"

        print(f"{status} Mean Error < 10%: {mean_error:.1%}")
        print("   Target: < 10% for production use")
        print("   Current: " + ("PASS" if mean_error < 0.10 else "NEEDS IMPROVEMENT"))

        print("\n" + "="*70)


async def main():
    parser = argparse.ArgumentParser(
        description="Calibrate token estimation against Claude API"
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=10,
        help="Number of samples per content type (default: 10)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="claude-sonnet-4-5-20250929",
        choices=[
            "claude-opus-4-5-20251101",
            "claude-sonnet-4-5-20250929",
            "claude-haiku-4-5-20250929"
        ],
        help="Claude model to use for calibration"
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Only show report, don't run new calibration"
    )

    args = parser.parse_args()

    # Check for API key
    if not os.environ.get("ANTHROPIC_API_KEY") and not args.report_only:
        print("\n❌ ANTHROPIC_API_KEY environment variable not set")
        print("   Set your API key: export ANTHROPIC_API_KEY='your-key-here'")
        print("   Or use --report-only to view existing calibration data")
        return

    try:
        calibrator = TokenCalibrator()

        if args.report_only:
            # Only show report
            calibrator.print_report()
        else:
            # Run calibration
            print(f"\n⚠️  WARNING: This will make ~{args.samples * 4} API calls to Claude")
            print(f"   Model: {args.model}")
            print(f"   Estimated cost: ~${args.samples * 4 * 0.003:.2f} (rough estimate)")
            print("\nPress Ctrl+C to cancel, or wait 5 seconds to continue...")

            await asyncio.sleep(5)

            print("\n🚀 Starting calibration...")
            await calibrator.calibrate_batch(
                samples_per_type=args.samples,
                model=args.model
            )

            # Show report
            calibrator.print_report()

            print(f"\n💾 Calibration data saved to: {calibrator.CALIBRATION_FILE}")

    except KeyboardInterrupt:
        print("\n\n❌ Calibration cancelled by user")
    except Exception as e:
        logger.error(f"Calibration failed: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
