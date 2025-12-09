from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field

class TuneBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    icon: Optional[str] = Field("FileText", max_length=50)
    color: Optional[str] = Field("bg-slate-500", max_length=50)
    prompt_template: Optional[str] = None
    default_backend: Optional[str] = None
    is_active: bool = True

class TuneCreate(TuneBase):
    pass

class TuneUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    icon: Optional[str] = Field(None, max_length=50)
    color: Optional[str] = Field(None, max_length=50)
    prompt_template: Optional[str] = None
    default_backend: Optional[str] = None
    is_active: Optional[bool] = None

class TuneResponse(TuneBase):
    id: UUID
    is_system: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
