# -*- coding: utf-8 -*-
"""Test-Konfiguration fuer die Execution-Layer-Validator-Tests (OPEN-60/05).

Die Tests hier importieren `from Validators...`. Das Paket `Validators` liegt unter
`Execution_Layer/` im Repo-Root (im Container `/app/Execution_Layer`), ist aber nicht
auf `sys.path`. Ohne diesen Fix scheitern 3 Module mit `ModuleNotFoundError: Validators`
und brechen damit die GESAMTE `tests/unit`-Collection ab (pytest exit -> `unit`-Stufe
des A-Z-Loops dauerhaft rot).

Dieses conftest legt `Execution_Layer` auf den Pfad. Falls das Verzeichnis fehlt
(z. B. in einer reduzierten CI-Umgebung), werden die abhaengigen Tests aus der
Collection genommen statt einen Abbruch zu verursachen.
"""
import importlib.util
import sys
from pathlib import Path

_exec_layer = Path(__file__).resolve().parents[3] / "Execution_Layer"
if _exec_layer.is_dir() and str(_exec_layer) not in sys.path:
    sys.path.insert(0, str(_exec_layer))

# Defensive: wenn `Validators` trotzdem nicht aufloest, die Validator-Tests
# ignorieren (kein Collection-Abbruch der gesamten Unit-Suite).
collect_ignore_glob: list[str] = []
if importlib.util.find_spec("Validators") is None:
    collect_ignore_glob = ["test_*validator*.py"]
