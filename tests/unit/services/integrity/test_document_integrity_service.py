# -*- coding: utf-8 -*-
"""
Unit tests fuer DocumentIntegrityService.

Tests:
- SHA-256 Hash-Berechnung
- Dokument-Hash speichern und abrufen
- Verifizierung (gueltig und manipuliert)
- Merkle-Baum Konstruktion
- Merkle-Root Berechnung (einzeln, gerade, ungerade)
- Integritaetsbericht-Generierung
"""

import hashlib
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.integrity.document_integrity_service import DocumentIntegrityService
from app.db.models_integrity import DocumentHash, VerificationStatus


@pytest.fixture
def service():
    """Erstellt eine DocumentIntegrityService-Instanz."""
    return DocumentIntegrityService()


@pytest.fixture
def mock_db():
    """Erstellt eine Mock-Datenbank-Session."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.delete = AsyncMock()
    return db


@pytest.fixture
def sample_content():
    """Beispiel-Dateiinhalt."""
    return b"Dies ist ein Testdokument fuer die Integritaetspruefung."


@pytest.fixture
def sample_hash(sample_content):
    """Erwarteter SHA-256 Hash des Beispielinhalts."""
    return hashlib.sha256(sample_content).hexdigest()


class TestComputeSha256:
    """Tests fuer die SHA-256 Hash-Berechnung."""

    def test_compute_sha256(self, service, sample_content, sample_hash):
        """SHA-256 Hash wird korrekt berechnet."""
        result = service._compute_sha256(sample_content)
        assert result == sample_hash
        assert len(result) == 64  # SHA-256 hex digest ist immer 64 Zeichen

    def test_compute_sha256_empty(self, service):
        """Leere Bytes ergeben den bekannten SHA-256 Empty-Hash."""
        result = service._compute_sha256(b"")
        expected = hashlib.sha256(b"").hexdigest()
        assert result == expected

    def test_compute_sha256_deterministic(self, service, sample_content):
        """Gleicher Input ergibt immer gleichen Hash."""
        hash1 = service._compute_sha256(sample_content)
        hash2 = service._compute_sha256(sample_content)
        assert hash1 == hash2

    def test_compute_sha256_different_content(self, service):
        """Unterschiedlicher Input ergibt unterschiedliche Hashes."""
        hash1 = service._compute_sha256(b"Dokument A")
        hash2 = service._compute_sha256(b"Dokument B")
        assert hash1 != hash2


class TestComputeDocumentHash:
    """Tests fuer das Speichern eines Dokument-Hashes in der DB."""

    @pytest.mark.asyncio
    async def test_compute_document_hash_new(
        self, service, mock_db, sample_content, sample_hash
    ):
        """Neuer Hash wird erstellt wenn keiner existiert."""
        document_id = uuid4()
        company_id = uuid4()

        # Kein existierender Hash
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.compute_document_hash(
            mock_db, document_id, sample_content, company_id
        )

        # Pruefen dass ein neues Objekt zur Session hinzugefuegt wurde
        mock_db.add.assert_called_once()
        mock_db.flush.assert_awaited_once()

        added_obj = mock_db.add.call_args[0][0]
        assert isinstance(added_obj, DocumentHash)
        assert added_obj.document_id == document_id
        assert added_obj.company_id == company_id
        assert added_obj.file_hash == sample_hash
        assert added_obj.hash_algorithm == "sha-256"
        assert added_obj.file_size_bytes == len(sample_content)

    @pytest.mark.asyncio
    async def test_compute_document_hash_update_existing(
        self, service, mock_db, sample_content, sample_hash
    ):
        """Bestehender Hash wird aktualisiert."""
        document_id = uuid4()
        company_id = uuid4()

        existing_hash = MagicMock(spec=DocumentHash)
        existing_hash.document_id = document_id
        existing_hash.company_id = company_id
        existing_hash.file_hash = "old_hash_value"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_hash
        mock_db.execute.return_value = mock_result

        result = await service.compute_document_hash(
            mock_db, document_id, sample_content, company_id
        )

        assert result is existing_hash
        assert existing_hash.file_hash == sample_hash
        assert existing_hash.file_size_bytes == len(sample_content)
        assert existing_hash.verification_status == VerificationStatus.UNVERIFIED.value
        mock_db.add.assert_not_called()


class TestVerifyDocument:
    """Tests fuer die Dokument-Verifizierung."""

    @pytest.mark.asyncio
    async def test_verify_document_valid(
        self, service, mock_db, sample_content, sample_hash
    ):
        """Verifizierung mit uebereinstimmendem Hash ist erfolgreich."""
        document_id = uuid4()

        existing_hash = MagicMock(spec=DocumentHash)
        existing_hash.file_hash = sample_hash
        existing_hash.verification_status = VerificationStatus.UNVERIFIED.value

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_hash
        mock_db.execute.return_value = mock_result

        is_valid, message = await service.verify_document(
            mock_db, document_id, sample_content
        )

        assert is_valid is True
        assert "bestaetigt" in message
        assert existing_hash.verification_status == VerificationStatus.VERIFIED.value
        assert existing_hash.verified_at is not None

    @pytest.mark.asyncio
    async def test_verify_document_tampered(
        self, service, mock_db, sample_hash
    ):
        """Verifizierung mit abweichendem Hash erkennt Manipulation."""
        document_id = uuid4()

        existing_hash = MagicMock(spec=DocumentHash)
        existing_hash.file_hash = sample_hash
        existing_hash.verification_status = VerificationStatus.UNVERIFIED.value

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_hash
        mock_db.execute.return_value = mock_result

        tampered_content = b"Manipulierter Inhalt!"
        is_valid, message = await service.verify_document(
            mock_db, document_id, tampered_content
        )

        assert is_valid is False
        assert "manipuliert" in message.lower()
        assert existing_hash.verification_status == VerificationStatus.TAMPERED.value

    @pytest.mark.asyncio
    async def test_verify_document_no_hash(self, service, mock_db, sample_content):
        """Verifizierung ohne gespeicherten Hash schlaegt fehl."""
        document_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        is_valid, message = await service.verify_document(
            mock_db, document_id, sample_content
        )

        assert is_valid is False
        assert "kein hash" in message.lower()


class TestMerkleTree:
    """Tests fuer die Merkle-Baum Konstruktion."""

    def test_compute_merkle_root_single(self, service):
        """Merkle-Root eines einzelnen Dokuments ist der Hash selbst."""
        single_hash = hashlib.sha256(b"einziges_dokument").hexdigest()
        root = service._compute_merkle_root([single_hash])
        assert root == single_hash

    def test_compute_merkle_root_even(self, service):
        """Merkle-Root mit gerader Anzahl Blaetter."""
        hashes = [
            hashlib.sha256(b"doc_a").hexdigest(),
            hashlib.sha256(b"doc_b").hexdigest(),
        ]
        root = service._compute_merkle_root(hashes)

        # Manuell berechnen
        combined = hashes[0] + hashes[1]
        expected_root = hashlib.sha256(combined.encode("utf-8")).hexdigest()
        assert root == expected_root

    def test_compute_merkle_root_odd(self, service):
        """Merkle-Root mit ungerader Anzahl (letzter Hash dupliziert)."""
        hashes = [
            hashlib.sha256(b"doc_a").hexdigest(),
            hashlib.sha256(b"doc_b").hexdigest(),
            hashlib.sha256(b"doc_c").hexdigest(),
        ]
        root = service._compute_merkle_root(hashes)

        # Manuell: level 1
        combined_ab = hashes[0] + hashes[1]
        hash_ab = hashlib.sha256(combined_ab.encode("utf-8")).hexdigest()
        # c wird dupliziert
        combined_cc = hashes[2] + hashes[2]
        hash_cc = hashlib.sha256(combined_cc.encode("utf-8")).hexdigest()
        # level 2 (root)
        combined_root = hash_ab + hash_cc
        expected_root = hashlib.sha256(combined_root.encode("utf-8")).hexdigest()

        assert root == expected_root

    def test_compute_merkle_root_empty(self, service):
        """Leere Hash-Liste ergibt den Hash von 'empty'."""
        root = service._compute_merkle_root([])
        expected = hashlib.sha256(b"empty").hexdigest()
        assert root == expected

    def test_build_merkle_level(self, service):
        """Eine Ebene des Merkle-Baums wird korrekt berechnet."""
        hashes = [
            hashlib.sha256(b"a").hexdigest(),
            hashlib.sha256(b"b").hexdigest(),
        ]
        next_level = service._build_merkle_level(hashes)

        assert len(next_level) == 1
        expected = hashlib.sha256(
            (hashes[0] + hashes[1]).encode("utf-8")
        ).hexdigest()
        assert next_level[0] == expected

    def test_build_merkle_level_odd_duplicates_last(self, service):
        """Ungerade Anzahl dupliziert den letzten Hash."""
        hashes = [
            hashlib.sha256(b"a").hexdigest(),
            hashlib.sha256(b"b").hexdigest(),
            hashlib.sha256(b"c").hexdigest(),
        ]
        next_level = service._build_merkle_level(hashes)

        # 3 Hashes -> 4 (c dupliziert) -> 2 Paare
        assert len(next_level) == 2

    @pytest.mark.asyncio
    async def test_build_daily_merkle_tree(self, service, mock_db):
        """Taeglicher Merkle-Baum wird korrekt erstellt."""
        company_id = uuid4()
        tree_date = date(2026, 2, 13)

        doc_hash_a = MagicMock(spec=DocumentHash)
        doc_hash_a.id = uuid4()
        doc_hash_a.file_hash = hashlib.sha256(b"doc_a").hexdigest()

        doc_hash_b = MagicMock(spec=DocumentHash)
        doc_hash_b.id = uuid4()
        doc_hash_b.file_hash = hashlib.sha256(b"doc_b").hexdigest()

        # Sortiert nach file_hash fuer Determinismus
        sorted_hashes = sorted(
            [doc_hash_a, doc_hash_b],
            key=lambda x: x.file_hash,
        )

        # Mock execute calls: first for doc hashes, second for old nodes
        doc_result = MagicMock()
        doc_result.scalars.return_value.all.return_value = sorted_hashes

        old_nodes_result = MagicMock()
        old_nodes_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [doc_result, old_nodes_result]

        root = await service.build_daily_merkle_tree(
            mock_db, company_id, tree_date
        )

        # Root sollte ein 64-Zeichen Hex-String sein
        assert len(root) == 64
        assert mock_db.add.called
        assert mock_db.flush.await_count == 1


class TestGenerateIntegrityReport:
    """Tests fuer die Bericht-Generierung."""

    @pytest.mark.asyncio
    async def test_generate_integrity_report(self, service, mock_db):
        """Integritaetsbericht wird korrekt generiert."""
        company_id = uuid4()
        user_id = uuid4()
        report_date = date(2026, 2, 13)

        # Mock counts: total=10, verified=7, tampered=1, unverified=2
        total_result = MagicMock()
        total_result.scalar_one.return_value = 10

        verified_result = MagicMock()
        verified_result.scalar_one.return_value = 7

        tampered_result = MagicMock()
        tampered_result.scalar_one.return_value = 1

        # Mock merkle root query (none found -> will build)
        root_query_result = MagicMock()
        root_query_result.scalar_one_or_none.return_value = None

        # Mock for build_daily_merkle_tree (doc hashes + old nodes)
        build_doc_result = MagicMock()
        build_doc_result.scalars.return_value.all.return_value = []

        build_old_result = MagicMock()
        build_old_result.scalars.return_value.all.return_value = []

        # Tampered docs detail query (tampered_count=1 > 0)
        tampered_detail = MagicMock()
        tampered_detail.all.return_value = [
            MagicMock(document_id=uuid4(), verified_at=datetime.now(timezone.utc))
        ]

        mock_db.execute.side_effect = [
            total_result,        # total count
            verified_result,     # verified count
            tampered_result,     # tampered count
            root_query_result,   # merkle root query
            build_doc_result,    # build_daily: doc hashes
            build_old_result,    # build_daily: old nodes
            tampered_detail,     # tampered docs detail
        ]

        report = await service.generate_integrity_report(
            mock_db, company_id, user_id, report_date
        )

        # Pruefen dass Report zur Session hinzugefuegt wurde
        # (add wird auch in build_daily aufgerufen, also mindestens einmal)
        assert mock_db.add.called
        mock_db.flush.assert_awaited()
