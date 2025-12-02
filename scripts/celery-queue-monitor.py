#!/usr/bin/env python3
"""
celery-queue-monitor.py - Celery Queue Health Monitoring

Ueberwacht Celery Worker und Queues fuer das Ablage-System:
- Queue-Laengen und Durchsatz
- Worker-Status und Task-Verteilung
- Stuck Tasks und Retries
- Echtzeit-Metriken

Verwendung:
    python scripts/celery-queue-monitor.py [--watch] [--export-metrics]
"""

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

try:
    from celery import Celery
    from celery.result import AsyncResult
    import redis
except ImportError:
    print("Benoetigte Pakete: pip install celery redis")
    sys.exit(1)


# Konfiguration
REDIS_URL = "redis://localhost:6380/0"
BROKER_URL = "redis://localhost:6380/0"

# Queue-Namen
QUEUES = [
    "celery",
    "ocr_high",
    "ocr_normal",
    "ocr_batch",
    "embeddings",
    "notifications",
    "cleanup",
]

# Schwellenwerte fuer Warnungen
THRESHOLDS = {
    "queue_length_warn": 100,
    "queue_length_critical": 500,
    "stuck_task_minutes": 30,
    "retry_rate_warn": 0.1,  # 10%
}


class CeleryQueueMonitor:
    """Monitor fuer Celery Queues und Worker."""

    def __init__(self, broker_url: str = BROKER_URL):
        """Initialisiert den Monitor.

        Args:
            broker_url: Redis Broker URL
        """
        self.app = Celery(broker=broker_url)
        self.redis_client = redis.from_url(REDIS_URL)
        self._stats_history: List[Dict] = []

    def get_queue_lengths(self) -> Dict[str, int]:
        """Holt aktuelle Queue-Laengen.

        Returns:
            Dict mit Queue-Namen und Laengen
        """
        lengths = {}
        for queue in QUEUES:
            try:
                length = self.redis_client.llen(queue)
                lengths[queue] = length
            except Exception as e:
                lengths[queue] = -1
                print(f"Fehler bei Queue {queue}: {e}")
        return lengths

    def get_worker_stats(self) -> Dict[str, Any]:
        """Holt Worker-Statistiken.

        Returns:
            Dict mit Worker-Informationen
        """
        try:
            inspect = self.app.control.inspect()

            # Aktive Worker
            active = inspect.active() or {}
            scheduled = inspect.scheduled() or {}
            reserved = inspect.reserved() or {}
            stats = inspect.stats() or {}

            workers = {}
            for worker_name in set(list(active.keys()) + list(stats.keys())):
                worker_stats = stats.get(worker_name, {})
                workers[worker_name] = {
                    "active_tasks": len(active.get(worker_name, [])),
                    "scheduled_tasks": len(scheduled.get(worker_name, [])),
                    "reserved_tasks": len(reserved.get(worker_name, [])),
                    "total_processed": worker_stats.get("total", {}).get(
                        "tasks.completed", 0
                    ),
                    "pool_size": worker_stats.get("pool", {}).get("max-concurrency", 0),
                    "uptime": worker_stats.get("uptime", 0),
                }

            return {
                "worker_count": len(workers),
                "workers": workers,
                "total_active": sum(w["active_tasks"] for w in workers.values()),
            }

        except Exception as e:
            return {"worker_count": 0, "workers": {}, "error": str(e)}

    def get_task_stats(self) -> Dict[str, Any]:
        """Holt Task-Statistiken aus Redis.

        Returns:
            Dict mit Task-Metriken
        """
        stats = {
            "pending": 0,
            "started": 0,
            "success": 0,
            "failure": 0,
            "retry": 0,
        }

        try:
            # Task-Results aus Redis scannen
            for key in self.redis_client.scan_iter("celery-task-meta-*"):
                try:
                    data = self.redis_client.get(key)
                    if data:
                        result = json.loads(data)
                        status = result.get("status", "UNKNOWN")
                        if status == "PENDING":
                            stats["pending"] += 1
                        elif status == "STARTED":
                            stats["started"] += 1
                        elif status == "SUCCESS":
                            stats["success"] += 1
                        elif status == "FAILURE":
                            stats["failure"] += 1
                        elif status == "RETRY":
                            stats["retry"] += 1
                except Exception:
                    pass

        except Exception as e:
            stats["error"] = str(e)

        # Berechne Retry-Rate
        total = stats["success"] + stats["failure"]
        if total > 0:
            stats["retry_rate"] = stats["retry"] / total
        else:
            stats["retry_rate"] = 0.0

        return stats

    def check_stuck_tasks(self, minutes: int = 30) -> List[Dict]:
        """Findet Tasks die laenger als X Minuten laufen.

        Args:
            minutes: Schwellenwert in Minuten

        Returns:
            Liste von stuck Tasks
        """
        stuck_tasks = []
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)

        try:
            inspect = self.app.control.inspect()
            active = inspect.active() or {}

            for worker_name, tasks in active.items():
                for task in tasks:
                    # Task-Start-Zeit parsen
                    time_start = task.get("time_start")
                    if time_start:
                        start_time = datetime.fromtimestamp(time_start)
                        if start_time < cutoff:
                            stuck_tasks.append(
                                {
                                    "task_id": task.get("id"),
                                    "name": task.get("name"),
                                    "worker": worker_name,
                                    "started": start_time.isoformat(),
                                    "running_minutes": (
                                        datetime.utcnow() - start_time
                                    ).total_seconds()
                                    / 60,
                                }
                            )

        except Exception as e:
            print(f"Fehler bei Stuck-Task-Check: {e}")

        return stuck_tasks

    def get_full_status(self) -> Dict[str, Any]:
        """Holt vollstaendigen Status.

        Returns:
            Dict mit allen Metriken
        """
        queue_lengths = self.get_queue_lengths()
        worker_stats = self.get_worker_stats()
        task_stats = self.get_task_stats()
        stuck_tasks = self.check_stuck_tasks(THRESHOLDS["stuck_task_minutes"])

        # Gesundheitsstatus berechnen
        health = "healthy"
        issues = []

        total_queue_length = sum(v for v in queue_lengths.values() if v >= 0)
        if total_queue_length > THRESHOLDS["queue_length_critical"]:
            health = "critical"
            issues.append(f"Queue-Laenge kritisch: {total_queue_length}")
        elif total_queue_length > THRESHOLDS["queue_length_warn"]:
            health = "warning"
            issues.append(f"Queue-Laenge erhoet: {total_queue_length}")

        if stuck_tasks:
            if health == "healthy":
                health = "warning"
            issues.append(f"{len(stuck_tasks)} stuck Task(s)")

        if task_stats.get("retry_rate", 0) > THRESHOLDS["retry_rate_warn"]:
            if health == "healthy":
                health = "warning"
            issues.append(
                f"Retry-Rate hoch: {task_stats['retry_rate']*100:.1f}%"
            )

        if worker_stats.get("worker_count", 0) == 0:
            health = "critical"
            issues.append("Keine Worker aktiv!")

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "health": health,
            "issues": issues,
            "queues": queue_lengths,
            "workers": worker_stats,
            "tasks": task_stats,
            "stuck_tasks": stuck_tasks,
        }

    def print_status(self, status: Dict[str, Any]) -> None:
        """Gibt Status formatiert aus.

        Args:
            status: Status-Dict
        """
        health_colors = {
            "healthy": "\033[92m",  # Gruen
            "warning": "\033[93m",  # Gelb
            "critical": "\033[91m",  # Rot
        }
        reset = "\033[0m"

        health = status["health"]
        color = health_colors.get(health, "")

        print("\n" + "=" * 60)
        print(f"  Celery Queue Monitor - {status['timestamp']}")
        print("=" * 60)

        # Gesundheit
        print(f"\nStatus: {color}{health.upper()}{reset}")
        if status["issues"]:
            for issue in status["issues"]:
                print(f"  - {issue}")

        # Queues
        print("\nQueues:")
        for queue, length in status["queues"].items():
            indicator = (
                "🔴"
                if length > THRESHOLDS["queue_length_critical"]
                else "🟡"
                if length > THRESHOLDS["queue_length_warn"]
                else "🟢"
            )
            print(f"  {indicator} {queue}: {length}")

        # Workers
        print(f"\nWorkers ({status['workers']['worker_count']} aktiv):")
        for worker_name, worker_info in status["workers"].get("workers", {}).items():
            print(f"  📦 {worker_name}")
            print(f"     Active: {worker_info['active_tasks']}, "
                  f"Reserved: {worker_info['reserved_tasks']}, "
                  f"Processed: {worker_info['total_processed']}")

        # Task Stats
        tasks = status["tasks"]
        print(f"\nTasks:")
        print(f"  Pending: {tasks['pending']}")
        print(f"  Started: {tasks['started']}")
        print(f"  Success: {tasks['success']}")
        print(f"  Failed: {tasks['failure']}")
        print(f"  Retrying: {tasks['retry']}")
        print(f"  Retry Rate: {tasks['retry_rate']*100:.2f}%")

        # Stuck Tasks
        if status["stuck_tasks"]:
            print(f"\n⚠️  Stuck Tasks ({len(status['stuck_tasks'])}):")
            for task in status["stuck_tasks"]:
                print(f"  - {task['name']} ({task['task_id'][:8]}...)")
                print(f"    Running: {task['running_minutes']:.0f} min on {task['worker']}")

        print("\n" + "=" * 60)

    def export_prometheus_metrics(self, status: Dict[str, Any]) -> str:
        """Exportiert Metriken im Prometheus-Format.

        Args:
            status: Status-Dict

        Returns:
            Prometheus-formatierte Metriken
        """
        lines = [
            "# HELP celery_queue_length Current queue length",
            "# TYPE celery_queue_length gauge",
        ]
        for queue, length in status["queues"].items():
            lines.append(f'celery_queue_length{{queue="{queue}"}} {length}')

        lines.extend([
            "# HELP celery_workers_total Number of active workers",
            "# TYPE celery_workers_total gauge",
            f"celery_workers_total {status['workers']['worker_count']}",
        ])

        lines.extend([
            "# HELP celery_tasks_total Total tasks by status",
            "# TYPE celery_tasks_total counter",
        ])
        for stat_name, value in status["tasks"].items():
            if stat_name != "retry_rate" and stat_name != "error":
                lines.append(f'celery_tasks_total{{status="{stat_name}"}} {value}')

        lines.extend([
            "# HELP celery_retry_rate Current retry rate",
            "# TYPE celery_retry_rate gauge",
            f"celery_retry_rate {status['tasks']['retry_rate']:.4f}",
        ])

        lines.extend([
            "# HELP celery_stuck_tasks Number of stuck tasks",
            "# TYPE celery_stuck_tasks gauge",
            f"celery_stuck_tasks {len(status['stuck_tasks'])}",
        ])

        return "\n".join(lines)

    def watch(self, interval: int = 5) -> None:
        """Kontinuierliche Ueberwachung.

        Args:
            interval: Update-Intervall in Sekunden
        """
        print("Starte kontinuierliche Ueberwachung (Ctrl+C zum Beenden)...")
        try:
            while True:
                # Terminal leeren
                print("\033[H\033[J", end="")

                status = self.get_full_status()
                self.print_status(status)

                time.sleep(interval)
        except KeyboardInterrupt:
            print("\nUeberwachung beendet.")


