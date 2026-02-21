"""Dokumenten-Zusammenfassungs-Service.

Generiert automatische deutsche Zusammenfassungen, Schluesselwoerter
und Einzeiler fuer verarbeitete Dokumente. Nutzt lokales LLM (On-Premises)
via Ollama-Integration - keine Cloud-Abhaengigkeiten.

Phase 2.2: Auto-Zusammenfassungen nach OCR-Verarbeitung.
Feinpoliert und durchdacht.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.datetime_utils import utc_now
from app.db.models import Document, ProcessingStatus

logger = structlog.get_logger(__name__)

# Maximale Zeichenanzahl fuer LLM-Eingabe (Token-Limit-Schutz)
MAX_TEXT_CHARS = 4000

# Prompt-Template fuer Zusammenfassungs-Generierung
SUMMARY_PROMPT = """Du bist ein Dokumenten-Analyst fuer ein deutsches Unternehmen.
Analysiere den folgenden OCR-Text und erstelle:

1. ZUSAMMENFASSUNG: Eine praezise deutsche Zusammenfassung in 3-5 Saetzen.
   Erfasse den Dokumenttyp, Absender/Empfaenger, Kerninhalt und wichtige Daten/Betraege.

2. SCHLUESSELWOERTER: 5-10 relevante deutsche Begriffe als kommagetrennte Liste.
   Fokus auf: Dokumenttyp, beteiligte Firmen, Betraege, Termine, Kategorien.

3. EINZEILER: Eine einzelne Zeile die das Dokument beschreibt (max 100 Zeichen).
   Format: "[Dokumenttyp] von [Absender] - [Kerninhalt]"

OCR-Text:
---
{text}
---

