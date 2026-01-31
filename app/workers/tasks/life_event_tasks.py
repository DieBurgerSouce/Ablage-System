# -*- coding: utf-8 -*-
"""Life Event Engine periodic tasks (F16).

Phase 12: Dokumenten-basierte Mustererkennung fuer Lebensereignisse.
"""

import asyncio
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

import structlog
from sqlalchemy import select, and_

from app.core.safe_errors import safe_error_log
from app.workers.celery_app import celery_app
from app.db.session import async_session_maker
from app.db.models import Company, Document, DocumentType

logger = structlog.get_logger(__name__)


# Muster fuer Lebensereignis-Erkennung
LIFE_EVENT_PATTERNS = {
    "umzug": {
        "keywords": ["umzug", "neue adresse", "adressaenderung", "einzug", "auszug", "mietvertrag"],
        "doc_types": [DocumentType.LETTER, DocumentType.CONTRACT, DocumentType.OTHER],
    },
    "heirat": {
        "keywords": ["heirat", "eheschliessung", "standesamt", "trauung", "eheurkunde"],
        "doc_types": [DocumentType.OTHER, DocumentType.LETTER],
    },
    "geburt": {
        "keywords": ["geburt", "geburtsurkunde", "kindergeld", "elterngeld", "kind"],
        "doc_types": [DocumentType.OTHER, DocumentType.LETTER, DocumentType.FORM],
    },
    "jobwechsel": {
        "keywords": ["arbeitsvertrag", "kuendigung", "neuer arbeitgeber", "einstellung", "probezeit"],
        "doc_types": [DocumentType.CONTRACT, DocumentType.LETTER],
    },
    "immobilienkauf": {
        "keywords": ["kaufvertrag", "grundbuch", "notar", "immobilie", "eigentum", "grundstueck"],
        "doc_types": [DocumentType.CONTRACT, DocumentType.OTHER],
    },
    "rente": {
        "keywords": ["rente", "rentenbescheid", "altersrente", "rentenversicherung"],
        "doc_types": [DocumentType.LETTER, DocumentType.OTHER],
    },
}


@celery_app.task(name="app.workers.tasks.life_event_tasks.detect_life_events")
def detect_life_events() -> dict:
    """Erkenne Lebensereignisse aus neuen Dokumenten.

    Erkennt:
    - Umzug (Adressaenderung in Dokumenten)
    - Heirat (Namensaenderung, Heiratsurkunde)
    - Kind (Geburtsurkunde, Kindergeld-Antrag)
    - Jobwechsel (Neue Arbeitsvertraege)
    - Immobilienkauf (Kaufvertraege, Grundbuch)
    """
    logger.info("life_events_detection_start")
    try:
        result = asyncio.get_event_loop().run_until_complete(_detect_life_events())
        logger.info(
            "life_events_detection_complete",
            events_detected=result.get("events_detected", 0),
        )
        return result
    except Exception as e:
        logger.error("life_events_detection_error", **safe_error_log(e))
        raise


async def _detect_life_events() -> Dict[str, Any]:
    """Async Implementation fuer Life Event Detection."""
    events_detected = 0
    events_by_type: Dict[str, int] = {}

    async with async_session_maker() as db:
        # Dokumente der letzten 24 Stunden mit OCR-Text
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

        docs_result = await db.execute(
            select(Document)
            .where(
                and_(
                    Document.created_at >= cutoff,
                    Document.ocr_text.isnot(None),
                    Document.ocr_processed == True,
                )
            )
        )
        documents = docs_result.scalars().all()

        for doc in documents:
            detected = _detect_life_event_in_document(doc)

            if detected:
                events_detected += 1
                events_by_type[detected] = events_by_type.get(detected, 0) + 1

                logger.info(
                    "life_event_detected",
                    document_id=str(doc.id),
                    event_type=detected,
                    document_type=doc.document_type.value if doc.document_type else "unknown",
                )

    return {
        "status": "success",
        "events_detected": events_detected,
        "events_by_type": events_by_type,
    }


def _detect_life_event_in_document(doc: Document) -> Optional[str]:
    """Prueft ein Dokument auf Lebensereignis-Muster.

    Args:
        doc: Dokument mit OCR-Text

    Returns:
        Event-Typ (z.B. "umzug") oder None
    """
    if not doc.ocr_text:
        return None

    text_lower = doc.ocr_text.lower()

    for event_type, config in LIFE_EVENT_PATTERNS.items():
        # Dokumenttyp pruefen
        if doc.document_type and doc.document_type not in config["doc_types"]:
            continue

        # Keywords suchen
        keyword_matches = sum(
            1 for keyword in config["keywords"]
            if keyword in text_lower
        )

        # Mindestens 2 Keywords muessen matchen fuer hoehere Confidence
        if keyword_matches >= 2:
            return event_type

        # Bei starkem Keyword-Match (z.B. "heiratsurkunde") auch bei 1 Match
        strong_keywords = ["heiratsurkunde", "geburtsurkunde", "kaufvertrag", "arbeitsvertrag"]
        for strong in strong_keywords:
            if strong in text_lower:
                return event_type

    return None
