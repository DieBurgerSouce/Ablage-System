# -*- coding: utf-8 -*-
"""
Document Integrity Service für Ablage-System.

Kryptographische Integritätssicherung:
- SHA-256 Hashes pro Dokument
- Tägliche Merkle-Baeume
- Verifizierung und Manipulationserkennung
- Integritätsberichte für Compliance

Feinpoliert und durchdacht - Enterprise-grade Document Integrity.
"""

import hashlib
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_integrity import (
    DocumentHash,
    IntegrityReport,
    MerkleTreeNode,
    VerificationStatus,
)

logger = structlog.get_logger(__name__)


class DocumentIntegrityService:
    """
    Service für Dokument-Integrität mit Hash-Chains und Merkle-Baeumen.

    Stellt sicher, dass Dokumente nach dem Upload nicht manipuliert wurden.
    Unterstützt Einzel- und Massenverifizierung sowie Merkle-Beweise.
    """

    def __init__(self) -> None:
        """Initialisiert den Integritäts-Service."""
        pass

    # =========================================================================
    # Hash-Berechnung und -Speicherung
    # =========================================================================

    def _compute_sha256(self, content: bytes) -> str:
        """
        Berechnet den SHA-256 Hash von Dateiinhalt.

        Args:
            content: Dateiinhalt als Bytes

        Returns:
            SHA-256 Hex-Digest (64 Zeichen)
        """
        return hashlib.sha256(content).hexdigest()

    async def compute_document_hash(
        self,
        db: AsyncSession,
        document_id: UUID,
        file_content: bytes,
        company_id: UUID,
    ) -> DocumentHash:
        """
        Berechnet und speichert den SHA-256 Hash eines Dokuments.

        Args:
            db: Datenbank-Session
            document_id: ID des Dokuments
            file_content: Dateiinhalt als Bytes
            company_id: ID des Unternehmens

        Returns:
            DocumentHash-Eintrag mit dem berechneten Hash
        """
        file_hash = self._compute_sha256(file_content)
        file_size = len(file_content)
        now = datetime.now(timezone.utc)

        # Prüfen ob bereits ein Hash existiert
        stmt = select(DocumentHash).where(
            and_(
                DocumentHash.document_id == document_id,
                DocumentHash.deleted_at.is_(None),
            )
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing is not None:
            # Bestehenden Hash aktualisieren
            existing.file_hash = file_hash
            existing.file_size_bytes = file_size
            existing.computed_at = now
            existing.verification_status = VerificationStatus.UNVERIFIED.value
            existing.verified_at = None
            await db.flush()
            logger.info(
                "Dokument-Hash aktualisiert",
                document_id=str(document_id),
                file_hash=file_hash[:16] + "...",
            )
            return existing

        # Neuen Hash-Eintrag erstellen
        doc_hash = DocumentHash(
            document_id=document_id,
            company_id=company_id,
            file_hash=file_hash,
            hash_algorithm="sha-256",
            file_size_bytes=file_size,
            computed_at=now,
            verification_status=VerificationStatus.UNVERIFIED.value,
        )
        db.add(doc_hash)
        await db.flush()

        logger.info(
            "Dokument-Hash berechnet",
            document_id=str(document_id),
            file_hash=file_hash[:16] + "...",
            file_size_bytes=file_size,
        )
        return doc_hash

    # =========================================================================
    # Verifizierung
    # =========================================================================

    async def verify_document(
        self,
        db: AsyncSession,
        document_id: UUID,
        file_content: bytes,
    ) -> Tuple[bool, str]:
        """
        Verifiziert ein Dokument gegen den gespeicherten Hash.

        Args:
            db: Datenbank-Session
            document_id: ID des Dokuments
            file_content: Aktueller Dateiinhalt

        Returns:
            Tuple aus (ist_gültig, deutsche_meldung)
        """
        stmt = select(DocumentHash).where(
            and_(
                DocumentHash.document_id == document_id,
                DocumentHash.deleted_at.is_(None),
            )
        )
        result = await db.execute(stmt)
        doc_hash = result.scalar_one_or_none()

        if doc_hash is None:
            return False, "Kein Hash für dieses Dokument gespeichert"

        current_hash = self._compute_sha256(file_content)
        now = datetime.now(timezone.utc)
        is_valid = current_hash == doc_hash.file_hash

        if is_valid:
            doc_hash.verification_status = VerificationStatus.VERIFIED.value
            doc_hash.verified_at = now
            message = "Dokument-Integrität bestätigt - Hash stimmt überein"
            logger.info(
                "Dokument verifiziert",
                document_id=str(document_id),
            )
        else:
            doc_hash.verification_status = VerificationStatus.TAMPERED.value
            doc_hash.verified_at = now
            message = (
                "WARNUNG: Dokument wurde manipuliert - "
                "Hash weicht vom gespeicherten Wert ab"
            )
            logger.warning(
                "Dokument-Manipulation erkannt",
                document_id=str(document_id),
                stored_hash=doc_hash.file_hash[:16] + "...",
                current_hash=current_hash[:16] + "...",
            )

        await db.flush()
        return is_valid, message

    async def bulk_verify(
        self,
        db: AsyncSession,
        company_id: UUID,
        document_ids: List[UUID],
        file_contents: Dict[UUID, bytes],
    ) -> Dict[UUID, Tuple[bool, str]]:
        """
        Massenverifizierung mehrerer Dokumente.

        Args:
            db: Datenbank-Session
            company_id: ID des Unternehmens
            document_ids: Liste der Dokument-IDs
            file_contents: Mapping von Dokument-ID zu Dateiinhalt

        Returns:
            Mapping von Dokument-ID zu (ist_gültig, meldung)
        """
        results: Dict[UUID, Tuple[bool, str]] = {}

        for doc_id in document_ids:
            content = file_contents.get(doc_id)
            if content is None:
                results[doc_id] = (
                    False,
                    "Kein Dateiinhalt für Verifizierung bereitgestellt",
                )
                continue

            is_valid, message = await self.verify_document(db, doc_id, content)
            results[doc_id] = (is_valid, message)

        logger.info(
            "Massenverifizierung abgeschlossen",
            company_id=str(company_id),
            total=len(document_ids),
            verified=sum(1 for v, _ in results.values() if v),
            tampered=sum(1 for v, _ in results.values() if not v),
        )
        return results

    async def get_document_integrity_status(
        self,
        db: AsyncSession,
        document_id: UUID,
    ) -> Optional[DocumentHash]:
        """
        Gibt den aktuellen Integritätsstatus eines Dokuments zurück.

        Args:
            db: Datenbank-Session
            document_id: ID des Dokuments

        Returns:
            DocumentHash oder None wenn kein Hash vorhanden
        """
        stmt = select(DocumentHash).where(
            and_(
                DocumentHash.document_id == document_id,
                DocumentHash.deleted_at.is_(None),
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    # =========================================================================
    # Merkle-Baum
    # =========================================================================

    def _build_merkle_level(self, hashes: List[str]) -> List[str]:
        """
        Baut eine Ebene des Merkle-Baums.

        Kombiniert jeweils zwei benachbarte Hashes zu einem neuen Hash.
        Bei ungerader Anzahl wird der letzte Hash dupliziert.

        Args:
            hashes: Liste von Hex-Hashes der aktuellen Ebene

        Returns:
            Liste von Hex-Hashes der nächsten Ebene
        """
        if len(hashes) % 2 == 1:
            hashes = hashes + [hashes[-1]]  # Letzten Hash duplizieren

        next_level: List[str] = []
        for i in range(0, len(hashes), 2):
            combined = hashes[i] + hashes[i + 1]
            parent_hash = hashlib.sha256(combined.encode("utf-8")).hexdigest()
            next_level.append(parent_hash)

        return next_level

    def _compute_merkle_root(self, leaf_hashes: List[str]) -> str:
        """
        Berechnet den Merkle-Root aus einer Liste von Blatt-Hashes.

        Args:
            leaf_hashes: Sortierte Liste von Hex-Hashes

        Returns:
            Merkle-Root als Hex-Hash
        """
        if not leaf_hashes:
            return hashlib.sha256(b"empty").hexdigest()

        if len(leaf_hashes) == 1:
            return leaf_hashes[0]

        current_level = leaf_hashes
        while len(current_level) > 1:
            current_level = self._build_merkle_level(current_level)

        return current_level[0]

    async def build_daily_merkle_tree(
        self,
        db: AsyncSession,
        company_id: UUID,
        tree_date: date,
    ) -> str:
        """
        Baut den täglichen Merkle-Baum für alle Dokument-Hashes.

        Args:
            db: Datenbank-Session
            company_id: ID des Unternehmens
            tree_date: Tag für den Merkle-Baum

        Returns:
            Merkle-Root Hash
        """
        # Alle Hashes des Tages laden (sortiert für Determinismus)
        stmt = (
            select(DocumentHash)
            .where(
                and_(
                    DocumentHash.company_id == company_id,
                    func.date(DocumentHash.computed_at) == tree_date,
                    DocumentHash.deleted_at.is_(None),
                )
            )
            .order_by(DocumentHash.file_hash)
        )
        result = await db.execute(stmt)
        doc_hashes = list(result.scalars().all())

        if not doc_hashes:
            logger.info(
                "Keine Dokument-Hashes für Merkle-Baum",
                company_id=str(company_id),
                tree_date=tree_date.isoformat(),
            )
            return self._compute_merkle_root([])

        # Alte Merkle-Knoten für diesen Tag löschen
        old_nodes_stmt = select(MerkleTreeNode).where(
            and_(
                MerkleTreeNode.company_id == company_id,
                MerkleTreeNode.tree_date == tree_date,
            )
        )
        old_result = await db.execute(old_nodes_stmt)
        for old_node in old_result.scalars().all():
            await db.delete(old_node)

        # Blatt-Knoten erstellen
        leaf_hashes: List[str] = []
        leaf_nodes: List[MerkleTreeNode] = []

        for position, doc_hash in enumerate(doc_hashes):
            leaf_node = MerkleTreeNode(
                company_id=company_id,
                tree_date=tree_date,
                node_hash=doc_hash.file_hash,
                parent_hash=None,  # Wird später gesetzt
                level=0,
                position=position,
                document_hash_id=doc_hash.id,
            )
            db.add(leaf_node)
            leaf_nodes.append(leaf_node)
            leaf_hashes.append(doc_hash.file_hash)

        # Merkle-Baum ebenenweise aufbauen
        current_level_hashes = leaf_hashes
        current_level_nodes = leaf_nodes
        level = 1

        while len(current_level_hashes) > 1:
            # Ungerade Anzahl: letzten Hash duplizieren
            if len(current_level_hashes) % 2 == 1:
                current_level_hashes = current_level_hashes + [current_level_hashes[-1]]

            next_level_hashes: List[str] = []
            next_level_nodes: List[MerkleTreeNode] = []

            for i in range(0, len(current_level_hashes), 2):
                combined = current_level_hashes[i] + current_level_hashes[i + 1]
                parent_hash = hashlib.sha256(combined.encode("utf-8")).hexdigest()

                parent_node = MerkleTreeNode(
                    company_id=company_id,
                    tree_date=tree_date,
                    node_hash=parent_hash,
                    parent_hash=None,
                    level=level,
                    position=i // 2,
                )
                db.add(parent_node)

                # Parent-Hash bei Kindern setzen
                if i < len(current_level_nodes):
                    current_level_nodes[i].parent_hash = parent_hash
                if i + 1 < len(current_level_nodes):
                    current_level_nodes[i + 1].parent_hash = parent_hash

                next_level_hashes.append(parent_hash)
                next_level_nodes.append(parent_node)

            current_level_hashes = next_level_hashes
            current_level_nodes = next_level_nodes
            level += 1

        # Root-Knoten markieren
        merkle_root = current_level_hashes[0]
        if current_level_nodes:
            current_level_nodes[0].merkle_root = merkle_root

        await db.flush()

        logger.info(
            "Merkle-Baum erstellt",
            company_id=str(company_id),
            tree_date=tree_date.isoformat(),
            document_count=len(doc_hashes),
            merkle_root=merkle_root[:16] + "...",
        )
        return merkle_root

    async def verify_merkle_proof(
        self,
        db: AsyncSession,
        document_hash_id: UUID,
    ) -> Tuple[bool, List[str]]:
        """
        Verifiziert die Aufnahme eines Dokuments im Merkle-Baum.

        Args:
            db: Datenbank-Session
            document_hash_id: ID des DocumentHash-Eintrags

        Returns:
            Tuple aus (ist_enthalten, beweis_pfad)
        """
        # Blatt-Knoten finden
        stmt = select(MerkleTreeNode).where(
            and_(
                MerkleTreeNode.document_hash_id == document_hash_id,
                MerkleTreeNode.level == 0,
            )
        )
        result = await db.execute(stmt)
        leaf_node = result.scalar_one_or_none()

        if leaf_node is None:
            return False, []

        # Beweis-Pfad aufbauen (vom Blatt zur Wurzel)
        proof_path: List[str] = [leaf_node.node_hash]
        current_hash = leaf_node.parent_hash

        while current_hash is not None:
            proof_path.append(current_hash)
            # Nächsten Eltern-Knoten finden
            parent_stmt = select(MerkleTreeNode).where(
                and_(
                    MerkleTreeNode.company_id == leaf_node.company_id,
                    MerkleTreeNode.tree_date == leaf_node.tree_date,
                    MerkleTreeNode.node_hash == current_hash,
                )
            )
            parent_result = await db.execute(parent_stmt)
            parent_node = parent_result.scalar_one_or_none()

            if parent_node is None:
                break
            current_hash = parent_node.parent_hash

        # Root-Knoten prüfen
        root_stmt = select(MerkleTreeNode).where(
            and_(
                MerkleTreeNode.company_id == leaf_node.company_id,
                MerkleTreeNode.tree_date == leaf_node.tree_date,
                MerkleTreeNode.merkle_root.isnot(None),
            )
        )
        root_result = await db.execute(root_stmt)
        root_node = root_result.scalar_one_or_none()

        if root_node is None:
            return False, proof_path

        # Prüfen ob der Beweis-Pfad zum Root führt
        is_included = proof_path[-1] == root_node.merkle_root or \
            root_node.node_hash in proof_path

        return is_included, proof_path

    # =========================================================================
    # Berichte
    # =========================================================================

    async def generate_integrity_report(
        self,
        db: AsyncSession,
        company_id: UUID,
        user_id: UUID,
        report_date: Optional[date] = None,
    ) -> IntegrityReport:
        """
        Generiert einen Integritätsbericht für ein Unternehmen.

        Args:
            db: Datenbank-Session
            company_id: ID des Unternehmens
            user_id: ID des Erstellers
            report_date: Berichtsdatum (Standard: heute)

        Returns:
            IntegrityReport mit allen Statistiken
        """
        if report_date is None:
            report_date = date.today()

        # Statistiken ermitteln
        base_filter = and_(
            DocumentHash.company_id == company_id,
            DocumentHash.deleted_at.is_(None),
        )

        total_stmt = select(func.count(DocumentHash.id)).where(base_filter)
        total_result = await db.execute(total_stmt)
        total_documents = total_result.scalar_one()

        verified_stmt = select(func.count(DocumentHash.id)).where(
            and_(
                base_filter,
                DocumentHash.verification_status == VerificationStatus.VERIFIED.value,
            )
        )
        verified_result = await db.execute(verified_stmt)
        verified_count = verified_result.scalar_one()

        tampered_stmt = select(func.count(DocumentHash.id)).where(
            and_(
                base_filter,
                DocumentHash.verification_status == VerificationStatus.TAMPERED.value,
            )
        )
        tampered_result = await db.execute(tampered_stmt)
        tampered_count = tampered_result.scalar_one()

        unverified_count = total_documents - verified_count - tampered_count

        # Aktuellen Merkle-Root holen (falls vorhanden)
        root_stmt = select(MerkleTreeNode.merkle_root).where(
            and_(
                MerkleTreeNode.company_id == company_id,
                MerkleTreeNode.tree_date == report_date,
                MerkleTreeNode.merkle_root.isnot(None),
            )
        )
        root_result = await db.execute(root_stmt)
        merkle_root = root_result.scalar_one_or_none()

        if merkle_root is None:
            # Merkle-Root berechnen wenn keiner vorhanden
            merkle_root = await self.build_daily_merkle_tree(
                db, company_id, report_date
            )

        # Detaillierte Report-Daten
        report_data = {
            "zusammenfassung": {
                "gesamt": total_documents,
                "verifiziert": verified_count,
                "manipuliert": tampered_count,
                "nicht_geprüft": unverified_count,
            },
            "merkle_root": merkle_root,
            "berichtsdatum": report_date.isoformat(),
            "integritätsquote": (
                round(verified_count / total_documents * 100, 2)
                if total_documents > 0
                else 0.0
            ),
        }

        # Manipulierte Dokumente auflisten (ohne sensible Daten)
        if tampered_count > 0:
            tampered_stmt_detail = select(
                DocumentHash.document_id,
                DocumentHash.verified_at,
            ).where(
                and_(
                    base_filter,
                    DocumentHash.verification_status == VerificationStatus.TAMPERED.value,
                )
            )
            tampered_detail = await db.execute(tampered_stmt_detail)
            tampered_docs = [
                {
                    "document_id": str(row.document_id),
                    "erkannt_am": row.verified_at.isoformat() if row.verified_at else None,
                }
                for row in tampered_detail.all()
            ]
            report_data["manipulierte_dokumente"] = tampered_docs

        now = datetime.now(timezone.utc)

        report = IntegrityReport(
            company_id=company_id,
            report_date=report_date,
            total_documents=total_documents,
            verified_count=verified_count,
            tampered_count=tampered_count,
            unverified_count=unverified_count,
            merkle_root=merkle_root,
            report_data=report_data,
            generated_by=user_id,
            generated_at=now,
        )
        db.add(report)
        await db.flush()

        logger.info(
            "Integritätsbericht generiert",
            company_id=str(company_id),
            report_date=report_date.isoformat(),
            total=total_documents,
            verified=verified_count,
            tampered=tampered_count,
        )
        return report
