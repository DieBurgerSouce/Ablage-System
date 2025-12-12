"""
Company Settings Administration API Endpoints.

Provides company details management for admins:
- GET/PUT company settings (singleton)
- Used for invoice direction detection (incoming vs outgoing)

All endpoints require admin/superuser permissions.
"""

from typing import Optional, List
from datetime import datetime, timezone
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_superuser
from app.db.models import User, CompanySettings

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/company", tags=["Admin - Firmendaten"])


# ==================== Schemas ====================

class CompanySettingsResponse(BaseModel):
    """Response schema fuer Firmendaten."""
    id: str
    company_name: str
    alternative_names: List[str] = []
    street: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    country: str = "Deutschland"
    vat_id: Optional[str] = None
    tax_number: Optional[str] = None
    iban: Optional[str] = None
    bic: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    commercial_register: Optional[str] = None
    court: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    updated_by_id: Optional[str] = None

    class Config:
        from_attributes = True


class CompanySettingsUpdate(BaseModel):
    """Request schema zum Aktualisieren von Firmendaten."""
    company_name: str = Field(..., min_length=1, max_length=255, description="Offizieller Firmenname")
    alternative_names: List[str] = Field(
        default=[],
        description="Alternative Schreibweisen fuer Dokumentenerkennung"
    )
    street: Optional[str] = Field(None, max_length=255, description="Strasse mit Hausnummer")
    postal_code: Optional[str] = Field(None, max_length=20, description="PLZ")
    city: Optional[str] = Field(None, max_length=100, description="Stadt")
    country: str = Field(default="Deutschland", max_length=100, description="Land")
    vat_id: Optional[str] = Field(None, max_length=50, description="USt-IdNr. (z.B. DE123456789)")
    tax_number: Optional[str] = Field(None, max_length=50, description="Steuernummer")
    iban: Optional[str] = Field(None, max_length=34, description="IBAN")
    bic: Optional[str] = Field(None, max_length=11, description="BIC/SWIFT")
    email: Optional[str] = Field(None, max_length=255, description="Zentrale E-Mail-Adresse")
    phone: Optional[str] = Field(None, max_length=50, description="Telefonnummer")
    website: Optional[str] = Field(None, max_length=255, description="Webseite")
    commercial_register: Optional[str] = Field(None, max_length=100, description="Handelsregister-Nr.")
    court: Optional[str] = Field(None, max_length=100, description="Registergericht")

    @field_validator("vat_id")
    @classmethod
    def validate_vat_id(cls, v: Optional[str]) -> Optional[str]:
        """Validiert deutsche USt-IdNr. (DE + 9 Ziffern)."""
        if v is None or v == "":
            return None
        v = v.strip().upper().replace(" ", "")
        if v and not (v.startswith("DE") and len(v) == 11 and v[2:].isdigit()):
            raise ValueError("USt-IdNr. muss mit DE beginnen und 9 Ziffern haben (z.B. DE123456789)")
        return v

    @field_validator("iban")
    @classmethod
    def validate_iban(cls, v: Optional[str]) -> Optional[str]:
        """Validiert IBAN-Format (vereinfacht fuer DE)."""
        if v is None or v == "":
            return None
        v = v.strip().upper().replace(" ", "")
        if v and len(v) < 15:
            raise ValueError("IBAN muss mindestens 15 Zeichen haben")
        return v

    @field_validator("bic")
    @classmethod
    def validate_bic(cls, v: Optional[str]) -> Optional[str]:
        """Validiert BIC-Format (8 oder 11 Zeichen)."""
        if v is None or v == "":
            return None
        v = v.strip().upper().replace(" ", "")
        if v and len(v) not in [8, 11]:
            raise ValueError("BIC muss 8 oder 11 Zeichen haben")
        return v


class CompanySettingsEmpty(BaseModel):
    """Response wenn keine Firmendaten vorhanden sind."""
    message: str = "Keine Firmendaten konfiguriert"
    configured: bool = False


# ==================== Helper Functions ====================

async def get_company_settings_or_none(db: AsyncSession) -> Optional[CompanySettings]:
    """Ruft die Firmeneinstellungen ab (Singleton)."""
    result = await db.execute(select(CompanySettings).limit(1))
    return result.scalar_one_or_none()


# ==================== Endpoints ====================

