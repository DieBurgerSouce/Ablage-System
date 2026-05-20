"""
Tag Admin Schemas.

Pydantic schemas for Tag CRUD operations in admin interface.
"""
from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class TagBase(BaseModel):
    """Basis-Schema für Tags."""
    name: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = Field(None, max_length=255)
    icon: Optional[str] = Field("Tag", max_length=50)
    color: Optional[str] = Field("bg-slate-500", max_length=50)
    tune_id: Optional[UUID] = None
    is_active: bool = True


class TagCreate(TagBase):
    """Schema für Tag-Erstellung."""
    pass


class TagUpdate(BaseModel):
    """Schema für Tag-Aktualisierung (partial update)."""
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    description: Optional[str] = Field(None, max_length=255)
    icon: Optional[str] = Field(None, max_length=50)
    color: Optional[str] = Field(None, max_length=50)
    tune_id: Optional[UUID] = None
    is_active: Optional[bool] = None


class TagResponse(TagBase):
    """Response-Schema für Tags."""
    id: UUID
    is_system: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TagListResponse(BaseModel):
    """Response-Schema für Tag-Liste."""
    tags: list[TagResponse]
    total: int
