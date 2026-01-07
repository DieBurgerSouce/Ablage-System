# -*- coding: utf-8 -*-
"""
Extracted Data API Endpoints.

Provides REST API endpoints for:
- Querying structured extraction data (invoices, orders, contracts)
- Searching by extracted fields (invoice number, IBAN, amounts)
- Aggregations and statistics

Feinpoliert und durchdacht - Deutsche Dokumente mit hoechster Genauigkeit.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select, and_, or_, cast, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.core.security import build_content_disposition
from app.api.schemas.extracted_data import (
    ExtractedDocumentData,
    ExtractedDocumentType,
    ExtractedInvoiceData,
    ExtractedOrderData,
    ExtractedContractData,
)
from app.db import models
from app.services.export_service import (
    export_invoices_csv,
    export_invoices_excel,
    export_orders_csv,
    export_orders_excel,
    export_contracts_csv,
    export_contracts_excel,
    export_all_excel,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/extracted_data", tags=["Strukturierte Daten"])


# =============================================================================
# RESPONSE SCHEMAS
# =============================================================================

class ExtractedDataSearchResult(BaseModel):
    """Suchergebnis mit Highlight."""
    document_id: UUID
    document_type: ExtractedDocumentType
    confidence: float

    # Wichtigste Felder (je nach Typ)
    reference_number: Optional[str] = None  # Rechnungs-/Bestell-/Vertragsnummer
    document_date: Optional[date] = None
    gross_amount: Optional[Decimal] = None

    # Matching-Info
    matched_field: Optional[str] = None
    matched_value: Optional[str] = None

    # Vorschau
    preview_text: Optional[str] = None  # Erste 200 Zeichen OCR-Text
    filename: Optional[str] = None

    class Config:
        from_attributes = True


class PaginatedSearchResponse(BaseModel):
    """Paginierte Suchergebnisse."""
    items: List[ExtractedDataSearchResult]
    total: int
    page: int
    per_page: int
    pages: int


class InvoiceSummary(BaseModel):
    """Rechnungsuebersicht fuer Liste."""
    document_id: UUID
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    sender_company: Optional[str] = None
    gross_amount: Optional[Decimal] = None
    currency: str = "EUR"
    has_skonto: bool = False
    discount_percent: Optional[Decimal] = None
    discount_due_date: Optional[date] = None
    extraction_confidence: float = 0.0
    needs_review: bool = False
    filename: Optional[str] = None

    class Config:
        from_attributes = True


class PaginatedInvoiceList(BaseModel):
    """Paginierte Rechnungsliste."""
    items: List[InvoiceSummary]
    total: int
    page: int
    per_page: int
    pages: int


class MonthlyAggregation(BaseModel):
    """Monatliche Aggregation."""
    month: str  # "2024-01"
    count: int
    gross_amount: Decimal
    net_amount: Decimal


class ExtractedDataAggregations(BaseModel):
    """Aggregierte Statistiken."""
    total_documents: int
    total_gross_amount: Decimal
    total_net_amount: Decimal
    total_vat_amount: Decimal
    avg_gross_amount: Decimal

    by_month: List[MonthlyAggregation]
    by_document_type: Dict[str, int]


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/search", response_model=PaginatedSearchResponse)
async def search_extracted_data(
    # Rechnungsfelder
    invoice_number: Optional[str] = Query(None, description="Rechnungsnummer (Teilmatch)"),
    customer_number: Optional[str] = Query(None, description="Kundennummer"),
    iban: Optional[str] = Query(None, description="IBAN (exakt oder Teilmatch)"),
    vat_id: Optional[str] = Query(None, description="USt-IdNr."),

    # Betragsfilter
    min_amount: Optional[Decimal] = Query(None, ge=0, description="Mindestbetrag (brutto)"),
    max_amount: Optional[Decimal] = Query(None, ge=0, description="Maximalbetrag (brutto)"),

    # Datumsfilter
    date_from: Optional[date] = Query(None, description="Datum ab (inklusiv)"),
    date_to: Optional[date] = Query(None, description="Datum bis (inklusiv)"),

    # Dokumenttyp
    document_type: Optional[ExtractedDocumentType] = Query(None, description="Dokumenttyp"),

    # Flags
    needs_review: Optional[bool] = Query(None, description="Nur Dokumente die Review benoetigen"),
    has_skonto: Optional[bool] = Query(None, description="Nur Rechnungen mit Skonto"),

    # Pagination
    page: int = Query(1, ge=1, description="Seitennummer"),
    per_page: int = Query(20, ge=1, le=100, description="Ergebnisse pro Seite"),

    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
) -> PaginatedSearchResponse:
    """
    Sucht Dokumente nach extrahierten Feldern.

    **Beispiele:**
    - Alle Rechnungen > 1000 EUR: `?min_amount=1000&document_type=invoice`
    - Dokumente mit IBAN: `?iban=DE89370400440532013000`
    - Rechnungen Januar 2024: `?date_from=2024-01-01&date_to=2024-01-31`
    - Rechnungen mit Skonto: `?has_skonto=true`
    """
    # Basis-Query
    query = select(models.Document).where(
        and_(
            models.Document.owner_id == current_user.id,
            models.Document.deleted_at.is_(None),
            models.Document.extracted_data.isnot(None)
        )
    )

    # Filter aufbauen
    filters = []

    # Dokumenttyp
    if document_type:
        filters.append(
            models.Document.extracted_data["classification"]["document_type"].astext == document_type.value
        )

    # Rechnungsnummer (ILIKE fuer Teilmatch)
    if invoice_number:
        filters.append(
            or_(
                models.Document.extracted_data["invoice"]["invoice_number"].astext.ilike(f"%{invoice_number}%"),
                models.Document.extracted_data["order"]["order_number"].astext.ilike(f"%{invoice_number}%"),
                models.Document.extracted_data["contract"]["contract_number"].astext.ilike(f"%{invoice_number}%")
            )
        )

    # Kundennummer
    if customer_number:
        filters.append(
            models.Document.extracted_data["invoice"]["customer_number"].astext.ilike(f"%{customer_number}%")
        )

    # IBAN
    if iban:
        # Normalisiere IBAN (entferne Leerzeichen)
        iban_clean = iban.replace(" ", "").upper()
        filters.append(
            or_(
                models.Document.extracted_data["invoice"]["sender_bank"]["iban"].astext.ilike(f"%{iban_clean}%"),
                func.jsonb_path_exists(
                    models.Document.extracted_data,
                    f'$.ibans[*] ? (@ like_regex "{iban_clean}")'
                )
            )
        )

    # USt-IdNr
    if vat_id:
        vat_clean = vat_id.replace(" ", "").upper()
        filters.append(
            or_(
                models.Document.extracted_data["invoice"]["sender_vat_id"].astext.ilike(f"%{vat_clean}%"),
                func.jsonb_path_exists(
                    models.Document.extracted_data,
                    f'$.vat_ids[*] ? (@ like_regex "{vat_clean}")'
                )
            )
        )

    # Betragsfilter
    if min_amount is not None:
        filters.append(
            cast(
                models.Document.extracted_data["invoice"]["gross_amount"].astext,
                Decimal
            ) >= min_amount
        )

    if max_amount is not None:
        filters.append(
            cast(
                models.Document.extracted_data["invoice"]["gross_amount"].astext,
                Decimal
            ) <= max_amount
        )

    # Datumsfilter (auf invoice_date oder order_date)
    if date_from:
        filters.append(
            or_(
                cast(
                    models.Document.extracted_data["invoice"]["invoice_date"].astext,
                    String
                ) >= date_from.isoformat(),
                cast(
                    models.Document.extracted_data["order"]["order_date"].astext,
                    String
                ) >= date_from.isoformat()
            )
        )

    if date_to:
        filters.append(
            or_(
                cast(
                    models.Document.extracted_data["invoice"]["invoice_date"].astext,
                    String
                ) <= date_to.isoformat(),
                cast(
                    models.Document.extracted_data["order"]["order_date"].astext,
                    String
                ) <= date_to.isoformat()
            )
        )

    # Needs Review
    if needs_review is not None:
        filters.append(
            or_(
                models.Document.extracted_data["invoice"]["needs_review"].astext == str(needs_review).lower(),
                models.Document.extracted_data["order"]["needs_review"].astext == str(needs_review).lower()
            )
        )

    # Hat Skonto
    if has_skonto is True:
        filters.append(
            models.Document.extracted_data["invoice"]["discount_percent"].isnot(None)
        )

    # Filter anwenden
    if filters:
        query = query.where(and_(*filters))

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Pagination
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    # Sortierung (neueste zuerst)
    query = query.order_by(models.Document.created_at.desc())

    # Ausfuehren
    result = await db.execute(query)
    documents = result.scalars().all()

    # Zu Suchergebnissen konvertieren
    items = []
    for doc in documents:
        extracted = doc.extracted_data or {}
        classification = extracted.get("classification", {})
        invoice = extracted.get("invoice", {})
        order = extracted.get("order", {})
        contract = extracted.get("contract", {})

        doc_type = classification.get("document_type", "unknown")

        # Referenznummer je nach Typ
        ref_number = None
        doc_date = None
        amount = None

        if doc_type == "invoice":
            ref_number = invoice.get("invoice_number")
            doc_date = invoice.get("invoice_date")
            amount = invoice.get("gross_amount")
        elif doc_type == "order":
            ref_number = order.get("order_number")
            doc_date = order.get("order_date")
            amount = order.get("total_amount")
        elif doc_type == "contract":
            ref_number = contract.get("contract_number")
            doc_date = contract.get("contract_date")
            amount = contract.get("contract_value")

        items.append(ExtractedDataSearchResult(
            document_id=doc.id,
            document_type=ExtractedDocumentType(doc_type) if doc_type in ["invoice", "order", "contract", "delivery_note", "receipt"] else ExtractedDocumentType.UNKNOWN,
            confidence=classification.get("confidence", 0.0),
            reference_number=ref_number,
            document_date=doc_date,
            gross_amount=Decimal(str(amount)) if amount else None,
            preview_text=doc.ocr_text[:200] if doc.ocr_text else None,
            filename=doc.filename
        ))

    pages = (total + per_page - 1) // per_page

    logger.info(
        "extracted_data_search",
        user_id=str(current_user.id),
        total_results=total,
        page=page,
        filters_applied=len(filters)
    )

    return PaginatedSearchResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages
    )


@router.get("/invoices", response_model=PaginatedInvoiceList)
async def list_invoices(
    # Filter
    overdue: Optional[bool] = Query(None, description="Nur ueberfaellige Rechnungen"),
    has_skonto: Optional[bool] = Query(None, description="Nur mit Skonto-Option"),
    skonto_expiring_soon: Optional[bool] = Query(None, description="Skonto laeuft in 3 Tagen ab"),

    # Betragsfilter
    min_amount: Optional[Decimal] = Query(None, ge=0),
    max_amount: Optional[Decimal] = Query(None, ge=0),

    # Sortierung
    order_by: str = Query("invoice_date", pattern="^(invoice_date|gross_amount|due_date)$"),
    order_dir: str = Query("desc", pattern="^(asc|desc)$"),

    # Pagination
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),

    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
) -> PaginatedInvoiceList:
    """
    Listet alle Rechnungen mit Filtermoeglichkeiten.

    Optimiert fuer Buchhaltungs-Workflows:
    - Offene Rechnungen: `?overdue=true`
    - Mit Skonto-Option: `?has_skonto=true`
    - Skonto laeuft bald ab: `?skonto_expiring_soon=true`
    """
    # Helper fuer JSONB Text-Extraktion (PostgreSQL-kompatibel)
    def jsonb_text(field: str, *path: str) -> Any:
        """Extrahiert Text aus JSONB-Feld mit PostgreSQL jsonb_extract_path_text."""
        return func.jsonb_extract_path_text(
            cast(models.Document.extracted_data, JSONB),
            *path
        )

    # Basis-Query: Nur Rechnungen
    query = select(models.Document).where(
        and_(
            models.Document.owner_id == current_user.id,
            models.Document.deleted_at.is_(None),
            jsonb_text("extracted_data", "classification", "document_type") == "invoice"
        )
    )

    filters = []

    # Ueberfaellige (due_date < heute)
    if overdue is True:
        today = date.today().isoformat()
        filters.append(
            jsonb_text("extracted_data", "invoice", "due_date") < today
        )

    # Hat Skonto
    if has_skonto is True:
        filters.append(
            jsonb_text("extracted_data", "invoice", "discount_percent").isnot(None)
        )

    # Skonto laeuft bald ab (innerhalb 3 Tagen)
    if skonto_expiring_soon is True:
        from datetime import timedelta
        today = date.today()
        soon = (today + timedelta(days=3)).isoformat()
        filters.append(
            and_(
                jsonb_text("extracted_data", "invoice", "discount_due_date").isnot(None),
                jsonb_text("extracted_data", "invoice", "discount_due_date") <= soon,
                jsonb_text("extracted_data", "invoice", "discount_due_date") >= today.isoformat()
            )
        )

    # Betragsfilter
    if min_amount is not None:
        filters.append(
            cast(jsonb_text("extracted_data", "invoice", "gross_amount"), Decimal) >= min_amount
        )

    if max_amount is not None:
        filters.append(
            cast(jsonb_text("extracted_data", "invoice", "gross_amount"), Decimal) <= max_amount
        )

    if filters:
        query = query.where(and_(*filters))

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Sortierung - verwende created_at als Fallback
    if order_dir == "desc":
        query = query.order_by(models.Document.created_at.desc().nulls_last())
    else:
        query = query.order_by(models.Document.created_at.asc().nulls_last())

    # Pagination
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    documents = result.scalars().all()

    # Zu InvoiceSummary konvertieren
    items = []
    for doc in documents:
        invoice = doc.extracted_data.get("invoice", {}) if doc.extracted_data else {}
        sender = invoice.get("sender", {})

        items.append(InvoiceSummary(
            document_id=doc.id,
            invoice_number=invoice.get("invoice_number"),
            invoice_date=invoice.get("invoice_date"),
            due_date=invoice.get("due_date"),
            sender_company=sender.get("company"),
            gross_amount=Decimal(str(invoice["gross_amount"])) if invoice.get("gross_amount") else None,
            currency=invoice.get("currency", "EUR"),
            has_skonto=invoice.get("discount_percent") is not None,
            discount_percent=Decimal(str(invoice["discount_percent"])) if invoice.get("discount_percent") else None,
            discount_due_date=invoice.get("discount_due_date"),
            extraction_confidence=invoice.get("extraction_confidence", 0.0),
            needs_review=invoice.get("needs_review", False),
            filename=doc.filename
        ))

    pages = (total + per_page - 1) // per_page

    return PaginatedInvoiceList(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages
    )


@router.get("/aggregations", response_model=ExtractedDataAggregations)
async def get_aggregations(
    document_type: Optional[ExtractedDocumentType] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),

    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
) -> ExtractedDataAggregations:
    """
    Aggregierte Statistiken ueber extrahierte Daten.

    **Returns:**
    - Gesamtanzahl Dokumente
    - Summe Brutto/Netto/MwSt
    - Durchschnittlicher Rechnungsbetrag
    - Monatliche Aufteilung
    - Aufteilung nach Dokumenttyp
    """
    # Basis-Query
    base_filter = and_(
        models.Document.owner_id == current_user.id,
        models.Document.deleted_at.is_(None),
        models.Document.extracted_data.isnot(None)
    )

    filters = [base_filter]

    if document_type:
        filters.append(
            models.Document.extracted_data["classification"]["document_type"].astext == document_type.value
        )

    if date_from:
        filters.append(
            or_(
                cast(models.Document.extracted_data["invoice"]["invoice_date"].astext, String) >= date_from.isoformat(),
                cast(models.Document.extracted_data["order"]["order_date"].astext, String) >= date_from.isoformat()
            )
        )

    if date_to:
        filters.append(
            or_(
                cast(models.Document.extracted_data["invoice"]["invoice_date"].astext, String) <= date_to.isoformat(),
                cast(models.Document.extracted_data["order"]["order_date"].astext, String) <= date_to.isoformat()
            )
        )

    combined_filter = and_(*filters)

    # Alle relevanten Dokumente laden
    query = select(models.Document).where(combined_filter)
    result = await db.execute(query)
    documents = result.scalars().all()

    # Aggregationen berechnen
    total_documents = len(documents)
    total_gross = Decimal("0")
    total_net = Decimal("0")
    total_vat = Decimal("0")
    by_type: Dict[str, int] = {}
    by_month: Dict[str, Dict[str, Any]] = {}

    for doc in documents:
        extracted = doc.extracted_data or {}
        classification = extracted.get("classification", {})
        doc_type = classification.get("document_type", "unknown")

        # By Type
        by_type[doc_type] = by_type.get(doc_type, 0) + 1

        # Betraege (nur fuer Rechnungen)
        if doc_type == "invoice":
            invoice = extracted.get("invoice", {})

            gross = invoice.get("gross_amount")
            net = invoice.get("net_amount")
            vat = invoice.get("vat_amount")

            if gross:
                total_gross += Decimal(str(gross))
            if net:
                total_net += Decimal(str(net))
            if vat:
                total_vat += Decimal(str(vat))

            # By Month
            invoice_date = invoice.get("invoice_date")
            if invoice_date:
                # Format: "2024-01"
                if isinstance(invoice_date, str):
                    month_key = invoice_date[:7]
                else:
                    month_key = str(invoice_date)[:7]

                if month_key not in by_month:
                    by_month[month_key] = {
                        "count": 0,
                        "gross": Decimal("0"),
                        "net": Decimal("0")
                    }

                by_month[month_key]["count"] += 1
                if gross:
                    by_month[month_key]["gross"] += Decimal(str(gross))
                if net:
                    by_month[month_key]["net"] += Decimal(str(net))

    # Durchschnitt berechnen
    invoice_count = by_type.get("invoice", 0)
    avg_gross = total_gross / invoice_count if invoice_count > 0 else Decimal("0")

    # Monatliche Aggregationen sortieren
    monthly_list = [
        MonthlyAggregation(
            month=month,
            count=data["count"],
            gross_amount=data["gross"],
            net_amount=data["net"]
        )
        for month, data in sorted(by_month.items(), reverse=True)
    ]

    return ExtractedDataAggregations(
        total_documents=total_documents,
        total_gross_amount=total_gross,
        total_net_amount=total_net,
        total_vat_amount=total_vat,
        avg_gross_amount=avg_gross.quantize(Decimal("0.01")),
        by_month=monthly_list[:12],  # Letzte 12 Monate
        by_document_type=by_type
    )


@router.get("/document-types/stats", response_model=Dict[str, int])
async def get_document_type_stats(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
) -> Dict[str, int]:
    """
    Statistik ueber Dokumenttypen.

    **Returns:**
    Dict mit Dokumenttyp -> Anzahl
    """
    query = select(models.Document).where(
        and_(
            models.Document.owner_id == current_user.id,
            models.Document.deleted_at.is_(None),
            models.Document.extracted_data.isnot(None)
        )
    )

    result = await db.execute(query)
    documents = result.scalars().all()

    stats: Dict[str, int] = {}
    for doc in documents:
        extracted = doc.extracted_data or {}
        doc_type = extracted.get("classification", {}).get("document_type", "unknown")
        stats[doc_type] = stats.get(doc_type, 0) + 1

    return stats


# =============================================================================
# EXPORT ENDPOINTS
# =============================================================================

async def _get_documents_for_export(
    db: AsyncSession,
    user_id: UUID,
    document_type: Optional[str],
    date_from: Optional[date],
    date_to: Optional[date],
    min_amount: Optional[Decimal],
    max_amount: Optional[Decimal],
) -> List[Dict[str, Any]]:
    """Holt Dokumente fuer Export mit Filtern."""
    query = select(models.Document).where(
        and_(
            models.Document.owner_id == user_id,
            models.Document.deleted_at.is_(None),
            models.Document.extracted_data.isnot(None)
        )
    )

    filters = []

    if document_type:
        filters.append(
            models.Document.extracted_data["classification"]["document_type"].astext == document_type
        )

    if date_from:
        filters.append(
            or_(
                cast(models.Document.extracted_data["invoice"]["invoice_date"].astext, String) >= date_from.isoformat(),
                cast(models.Document.extracted_data["order"]["order_date"].astext, String) >= date_from.isoformat(),
                cast(models.Document.extracted_data["contract"]["contract_date"].astext, String) >= date_from.isoformat()
            )
        )

    if date_to:
        filters.append(
            or_(
                cast(models.Document.extracted_data["invoice"]["invoice_date"].astext, String) <= date_to.isoformat(),
                cast(models.Document.extracted_data["order"]["order_date"].astext, String) <= date_to.isoformat(),
                cast(models.Document.extracted_data["contract"]["contract_date"].astext, String) <= date_to.isoformat()
            )
        )

    if min_amount is not None:
        filters.append(
            cast(models.Document.extracted_data["invoice"]["gross_amount"].astext, Decimal) >= min_amount
        )

    if max_amount is not None:
        filters.append(
            cast(models.Document.extracted_data["invoice"]["gross_amount"].astext, Decimal) <= max_amount
        )

    if filters:
        query = query.where(and_(*filters))

    query = query.order_by(models.Document.created_at.desc())

    result = await db.execute(query)
    documents = result.scalars().all()

    # Zu Dicts konvertieren
    return [
        {
            "id": doc.id,
            "filename": doc.filename,
            "extracted_data": doc.extracted_data,
        }
        for doc in documents
    ]


@router.get("/export/csv")
async def export_csv(
    document_type: ExtractedDocumentType = Query(
        ExtractedDocumentType.INVOICE,
        description="Dokumenttyp fuer Export"
    ),
    date_from: Optional[date] = Query(None, description="Datum ab (inklusiv)"),
    date_to: Optional[date] = Query(None, description="Datum bis (inklusiv)"),
    min_amount: Optional[Decimal] = Query(None, ge=0, description="Mindestbetrag (brutto)"),
    max_amount: Optional[Decimal] = Query(None, ge=0, description="Maximalbetrag (brutto)"),

    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
) -> Response:
    """
    Exportiert extrahierte Daten als CSV.

    **Format:**
    - Semikolon-getrennt (;) fuer deutsche Excel-Versionen
    - UTF-8 mit BOM fuer korrekte Umlaut-Darstellung
    - Deutsche Spaltennamen

    **Beispiele:**
    - Alle Rechnungen: `?document_type=invoice`
    - Rechnungen 2024: `?document_type=invoice&date_from=2024-01-01&date_to=2024-12-31`
    - Rechnungen > 1000 EUR: `?document_type=invoice&min_amount=1000`
    """
    documents = await _get_documents_for_export(
        db=db,
        user_id=current_user.id,
        document_type=document_type.value,
        date_from=date_from,
        date_to=date_to,
        min_amount=min_amount,
        max_amount=max_amount,
    )

    if not documents:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Dokumente fuer Export gefunden"
        )

    # CSV generieren
    if document_type == ExtractedDocumentType.INVOICE:
        csv_content = export_invoices_csv(documents)
        filename = f"rechnungen_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    elif document_type == ExtractedDocumentType.ORDER:
        csv_content = export_orders_csv(documents)
        filename = f"bestellungen_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    elif document_type == ExtractedDocumentType.CONTRACT:
        csv_content = export_contracts_csv(documents)
        filename = f"vertraege_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Export fuer Dokumenttyp '{document_type.value}' nicht unterstuetzt"
        )

    logger.info(
        "export_csv_generated",
        user_id=str(current_user.id),
        document_type=document_type.value,
        count=len(documents)
    )

    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={
            # SECURITY: Use sanitized Content-Disposition (Phase 10)
            "Content-Disposition": build_content_disposition(filename, "attachment")
        }
    )


@router.get("/export/excel")
async def export_excel(
    document_type: ExtractedDocumentType = Query(
        ExtractedDocumentType.INVOICE,
        description="Dokumenttyp fuer Export"
    ),
    date_from: Optional[date] = Query(None, description="Datum ab (inklusiv)"),
    date_to: Optional[date] = Query(None, description="Datum bis (inklusiv)"),
    min_amount: Optional[Decimal] = Query(None, ge=0, description="Mindestbetrag (brutto)"),
    max_amount: Optional[Decimal] = Query(None, ge=0, description="Maximalbetrag (brutto)"),

    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
) -> Response:
    """
    Exportiert extrahierte Daten als Excel (.xlsx).

    **Features:**
    - Professionelle Formatierung (Header, Spaltenbreiten, Zahlenformate)
    - Autofilter aktiviert
    - Erste Zeile fixiert
    - Deutsche Spaltennamen

    **Beispiele:**
    - Alle Rechnungen: `?document_type=invoice`
    - Alle Bestellungen: `?document_type=order`
    - Alle Vertraege: `?document_type=contract`
    """
    documents = await _get_documents_for_export(
        db=db,
        user_id=current_user.id,
        document_type=document_type.value,
        date_from=date_from,
        date_to=date_to,
        min_amount=min_amount,
        max_amount=max_amount,
    )

    if not documents:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Dokumente fuer Export gefunden"
        )

    # Excel generieren
    if document_type == ExtractedDocumentType.INVOICE:
        excel_content = export_invoices_excel(documents)
        filename = f"rechnungen_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    elif document_type == ExtractedDocumentType.ORDER:
        excel_content = export_orders_excel(documents)
        filename = f"bestellungen_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    elif document_type == ExtractedDocumentType.CONTRACT:
        excel_content = export_contracts_excel(documents)
        filename = f"vertraege_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Export fuer Dokumenttyp '{document_type.value}' nicht unterstuetzt"
        )

    logger.info(
        "export_excel_generated",
        user_id=str(current_user.id),
        document_type=document_type.value,
        count=len(documents)
    )

    return Response(
        content=excel_content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            # SECURITY: Use sanitized Content-Disposition (Phase 10)
            "Content-Disposition": build_content_disposition(filename, "attachment")
        }
    )


@router.get("/export/excel/all")
async def export_all_types_excel(
    date_from: Optional[date] = Query(None, description="Datum ab (inklusiv)"),
    date_to: Optional[date] = Query(None, description="Datum bis (inklusiv)"),

    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
) -> Response:
    """
    Exportiert ALLE Dokumenttypen in eine Excel-Datei mit separaten Tabs.

    **Tabs:**
    - Rechnungen
    - Bestellungen
    - Vertraege

    Ideal fuer Monats-/Jahresabschluesse.
    """
    # Alle Dokumenttypen laden
    invoices = await _get_documents_for_export(
        db=db,
        user_id=current_user.id,
        document_type="invoice",
        date_from=date_from,
        date_to=date_to,
        min_amount=None,
        max_amount=None,
    )

    orders = await _get_documents_for_export(
        db=db,
        user_id=current_user.id,
        document_type="order",
        date_from=date_from,
        date_to=date_to,
        min_amount=None,
        max_amount=None,
    )

    contracts = await _get_documents_for_export(
        db=db,
        user_id=current_user.id,
        document_type="contract",
        date_from=date_from,
        date_to=date_to,
        min_amount=None,
        max_amount=None,
    )

    total_count = len(invoices) + len(orders) + len(contracts)

    if total_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Dokumente fuer Export gefunden"
        )

    # Kombinierte Excel generieren
    excel_content = export_all_excel(invoices, orders, contracts)
    filename = f"dokumente_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    logger.info(
        "export_all_excel_generated",
        user_id=str(current_user.id),
        invoices=len(invoices),
        orders=len(orders),
        contracts=len(contracts)
    )

    return Response(
        content=excel_content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            # SECURITY: Use sanitized Content-Disposition (Phase 10)
            "Content-Disposition": build_content_disposition(filename, "attachment")
        }
    )


# =============================================================================
# EINZELDOKUMENT-ABRUF (MUSS AM ENDE STEHEN - sonst matched {document_id} vor /invoices etc.)
# =============================================================================

@router.get("/detail/{document_id}", response_model=ExtractedDocumentData)
async def get_extracted_data_by_id(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
) -> ExtractedDocumentData:
    """
    Liefert alle extrahierten Daten eines Dokuments.

    **Returns:**
    - Klassifizierung (Dokumenttyp + Konfidenz)
    - Typspezifische Daten (Invoice/Order/Contract)
    - Allgemeine Entities (IBANs, USt-IDs, Firmen)
    """
    # Dokument laden
    result = await db.execute(
        select(models.Document).where(
            and_(
                models.Document.id == document_id,
                models.Document.owner_id == current_user.id,
                models.Document.deleted_at.is_(None)
            )
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden"
        )

    if not document.extracted_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine strukturierten Daten fuer dieses Dokument verfuegbar"
        )

    # JSONB zu Pydantic konvertieren
    try:
        return ExtractedDocumentData.model_validate(document.extracted_data)
    except Exception as e:
        logger.error(
            "extracted_data_parse_error",
            document_id=str(document_id),
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Parsen der extrahierten Daten"
        )
