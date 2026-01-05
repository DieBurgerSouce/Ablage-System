# -*- coding: utf-8 -*-
"""
DATEV Export API Endpoints.

Endpunkte fuer:
- /api/v1/datev/config - Konfiguration verwalten
- /api/v1/datev/config/{id}/vendors - Vendor-Mappings verwalten
- /api/v1/datev/export/preview - Export-Vorschau
- /api/v1/datev/export - Buchungsstapel exportieren
- /api/v1/datev/export/history - Export-Historie

Standards: DATEV Buchungsstapel CSV Format (Version 700)
"""

import logging
import urllib.parse
import uuid as uuid_module
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.datev import (
    DATEVConfigurationCreate,
    DATEVConfigurationResponse,
    DATEVConfigurationUpdate,
    DATEVExportHistoryItem,
    DATEVExportHistoryResponse,
    DATEVExportPreview,
    DATEVExportRequest,
    DATEVExportResponse,
    DATEVVendorMappingCreate,
    DATEVVendorMappingResponse,
    DATEVVendorMappingUpdate,
    Kontenrahmen,
    KontenrahmenInfo,
)
from app.api.dependencies import get_current_active_user, check_datev_export_rate_limit
from app.core.security import build_content_disposition
from app.db import models
from app.db.database import get_async_db
from app.services.datev import get_datev_export_service, SKR03, SKR04

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/datev", tags=["DATEV Export"])


# =============================================================================
# CONFIGURATION ENDPOINTS
# =============================================================================

@router.post(
    "/config",
    response_model=DATEVConfigurationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="DATEV-Konfiguration erstellen",
    description="""
    Erstellt eine neue DATEV-Konfiguration fuer den Buchungsstapel-Export.

    **Pflichtfelder:**
    - berater_nr: Beraternummer (max. 7 Stellen)
    - mandanten_nr: Mandantennummer (max. 5 Stellen)
    - wj_beginn: Wirtschaftsjahr-Beginn

    Diese Daten erhalten Sie von Ihrem Steuerberater.
    """
)
async def create_config(
    config_data: DATEVConfigurationCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(get_current_active_user),
) -> DATEVConfigurationResponse:
    """Erstellt eine neue DATEV-Konfiguration."""
    # Bestehende Default-Konfiguration deaktivieren falls neue Default
    if config_data.is_default:
        result = await db.execute(
            select(models.DATEVConfiguration).where(
                models.DATEVConfiguration.user_id == current_user.id,
                models.DATEVConfiguration.is_default == True,
            )
        )
        existing_default = result.scalar_one_or_none()
        if existing_default:
            existing_default.is_default = False

    # Neue Konfiguration erstellen
    config = models.DATEVConfiguration(
        id=uuid_module.uuid4(),
        user_id=current_user.id,
        berater_nr=config_data.berater_nr,
        mandanten_nr=config_data.mandanten_nr,
        wj_beginn=config_data.wj_beginn,
        kontenrahmen=config_data.kontenrahmen.value,
        incoming_expense_account=config_data.incoming_expense_account,
        incoming_creditor_account=config_data.incoming_creditor_account,
        outgoing_revenue_account=config_data.outgoing_revenue_account,
        outgoing_debtor_account=config_data.outgoing_debtor_account,
        sammelkonto_kreditoren=config_data.sammelkonto_kreditoren,
        sammelkonto_debitoren=config_data.sammelkonto_debitoren,
        sachkontenlange=config_data.sachkontenlange,
        buchungstext_format=config_data.buchungstext_format,
        is_default=config_data.is_default,
        is_active=True,
    )

    db.add(config)
    await db.commit()
    await db.refresh(config)

    logger.info(
        "datev_config_created",
        extra={"config_id": str(config.id), "user_id": str(current_user.id)}
    )

    return DATEVConfigurationResponse.model_validate(config)


