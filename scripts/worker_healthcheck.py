#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Worker Health Check Script.

Prueft den Status des Celery Workers und der GPU:
- Celery Worker Ping
- GPU-Verfuegbarkeit und Speicher
- Redis-Verbindung

Exit Codes:
    0 - Alles OK
    1 - Worker nicht erreichbar
    2 - GPU-Problem
    3 - Redis nicht erreichbar
"""

import os
import sys
import subprocess
import json
from typing import Tuple

# GPU Memory Threshold (default 85% von 16GB = 13.6GB)
GPU_MEMORY_THRESHOLD_GB = float(os.environ.get("GPU_MEMORY_LIMIT_GB", "13.6"))


def check_celery_worker() -> Tuple[bool, str]:
    """
    Prueft ob der Celery Worker antwortet.

    Returns:
        Tuple[bool, str]: (OK, Nachricht)
    """
    try:
        # Celery inspect ping
        result = subprocess.run(
            [
                "celery",
                "-A", "app.workers.celery_app",
                "inspect", "ping",
                "--timeout", "10"
            ],
            capture_output=True,
            text=True,
            timeout=15
        )

        if result.returncode == 0 and "pong" in result.stdout.lower():
            return True, "Celery Worker antwortet"
        else:
            return False, f"Celery Worker antwortet nicht: {result.stderr or result.stdout}"

    except subprocess.TimeoutExpired:
        return False, "Celery Worker Timeout"
    except FileNotFoundError:
        return False, "Celery nicht gefunden"
    except Exception as e:
        return False, f"Celery Check fehlgeschlagen: {e}"


def check_gpu_status() -> Tuple[bool, str]:
    """
    Prueft GPU-Verfuegbarkeit und Speichernutzung.

    Returns:
        Tuple[bool, str]: (OK, Nachricht)
    """
    try:
        # nvidia-smi fuer GPU Info
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.used,memory.total,utilization.gpu",
                "--format=csv,noheader,nounits"
            ],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            # GPU nicht verfuegbar - kann OK sein wenn CPU-only
            if "GPU_REQUIRED" in os.environ and os.environ["GPU_REQUIRED"] == "true":
                return False, "GPU erforderlich aber nicht verfuegbar"
            return True, "GPU nicht verfuegbar (CPU-Mode)"

        # Parse GPU Info
        lines = result.stdout.strip().split("\n")
        for line in lines:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 4:
                gpu_name = parts[0]
                memory_used_mb = float(parts[1])
                memory_total_mb = float(parts[2])
                gpu_util = float(parts[3]) if parts[3] else 0

                memory_used_gb = memory_used_mb / 1024

                # Pruefe Speicherlimit
                if memory_used_gb > GPU_MEMORY_THRESHOLD_GB:
                    return False, (
                        f"GPU Speicher ueberschritten: {memory_used_gb:.2f}GB "
                        f"(Limit: {GPU_MEMORY_THRESHOLD_GB}GB)"
                    )

                return True, (
                    f"GPU OK: {gpu_name}, "
                    f"Speicher: {memory_used_gb:.2f}GB/{memory_total_mb/1024:.1f}GB, "
                    f"Auslastung: {gpu_util}%"
                )

        return True, "GPU vorhanden"

    except subprocess.TimeoutExpired:
        return False, "nvidia-smi Timeout"
    except FileNotFoundError:
        # nvidia-smi nicht vorhanden - CPU-only Mode
        return True, "nvidia-smi nicht verfuegbar (CPU-Mode)"
    except Exception as e:
        return False, f"GPU Check fehlgeschlagen: {e}"


def check_redis_connection() -> Tuple[bool, str]:
    """
    Prueft Redis-Verbindung (wichtig fuer Celery Broker).

    Returns:
        Tuple[bool, str]: (OK, Nachricht)
    """
    try:
        import redis
    except ImportError:
        # Redis-Modul nicht installiert, ueberspringe
        return True, "Redis-Check uebersprungen (Modul nicht verfuegbar)"

    try:
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

        # Verbindung testen
        r = redis.from_url(redis_url)
        r.ping()
        return True, "Redis verbunden"

    except redis.ConnectionError:
        return False, "Redis nicht erreichbar"
    except Exception as e:
        return False, f"Redis Check fehlgeschlagen: {e}"


def run_health_checks() -> int:
    """
    Fuehrt alle Health Checks aus.

    Returns:
        Exit Code (0 = OK, >0 = Fehler)
    """
    results = []

    # 1. Celery Worker Check
    worker_ok, worker_msg = check_celery_worker()
    results.append(("Celery Worker", worker_ok, worker_msg))

    # 2. GPU Check (optional)
    gpu_ok, gpu_msg = check_gpu_status()
    results.append(("GPU", gpu_ok, gpu_msg))

    # 3. Redis Check
    redis_ok, redis_msg = check_redis_connection()
    results.append(("Redis", redis_ok, redis_msg))

    # Ausgabe
    all_ok = True
    for name, ok, msg in results:
        status = "OK" if ok else "FEHLER"
        print(f"[{status}] {name}: {msg}")
        if not ok:
            all_ok = False

    # Exit Code basierend auf kritischen Checks
    if not worker_ok:
        return 1
    if not gpu_ok and "GPU_REQUIRED" in os.environ:
        return 2
    if not redis_ok:
        return 3

    return 0 if all_ok else 1


def simple_health_check() -> int:
    """
    Einfacher Health Check nur fuer Celery Worker.

    Schneller als run_health_checks(), geeignet fuer Docker healthcheck.

    Returns:
        Exit Code (0 = OK, 1 = Fehler)
    """
    # Nur Worker pruefen
    worker_ok, worker_msg = check_celery_worker()

    if worker_ok:
        print(f"OK: {worker_msg}")
        return 0
    else:
        print(f"FEHLER: {worker_msg}")
        return 1


if __name__ == "__main__":
    # Argument-Verarbeitung
    if len(sys.argv) > 1 and sys.argv[1] == "--simple":
        exit_code = simple_health_check()
    else:
        exit_code = run_health_checks()

    sys.exit(exit_code)
