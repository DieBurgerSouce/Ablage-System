# -*- coding: utf-8 -*-
"""DoS-Haertung von EntityExtractionService.extract_entities (2026-06-25).

api-Hang-Defense-in-Depth (letzter Restkandidat aus dem api-Hang/DoS-Audit):
extract_entities laeuft ~20 Regex-finditer-Scans ueber den vollen OCR-Text. Die
Patterns sind linear (disjunkte Klassen, kein catastrophic backtracking), aber
ueber pathologisch grossen OCR-Text summiert sich das. Diese Tests verifizieren
die harte Input-Laengen-Schranke.
"""

from unittest.mock import patch

import pytest

from app.services.entity_extraction_service import (
    EntityExtractionService,
    MAX_EXTRACTION_TEXT_LEN,
)


@pytest.mark.asyncio
async def test_extract_entities_caps_oversized_text():
    """Text > Schranke wird gekappt -> extraction_details spiegelt die Schranke."""
    svc = EntityExtractionService()  # db ist optional
    with patch(
        "app.services.entity_extraction_service.MAX_EXTRACTION_TEXT_LEN", 1000
    ):
        text = "wort " * 500  # 2500 Zeichen > 1000
        result = await svc.extract_entities(text)
    assert result.extraction_details["text_length"] == 1000


@pytest.mark.asyncio
async def test_extract_entities_normal_text_not_truncated():
    """Reale (kurze) Texte bleiben unveraendert (keine Regression)."""
    svc = EntityExtractionService()
    text = "Rechnung von Mustermann GmbH, USt-IdNr DE123456789."
    result = await svc.extract_entities(text)
    assert result.extraction_details["text_length"] == len(text)


def test_max_extraction_text_len_sane():
    """Schranke gross genug fuer reale Mehrseiter, klein genug als DoS-Grenze."""
    assert 500_000 <= MAX_EXTRACTION_TEXT_LEN <= 10_000_000
