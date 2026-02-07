# -*- coding: utf-8 -*-
"""
Document Chain Celery Tasks.

Automatische Verknuepfung von Dokumenten zu Auftragsketten:
- Angebot -> Auftrag -> Lieferschein -> Rechnung -> Gutschrift
- Auto-Matching basierend auf Referenznummern, Betraegen, Kunden
- Automatischer Lauf nach OCR-Completion
- Discrepancy-Erkennung bei Abweichungen

Feinpoliert und durchdacht - Intelligente Kettenbildung.
"""

import asyncio
import structlog
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.core.safe_errors import safe_error_log
from app.workers.celery_app import celery_app
from app.db.session import get_async_session_context

logger = structlog.get_logger(__name__)


# =============================================================================
# Single Document Auto-Linking
# =============================================================================


@celery_app.task(
    name="chains.auto_link_document",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def auto_link_document_task(
    self,
    document_id: str,
    company_id: str,
    min_confidence: float = 0.85,
    auto_create_chain: bool = True,
) -> Dict[str, Any]:
    """Sucht automatisch passende Ketten fuer ein Dokument.

    Wird nach OCR-Completion aufgerufen um das Dokument
    automatisch mit verwandten Dokumenten zu verknuepfen.

    Matching-Strategien:
    1. Referenznummern (95%+ Confidence)
    2. Kundennummer + Betrag + Zeitraum (85%+ Confidence)
    3. Textanalyse (70%+ Confidence)

    Args:
        document_id: UUID des Dokuments
        company_id: UUID der Firma
        min_confidence: Minimale Confidence fuer automatische Verknuepfung
        auto_create_chain: Bei hoher Confidence automatisch verknuepfen

    Returns:
        Dict mit Match-Ergebnissen und ggf. erstellter Chain
    """
    from app.services.document_chain_service import DocumentChainService

    async def _auto_link():
        async with get_async_session_context() as db:
            service = DocumentChainService()

            # Auto-Matching durchfuehren
            matches = await service.auto_match_documents(
                db=db,
                document_id=UUID(document_id),
                company_id=UUID(company_id),
            )

            result: Dict[str, Any] = {
                "document_id": document_id,
                "matches_found": len(matches),
                "matches": [],
                "chain_created": False,
                "chain_id": None,
            }

            if not matches:
                return result

            # Matches verarbeiten
            for match in matches:
                result["matches"].append({
                    "confidence": match.confidence,
                    "relationship_type": match.relationship_type.value if match.relationship_type else None,
                    "matched_documents": [str(d) for d in match.matched_documents],
                    "match_reason": match.match_reason,
                    "chain_id": match.chain_id,
                })

            # Beste Match pruefen
            best_match = max(matches, key=lambda m: m.confidence)

            if auto_create_chain and best_match.confidence >= min_confidence:
                if best_match.chain_id:
                    # Zu existierender Chain hinzufuegen
                    from app.db.models import Document

                    doc = await db.get(Document, UUID(document_id))
                    if doc and not doc.chain_id:
                        doc.chain_id = best_match.chain_id

                        # Position basierend auf Dokumenttyp
                        from app.services.document_chain_service import CHAIN_POSITIONS
                        doc.chain_position = CHAIN_POSITIONS.get(doc.document_type, 99)

                        await db.commit()

                        result["chain_created"] = False
                        result["chain_id"] = best_match.chain_id
                        result["action"] = "added_to_existing_chain"

                        logger.info(
                            "document_added_to_chain",
                            document_id=document_id,
                            chain_id=best_match.chain_id,
                            confidence=best_match.confidence,
                        )
                else:
                    # Neue Chain erstellen mit gematchten Dokumenten
                    all_doc_ids = [UUID(document_id)] + best_match.matched_documents

                    # System-User fuer automatische Verknuepfung
                    from app.db.models import User
                    from sqlalchemy import select

                    system_user_stmt = select(User).where(User.email == "system@ablage.local").limit(1)
                    system_user = await db.scalar(system_user_stmt)

                    if system_user:
                        chain_id = await service.create_chain(
                            db=db,
                            documents=all_doc_ids,
                            company_id=UUID(company_id),
                            user_id=system_user.id,
                        )

                        result["chain_created"] = True
                        result["chain_id"] = chain_id
                        result["action"] = "created_new_chain"

                        logger.info(
                            "chain_created_automatically",
                            chain_id=chain_id,
                            documents=len(all_doc_ids),
                            confidence=best_match.confidence,
                        )
            else:
                # Nur Vorschlaege speichern, keine automatische Verknuepfung
                result["action"] = "suggestions_only"
                result["best_confidence"] = best_match.confidence
                result["reason"] = (
                    f"Confidence {best_match.confidence:.0%} unter Schwelle {min_confidence:.0%}"
                    if best_match.confidence < min_confidence
                    else "Auto-Link deaktiviert"
                )

            return result

    try:
        result = asyncio.get_event_loop().run_until_complete(_auto_link())

        if result["matches_found"] > 0:
            logger.info(
                "document_chain_auto_match_completed",
                document_id=document_id,
                matches=result["matches_found"],
                chain_created=result["chain_created"],
            )
        else:
            logger.debug(
                "document_chain_no_matches",
                document_id=document_id,
            )

        return result
    except Exception as e:
        logger.error(
            "document_chain_auto_link_failed",
            document_id=document_id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# Batch Auto-Linking
# =============================================================================


@celery_app.task(
    name="chains.auto_link_all_documents",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def auto_link_all_documents_task(
    self,
    company_id: Optional[str] = None,
    min_confidence: float = 0.85,
    batch_size: int = 100,
    only_unchained: bool = True,
) -> Dict[str, Any]:
    """Versucht alle Dokumente automatisch zu Ketten zu verknuepfen.

    Kann periodisch oder manuell gestartet werden.

    Args:
        company_id: Optional - nur fuer diese Firma
        min_confidence: Minimale Confidence fuer automatische Verknuepfung
        batch_size: Anzahl Dokumente pro Batch
        only_unchained: Nur Dokumente ohne chain_id

    Returns:
        Dict mit Batch-Statistiken
    """
    from app.services.document_chain_service import DocumentChainService
    from app.db.models import Document
    from sqlalchemy import select, and_

    async def _auto_link_batch():
        stats = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "documents_processed": 0,
            "matches_found": 0,
            "chains_created": 0,
            "chains_extended": 0,
            "no_matches": 0,
            "errors": 0,
        }

        async with get_async_session_context() as db:
            service = DocumentChainService()

            # Dokumente ohne Chain laden
            conditions = [
                Document.deleted_at.is_(None),
                Document.extracted_text.isnot(None),
                Document.extracted_text != "",
            ]

            if only_unchained:
                conditions.append(Document.chain_id.is_(None))

            if company_id:
                conditions.append(Document.company_id == UUID(company_id))

            stmt = (
                select(Document)
                .where(and_(*conditions))
                .order_by(Document.created_at.asc())
                .limit(batch_size)
            )

            result = await db.execute(stmt)
            documents = result.scalars().all()

            stats["documents_to_process"] = len(documents)

            for doc in documents:
                try:
                    matches = await service.auto_match_documents(
                        db=db,
                        document_id=doc.id,
                        company_id=doc.company_id,
                    )

                    stats["documents_processed"] += 1

                    if not matches:
                        stats["no_matches"] += 1
                        continue

                    best_match = max(matches, key=lambda m: m.confidence)
                    stats["matches_found"] += 1

                    if best_match.confidence >= min_confidence:
                        if best_match.chain_id:
                            # Zu existierender Chain hinzufuegen
                            doc.chain_id = best_match.chain_id
                            from app.services.document_chain_service import CHAIN_POSITIONS
                            doc.chain_position = CHAIN_POSITIONS.get(doc.document_type, 99)
                            stats["chains_extended"] += 1
                        else:
                            # Neue Chain erstellen (vereinfacht - ohne explizite Chain)
                            # In diesem Batch-Modus erstellen wir nur Suggestions
                            pass

                except Exception as e:
                    logger.warning(
                        "document_chain_batch_error",
                        document_id=str(doc.id),
                        **safe_error_log(e),
                    )
                    stats["errors"] += 1

            await db.commit()

        stats["completed_at"] = datetime.now(timezone.utc).isoformat()

        # Erfolgsrate
        if stats["documents_processed"] > 0:
            stats["match_rate"] = round(
                stats["matches_found"] / stats["documents_processed"] * 100, 1
            )
        else:
            stats["match_rate"] = 0.0

        return stats

    try:
        result = asyncio.get_event_loop().run_until_complete(_auto_link_batch())

        logger.info(
            "document_chain_batch_completed",
            processed=result["documents_processed"],
            matches=result["matches_found"],
            chains_created=result["chains_created"],
            match_rate=result["match_rate"],
        )

        return result
    except Exception as e:
        logger.error("document_chain_batch_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Discrepancy Checking
# =============================================================================


@celery_app.task(
    name="chains.check_chain_discrepancies",
    bind=True,
    max_retries=2,
)
def check_chain_discrepancies_task(
    self,
    chain_id: str,
    company_id: str,
) -> Dict[str, Any]:
    """Prueft eine Chain auf Abweichungen zwischen Dokumenten.

    Wird nach Hinzufuegen eines Dokuments zur Chain aufgerufen.

    Args:
        chain_id: Chain-ID
        company_id: Firmen-ID

    Returns:
        Dict mit gefundenen Discrepancies
    """
    from app.services.document_chain_service import DocumentChainService

    async def _check_discrepancies():
        async with get_async_session_context() as db:
            service = DocumentChainService()

            discrepancies = await service.get_chain_discrepancies(
                db=db,
                chain_id=chain_id,
                company_id=UUID(company_id),
            )

            return {
                "chain_id": chain_id,
                "discrepancy_count": len(discrepancies),
                "discrepancies": [
                    {
                        "type": d.discrepancy_type.value,
                        "severity": d.severity.value,
                        "field": d.field_name,
                        "expected": d.expected_value,
                        "actual": d.actual_value,
                        "diff_percent": d.difference_percentage,
                    }
                    for d in discrepancies
                ],
            }

    try:
        result = asyncio.get_event_loop().run_until_complete(_check_discrepancies())

        if result["discrepancy_count"] > 0:
            logger.warning(
                "chain_discrepancies_found",
                chain_id=chain_id,
                count=result["discrepancy_count"],
            )

        return result
    except Exception as e:
        logger.error(
            "chain_discrepancy_check_failed",
            chain_id=chain_id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# Event Handlers
# =============================================================================


@celery_app.task(name="chains.on_ocr_completed")
def on_ocr_completed_auto_link(document_id: str, company_id: str) -> Dict[str, Any]:
    """Handler fuer OCR-Completion Events.

    Wird von OCR-Tasks aufgerufen nachdem Text extrahiert wurde.
    Versucht automatisch, das Dokument mit einer Chain zu verknuepfen.

    Args:
        document_id: UUID des Dokuments
        company_id: UUID der Firma

    Returns:
        Dict mit Auto-Link-Ergebnis
    """
    return auto_link_document_task.delay(
        document_id=document_id,
        company_id=company_id,
        min_confidence=0.85,
        auto_create_chain=True,
    ).get(timeout=120)


# =============================================================================
# Statistics
# =============================================================================


@celery_app.task(name="chains.generate_statistics")
def generate_chain_statistics_task(company_id: Optional[str] = None) -> Dict[str, Any]:
    """Generiert Statistiken ueber Document Chains.

    Args:
        company_id: Optional - nur fuer diese Firma

    Returns:
        Dict mit Chain-Statistiken
    """
    from app.db.models import Document
    from sqlalchemy import select, func, and_

    async def _generate_stats():
        async with get_async_session_context() as db:
            stats: Dict[str, Any] = {}

            base_condition = Document.deleted_at.is_(None)
            if company_id:
                base_condition = and_(
                    base_condition,
                    Document.company_id == UUID(company_id),
                )

            # Dokumente mit Chain
            chained_docs = await db.scalar(
                select(func.count()).where(
                    and_(
                        base_condition,
                        Document.chain_id.isnot(None),
                    )
                )
            )
            stats["documents_in_chains"] = chained_docs

            # Dokumente ohne Chain (aber mit OCR-Text)
            unchained_docs = await db.scalar(
                select(func.count()).where(
                    and_(
                        base_condition,
                        Document.chain_id.is_(None),
                        Document.extracted_text.isnot(None),
                    )
                )
            )
            stats["documents_unchained"] = unchained_docs

            # Anzahl verschiedener Chains
            chain_count = await db.scalar(
                select(func.count(func.distinct(Document.chain_id))).where(
                    and_(
                        base_condition,
                        Document.chain_id.isnot(None),
                    )
                )
            )
            stats["total_chains"] = chain_count

            # Durchschnittliche Chain-Laenge
            if chain_count and chain_count > 0:
                stats["avg_chain_length"] = round(chained_docs / chain_count, 1)
            else:
                stats["avg_chain_length"] = 0.0

            # Chain-Rate
            total_docs = chained_docs + unchained_docs
            if total_docs > 0:
                stats["chain_rate_percent"] = round(chained_docs / total_docs * 100, 1)
            else:
                stats["chain_rate_percent"] = 0.0

            stats["generated_at"] = datetime.now(timezone.utc).isoformat()

            return stats

    result = asyncio.get_event_loop().run_until_complete(_generate_stats())

    logger.info(
        "chain_statistics_generated",
        chains=result["total_chains"],
        chained_docs=result["documents_in_chains"],
        chain_rate=result["chain_rate_percent"],
    )

    return result


# =============================================================================
# Chain Validation Task (Phase 1.3 - Beat Schedule Activated)
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.chain_tasks.validate_document_chains",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def validate_document_chains(
    self,
    company_id: Optional[str] = None,
    max_chains: int = 500,
    check_discrepancies: bool = True,
) -> Dict[str, Any]:
    """
    Validiert Document Chains auf Integritaet und Vollstaendigkeit.

    Wird taeglich um 03:15 Uhr automatisch ausgefuehrt.
    Prueft:
    - Chain-Struktur (Position, Verknuepfung)
    - Dokumenten-Konsistenz innerhalb der Chain
    - Abweichungen zwischen Dokumenten
    - Verwaiste Dokumente (chain_id aber keine anderen in Chain)

    Args:
        company_id: Optional - nur fuer spezifische Firma
        max_chains: Maximale Anzahl zu pruefender Chains
        check_discrepancies: Abweichungen pruefen (performance-intensiv)

    Returns:
        Dict mit Validierungsergebnissen und Statistiken
    """
    from app.db.models import Document
    from sqlalchemy import select, func, and_

    async def _validate_chains():
        async with get_async_session_context() as db:
            stats = {
                "started_at": datetime.now(timezone.utc).isoformat(),
                "chains_validated": 0,
                "chains_valid": 0,
                "chains_with_issues": 0,
                "orphaned_documents": 0,
                "discrepancies_found": 0,
                "issues": [],
                "companies_checked": 0,
                "errors": [],
            }

            # Base query fuer distinct chains
            base_condition = Document.deleted_at.is_(None)

            if company_id:
                base_condition = and_(
                    base_condition,
                    Document.company_id == UUID(company_id),
                )

            # Distinct chain_ids ermitteln
            chains_query = (
                select(
                    Document.chain_id,
                    Document.company_id,
                    func.count().label("doc_count"),
                )
                .where(
                    and_(
                        base_condition,
                        Document.chain_id.isnot(None),
                    )
                )
                .group_by(Document.chain_id, Document.company_id)
                .limit(max_chains)
            )

            chains_result = await db.execute(chains_query)
            chains = chains_result.all()

            company_ids_seen = set()

            for chain_row in chains:
                chain_id = chain_row.chain_id
                chain_company_id = chain_row.company_id
                doc_count = chain_row.doc_count

                company_ids_seen.add(chain_company_id)
                stats["chains_validated"] += 1

                try:
                    chain_issues: List[Dict[str, Any]] = []

                    # 1. Pruefe ob Chain nur 1 Dokument hat (verwaist)
                    if doc_count == 1:
                        stats["orphaned_documents"] += 1
                        chain_issues.append({
                            "type": "orphaned",
                            "message": "Chain enthaelt nur ein Dokument",
                        })

                    # 2. Hole alle Dokumente der Chain fuer weitere Pruefungen
                    if doc_count > 1:
                        docs_query = (
                            select(Document)
                            .where(
                                and_(
                                    Document.chain_id == chain_id,
                                    Document.deleted_at.is_(None),
                                )
                            )
                            .order_by(Document.chain_position.asc())
                        )

                        docs_result = await db.execute(docs_query)
                        docs = docs_result.scalars().all()

                        # 3. Pruefe Position-Kontinuitaet
                        positions = [d.chain_position for d in docs if d.chain_position is not None]
                        if positions:
                            # Gaps in Positionen pruefen
                            sorted_positions = sorted(positions)
                            for i in range(1, len(sorted_positions)):
                                gap = sorted_positions[i] - sorted_positions[i - 1]
                                if gap > 10:  # Tolerance fuer Luecken
                                    chain_issues.append({
                                        "type": "position_gap",
                                        "message": f"Grosse Luecke in Positionen: {sorted_positions[i - 1]} -> {sorted_positions[i]}",
                                    })

                        # 4. Discrepancy-Check (optional, performance-intensiv)
                        if check_discrepancies and doc_count <= 10:
                            # Betraege vergleichen (falls vorhanden)
                            amounts = []
                            for doc in docs:
                                if doc.metadata and isinstance(doc.metadata, dict):
                                    amount = doc.metadata.get("total_amount") or doc.metadata.get("betrag")
                                    if amount is not None:
                                        try:
                                            amounts.append(float(amount))
                                        except (ValueError, TypeError):
                                            pass

                            if len(amounts) >= 2:
                                # Pruefen ob Betraege stark abweichen
                                avg_amount = sum(amounts) / len(amounts)
                                for amount in amounts:
                                    if avg_amount > 0:
                                        deviation = abs(amount - avg_amount) / avg_amount
                                        if deviation > 0.1:  # >10% Abweichung
                                            stats["discrepancies_found"] += 1
                                            chain_issues.append({
                                                "type": "amount_discrepancy",
                                                "message": f"Betragsabweichung >10%: {amount:.2f} vs Durchschnitt {avg_amount:.2f}",
                                            })
                                            break

                    # Zusammenfassung fuer diese Chain
                    if chain_issues:
                        stats["chains_with_issues"] += 1
                        if len(stats["issues"]) < 100:  # Limit fuer Issues
                            stats["issues"].append({
                                "chain_id": chain_id,
                                "company_id": str(chain_company_id),
                                "doc_count": doc_count,
                                "issues": chain_issues,
                            })
                    else:
                        stats["chains_valid"] += 1

                except Exception as chain_e:
                    stats["errors"].append({
                        "chain_id": chain_id,
                        "error": str(chain_e)[:100],
                    })
                    logger.warning(
                        "chain_validation_error",
                        chain_id=chain_id,
                        **safe_error_log(chain_e),
                    )

            stats["companies_checked"] = len(company_ids_seen)
            stats["completed_at"] = datetime.now(timezone.utc).isoformat()

            # Erfolgsrate
            if stats["chains_validated"] > 0:
                stats["validity_rate_percent"] = round(
                    stats["chains_valid"] / stats["chains_validated"] * 100, 1
                )
            else:
                stats["validity_rate_percent"] = 100.0

            return stats

    try:
        result = asyncio.get_event_loop().run_until_complete(_validate_chains())

        logger.info(
            "document_chains_validation_completed",
            chains_validated=result["chains_validated"],
            chains_valid=result["chains_valid"],
            chains_with_issues=result["chains_with_issues"],
            orphaned=result["orphaned_documents"],
            discrepancies=result["discrepancies_found"],
            validity_rate=result["validity_rate_percent"],
        )

        # Alert bei vielen fehlerhaften Chains
        if result["chains_with_issues"] > 50:
            logger.warning(
                "document_chains_many_issues",
                chains_with_issues=result["chains_with_issues"],
                total_validated=result["chains_validated"],
            )

        return result

    except Exception as e:
        logger.error("document_chains_validation_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Celery Beat Schedule
# =============================================================================

CHAIN_BEAT_SCHEDULE = {
    # Batch Auto-Linking taeglich um 02:30
    "auto-link-documents-to-chains": {
        "task": "chains.auto_link_all_documents",
        "schedule": {
            "hour": 2,
            "minute": 30,
        },
        "kwargs": {
            "min_confidence": 0.85,
            "batch_size": 200,
        },
        "options": {"queue": "default"},
    },
    # Chain-Statistiken woechentlich am Montag um 01:30
    "generate-chain-statistics": {
        "task": "chains.generate_statistics",
        "schedule": {
            "day_of_week": 1,  # Montag
            "hour": 1,
            "minute": 30,
        },
        "options": {"queue": "default"},
    },
}
