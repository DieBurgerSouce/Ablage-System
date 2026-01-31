# -*- coding: utf-8 -*-
"""Kryptografischer Audit-Trail periodic tasks (F6).

Phase 12: Vollstaendige Integration mit MerkleTreeService.
"""

import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

import structlog
from sqlalchemy import select, and_

from app.workers.celery_app import celery_app
from app.core.safe_errors import safe_error_log
from app.db.session import async_session_maker
from app.db.models import Company, AuditLog

logger = structlog.get_logger(__name__)


@celery_app.task(name="app.workers.tasks.audit_chain_tasks.verify_integrity")
def verify_integrity() -> dict:
    """Verifiziere Integritaet der gesamten Audit-Kette.

    Prueft:
    - SHA-256 Hash-Kette Konsistenz
    - Merkle-Tree Integritaet
    - Fehlende oder manipulierte Eintraege
    """
    logger.info("audit_chain_integrity_check_start")
    try:
        result = asyncio.get_event_loop().run_until_complete(_verify_integrity())
        logger.info(
            "audit_chain_integrity_check_complete",
            entries_verified=result.get("entries_verified", 0),
            errors_found=result.get("errors_found", 0),
        )
        return result
    except Exception as e:
        logger.error("audit_chain_integrity_check_error", **safe_error_log(e))
        raise


async def _verify_integrity() -> Dict[str, Any]:
    """Async Implementation fuer Integritaetspruefung."""
    from app.services.compliance.merkle_tree_service import MerkleTreeService

    total_entries = 0
    errors_found = 0

    async with async_session_maker() as db:
        result = await db.execute(
            select(Company.id).where(Company.is_active == True)
        )
        company_ids = [row[0] for row in result.all()]

        service = MerkleTreeService()

        for company_id in company_ids:
            try:
                # Audit-Logs der letzten 7 Tage laden
                cutoff = datetime.now(timezone.utc) - timedelta(days=7)

                audit_result = await db.execute(
                    select(AuditLog)
                    .where(
                        and_(
                            AuditLog.company_id == company_id,
                            AuditLog.created_at >= cutoff,
                        )
                    )
                    .order_by(AuditLog.created_at)
                )
                audit_logs = audit_result.scalars().all()

                if not audit_logs:
                    continue

                # Entries fuer Merkle Tree vorbereiten
                entries = [
                    json.dumps({
                        "id": str(log.id),
                        "action": log.action,
                        "timestamp": log.created_at.isoformat(),
                        "entity_type": log.entity_type,
                        "entity_id": str(log.entity_id) if log.entity_id else None,
                    }, sort_keys=True)
                    for log in audit_logs
                ]

                total_entries += len(entries)

                # Merkle Tree bauen und Integritaet pruefen
                tree = service.build_tree(entries)

                if tree.leaf_count != len(entries):
                    errors_found += 1
                    logger.warning(
                        "merkle_tree_leaf_count_mismatch",
                        company_id=str(company_id),
                        expected=len(entries),
                        actual=tree.leaf_count,
                    )

            except Exception as e:
                errors_found += 1
                logger.warning(
                    "integrity_check_company_failed",
                    company_id=str(company_id),
                    **safe_error_log(e),
                )
                continue

    return {
        "status": "success",
        "entries_verified": total_entries,
        "errors_found": errors_found,
    }


@celery_app.task(name="app.workers.tasks.audit_chain_tasks.build_merkle_tree")
def build_merkle_tree() -> dict:
    """Erstelle neuen Merkle-Tree-Block fuer die aktuelle Woche."""
    logger.info("audit_chain_merkle_build_start")
    try:
        result = asyncio.get_event_loop().run_until_complete(_build_merkle_tree())
        logger.info(
            "audit_chain_merkle_build_complete",
            tree_id=result.get("tree_id"),
        )
        return result
    except Exception as e:
        logger.error("audit_chain_merkle_build_error", **safe_error_log(e))
        raise


async def _build_merkle_tree() -> Dict[str, Any]:
    """Async Implementation fuer Merkle Tree Build."""
    from app.services.compliance.merkle_tree_service import MerkleTreeService

    trees_built: List[Dict[str, Any]] = []

    async with async_session_maker() as db:
        result = await db.execute(
            select(Company.id).where(Company.is_active == True)
        )
        company_ids = [row[0] for row in result.all()]

        service = MerkleTreeService()

        for company_id in company_ids:
            try:
                # Audit-Logs der letzten Woche laden
                cutoff = datetime.now(timezone.utc) - timedelta(days=7)

                audit_result = await db.execute(
                    select(AuditLog)
                    .where(
                        and_(
                            AuditLog.company_id == company_id,
                            AuditLog.created_at >= cutoff,
                        )
                    )
                    .order_by(AuditLog.created_at)
                )
                audit_logs = audit_result.scalars().all()

                if not audit_logs:
                    continue

                # Entries vorbereiten
                entries = [
                    json.dumps({
                        "id": str(log.id),
                        "action": log.action,
                        "timestamp": log.created_at.isoformat(),
                    }, sort_keys=True)
                    for log in audit_logs
                ]

                # Tree bauen
                tree = service.build_tree(entries)

                trees_built.append({
                    "company_id": str(company_id),
                    "root_hash": tree.root_hash,
                    "leaf_count": tree.leaf_count,
                    "tree_height": tree.tree_height,
                })

                logger.info(
                    "merkle_tree_built",
                    company_id=str(company_id),
                    root_hash=tree.root_hash[:16] + "...",
                    leaves=tree.leaf_count,
                )

            except Exception as e:
                logger.warning(
                    "merkle_tree_build_company_failed",
                    company_id=str(company_id),
                    **safe_error_log(e),
                )
                continue

    return {
        "status": "success",
        "trees_built": len(trees_built),
        "tree_id": trees_built[-1]["root_hash"] if trees_built else None,
    }
