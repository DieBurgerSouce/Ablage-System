# -*- coding: utf-8 -*-
"""
E-Invoice Tasks - Celery Tasks fuer E-Rechnungsverarbeitung.

Tasks:
- zugferd_batch_convert_task: Batch-Konvertierung zu ZUGFeRD
- zugferd_embed_task: XML in einzelnes PDF embedden
- xrechnung_generate_task: XRechnung XML generieren
- einvoice_validate_task: E-Rechnung validieren
"""

import io
import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

import structlog
from celery import states
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.workers.celery_app import celery_app, CPUTask
from app.core.config import settings
from app.core.safe_errors import safe_error_log, safe_error_detail
from app.db.session import get_async_session_context
from app.db.models import Document, EInvoiceDocument

logger = structlog.get_logger(__name__)


# =============================================================================
# ZUGFERD BATCH CONVERT TASK
# =============================================================================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="einvoice.batch_convert",
    queue="default",
    max_retries=2,
    soft_time_limit=1800,  # 30 min
    time_limit=2100,  # 35 min
    acks_late=True,
)
def zugferd_batch_convert_task(
    self,
    document_ids: List[str],
    user_id: str,
    profile: str = "EN16931",
    overwrite_existing: bool = False,
) -> dict:
    """
    Konvertiert mehrere Dokumente zu ZUGFeRD-PDFs.

    Args:
        document_ids: Liste der Dokument-UUIDs (muessen PDFs sein)
        user_id: User-UUID fuer Berechtigungspruefung
        profile: ZUGFeRD-Profil (MINIMUM, BASIC, EN16931, EXTENDED, XRECHNUNG)
        overwrite_existing: Bestehende ZUGFeRD-Daten ueberschreiben

    Returns:
        dict mit:
        - success: bool
        - converted: Anzahl erfolgreich konvertierter Dokumente
        - failed: Anzahl fehlgeschlagener Dokumente
        - errors: Liste mit Fehlern
        - results: Liste mit Ergebnis-Details pro Dokument
    """
    import asyncio

    async def _do_convert():
        async with get_async_session_context() as db:
            return await _execute_batch_convert(
                db=db,
                document_ids=[UUID(doc_id) for doc_id in document_ids],
                user_id=UUID(user_id),
                profile=profile,
                overwrite_existing=overwrite_existing,
                task=self,
            )

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_do_convert())
        loop.close()
        return result

    except Exception as e:
        logger.error("zugferd_batch_convert_failed", **safe_error_log(e))
        return {
            "success": False,
            "error": safe_error_detail(e, "Konvertierung"),
            "converted": 0,
            "failed": len(document_ids),
            "errors": [],
            "results": [],
        }


