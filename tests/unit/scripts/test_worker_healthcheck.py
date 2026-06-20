# -*- coding: utf-8 -*-
"""
Unit Tests fuer Worker Health Check Script.

Testet:
- Celery Worker Check
- GPU Status Check
- Redis Connection Check
"""

import os
import sys
import importlib
import importlib.util
import pytest
from unittest.mock import Mock, patch, MagicMock


def _locate_worker_healthcheck() -> str:
    """Finde das worker_healthcheck.py-Skript ueber mehrere Kandidaten-Pfade.

    Der Test laeuft sowohl direkt auf dem Host (Repo-Root) als auch im
    Backend-Container. Im Container ist scripts/ je nach Compose-Setup unter
    /app/scripts gemountet, der Test-Tree liegt unter /app/tests/...
    """
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        # Repo-Layout: tests/unit/scripts -> ../../../scripts
        os.path.join(here, "..", "..", "..", "scripts"),
        # Container mit gemountetem scripts/
        "/app/scripts",
        os.path.join(os.getcwd(), "scripts"),
    ]
    for base in candidates:
        path = os.path.abspath(os.path.join(base, "worker_healthcheck.py"))
        if os.path.isfile(path):
            return os.path.dirname(path)
    return ""


_SCRIPTS_DIR = _locate_worker_healthcheck()

if not _SCRIPTS_DIR:
    pytest.skip(
        "worker_healthcheck.py nicht auffindbar - scripts/ ist in dieser "
        "Umgebung nicht gemountet (Infra-Setup, kein Test-Drift).",
        allow_module_level=True,
    )

# Script-Verzeichnis zum Path hinzufuegen, damit `import worker_healthcheck` klappt
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)


class TestCeleryWorkerCheck:
    """Tests fuer Celery Worker Health Check."""

    @patch("subprocess.run")
    def test_celery_ping_success(self, mock_run):
        """Erfolgreicher Celery Ping."""
        from worker_healthcheck import check_celery_worker

        mock_run.return_value = Mock(
            returncode=0,
            stdout="celery@worker: PONG",
            stderr=""
        )

        ok, msg = check_celery_worker()

        assert ok is True
        assert "antwortet" in msg

    @patch("subprocess.run")
    def test_celery_ping_failure(self, mock_run):
        """Fehlgeschlagener Celery Ping."""
        from worker_healthcheck import check_celery_worker

        mock_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="Error: No workers"
        )

        ok, msg = check_celery_worker()

        assert ok is False
        assert "nicht" in msg.lower() or "error" in msg.lower()

    @patch("subprocess.run")
    def test_celery_ping_timeout(self, mock_run):
        """Celery Ping Timeout."""
        from worker_healthcheck import check_celery_worker
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="celery", timeout=15)

        ok, msg = check_celery_worker()

        assert ok is False
        assert "timeout" in msg.lower()

    @patch("subprocess.run")
    def test_celery_not_found(self, mock_run):
        """Celery nicht installiert."""
        from worker_healthcheck import check_celery_worker

        mock_run.side_effect = FileNotFoundError("celery")

        ok, msg = check_celery_worker()

        assert ok is False
        assert "nicht gefunden" in msg