@router.get(
    "/config",
    response_model=List[DATEVConfigurationResponse],
    summary="DATEV-Konfigurationen auflisten",
)
async def list_configs(
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(get_current_active_user),
) -> List[DATEVConfigurationResponse]:
    """Listet alle DATEV-Konfigurationen des Benutzers."""
    result = await db.execute(
        select(models.DATEVConfiguration).where(
            models.DATEVConfiguration.user_id == current_user.id,
            models.DATEVConfiguration.is_active == True,
        ).order_by(models.DATEVConfiguration.is_default.desc())
    )
    configs = result.scalars().all()
    return [DATEVConfigurationResponse.model_validate(c) for c in configs]


@router.get(
    "/config/default",
    response_model=DATEVConfigurationResponse,
    summary="Standard-Konfiguration abrufen",
)
async def get_default_config(
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(get_current_active_user),
) -> DATEVConfigurationResponse:
    """Ruft die Standard-Konfiguration ab."""
    result = await db.execute(
        select(models.DATEVConfiguration).where(
            models.DATEVConfiguration.user_id == current_user.id,
            models.DATEVConfiguration.is_default == True,
            models.DATEVConfiguration.is_active == True,
        )
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Standard-Konfiguration gefunden. Bitte zuerst eine Konfiguration erstellen."
        )

    return DATEVConfigurationResponse.model_validate(config)


@router.get(
    "/config/{config_id}",
    response_model=DATEVConfigurationResponse,
    summary="Konfiguration abrufen",
)
async def get_config(
    config_id: uuid_module.UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(get_current_active_user),
) -> DATEVConfigurationResponse:
    """Ruft eine spezifische Konfiguration ab."""
    result = await db.execute(
        select(models.DATEVConfiguration).where(
            models.DATEVConfiguration.id == config_id,
            models.DATEVConfiguration.user_id == current_user.id,
        )
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Konfiguration nicht gefunden"
        )

    return DATEVConfigurationResponse.model_validate(config)


@router.put(
    "/config/{config_id}",
    response_model=DATEVConfigurationResponse,
    summary="Konfiguration aktualisieren",
)
async def update_config(
    config_id: uuid_module.UUID,
    config_data: DATEVConfigurationUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(get_current_active_user),
) -> DATEVConfigurationResponse:
    """Aktualisiert eine DATEV-Konfiguration."""
    result = await db.execute(
        select(models.DATEVConfiguration).where(
            models.DATEVConfiguration.id == config_id,
            models.DATEVConfiguration.user_id == current_user.id,
        )
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Konfiguration nicht gefunden"
        )

    # Update nur gesetzte Felder
    update_data = config_data.model_dump(exclude_unset=True)

    # Kontenrahmen-Enum zu String konvertieren
    if "kontenrahmen" in update_data and update_data["kontenrahmen"]:
        update_data["kontenrahmen"] = update_data["kontenrahmen"].value

    for key, value in update_data.items():
        setattr(config, key, value)

    await db.commit()
    await db.refresh(config)

    # Audit Logging
    logger.info(
        "datev_config_updated",
        extra={
            "config_id": str(config_id),
            "user_id": str(current_user.id),
            "updated_fields": list(update_data.keys()),
        }
    )

    return DATEVConfigurationResponse.model_validate(config)


