# -*- coding: utf-8 -*-
"""Regressionstests fuer AutoFilingService.auto_file_document (OPEN-11).

Sichert ab, dass Auto-Filing eine ECHTE folder_documents-Assoziation erzeugt
(frueher: stilles No-Op via nicht-existenter Document.folder_id-Spalte) und die
Kategorie kanonisch auf document_type abbildet (wie bulk_move_category).
"""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.models import DocumentType
from app.db.models_folder import FolderDocument
from app.services.auto_filing_service import AutoFilingService

_UNSET = object()


def _result(scalar=_UNSET):
    """Mock fuer ein db.execute()-Ergebnis mit scalar_one_or_none()."""
    res = MagicMock()
    if scalar is not _UNSET:
        res.scalar_one_or_none = MagicMock(return_value=scalar)
    return res


def _make_rule(folder_id=None, category=None):
    rule = MagicMock()
    rule.id = uuid.uuid4()
    rule.name = "Regel A"
    rule.target_folder_id = folder_id
    rule.target_category = category
    rule.training_sample_count = 0
    return rule


@pytest.mark.asyncio
async def test_auto_file_creates_real_folder_association():
    """Filing erzeugt eine echte primaere FolderDocument-Verknuepfung +
    bildet die Kategorie auf document_type ab."""
    service = AutoFilingService(db=AsyncMock())
    company_id = uuid.uuid4()
    document_id = uuid.uuid4()
    folder_id = uuid.uuid4()

    document = MagicMock()
    document.id = document_id
    document.document_type = DocumentType.OTHER.value
    rule = _make_rule(folder_id=folder_id, category="rechnungen")

    service.classify_document = AsyncMock(return_value=rule)
    # db.execute: 1) Dokument laden, 2) bestehende Assoziation (keine),
    #             3) is_primary-Reset-Update
    service.db.execute = AsyncMock(
        side_effect=[_result(scalar=document), _result(scalar=None), _result()]
    )
    service.db.add = MagicMock()
    service.db.flush = AsyncMock()

    result = await service.auto_file_document(service.db, company_id, document_id)

    assert result["filed"] is True
    assert result["folder_id"] == str(folder_id)

    # Echte FolderDocument-Assoziation (kein Phantom-Attribut auf Document)
    service.db.add.assert_called_once()
    added = service.db.add.call_args.args[0]
    assert isinstance(added, FolderDocument)
    assert added.folder_id == folder_id
    assert added.document_id == document_id
    assert added.is_primary is True

    # Kategorie kanonisch auf document_type abgebildet
    assert document.document_type == DocumentType.INVOICE.value


@pytest.mark.asyncio
async def test_auto_file_idempotent_when_already_in_folder():
    """Existiert die Assoziation bereits, wird KEINE Doppelverknuepfung erzeugt."""
    service = AutoFilingService(db=AsyncMock())
    document_id = uuid.uuid4()
    folder_id = uuid.uuid4()

    document = MagicMock()
    document.id = document_id
    rule = _make_rule(folder_id=folder_id, category=None)

    existing = FolderDocument(
        folder_id=folder_id, document_id=document_id, is_primary=True
    )
    service.classify_document = AsyncMock(return_value=rule)
    service.db.execute = AsyncMock(
        side_effect=[_result(scalar=document), _result(scalar=existing)]
    )
    service.db.add = MagicMock()
    service.db.flush = AsyncMock()

    result = await service.auto_file_document(
        service.db, uuid.uuid4(), document_id
    )

    assert result["filed"] is True
    service.db.add.assert_not_called()


@pytest.mark.asyncio
async def test_auto_file_unknown_category_does_not_crash():
    """Unbekannte Kategorie wird vermerkt, aendert document_type aber nicht."""
    service = AutoFilingService(db=AsyncMock())
    document_id = uuid.uuid4()

    document = MagicMock()
    document.id = document_id
    document.document_type = DocumentType.OTHER.value
    rule = _make_rule(folder_id=None, category="voellig-unbekannt")

    service.classify_document = AsyncMock(return_value=rule)
    service.db.execute = AsyncMock(side_effect=[_result(scalar=document)])
    service.db.add = MagicMock()
    service.db.flush = AsyncMock()

    result = await service.auto_file_document(
        service.db, uuid.uuid4(), document_id
    )

    assert result["filed"] is True
    assert result["target_category"] == "voellig-unbekannt"
    assert document.document_type == DocumentType.OTHER.value


@pytest.mark.asyncio
async def test_auto_file_no_rule_returns_unfiled():
    """Ohne passende Regel: filed=False, keine DB-Mutation."""
    service = AutoFilingService(db=AsyncMock())
    service.classify_document = AsyncMock(return_value=None)
    service.db.add = MagicMock()

    result = await service.auto_file_document(
        service.db, uuid.uuid4(), uuid.uuid4()
    )

    assert result["filed"] is False
    service.db.add.assert_not_called()
