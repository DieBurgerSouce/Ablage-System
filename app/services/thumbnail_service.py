"""Thumbnail Generation Service.

Generiert Vorschaubilder fuer Dokumente:
- PDF: Erste Seite als Bild (via pdf2image/poppler)
- Bilder: Verkleinerte Version

Feinpoliert und durchdacht - Enterprise Thumbnail Generation.
"""

import asyncio
import io
from pathlib import Path
from typing import Optional, Tuple

import structlog
from PIL import Image

logger = structlog.get_logger(__name__)

# Thumbnail settings
THUMBNAIL_SIZE = (200, 200)
PREVIEW_SIZE = (800, 800)
THUMBNAIL_FORMAT = "webp"
THUMBNAIL_QUALITY = 85


def _resize_image(
    image: Image.Image,
    max_size: Tuple[int, int],
    preserve_aspect: bool = True,
) -> Image.Image:
    """Resize image while preserving aspect ratio.

    Args:
        image: PIL Image
        max_size: Maximum (width, height)
        preserve_aspect: Keep aspect ratio

    Returns:
        Resized image
    """
    if preserve_aspect:
        image.thumbnail(max_size, Image.Resampling.LANCZOS)
        return image
    else:
        return image.resize(max_size, Image.Resampling.LANCZOS)