@router.get(
    "",
    response_model=CompanySettingsResponse | CompanySettingsEmpty,
    summary="Firmendaten abrufen",
    description="Ruft die konfigurierten Firmendaten ab"
)
async def get_company_settings(
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> CompanySettingsResponse | CompanySettingsEmpty:
    """
    Ruft die Firmendaten ab.

    Die Firmendaten werden verwendet um zu bestimmen, ob eine
    hochgeladene Rechnung eine Eingangs- oder Ausgangsrechnung ist.

    Falls keine Firmendaten konfiguriert sind, wird ein Hinweis zurueckgegeben.

    Nur fuer Administratoren zugaenglich.
    """
    settings = await get_company_settings_or_none(db)

    if settings is None:
        return CompanySettingsEmpty()

    return CompanySettingsResponse(
        id=str(settings.id),
        company_name=settings.company_name,
        alternative_names=settings.alternative_names or [],
        street=settings.street,
        postal_code=settings.postal_code,
        city=settings.city,
        country=settings.country or "Deutschland",
        vat_id=settings.vat_id,
        tax_number=settings.tax_number,
        iban=settings.iban,
        bic=settings.bic,
        email=settings.email,
        phone=settings.phone,
        website=settings.website,
        commercial_register=settings.commercial_register,
        court=settings.court,
        created_at=settings.created_at,
        updated_at=settings.updated_at,
        updated_by_id=str(settings.updated_by_id) if settings.updated_by_id else None,
    )


@router.put(
    "",
    response_model=CompanySettingsResponse,
    summary="Firmendaten aktualisieren",
    description="Erstellt oder aktualisiert die Firmendaten"
)
async def update_company_settings(
    request: CompanySettingsUpdate,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> CompanySettingsResponse:
    """
    Erstellt oder aktualisiert die Firmendaten.

    Die Firmendaten werden verwendet fuer:
    - Erkennung von Eingangs- vs. Ausgangsrechnungen
    - Abgleich von Absender/Empfaenger gegen eigene Firmendaten
    - Alternative Firmennamen fuer flexible Erkennung

    Falls noch keine Firmendaten existieren, werden sie erstellt.
    Falls bereits Firmendaten existieren, werden sie aktualisiert.

    Nur fuer Administratoren zugaenglich.
    """
    settings = await get_company_settings_or_none(db)

    if settings is None:
        # Erstelle neue Firmendaten
        settings = CompanySettings(
            id=uuid.uuid4(),
            company_name=request.company_name,
            alternative_names=request.alternative_names,
            street=request.street,
            postal_code=request.postal_code,
            city=request.city,
            country=request.country,
            vat_id=request.vat_id,
            tax_number=request.tax_number,
            iban=request.iban,
            bic=request.bic,
            email=request.email,
            phone=request.phone,
            website=request.website,
            commercial_register=request.commercial_register,
            court=request.court,
            updated_by_id=admin.id,
        )
        db.add(settings)
        logger.info(
            "company_settings_created",
            user_id=str(admin.id),
            company_name=request.company_name
        )
    else:
        # Aktualisiere bestehende Firmendaten
        settings.company_name = request.company_name
        settings.alternative_names = request.alternative_names
        settings.street = request.street
        settings.postal_code = request.postal_code
        settings.city = request.city
        settings.country = request.country
        settings.vat_id = request.vat_id
        settings.tax_number = request.tax_number
        settings.iban = request.iban
        settings.bic = request.bic
        settings.email = request.email
        settings.phone = request.phone
        settings.website = request.website
        settings.commercial_register = request.commercial_register
        settings.court = request.court
        settings.updated_by_id = admin.id
        settings.updated_at = datetime.now(timezone.utc)

        logger.info(
            "company_settings_updated",
            user_id=str(admin.id),
            company_name=request.company_name
        )

    await db.commit()
    await db.refresh(settings)

    return CompanySettingsResponse(
        id=str(settings.id),
        company_name=settings.company_name,
        alternative_names=settings.alternative_names or [],
        street=settings.street,
        postal_code=settings.postal_code,
        city=settings.city,
        country=settings.country or "Deutschland",
        vat_id=settings.vat_id,
        tax_number=settings.tax_number,
        iban=settings.iban,
        bic=settings.bic,
        email=settings.email,
        phone=settings.phone,
        website=settings.website,
        commercial_register=settings.commercial_register,
        court=settings.court,
        created_at=settings.created_at,
        updated_at=settings.updated_at,
        updated_by_id=str(settings.updated_by_id) if settings.updated_by_id else None,
    )


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Firmendaten loeschen",
    description="Loescht alle konfigurierten Firmendaten"
)
async def delete_company_settings(
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Loescht die Firmendaten.

    Nach dem Loeschen ist keine automatische Erkennung von
    Eingangs-/Ausgangsrechnungen mehr moeglich.

    Nur fuer Administratoren zugaenglich.
    """
    settings = await get_company_settings_or_none(db)

    if settings is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Firmendaten zum Loeschen vorhanden"
        )

    await db.delete(settings)
    await db.commit()

    logger.info(
        "company_settings_deleted",
        user_id=str(admin.id)
    )
