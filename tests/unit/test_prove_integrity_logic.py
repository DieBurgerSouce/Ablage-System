# -*- coding: utf-8 -*-
"""Trust-Theater K1 (2026-07-12): Logik-Beweise für die Live-Beweisführung.

Negativ-Beweis in ISOLIERTER Testumgebung: Die Tests bauen ihre eigenen
Objekte (Archiv, Chain-Einträge) im Speicher, manipulieren NUR diese Kopien
und beweisen, dass die echte SHA-256-/Ketten-Logik Manipulation erkennt.
Das echte Archiv (Live-DB, unlöschbare gobd_audit_chain) wird nie berührt —
ein Live-Rot-Test würde die Beweiskette dauerhaft mit
INTEGRITY_CHECK_FAILED-Einträgen verschmutzen.

Async-Muster wie test_rls_guc_persistence.py (mark.asyncio nur wo nötig;
hier reichen frische Event-Loops pro Aufruf via asyncio.run).
"""
from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import datetime, timezone
from typing import List, Optional

import pytest

from app.db.bpmn_models.gobd import AuditChainEventType
from app.services.compliance.audit_chain_service import (
    AuditChainService,
    ChainEntry,
)


# =========================================================================
# Hilfen: In-Memory-Kette bauen (exakt die Produktions-Hash-Mathematik)
# =========================================================================


class _FakeChainEntry:
    """Duck-typed AuditChainEntry — nur die von verify gelesenen Felder."""

    def __init__(
        self,
        sequence_number: int,
        event_type: str,
        event_data: dict,
        document_id: Optional[uuid.UUID],
        user_id: Optional[uuid.UUID],
        previous_hash: Optional[str],
        content_hash: str,
        combined_hash: str,
    ) -> None:
        self.id = uuid.uuid4()
        self.sequence_number = sequence_number
        self.event_type = event_type
        self.event_data = event_data
        self.document_id = document_id
        self.user_id = user_id
        self.previous_hash = previous_hash
        self.content_hash = content_hash
        self.combined_hash = combined_hash
        self.created_at = datetime.now(timezone.utc)
        self.is_verified = False
        self.last_verified_at: Optional[datetime] = None
        self.verification_error: Optional[str] = None


def _build_chain(document_id: uuid.UUID, n: int = 3) -> List[_FakeChainEntry]:
    """Baut eine gültige Kette mit der echten Service-Hash-Logik."""
    service = AuditChainService()
    entries: List[_FakeChainEntry] = []
    previous_hash: Optional[str] = None
    for i in range(1, n + 1):
        entry = ChainEntry(
            event_type=AuditChainEventType.DOCUMENT_ARCHIVED,
            event_data={"schritt": i},
            document_id=document_id,
            user_id=None,
        )
        content_hash = service._calculate_content_hash(entry)
        combined_hash = service._calculate_combined_hash(previous_hash, content_hash)
        entries.append(
            _FakeChainEntry(
                sequence_number=i,
                event_type=AuditChainEventType.DOCUMENT_ARCHIVED.value,
                event_data={"schritt": i},
                document_id=document_id,
                user_id=None,
                previous_hash=previous_hash,
                content_hash=content_hash,
                combined_hash=combined_hash,
            )
        )
        previous_hash = combined_hash
    return entries


def _service_mit_fake_kette(entries: List[_FakeChainEntry]) -> AuditChainService:
    """Service, dessen DB-Getter aus der In-Memory-Kette lesen."""
    service = AuditChainService()
    by_seq = {e.sequence_number: e for e in entries}

    async def fake_get_entries_by_document(db, company_id, document_id, limit=100):
        return list(entries)

    async def fake_get_entry_by_sequence(db, company_id, sequence_number):
        return by_seq.get(sequence_number)

    service.get_entries_by_document = fake_get_entries_by_document  # type: ignore[method-assign]
    service.get_entry_by_sequence = fake_get_entry_by_sequence  # type: ignore[method-assign]
    return service


# =========================================================================
# verify_document_entries: Kette intakt / manipuliert / gebrochen / leer
# =========================================================================


