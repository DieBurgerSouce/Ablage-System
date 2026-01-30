"""Visual Version Diff API Router.

Endpoints fuer Seite-an-Seite Dokumentenvergleich.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_async_session
from app.services.diff.visual_diff_service import VisualDiffService

router = APIRouter(prefix="/visual-diff", tags=["visual-diff"])


class DiffRequest(BaseModel):
    """Schema fuer Vergleichsanfrage."""
    text_a: str = Field(..., min_length=1, max_length=500000)
    text_b: str = Field(..., min_length=1, max_length=500000)
    document_a_id: Optional[str] = None
    document_b_id: Optional[str] = None
    context_lines: int = Field(default=3, ge=0, le=10)


class DiffBlockResponse(BaseModel):
    """Schema fuer einen Diff-Block."""
    diff_type: str
    old_text: str = ""
    new_text: str = ""
    old_line_start: int = 0
    old_line_end: int = 0
    new_line_start: int = 0
    new_line_end: int = 0
    page_number: int = 1


class DiffResponse(BaseModel):
    """Schema fuer Vergleichsergebnis."""
    document_a_id: str
    document_b_id: str
    total_changes: int
    additions: int
    deletions: int
    modifications: int
    similarity_ratio: float
    blocks: list[DiffBlockResponse]
    summary: str


class ChangeSummaryResponse(BaseModel):
    """Schema fuer Aenderungszusammenfassung."""
    total_changes: int
    additions: int
    deletions: int
    modifications: int
    similarity_percentage: float
    key_changes: list[str]
    risk_level: str


@router.post("/compare", response_model=DiffResponse)
async def compare_texts(
    data: DiffRequest,
    current_user: dict = Depends(get_current_user),
) -> DiffResponse:
    """Vergleicht zwei Texte und gibt Diff zurueck."""
    service = VisualDiffService()
    result = service.compare_texts(
        text_a=data.text_a,
        text_b=data.text_b,
        document_a_id=data.document_a_id or "",
        document_b_id=data.document_b_id or "",
        context_lines=data.context_lines,
    )
    return DiffResponse(
        document_a_id=result.document_a_id,
        document_b_id=result.document_b_id,
        total_changes=result.total_changes,
        additions=result.additions,
        deletions=result.deletions,
        modifications=result.modifications,
        similarity_ratio=result.similarity_ratio,
        blocks=[
            DiffBlockResponse(
                diff_type=b.diff_type.value,
                old_text=b.old_text,
                new_text=b.new_text,
                old_line_start=b.old_line_start,
                old_line_end=b.old_line_end,
                new_line_start=b.new_line_start,
                new_line_end=b.new_line_end,
                page_number=b.page_number,
            )
            for b in result.blocks
        ],
        summary=result.summary,
    )


@router.post("/compare/summary", response_model=ChangeSummaryResponse)
async def compare_texts_summary(
    data: DiffRequest,
    current_user: dict = Depends(get_current_user),
) -> ChangeSummaryResponse:
    """Vergleicht zwei Texte und gibt nur die Zusammenfassung zurueck."""
    service = VisualDiffService()
    result = service.compare_texts(
        text_a=data.text_a,
        text_b=data.text_b,
        document_a_id=data.document_a_id or "",
        document_b_id=data.document_b_id or "",
    )
    summary = service.generate_change_summary(result)
    return ChangeSummaryResponse(
        total_changes=summary.total_changes,
        additions=summary.additions,
        deletions=summary.deletions,
        modifications=summary.modifications,
        similarity_percentage=summary.similarity_percentage,
        key_changes=summary.key_changes,
        risk_level=summary.risk_level,
    )


@router.post("/hash")
async def compute_hash(
    text: str = Body(..., min_length=1, embed=True),
    current_user: dict = Depends(get_current_user),
) -> dict[str, str]:
    """Berechnet SHA-256 Hash eines Textes."""
    service = VisualDiffService()
    return {"hash": service.compute_text_hash(text)}
