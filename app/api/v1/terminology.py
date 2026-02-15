# -*- coding: utf-8 -*-
"""Deutsche Terminologie API Router.

Endpoints fuer das zentrale deutsche Terminologie-Woerterbuch.
DATEV-konforme Fachbegriffe, Fehlermeldungen, Statusmeldungen und Tooltips.
"""
from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_user

router = APIRouter(
    prefix="/terminology",
    tags=["Deutsche Terminologie"],
    dependencies=[Depends(get_current_user)],
)


# ============================================================================
# Pydantic Schemas
# ============================================================================


class TerminologyValidateRequest(BaseModel):
    """Schema fuer Terminologie-Validierung."""
    text: str = Field(..., min_length=1, max_length=10000)


class TerminologyFinding(BaseModel):
    """Einzelner Befund bei Terminologie-Validierung."""
    found: str
    should_be: str
    message: str


class TerminologyValidateResponse(BaseModel):
    """Antwort der Terminologie-Validierung."""
    findings: List[TerminologyFinding]
    has_issues: bool


# ============================================================================
# Endpoints
# ============================================================================


@router.get(
    "/terms",
    summary="Alle deutschen Fachbegriffe",
)
async def get_all_terms() -> Dict[str, str]:
    """Komplettes Terminologie-Woerterbuch fuer Frontend-i18n."""
    from app.services.german_terminology_service import get_german_terminology_service

    service = get_german_terminology_service()
    return service.get_all_terms()


@router.get(
    "/terms/{category}",
    summary="Fachbegriffe einer Kategorie",
)
async def get_category_terms(category: str) -> Dict[str, str]:
    """Fachbegriffe einer bestimmten Kategorie abrufen.

    Kategorien: buchhaltung, rechnungswesen, steuer, datev, bwa,
    dokumente, bank, entities, status
    """
    from app.services.german_terminology_service import get_german_terminology_service

    service = get_german_terminology_service()
    return service.get_category_terms(category)


@router.get(
    "/errors",
    summary="Alle deutschen Fehlermeldungen",
)
async def get_all_errors() -> Dict[str, str]:
    """Alle deutschen Fehlermeldungen als Dictionary."""
    from app.services.german_terminology_service import get_german_terminology_service

    service = get_german_terminology_service()
    return service.get_all_errors()


@router.get(
    "/translate/{key}",
    summary="Fachbegriff uebersetzen",
)
async def translate_term(key: str) -> dict:
    """Englischen Fachbegriff ins Deutsche uebersetzen."""
    from app.services.german_terminology_service import get_german_terminology_service

    service = get_german_terminology_service()
    translation = service.translate(key)

    return {
        "key": key,
        "translation": translation,
        "found": translation != key,
    }


@router.get(
    "/errors/{key}",
    summary="Deutsche Fehlermeldung abrufen",
)
async def get_error_message(key: str) -> dict:
    """Deutsche Fehlermeldung fuer einen Fehler-Schluessel abrufen."""
    from app.services.german_terminology_service import get_german_terminology_service

    service = get_german_terminology_service()
    message = service.get_error_message(key)

    return {
        "key": key,
        "message": message,
    }


@router.get(
    "/status/{key}",
    summary="Deutsche Statusmeldung abrufen",
)
async def get_status_message(key: str) -> dict:
    """Deutsche Statusmeldung fuer einen Status-Schluessel abrufen."""
    from app.services.german_terminology_service import get_german_terminology_service

    service = get_german_terminology_service()
    message = service.get_status_message(key)

    return {
        "key": key,
        "message": message,
    }


@router.get(
    "/tooltips",
    summary="Alle Tooltips abrufen",
)
async def get_all_tooltips() -> Dict[str, str]:
    """Alle deutschen Tooltips fuer UI-Elemente abrufen."""
    from app.services.german_terminology_service import get_german_terminology_service

    service = get_german_terminology_service()
    return service.TOOLTIPS


@router.post(
    "/validate",
    response_model=TerminologyValidateResponse,
    summary="Text auf englische Begriffe pruefen",
)
async def validate_terminology(data: TerminologyValidateRequest) -> TerminologyValidateResponse:
    """Pruefen ob englische Fachbegriffe im Text vorkommen die deutsch sein sollten."""
    from app.services.german_terminology_service import get_german_terminology_service

    service = get_german_terminology_service()
    findings = service.validate_terminology(data.text)

    return TerminologyValidateResponse(
        findings=[
            TerminologyFinding(
                found=f["found"],
                should_be=f.get("should_be", f.get("suggestion", "")),
                message=f.get("message", f.get("context", "")),
            )
            for f in findings
        ],
        has_issues=len(findings) > 0,
    )


@router.get(
    "/dictionary",
    summary="Komplettes Woerterbuch abrufen",
)
async def get_dictionary() -> Dict[str, Dict[str, str]]:
    """Komplettes deutsches Terminologie-Woerterbuch abrufen."""
    from app.services.german_terminology_service import get_german_terminology_service

    service = get_german_terminology_service()
    return service.get_full_dictionary()
