"""Document Classification Workflow Task Implementations.

Service Tasks fuer den Dokumenten-Klassifizierungs-Workflow.
Diese Funktionen werden von der BPMN Engine aufgerufen.

Enterprise-Grade: Echte OCR/Classifier/Entity-Integration statt Platzhalter.
"""

from typing import Dict, Any, List, Optional
from uuid import UUID
from datetime import datetime, timezone
import structlog

from sqlalchemy import select

logger = structlog.get_logger(__name__)


async def extract_document_text(
    instance_id: str,
    variables: Dict[str, Any]
) -> Dict[str, Any]:
    """Extrahiert Text aus dem Dokument via OCR.

    Args:
        instance_id: BPMN Prozess-Instanz ID
        variables: Prozess-Variablen (document_id, file_path, etc.)

    Returns:
        Extrahierter Text und Metadaten
    """
    from app.db.session import async_session_maker
    from app.db.models.bpmn import ProcessHistory

    document_id = variables.get("document_id")
    file_path = variables.get("file_path", "")
    ocr_backend = variables.get("ocr_backend", "auto")

    logger.info(
        "extracting_document_text",
        instance_id=instance_id,
        document_id=document_id,
        ocr_backend=ocr_backend
    )

    # Echte OCR-Verarbeitung via OCRService
    from app.services.ocr_service import OCRService
    from app.services.storage_service import StorageService
    from app.db.models import Document

    extracted_text = ""
    confidence = 0.0
    page_count = 1
    ocr_error: Optional[str] = None

    # Input-Validierung
    if not document_id:
        ocr_error = "Keine document_id angegeben"
        logger.error("ocr_missing_document_id", instance_id=instance_id)
        return {
            "text_extracted": False,
            "extracted_text": "",
            "ocr_confidence": 0.0,
            "page_count": 0,
            "ocr_backend_used": ocr_backend,
            "ocr_error": ocr_error,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
        }

    company_id = variables.get("company_id")
    if not company_id:
        ocr_error = "Keine company_id fuer Multi-Tenant-Isolation"
        logger.error("ocr_missing_company_id", instance_id=instance_id)
        return {
            "text_extracted": False,
            "extracted_text": "",
            "ocr_confidence": 0.0,
            "page_count": 0,
            "ocr_backend_used": ocr_backend,
            "ocr_error": ocr_error,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
        }

    try:
        async with async_session_maker() as db_session:
            # Dokument aus DB laden MIT company_id Filter (Multi-Tenant RLS!)
            result = await db_session.execute(
                select(Document).where(
                    Document.id == UUID(str(document_id)),
                    Document.company_id == UUID(str(company_id)),  # KRITISCH: Multi-Tenant!
                )
            )
            doc = result.scalar_one_or_none()

            if doc and doc.file_path:
                # Datei aus Storage herunterladen in temporaeres Verzeichnis
                import tempfile
                import os

                storage = StorageService()
                document_bytes = await storage.download_document(doc.file_path)

                # Temporaere Datei erstellen
                suffix = os.path.splitext(doc.file_path)[1] or ".pdf"
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
                    tmp_file.write(document_bytes)
                    local_path = tmp_file.name

                if local_path and os.path.exists(local_path):
                    # OCR durchfuehren
                    ocr_service = OCRService(enable_german_correction=True)
                    backend_to_use = ocr_backend if ocr_backend != "auto" else None

                    ocr_result = await ocr_service.process_document(
                        image_path=str(local_path),
                        backend=backend_to_use,
                        language="de",
                        detect_layout=True
                    )

                    extracted_text = ocr_result.get("text", "")
                    confidence = ocr_result.get("confidence", 0.85)
                    page_count = ocr_result.get("page_count", 1)
                    ocr_backend = ocr_result.get("backend_used", ocr_backend)

                    logger.info(
                        "ocr_extraction_completed",
                        document_id=document_id,
                        text_length=len(extracted_text),
                        confidence=confidence,
                        backend=ocr_backend
                    )

                    # Temporaere Datei aufraeumen
                    try:
                        os.unlink(local_path)
                    except Exception:
                        pass
                else:
                    ocr_error = "Datei nicht im Storage gefunden"
                    logger.warning("ocr_file_not_found", document_id=document_id)
            else:
                ocr_error = "Dokument nicht in DB gefunden"
                logger.warning("ocr_document_not_found", document_id=document_id)

    except Exception as e:
        ocr_error = str(e)
        logger.error(
            "ocr_extraction_failed",
            document_id=document_id,
            error=str(e)
        )
        # Fallback auf leeren Text, damit Workflow weiterlaufen kann
        extracted_text = ""
        confidence = 0.0

    async with async_session_maker() as db:
        history = ProcessHistory(
            instance_id=UUID(instance_id),
            event_type="TEXT_EXTRACTED",
            message=f"Text extrahiert ({page_count} Seiten, Confidence: {confidence:.0%})",
            actor_type="system",
            company_id=UUID(str(company_id)),  # Bereits validiert
            timestamp=datetime.now(timezone.utc)
        )
        db.add(history)
        await db.commit()

    return {
        "text_extracted": bool(extracted_text),
        "extracted_text": extracted_text,
        "ocr_confidence": confidence,
        "page_count": page_count,
        "ocr_backend_used": ocr_backend,
        "ocr_error": ocr_error,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
    }