def test_kette_intakt_wird_als_gueltig_bewiesen():
    doc_id = uuid.uuid4()
    entries = _build_chain(doc_id, n=3)
    service = _service_mit_fake_kette(entries)

    result = asyncio.run(
        service.verify_document_entries(db=None, company_id=uuid.uuid4(), document_id=doc_id)
    )

    assert result.valid is True
    assert result.total_entries == 3
    assert result.verified_entries == 3
    assert result.broken_at_sequence is None
    assert all(e.is_verified for e in entries)


def test_manipuliertes_event_data_bricht_die_kette():
    """Negativ-Beweis: nachträglich geänderte Protokolldaten fliegen auf."""
    doc_id = uuid.uuid4()
    entries = _build_chain(doc_id, n=3)
    # Manipulation NUR an der In-Memory-Kopie
    entries[1].event_data = {"schritt": 2, "manipuliert": True}
    service = _service_mit_fake_kette(entries)

    result = asyncio.run(
        service.verify_document_entries(db=None, company_id=uuid.uuid4(), document_id=doc_id)
    )

    assert result.valid is False
    assert result.broken_at_sequence == 2
    assert result.error_message is not None
    assert "Sequenz 2" in result.error_message


def test_gebrochene_verkettung_wird_erkannt():
    """previous_hash zeigt nicht mehr auf den Vorgänger -> Bruch."""
    doc_id = uuid.uuid4()
    entries = _build_chain(doc_id, n=3)
    service = AuditChainService()
    # Eintrag 3 bekommt einen gefälschten previous_hash — combined_hash wird
    # passend nachgerechnet, damit NUR die Verkettung (nicht der Selbst-Hash)
    # bricht.
    fake_previous = "f" * 64
    entries[2].previous_hash = fake_previous
    entries[2].combined_hash = service._calculate_combined_hash(
        fake_previous, entries[2].content_hash
    )
    service = _service_mit_fake_kette(entries)

    result = asyncio.run(
        service.verify_document_entries(db=None, company_id=uuid.uuid4(), document_id=doc_id)
    )

    assert result.valid is False
    assert result.broken_at_sequence == 3


def test_leere_kette_ist_ehrlich_none():
    service = _service_mit_fake_kette([])

    result = asyncio.run(
        service.verify_document_entries(
            db=None, company_id=uuid.uuid4(), document_id=uuid.uuid4()
        )
    )

    assert result.valid is None
    assert result.total_entries == 0


# =========================================================================
# verify_archive_integrity: Original grün / manipulierte Kopie rot
# =========================================================================


class _FakeArchive:
    """Duck-typed DocumentArchive für die Hash-Prüfung."""

    def __init__(self, company_id: uuid.UUID, content: bytes) -> None:
        self.id = uuid.uuid4()
        self.document_id = uuid.uuid4()
        self.company_id = company_id
        self.content_hash = hashlib.sha256(content).hexdigest()
        self.signature_certificate: Optional[str] = None
        self.is_verified = False
        self.last_verification_at: Optional[datetime] = None
        self.verification_failed_reason: Optional[str] = None


class _FakeSession:
    """Minimale AsyncSession-Attrappe: get/add/flush."""

    def __init__(self, archive: _FakeArchive) -> None:
        self._archive = archive
        self.added: list = []

    async def get(self, model, pk):
        return self._archive if pk == self._archive.id else None

    def add(self, obj) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None


@pytest.fixture()
def _kein_chain_logging(monkeypatch):
    """log_document_event würde eine echte DB brauchen — hier stummschalten."""

    async def _noop(**kwargs):
        return None

    monkeypatch.setattr(
        "app.services.compliance.archive_service.log_document_event", _noop
    )


def test_original_inhalt_wird_gruen_bewiesen(_kein_chain_logging):
    from app.services.compliance.archive_service import GoBDArchiveService

    company_id = uuid.uuid4()
    original = b"%PDF-1.4 Rechnung Buerohaus Mueller GmbH 119,00 EUR"
    archive = _FakeArchive(company_id, original)
    db = _FakeSession(archive)

    result = asyncio.run(
        GoBDArchiveService().verify_archive_integrity(
            db=db,
            archive_id=archive.id,
            company_id=company_id,
            document_content=original,
        )
    )

    assert result.hash_match is True
    assert archive.is_verified is True
    assert archive.verification_failed_reason is None