async def _execute_batch_convert(
    db: AsyncSession,
    document_ids: List[UUID],
    user_id: UUID,
    profile: str,
    overwrite_existing: bool,
    task,
) -> dict:
    """Fuehrt die Batch-Konvertierung aus."""
    from app.services.einvoice import get_zugferd_embedder, ZUGFeRDProfile
    from app.services.storage_service import get_storage_service
    from uuid import uuid4
    import hashlib

    embedder = get_zugferd_embedder()
    storage = get_storage_service()

    if not embedder.available:
        return {
            "success": False,
            "error": "PDF-Backend (PyMuPDF/pikepdf) nicht verfuegbar",
            "converted": 0,
            "failed": len(document_ids),
            "errors": [],
            "results": [],
        }

    # Profile validieren
    try:
        zugferd_profile = ZUGFeRDProfile(profile)
    except ValueError:
        return {
            "success": False,
            "error": f"Ungueltiges Profil: {profile}",
            "converted": 0,
            "failed": len(document_ids),
            "errors": [],
            "results": [],
        }

    # Dokumente laden
    query = select(Document).where(
        Document.id.in_(document_ids),
        Document.owner_id == user_id,
        Document.deleted_at.is_(None)
    )
    result = await db.execute(query)
    documents = result.scalars().all()

    if not documents:
        return {
            "success": False,
            "error": "Keine Dokumente gefunden oder keine Berechtigung",
            "converted": 0,
            "failed": len(document_ids),
            "errors": [],
            "results": [],
        }

    converted = 0
    failed = 0
    errors: List[dict] = []
    results: List[dict] = []
    total = len(documents)

    for i, doc in enumerate(documents):
        doc_result = {
            "document_id": str(doc.id),
            "filename": doc.original_filename or doc.filename,
            "success": False,
            "einvoice_id": None,
            "error": None,
        }

        try:
            # Progress Update
            task.update_state(
                state=states.STARTED,
                meta={
                    "current": i + 1,
                    "total": total,
                    "status": f"Konvertiere {doc.original_filename or doc.filename}..."
                }
            )

            # Nur PDFs
            if not doc.mime_type or "pdf" not in doc.mime_type.lower():
                doc_result["error"] = "Kein PDF-Dokument"
                failed += 1
                errors.append({
                    "document_id": str(doc.id),
                    "error": "Kein PDF-Dokument"
                })
                results.append(doc_result)
                continue

            # Pruefen ob bereits E-Invoice existiert
            existing_query = select(EInvoiceDocument).where(
                EInvoiceDocument.document_id == doc.id
            )
            existing_result = await db.execute(existing_query)
            existing_einvoice = existing_result.scalar_one_or_none()

            if existing_einvoice and not overwrite_existing:
                doc_result["error"] = "E-Invoice existiert bereits"
                doc_result["einvoice_id"] = str(existing_einvoice.id)
                failed += 1
                errors.append({
                    "document_id": str(doc.id),
                    "error": "E-Invoice existiert bereits (overwrite=False)"
                })
                results.append(doc_result)
                continue

            # PDF aus Storage laden
            pdf_content = await storage.get_document(doc.file_path)
            if not pdf_content:
                doc_result["error"] = "PDF nicht im Storage gefunden"
                failed += 1
                errors.append({
                    "document_id": str(doc.id),
                    "error": "PDF nicht im Storage gefunden"
                })
                results.append(doc_result)
                continue

            # XML generieren aus extracted_data
            xml_content = _generate_zugferd_xml(doc, zugferd_profile)
            if not xml_content:
                doc_result["error"] = "XML-Generierung fehlgeschlagen (keine Rechnungsdaten)"
                failed += 1
                errors.append({
                    "document_id": str(doc.id),
                    "error": "Keine Rechnungsdaten fuer XML-Generierung"
                })
                results.append(doc_result)
                continue

            # XML in PDF embedden
            embedded_pdf, metadata = embedder.embed_xml_in_pdf(
                pdf_content=pdf_content,
                xml_content=xml_content,
                profile=zugferd_profile,
                use_facturx_name=True,
            )

            # Neues PDF speichern
            new_filename = f"zugferd_{doc.id}.pdf"
            new_path = f"zugferd/{user_id}/{new_filename}"

            await storage.upload_document(
                file_data=embedded_pdf,
                filename=new_filename,
                content_type="application/pdf",
                user_id=str(user_id),
                metadata={
                    "original_document_id": str(doc.id),
                    "zugferd_profile": profile,
                }
            )

            # EInvoiceDocument erstellen oder aktualisieren
            if existing_einvoice:
                existing_einvoice.format = "zugferd"
                existing_einvoice.profile = profile
                existing_einvoice.version = "2.3"
                existing_einvoice.xml_content = xml_content
                existing_einvoice.xml_hash = hashlib.sha256(xml_content.encode()).hexdigest()
                existing_einvoice.was_generated = True
                existing_einvoice.updated_at = datetime.now(timezone.utc)
                einvoice_id = existing_einvoice.id
            else:
                einvoice_id = uuid4()
                new_einvoice = EInvoiceDocument(
                    id=einvoice_id,
                    document_id=doc.id,
                    format="zugferd",
                    profile=profile,
                    version="2.3",
                    xml_content=xml_content,
                    xml_hash=hashlib.sha256(xml_content.encode()).hexdigest(),
                    was_extracted=False,
                    was_generated=True,
                    source_filename=doc.original_filename,
                    extraction_method="generated",
                )
                db.add(new_einvoice)

            # Document Metadaten aktualisieren
            doc.document_metadata = doc.document_metadata or {}
            doc.document_metadata["zugferd"] = {
                "profile": profile,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "file_path": new_path,
            }

            await db.commit()

            doc_result["success"] = True
            doc_result["einvoice_id"] = str(einvoice_id)
            converted += 1

            logger.info(
                "zugferd_document_converted",
                document_id=str(doc.id),
                einvoice_id=str(einvoice_id),
                profile=profile,
            )

        except Exception as e:
            doc_result["error"] = safe_error_detail(e, "Konvertierung")
            failed += 1
            errors.append({
                "document_id": str(doc.id),
                "error": safe_error_detail(e, "Konvertierung")
            })
            logger.warning(
                "zugferd_convert_document_failed",
                document_id=str(doc.id),
                **safe_error_log(e)
            )

        results.append(doc_result)

    return {
        "success": failed == 0,
        "converted": converted,
        "failed": failed,
        "total": total,
        "errors": errors,
        "results": results,
        "profile": profile,
    }