async def classify_document(
    instance_id: str,
    variables: Dict[str, Any]
) -> Dict[str, Any]:
    """Klassifiziert das Dokument mittels KI.

    Bestimmt Dokumenttyp und extrahiert strukturierte Daten.

    Args:
        instance_id: BPMN Prozess-Instanz ID
        variables: Prozess-Variablen

    Returns:
        Klassifizierungsergebnis
    """
    from app.db.session import async_session_maker
    from app.db.models.bpmn import ProcessHistory

    document_id = variables.get("document_id")
    extracted_text = variables.get("extracted_text", "")

    # Input-Validierung (Multi-Tenant!)
    company_id = variables.get("company_id")
    if not document_id:
        logger.error("classify_missing_document_id", instance_id=instance_id)
        return {
            "classified": False,
            "document_type": "other",
            "classification_confidence": 0.0,
            "needs_review": True,
            "error": "Keine document_id angegeben",
            "classified_at": datetime.now(timezone.utc).isoformat(),
        }
    if not company_id:
        logger.error("classify_missing_company_id", instance_id=instance_id)
        return {
            "classified": False,
            "document_type": "other",
            "classification_confidence": 0.0,
            "needs_review": True,
            "error": "Keine company_id fuer Multi-Tenant-Isolation",
            "classified_at": datetime.now(timezone.utc).isoformat(),
        }

    logger.info(
        "classifying_document",
        instance_id=instance_id,
        document_id=document_id
    )

    # Echte KI-basierte Klassifizierung via QuickClassificationService
    from app.services.quick_classification_service import (
        QuickClassificationService,
        get_quick_classification_service
    )
    from app.api.schemas.extracted_data import InvoiceDirection

    document_type = "other"
    confidence = 0.0
    classification_details: Dict[str, Any] = {}

    try:
        async with async_session_maker() as db_session:
            classifier = get_quick_classification_service()

            # QuickClassificationService nutzen fuer Richtungserkennung
            classification_result = await classifier.classify_document(
                document_id=UUID(str(document_id)),
                ocr_text=extracted_text,
                db=db_session,
                auto_assign_tag=False  # Wir assignen Tags in einem spaeteren Schritt
            )

            # Ergebnis auswerten
            confidence = classification_result.confidence

            # Dokumenttyp basierend auf Direction und Keywords bestimmen
            if classification_result.direction == InvoiceDirection.INCOMING:
                document_type = "invoice"
            elif classification_result.direction == InvoiceDirection.OUTGOING:
                document_type = "outgoing_invoice"
            else:
                # Fallback: Keyword-basierte Klassifizierung
                text_lower = extracted_text.lower()
                if "rechnung" in text_lower or "invoice" in text_lower:
                    document_type = "invoice"
                    confidence = max(confidence, 0.70)
                elif "angebot" in text_lower or "quotation" in text_lower:
                    document_type = "quote"
                    confidence = max(confidence, 0.70)
                elif "lieferschein" in text_lower or "delivery" in text_lower:
                    document_type = "delivery_note"
                    confidence = max(confidence, 0.70)
                elif "vertrag" in text_lower or "contract" in text_lower:
                    document_type = "contract"
                    confidence = max(confidence, 0.65)
                elif "mahnung" in text_lower or "reminder" in text_lower:
                    document_type = "dunning_notice"
                    confidence = max(confidence, 0.75)
                else:
                    document_type = "other"
                    confidence = 0.50

            classification_details = {
                "direction": classification_result.direction.value if hasattr(classification_result.direction, 'value') else str(classification_result.direction),
                "reason": classification_result.reason,
                "matched_entity_id": str(classification_result.matched_entity_id) if classification_result.matched_entity_id else None,
                "matched_entity_name": classification_result.matched_entity_name,
                "rename_suggestion": classification_result.rename_suggestion,
            }

            logger.info(
                "classification_completed",
                document_id=document_id,
                document_type=document_type,
                confidence=confidence,
                direction=classification_details.get("direction")
            )

    except Exception as e:
        logger.error(
            "classification_failed",
            document_id=document_id,
            error=str(e)
        )
        # Fallback auf Keyword-basierte Klassifizierung
        text_lower = extracted_text.lower()
        if "rechnung" in text_lower:
            document_type = "invoice"
            confidence = 0.60
        elif "angebot" in text_lower:
            document_type = "quote"
            confidence = 0.55
        else:
            document_type = "other"
            confidence = 0.40

    # Threshold fuer automatische Verarbeitung
    auto_threshold = 0.85
    needs_review = confidence < auto_threshold

    async with async_session_maker() as db:
        history = ProcessHistory(
            instance_id=UUID(instance_id),
            event_type="DOCUMENT_CLASSIFIED",
            message=f"Dokument klassifiziert: {document_type} (Confidence: {confidence:.0%})",
            actor_type="system",
            company_id=UUID(str(company_id)),  # Bereits validiert
            timestamp=datetime.now(timezone.utc)
        )
        db.add(history)
        await db.commit()

    return {
        "classified": True,
        "document_type": document_type,
        "classification_confidence": confidence,
        "needs_review": needs_review,
        "auto_threshold": auto_threshold,
        "classification_details": classification_details,
        "classified_at": datetime.now(timezone.utc).isoformat(),
    }


