# -*- coding: utf-8 -*-
"""Unit tests for Merkle Tree Service."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from datetime import datetime, timezone

from app.services.compliance.merkle_tree_service import (
    MerkleTreeService,
    MerkleTree,
    MerkleProof,
    IntegrityReport,
    MerkleNode,
)
from app.db.models import AuditLog


# =============================================================================
# Tree Construction Tests
# =============================================================================


def test_merkle_tree_construction():
    """Merkle Tree sollte korrekt aus Entries gebaut werden."""
    service = MerkleTreeService()
    entries = [
        "entry1|action1|user1|2024-01-01",
        "entry2|action2|user2|2024-01-02",
        "entry3|action3|user3|2024-01-03",
        "entry4|action4|user4|2024-01-04",
    ]

    tree = service.build_tree(entries)

    assert isinstance(tree, MerkleTree)
    assert tree.leaf_count == 4
    assert tree.tree_height == 2  # 4 leaves -> height 2
    assert len(tree.root_hash) == 64  # SHA256 hex = 64 chars
    assert tree.root_hash is not None


def test_merkle_tree_empty():
    """Merkle Tree sollte leeren Tree für leere Entry-Liste erstellen."""
    service = MerkleTreeService()
    entries = []

    tree = service.build_tree(entries)

    assert tree.leaf_count == 0
    assert tree.tree_height == 0
    assert tree.root_hash is not None
    assert len(tree.nodes) == 0


def test_merkle_tree_single_entry():
    """Merkle Tree sollte mit einzelnem Entry funktionieren."""
    service = MerkleTreeService()
    entries = ["single_entry"]

    tree = service.build_tree(entries)

    assert tree.leaf_count == 1
    assert tree.tree_height == 0
    assert tree.root_hash is not None


def test_merkle_tree_odd_number():
    """Merkle Tree sollte ungerade Anzahl Entries korrekt behandeln."""
    service = MerkleTreeService()
    entries = ["entry1", "entry2", "entry3"]  # 3 entries (ungerade)

    tree = service.build_tree(entries)

    assert tree.leaf_count == 3
    assert tree.tree_height == 2  # 3 -> 2 -> 1
    assert tree.root_hash is not None


# =============================================================================
# Proof Generation Tests
# =============================================================================


@pytest.mark.asyncio
async def test_merkle_proof_generation():
    """Merkle Proof sollte validen Proof-Pfad generieren."""
    service = MerkleTreeService()
    mock_db = AsyncMock()
    company_id = uuid4()

    # Mock Audit Logs
    log1 = MagicMock(spec=AuditLog)
    log1.id = uuid4()
    log1.action = "action1"
    log1.user_id = uuid4()
    log1.created_at = datetime.now(timezone.utc)

    log2 = MagicMock(spec=AuditLog)
    log2.id = uuid4()
    log2.action = "action2"
    log2.user_id = uuid4()
    log2.created_at = datetime.now(timezone.utc)

    logs_result = MagicMock()
    logs_result.scalars.return_value.all.return_value = [log1, log2]

    mock_db.execute.return_value = logs_result

    # Entry Hash für log1
    entry_str = f"{log1.id}|{log1.action}|{log1.user_id}|{log1.created_at.isoformat()}"
    entry_hash = service._hash(entry_str)

    proof = await service.get_proof(entry_hash, company_id, mock_db)

    assert proof is not None
    assert isinstance(proof, MerkleProof)
    assert proof.entry_hash == entry_hash
    assert proof.root_hash is not None
    assert len(proof.proof_path) >= 0


@pytest.mark.asyncio
async def test_merkle_proof_not_found():
    """Merkle Proof sollte None returnen für unbekannten Hash."""
    service = MerkleTreeService()
    mock_db = AsyncMock()
    company_id = uuid4()

    # Mock Audit Logs
    log1 = MagicMock(spec=AuditLog)
    log1.id = uuid4()
    log1.action = "action1"
    log1.user_id = uuid4()
    log1.created_at = datetime.now(timezone.utc)

    logs_result = MagicMock()
    logs_result.scalars.return_value.all.return_value = [log1]

    mock_db.execute.return_value = logs_result

    # Unbekannter Hash
    unknown_hash = service._hash("unknown_entry")

    proof = await service.get_proof(unknown_hash, company_id, mock_db)

    assert proof is None


# =============================================================================
# Proof Verification Tests
# =============================================================================


def test_merkle_proof_verification():
    """Merkle Proof Verifikation sollte validen Proof akzeptieren."""
    service = MerkleTreeService()
    entries = [
        "entry1",
        "entry2",
        "entry3",
        "entry4",
    ]

    tree = service.build_tree(entries)

    # Generiere Proof für entry1
    entry_hash = service._hash(entries[0])
    proof_path = service._generate_proof_path(0, tree)

    proof = MerkleProof(
        entry_hash=entry_hash,
        root_hash=tree.root_hash,
        proof_path=proof_path,
        verified=False,
    )

    verified = service.verify_proof(proof)

    assert verified is True


def test_merkle_proof_invalid():
    """Merkle Proof Verifikation sollte manipulierten Proof ablehnen."""
    service = MerkleTreeService()
    entries = [
        "entry1",
        "entry2",
        "entry3",
        "entry4",
    ]

    tree = service.build_tree(entries)

    # Manipulierter Entry Hash
    tampered_hash = service._hash("tampered_entry")
    proof_path = service._generate_proof_path(0, tree)

    proof = MerkleProof(
        entry_hash=tampered_hash,  # FALSCH
        root_hash=tree.root_hash,
        proof_path=proof_path,
        verified=False,
    )

    verified = service.verify_proof(proof)

    assert verified is False


def test_merkle_proof_tampered_root():
    """Merkle Proof sollte manipulierten Root Hash erkennen."""
    service = MerkleTreeService()
    entries = ["entry1", "entry2"]

    tree = service.build_tree(entries)

    entry_hash = service._hash(entries[0])
    proof_path = service._generate_proof_path(0, tree)

    # Manipulierter Root Hash
    tampered_root = service._hash("tampered_root")

    proof = MerkleProof(
        entry_hash=entry_hash,
        root_hash=tampered_root,  # FALSCH
        proof_path=proof_path,
        verified=False,
    )

    verified = service.verify_proof(proof)

    assert verified is False


# =============================================================================
# Integrity Report Tests
# =============================================================================


@pytest.mark.asyncio
async def test_integrity_report_clean():
    """Integrity Report sollte 100% Score bei validen Daten zeigen."""
    service = MerkleTreeService()
    mock_db = AsyncMock()
    company_id = uuid4()

    # Mock 10 Audit Logs
    logs = []
    for i in range(10):
        log = MagicMock(spec=AuditLog)
        log.id = uuid4()
        log.action = f"action{i}"
        log.user_id = uuid4()
        log.created_at = datetime.now(timezone.utc)
        logs.append(log)

    logs_result = MagicMock()
    logs_result.scalars.return_value.all.return_value = logs

    mock_db.execute.return_value = logs_result

    report = await service.get_integrity_report(company_id, mock_db)

    assert isinstance(report, IntegrityReport)
    assert report.total_entries == 10
    assert report.verified_entries > 0
    assert report.integrity_score == 100.0  # Alle valide
    assert len(report.violations) == 0
    assert report.root_hash is not None


@pytest.mark.asyncio
async def test_integrity_report_no_data():
    """Integrity Report sollte 100% bei keinen Daten zeigen."""
    service = MerkleTreeService()
    mock_db = AsyncMock()
    company_id = uuid4()

    # Mock keine Logs
    logs_result = MagicMock()
    logs_result.scalars.return_value.all.return_value = []

    mock_db.execute.return_value = logs_result

    report = await service.get_integrity_report(company_id, mock_db)

    assert report.total_entries == 0
    assert report.verified_entries == 0
    assert report.integrity_score == 100.0  # Keine Daten = kein Problem
    assert len(report.violations) == 0


# =============================================================================
# Chain Export Tests
# =============================================================================


@pytest.mark.asyncio
async def test_export_with_merkle_tree():
    """Chain Export sollte Merkle Tree einbetten."""
    service = MerkleTreeService()
    mock_db = AsyncMock()
    company_id = uuid4()

    from_date = datetime.now(timezone.utc) - timedelta(days=7)
    to_date = datetime.now(timezone.utc)

    # Mock Audit Logs
    log1 = MagicMock(spec=AuditLog)
    log1.id = uuid4()
    log1.action = "action1"
    log1.user_id = uuid4()
    log1.created_at = datetime.now(timezone.utc)
    log1.changes = {"field": "value"}

    log2 = MagicMock(spec=AuditLog)
    log2.id = uuid4()
    log2.action = "action2"
    log2.user_id = uuid4()
    log2.created_at = datetime.now(timezone.utc)
    log2.changes = {"field2": "value2"}

    logs_result = MagicMock()
    logs_result.scalars.return_value.all.return_value = [log1, log2]

    mock_db.execute.return_value = logs_result

    result_bytes = await service.export_chain(company_id, from_date, to_date, mock_db)

    assert isinstance(result_bytes, bytes)

    # Decode und parse JSON
    import json
    data = json.loads(result_bytes.decode('utf-8'))

    assert "merkle_tree" in data
    assert "audit_logs" in data
    assert data["company_id"] == str(company_id)
    assert len(data["audit_logs"]) == 2

    # Check Merkle Tree Struktur
    merkle_tree = data["merkle_tree"]
    assert "root_hash" in merkle_tree
    assert merkle_tree["leaf_count"] == 2


# =============================================================================
# Hash Consistency Tests
# =============================================================================


def test_sha256_hash_consistency():
    """SHA256 Hash sollte konsistent sein für gleiche Inputs."""
    service = MerkleTreeService()

    data = "test_data_123"
    hash1 = service._hash(data)
    hash2 = service._hash(data)

    assert hash1 == hash2
    assert len(hash1) == 64  # SHA256 hex


def test_combine_hashes():
    """Combine Hashes sollte deterministisch sein."""
    service = MerkleTreeService()

    left = service._hash("left")
    right = service._hash("right")

    combined1 = service._combine_hashes(left, right)
    combined2 = service._combine_hashes(left, right)

    assert combined1 == combined2
    assert len(combined1) == 64


def test_combine_hashes_order_matters():
    """Combine Hashes sollte Reihenfolge berücksichtigen."""
    service = MerkleTreeService()

    left = service._hash("left")
    right = service._hash("right")

    combined_lr = service._combine_hashes(left, right)
    combined_rl = service._combine_hashes(right, left)

    # Links-Rechts vs. Rechts-Links sollte unterschiedlich sein
    assert combined_lr != combined_rl


# =============================================================================
# Chain Status Tests
# =============================================================================


@pytest.mark.asyncio
async def test_chain_status():
    """Chain sollte korrekte Statistiken liefern."""
    service = MerkleTreeService()
    mock_db = AsyncMock()
    company_id = uuid4()

    # Mock 100 Audit Logs
    logs = []
    for i in range(100):
        log = MagicMock(spec=AuditLog)
        log.id = uuid4()
        log.action = f"action{i}"
        log.user_id = uuid4()
        log.created_at = datetime.now(timezone.utc)
        logs.append(log)

    logs_result = MagicMock()
    logs_result.scalars.return_value.all.return_value = logs

    mock_db.execute.return_value = logs_result

    report = await service.get_integrity_report(company_id, mock_db)

    assert report.total_entries == 100
    # Sample size sollte ca. 10% sein (min 10)
    assert report.verified_entries >= 10
    assert report.integrity_score <= 100.0


# Import timedelta for test_export_with_merkle_tree
from datetime import timedelta