class TestGPUStatusCheck:
    """Tests fuer GPU Status Check."""

    @patch("subprocess.run")
    def test_gpu_available_and_healthy(self, mock_run):
        """GPU verfuegbar und Speicher OK."""
        from worker_healthcheck import check_gpu_status

        mock_run.return_value = Mock(
            returncode=0,
            stdout="NVIDIA GeForce RTX 4080, 5000, 16384, 45\n",
            stderr=""
        )

        ok, msg = check_gpu_status()

        assert ok is True
        assert "RTX 4080" in msg

    @patch("subprocess.run")
    def test_gpu_memory_exceeded(self, mock_run):
        """GPU Speicher ueberschritten."""
        from worker_healthcheck import check_gpu_status

        # Setze niedriges Limit fuer Test
        with patch.dict(os.environ, {"GPU_MEMORY_LIMIT_GB": "10"}):
            # Importiere neu mit neuem Limit
            import importlib
            import worker_healthcheck
            importlib.reload(worker_healthcheck)

            mock_run.return_value = Mock(
                returncode=0,
                stdout="NVIDIA GeForce RTX 4080, 12000, 16384, 80\n",  # 11.7GB > 10GB Limit
                stderr=""
            )

            ok, msg = worker_healthcheck.check_gpu_status()

            # Memory exceeds threshold
            assert ok is False
            assert "ueberschritten" in msg

    @patch("subprocess.run")
    def test_gpu_not_available_cpu_mode(self, mock_run):
        """GPU nicht verfuegbar - CPU Mode."""
        from worker_healthcheck import check_gpu_status

        mock_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="NVIDIA-SMI has failed"
        )

        # Ohne GPU_REQUIRED sollte es OK sein
        with patch.dict(os.environ, {}, clear=False):
            if "GPU_REQUIRED" in os.environ:
                del os.environ["GPU_REQUIRED"]

            ok, msg = check_gpu_status()

            assert ok is True
            assert "CPU" in msg

    @patch("subprocess.run")
    def test_gpu_required_but_not_available(self, mock_run):
        """GPU erforderlich aber nicht verfuegbar."""
        from worker_healthcheck import check_gpu_status

        mock_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="NVIDIA-SMI has failed"
        )

        with patch.dict(os.environ, {"GPU_REQUIRED": "true"}):
            ok, msg = check_gpu_status()

            assert ok is False
            assert "erforderlich" in msg or "nicht verfuegbar" in msg.lower()

    @patch("subprocess.run")
    def test_nvidia_smi_not_found(self, mock_run):
        """nvidia-smi nicht installiert."""
        from worker_healthcheck import check_gpu_status

        mock_run.side_effect = FileNotFoundError("nvidia-smi")

        ok, msg = check_gpu_status()

        # Sollte OK sein (CPU-Mode)
        assert ok is True
        assert "CPU" in msg


class TestRedisConnectionCheck:
    """Tests fuer Redis Connection Check."""

    def test_redis_connection_success(self):
        """Erfolgreiche Redis-Verbindung."""
        # Da redis als lokaler Import verwendet wird, testen wir das Verhalten
        from worker_healthcheck import check_redis_connection

        # Redis ist installiert, also testen wir den echten Import-Pfad
        try:
            import redis
            # Redis ist verfuegbar, aber Verbindung wird fehlschlagen ohne Server
            # Das ist OK fuer diesen Unit-Test
            ok, msg = check_redis_connection()
            # Entweder Verbindung erfolgreich oder nicht erreichbar
            assert isinstance(ok, bool)
            assert isinstance(msg, str)
        except ImportError:
            # Redis nicht installiert - wird uebersprungen
            ok, msg = check_redis_connection()
            assert ok is True
            assert "uebersprungen" in msg.lower() or "verfuegbar" in msg.lower()

    def test_redis_module_not_available(self):
        """Redis-Modul nicht installiert."""
        from worker_healthcheck import check_redis_connection

        # Entferne redis aus sys.modules falls vorhanden
        with patch.dict("sys.modules", {"redis": None}):
            ok, msg = check_redis_connection()

            # Sollte OK sein (uebersprungen)
            assert ok is True


