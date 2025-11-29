#!/usr/bin/env python
"""
Real-time VRAM Monitor for Ablage-System OCR Backends.

Monitors GPU memory usage during OCR processing with threshold alerting.
Use this to verify VRAM stays under 85% (13.6GB) during processing.

Usage:
    # Monitor for 60 seconds with 1 second interval
    python scripts/vram_monitor.py

    # Monitor for 5 minutes with 2 second interval
    python scripts/vram_monitor.py --duration 300 --interval 2

    # Custom threshold (default is 13.6GB = 85% of 16GB)
    python scripts/vram_monitor.py --threshold 12.0

    # Output to CSV file
    python scripts/vram_monitor.py --output vram_log.csv
"""

import argparse
import csv
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class VRAMReading:
    """Single VRAM measurement."""
    timestamp: datetime
    allocated_gb: float
    reserved_gb: float
    total_gb: float
    free_gb: float
    utilization_percent: float


class VRAMMonitor:
    """Real-time VRAM monitoring with alerting."""

    # RTX 4080 threshold (85% of 16GB)
    DEFAULT_THRESHOLD_GB = 13.6

    def __init__(
        self,
        threshold_gb: float = DEFAULT_THRESHOLD_GB,
        output_file: Optional[str] = None,
    ):
        """Initialize VRAM monitor.

        Args:
            threshold_gb: Alert threshold in GB
            output_file: Optional CSV file for logging
        """
        self.threshold_gb = threshold_gb
        self.output_file = output_file
        self.readings: list[VRAMReading] = []
        self.peak_allocated_gb = 0.0
        self.peak_reserved_gb = 0.0
        self.alert_count = 0

        self._torch_available = False
        self._csv_writer = None
        self._csv_file = None

        self._setup_torch()
        self._setup_csv()

    def _setup_torch(self):
        """Setup PyTorch and verify GPU."""
        try:
            import torch
            self._torch_available = torch.cuda.is_available()
            if self._torch_available:
                self.gpu_name = torch.cuda.get_device_name(0)
                props = torch.cuda.get_device_properties(0)
                self.total_gb = props.total_memory / (1024**3)
            else:
                self.gpu_name = "No GPU"
                self.total_gb = 0.0
        except ImportError:
            self._torch_available = False
            self.gpu_name = "PyTorch not installed"
            self.total_gb = 0.0

    def _setup_csv(self):
        """Setup CSV logging if output file specified."""
        if self.output_file:
            self._csv_file = open(self.output_file, "w", newline="")
            self._csv_writer = csv.writer(self._csv_file)
            self._csv_writer.writerow([
                "timestamp",
                "allocated_gb",
                "reserved_gb",
                "free_gb",
                "utilization_percent",
                "status",
            ])

    def get_reading(self) -> Optional[VRAMReading]:
        """Get current VRAM reading."""
        if not self._torch_available:
            return None

        import torch

        try:
            allocated = torch.cuda.memory_allocated(0) / (1024**3)
            reserved = torch.cuda.memory_reserved(0) / (1024**3)
            total = self.total_gb
            free = total - allocated
            utilization = (allocated / total) * 100 if total > 0 else 0

            reading = VRAMReading(
                timestamp=datetime.now(),
                allocated_gb=round(allocated, 2),
                reserved_gb=round(reserved, 2),
                total_gb=round(total, 2),
                free_gb=round(free, 2),
                utilization_percent=round(utilization, 1),
            )

            # Track peaks
            self.peak_allocated_gb = max(self.peak_allocated_gb, allocated)
            self.peak_reserved_gb = max(self.peak_reserved_gb, reserved)

            # Check threshold
            if allocated > self.threshold_gb:
                self.alert_count += 1

            return reading

        except Exception as e:
            print(f"Error reading VRAM: {e}", file=sys.stderr)
            return None

    def log_reading(self, reading: VRAMReading):
        """Log reading to CSV if enabled."""
        if self._csv_writer and reading:
            status = "WARNING" if reading.allocated_gb > self.threshold_gb else "OK"
            self._csv_writer.writerow([
                reading.timestamp.isoformat(),
                reading.allocated_gb,
                reading.reserved_gb,
                reading.free_gb,
                reading.utilization_percent,
                status,
            ])
            self._csv_file.flush()

    def print_reading(self, reading: VRAMReading, elapsed: float):
        """Print reading to console."""
        status = "WARNING!" if reading.allocated_gb > self.threshold_gb else "OK"
        print(
            f"[{elapsed:6.1f}s] "
            f"Alloc: {reading.allocated_gb:5.2f}GB | "
            f"Rsrvd: {reading.reserved_gb:5.2f}GB | "
            f"Free: {reading.free_gb:5.2f}GB | "
            f"Util: {reading.utilization_percent:5.1f}% | "
            f"{status}"
        )

    def monitor(
        self,
        duration_seconds: float = 60.0,
        interval_seconds: float = 1.0,
    ) -> dict:
        """
        Monitor VRAM for specified duration.

        Args:
            duration_seconds: How long to monitor
            interval_seconds: Interval between readings

        Returns:
            Summary statistics
        """
        if not self._torch_available:
            print("ERROR: GPU not available for monitoring", file=sys.stderr)
            return {"error": "GPU not available"}

        print("\n" + "=" * 70)
        print(f"VRAM MONITOR - {self.gpu_name}")
        print(f"Total: {self.total_gb:.1f}GB | Threshold: {self.threshold_gb:.1f}GB")
        print("=" * 70)
        print(f"Monitoring for {duration_seconds}s at {interval_seconds}s intervals\n")

        start_time = time.time()
        iterations = int(duration_seconds / interval_seconds)

        try:
            for i in range(iterations):
                reading = self.get_reading()
                if reading:
                    self.readings.append(reading)
                    elapsed = time.time() - start_time
                    self.print_reading(reading, elapsed)
                    self.log_reading(reading)

                time.sleep(interval_seconds)

        except KeyboardInterrupt:
            print("\nMonitoring interrupted by user.")

        return self.get_summary()

    def get_summary(self) -> dict:
        """Get summary statistics."""
        if not self.readings:
            return {"error": "No readings collected"}

        allocated_values = [r.allocated_gb for r in self.readings]
        utilization_values = [r.utilization_percent for r in self.readings]

        summary = {
            "gpu_name": self.gpu_name,
            "total_gb": self.total_gb,
            "threshold_gb": self.threshold_gb,
            "duration_seconds": (
                self.readings[-1].timestamp - self.readings[0].timestamp
            ).total_seconds() if len(self.readings) > 1 else 0,
            "num_readings": len(self.readings),
            "peak_allocated_gb": round(self.peak_allocated_gb, 2),
            "peak_reserved_gb": round(self.peak_reserved_gb, 2),
            "avg_allocated_gb": round(sum(allocated_values) / len(allocated_values), 2),
            "avg_utilization_percent": round(
                sum(utilization_values) / len(utilization_values), 1
            ),
            "alert_count": self.alert_count,
            "threshold_exceeded": self.peak_allocated_gb > self.threshold_gb,
        }

        return summary

    def print_summary(self):
        """Print summary to console."""
        summary = self.get_summary()

        if "error" in summary:
            print(f"\nError: {summary['error']}")
            return

        print("\n" + "-" * 70)
        print("MONITORING SUMMARY")
        print("-" * 70)
        print(f"GPU: {summary['gpu_name']}")
        print(f"Duration: {summary['duration_seconds']:.1f}s ({summary['num_readings']} readings)")
        print(f"Peak Allocated: {summary['peak_allocated_gb']:.2f}GB")
        print(f"Peak Reserved: {summary['peak_reserved_gb']:.2f}GB")
        print(f"Avg Allocated: {summary['avg_allocated_gb']:.2f}GB")
        print(f"Avg Utilization: {summary['avg_utilization_percent']:.1f}%")
        print(f"Threshold Alerts: {summary['alert_count']}")

        if summary["threshold_exceeded"]:
            print(f"\n[WARNING] Peak VRAM exceeded threshold of {summary['threshold_gb']:.1f}GB!")
        else:
            print(f"\n[OK] VRAM stayed under threshold of {summary['threshold_gb']:.1f}GB")

        if self.output_file:
            print(f"\nLog saved to: {self.output_file}")

        print("-" * 70 + "\n")

    def close(self):
        """Close any open resources."""
        if self._csv_file:
            self._csv_file.close()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Real-time VRAM monitor for Ablage-System OCR backends"
    )
    parser.add_argument(
        "--duration", "-d",
        type=float,
        default=60.0,
        help="Monitoring duration in seconds (default: 60)"
    )
    parser.add_argument(
        "--interval", "-i",
        type=float,
        default=1.0,
        help="Reading interval in seconds (default: 1.0)"
    )
    parser.add_argument(
        "--threshold", "-t",
        type=float,
        default=13.6,
        help="Alert threshold in GB (default: 13.6 = 85%% of 16GB)"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output CSV file for logging"
    )
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    monitor = VRAMMonitor(
        threshold_gb=args.threshold,
        output_file=args.output,
    )

    try:
        monitor.monitor(
            duration_seconds=args.duration,
            interval_seconds=args.interval,
        )
        monitor.print_summary()

    finally:
        monitor.close()

    # Exit with error if threshold exceeded
    summary = monitor.get_summary()
    if summary.get("threshold_exceeded"):
        sys.exit(1)


if __name__ == "__main__":
    main()
