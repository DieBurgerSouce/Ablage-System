"""GoBD Audit Chain Service - Blockchain-ähnliche Ereignis-Verkettung.

Implementiert eine unveränderbare Hash-Kette für GoBD-konforme
Nachvollziehbarkeit aller Dokumenten-Operationen.

Eigenschaften:
- APPEND-ONLY: Neue Einträge werden nur angehaengt
- IMMUTABLE: Bestehende Einträge werden nie geändert
- VERIFIABLE: Jeder Eintrag kann durch Hash-Vergleich verifiziert werden
- TAMPER-EVIDENT: Manipulationen werden durch Kettenbruch erkannt

Die Kette ist ähnlich einer Blockchain aufgebaut:
- Jeder Eintrag hat einen Hash des vorherigen Eintrags
- Der kombinierte Hash ist: SHA256(previous_hash + content_hash)
- Der erste Eintrag (Genesis) hat keinen previous_hash
"""

import hashlib
import json
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum

import structlog
from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.bpmn_models.gobd import AuditChainEntry, AuditChainEventType

logger = structlog.get_logger(__name__)


class ChainVerificationStatus(str, Enum):
    """Status der Kettenverifikation."""
    VALID = "valid"
    INVALID = "invalid"
    BROKEN_AT = "broken_at"
    EMPTY = "empty"


@dataclass
class ChainVerificationResult:
    """Ergebnis einer Kettenverifikation."""
    status: ChainVerificationStatus
    total_entries: int
    verified_entries: int
    broken_at_sequence: Optional[int] = None
    broken_entry_id: Optional[uuid.UUID] = None
    error_message: Optional[str] = None
    verification_time_ms: float = 0


@dataclass
class ChainEntry:
    """Datenstruktur für einen neuen Chain-Eintrag."""
    event_type: AuditChainEventType
    event_data: Dict[str, Any]
    document_id: Optional[uuid.UUID] = None
    user_id: Optional[uuid.UUID] = None


