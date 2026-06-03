# -*- coding: utf-8 -*-
"""Unit-Tests fuer die autonome Folder-Ablage (M16).

`propose_filing_location` / `execute_filing` waren deaktiviert ("Folder-Model
nicht implementiert"). Seit das Folder-System existiert (app/db/models_folder.py)
sind sie echt. Diese Tests verifizieren Vorschlag + Ausfuehrung mit gemockter
DB-Session (keine echte DB noetig).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.ai.autonomous_actions_service import (
    AutonomousAction,
    AutonomousActionsService,
)


def _result(scalar=None, scalars_list=None, rows=None) -> MagicMock:
    """Baut ein gemocktes SQLAlchemy-Result (sync-Zugriffe auf das Result-Objekt)."""
    res = MagicMock()
    res.scalar_one_or_none.return_value = scalar
    res.scalars.return_value.all.return_value = scalars_list if scalars_list is not None else []
    res.all.return_value = rows if rows is not None else []
    return res


@pytest.fixture
def service() -> AutonomousActionsService:
    return AutonomousActionsService(db=AsyncMock())


def _document() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        document_type="invoice",
        business_entity_id=None,
    )


def _folder(name: str = "Rechnungen") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        name=name,
        path=f"/{name}",
        folder_type="invoice",
        deleted_at=None,
    )


@pytest.mark.asyncio
async def test_propose_filing_uses_default_folder_by_type(service):
    """Ohne Verlauf wird der Standard-Ordner nach Dokumenttyp vorgeschlagen."""
    document = _document()
    folder = _folder()
    # Reihenfolge der db.execute-Aufrufe: Dokument laden, Verlauf (leer), Typ-Ordner
    service.db.execute = AsyncMock(side_effect=[
        _result(scalar=document),       # Dokument
        _result(rows=[]),               # _find_folder_by_history -> kein Treffer
        _result(scalar=folder),         # _find_folder_by_document_type
    ])

    proposal = await service.propose_filing_location(document.id, company_id=document.company_id)

    assert proposal.action_type == AutonomousAction.FILE_DOCUMENT
    assert proposal.proposed_value["folder_id"] == str(folder.id)
    assert proposal.proposed_value["folder_name"] == "Rechnungen"
    assert proposal.confidence == service.config.filing_suggest_confidence


@pytest.mark.asyncio
async def test_propose_filing_prefers_history(service):
    """Mit Verlauf wird der historisch genutzte Ordner mit hoeherer Confidence vorgeschlagen."""
    document = _document()
    folder = _folder("Stamm-Lieferant")
    fid = folder.id
    service.db.execute = AsyncMock(side_effect=[
        _result(scalar=document),                 # Dokument
        _result(rows=[(fid, 9)]),                 # Verlauf-Aggregat (folder_id, count)
        _result(scalar=folder),                   # Folder zur top folder_id laden
    ])

    proposal = await service.propose_filing_location(document.id, company_id=document.company_id)

    assert proposal.proposed_value["folder_id"] == str(fid)
    assert proposal.confidence >= 0.9  # ein einzelner dominanter Treffer


@pytest.mark.asyncio
async def test_propose_filing_document_not_found(service):
    """Unbekanntes Dokument -> Confidence 0, manuelle Ablage."""
    service.db.execute = AsyncMock(side_effect=[_result(scalar=None)])

    proposal = await service.propose_filing_location(uuid.uuid4(), company_id=uuid.uuid4())

    assert proposal.confidence == 0.0
    assert proposal.requires_confirmation is True
    assert proposal.proposed_value == {}


@pytest.mark.asyncio
async def test_execute_filing_success(service):
    """Erfolgreiche Ablage erzeugt eine primaere FolderDocument-Verknuepfung."""
    document = _document()
    folder = _folder()
    service.db.execute = AsyncMock(side_effect=[
        _result(scalar=document),      # Dokument laden
        _result(scalar=folder),        # Folder laden
        _result(scalars_list=[]),      # bestehende FolderDocuments (keine)
    ])
    service.db.add = MagicMock()
    service.db.commit = AsyncMock()

    result = await service.execute_filing(
        document.id, folder.id, company_id=document.company_id
    )

    assert result.success is True
    assert result.applied_value["folder_id"] == str(folder.id)
    assert result.was_autonomous is True
    service.db.add.assert_called_once()
    service.db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_filing_folder_not_found(service):
    """Fehlender/fremder Ziel-Ordner -> kein Erfolg, kein Commit."""
    document = _document()
    service.db.execute = AsyncMock(side_effect=[
        _result(scalar=document),      # Dokument vorhanden
        _result(scalar=None),          # Folder nicht gefunden / fremder Mandant
    ])
    service.db.commit = AsyncMock()

    result = await service.execute_filing(document.id, uuid.uuid4(), company_id=document.company_id)

    assert result.success is False
    assert "Ordner" in (result.error_message or "")
    service.db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_filing_document_not_found(service):
    """Unbekanntes/fremdes Dokument -> kein Erfolg."""
    service.db.execute = AsyncMock(side_effect=[_result(scalar=None)])
    service.db.commit = AsyncMock()

    result = await service.execute_filing(uuid.uuid4(), uuid.uuid4(), company_id=uuid.uuid4())

    assert result.success is False
    service.db.commit.assert_not_awaited()
