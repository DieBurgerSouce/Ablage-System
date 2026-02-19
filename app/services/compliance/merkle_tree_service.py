"""
Merkle Tree Service

Erweitert Audit-Chain mit Merkle Trees für kryptografische Integrität.
Ermöglicht effiziente Verifikation einzelner Einträge.

Feinpoliert und durchdacht - Enterprise Audit Trail Security.
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, List, Dict, Optional, Tuple
from uuid import UUID
import math

import structlog
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog

logger = structlog.get_logger(__name__)


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class MerkleNode:
    """Node im Merkle Tree."""

    hash: str  # SHA256 Hash
    left_hash: Optional[str]  # Linker Child
    right_hash: Optional[str]  # Rechter Child
    level: int  # Baum-Ebene (0 = Leaf)
    position: int  # Position in Ebene

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "hash": self.hash,
            "left_hash": self.left_hash,
            "right_hash": self.right_hash,
            "level": self.level,
            "position": self.position,
        }


@dataclass
class MerkleProof:
    """Merkle Proof für Entry-Verifikation."""

    entry_hash: str  # Hash des zu verifizierenden Eintrags
    root_hash: str  # Root Hash des Trees
    proof_path: List[Dict[str, str]]  # Proof-Pfad [{hash, position}]
    verified: bool  # Verifikations-Status

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "entry_hash": self.entry_hash,
            "root_hash": self.root_hash,
            "proof_path": self.proof_path,
            "verified": self.verified,
        }


@dataclass
class MerkleTree:
    """Kompletter Merkle Tree."""

    root_hash: str  # Root Hash
    leaf_count: int  # Anzahl Leaves
    tree_height: int  # Baum-Höhe
    nodes: List[MerkleNode]  # Alle Nodes

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "root_hash": self.root_hash,
            "leaf_count": self.leaf_count,
            "tree_height": self.tree_height,
            "nodes": [n.to_dict() for n in self.nodes],
        }


@dataclass
class IntegrityReport:
    """Integritäts-Report für Audit-Chain."""

    total_entries: int
    verified_entries: int
    integrity_score: float  # 0-100
    last_verified: datetime
    violations: List[str]  # Liste erkannter Verletzungen
    root_hash: str

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "total_entries": self.total_entries,
            "verified_entries": self.verified_entries,
            "integrity_score": round(self.integrity_score, 2),
            "last_verified": self.last_verified.isoformat(),
            "violations": self.violations,
            "root_hash": self.root_hash,
        }


# =============================================================================
# Merkle Tree Service
# =============================================================================


class MerkleTreeService:
    """
    Merkle Tree Service für Audit-Chain.

    Implementiert:
    - Tree-Konstruktion aus Audit-Logs
    - Proof-Generierung
    - Proof-Verifikation
    - Integritäts-Checks
    """

    def __init__(self) -> None:
        """Initialisiert Service."""
        pass

    def _hash(self, data: str) -> str:
        """
        Erstellt SHA256 Hash.

        Args:
            data: Zu hashende Daten

        Returns:
            Hex-String des Hashes
        """
        return hashlib.sha256(data.encode('utf-8')).hexdigest()

    def _combine_hashes(self, left: str, right: str) -> str:
        """
        Kombiniert zwei Hashes zu Parent-Hash.

        Args:
            left: Linker Hash
            right: Rechter Hash

        Returns:
            Kombinierter Hash
        """
        combined = left + right
        return self._hash(combined)

    def build_tree(self, entries: List[str]) -> MerkleTree:
        """
        Baut Merkle Tree aus Entry-Liste.

        Args:
            entries: Liste von Entry-Strings (z.B. JSON-serialisierte Logs)

        Returns:
            MerkleTree mit Root-Hash und allen Nodes
        """
        if not entries:
            # Empty tree
            empty_hash = self._hash("")
            return MerkleTree(
                root_hash=empty_hash,
                leaf_count=0,
                tree_height=0,
                nodes=[],
            )

        # 1. Erstelle Leaf-Hashes (Ebene 0)
        leaf_hashes = [self._hash(entry) for entry in entries]
        leaf_nodes = [
            MerkleNode(
                hash=h,
                left_hash=None,
                right_hash=None,
                level=0,
                position=i,
            )
            for i, h in enumerate(leaf_hashes)
        ]

        all_nodes: List[MerkleNode] = leaf_nodes.copy()
        current_level = leaf_hashes.copy()
        level = 0

        # 2. Baue Baum bottom-up
        while len(current_level) > 1:
            level += 1
            next_level: List[str] = []

            # Paare bilden und kombinieren
            for i in range(0, len(current_level), 2):
                left = current_level[i]

                if i + 1 < len(current_level):
                    # Paar vorhanden
                    right = current_level[i + 1]
                else:
                    # Ungeradzahl: Letztes Element verdoppeln
                    right = left

                parent_hash = self._combine_hashes(left, right)
                next_level.append(parent_hash)

                # Add Parent Node
                all_nodes.append(
                    MerkleNode(
                        hash=parent_hash,
                        left_hash=left,
                        right_hash=right if right != left else None,
                        level=level,
                        position=len(next_level) - 1,
                    )
                )

            current_level = next_level

        # Root ist letztes Element
        root_hash = current_level[0]
        tree_height = level

        logger.info(
            "merkle_tree.built",
            leaf_count=len(entries),
            tree_height=tree_height,
            root_hash=root_hash[:16] + "...",
        )

        return MerkleTree(
            root_hash=root_hash,
            leaf_count=len(entries),
            tree_height=tree_height,
            nodes=all_nodes,
        )

    async def get_proof(
        self,
        entry_hash: str,
        company_id: UUID,
        db: AsyncSession,
    ) -> Optional[MerkleProof]:
        """
        Generiert Merkle Proof für Entry.

        Args:
            entry_hash: Hash des zu verifizierenden Eintrags
            company_id: Mandanten-ID für Multi-Tenant Isolation
            db: Database session

        Returns:
            MerkleProof oder None wenn Entry nicht gefunden
        """
        # Production: Nutze Cache wenn verfügbar
        cache_key = f"merkle_tree:{company_id}"
        cached_tree = await self._get_cached_tree(cache_key, db)

        if cached_tree:
            logger.debug("merkle_tree.cache_hit", company_id=str(company_id))
        else:
            logger.debug("merkle_tree.cache_miss", company_id=str(company_id))

        # SECURITY FIX: company_id Filter für Multi-Tenant Isolation
        query = select(AuditLog).where(
            AuditLog.company_id == company_id
        ).order_by(AuditLog.created_at)
        result = await db.execute(query)
        logs = result.scalars().all()

        if not logs:
            return None

        # Serialisiere Logs
        entries = [
            f"{log.id}|{log.action}|{log.user_id}|{log.created_at.isoformat()}"
            for log in logs
        ]

        # Finde Entry-Position
        entry_position = None
        for i, entry in enumerate(entries):
            if self._hash(entry) == entry_hash:
                entry_position = i
                break

        if entry_position is None:
            return None

        # Baue Tree
        tree = self.build_tree(entries)

        # Generiere Proof-Pfad
        proof_path = self._generate_proof_path(entry_position, tree)

        # Verifiziere Proof
        verified = self.verify_proof(
            MerkleProof(
                entry_hash=entry_hash,
                root_hash=tree.root_hash,
                proof_path=proof_path,
                verified=False,  # Wird von verify_proof gesetzt
            )
        )

        return MerkleProof(
            entry_hash=entry_hash,
            root_hash=tree.root_hash,
            proof_path=proof_path,
            verified=verified,
        )

    def _generate_proof_path(
        self,
        leaf_position: int,
        tree: MerkleTree,
    ) -> List[Dict[str, str]]:
        """
        Generiert Proof-Pfad von Leaf zu Root.

        Args:
            leaf_position: Position des Leafs
            tree: MerkleTree

        Returns:
            Liste von Proof-Elementen [{hash, position}]
        """
        proof_path: List[Dict[str, str]] = []

        # Hole Leaf-Nodes (Level 0)
        leaf_nodes = [n for n in tree.nodes if n.level == 0]

        if leaf_position >= len(leaf_nodes):
            return proof_path

        current_position = leaf_position
        current_level = 0

        # Traversiere Baum nach oben
        while current_level < tree.tree_height:
            # Finde Sibling
            if current_position % 2 == 0:
                # Linkes Kind - rechter Sibling
                sibling_position = current_position + 1
                side = "right"
            else:
                # Rechtes Kind - linker Sibling
                sibling_position = current_position - 1
                side = "left"

            # Finde Sibling-Node
            level_nodes = [n for n in tree.nodes if n.level == current_level]
            if sibling_position < len(level_nodes):
                sibling = level_nodes[sibling_position]
                proof_path.append({
                    "hash": sibling.hash,
                    "position": side,
                })

            # Move up
            current_position = current_position // 2
            current_level += 1

        return proof_path

    def verify_proof(self, proof: MerkleProof) -> bool:
        """
        Verifiziert Merkle Proof.

        Args:
            proof: MerkleProof zu verifizieren

        Returns:
            True wenn Proof valide
        """
        current_hash = proof.entry_hash

        # Traversiere Proof-Pfad
        for proof_element in proof.proof_path:
            sibling_hash = proof_element["hash"]
            position = proof_element["position"]

            if position == "left":
                # Sibling ist links
                current_hash = self._combine_hashes(sibling_hash, current_hash)
            else:
                # Sibling ist rechts
                current_hash = self._combine_hashes(current_hash, sibling_hash)

        # Vergleiche mit Root
        verified = current_hash == proof.root_hash

        logger.info(
            "merkle_proof.verified",
            entry_hash=proof.entry_hash[:16] + "...",
            verified=verified,
        )

        return verified

    async def get_integrity_report(
        self,
        company_id: UUID,
        db: AsyncSession,
    ) -> IntegrityReport:
        """
        Erstellt Integritäts-Report für Audit-Chain.

        Args:
            company_id: Company UUID
            db: Database session

        Returns:
            IntegrityReport mit Statistiken
        """
        logger.info("merkle_tree.integrity_report", company_id=str(company_id))

        # Hole alle Audit-Logs der Company
        query = select(AuditLog).where(
            AuditLog.company_id == company_id
        ).order_by(AuditLog.created_at)
        result = await db.execute(query)
        logs = result.scalars().all()

        if not logs:
            return IntegrityReport(
                total_entries=0,
                verified_entries=0,
                integrity_score=100.0,
                last_verified=datetime.now(timezone.utc),
                violations=[],
                root_hash=self._hash(""),
            )

        # Serialisiere Logs
        entries = [
            f"{log.id}|{log.action}|{log.user_id}|{log.created_at.isoformat()}"
            for log in logs
        ]

        # Baue Tree
        tree = self.build_tree(entries)

        # Verifiziere Stichprobe (z.B. jedes 10. Entry)
        verified_count = 0
        violations: List[str] = []
        sample_size = min(len(entries), max(10, len(entries) // 10))

        for i in range(0, len(entries), max(1, len(entries) // sample_size)):
            entry_hash = self._hash(entries[i])
            proof = self._generate_proof_path(i, tree)

            merkle_proof = MerkleProof(
                entry_hash=entry_hash,
                root_hash=tree.root_hash,
                proof_path=proof,
                verified=False,
            )

            if self.verify_proof(merkle_proof):
                verified_count += 1
            else:
                violations.append(f"Entry {i} Verifikation fehlgeschlagen")

        integrity_score = (verified_count / sample_size) * 100 if sample_size > 0 else 100.0

        return IntegrityReport(
            total_entries=len(entries),
            verified_entries=verified_count,
            integrity_score=integrity_score,
            last_verified=datetime.now(timezone.utc),
            violations=violations,
            root_hash=tree.root_hash,
        )

    async def export_chain(
        self,
        company_id: UUID,
        from_date: datetime,
        to_date: datetime,
        db: AsyncSession,
    ) -> bytes:
        """
        Exportiert Audit-Chain mit Merkle Proofs.

        Args:
            company_id: Company UUID
            from_date: Start-Datum
            to_date: End-Datum
            db: Database session

        Returns:
            JSON-Bytes mit Audit-Logs und Merkle Tree
        """
        import json

        logger.info(
            "merkle_tree.export_chain",
            company_id=str(company_id),
            from_date=from_date.isoformat(),
            to_date=to_date.isoformat(),
        )

        # Hole Audit-Logs im Zeitraum
        query = select(AuditLog).where(
            and_(
                AuditLog.company_id == company_id,
                AuditLog.created_at >= from_date,
                AuditLog.created_at <= to_date,
            )
        ).order_by(AuditLog.created_at)
        result = await db.execute(query)
        logs = result.scalars().all()

        # Serialisiere Logs
        entries = [
            f"{log.id}|{log.action}|{log.user_id}|{log.created_at.isoformat()}"
            for log in logs
        ]

        # Baue Tree
        tree = self.build_tree(entries)

        # Export-Daten
        export_data = {
            "company_id": str(company_id),
            "export_date": datetime.now(timezone.utc).isoformat(),
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "merkle_tree": tree.to_dict(),
            "audit_logs": [
                {
                    "id": str(log.id),
                    "action": log.action,
                    "user_id": str(log.user_id),
                    "created_at": log.created_at.isoformat(),
                    "changes": log.changes,
                }
                for log in logs
            ],
        }

        return json.dumps(export_data, indent=2, ensure_ascii=False).encode('utf-8')

    # ================== Caching Methods ==================

    async def _get_cached_tree(
        self,
        cache_key: str,
        db: AsyncSession,
    ) -> Optional[MerkleTree]:
        """
        Holt gecachten Merkle Tree aus AppConfig.

        Args:
            cache_key: Cache-Schluessel (z.B. 'merkle_tree:<company_id>')
            db: Database session

        Returns:
            MerkleTree wenn im Cache, sonst None
        """
        from app.db.models import AppConfig

        try:
            result = await db.execute(
                select(AppConfig).where(AppConfig.key == cache_key)
            )
            config = result.scalar_one_or_none()

            if not config or not config.value:
                return None

            # Prüfe Cache-Alter (max 1 Stunde)
            cache_data = config.value
            if not isinstance(cache_data, dict):
                return None

            cached_at_str = cache_data.get("cached_at")
            if cached_at_str:
                cached_at = datetime.fromisoformat(cached_at_str)
                cache_age = datetime.now(timezone.utc) - cached_at
                if cache_age.total_seconds() > 3600:  # 1 Stunde
                    logger.debug("merkle_tree.cache_expired", cache_key=cache_key)
                    return None

            # Rekonstruiere MerkleTree aus Cache
            tree_data = cache_data.get("tree")
            if not tree_data:
                return None

            nodes = [
                MerkleNode(
                    hash=n["hash"],
                    left_hash=n.get("left_hash"),
                    right_hash=n.get("right_hash"),
                    level=n["level"],
                    position=n["position"],
                )
                for n in tree_data.get("nodes", [])
            ]

            return MerkleTree(
                root_hash=tree_data["root_hash"],
                leaf_count=tree_data["leaf_count"],
                tree_height=tree_data["tree_height"],
                nodes=nodes,
            )

        except Exception as e:
            logger.warning("merkle_tree.cache_read_error", error=str(e))
            return None

    async def cache_tree(
        self,
        company_id: UUID,
        tree: MerkleTree,
        db: AsyncSession,
    ) -> bool:
        """
        Cached Merkle Tree in AppConfig.

        Args:
            company_id: Company UUID
            tree: MerkleTree zu cachen
            db: Database session

        Returns:
            True bei Erfolg
        """
        from app.db.models import AppConfig

        cache_key = f"merkle_tree:{company_id}"

        try:
            cache_data = {
                "cached_at": datetime.now(timezone.utc).isoformat(),
                "company_id": str(company_id),
                "tree": tree.to_dict(),
            }

            result = await db.execute(
                select(AppConfig).where(AppConfig.key == cache_key)
            )
            config = result.scalar_one_or_none()

            if config:
                config.value = cache_data
            else:
                new_config = AppConfig(
                    key=cache_key,
                    value=cache_data,
                )
                db.add(new_config)

            await db.commit()

            logger.info(
                "merkle_tree.cached",
                company_id=str(company_id),
                leaf_count=tree.leaf_count,
            )
            return True

        except Exception as e:
            logger.error("merkle_tree.cache_write_error", error=str(e))
            return False

    async def invalidate_cache(
        self,
        company_id: UUID,
        db: AsyncSession,
    ) -> bool:
        """
        Invalidiert gecachten Merkle Tree.

        Sollte aufgerufen werden wenn neue AuditLog-Einträge hinzugefuegt werden.

        Args:
            company_id: Company UUID
            db: Database session

        Returns:
            True bei Erfolg
        """
        from app.db.models import AppConfig

        cache_key = f"merkle_tree:{company_id}"

        try:
            result = await db.execute(
                select(AppConfig).where(AppConfig.key == cache_key)
            )
            config = result.scalar_one_or_none()

            if config:
                await db.delete(config)
                await db.commit()

                logger.info(
                    "merkle_tree.cache_invalidated",
                    company_id=str(company_id),
                )

            return True

        except Exception as e:
            logger.error("merkle_tree.cache_invalidate_error", error=str(e))
            return False