async def extract_entities(
    instance_id: str,
    variables: Dict[str, Any]
) -> Dict[str, Any]:
    """Extrahiert Entitaeten aus dem Dokument.

    Erkennt Firmen, Betraege, Daten, etc.

    Args:
        instance_id: BPMN Prozess-Instanz ID
        variables: Prozess-Variablen

    Returns:
        Extrahierte Entitaeten
    """
    from app.db.session import async_session_maker
    from app.db.models.bpmn import ProcessHistory

    document_id = variables.get("document_id")
    document_type = variables.get("document_type", "other")
    extracted_text = variables.get("extracted_text", "")

    # Input-Validierung (Multi-Tenant!)
    company_id = variables.get("company_id")
    if not document_id:
        logger.error("extract_entities_missing_document_id", instance_id=instance_id)
        return {
            "entities_extracted": False,
            "entities": {},
            "entity_count": 0,
            "error": "Keine document_id angegeben",
            "extracted_at": datetime.now(timezone.utc).isoformat(),
        }
    if not company_id:
        logger.error("extract_entities_missing_company_id", instance_id=instance_id)
        return {
            "entities_extracted": False,
            "entities": {},
            "entity_count": 0,
            "error": "Keine company_id fuer Multi-Tenant-Isolation",
            "extracted_at": datetime.now(timezone.utc).isoformat(),
        }

    logger.info(
        "extracting_entities",
        instance_id=instance_id,
        document_id=document_id,
        document_type=document_type
    )

    # Echte Entity-Extraktion via Pattern-Matching
    # HINWEIS: Wir nutzen eigene Regex-Pattern statt private Methoden des Classifiers
    import re

    entities: Dict[str, Any] = {}
    extraction_confidence = 0.0

    try:
        # VAT-IDs extrahieren (deutsches und EU-Format)
        # Pattern: DE + 9 Ziffern oder andere EU-Laendercodes + Ziffern
        vat_pattern = re.compile(
            r'\b(DE\d{9}|AT[U]\d{8}|CH[E]?\d{9}|[A-Z]{2}\d{8,12})\b'
        )
        vat_matches = vat_pattern.findall(extracted_text)
        if vat_matches:
            entities["vendor_vat_id"] = vat_matches[0]
            extraction_confidence = max(extraction_confidence, 0.90)

        # IBANs extrahieren (DE-Format + international)
        iban_pattern = re.compile(
            r'\b([A-Z]{2}\d{2}[A-Z0-9]{4,30})\b'
        )
        iban_matches = iban_pattern.findall(extracted_text)
        if iban_matches:
            # Einfache IBAN-Validierung: Mindestlaenge 15 (z.B. NO)
            valid_ibans = [iban for iban in iban_matches if len(iban) >= 15]
            if valid_ibans:
                entities["iban"] = valid_ibans[0]
                extraction_confidence = max(extraction_confidence, 0.85)

        # Firmennamen extrahieren (GmbH, AG, etc.)
        company_pattern = re.compile(
            r'([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)*\s+'
            r'(?:GmbH|AG|KG|OHG|e\.?K\.?|GbR|SE|UG|Ltd|Inc|Corp)\.?)',
            re.UNICODE
        )
        company_matches = company_pattern.findall(extracted_text)
        if company_matches:
            entities["vendor_name"] = company_matches[0].strip()
            extraction_confidence = max(extraction_confidence, 0.75)

        # Rechnungsnummer extrahieren
        invoice_pattern = re.compile(
            r'(?:Rechnungs?-?Nr\.?|Invoice\s*(?:No\.?|Number)?|RE-?Nr\.?)'
            r'[:\s]*([A-Za-z0-9\-_/]+)',
            re.IGNORECASE
        )
        invoice_match = invoice_pattern.search(extracted_text)
        if invoice_match:
            entities["invoice_number"] = invoice_match.group(1).strip()
            extraction_confidence = max(extraction_confidence, 0.85)

        # Datum-Patterns (deutsches Format: DD.MM.YYYY)
        date_patterns = [
            (r'(?:Rechnungsdatum|Datum)[:\s]*(\d{2}\.\d{2}\.\d{4})', 'invoice_date'),
            (r'(?:F[aä]llig(?:keit)?|Zahlbar bis)[:\s]*(\d{2}\.\d{2}\.\d{4})', 'due_date'),
            (r'(?:Angebotsdatum|Datum)[:\s]*(\d{2}\.\d{2}\.\d{4})', 'quote_date'),
            (r'(?:G[uü]ltig bis|Angebot g[uü]ltig)[:\s]*(\d{2}\.\d{2}\.\d{4})', 'valid_until'),
        ]
        for pattern, field_name in date_patterns:
            match = re.search(pattern, extracted_text, re.IGNORECASE)
            if match:
                entities[field_name] = match.group(1)

        # Betrags-Patterns (Euro-Betraege)
        amount_patterns = [
            (r'(?:Brutto|Gesamtbetrag|Rechnungsbetrag)[:\s]*(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})\s*(?:EUR|€)?', 'gross_amount'),
            (r'(?:Netto|Nettobetrag)[:\s]*(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})\s*(?:EUR|€)?', 'net_amount'),
            (r'(?:MwSt|USt|Mehrwertsteuer)[:\s]*(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})\s*(?:EUR|€)?', 'vat_amount'),
            (r'(\d{1,2})[,.]?0?\s*%\s*(?:MwSt|USt|Mehrwertsteuer)', 'vat_rate'),
        ]
        for pattern, field_name in amount_patterns:
            match = re.search(pattern, extracted_text, re.IGNORECASE)
            if match:
                value = match.group(1)
                # Betrag normalisieren (1.234,56 -> 1234.56)
                if field_name != 'vat_rate':
                    value = value.replace('.', '').replace(',', '.')
                    try:
                        entities[field_name] = float(value)
                    except ValueError:
                        pass
                else:
                    try:
                        entities[field_name] = float(value.replace(',', '.'))
                    except ValueError:
                        pass

        # Dokumenttyp-spezifische Felder
        if document_type == "quote" and "quote_number" not in entities:
            quote_match = re.search(r'(?:Angebots?-?Nr\.?|Angebot\s*Nr\.?)[:\s]*([A-Za-z0-9\-_/]+)', extracted_text, re.IGNORECASE)
            if quote_match:
                entities["quote_number"] = quote_match.group(1).strip()

        logger.info(
            "entity_extraction_completed",
            document_id=document_id,
            entity_count=len(entities),
            confidence=extraction_confidence
        )

    except Exception as e:
        logger.error(
            "entity_extraction_failed",
            document_id=document_id,
            error=str(e)
        )

    entity_count = len(entities)

    async with async_session_maker() as db:
        history = ProcessHistory(
            instance_id=UUID(instance_id),
            event_type="ENTITIES_EXTRACTED",
            message=f"{entity_count} Entitaeten extrahiert",
            actor_type="system",
            company_id=UUID(str(company_id)),  # Bereits validiert
            timestamp=datetime.now(timezone.utc)
        )
        db.add(history)
        await db.commit()

    return {
        "entities_extracted": True,
        "entities": entities,
        "entity_count": entity_count,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
    }


