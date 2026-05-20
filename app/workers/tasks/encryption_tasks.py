# -*- coding: utf-8 -*-
"""Celery Tasks fuer Field-Level Encryption.

Hintergrund-Tasks fuer:
- Migration bestehender Klartext-Daten zu verschluesselten Werten
- Key-Rotation fuer einzelne Felder
- Verifizierung aller verschluesselten Felder

DSGVO Art. 32 - Sicherheit der Verarbeitung.
Feinpoliert und durchdacht - Sichere Hintergrund-Verschluesselung.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Union

import structlog

from app.workers.celery_app import celery_app
from app.db.session import get_async_session_context
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

# Type alias fuer Task-Rueckgabewerte
EncryptionTaskResult = Dict[str, Union[str, int, bool, None]]


# =============================================================================
# Feld-Migration (Klartext -> Verschluesselt)
# =============================================================================


@celery_app.task(
    name="encryption.migrate_field",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
    acks_late=True,
    reject_on_worker_lost=True,
)
def encrypt_field_task(
    self,  # type: ignore[override]
    table_name: str,
    column_name: str,
    batch_size: int = 500,
) -> EncryptionTaskResult:
    """Verschluesselt eine Spalte (Hintergrund-Migration).

    Verarbeitet alle Klartext-Werte in der angegebenen Spalte
    und verschluesselt sie mit AES-256-GCM.

    Args:
        table_name: Name der Tabelle.
        column_name: Name der zu verschluesselnden Spalte.
        batch_size: Anzahl Zeilen pro Batch (Standard: 500).

    Returns:
        Dict mit Ergebnis der Migration.
    """
    logger.info(
        "encryption_task_started",
        task_id=self.request.id,
        table=table_name,
        column=column_name,
        batch_size=batch_size,
    )

    async def _run() -> EncryptionTaskResult:
        from app.services.encryption.field_encryption_service import (
            FieldEncryptionService,
        )

        async with get_async_session_context() as session:
            service = FieldEncryptionService(session)

            try:
                rows_encrypted = await service.encrypt_existing_data(
                    table_name=table_name,
                    column_name=column_name,
                    batch_size=batch_size,
                )

                result: EncryptionTaskResult = {
                    "status": "completed",
                    "tabelle": table_name,
                    "spalte": column_name,
                    "zeilen_verschluesselt": rows_encrypted,
                    "fehler": None,
                }

                logger.info(
                    "encryption_task_completed",
                    task_id=self.request.id,
                    **{k: str(v) for k, v in result.items()},
                )
                return result

            except ValueError as exc:
                error_result: EncryptionTaskResult = {
                    "status": "failed",
                    "tabelle": table_name,
                    "spalte": column_name,
                    "zeilen_verschluesselt": 0,
                    "fehler": str(exc),
                }
                logger.error(
                    "encryption_task_validation_error",
                    task_id=self.request.id,
                    error=str(exc),
                )
                return error_result

            except Exception as exc:
                logger.error(
                    "encryption_task_failed",
                    task_id=self.request.id,
                    **safe_error_log(exc),
                )
                raise self.retry(exc=exc)

    return asyncio.run(_run())


# =============================================================================
# Key-Rotation
# =============================================================================


@celery_app.task(
    name="encryption.rotate_key",
    bind=True,
    max_retries=1,
    default_retry_delay=300,
    acks_late=True,
    reject_on_worker_lost=True,
)
def rotate_key_task(
    self,  # type: ignore[override]
    table_name: str,
    column_name: str,
    batch_size: int = 500,
) -> EncryptionTaskResult:
    """Rotiert den Key fuer eine verschluesselte Spalte.

    Entschluesselt alle Werte mit dem alten Key und verschluesselt
    sie mit dem neuen Key.

    Args:
        table_name: Name der Tabelle.
        column_name: Name der Spalte.
        batch_size: Anzahl Zeilen pro Batch.

    Returns:
        Dict mit Ergebnis der Rotation.
    """
    logger.info(
        "key_rotation_task_started",
        task_id=self.request.id,
        table=table_name,
        column=column_name,
    )

    async def _run() -> EncryptionTaskResult:
        from app.services.encryption.field_encryption_service import (
            FieldEncryptionService,
        )

        async with get_async_session_context() as session:
            service = FieldEncryptionService(session)

            try:
                rows_rotated = await service.rotate_key(
                    table_name=table_name,
                    column_name=column_name,
                    batch_size=batch_size,
                )

                result: EncryptionTaskResult = {
                    "status": "completed",
                    "tabelle": table_name,
                    "spalte": column_name,
                    "zeilen_rotiert": rows_rotated,
                    "fehler": None,
                }

                logger.info(
                    "key_rotation_task_completed",
                    task_id=self.request.id,
                    **{k: str(v) for k, v in result.items()},
                )
                return result

            except ValueError as exc:
                error_result: EncryptionTaskResult = {
                    "status": "failed",
                    "tabelle": table_name,
                    "spalte": column_name,
                    "zeilen_rotiert": 0,
                    "fehler": str(exc),
                }
                return error_result

            except Exception as exc:
                logger.error(
                    "key_rotation_task_failed",
                    task_id=self.request.id,
                    **safe_error_log(exc),
                )
                raise self.retry(exc=exc)

    return asyncio.run(_run())


# =============================================================================
# Verifizierung
# =============================================================================


@celery_app.task(
    name="encryption.verify_all",
    bind=True,
    max_retries=0,
)
def verify_encryption_task(
    self,  # type: ignore[override]
    sample_size: int = 10,
) -> Dict[str, List[Dict[str, object]]]:
    """Verifiziert alle verschluesselten Felder.

    Prueft eine Stichprobe pro Feld und gibt aggregierte Ergebnisse zurueck.

    Args:
        sample_size: Anzahl zu pruefender Zeilen pro Feld.

    Returns:
        Dict mit Verifizierungsergebnissen pro Feld.
    """
    logger.info(
        "encryption_verify_task_started",
        task_id=self.request.id,
        sample_size=sample_size,
    )

    async def _run() -> Dict[str, List[Dict[str, object]]]:
        from app.services.encryption.field_encryption_service import (
            FieldEncryptionService,
            ENCRYPTED_FIELDS,
        )

        async with get_async_session_context() as session:
            service = FieldEncryptionService(session)
            results: List[Dict[str, object]] = []

            for field in ENCRYPTED_FIELDS:
                try:
                    verification = await service.verify_encryption(
                        table_name=field["table"],
                        column_name=field["column"],
                        sample_size=sample_size,
                    )
                    results.append(verification)
                except ValueError as exc:
                    results.append({
                        "tabelle": field["table"],
                        "spalte": field["column"],
                        "fehler": str(exc),
                        "intakt": False,
                    })

            all_intact = all(
                r.get("intakt", False) for r in results
            )

            logger.info(
                "encryption_verify_task_completed",
                task_id=self.request.id,
                fields_checked=len(results),
                all_intact=all_intact,
            )

            return {
                "ergebnisse": results,
            }

    return asyncio.run(_run())