def _convert_to_rgb(img: Image.Image) -> Image.Image:
    """Convert image to RGB mode, handling transparency."""
    if img.mode in ("RGBA", "LA", "P"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        if img.mode in ("RGBA", "LA"):
            background.paste(img, mask=img.split()[-1])
        else:
            background.paste(img)
        return background
    elif img.mode != "RGB":
        return img.convert("RGB")
    return img


class ThumbnailService:
    """Service for generating document thumbnails and previews."""

    def __init__(
        self,
        thumbnail_size: Tuple[int, int] = THUMBNAIL_SIZE,
        preview_size: Tuple[int, int] = PREVIEW_SIZE,
        output_format: str = THUMBNAIL_FORMAT,
        quality: int = THUMBNAIL_QUALITY,
    ):
        self.thumbnail_size = thumbnail_size
        self.preview_size = preview_size
        self.output_format = output_format
        self.quality = quality
        self._pdf2image_available: Optional[bool] = None

    def _check_pdf2image(self) -> bool:
        """Check if pdf2image is available."""
        if self._pdf2image_available is None:
            try:
                from pdf2image import convert_from_path
                self._pdf2image_available = True
            except ImportError:
                logger.warning("pdf2image_not_installed")
                self._pdf2image_available = False
        return self._pdf2image_available

    async def generate_thumbnail(
        self,
        file_path: str,
        document_id: str,
    ) -> Optional[bytes]:
        """Generate thumbnail for a document.

        Args:
            file_path: Path to the document file
            document_id: Document UUID for logging

        Returns:
            Thumbnail bytes or None if generation failed
        """
        path = Path(file_path)
        if not path.exists():
            logger.warning(
                "thumbnail_file_not_found",
                document_id=document_id,
                file_path=file_path,
            )
            return None

        extension = path.suffix.lower()

        try:
            if extension == ".pdf":
                return await self._thumbnail_from_pdf(file_path, document_id)
            elif extension in [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"]:
                return await self._thumbnail_from_image(file_path, document_id)
            else:
                logger.info(
                    "unsupported_file_type_for_thumbnail",
                    document_id=document_id,
                    extension=extension,
                )
                return None

        except Exception as e:
            logger.exception(
                "thumbnail_generation_failed",
                document_id=document_id,
                error=str(e),
            )
            return None

    async def generate_preview(
        self,
        file_path: str,
        document_id: str,
    ) -> Optional[bytes]:
        """Generate larger preview image for a document.

        Args:
            file_path: Path to the document file
            document_id: Document UUID

        Returns:
            Preview bytes or None if generation failed
        """
        path = Path(file_path)
        if not path.exists():
            return None

        extension = path.suffix.lower()

        try:
            if extension == ".pdf":
                return await self._preview_from_pdf(file_path, document_id)
            elif extension in [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"]:
                return await self._preview_from_image(file_path, document_id)
            else:
                return None

        except Exception as e:
            logger.exception(
                "preview_generation_failed",
                document_id=document_id,
                error=str(e),
            )
            return None

    async def _thumbnail_from_pdf(
        self,
        file_path: str,
        document_id: str,
    ) -> Optional[bytes]:
        """Generate thumbnail from PDF first page using pdf2image."""
        if not self._check_pdf2image():
            logger.warning(
                "pdf_thumbnail_skipped_no_pdf2image",
                document_id=document_id,
            )
            return None

        def _process():
            from pdf2image import convert_from_path

            # Convert first page at low DPI for thumbnail
            images = convert_from_path(
                file_path,
                first_page=1,
                last_page=1,
                dpi=72,
                fmt="png",
            )

            if not images:
                return None

            img = images[0]
            img = _convert_to_rgb(img)
            resized = _resize_image(img, self.thumbnail_size)

            buffer = io.BytesIO()
            resized.save(
                buffer,
                format=self.output_format.upper(),
                quality=self.quality,
            )
            return buffer.getvalue()

        try:
            return await asyncio.to_thread(_process)
        except Exception as e:
            logger.warning(
                "pdf_thumbnail_failed",
                document_id=document_id,
                error=str(e),
            )
            return None

    async def _preview_from_pdf(
        self,
        file_path: str,
        document_id: str,
    ) -> Optional[bytes]:
        """Generate preview from PDF first page using pdf2image."""
        if not self._check_pdf2image():
            return None

        def _process():
            from pdf2image import convert_from_path

            # Convert first page at higher DPI for preview
            images = convert_from_path(
                file_path,
                first_page=1,
                last_page=1,
                dpi=150,
                fmt="png",
            )

            if not images:
                return None

            img = images[0]
            img = _convert_to_rgb(img)
            resized = _resize_image(img, self.preview_size)

            buffer = io.BytesIO()
            resized.save(
                buffer,
                format=self.output_format.upper(),
                quality=self.quality,
            )
            return buffer.getvalue()

        try:
            return await asyncio.to_thread(_process)
        except Exception as e:
            logger.warning(
                "pdf_preview_failed",
                document_id=document_id,
                error=str(e),
            )
            return None

    async def _thumbnail_from_image(
        self,
        file_path: str,
        document_id: str,
    ) -> Optional[bytes]:
        """Generate thumbnail from image file."""
        def _process():
            with Image.open(file_path) as img:
                img = _convert_to_rgb(img)
                resized = _resize_image(img.copy(), self.thumbnail_size)

                buffer = io.BytesIO()
                resized.save(
                    buffer,
                    format=self.output_format.upper(),
                    quality=self.quality,
                )
                return buffer.getvalue()

        return await asyncio.to_thread(_process)

    async def _preview_from_image(
        self,
        file_path: str,
        document_id: str,
    ) -> Optional[bytes]:
        """Generate preview from image file."""
        def _process():
            with Image.open(file_path) as img:
                img = _convert_to_rgb(img)
                resized = _resize_image(img.copy(), self.preview_size)

                buffer = io.BytesIO()
                resized.save(
                    buffer,
                    format=self.output_format.upper(),
                    quality=self.quality,
                )
                return buffer.getvalue()

        return await asyncio.to_thread(_process)


# Singleton instance
_thumbnail_service: Optional[ThumbnailService] = None


def get_thumbnail_service() -> ThumbnailService:
    """Get the singleton ThumbnailService instance."""
    global _thumbnail_service
    if _thumbnail_service is None:
        _thumbnail_service = ThumbnailService()
    return _thumbnail_service