def _generate_zugferd_xml(doc: Document, profile) -> Optional[str]:
    """
    Generiert ZUGFeRD XML aus Dokument-Daten.

    Verwendet factur-x wenn verfuegbar, sonst manuelles Template.
    """
    extracted = doc.extracted_data or {}

    # Minimal erforderliche Daten pruefen
    invoice_number = extracted.get("invoice_number") or extracted.get("rechnungsnummer")
    if not invoice_number:
        return None

    # Betraege extrahieren
    total_amount = extracted.get("total_amount") or extracted.get("gesamtbetrag") or "0.00"
    tax_amount = extracted.get("tax_amount") or extracted.get("mwst_betrag") or "0.00"
    net_amount = extracted.get("net_amount") or extracted.get("nettobetrag") or str(
        float(str(total_amount).replace(",", ".")) - float(str(tax_amount).replace(",", "."))
    )

    # Datum
    invoice_date = extracted.get("invoice_date") or extracted.get("rechnungsdatum")
    if not invoice_date:
        invoice_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Versuche factur-x zu verwenden
    try:
        from facturx import generate_from_file
        # factur-x braucht strukturierte Daten - hier nur Basic-Template

    except ImportError:
        pass

    # Manuelles ZUGFeRD XML Template (Minimal-Version)
    xml_template = f'''<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice
    xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
    xmlns:qdt="urn:un:unece:uncefact:data:standard:QualifiedDataType:100"
    xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
    xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100">

    <rsm:ExchangedDocumentContext>
        <ram:GuidelineSpecifiedDocumentContextParameter>
            <ram:ID>urn:cen.eu:en16931:2017</ram:ID>
        </ram:GuidelineSpecifiedDocumentContextParameter>
    </rsm:ExchangedDocumentContext>

    <rsm:ExchangedDocument>
        <ram:ID>{invoice_number}</ram:ID>
        <ram:TypeCode>380</ram:TypeCode>
        <ram:IssueDateTime>
            <udt:DateTimeString format="102">{invoice_date.replace("-", "")[:8]}</udt:DateTimeString>
        </ram:IssueDateTime>
    </rsm:ExchangedDocument>

    <rsm:SupplyChainTradeTransaction>
        <ram:ApplicableHeaderTradeAgreement>
            <ram:SellerTradeParty>
                <ram:Name>{extracted.get("supplier_name", "Lieferant")}</ram:Name>
            </ram:SellerTradeParty>
            <ram:BuyerTradeParty>
                <ram:Name>{extracted.get("customer_name", "Kunde")}</ram:Name>
            </ram:BuyerTradeParty>
        </ram:ApplicableHeaderTradeAgreement>

        <ram:ApplicableHeaderTradeDelivery/>

        <ram:ApplicableHeaderTradeSettlement>
            <ram:InvoiceCurrencyCode>EUR</ram:InvoiceCurrencyCode>
            <ram:SpecifiedTradeSettlementHeaderMonetarySummation>
                <ram:LineTotalAmount>{net_amount}</ram:LineTotalAmount>
                <ram:TaxTotalAmount currencyID="EUR">{tax_amount}</ram:TaxTotalAmount>
                <ram:GrandTotalAmount>{total_amount}</ram:GrandTotalAmount>
                <ram:DuePayableAmount>{total_amount}</ram:DuePayableAmount>
            </ram:SpecifiedTradeSettlementHeaderMonetarySummation>
        </ram:ApplicableHeaderTradeSettlement>
    </rsm:SupplyChainTradeTransaction>

</rsm:CrossIndustryInvoice>'''

    return xml_template