async def match_business_entity(
    instance_id: str,
    variables: Dict[str, Any]
) -> Dict[str, Any]:
    """Ordnet das Dokument einem Geschaeftspartner zu.

    Verwendet verschiedene Matching-Strategien.

    Args:
        instance_id: BPMN Prozess-Instanz ID
        variables: Prozess-Variablen

    Returns:
        Matching-Ergebnis
    """
    from app.db.session import async_session_maker
    from app.db.models.bpmn import ProcessHistory

    document_id = variables.get("document_id")
    entities = variables.get("entities", {})

    # Input-Validierung (Multi-Tenant!)
    company_id = variables.get("company_id")
    if not company_id:
        logger.error("entity_matching_missing_company_id", instance_id=instance_id)
        return {
            "entity_matched": False,
            "match_confidence": 0.0,
            "match_strategy": "none",
            "matched_entity_id": None,
            "matched_entity_name": None,
            "error": "Keine company_id fuer Multi-Tenant-Isolation",
            "matched_at": datetime.now(timezone.utc).isoformat(),
        }

    logger.info(
        "matching_business_entity",
        instance_id=instance_id,
        document_id=document_id
        # WICHTIG: KEINE PII (VAT-IDs, IBANs) loggen!
    )

    # Echtes Entity-Matching via EntitySearchService
    from app.services.entity_search_service import EntitySearchService

    vendor_name = entities.get("vendor_name", "")
    vendor_vat_id = entities.get("vendor_vat_id", "")
    vendor_iban = entities.get("iban", "")

    entity_matched = False
    match_confidence = 0.0
    match_strategy = "none"
    matched_entity_id: Optional[str] = None
    matched_entity_name: Optional[str] = None

    try:
        async with async_session_maker() as db_session:
            search_service = EntitySearchService(db_session)

            # Prioritaet 1: VAT-ID Matching (hoechste Praezision)
            if vendor_vat_id:
                entity = await search_service.find_by_vat_id(vendor_vat_id)
                if entity:
                    entity_matched = True
                    match_confidence = 0.95
                    match_strategy = "vat_id"
                    matched_entity_id = str(entity.id)
                    matched_entity_name = entity.display_name or entity.name
                    # WICHTIG: VAT-ID NIEMALS loggen (PII-Compliance!)
                    logger.info(
                        "entity_matched_by_vat",
                        entity_id=matched_entity_id,
                        strategy="vat_id"
                    )

            # Prioritaet 2: IBAN Matching
            if not entity_matched and vendor_iban:
                entity = await search_service.find_by_iban(vendor_iban)
                if entity:
                    entity_matched = True
                    match_confidence = 0.90
                    match_strategy = "iban"
                    matched_entity_id = str(entity.id)
                    matched_entity_name = entity.display_name or entity.name
                    # WICHTIG: IBAN NIEMALS loggen (PII-Compliance!)
                    logger.info(
                        "entity_matched_by_iban",
                        entity_id=matched_entity_id,
                        strategy="iban"
                    )

            # Prioritaet 3: Fuzzy Name Matching
            if not entity_matched and vendor_name:
                matches = await search_service.find_by_matchcode(
                    matchcode=vendor_name,
                    similarity_threshold=0.75
                )
                if matches:
                    best_match, similarity = matches[0]
                    entity_matched = True
                    match_confidence = similarity * 0.85  # Etwas Unsicherheit einbauen
                    match_strategy = "name"
                    matched_entity_id = str(best_match.id)
                    matched_entity_name = best_match.display_name or best_match.name
                    logger.info(
                        "entity_matched_by_name",
                        similarity=round(similarity, 2),
                        entity_id=matched_entity_id,
                        strategy="name"
                    )

    except Exception as e:
        logger.error(
            "entity_matching_failed",
            document_id=document_id,
            error=str(e)
        )
        # Bei Fehler: Kein Match, aber Workflow laeuft weiter
        entity_matched = False
        match_confidence = 0.0

    async with async_session_maker() as db:
        history = ProcessHistory(
            instance_id=UUID(instance_id),
            event_type="ENTITY_MATCHED" if entity_matched else "ENTITY_NOT_MATCHED",
            message=f"Entity-Matching: {'Erfolgreich' if entity_matched else 'Kein Match'} ({match_strategy}, {match_confidence:.0%})",
            actor_type="system",
            company_id=UUID(str(company_id)),  # Bereits validiert
            timestamp=datetime.now(timezone.utc)
        )
        db.add(history)
        await db.commit()

    return {
        "entity_matched": entity_matched,
        "match_confidence": match_confidence,
        "match_strategy": match_strategy,
        "matched_entity_id": matched_entity_id,
        "matched_entity_name": matched_entity_name,
        "matched_at": datetime.now(timezone.utc).isoformat(),
    }


