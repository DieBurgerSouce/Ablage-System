# -*- coding: utf-8 -*-
"""Tests fuer die DoS-Haertung von app/services/ocr.py::quick_ocr_preview (2026-06-22).

Hintergrund (A-Z-Loop-Befund): quick_ocr_preview verarbeitet hochgeladene
(potenziell boesartige/gefuzzte) Dateien im Threadpool. Ohne Schranken kann ein
malformed File Tesseract/pdfium/PIL in einen Endlos-/Riesen-Spin treiben ->
Backend-CPU-Spin, Request haengt ~unbegrenzt. Diese Tests verifizieren die
Schranken (Datei-Groesse, Bild-Pixel, Tesseract-Timeout) mit Mocks (kein echtes
OCR noetig).
"""

import pytest
from unittest.mock import patch, MagicMock

# app/services/ocr.py koexistiert mit dem Package app/services/ocr/ und wird von
# dessen __init__.py via importlib als Ad-hoc-Modul (_ocr_module) geladen;
# quick_ocr_preview wird daraus re-exportiert. Die gehaertete Funktion liest ihre
# DoS-Guards (PILLOW_AVAILABLE, Image, OCR_MAX_*, OCR_PREVIEW_TIMEOUT_SECONDS) aus
# DIESEM Modul-Namespace. Patches muessen daher auf genau dieser Instanz greifen,
# nicht auf dem Package-Namespace (der die Konstanten gar nicht hat).
from app.services import ocr as _ocr_pkg

ocr = _ocr_pkg._ocr_module


@pytest.mark.asyncio
async def test_oversized_file_is_skipped(tmp_path):
    """Datei > OCR_MAX_FILE_BYTES wird gar nicht erst verarbeitet (-> '')."""
    f = tmp_path / "big.pdf"
    f.write_bytes(b"%PDF-1.7" + b"x" * 500)
    with patch.object(ocr, "OCR_MAX_FILE_BYTES", 100):
        result = await ocr.quick_ocr_preview(f)
    assert result == ""


@pytest.mark.asyncio
async def test_decompression_bomb_image_skipped_before_ocr(tmp_path):
    """Riesenbild (Pixel > Cap) wird abgefangen, BEVOR Tesseract laeuft."""
    if not ocr.PILLOW_AVAILABLE:
        pytest.skip("Pillow nicht verfuegbar")
    f = tmp_path / "bomb.png"
    f.write_bytes(b"\x89PNG" + b"x" * 50)
    fake_img = MagicMock()
    fake_img.size = (12000, 12000)  # 144 Mpx > 40 Mpx-Cap
    with patch.object(ocr.Image, "open", return_value=fake_img), \
         patch("pytesseract.image_to_string") as mock_ocr:
        result = await ocr.quick_ocr_preview(f)
    assert result == ""
    mock_ocr.assert_not_called()  # OCR darf gar nicht erreicht werden


@pytest.mark.asyncio
async def test_image_ocr_passes_tesseract_timeout(tmp_path):
    """Normales Bild -> OCR laeuft und Tesseract wird MIT timeout= aufgerufen."""
    if not ocr.PILLOW_AVAILABLE:
        pytest.skip("Pillow nicht verfuegbar")
    f = tmp_path / "ok.png"
    f.write_bytes(b"\x89PNG" + b"x" * 50)
    fake_img = MagicMock()
    fake_img.size = (800, 600)  # klein, unter Cap
    with patch.object(ocr.Image, "open", return_value=fake_img), \
         patch("pytesseract.image_to_string", return_value="Hallo Welt") as mock_ocr:
        result = await ocr.quick_ocr_preview(f)
    assert "Hallo Welt" in result
    assert mock_ocr.call_args is not None
    _, kwargs = mock_ocr.call_args
    assert kwargs.get("timeout") == ocr.OCR_PREVIEW_TIMEOUT_SECONDS


@pytest.mark.asyncio
async def test_tesseract_timeout_returns_empty_not_hang(tmp_path):
    """Tesseract-Timeout (RuntimeError) wird graceful gefangen -> '' (kein Crash)."""
    if not ocr.PILLOW_AVAILABLE:
        pytest.skip("Pillow nicht verfuegbar")
    f = tmp_path / "slow.png"
    f.write_bytes(b"\x89PNG" + b"x" * 50)
    fake_img = MagicMock()
    fake_img.size = (800, 600)
    with patch.object(ocr.Image, "open", return_value=fake_img), \
         patch("pytesseract.image_to_string", side_effect=RuntimeError("Tesseract process timeout")):
        result = await ocr.quick_ocr_preview(f)
    assert result == ""
