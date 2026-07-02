# -*- coding: utf-8 -*-
"""
Image Diff Service - Pixelweiser Bildvergleich fuer gescannte Dokumente.

Vergleicht zwei Dokument-Bilder pixelweise und erzeugt:
- Diff-Bild: Geaenderte Pixel rot markiert
- Overlay-Bild: Ueberblendung beider Dokumente
- Aehnlichkeits-Score und Aenderungsprozentsatz

Feinpoliert und durchdacht - Visueller Dokumentenvergleich.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Tuple

import structlog
from PIL import Image, ImageChops

logger = structlog.get_logger(__name__)


@dataclass
class ImageDiffResult:
    """Ergebnis eines pixelweisen Bildvergleichs."""

    similarity_score: float
    changed_percentage: float
    diff_image_bytes: bytes
    overlay_image_bytes: bytes
    dimensions: Tuple[int, int]


class ImageDiffService:
    """Service fuer pixelweisen Bildvergleich von Dokumenten."""

    def compare_images(
        self,
        img_a_bytes: bytes,
        img_b_bytes: bytes,
        threshold: int = 30,
    ) -> ImageDiffResult:
        """Vergleicht zwei Bilder pixelweise.

        Args:
            img_a_bytes: Bilddaten des ersten Dokuments
            img_b_bytes: Bilddaten des zweiten Dokuments
            threshold: Schwellwert fuer Pixel-Differenz (0-255).
                       Pixel mit Differenz < threshold werden ignoriert.

        Returns:
            ImageDiffResult mit Diff-Bild, Overlay und Statistiken
        """
        img_a = Image.open(io.BytesIO(img_a_bytes)).convert("RGB")
        img_b = Image.open(io.BytesIO(img_b_bytes)).convert("RGB")

        # Auf gleiche Groesse skalieren (Maximum beider Dimensionen)
        max_w = max(img_a.width, img_b.width)
        max_h = max(img_a.height, img_b.height)
        if img_a.size != (max_w, max_h):
            img_a = img_a.resize((max_w, max_h), Image.LANCZOS)
        if img_b.size != (max_w, max_h):
            img_b = img_b.resize((max_w, max_h), Image.LANCZOS)

        # Pixel-Differenz berechnen
        diff = ImageChops.difference(img_a, img_b)

        # Optimierter Vergleich mit numpy (falls verfuegbar)
        total_pixels = max_w * max_h
        try:
            import numpy as np

            diff_arr = np.array(diff, dtype=np.float32)
            img_a_arr = np.array(img_a, dtype=np.uint8)

            # Durchschnittliche Differenz pro Pixel
            pixel_diff_avg = diff_arr.mean(axis=2)

            # Maske: Pixel ueber Schwellwert
            changed_mask = pixel_diff_avg >= threshold
            changed_pixels = int(changed_mask.sum())

            # Diff-Bild erstellen
            # Basis: Graue gedaempfte Version von Bild A
            gray_base = (img_a_arr.mean(axis=2, keepdims=True) * 0.5).astype(
                np.uint8
            )
            gray_base = np.repeat(gray_base, 3, axis=2)

            # Geaenderte Pixel rot markieren
            diff_arr_out = gray_base.copy()
            diff_arr_out[changed_mask] = [255, 0, 0]

            diff_highlight = Image.fromarray(diff_arr_out)
        except ImportError:
            # Fallback ohne numpy - pixel-weise
            diff_highlight = Image.new("RGB", (max_w, max_h), (255, 255, 255))
            diff_data_px = diff.load()
            img_a_data_px = img_a.load()
            changed_pixels = 0
            for y in range(max_h):
                for x in range(max_w):
                    r, g, b = diff_data_px[x, y]
                    px_diff = (r + g + b) / 3
                    if px_diff >= threshold:
                        changed_pixels += 1
                        diff_highlight.putpixel((x, y), (255, 0, 0))
                    else:
                        orig_r, orig_g, orig_b = img_a_data_px[x, y]
                        gray = int((orig_r + orig_g + orig_b) / 3 * 0.5)
                        diff_highlight.putpixel((x, y), (gray, gray, gray))

        # Overlay-Bild: Ueberblendung beider Dokumente
        overlay = Image.blend(img_a, img_b, alpha=0.5)

        # Statistiken
        changed_percentage = (
            (changed_pixels / total_pixels * 100) if total_pixels > 0 else 0.0
        )
        similarity_score = (
            1.0 - (changed_pixels / total_pixels) if total_pixels > 0 else 1.0
        )

        # Bilder zu Bytes konvertieren
        diff_buf = io.BytesIO()
        diff_highlight.save(diff_buf, format="PNG")
        diff_bytes = diff_buf.getvalue()

        overlay_buf = io.BytesIO()
        overlay.save(overlay_buf, format="PNG")
        overlay_bytes = overlay_buf.getvalue()

        logger.info(
            "image_diff_completed",
            dimensions=f"{max_w}x{max_h}",
            changed_percentage=f"{changed_percentage:.2f}%",
            similarity_score=f"{similarity_score:.4f}",
        )

        return ImageDiffResult(
            similarity_score=round(similarity_score, 4),
            changed_percentage=round(changed_percentage, 2),
            diff_image_bytes=diff_bytes,
            overlay_image_bytes=overlay_bytes,
            dimensions=(max_w, max_h),
        )

    def compare_document_pages(
        self,
        doc_a_bytes: bytes,
        doc_b_bytes: bytes,
        page: int = 1,
        threshold: int = 30,
    ) -> ImageDiffResult:
        """Vergleicht eine bestimmte Seite zweier Dokumente.

        Rendert PDF-Seiten zu Bildern via PyMuPDF (fitz).
        Fuer Bilder (JPEG/PNG/TIFF) wird das Bild direkt geladen.

        Args:
            doc_a_bytes: Dateiinhalt Dokument A
            doc_b_bytes: Dateiinhalt Dokument B
            page: Seitennummer (1-basiert)
            threshold: Pixel-Differenz-Schwellwert

        Returns:
            ImageDiffResult
        """
        img_a_bytes = self._render_page(doc_a_bytes, page)
        img_b_bytes = self._render_page(doc_b_bytes, page)
        return self.compare_images(img_a_bytes, img_b_bytes, threshold)

    def _render_page(self, file_bytes: bytes, page: int = 1) -> bytes:
        """Rendert eine Dokumentseite als PNG.

        Versucht zuerst als PDF zu oeffnen, dann als Bild.
        """
        # Versuche als PDF
        try:
            import fitz

            pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
            page_idx = page - 1
            if page_idx < 0 or page_idx >= len(pdf_doc):
                page_idx = 0
            pix = pdf_doc[page_idx].get_pixmap(dpi=150)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            pdf_doc.close()
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception as e:
            logger.debug(
                "image_diff_pdf_open_fallback",
                error_type=type(e).__name__,
            )

        # Fallback: als Bild oeffnen
        try:
            img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception as e:
            raise ValueError(
                f"Dokument konnte nicht als Bild gerendert werden: {e}"
            )