async def route_to_folder(
    instance_id: str,
    variables: Dict[str, Any]
) -> Dict[str, Any]:
    """Routet das Dokument in den passenden Ordner.

    Basierend auf Dokumenttyp und Geschaeftspartner.

    Args:
        instance_id: BPMN Prozess-Instanz ID
        variables: Prozess-Variablen

    Returns:
        Routing-Ergebnis
    """
    from app.db.session import async_session_maker
    from app.db.models.bpmn import ProcessHistory

    document_id = variables.get("document_id")
    document_type = variables.get("document_type", "other")
    matched_entity_id = variables.get("matched_entity_id")

    # Input-Validierung (Multi-Tenant!)
    company_id = variables.get("company_id")
    if not document_id:
        logger.error("routing_missing_document_id", instance_id=instance_id)
        return {
            "routed": False,
            "error": "Keine document_id angegeben",
            "target_folder": None,
            "routed_at": datetime.now(timezone.utc).isoformat(),
        }
    if not company_id:
        logger.error("routing_missing_company_id", instance_id=instance_id)
        return {
            "routed": False,
            "error": "Keine company_id fuer Multi-Tenant-Isolation",
            "target_folder": None,
            "routed_at": datetime.now(timezone.utc).isoformat(),
        }

    logger.info(
        "routing_to_folder",
        instance_id=instance_id,
        document_id=document_id,
        document_type=document_type
    )

    # Routing-Regeln basierend auf Dokumenttyp
    folder_mapping = {
        "invoice": "Eingangsrechnungen",
        "quote": "Angebote",
        "delivery_note": "Lieferscheine",
        "contract": "Vertraege",
        "dunning_notice": "Mahnungen",
        "other": "Sonstiges",
    }

    target_folder = folder_mapping.get(document_type, "Sonstiges")

    # Bei Entity-Match: Unterordner nach Geschaeftspartner
    if matched_entity_id:
        target_folder = f"{target_folder}/Lieferant-{matched_entity_id[:8]}"

    async with async_session_maker() as db:
        # Echtes Routing: document_type setzen und in Metadaten speichern
        from app.db.models import Document

        try:
            # KRITISCH: Multi-Tenant RLS - company_id Filter!
            doc_result = await db.execute(
                select(Document).where(
                    Document.id == UUID(str(document_id)),
                    Document.company_id == UUID(str(company_id)),  # Multi-Tenant!
                )
            )
            doc = doc_result.scalar_one_or_none()

            if doc:
                # Dokumenttyp aktualisieren basierend auf Klassifizierung
                doc.document_type = document_type

                # Target-Folder in Metadaten speichern fuer spaetere Verarbeitung
                if not doc.document_metadata:
                    doc.document_metadata = {}
                doc.document_metadata["target_folder"] = target_folder
                doc.document_metadata["routed_by_workflow"] = instance_id
                doc.document_metadata["routed_at"] = datetime.now(timezone.utc).isoformat()

                await db.commit()

                logger.info(
                    "document_routed",
                    document_id=document_id,
                    target_folder=target_folder,
                    document_type=document_type
                )
            else:
                logger.warning(
                    "document_not_found_for_routing",
                    document_id=document_id
                )

        except Exception as e:
            logger.error(
                "document_routing_failed",
                document_id=document_id,
                error=str(e)
            )
            await db.rollback()

        history = ProcessHistory(
            instance_id=UUID(instance_id),
            event_type="DOCUMENT_ROUTED",
            message=f"Dokument in '{target_folder}' abgelegt",
            actor_type="system",
            company_id=UUID(str(company_id)),  # Bereits validiert
            timestamp=datetime.now(timezone.utc)
        )
        db.add(history)
        await db.commit()

    return {
        "routed": True,
        "target_folder": target_folder,
        "routed_at": datetime.now(timezone.utc).isoformat(),
    }