class AuditChainService:
    """Service für die Verwaltung der GoBD Audit-Chain.

    Die Audit-Chain ist eine unveränderbare Ereigniskette,
    die alle relevanten Dokumenten-Operationen protokolliert.
    """

    HASH_ALGORITHM = "sha256"
    GENESIS_PREVIOUS_HASH = "0" * 64  # 64 Nullen für Genesis-Block

    async def append_entry(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        entry: ChainEntry,
        tsa_timestamp: Optional[datetime] = None,
        tsa_token: Optional[str] = None,
        tsa_provider: Optional[str] = None,
    ) -> AuditChainEntry:
        """Fuegt einen neuen Eintrag zur Audit-Chain hinzu.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            entry: Der neue Eintrag
            tsa_timestamp: Optionaler RFC 3161 Zeitstempel
            tsa_token: Optionales TSA Response Token
            tsa_provider: Name des TSA-Providers

        Returns:
            Der erstellte AuditChainEntry

        Raises:
            ValueError: Bei ungültigem Entry
        """
        # 1. Hole den letzten Eintrag der Company
        last_entry = await self._get_last_entry(db, company_id)

        # 2. Berechne Sequenznummer
        if last_entry is None:
            sequence_number = 1
            previous_hash = None  # Genesis
        else:
            sequence_number = last_entry.sequence_number + 1
            previous_hash = last_entry.combined_hash

        # 3. Berechne Content-Hash
        content_hash = self._calculate_content_hash(entry)

        # 4. Berechne Combined-Hash
        combined_hash = self._calculate_combined_hash(previous_hash, content_hash)

        # 5. Erstelle Eintrag
        chain_entry = AuditChainEntry(
            sequence_number=sequence_number,
            previous_hash=previous_hash,
            content_hash=content_hash,
            combined_hash=combined_hash,
            event_type=entry.event_type.value,
            event_data=entry.event_data,
            document_id=entry.document_id,
            company_id=company_id,
            user_id=entry.user_id,
            tsa_timestamp=tsa_timestamp,
            tsa_token=tsa_token,
            tsa_provider=tsa_provider,
            is_verified=True,
            last_verified_at=datetime.utcnow(),
        )

        db.add(chain_entry)
        await db.flush()

        logger.info(
            "audit_chain_entry_appended",
            company_id=str(company_id),
            sequence_number=sequence_number,
            event_type=entry.event_type.value,
            combined_hash=combined_hash[:16] + "...",
        )

        return chain_entry

    async def verify_chain(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        start_sequence: int = 1,
        end_sequence: Optional[int] = None,
    ) -> ChainVerificationResult:
        """Verifiziert die Integrität der Audit-Chain.

        Prüft ob alle Hashes korrekt sind und die Kette nicht
        manipuliert wurde.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            start_sequence: Start-Sequenznummer (default: 1)
            end_sequence: End-Sequenznummer (default: letzter Eintrag)

        Returns:
            ChainVerificationResult mit Verifikationsstatus
        """
        start_time = datetime.utcnow()

        # Hole alle Einträge im Bereich
        query = (
            select(AuditChainEntry)
            .where(
                and_(
                    AuditChainEntry.company_id == company_id,
                    AuditChainEntry.sequence_number >= start_sequence,
                )
            )
            .order_by(AuditChainEntry.sequence_number)
        )

        if end_sequence is not None:
            query = query.where(AuditChainEntry.sequence_number <= end_sequence)

        result = await db.execute(query)
        entries = result.scalars().all()

        if not entries:
            return ChainVerificationResult(
                status=ChainVerificationStatus.EMPTY,
                total_entries=0,
                verified_entries=0,
            )

        verified_count = 0
        previous_entry: Optional[AuditChainEntry] = None

        for entry in entries:
            # 1. Verifiziere Content-Hash
            expected_content_hash = self._calculate_content_hash(
                ChainEntry(
                    event_type=AuditChainEventType(entry.event_type),
                    event_data=entry.event_data,
                    document_id=entry.document_id,
                    user_id=entry.user_id,
                )
            )

            if entry.content_hash != expected_content_hash:
                duration = (datetime.utcnow() - start_time).total_seconds() * 1000
                return ChainVerificationResult(
                    status=ChainVerificationStatus.BROKEN_AT,
                    total_entries=len(entries),
                    verified_entries=verified_count,
                    broken_at_sequence=entry.sequence_number,
                    broken_entry_id=entry.id,
                    error_message=f"Content-Hash stimmt nicht überein bei Sequenz {entry.sequence_number}",
                    verification_time_ms=duration,
                )

            # 2. Verifiziere Verkettung (ausser Genesis)
            if entry.sequence_number > 1:
                if previous_entry is None:
                    # Wir haben nicht bei 1 angefangen - prüfe Vorherigen
                    prev_result = await db.execute(
                        select(AuditChainEntry)
                        .where(
                            and_(
                                AuditChainEntry.company_id == company_id,
                                AuditChainEntry.sequence_number == entry.sequence_number - 1,
                            )
                        )
                    )
                    previous_entry = prev_result.scalar_one_or_none()

                if previous_entry is None:
                    duration = (datetime.utcnow() - start_time).total_seconds() * 1000
                    return ChainVerificationResult(
                        status=ChainVerificationStatus.BROKEN_AT,
                        total_entries=len(entries),
                        verified_entries=verified_count,
                        broken_at_sequence=entry.sequence_number,
                        broken_entry_id=entry.id,
                        error_message=f"Vorheriger Eintrag fehlt bei Sequenz {entry.sequence_number}",
                        verification_time_ms=duration,
                    )

                # Prüfe ob previous_hash korrekt ist
                if entry.previous_hash != previous_entry.combined_hash:
                    duration = (datetime.utcnow() - start_time).total_seconds() * 1000
                    return ChainVerificationResult(
                        status=ChainVerificationStatus.BROKEN_AT,
                        total_entries=len(entries),
                        verified_entries=verified_count,
                        broken_at_sequence=entry.sequence_number,
                        broken_entry_id=entry.id,
                        error_message=f"Ketten-Hash stimmt nicht bei Sequenz {entry.sequence_number}",
                        verification_time_ms=duration,
                    )

            # 3. Verifiziere Combined-Hash
            expected_combined = self._calculate_combined_hash(
                entry.previous_hash, entry.content_hash
            )

            if entry.combined_hash != expected_combined:
                duration = (datetime.utcnow() - start_time).total_seconds() * 1000
                return ChainVerificationResult(
                    status=ChainVerificationStatus.BROKEN_AT,
                    total_entries=len(entries),
                    verified_entries=verified_count,
                    broken_at_sequence=entry.sequence_number,
                    broken_entry_id=entry.id,
                    error_message=f"Combined-Hash stimmt nicht bei Sequenz {entry.sequence_number}",
                    verification_time_ms=duration,
                )

            # Update Verifikationsstatus
            entry.is_verified = True
            entry.last_verified_at = datetime.utcnow()
            entry.verification_error = None

            verified_count += 1
            previous_entry = entry

        duration = (datetime.utcnow() - start_time).total_seconds() * 1000

        logger.info(
            "audit_chain_verified",
            company_id=str(company_id),
            total_entries=len(entries),
            verified_entries=verified_count,
            duration_ms=round(duration, 2),
        )

        return ChainVerificationResult(
            status=ChainVerificationStatus.VALID,
            total_entries=len(entries),
            verified_entries=verified_count,
            verification_time_ms=duration,
        )

    async def get_chain_statistics(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Holt Statistiken über die Audit-Chain.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID

        Returns:
            Dict mit Chain-Statistiken
        """
        # Gesamtanzahl
        total_result = await db.execute(
            select(func.count()).select_from(AuditChainEntry)
            .where(AuditChainEntry.company_id == company_id)
        )
        total_entries = total_result.scalar() or 0

        # Nach Event-Typ
        event_type_result = await db.execute(
            select(
                AuditChainEntry.event_type,
                func.count().label("count"),
            )
            .where(AuditChainEntry.company_id == company_id)
            .group_by(AuditChainEntry.event_type)
        )
        by_event_type = {row.event_type: row.count for row in event_type_result.all()}

        # Unverified Entries
        unverified_result = await db.execute(
            select(func.count()).select_from(AuditChainEntry)
            .where(
                and_(
                    AuditChainEntry.company_id == company_id,
                    AuditChainEntry.is_verified == False,
                )
            )
        )
        unverified_count = unverified_result.scalar() or 0

        # Mit TSA-Timestamp
        tsa_result = await db.execute(
            select(func.count()).select_from(AuditChainEntry)
            .where(
                and_(
                    AuditChainEntry.company_id == company_id,
                    AuditChainEntry.tsa_timestamp.isnot(None),
                )
            )
        )
        tsa_count = tsa_result.scalar() or 0

        # Erster und letzter Eintrag
        first_entry = await self._get_first_entry(db, company_id)
        last_entry = await self._get_last_entry(db, company_id)

        return {
            "total_entries": total_entries,
            "by_event_type": by_event_type,
            "unverified_count": unverified_count,
            "tsa_timestamped_count": tsa_count,
            "first_entry": {
                "sequence": first_entry.sequence_number if first_entry else None,
                "created_at": first_entry.created_at.isoformat() if first_entry else None,
            },
            "last_entry": {
                "sequence": last_entry.sequence_number if last_entry else None,
                "created_at": last_entry.created_at.isoformat() if last_entry else None,
            },
        }

    async def get_entries_by_document(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        document_id: uuid.UUID,
        limit: int = 100,
    ) -> List[AuditChainEntry]:
        """Holt alle Chain-Einträge für ein Dokument.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            document_id: Dokument-ID
            limit: Maximale Anzahl Einträge

        Returns:
            Liste von AuditChainEntry
        """
        result = await db.execute(
            select(AuditChainEntry)
            .where(
                and_(
                    AuditChainEntry.company_id == company_id,
                    AuditChainEntry.document_id == document_id,
                )
            )
            .order_by(desc(AuditChainEntry.sequence_number))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_entry_by_sequence(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        sequence_number: int,
    ) -> Optional[AuditChainEntry]:
        """Holt einen spezifischen Chain-Eintrag nach Sequenznummer.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            sequence_number: Sequenznummer

        Returns:
            AuditChainEntry oder None
        """
        result = await db.execute(
            select(AuditChainEntry)
            .where(
                and_(
                    AuditChainEntry.company_id == company_id,
                    AuditChainEntry.sequence_number == sequence_number,
                )
            )
        )
        return result.scalar_one_or_none()

    # ================== Helper Methods ==================

    async def _get_last_entry(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> Optional[AuditChainEntry]:
        """Holt den letzten Eintrag der Chain."""
        result = await db.execute(
            select(AuditChainEntry)
            .where(AuditChainEntry.company_id == company_id)
            .order_by(desc(AuditChainEntry.sequence_number))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_first_entry(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> Optional[AuditChainEntry]:
        """Holt den ersten Eintrag der Chain (Genesis)."""
        result = await db.execute(
            select(AuditChainEntry)
            .where(
                and_(
                    AuditChainEntry.company_id == company_id,
                    AuditChainEntry.sequence_number == 1,
                )
            )
        )
        return result.scalar_one_or_none()

    def _calculate_content_hash(self, entry: ChainEntry) -> str:
        """Berechnet den SHA-256 Hash des Entry-Inhalts.

        Der Hash wird aus einem kanonischen JSON des Inhalts berechnet.
        """
        # Kanonisches JSON (sortiert, deterministisch)
        canonical_data = {
            "event_type": entry.event_type.value,
            "event_data": entry.event_data,
            "document_id": str(entry.document_id) if entry.document_id else None,
            "user_id": str(entry.user_id) if entry.user_id else None,
        }

        canonical_json = json.dumps(
            canonical_data,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )

        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    def _calculate_combined_hash(
        self,
        previous_hash: Optional[str],
        content_hash: str,
    ) -> str:
        """Berechnet den kombinierten Hash (Verkettung).

        combined_hash = SHA256(previous_hash + content_hash)

        Für Genesis-Block wird ein spezieller Null-Hash verwendet.
        """
        if previous_hash is None:
            previous_hash = self.GENESIS_PREVIOUS_HASH

        combined = previous_hash + content_hash
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()


# ================== Convenience Functions ==================

async def log_document_event(
    db: AsyncSession,
    company_id: uuid.UUID,
    event_type: AuditChainEventType,
    document_id: uuid.UUID,
    event_data: Dict[str, Any],
    user_id: Optional[uuid.UUID] = None,
) -> AuditChainEntry:
    """Convenience-Funktion zum Loggen eines Dokument-Ereignisses.

    Args:
        db: Datenbank-Session
        company_id: Firmen-ID
        event_type: Typ des Ereignisses
        document_id: Dokument-ID
        event_data: Ereignis-Daten (keine PII!)
        user_id: Optional - User der das Ereignis ausgeloest hat

    Returns:
        Der erstellte AuditChainEntry
    """
    entry = ChainEntry(
        event_type=event_type,
        event_data=event_data,
        document_id=document_id,
        user_id=user_id,
    )
    return await audit_chain_service.append_entry(db, company_id, entry)


async def log_system_event(
    db: AsyncSession,
    company_id: uuid.UUID,
    event_type: AuditChainEventType,
    event_data: Dict[str, Any],
    user_id: Optional[uuid.UUID] = None,
) -> AuditChainEntry:
    """Convenience-Funktion zum Loggen eines System-Ereignisses.

    Args:
        db: Datenbank-Session
        company_id: Firmen-ID
        event_type: Typ des Ereignisses
        event_data: Ereignis-Daten (keine PII!)
        user_id: Optional - User der das Ereignis ausgeloest hat

    Returns:
        Der erstellte AuditChainEntry
    """
    entry = ChainEntry(
        event_type=event_type,
        event_data=event_data,
        user_id=user_id,
    )
    return await audit_chain_service.append_entry(db, company_id, entry)


# Singleton-Instanz
audit_chain_service = AuditChainService()
