"""OCR Version Management Service.

Handles versioning, comparison, and rollback of OCR results.
Provides full audit trail for document OCR history.

Features:
- Version creation from OCR results
- Version listing and retrieval
- Side-by-side and unified diff comparison
- Rollback to previous versions (creates new version)
"""

import structlog
from datetime import datetime
from difflib import unified_diff, HtmlDiff
from functools import lru_cache
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from sqlalchemy.orm import selectinload

from app.db.models import Document, OCRResult, OCRResultVersion, User
from app.db.schemas import (
    OCRVersionResponse,
    OCRVersionSummary,
    OCRVersionListResponse,
    OCRVersionCompareResponse,
    OCRVersionRollbackResponse,
    OCRVersionDiff,
)

logger = structlog.get_logger(__name__)


class VersionService:
    """Service for managing OCR result versions."""

    # Max extracted text size (10MB) - prevents database bloat from oversized OCR results
    MAX_EXTRACTED_TEXT_SIZE = 10 * 1024 * 1024  # 10MB

    def __init__(self) -> None:
        """Initialize version service."""
        self._html_differ = HtmlDiff(wrapcolumn=80)

    def _validate_text_size(self, text: Optional[str]) -> str:
        """Validate and truncate extracted text if too large."""
        if text is None:
            return ""
        if len(text) > self.MAX_EXTRACTED_TEXT_SIZE:
            logger.warning(
                "extracted_text_truncated",
                original_size=len(text),
                max_size=self.MAX_EXTRACTED_TEXT_SIZE
            )
            return text[:self.MAX_EXTRACTED_TEXT_SIZE] + "\n\n[TEXT TRUNCATED - exceeded 10MB limit]"
        return text

    async def create_version_from_dict(
        self,
        db: AsyncSession,
        document_id: UUID,
        ocr_data: Dict[str, Any],
        user_id: Optional[UUID] = None,
        version_note: Optional[str] = None
    ) -> OCRResultVersion:
        """Create a new version from OCR result dictionary.

        This method is useful for creating versions from OCR processing
        results without needing a persisted OCRResult model.

        Args:
            db: Database session
            document_id: Document ID
            ocr_data: Dictionary with OCR result data including:
                - backend: OCR backend used
                - text or extracted_text: Extracted text
                - confidence_score: OCR confidence
                - metadata: Additional metadata dict
            user_id: User creating the version
            version_note: Optional note for this version

        Returns:
            Created version record
        """
        # Get next version number
        next_version = await self._get_next_version_number(db, document_id)

        # Mark all existing versions as not current
        await db.execute(
            update(OCRResultVersion)
            .where(OCRResultVersion.document_id == document_id)
            .values(is_current=False)
        )

        # Extract data from dictionary
        backend = ocr_data.get("backend") or ocr_data.get("metadata", {}).get("backend_used", "unknown")
        raw_text = ocr_data.get("text") or ocr_data.get("extracted_text", "")
        text = self._validate_text_size(raw_text)
        confidence = ocr_data.get("confidence_score") or ocr_data.get("confidence", 0.0)
        metadata = ocr_data.get("metadata", {})

        # Calculate word and char counts if not provided
        word_count = ocr_data.get("word_count") or (len(text.split()) if text else 0)
        char_count = ocr_data.get("char_count") or len(text) if text else 0

        # Processing time
        processing_time_ms = None
        if "processing_time_seconds" in metadata:
            processing_time_ms = int(metadata["processing_time_seconds"] * 1000)
        elif "processing_time_ms" in ocr_data:
            processing_time_ms = ocr_data["processing_time_ms"]

        # Create new version
        version = OCRResultVersion(
            document_id=document_id,
            ocr_result_id=None,  # No linked OCRResult
            version_number=next_version,
            is_current=True,
            is_rollback=False,
            backend=backend,
            extracted_text=text,
            confidence_score=confidence,
            word_count=word_count,
            char_count=char_count,
            detected_dates=ocr_data.get("detected_dates", []),
            detected_amounts=ocr_data.get("detected_amounts", []),
            detected_ibans=ocr_data.get("ibans", []),
            detected_vat_ids=ocr_data.get("vat_ids", []),
            business_terms=ocr_data.get("business_terms", []),
            detected_layout=ocr_data.get("layout", {}),
            bounding_boxes=ocr_data.get("bounding_boxes", []),
            processing_time_ms=processing_time_ms,
            has_umlauts=ocr_data.get("has_umlauts"),
            german_validation_score=ocr_data.get("german_validation", {}).get("quality_score"),
            created_by_id=user_id,
            version_note=version_note or f"OCR mit {backend}",
        )

        db.add(version)

        # Update document version counters
        await db.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(
                current_version_number=next_version,
                total_versions=next_version
            )
        )

        await db.commit()
        await db.refresh(version)

        logger.info(
            "ocr_version_created_from_dict",
            document_id=str(document_id),
            version_number=next_version,
            backend=backend,
            user_id=str(user_id) if user_id else None
        )

        return version

    async def create_version_from_ocr_result(
        self,
        db: AsyncSession,
        document_id: UUID,
        ocr_result: OCRResult,
        user_id: Optional[UUID] = None,
        version_note: Optional[str] = None
    ) -> OCRResultVersion:
        """Create a new version from an OCR result.

        Args:
            db: Database session
            document_id: Document ID
            ocr_result: OCR result to version
            user_id: User creating the version
            version_note: Optional note for this version

        Returns:
            Created version record
        """
        # Get next version number
        next_version = await self._get_next_version_number(db, document_id)

        # Mark all existing versions as not current
        await db.execute(
            update(OCRResultVersion)
            .where(OCRResultVersion.document_id == document_id)
            .values(is_current=False)
        )

        # Create new version from OCR result
        validated_text = self._validate_text_size(ocr_result.extracted_text)
        version = OCRResultVersion(
            document_id=document_id,
            ocr_result_id=ocr_result.id,
            version_number=next_version,
            is_current=True,
            is_rollback=False,
            backend=ocr_result.backend,
            extracted_text=validated_text,
            confidence_score=ocr_result.confidence_score,
            word_count=ocr_result.word_count,
            char_count=ocr_result.char_count,
            detected_dates=ocr_result.detected_dates or [],
            detected_amounts=ocr_result.detected_amounts or [],
            detected_ibans=ocr_result.detected_ibans or [],
            detected_vat_ids=ocr_result.detected_vat_ids or [],
            business_terms=ocr_result.business_terms or [],
            detected_layout=ocr_result.detected_layout or {},
            bounding_boxes=ocr_result.bounding_boxes or [],
            processing_time_ms=ocr_result.processing_time_ms,
            created_by_id=user_id,
            version_note=version_note or f"OCR mit {ocr_result.backend}",
        )

        db.add(version)

        # Update document version counters
        await db.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(
                current_version_number=next_version,
                total_versions=next_version
            )
        )

        await db.commit()
        await db.refresh(version)

        logger.info(
            "ocr_version_created",
            document_id=str(document_id),
            version_number=next_version,
            backend=ocr_result.backend,
            user_id=str(user_id) if user_id else None
        )

        return version

    async def get_version(
        self,
        db: AsyncSession,
        document_id: UUID,
        version_number: int
    ) -> Optional[OCRResultVersion]:
        """Get a specific version by number.

        Args:
            db: Database session
            document_id: Document ID
            version_number: Version number to retrieve

        Returns:
            Version record if found, None otherwise
        """
        result = await db.execute(
            select(OCRResultVersion)
            .where(
                OCRResultVersion.document_id == document_id,
                OCRResultVersion.version_number == version_number
            )
        )
        return result.scalar_one_or_none()

    async def get_current_version(
        self,
        db: AsyncSession,
        document_id: UUID
    ) -> Optional[OCRResultVersion]:
        """Get the current (active) version for a document.

        Args:
            db: Database session
            document_id: Document ID

        Returns:
            Current version record if found, None otherwise
        """
        result = await db.execute(
            select(OCRResultVersion)
            .where(
                OCRResultVersion.document_id == document_id,
                OCRResultVersion.is_current == True
            )
        )
        return result.scalar_one_or_none()

    async def list_versions(
        self,
        db: AsyncSession,
        document_id: UUID,
        limit: int = 50,
        offset: int = 0
    ) -> OCRVersionListResponse:
        """List all versions for a document.

        Args:
            db: Database session
            document_id: Document ID
            limit: Maximum results to return
            offset: Results offset for pagination

        Returns:
            List response with version summaries
        """
        # Get document info
        doc_result = await db.execute(
            select(Document).where(Document.id == document_id)
        )
        document = doc_result.scalar_one_or_none()

        if not document:
            raise ValueError("Dokument nicht gefunden")

        # Get versions
        versions_result = await db.execute(
            select(OCRResultVersion)
            .where(OCRResultVersion.document_id == document_id)
            .order_by(OCRResultVersion.version_number.desc())
            .limit(limit)
            .offset(offset)
        )
        versions = versions_result.scalars().all()

        # Get total count
        count_result = await db.execute(
            select(func.count(OCRResultVersion.id))
            .where(OCRResultVersion.document_id == document_id)
        )
        total = count_result.scalar() or 0

        return OCRVersionListResponse(
            document_id=document_id,
            document_filename=document.original_filename or document.filename,
            current_version=document.current_version_number or 0,
            total_versions=total,
            versions=[
                OCRVersionSummary.model_validate(v) for v in versions
            ]
        )

    async def compare_versions(
        self,
        db: AsyncSession,
        document_id: UUID,
        version_a: int,
        version_b: int
    ) -> OCRVersionCompareResponse:
        """Compare two versions of a document.

        Generates both side-by-side HTML diff and unified diff.

        Args:
            db: Database session
            document_id: Document ID
            version_a: First version number
            version_b: Second version number

        Returns:
            Comparison response with diffs
        """
        ver_a = await self.get_version(db, document_id, version_a)
        ver_b = await self.get_version(db, document_id, version_b)

        if not ver_a:
            raise ValueError(f"Version {version_a} nicht gefunden")
        if not ver_b:
            raise ValueError(f"Version {version_b} nicht gefunden")

        # Generate text diffs
        text_diff_html = None
        text_diff_unified = None

        if ver_a.extracted_text and ver_b.extracted_text:
            lines_a = ver_a.extracted_text.splitlines(keepends=True)
            lines_b = ver_b.extracted_text.splitlines(keepends=True)

            # HTML diff for side-by-side view
            try:
                text_diff_html = self._html_differ.make_table(
                    lines_a,
                    lines_b,
                    fromdesc=f"Version {version_a}",
                    todesc=f"Version {version_b}",
                    context=True,
                    numlines=3
                )
            except Exception as e:
                logger.warning("html_diff_failed", error=str(e))

            # Unified diff like git
            unified = list(unified_diff(
                lines_a,
                lines_b,
                fromfile=f"Version {version_a}",
                tofile=f"Version {version_b}",
                lineterm=""
            ))
            text_diff_unified = "\n".join(unified) if unified else None

        # Calculate differences
        confidence_a = ver_a.confidence_score or 0
        confidence_b = ver_b.confidence_score or 0
        confidence_delta = confidence_b - confidence_a

        word_count_a = ver_a.word_count or 0
        word_count_b = ver_b.word_count or 0
        word_count_delta = word_count_b - word_count_a

        differences = OCRVersionDiff(
            backend_changed=ver_a.backend != ver_b.backend,
            text_length_delta=(ver_b.char_count or 0) - (ver_a.char_count or 0),
            dates_count_delta=len(ver_b.detected_dates or []) - len(ver_a.detected_dates or []),
            amounts_count_delta=len(ver_b.detected_amounts or []) - len(ver_a.detected_amounts or []),
            ibans_count_delta=len(ver_b.detected_ibans or []) - len(ver_a.detected_ibans or []),
            vat_ids_count_delta=len(ver_b.detected_vat_ids or []) - len(ver_a.detected_vat_ids or []),
            confidence_improved=confidence_delta > 0 if confidence_delta != 0 else None
        )

        logger.info(
            "versions_compared",
            document_id=str(document_id),
            version_a=version_a,
            version_b=version_b,
            backend_changed=differences.backend_changed
        )

        return OCRVersionCompareResponse(
            document_id=document_id,
            version_a=OCRVersionResponse.model_validate(ver_a),
            version_b=OCRVersionResponse.model_validate(ver_b),
            differences=differences,
            text_diff_html=text_diff_html,
            text_diff_unified=text_diff_unified,
            confidence_delta=confidence_delta if confidence_delta != 0 else None,
            word_count_delta=word_count_delta if word_count_delta != 0 else None
        )

    async def rollback_to_version(
        self,
        db: AsyncSession,
        document_id: UUID,
        target_version: int,
        user_id: Optional[UUID] = None,
        rollback_note: Optional[str] = None
    ) -> OCRVersionRollbackResponse:
        """Rollback to a previous version.

        Creates a new version with the content of the target version.
        Does not delete any existing versions (preserves full history).

        Args:
            db: Database session
            document_id: Document ID
            target_version: Version number to rollback to
            user_id: User performing the rollback
            rollback_note: Optional note for the rollback

        Returns:
            Rollback response with new version number
        """
        # Get target version
        target = await self.get_version(db, document_id, target_version)
        if not target:
            raise ValueError(f"Version {target_version} nicht gefunden")

        # Get current version for logging
        current = await self.get_current_version(db, document_id)
        current_number = current.version_number if current else 0

        # Get next version number
        next_version = await self._get_next_version_number(db, document_id)

        # Mark all versions as not current
        await db.execute(
            update(OCRResultVersion)
            .where(OCRResultVersion.document_id == document_id)
            .values(is_current=False)
        )

        # Create note for rollback
        note = rollback_note or f"Rollback von Version {current_number} zu Version {target_version}"

        # Create new version as rollback (copies target version data)
        rollback_version = OCRResultVersion(
            document_id=document_id,
            ocr_result_id=target.ocr_result_id,
            version_number=next_version,
            is_current=True,
            is_rollback=True,
            rollback_from_version=target_version,
            backend=target.backend,
            extracted_text=target.extracted_text,
            confidence_score=target.confidence_score,
            word_count=target.word_count,
            char_count=target.char_count,
            detected_dates=target.detected_dates or [],
            detected_amounts=target.detected_amounts or [],
            detected_ibans=target.detected_ibans or [],
            detected_vat_ids=target.detected_vat_ids or [],
            business_terms=target.business_terms or [],
            detected_layout=target.detected_layout or {},
            bounding_boxes=target.bounding_boxes or [],
            processing_time_ms=target.processing_time_ms,
            german_validation_score=target.german_validation_score,
            has_umlauts=target.has_umlauts,
            created_by_id=user_id,
            version_note=note,
        )

        db.add(rollback_version)

        # Update document with rolled-back content and version counters
        await db.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(
                current_version_number=next_version,
                total_versions=next_version,
                extracted_text=target.extracted_text,
                ocr_confidence=target.confidence_score,
                ocr_backend_used=target.backend,
            )
        )

        await db.commit()

        logger.info(
            "version_rollback",
            document_id=str(document_id),
            from_version=current_number,
            to_version=target_version,
            new_version=next_version,
            user_id=str(user_id) if user_id else None
        )

        return OCRVersionRollbackResponse(
            success=True,
            new_version_number=next_version,
            rolled_back_from=target_version,
            message=f"Erfolgreich zu Version {target_version} zuruckgesetzt. Neue Version: {next_version}"
        )

    async def _get_next_version_number(
        self,
        db: AsyncSession,
        document_id: UUID
    ) -> int:
        """Get the next version number for a document.

        Args:
            db: Database session
            document_id: Document ID

        Returns:
            Next version number (max + 1, or 1 if no versions exist)
        """
        result = await db.execute(
            select(func.max(OCRResultVersion.version_number))
            .where(OCRResultVersion.document_id == document_id)
        )
        max_version = result.scalar() or 0
        return max_version + 1


# Thread-safe singleton via lru_cache
@lru_cache(maxsize=1)
def get_version_service() -> VersionService:
    """Get singleton version service instance (thread-safe).

    Returns:
        VersionService instance
    """
    return VersionService()