def test_manipulierte_kopie_wird_rot_bewiesen(_kein_chain_logging):
    """DER Negativ-Beweis: ein einziges geändertes Byte -> Manipulation rot."""
    from app.services.compliance.archive_service import GoBDArchiveService

    company_id = uuid.uuid4()
    original = b"%PDF-1.4 Rechnung Buerohaus Mueller GmbH 119,00 EUR"
    manipuliert = b"%PDF-1.4 Rechnung Buerohaus Mueller GmbH 919,00 EUR"
    archive = _FakeArchive(company_id, original)
    db = _FakeSession(archive)

    result = asyncio.run(
        GoBDArchiveService().verify_archive_integrity(
            db=db,
            archive_id=archive.id,
            company_id=company_id,
            document_content=manipuliert,
        )
    )

    assert result.hash_match is False
    assert result.expected_hash != result.actual_hash
    assert archive.is_verified is False
    assert archive.verification_failed_reason is not None
    assert "Manipulation" in (result.error_message or "")


def test_tsa_verify_nutzt_digest_bytes_wie_bei_erstellung(
    _kein_chain_logging, monkeypatch
):
    """Regression-Guard für den TSA-Doppel-Hash-Fix (2026-07-12).

    Der Token wird bei der Archivierung über die ROHEN Digest-Bytes erstellt
    (_get_tsa_timestamp: bytes.fromhex(content_hash) -> request_timestamp
    hasht intern nochmal). Verify MUSS daher dieselben Digest-Bytes prüfen —
    wer hier auf den vollen Dateiinhalt „vereinfacht", macht jede
    TSA-Prüfung wieder dauerhaft falsch-negativ.
    """
    from app.services.compliance.archive_service import GoBDArchiveService

    captured: dict = {}

    class _FakeTsaService:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def verify_timestamp(self, token_base64: str, original_data: bytes) -> bool:
            captured["token"] = token_base64
            captured["data"] = original_data
            return True

    # Achtung Namensfalle: Das Modul tsa_service wird im Package-Namespace vom
    # gleichnamigen Singleton verschattet — String-Pfad-monkeypatch träfe die
    # Instanz. Deshalb das Modul explizit via importlib auflösen.
    import importlib

    tsa_module = importlib.import_module("app.services.compliance.tsa_service")
    monkeypatch.setattr(tsa_module, "TimestampAuthorityService", _FakeTsaService)

    company_id = uuid.uuid4()
    original = b"%PDF-1.4 Rechnung Buerohaus Mueller GmbH 119,00 EUR"
    archive = _FakeArchive(company_id, original)
    archive.signature_certificate = "dummy-rfc3161-token-base64"
    db = _FakeSession(archive)

    result = asyncio.run(
        GoBDArchiveService().verify_archive_integrity(
            db=db,
            archive_id=archive.id,
            company_id=company_id,
            document_content=original,
        )
    )

    assert result.tsa_verified is True
    assert captured["token"] == "dummy-rfc3161-token-base64"
    # Exakt die Digest-Bytes der Erstellung — NICHT der volle Dateiinhalt
    assert captured["data"] == hashlib.sha256(original).digest()
    assert captured["data"] != original


def test_fremdes_archiv_wird_verweigert(_kein_chain_logging):
    """Company-Scoping: fremde Firma darf nicht einmal prüfen."""
    from app.services.compliance.archive_service import GoBDArchiveService

    original = b"inhalt"
    archive = _FakeArchive(uuid.uuid4(), original)
    db = _FakeSession(archive)

    with pytest.raises(ValueError):
        asyncio.run(
            GoBDArchiveService().verify_archive_integrity(
                db=db,
                archive_id=archive.id,
                company_id=uuid.uuid4(),  # andere Firma
                document_content=original,
            )
        )