@router.delete(
    "/config/{config_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Konfiguration loeschen",
)
async def delete_config(
    config_id: uuid_module.UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Response:
    """Loescht eine DATEV-Konfiguration (Soft-Delete)."""
    result = await db.execute(
        select(models.DATEVConfiguration).where(
            models.DATEVConfiguration.id == config_id,
            models.DATEVConfiguration.user_id == current_user.id,
        )
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Konfiguration nicht gefunden"
        )

    # Soft-Delete
    config.is_active = False
    await db.commit()

    # Audit Logging
    logger.info(
        "datev_config_deleted",
        extra={
            "config_id": str(config_id),
            "user_id": str(current_user.id),
            "action": "soft_delete",
        }
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =============================================================================
# VENDOR MAPPING ENDPOINTS
# =============================================================================

@router.post(
    "/config/{config_id}/vendors",
    response_model=DATEVVendorMappingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Vendor-Mapping hinzufuegen",
    description="""
    Erstellt eine lieferantenspezifische Kontozuordnung.

    Ermoeglicht individuelle Konten pro Lieferant statt Standardkonten.
    Matching erfolgt ueber: USt-IdNr > IBAN > Firmenname
    """
)
async def create_vendor_mapping(
    config_id: uuid_module.UUID,
    mapping_data: DATEVVendorMappingCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(get_current_active_user),
) -> DATEVVendorMappingResponse:
    """Erstellt ein Vendor-Mapping."""
    # Konfiguration pruefen
    result = await db.execute(
        select(models.DATEVConfiguration).where(
            models.DATEVConfiguration.id == config_id,
            models.DATEVConfiguration.user_id == current_user.id,
            models.DATEVConfiguration.is_active == True,
        )
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Konfiguration nicht gefunden"
        )

    # Mindestens ein Identifikationsmerkmal erforderlich
    if not any([mapping_data.vendor_name, mapping_data.vendor_vat_id,
                mapping_data.vendor_iban, mapping_data.business_entity_id]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mindestens ein Identifikationsmerkmal erforderlich (Name, USt-IdNr, IBAN oder Entity)"
        )

    # Optionale VIES-Validierung der USt-IdNr
    vies_validation_result = None
    if mapping_data.verify_vat_with_vies and mapping_data.vendor_vat_id:
        from app.services.vies_service import get_vies_service, VIESValidationStatus

        vies_service = get_vies_service()
        vies_validation_result = await vies_service.validate_vat_id(
            mapping_data.vendor_vat_id
        )

        if vies_validation_result.status == VIESValidationStatus.INVALID:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"USt-IdNr ungueltig: {vies_validation_result.error_message or 'VIES-Pruefung fehlgeschlagen'}"
            )
        elif vies_validation_result.status == VIESValidationStatus.ERROR:
            # Bei Service-Fehlern nur warnen, nicht blockieren
            logger.warning(
                "vies_validation_error",
                extra={
                    "vat_id": mapping_data.vendor_vat_id,
                    "error": vies_validation_result.error_message,
                }
            )

    # verify_vat_with_vies aus dem Mapping entfernen (nicht in DB speichern)
    mapping_dict = mapping_data.model_dump(exclude={"verify_vat_with_vies"})

    mapping = models.DATEVVendorMapping(
        id=uuid_module.uuid4(),
        config_id=config_id,
        **mapping_dict
    )

    db.add(mapping)
    await db.commit()
    await db.refresh(mapping)

    # Audit Logging
    logger.info(
        "datev_vendor_mapping_created",
        extra={
            "mapping_id": str(mapping.id),
            "config_id": str(config_id),
            "user_id": str(current_user.id),
            "vendor_name": mapping_data.vendor_name,
            "vies_validated": vies_validation_result is not None,
            "vies_status": vies_validation_result.status.value if vies_validation_result else None,
        }
    )

    return DATEVVendorMappingResponse.model_validate(mapping)


@router.get(
    "/config/{config_id}/vendors",
    response_model=List[DATEVVendorMappingResponse],
    summary="Vendor-Mappings auflisten",
)
async def list_vendor_mappings(
    config_id: uuid_module.UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(get_current_active_user),
) -> List[DATEVVendorMappingResponse]:
    """Listet alle Vendor-Mappings einer Konfiguration."""
    # Konfiguration pruefen
    result = await db.execute(
        select(models.DATEVConfiguration).where(
            models.DATEVConfiguration.id == config_id,
            models.DATEVConfiguration.user_id == current_user.id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Konfiguration nicht gefunden"
        )

    result = await db.execute(
        select(models.DATEVVendorMapping).where(
            models.DATEVVendorMapping.config_id == config_id
        )
    )
    mappings = result.scalars().all()

    return [DATEVVendorMappingResponse.model_validate(m) for m in mappings]


@router.put(
    "/config/{config_id}/vendors/{mapping_id}",
    response_model=DATEVVendorMappingResponse,
    summary="Vendor-Mapping aktualisieren",
    description="""
    Aktualisiert ein bestehendes Vendor-Mapping.

    Ermoeglicht Aenderung von Kontozuordnungen, Identifikationsmerkmalen
    und Kostenstellen fuer einen Lieferanten.
    """
)
async def update_vendor_mapping(
    config_id: uuid_module.UUID,
    mapping_id: uuid_module.UUID,
    mapping_data: DATEVVendorMappingUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(get_current_active_user),
) -> DATEVVendorMappingResponse:
    """Aktualisiert ein Vendor-Mapping."""
    # Config-Ownership pruefen
    config_result = await db.execute(
        select(models.DATEVConfiguration).where(
            models.DATEVConfiguration.id == config_id,
            models.DATEVConfiguration.user_id == current_user.id,
        )
    )
    if not config_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Konfiguration nicht gefunden"
        )

    # Mapping laden
    result = await db.execute(
        select(models.DATEVVendorMapping).where(
            models.DATEVVendorMapping.id == mapping_id,
            models.DATEVVendorMapping.config_id == config_id,
        )
    )
    mapping = result.scalar_one_or_none()

    if not mapping:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor-Mapping nicht gefunden"
        )

    # Update nur gesetzte Felder
    update_data = mapping_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(mapping, key, value)

    await db.commit()
    await db.refresh(mapping)

    # Audit Logging
    logger.info(
        "datev_vendor_mapping_updated",
        extra={
            "mapping_id": str(mapping_id),
            "config_id": str(config_id),
            "user_id": str(current_user.id),
            "updated_fields": list(update_data.keys()),
        }
    )

    return DATEVVendorMappingResponse.model_validate(mapping)