# =============================================================================
# SINGLE EMBED TASK
# =============================================================================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="einvoice.embed_xml",
    queue="default",
    max_retries=2,
)
def zugferd_embed_task(
    self,
    document_id: str,
    xml_content: str,
    profile: str = "EN16931",
) -> dict:
    """
    Embeddet XML in ein einzelnes PDF.

    Args:
        document_id: Dokument-UUID
        xml_content: ZUGFeRD XML als String
        profile: ZUGFeRD-Profil

    Returns:
        dict mit Ergebnis
    """
    import asyncio

    async def _do_embed():
        async with get_async_session_context() as db:
            from app.services.einvoice import get_zugferd_embedder, ZUGFeRDProfile
            from app.services.storage_service import get_storage_service
            import hashlib
            from uuid import uuid4

            embedder = get_zugferd_embedder()
            storage = get_storage_service()

            if not embedder.available:
                return {"success": False, "error": "PDF-Backend nicht verfuegbar"}

            # Dokument laden
            query = select(Document).where(Document.id == UUID(document_id))
            result = await db.execute(query)
            doc = result.scalar_one_or_none()

            if not doc:
                return {"success": False, "error": "Dokument nicht gefunden"}

            # PDF laden
            pdf_content = await storage.get_document(doc.file_path)
            if not pdf_content:
                return {"success": False, "error": "PDF nicht im Storage"}

            # Embedden
            try:
                zugferd_profile = ZUGFeRDProfile(profile)
            except ValueError:
                return {"success": False, "error": f"Ungueltiges Profil: {profile}"}

            embedded_pdf, metadata = embedder.embed_xml_in_pdf(
                pdf_content=pdf_content,
                xml_content=xml_content,
                profile=zugferd_profile,
            )

            # Speichern
            new_filename = f"zugferd_{document_id}.pdf"
            await storage.upload_document(
                file_data=embedded_pdf,
                filename=new_filename,
                content_type="application/pdf",
                user_id=str(doc.owner_id),
                metadata={"zugferd_profile": profile}
            )

            # EInvoiceDocument erstellen
            einvoice_id = uuid4()
            new_einvoice = EInvoiceDocument(
                id=einvoice_id,
                document_id=doc.id,
                format="zugferd",
                profile=profile,
                version="2.3",
                xml_content=xml_content,
                xml_hash=hashlib.sha256(xml_content.encode()).hexdigest(),
                was_extracted=False,
                was_generated=True,
            )
            db.add(new_einvoice)
            await db.commit()

            return {
                "success": True,
                "einvoice_id": str(einvoice_id),
                "profile": profile,
                "xml_hash": metadata["xml_hash"],
            }

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_do_embed())
        loop.close()
        return result

    except Exception as e:
        logger.error("zugferd_embed_failed", **safe_error_log(e))
        return {"success": False, "error": safe_error_detail(e, "Embedding")}


# =============================================================================
# VALIDATION TASK
# =============================================================================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="einvoice.validate",
    queue="default",
    max_retries=1,
)
def einvoice_validate_task(
    self,
    document_id: str,
    validator_type: str = "auto",
) -> dict:
    """
    Validiert eine E-Rechnung asynchron.

    Args:
        document_id: Dokument-UUID
        validator_type: "facturx", "kosit", "mustang" oder "auto"

    Returns:
        dict mit Validierungsergebnis
    """
    import asyncio

    async def _do_validate():
        async with get_async_session_context() as db:
            from app.services.einvoice import get_validator_service, ValidatorType

            validator = get_validator_service()

            # EInvoiceDocument laden
            query = select(EInvoiceDocument).where(
                EInvoiceDocument.document_id == UUID(document_id)
            )
            result = await db.execute(query)
            einvoice_doc = result.scalar_one_or_none()

            if not einvoice_doc or not einvoice_doc.xml_content:
                return {"success": False, "error": "Keine E-Invoice gefunden"}

            # Validator-Typ bestimmen
            v_type = ValidatorType.AUTO
            if validator_type == "facturx":
                v_type = ValidatorType.FACTURX
            elif validator_type == "kosit":
                v_type = ValidatorType.KOSIT
            elif validator_type == "mustang":
                v_type = ValidatorType.MUSTANG

            # Validieren
            validation_result = await validator.validate_xml(
                einvoice_doc.xml_content,
                v_type
            )

            # Ergebnis speichern
            einvoice_doc.is_valid = validation_result.valid
            einvoice_doc.validation_errors = [
                {"code": m.code, "message": m.message, "location": m.location}
                for m in validation_result.messages
                if m.severity.value in ("fatal", "error")
            ]
            einvoice_doc.last_validated_at = datetime.now(timezone.utc)
            await db.commit()

            return {
                "success": True,
                "valid": validation_result.valid,
                "error_count": validation_result.error_count,
                "warning_count": validation_result.warning_count,
                "validator_used": validation_result.validator_used,
            }

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_do_validate())
        loop.close()
        return result

    except Exception as e:
        logger.error("einvoice_validate_failed", **safe_error_log(e))
        return {"success": False, "error": safe_error_detail(e, "Validierung")}


# =============================================================================
# BEAT SCHEDULE
# =============================================================================

EINVOICE_BEAT_SCHEDULE = {
    # Keine periodischen Tasks fuer E-Invoice aktuell
}