def main():
    """Hauptfunktion."""
    parser = argparse.ArgumentParser(
        description="Celery Queue Monitor fuer Ablage-System"
    )
    parser.add_argument(
        "--watch",
        "-w",
        action="store_true",
        help="Kontinuierliche Ueberwachung"
    )
    parser.add_argument(
        "--interval",
        "-i",
        type=int,
        default=5,
        help="Update-Intervall in Sekunden (default: 5)"
    )
    parser.add_argument(
        "--export-metrics",
        "-e",
        action="store_true",
        help="Prometheus-Metriken exportieren"
    )
    parser.add_argument(
        "--json",
        "-j",
        action="store_true",
        help="JSON-Output"
    )
    parser.add_argument(
        "--broker",
        "-b",
        default=BROKER_URL,
        help=f"Broker URL (default: {BROKER_URL})"
    )

    args = parser.parse_args()

    monitor = CeleryQueueMonitor(broker_url=args.broker)

    if args.watch:
        monitor.watch(interval=args.interval)
    else:
        status = monitor.get_full_status()

        if args.json:
            print(json.dumps(status, indent=2, default=str))
        elif args.export_metrics:
            print(monitor.export_prometheus_metrics(status))
        else:
            monitor.print_status(status)


if __name__ == "__main__":
    main()
