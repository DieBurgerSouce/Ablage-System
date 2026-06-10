# -*- coding: utf-8 -*-
"""W3-F4: DATEV-Export-Vorprüfung — validation_results in preview_export.

Testet fokussiert die neue Pro-Dokument-Validierung (exportierbar vs.
übersprungen mit Grund), indem die DATEV-Mapping-Maschinerie gemockt wird.
So bleibt der Test unabhängig von Kontenrahmen/Vendor-Mappings und prüft
genau den F4-Beitrag.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.datev.export_service import DATEVExportService


def _doc(filename: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        original_filename=filename,
        filename=filename,
        extracted_data={"invoice": {}},
    )


@pytest.mark.asyncio
async def test_preview_export_builds_validation_results(monkeypatch) -> None:
    """included -> status ok, skipped -> status error mit Grund aus Warnung."""
    service = DATEVExportService()

    ok_doc = _doc("rechnung_ok.pdf")
    bad_doc = _doc("rechnung_kaputt.pdf")

    # Abhaengigkeiten der preview_export-Pipeline mocken
    monkeypatch.setattr(
        service, "_get_config", AsyncMock(return_value=SimpleNamespace(
            id=uuid.uuid4(), kontenrahmen="SKR03",
        ))
    )
    monkeypatch.setattr(service, "_get_kontenrahmen", lambda _k: object())
    monkeypatch.setattr(service, "_get_vendor_mappings", AsyncMock(return_value={}))
    monkeypatch.setattr(
        service, "_get_exportable_documents",
        AsyncMock(return_value=[ok_doc, bad_doc]),
    )

    buchung = SimpleNamespace(
        umsatz=Decimal("119.00"),
        belegdatum=__import__("datetime").date(2026, 1, 15),
        belegfeld_1="RE-1", soll_haben="S", konto="8400", gegenkonto="1200",
        bu_schluessel="", buchungstext="Test",
    )
    monkeypatch.setattr(
        service, "_map_documents_async",
        AsyncMock(return_value=(
            [buchung],
            [ok_doc.id],          # included
            [bad_doc.id],         # skipped
            [f"Dokument {bad_doc.id}: Keine gültige USt-IdNr"],  # warnings
        )),
    )

    preview = await service.preview_export(db=AsyncMock(), user_id=uuid.uuid4())

    assert preview.skipped_count == 1
    results = {r.document_id: r for r in preview.validation_results}
    assert len(results) == 2

    assert results[ok_doc.id].status == "ok"
    assert results[ok_doc.id].filename == "rechnung_ok.pdf"

    assert results[bad_doc.id].status == "error"
    assert results[bad_doc.id].filename == "rechnung_kaputt.pdf"
    assert results[bad_doc.id].reason == "Keine gültige USt-IdNr"


@pytest.mark.asyncio
async def test_preview_export_empty_without_config(monkeypatch) -> None:
    """Ohne Konfiguration: leere validation_results, kein Fehler."""
    service = DATEVExportService()
    monkeypatch.setattr(service, "_get_config", AsyncMock(return_value=None))

    preview = await service.preview_export(db=AsyncMock(), user_id=uuid.uuid4())

    assert preview.document_count == 0
    assert preview.validation_results == []