@router.delete(
    "/config/{config_id}/vendors/{mapping_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Vendor-Mapping loeschen",
)
async def delete_vendor_mapping(
    config_id: uuid_module.UUID,
    mapping_id: uuid_module.UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Response:
    """Loescht ein Vendor-Mapping."""
    # SECURITY FIX: Zuerst Config-Ownership pruefen (OWASP A07:2021)
    config_result = await db.execute(
        select(models.DATEVConfiguration).where(
            models.DATEVConfiguration.id == config_id,
            models.DATEVConfiguration.user_id == current_user.id,
        )
    )
    if not config_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Konfiguration nicht gefunden"
        )

    # Mapping pruefen
    result = await db.execute(
        select(models.DATEVVendorMapping).where(
            models.DATEVVendorMapping.id == mapping_id,
            models.DATEVVendorMapping.config_id == config_id,
        )
    )
    mapping = result.scalar_one_or_none()

    if not mapping:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor-Mapping nicht gefunden"
        )

    await db.delete(mapping)
    await db.commit()

    # Audit Logging
    logger.info(
        "datev_vendor_mapping_deleted",
        extra={
            "mapping_id": str(mapping_id),
            "config_id": str(config_id),
            "user_id": str(current_user.id),
        }
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =============================================================================
# EXPORT ENDPOINTS
# =============================================================================

@router.post(
    "/export/preview",
    response_model=DATEVExportPreview,
    summary="Export-Vorschau",
    description="""
    Zeigt Vorschau des Exports ohne tatsaechlichen Download.

    Nuetzlich um zu pruefen:
    - Welche Dokumente exportiert werden
    - Welche uebersprungen werden (und warum)
    - Beispiel-Buchungssaetze
    """
)
async def preview_export(
    request: DATEVExportRequest = Body(...),
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(get_current_active_user),
) -> DATEVExportPreview:
    """Erstellt Vorschau des DATEV-Exports."""
    service = get_datev_export_service()

    try:
        preview = await service.preview_export(
            db=db,
            user_id=current_user.id,
            document_ids=request.document_ids,
            period_from=request.period_from,
            period_to=request.period_to,
            config_id=request.config_id,
        )
        return preview

    except ValueError as e:
        # SECURITY FIX: Keine internen Details an Client senden
        logger.warning(
            "datev_preview_validation_error",
            extra={
                "user_id": str(current_user.id),
                "error": str(e),
            }
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungueltige Eingabedaten. Bitte pruefen Sie Ihre Angaben."
        )


@router.post(
    "/export",
    response_class=Response,
    summary="DATEV Buchungsstapel exportieren",
    description="""
    Exportiert Rechnungen als DATEV Buchungsstapel CSV.

    **Format:**
    - Encoding: CP1252 (Windows)
    - Trennzeichen: Semikolon
    - Dezimalformat: Komma
    - 116 Spalten gemaess DATEV-Standard

    **Voraussetzungen:**
    - Dokumente muessen extrahierte Rechnungsdaten haben
    - Rechnungsrichtung muss bekannt sein (Eingang/Ausgang)
    - Gueltige DATEV-Konfiguration erforderlich
    """
)
async def export_buchungsstapel(
    request: DATEVExportRequest = Body(...),
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(check_datev_export_rate_limit),
) -> Response:
    """Exportiert DATEV-Buchungsstapel als CSV-Download."""
    service = get_datev_export_service()

    try:
        csv_bytes, export_record = await service.export_buchungsstapel(
            db=db,
            user_id=current_user.id,
            document_ids=request.document_ids,
            period_from=request.period_from,
            period_to=request.period_to,
            config_id=request.config_id,
            include_already_exported=request.include_already_exported,
        )

        # CRITICAL FIX: Commit VOR Response senden!
        # Bei parallelen Exporten kann sonst Transaktion A fehlschlagen
        # wenn B zwischendurch committet (Race Condition)
        await db.commit()

        # SECURITY: Use centralized sanitization to prevent CRLF injection (Phase 10)
        return Response(
            content=csv_bytes,
            media_type="text/csv; charset=windows-1252",
            headers={
                "Content-Disposition": build_content_disposition(export_record.filename, "attachment"),
                "X-DATEV-Export-ID": str(export_record.id),
                "X-DATEV-Document-Count": str(export_record.document_count),
            }
        )

    except ValueError as e:
        # SECURITY FIX: Keine internen Details an Client senden
        logger.warning(
            "datev_export_validation_error",
            extra={
                "user_id": str(current_user.id),
                "error": str(e),
            }
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungueltige Eingabedaten. Bitte pruefen Sie Ihre Angaben."
        )
    except Exception as e:
        # SECURITY FIX: Keine Exception-Details an Client senden (Information Disclosure)
        logger.exception(
            "datev_export_error",
            extra={
                "user_id": str(current_user.id),
                "error_type": type(e).__name__,
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Export fehlgeschlagen. Bitte kontaktieren Sie den Administrator."
        )


@router.get(
    "/export/history",
    response_model=DATEVExportHistoryResponse,
    summary="Export-Historie",
)
async def get_export_history(
    page: int = Query(1, ge=1, description="Seite"),
    page_size: int = Query(20, ge=1, le=100, description="Eintraege pro Seite"),
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(get_current_active_user),
) -> DATEVExportHistoryResponse:
    """Ruft die Export-Historie ab."""
    # Total zaehlen
    count_result = await db.execute(
        select(func.count(models.DATEVExport.id)).where(
            models.DATEVExport.exported_by_id == current_user.id
        )
    )
    total = count_result.scalar() or 0

    # Exporte laden
    offset = (page - 1) * page_size
    result = await db.execute(
        select(models.DATEVExport).where(
            models.DATEVExport.exported_by_id == current_user.id
        ).order_by(
            models.DATEVExport.exported_at.desc()
        ).offset(offset).limit(page_size)
    )
    exports = result.scalars().all()

    items = [DATEVExportHistoryItem.model_validate(e) for e in exports]

    return DATEVExportHistoryResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


# =============================================================================
# VIES VAT-ID VALIDATION
# =============================================================================

@router.get(
    "/vies/validate/{vat_id}",
    summary="USt-IdNr gegen VIES validieren",
    description="""
    Validiert eine EU USt-IdNr gegen die VIES-Datenbank der EU-Kommission.

    **Format:** 2 Buchstaben Laendercode + Nummer (z.B. DE123456789)

    **Antwort:**
    - valid: USt-IdNr ist gueltig und aktiv
    - invalid: USt-IdNr ist ungueltig oder nicht registriert
    - error: VIES-Service nicht erreichbar (Ergebnis gecached falls moeglich)

    **Hinweis:** VIES kann gelegentlich nicht erreichbar sein. Bei Fehlern
    wird empfohlen, es spaeter erneut zu versuchen.
    """
)
async def validate_vat_id(
    vat_id: str,
    current_user: models.User = Depends(get_current_active_user),
) -> dict:
    """Validiert eine USt-IdNr gegen VIES."""
    from app.services.vies_service import get_vies_service

    vies_service = get_vies_service()
    result = await vies_service.validate_vat_id(vat_id)

    return {
        "vat_id": result.vat_id,
        "status": result.status.value,
        "valid": result.valid,
        "company_name": result.company_name,
        "company_address": result.company_address,
        "country_code": result.country_code,
        "vat_number": result.vat_number,
        "request_date": result.request_date.isoformat() if result.request_date else None,
        "cached": result.cached,
        "error_message": result.error_message,
    }


# =============================================================================
# KONTENRAHMEN INFO
# =============================================================================

@router.get(
    "/kontenrahmen",
    response_model=List[KontenrahmenInfo],
    summary="Verfuegbare Kontenrahmen",
)
async def get_kontenrahmen_info(
    current_user: models.User = Depends(get_current_active_user),  # X.3 SECURITY FIX: Auth required
) -> List[KontenrahmenInfo]:
    """Listet verfuegbare Kontenrahmen mit Standardkonten.

    **REQUIRES AUTHENTICATION**

    Args:
        current_user: Authenticated user (required)
    """
    skr03 = SKR03()
    skr04 = SKR04()

    return [
        KontenrahmenInfo(
            name=Kontenrahmen.SKR03,
            beschreibung=skr03.beschreibung,
            standard_konten={
                "wareneingang_19": skr03.WARENEINGANG_19,
                "wareneingang_7": skr03.WARENEINGANG_7,
                "erloese_19": skr03.ERLOESE_19,
                "erloese_7": skr03.ERLOESE_7,
                "kreditor_default": skr03.default_creditor_account,
                "debitor_default": skr03.default_debtor_account,
                "sammelkonto_kreditoren": skr03.sammelkonto_kreditoren,
                "sammelkonto_debitoren": skr03.sammelkonto_debitoren,
            },
            verfuegbare_kategorien=list(skr03.expense_accounts.keys()),
        ),
        KontenrahmenInfo(
            name=Kontenrahmen.SKR04,
            beschreibung=skr04.beschreibung,
            standard_konten={
                "wareneingang_19": skr04.WARENEINGANG_19,
                "wareneingang_7": skr04.WARENEINGANG_7,
                "erloese_19": skr04.ERLOESE_19,
                "erloese_7": skr04.ERLOESE_7,
                "kreditor_default": skr04.default_creditor_account,
                "debitor_default": skr04.default_debtor_account,
                "sammelkonto_kreditoren": skr04.sammelkonto_kreditoren,
                "sammelkonto_debitoren": skr04.sammelkonto_debitoren,
            },
            verfuegbare_kategorien=list(skr04.expense_accounts.keys()),
        ),
    ]