async def trigger_workflow(
    instance_id: str,
    variables: Dict[str, Any]
) -> Dict[str, Any]:
    """Startet einen nachgelagerten Workflow basierend auf Dokumenttyp.

    Args:
        instance_id: BPMN Prozess-Instanz ID
        variables: Prozess-Variablen

    Returns:
        Workflow-Start-Info
    """
    from app.db.session import async_session_maker
    from app.db.models.bpmn import ProcessHistory

    document_id = variables.get("document_id")
    document_type = variables.get("document_type", "other")
    entities = variables.get("entities", {})

    # Input-Validierung (Multi-Tenant!)
    company_id = variables.get("company_id")
    if not company_id:
        logger.error("workflow_trigger_missing_company_id", instance_id=instance_id)
        return {
            "workflow_triggered": False,
            "error": "Keine company_id fuer Multi-Tenant-Isolation",
            "follow_up_workflow": None,
            "child_instance_id": None,
            "triggered_at": None,
        }

    logger.info(
        "triggering_follow_up_workflow",
        instance_id=instance_id,
        document_type=document_type
    )

    # Workflow-Mapping
    workflow_mapping = {
        "invoice": "invoice-approval-workflow",
        "dunning_notice": "dunning-process-workflow",
        "quote": None,  # Kein automatischer Workflow
        "contract": None,
    }

    follow_up_workflow = workflow_mapping.get(document_type)
    workflow_started = False
    child_instance_id = None

    if follow_up_workflow:
        # Echten Workflow starten via ProcessExecutionService
        try:
            async with async_session_maker() as db_session:
                from app.services.bpmn.process_execution_service import ProcessExecutionService

                exec_service = ProcessExecutionService(db_session)

                # Workflow-Definition finden (MIT company_id Filter fuer Multi-Tenant!)
                from app.db.models.bpmn import ProcessDefinition
                definition_result = await db_session.execute(
                    select(ProcessDefinition).where(
                        ProcessDefinition.key == follow_up_workflow,
                        ProcessDefinition.is_active == True,
                        ProcessDefinition.company_id == UUID(str(company_id)),  # Multi-Tenant!
                    )
                )
                definition = definition_result.scalar_one_or_none()

                if definition:
                    # Child-Prozess starten
                    child_instance = await exec_service.start_process(
                        definition_id=definition.id,
                        variables={
                            **entities,
                            "source_document_id": str(document_id),
                            "source_instance_id": instance_id,
                            "company_id": str(variables.get("company_id")),
                        },
                        started_by_id=variables.get("started_by_id"),
                        company_id=UUID(str(company_id)),  # Bereits validiert
                    )
                    workflow_started = True
                    child_instance_id = str(child_instance.id)

                    logger.info(
                        "follow_up_workflow_started",
                        parent_instance=instance_id,
                        child_instance=child_instance_id,
                        workflow=follow_up_workflow
                    )
                else:
                    logger.warning(
                        "follow_up_workflow_not_found",
                        workflow_key=follow_up_workflow
                    )

        except Exception as e:
            logger.error(
                "follow_up_workflow_start_failed",
                workflow=follow_up_workflow,
                error=str(e)
            )

    async with async_session_maker() as db:
        if workflow_started:
            history = ProcessHistory(
                instance_id=UUID(instance_id),
                event_type="WORKFLOW_TRIGGERED",
                message=f"Folge-Workflow gestartet: {follow_up_workflow}",
                actor_type="system",
                company_id=UUID(str(company_id)),  # Bereits validiert
                timestamp=datetime.now(timezone.utc)
            )
            db.add(history)
            await db.commit()

    return {
        "workflow_triggered": workflow_started,
        "follow_up_workflow": follow_up_workflow,
        "child_instance_id": child_instance_id,
        "triggered_at": datetime.now(timezone.utc).isoformat() if workflow_started else None,
    }