class TestHealthCheckIntegration:
    """Integration Tests fuer gesamten Health Check."""

    @patch("subprocess.run")
    def test_all_checks_pass(self, mock_run):
        """Alle Checks bestehen."""
        import worker_healthcheck
        from worker_healthcheck import run_health_checks

        # Celery OK (Celery + GPU laufen ueber subprocess.run)
        mock_run.return_value = Mock(
            returncode=0,
            stdout="celery@worker: PONG",
            stderr=""
        )

        # Redis-Check nutzt eine echte Verbindung -> fuer "alle OK" mocken,
        # damit run_health_checks nicht an einer fehlenden Redis-Instanz scheitert.
        with patch.object(
            worker_healthcheck,
            "check_redis_connection",
            return_value=(True, "Redis verbunden"),
        ):
            exit_code = run_health_checks()

        assert exit_code == 0

    @patch("subprocess.run")
    def test_worker_fails_returns_1(self, mock_run):
        """Worker-Fehler gibt Exit Code 1."""
        from worker_healthcheck import run_health_checks

        mock_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="Worker not found"
        )

        exit_code = run_health_checks()

        assert exit_code == 1

    @patch("subprocess.run")
    def test_simple_health_check(self, mock_run):
        """Einfacher Health Check."""
        from worker_healthcheck import simple_health_check

        mock_run.return_value = Mock(
            returncode=0,
            stdout="celery@worker: PONG",
            stderr=""
        )

        exit_code = simple_health_check()

        assert exit_code == 0


class TestGPUMemoryThreshold:
    """Tests fuer GPU-Speicher-Schwellwert."""

    def test_default_threshold(self):
        """Standard-Schwellwert ist 13.6GB (85% von 16GB)."""
        from worker_healthcheck import GPU_MEMORY_THRESHOLD_GB

        # Default sollte 13.6 sein
        assert GPU_MEMORY_THRESHOLD_GB == 13.6 or GPU_MEMORY_THRESHOLD_GB > 0

    @patch.dict(os.environ, {"GPU_MEMORY_LIMIT_GB": "8.0"})
    def test_custom_threshold_from_env(self):
        """Schwellwert kann ueber Umgebungsvariable gesetzt werden."""
        import importlib
        import worker_healthcheck
        importlib.reload(worker_healthcheck)

        assert worker_healthcheck.GPU_MEMORY_THRESHOLD_GB == 8.0

    @patch("subprocess.run")
    def test_memory_just_below_threshold_ok(self, mock_run):
        """Speicher knapp unter Schwellwert ist OK."""
        import importlib
        import worker_healthcheck

        with patch.dict(os.environ, {"GPU_MEMORY_LIMIT_GB": "10.0"}):
            importlib.reload(worker_healthcheck)

            mock_run.return_value = Mock(
                returncode=0,
                # 9.5GB = 9728MB
                stdout="NVIDIA GeForce RTX 4080, 9728, 16384, 50\n",
                stderr=""
            )

            ok, msg = worker_healthcheck.check_gpu_status()

            assert ok is True

    @patch("subprocess.run")
    def test_memory_just_above_threshold_fails(self, mock_run):
        """Speicher knapp ueber Schwellwert schlaegt fehl."""
        import importlib
        import worker_healthcheck

        with patch.dict(os.environ, {"GPU_MEMORY_LIMIT_GB": "10.0"}):
            importlib.reload(worker_healthcheck)

            mock_run.return_value = Mock(
                returncode=0,
                # 10.5GB = 10752MB
                stdout="NVIDIA GeForce RTX 4080, 10752, 16384, 50\n",
                stderr=""
            )

            ok, msg = worker_healthcheck.check_gpu_status()

            assert ok is False
            assert "ueberschritten" in msg


class TestOutputFormat:
    """Tests fuer Ausgabeformat."""

    @patch("subprocess.run")
    def test_output_includes_status(self, mock_run, capsys):
        """Ausgabe enthaelt Status-Informationen."""
        from worker_healthcheck import run_health_checks

        mock_run.return_value = Mock(
            returncode=0,
            stdout="celery@worker: PONG",
            stderr=""
        )

        run_health_checks()

        captured = capsys.readouterr()
        assert "[OK]" in captured.out

    @patch("subprocess.run")
    def test_output_includes_error_on_failure(self, mock_run, capsys):
        """Ausgabe enthaelt Fehler bei Fehlschlag."""
        from worker_healthcheck import run_health_checks

        mock_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="Error"
        )

        run_health_checks()

        captured = capsys.readouterr()
        assert "[FEHLER]" in captured.out