Antworte EXAKT in diesem Format:
ZUSAMMENFASSUNG: [deine Zusammenfassung]
SCHLUESSELWOERTER: [wort1, wort2, wort3, ...]
EINZEILER: [dein Einzeiler]"""

# System-Prompt fuer konsistente Ergebnisse
SYSTEM_PROMPT = (
    "Du bist ein praeziser Dokumenten-Analyst. "
    "Antworte immer auf Deutsch und halte dich exakt an das vorgegebene Format."
)


class SummaryService:
    """Service fuer KI-generierte Dokumenten-Zusammenfassungen.

    Verwendet den lokalen Ollama-Service fuer On-Premises LLM-Inferenz.
    Generiert Zusammenfassungen, Schluesselwoerter und Einzeiler
    fuer OCR-verarbeitete Dokumente.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def generate_summary(
        self,
        document_id: UUID,
        model_override: Optional[str] = None,
    ) -> Dict[str, object]:
        """Generiert Zusammenfassung fuer ein Dokument.

        Ablauf:
        1. Laedt extracted_text aus der DB
        2. Kuerzt auf max 4000 Zeichen (LLM Token-Limit)
        3. Sendet an lokales LLM via Ollama
        4. Parst strukturierte Antwort
        5. Speichert Ergebnis in DB

        Args:
            document_id: UUID des Dokuments
            model_override: Optionales LLM-Modell (ueberschreibt Default)

        Returns:
            Dict mit summary, keywords, one_liner

        Raises:
            ValueError: Wenn Dokument nicht gefunden oder kein Text vorhanden
        """
        # 1. Dokument laden
        result = await self.session.execute(
            select(Document).where(Document.id == document_id)
        )
        document = result.scalar_one_or_none()

        if document is None:
            raise ValueError(f"Dokument nicht gefunden: {document_id}")

        if not document.extracted_text or not document.extracted_text.strip():
            raise ValueError(
                f"Kein OCR-Text vorhanden fuer Dokument: {document_id}"
            )

        # 2. Text kuerzen
        truncated_text = self._truncate_text(
            document.extracted_text, MAX_TEXT_CHARS
        )

        # 3. LLM-Anfrage via Ollama
        model = model_override or settings.DEFAULT_LLM_ANALYSIS
        prompt = SUMMARY_PROMPT.format(text=truncated_text)

        llm_response = await self._call_llm(prompt, model=model)

        # 4. Antwort parsen
        summary, keywords, one_liner = self._parse_llm_response(llm_response)

        # 5. In DB speichern
        now = utc_now()
        await self.session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(
                summary=summary,
                keywords=keywords,
                one_liner=one_liner,
                summary_generated_at=now,
                summary_model=model,
            )
        )
        await self.session.flush()

        logger.info(
            "summary_generated",
            document_id=str(document_id),
            model=model,
            keywords_count=len(keywords),
            summary_length=len(summary),
        )

        return {
            "summary": summary,
            "keywords": keywords,
            "one_liner": one_liner,
            "model": model,
            "generated_at": now.isoformat(),
        }

    async def batch_generate(
        self,
        company_id: UUID,
        limit: int = 50,
        model_override: Optional[str] = None,
    ) -> int:
        """Generiert Zusammenfassungen fuer alle Dokumente ohne Summary.

        Verarbeitet nur Dokumente mit Status COMPLETED und vorhandenem
        extracted_text, die noch keine Summary haben.

        Args:
            company_id: Mandanten-ID
            limit: Maximale Anzahl zu verarbeitender Dokumente
            model_override: Optionales LLM-Modell

        Returns:
            Anzahl erfolgreich verarbeiteter Dokumente
        """
        # Dokumente ohne Summary finden
        result = await self.session.execute(
            select(Document.id)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.status == ProcessingStatus.COMPLETED.value,
                    Document.extracted_text.isnot(None),
                    Document.extracted_text != "",
                    Document.summary.is_(None),
                    Document.deleted_at.is_(None),
                )
            )
            .order_by(Document.created_at.desc())
            .limit(limit)
        )
        document_ids = [row[0] for row in result.fetchall()]

        if not document_ids:
            logger.info(
                "batch_summary_no_documents",
                company_id=str(company_id),
            )
            return 0

        processed = 0
        errors = 0

        for doc_id in document_ids:
            try:
                await self.generate_summary(
                    document_id=doc_id,
                    model_override=model_override,
                )
                processed += 1
            except Exception as exc:
                errors += 1
                logger.warning(
                    "batch_summary_document_failed",
                    document_id=str(doc_id),
                    error_type=type(exc).__name__,
                    error=str(exc),
                )

        logger.info(
            "batch_summary_completed",
            company_id=str(company_id),
            total=len(document_ids),
            processed=processed,
            errors=errors,
        )

        return processed

    async def regenerate_summary(
        self,
        document_id: UUID,
        model_override: Optional[str] = None,
    ) -> Dict[str, object]:
        """Erzwingt Neugenerierung der Zusammenfassung.

        Loescht vorhandene Summary und generiert eine neue.

        Args:
            document_id: UUID des Dokuments
            model_override: Optionales LLM-Modell

        Returns:
            Dict mit summary, keywords, one_liner
        """
        # Vorherige Summary loeschen
        await self.session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(
                summary=None,
                keywords=[],
                one_liner=None,
                summary_generated_at=None,
                summary_model=None,
            )
        )
        await self.session.flush()

        logger.info(
            "summary_regeneration_requested",
            document_id=str(document_id),
        )

        return await self.generate_summary(
            document_id=document_id,
            model_override=model_override,
        )

    async def get_summary_stats(
        self,
        company_id: UUID,
    ) -> Dict[str, int]:
        """Statistiken ueber Summary-Generierung.

        Args:
            company_id: Mandanten-ID

        Returns:
            Dict mit total_documents, with_summary, without_summary, percentage
        """
        base_filter = and_(
            Document.company_id == company_id,
            Document.status == ProcessingStatus.COMPLETED.value,
            Document.deleted_at.is_(None),
        )

        # Gesamt-Dokumente
        total_result = await self.session.execute(
            select(func.count(Document.id)).where(base_filter)
        )
        total = total_result.scalar() or 0

        # Mit Summary
        with_summary_result = await self.session.execute(
            select(func.count(Document.id)).where(
                and_(
                    base_filter,
                    Document.summary.isnot(None),
                )
            )
        )
        with_summary = with_summary_result.scalar() or 0

        without_summary = total - with_summary
        percentage = round((with_summary / total * 100), 1) if total > 0 else 0.0

        return {
            "total_documents": total,
            "with_summary": with_summary,
            "without_summary": without_summary,
            "percentage": percentage,
        }

    def _parse_llm_response(
        self, response: str
    ) -> Tuple[str, List[str], str]:
        """Parst die strukturierte LLM-Antwort.

        Erwartet Format:
            ZUSAMMENFASSUNG: ...
            SCHLUESSELWOERTER: wort1, wort2, ...
            EINZEILER: ...

        Args:
            response: Rohe LLM-Antwort

        Returns:
            Tuple aus (summary, keywords, one_liner)
        """
        summary = ""
        keywords: List[str] = []
        one_liner = ""

        # ZUSAMMENFASSUNG extrahieren
        summary_match = re.search(
            r"ZUSAMMENFASSUNG:\s*(.+?)(?=SCHLUESSELWOERTER:|$)",
            response,
            re.DOTALL | re.IGNORECASE,
        )
        if summary_match:
            summary = summary_match.group(1).strip()

        # SCHLUESSELWOERTER extrahieren
        keywords_match = re.search(
            r"SCHLUESSELWOERTER:\s*(.+?)(?=EINZEILER:|$)",
            response,
            re.DOTALL | re.IGNORECASE,
        )
        if keywords_match:
            raw_keywords = keywords_match.group(1).strip()
            keywords = [
                kw.strip()
                for kw in raw_keywords.split(",")
                if kw.strip()
            ]

        # EINZEILER extrahieren
        one_liner_match = re.search(
            r"EINZEILER:\s*(.+?)$",
            response,
            re.MULTILINE | re.IGNORECASE,
        )
        if one_liner_match:
            one_liner = one_liner_match.group(1).strip()
            # Auf 500 Zeichen begrenzen (DB-Spalte)
            if len(one_liner) > 500:
                one_liner = one_liner[:497] + "..."

        # Fallback: Wenn Parsing fehlschlaegt, gesamte Antwort als Summary
        if not summary and response.strip():
            logger.warning(
                "summary_parse_fallback",
                response_preview=response[:200],
            )
            summary = response.strip()
            if len(summary) > 2000:
                summary = summary[:1997] + "..."

        return summary, keywords, one_liner

    def _truncate_text(self, text: str, max_chars: int = MAX_TEXT_CHARS) -> str:
        """Kuerzt Text intelligent am Satzende.

        Schneidet am letzten vollstaendigen Satz innerhalb des Limits ab,
        um dem LLM einen semantisch sinnvollen Text zu uebergeben.

        Args:
            text: Zu kuerzender Text
            max_chars: Maximale Zeichenanzahl

        Returns:
            Gekuerzter Text
        """
        if len(text) <= max_chars:
            return text

        # Am letzten Satzende innerhalb des Limits abschneiden
        truncated = text[:max_chars]

        # Suche letztes Satzende (. ! ? gefolgt von Leerzeichen oder Zeilenumbruch)
        last_sentence_end = -1
        for match in re.finditer(r'[.!?]\s', truncated):
            last_sentence_end = match.end()

        if last_sentence_end > max_chars // 2:
            # Nur verwenden wenn mindestens die Haelfte des Textes erhalten bleibt
            return truncated[:last_sentence_end].strip()

        # Fallback: Am letzten Wort abschneiden
        last_space = truncated.rfind(" ")
        if last_space > max_chars // 2:
            return truncated[:last_space].strip() + "..."

        return truncated.strip() + "..."

    async def _call_llm(
        self,
        prompt: str,
        model: Optional[str] = None,
    ) -> str:
        """Ruft das lokale LLM via Ollama auf.

        Erstellt einen kurzlebigen OllamaService-Client fuer den Aufruf.

        Args:
            prompt: Der Prompt fuer das LLM
            model: Modellname (Default aus Settings)

        Returns:
            Generierter Text

        Raises:
            RuntimeError: Wenn Ollama nicht verfuegbar oder Generierung fehlschlaegt
        """
        from app.services.ai.ollama_service import OllamaService, OllamaConfig

        config = OllamaConfig(
            base_url=getattr(settings, "OLLAMA_URL", "http://localhost:11434"),
            default_model=model or settings.DEFAULT_LLM_ANALYSIS,
            timeout=float(getattr(settings, "OLLAMA_TIMEOUT", 120)),
            max_retries=3,
            temperature=0.1,
        )
        ollama = OllamaService(config=config)

        try:
            # Verfuegbarkeit pruefen
            available = await ollama.is_available()
            if not available:
                raise RuntimeError(
                    "Ollama-Service nicht verfuegbar. "
                    "Bitte pruefen Sie ob Ollama laeuft."
                )

            response = await ollama.generate(
                prompt=prompt,
                model=model or config.default_model,
                system_prompt=SYSTEM_PROMPT,
                temperature=0.1,
            )

            if not response or not response.strip():
                raise RuntimeError(
                    "LLM hat leere Antwort zurueckgegeben."
                )

            return response

        finally:
            await ollama.close()
