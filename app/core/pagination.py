"""Standardisierte Pagination fuer alle API-Endpoints.

Einheitliches page/per_page Pattern (1-indexed) fuer konsistente API-Schnittstellen.
"""

import math
from dataclasses import dataclass
from typing import Generic, List, Optional, Sequence, TypeVar

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


@dataclass
class PaginationParams:
    """Standard-Pagination-Parameter (1-indexed page)."""
    page: int = 1
    per_page: int = 20

    @property
    def offset(self) -> int:
        """Berechnet den Offset fuer SQL-Queries."""
        return (self.page - 1) * self.per_page

    @property
    def limit(self) -> int:
        """Alias fuer per_page."""
        return self.per_page


def get_pagination(
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(20, ge=1, le=100, description="Eintraege pro Seite"),
) -> PaginationParams:
    """FastAPI Dependency fuer Pagination-Parameter."""
    return PaginationParams(page=page, per_page=per_page)


class PaginatedResponse(BaseModel, Generic[T]):
    """Generische paginierte Antwort."""
    items: List[T]
    total: int
    page: int
    per_page: int
    total_pages: int

    @classmethod
    def create(
        cls,
        items: Sequence[T],
        total: int,
        params: PaginationParams,
    ) -> "PaginatedResponse[T]":
        """Erstellt eine paginierte Antwort aus Items und Total-Count."""
        return cls(
            items=list(items),
            total=total,
            page=params.page,
            per_page=params.per_page,
            total_pages=max(1, math.ceil(total / params.per_page)),
        )


async def paginate_query(
    db: AsyncSession,
    query: Select,
    params: PaginationParams,
    count_query: Optional[Select] = None,
) -> tuple:
    """Wendet Pagination auf eine SQLAlchemy-Query an.

    Returns:
        Tuple von (items, total_count)
    """
    # Count total
    if count_query is not None:
        count_result = await db.execute(count_query)
    else:
        # Auto-generate count query from the main query
        count_stmt = select(func.count()).select_from(query.subquery())
        count_result = await db.execute(count_stmt)
    total = count_result.scalar() or 0

    # Apply pagination
    paginated = query.offset(params.offset).limit(params.limit)
    result = await db.execute(paginated)
    items = result.scalars().all()

    return items, total
