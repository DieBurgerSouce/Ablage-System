# -*- coding: utf-8 -*-
"""
QES/eIDAS Signatur-Service für Ablage-System.

Business-Logik für qualifizierte elektronische Signaturen:
- Signaturanfragen erstellen und verwalten
- Dokumente signieren und ablehnen
- Signaturen verifizieren
- Audit-Trail führen

Feinpoliert und durchdacht - eIDAS-konforme Signaturverwaltung.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Tuple
from uuid import UUID, uuid4

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import structlog

from app.db.models_signature import (
    SignatureRequest,
    SignatureEntry,
    SignatureAuditLog,
    SignatureLevel,
    SignatureStatus,
    SignatureProvider,
)
from app.core.safe_errors import safe_error_detail, safe_error_log

logger = structlog.get_logger(__name__)


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class SignerInfo:
    """Informationen zu einem Unterzeichner."""
    email: str
    name: str
    user_id: Optional[UUID] = None
    signing_order: int = 1


@dataclass
class SignatureVerificationResult:
    """Ergebnis der Signaturverifikation."""
    document_id: UUID
    is_fully_signed: bool
    total_signatures: int
    completed_signatures: int
    pending_signatures: int
    rejected_signatures: int
    signatures: List[Dict[str, object]] = field(default_factory=list)


# ============================================================================
# Service
# ============================================================================


class SignatureService:
    """Service für QES/eIDAS Signaturverwaltung.

    Verwaltet den gesamten Signatur-Lebenszyklus:
    - Anfrage erstellen
    - Signaturen einsammeln (optional sequentiell)
    - Verifikation und Audit-Trail
    """

    # -------------------------------------------------------------------------
    # Signaturanfrage erstellen
    # -------------------------------------------------------------------------

    async def create_signature_request(
        self,
        db: AsyncSession,
        document_id: UUID,
        company_id: UUID,
        requested_by: UUID,
        title: str,
        signers: List[SignerInfo],
        signature_level: str = "advanced",
        provider: str = "internal",
        signing_order_required: bool = False,
        expires_in_days: int = 30,
    ) -> SignatureRequest:
        """Erstellt eine neue Signaturanfrage mit Unterzeichnern.

        Args:
            db: Datenbank-Session
            document_id: ID des zu signierenden Dokuments
            company_id: Mandanten-ID
            requested_by: User-ID des Anforderers
            title: Titel der Anfrage
            signers: Liste der Unterzeichner
            signature_level: Signaturniveau (simple/advanced/qualified)
            provider: Signaturanbieter
            signing_order_required: Sequentielle Signierung erforderlich
            expires_in_days: Ablaufzeit in Tagen

        Returns:
            Erstellte SignatureRequest mit Entries
        """
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=expires_in_days)

        request = SignatureRequest(
            id=uuid4(),
            document_id=document_id,
            company_id=company_id,
            title=title,
            signature_level=signature_level,
            provider=provider,
            status=SignatureStatus.PENDING.value,
            requested_by=requested_by,
            requested_at=now,
            expires_at=expires_at,
            signing_order_required=signing_order_required,
        )
        db.add(request)
        await db.flush()

        # Signatureinträge für jeden Unterzeichner erstellen
        for signer in signers:
            entry = SignatureEntry(
                id=uuid4(),
                signature_request_id=request.id,
                company_id=company_id,
                signer_id=signer.user_id,
                signer_email=signer.email,
                signer_name=signer.name,
                signing_order=signer.signing_order,
                status=SignatureStatus.PENDING.value,
            )
            db.add(entry)

        # Audit-Log erstellen
        await self._log_audit_event(
            db=db,
            request_id=request.id,
            company_id=company_id,
            action="requested",
            performed_by=requested_by,
            details={
                "title": title,
                "signature_level": signature_level,
                "provider": provider,
                "signer_count": len(signers),
                "signing_order_required": signing_order_required,
            },
        )

        await db.commit()
        await db.refresh(request)

        logger.info(
            "Signaturanfrage erstellt",
            request_id=str(request.id),
            document_id=str(document_id),
            signer_count=len(signers),
        )

        return request

    # -------------------------------------------------------------------------
    # Signaturanfrage abrufen
    # -------------------------------------------------------------------------

    async def get_signature_request(
        self,
        db: AsyncSession,
        request_id: UUID,
        company_id: UUID,
    ) -> Optional[SignatureRequest]:
        """Ruft eine Signaturanfrage mit Entries ab.

        Args:
            db: Datenbank-Session
            request_id: ID der Signaturanfrage
            company_id: Mandanten-ID (RLS)

        Returns:
            SignatureRequest oder None
        """
        stmt = (
            select(SignatureRequest)
            .options(selectinload(SignatureRequest.entries))
            .where(
                and_(
                    SignatureRequest.id == request_id,
                    SignatureRequest.company_id == company_id,
                    SignatureRequest.deleted_at.is_(None),
                )
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    # -------------------------------------------------------------------------
    # Signaturanfragen auflisten
    # -------------------------------------------------------------------------

    async def list_signature_requests(
        self,
        db: AsyncSession,
        company_id: UUID,
        document_id: Optional[UUID] = None,
        status: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple[List[SignatureRequest], int]:
        """Listet Signaturanfragen mit Pagination.

        Args:
            db: Datenbank-Session
            company_id: Mandanten-ID
            document_id: Optional - Filter nach Dokument
            status: Optional - Filter nach Status
            page: Seite (1-basiert)
            per_page: Einträge pro Seite

        Returns:
            Tuple aus (Ergebnisliste, Gesamtanzahl)
        """
        conditions = [
            SignatureRequest.company_id == company_id,
            SignatureRequest.deleted_at.is_(None),
        ]
        if document_id is not None:
            conditions.append(SignatureRequest.document_id == document_id)
        if status is not None:
            conditions.append(SignatureRequest.status == status)

        # Gesamtanzahl
        count_stmt = select(func.count(SignatureRequest.id)).where(
            and_(*conditions)
        )
        count_result = await db.execute(count_stmt)
        total = count_result.scalar() or 0

        # Paginierte Ergebnisse
        offset = (page - 1) * per_page
        stmt = (
            select(SignatureRequest)
            .options(selectinload(SignatureRequest.entries))
            .where(and_(*conditions))
            .order_by(SignatureRequest.created_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        result = await db.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    # -------------------------------------------------------------------------
    # Dokument signieren
    # -------------------------------------------------------------------------

    async def sign_document(
        self,
        db: AsyncSession,
        entry_id: UUID,
        company_id: UUID,
        signer_id: UUID,
        certificate_issuer: Optional[str] = None,
        certificate_serial: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> SignatureEntry:
        """Signiert ein Dokument (einzelner Eintrag).

        Validiert die Signierreihenfolge falls erforderlich und
        aktualisiert den Request-Status wenn alle signiert haben.

        Args:
            db: Datenbank-Session
            entry_id: ID des Signatureintrags
            company_id: Mandanten-ID
            signer_id: ID des signierenden Users
            certificate_issuer: Zertifikatsaussteller
            certificate_serial: Seriennummer des Zertifikats
            ip_address: IP-Adresse des Signierenden

        Returns:
            Aktualisierter SignatureEntry

        Raises:
            ValueError: Bei Validierungsfehlern
        """
        # Entry laden
        entry = await self._get_entry(db, entry_id, company_id)
        if entry is None:
            raise ValueError("Signatureintrag nicht gefunden")

        if entry.status != SignatureStatus.PENDING.value:
            raise ValueError(
                f"Signatureintrag hat Status '{entry.status}', "
                "erwartet 'pending'"
            )

        # Request laden für Reihenfolge-Validierung
        request = await self.get_signature_request(
            db, entry.signature_request_id, company_id
        )
        if request is None:
            raise ValueError("Signaturanfrage nicht gefunden")

        if request.status in (
            SignatureStatus.EXPIRED.value,
            SignatureStatus.REVOKED.value,
        ):
            raise ValueError(
                f"Signaturanfrage hat Status '{request.status}'"
            )

        # Signierreihenfolge prüfen
        if request.signing_order_required:
            await self._validate_signing_order(db, entry, request)

        # Signatur-Hash generieren
        now = datetime.now(timezone.utc)
        hash_input = (
            f"{entry_id}:{signer_id}:{now.isoformat()}"
            f":{certificate_serial or 'none'}"
        )
        signature_hash = hashlib.sha256(hash_input.encode()).hexdigest()

        # Entry aktualisieren
        entry.status = SignatureStatus.SIGNED.value
        entry.signed_at = now
        entry.signer_id = signer_id
        entry.certificate_issuer = certificate_issuer
        entry.certificate_serial = certificate_serial
        entry.signature_hash = signature_hash

        # Audit-Log
        await self._log_audit_event(
            db=db,
            request_id=request.id,
            company_id=company_id,
            action="signed",
            performed_by=signer_id,
            ip_address=ip_address,
            details={
                "entry_id": str(entry_id),
                "certificate_issuer": certificate_issuer,
                "signature_hash": signature_hash,
            },
        )

        # Prüfen ob alle signiert haben
        await self._check_request_completion(db, request)

        await db.commit()
        await db.refresh(entry)

        logger.info(
            "Dokument signiert",
            entry_id=str(entry_id),
            request_id=str(request.id),
            signer_id=str(signer_id),
        )

        return entry

    # -------------------------------------------------------------------------
    # Signatur ablehnen
    # -------------------------------------------------------------------------

    async def reject_signature(
        self,
        db: AsyncSession,
        entry_id: UUID,
        company_id: UUID,
        signer_id: UUID,
        reason: str,
        ip_address: Optional[str] = None,
    ) -> SignatureEntry:
        """Lehnt eine Signatur ab.

        Args:
            db: Datenbank-Session
            entry_id: ID des Signatureintrags
            company_id: Mandanten-ID
            signer_id: ID des ablehnenden Users
            reason: Ablehnungsgrund
            ip_address: IP-Adresse

        Returns:
            Aktualisierter SignatureEntry

        Raises:
            ValueError: Bei Validierungsfehlern
        """
        entry = await self._get_entry(db, entry_id, company_id)
        if entry is None:
            raise ValueError("Signatureintrag nicht gefunden")

        if entry.status != SignatureStatus.PENDING.value:
            raise ValueError(
                f"Signatureintrag hat Status '{entry.status}', "
                "erwartet 'pending'"
            )

        now = datetime.now(timezone.utc)
        entry.status = SignatureStatus.REJECTED.value
        entry.rejected_at = now
        entry.rejection_reason = reason
        entry.signer_id = signer_id

        # Request-Status ebenfalls auf REJECTED setzen
        request = await self.get_signature_request(
            db, entry.signature_request_id, company_id
        )
        if request is not None:
            request.status = SignatureStatus.REJECTED.value

            # Audit-Log
            await self._log_audit_event(
                db=db,
                request_id=request.id,
                company_id=company_id,
                action="rejected",
                performed_by=signer_id,
                ip_address=ip_address,
                details={
                    "entry_id": str(entry_id),
                    "reason": reason,
                },
            )

        await db.commit()
        await db.refresh(entry)

        logger.info(
            "Signatur abgelehnt",
            entry_id=str(entry_id),
            signer_id=str(signer_id),
            reason=reason,
        )

        return entry

    # -------------------------------------------------------------------------
    # Signaturen verifizieren
    # -------------------------------------------------------------------------

    async def verify_signatures(
        self,
        db: AsyncSession,
        document_id: UUID,
        company_id: UUID,
    ) -> SignatureVerificationResult:
        """Verifiziert alle Signaturen eines Dokuments.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            company_id: Mandanten-ID

        Returns:
            SignatureVerificationResult mit Status aller Signaturen
        """
        # Alle Requests für das Dokument laden
        stmt = (
            select(SignatureRequest)
            .options(selectinload(SignatureRequest.entries))
            .where(
                and_(
                    SignatureRequest.document_id == document_id,
                    SignatureRequest.company_id == company_id,
                    SignatureRequest.deleted_at.is_(None),
                )
            )
        )
        result = await db.execute(stmt)
        requests = list(result.scalars().all())

        # Alle Entries sammeln
        all_entries: List[SignatureEntry] = []
        for req in requests:
            all_entries.extend(req.entries)

        total = len(all_entries)
        completed = sum(
            1 for e in all_entries
            if e.status == SignatureStatus.SIGNED.value
        )
        pending = sum(
            1 for e in all_entries
            if e.status == SignatureStatus.PENDING.value
        )
        rejected = sum(
            1 for e in all_entries
            if e.status == SignatureStatus.REJECTED.value
        )

        signatures: List[Dict[str, object]] = []
        for entry in all_entries:
            signatures.append({
                "entry_id": str(entry.id),
                "signer_name": entry.signer_name,
                "signer_email": entry.signer_email,
                "status": entry.status,
                "signed_at": (
                    entry.signed_at.isoformat() if entry.signed_at else None
                ),
                "certificate_issuer": entry.certificate_issuer,
                "signature_hash": entry.signature_hash,
            })

        is_fully_signed = total > 0 and completed == total

        return SignatureVerificationResult(
            document_id=document_id,
            is_fully_signed=is_fully_signed,
            total_signatures=total,
            completed_signatures=completed,
            pending_signatures=pending,
            rejected_signatures=rejected,
            signatures=signatures,
        )

    # -------------------------------------------------------------------------
    # Audit-Trail
    # -------------------------------------------------------------------------

    async def get_audit_trail(
        self,
        db: AsyncSession,
        request_id: UUID,
        company_id: UUID,
    ) -> List[SignatureAuditLog]:
        """Ruft den Audit-Trail einer Signaturanfrage ab.

        Args:
            db: Datenbank-Session
            request_id: ID der Signaturanfrage
            company_id: Mandanten-ID

        Returns:
            Liste der Audit-Einträge
        """
        stmt = (
            select(SignatureAuditLog)
            .where(
                and_(
                    SignatureAuditLog.signature_request_id == request_id,
                    SignatureAuditLog.company_id == company_id,
                )
            )
            .order_by(SignatureAuditLog.performed_at.desc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # -------------------------------------------------------------------------
    # Ausstehende Signaturen
    # -------------------------------------------------------------------------

    async def get_pending_signatures(
        self,
        db: AsyncSession,
        signer_id: UUID,
        company_id: UUID,
    ) -> List[SignatureEntry]:
        """Ruft ausstehende Signaturen eines Users ab.

        Args:
            db: Datenbank-Session
            signer_id: User-ID des Unterzeichners
            company_id: Mandanten-ID

        Returns:
            Liste der ausstehenden Signatureinträge
        """
        stmt = (
            select(SignatureEntry)
            .where(
                and_(
                    SignatureEntry.signer_id == signer_id,
                    SignatureEntry.company_id == company_id,
                    SignatureEntry.status == SignatureStatus.PENDING.value,
                )
            )
            .order_by(SignatureEntry.created_at.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # -------------------------------------------------------------------------
    # Private Hilfsmethoden
    # -------------------------------------------------------------------------

    async def _get_entry(
        self,
        db: AsyncSession,
        entry_id: UUID,
        company_id: UUID,
    ) -> Optional[SignatureEntry]:
        """Laedt einen einzelnen Signatureintrag."""
        stmt = select(SignatureEntry).where(
            and_(
                SignatureEntry.id == entry_id,
                SignatureEntry.company_id == company_id,
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _validate_signing_order(
        self,
        db: AsyncSession,
        entry: SignatureEntry,
        request: SignatureRequest,
    ) -> None:
        """Validiert die Signierreihenfolge.

        Stellt sicher, dass alle vorherigen Unterzeichner
        bereits signiert haben.

        Raises:
            ValueError: Falls die Reihenfolge nicht eingehalten wird
        """
        # Alle Entries mit niedrigerer Reihenfolge prüfen
        earlier_entries = [
            e for e in request.entries
            if e.signing_order < entry.signing_order
        ]

        unsigned = [
            e for e in earlier_entries
            if e.status != SignatureStatus.SIGNED.value
        ]

        if unsigned:
            names = ", ".join(e.signer_name for e in unsigned)
            raise ValueError(
                f"Signierreihenfolge nicht eingehalten. "
                f"Ausstehende Signaturen von: {names}"
            )

    async def _check_request_completion(
        self,
        db: AsyncSession,
        request: SignatureRequest,
    ) -> None:
        """Prüft ob alle Entries signiert sind und setzt Request-Status."""
        all_signed = all(
            e.status == SignatureStatus.SIGNED.value
            for e in request.entries
        )

        if all_signed:
            request.status = SignatureStatus.SIGNED.value
            request.completed_at = datetime.now(timezone.utc)

            logger.info(
                "Signaturanfrage vollständig signiert",
                request_id=str(request.id),
            )

    async def _log_audit_event(
        self,
        db: AsyncSession,
        request_id: UUID,
        company_id: UUID,
        action: str,
        performed_by: Optional[UUID] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[Dict[str, object]] = None,
    ) -> SignatureAuditLog:
        """Erstellt einen Audit-Log-Eintrag."""
        audit = SignatureAuditLog(
            id=uuid4(),
            signature_request_id=request_id,
            company_id=company_id,
            action=action,
            performed_by=performed_by,
            performed_at=datetime.now(timezone.utc),
            ip_address=ip_address,
            user_agent=user_agent,
            details_json=details,
        )
        db.add(audit)
        return audit
