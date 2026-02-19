"""Folder-Import + Import-Regel Tasks - DEPRECATED.

Alle Tasks wurden in import_tasks.py konsolidiert.
Dieses Modul existiert nur fuer Rueckwaertskompatibilitaet bestehender
Celery-Task-Referenzen.

Migration: Verwende stattdessen die Tasks aus app.workers.tasks.import_tasks
"""

import structlog
from app.workers.tasks.import_tasks import (
    poll_all_folder_configs as _poll_all,
    apply_rules_to_pending_imports as _apply_pending,
    scan_import_folder as _scan_folder,
)

logger = structlog.get_logger(__name__)

# Backward-compatible aliases - Tasks sind in import_tasks.py definiert
poll_folder_imports_task = _poll_all
apply_rules_to_pending_imports_task = _apply_pending
scan_import_folder_task = _scan_folder