async def complete_classification(
    instance_id: str,
    variables: Dict[str, Any]
) -> Dict[str, Any]:
    """Schliesst den Klassifizierungs-Workflow ab.

    Args:
        instance_id: BPMN Prozess-Instanz ID
        variables: Prozess-Variablen

    Returns:
        Abschluss-Informationen
    """
    from app.db.session import async_session_maker
    from app.db.models.bpmn import ProcessHistory

    document_id = variables.get("document_id")
    document_type = variables.get("document_type", "other")
    entity_matched = variables.get("entity_matched", False)

    # Input-Validierung (Multi-Tenant!)
    company_id = variables.get("company_id")
    if not company_id:
        logger.error("complete_classification_missing_company_id", instance_id=instance_id)
        return {
            "classification_completed": False,
            "error": "Keine company_id fuer Multi-Tenant-Isolation",
            "final_document_type": document_type,
            "entity_linked": entity_matched,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

    logger.info(
        "completing_classification",
        instance_id=instance_id,
        document_id=document_id
    )

    async with async_session_maker() as db:
        history = ProcessHistory(
            instance_id=UUID(instance_id),
            event_type="CLASSIFICATION_COMPLETED",
            message=f"Klassifizierung abgeschlossen - Typ: {document_type}, Entity: {'Ja' if entity_matched else 'Nein'}",
            actor_type="system",
            company_id=UUID(str(company_id)),  # Explizit konvertieren
            timestamp=datetime.now(timezone.utc)
        )
        db.add(history)
        await db.commit()

    return {
        "classification_completed": True,
        "final_document_type": document_type,
        "entity_linked": entity_matched,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


def get_document_type_display_name(document_type: str) -> str:
    """Gibt den deutschen Anzeigenamen fuer einen Dokumenttyp zurueck.

    Args:
        document_type: Interner Dokumenttyp-Schluessel

    Returns:
        Deutscher Anzeigename
    """
    display_names = {
        "invoice": "Rechnung",
        "quote": "Angebot",
        "delivery_note": "Lieferschein",
        "contract": "Vertrag",
        "dunning_notice": "Mahnung",
        "order_confirmation": "Auftragsbestaetigung",
        "credit_note": "Gutschrift",
        "other": "Sonstiges",
    }
    return display_names.get(document_type, document_type)
