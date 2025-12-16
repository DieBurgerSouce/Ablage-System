# -*- coding: utf-8 -*-
"""
LLM OCR Review Service fuer Ablage-System.

LLM-basierte Review und Korrektur von OCR-Ergebnissen (Phase 6).

Verwendet Ollama (Qwen3-8B/14B) fuer:
1. Semantische Validierung (macht der Text Sinn?)
2. Fehlerkorrektur (OCR-typische Fehler beheben)
3. Qualitaetsbewertung (Score 1-10)
4. Entscheidung: Accept nach Korrektur oder ablehnen

Feinpoliert und durchdacht - Enterprise-grade OCR Quality Review.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Literal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.models import OCRTrainingSample, TrainingSampleStatus
from app.services.rag.llm_service import (
    LLMService,
    LLMMessage,
    LLMContextType,
    get_llm_service,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class LLMReviewResult:
    """Ergebnis der LLM-Review eines OCR-Samples."""
    quality_score: float  # 0-10
    issues_found: List[str]
    recommendation: Literal["accept", "reject", "needs_human"]
    reasoning: str
    corrected_text: Optional[str] = None
    confidence: float = 0.0
    processing_time_ms: int = 0


@dataclass
class BatchReviewResult:
    """Ergebnis eines Batch-Reviews."""
    total_processed: int = 0
    accepted: int = 0
    rejected: int = 0
    needs_human: int = 0
    errors: int = 0
    avg_quality_score: float = 0.0
    details: List[Dict[str, Any]] = field(default_factory=list)


# =============================================================================
# LLM Prompts
# =============================================================================

REVIEW_SYSTEM_PROMPT = """Du bist ein spezialisierter OCR-Qualitaetsprufer fuer deutsche Geschaeftsdokumente.

Deine Aufgabe ist es, OCR-extrahierten Text zu analysieren und zu bewerten.
Du bist Experte fuer:
- Deutsche Rechtschreibung und Grammatik
- Umlaute (ä, ö, ü, ß) und ihre OCR-typischen Fehler (ae, oe, ue, ss)
- Geschaeftsdokumente (Rechnungen, Vertraege, Briefe)
- OCR-typische Fehler (0/O Verwechslung, l/1 Verwechslung, etc.)

Sei praezise und kritisch. Qualitaet ist wichtiger als Quantitaet."""

REVIEW_USER_PROMPT = """Analysiere diesen OCR-Text und bewerte seine Qualitaet.

Dokumenttyp: {doc_type}

OCR-Text:
<ocr_text>
{text}
</ocr_text>

Bewerte folgende Aspekte:
1. Semantische Korrektheit - Macht der Text inhaltlich Sinn?
2. OCR-Fehler - Typische Erkennungsfehler (0/O, l/1, rn/m, etc.)
3. Umlaute - Korrekte deutsche Umlaute (ä/ae, ö/oe, ü/ue, ß/ss)
4. Strukturelle Vollstaendigkeit - Sind wichtige Felder erkennbar?

Antworte EXAKT im folgenden Format:

<quality_score>[Zahl 1-10]</quality_score>

<issues>
- [Problem 1]
- [Problem 2]
</issues>

<corrected_text>
[Korrigierter Text falls Korrekturen noetig, sonst UNCHANGED]
</corrected_text>

<recommendation>[accept|reject|needs_human]</recommendation>

<reasoning>
[Deine Begruendung hier]
</reasoning>

Kriterien fuer die Empfehlung:
- accept: Score >= 7, keine kritischen Fehler, Text ist verwendbar
- reject: Score < 4, zu viele Fehler, Text ist unbrauchbar
- needs_human: Score 4-6, unklar ob verwendbar, menschliche Pruefung noetig"""


# =============================================================================
# LLM OCR Review Service
# =============================================================================

class LLMOCRReviewService:
    """
    LLM-basierte Review und Korrektur von OCR-Ergebnissen.

    Verwendet Ollama (Qwen3) fuer:
    1. Semantische Validierung (macht der Text Sinn?)
    2. Fehlerkorrektur (OCR-typische Fehler beheben)
    3. Qualitaetsbewertung (Score 1-10)
    4. Entscheidung: Accept nach Korrektur oder ablehnen
    """

    # Maximale Textlaenge fuer LLM-Review (Token-Limit beachten)
    MAX_TEXT_LENGTH = 8000

    # Minimale Textlaenge fuer sinnvolle Review
    MIN_TEXT_LENGTH = 20

    def __init__(self, llm_service: Optional[LLMService] = None):
        """Initialisiere LLM OCR Review Service."""
        self.llm_service = llm_service or get_llm_service()

    # =========================================================================
    # MAIN API
    # =========================================================================

    async def review_sample(
        self,
        db: AsyncSession,
        sample: OCRTrainingSample,
        auto_correct: bool = True,
    ) -> LLMReviewResult:
        """
        Prueft ein Sample mit LLM.

        Args:
            db: Datenbank-Session
            sample: OCR Training Sample zum Pruefen
            auto_correct: Wenn True, werden Korrekturen automatisch angewendet

        Returns:
            LLMReviewResult mit Bewertung und ggf. Korrekturen
        """
        start_time = datetime.now(timezone.utc)

        # Text fuer Review vorbereiten
        text = sample.ground_truth_text or ""

        # Validierung
        if len(text) < self.MIN_TEXT_LENGTH:
            return LLMReviewResult(
                quality_score=0.0,
                issues_found=["Text zu kurz fuer Review"],
                recommendation="reject",
                reasoning="Der OCR-Text ist zu kurz fuer eine sinnvolle Bewertung.",
                confidence=1.0,
            )

        # Text kuerzen wenn noetig
        if len(text) > self.MAX_TEXT_LENGTH:
            text = text[:self.MAX_TEXT_LENGTH] + "\n[...Text gekuerzt...]"

        # LLM-Review durchfuehren
        try:
            result = await self._call_llm_review(
                text=text,
                doc_type=sample.document_type or "unknown",
            )

            # Ergebnis in Sample speichern
            await self._save_review_result(
                db=db,
                sample=sample,
                result=result,
                auto_correct=auto_correct,
            )

            # Processing Time berechnen
            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            result.processing_time_ms = int(processing_time * 1000)

            logger.info(
                "llm_ocr_review_complete",
                sample_id=str(sample.id),
                quality_score=result.quality_score,
                recommendation=result.recommendation,
                issues_count=len(result.issues_found),
                processing_time_ms=result.processing_time_ms,
            )

            return result

        except Exception as e:
            logger.error(
                "llm_ocr_review_error",
                sample_id=str(sample.id),
                error=str(e),
            )
            return LLMReviewResult(
                quality_score=0.0,
                issues_found=[f"LLM-Review fehlgeschlagen: {str(e)}"],
                recommendation="needs_human",
                reasoning=f"Technischer Fehler bei der LLM-Review: {str(e)}",
                confidence=0.0,
            )

    async def review_sample_by_id(
        self,
        db: AsyncSession,
        sample_id: UUID,
        auto_correct: bool = True,
    ) -> Optional[LLMReviewResult]:
        """
        Prueft ein Sample anhand seiner ID.

        Args:
            db: Datenbank-Session
            sample_id: ID des Samples
            auto_correct: Wenn True, werden Korrekturen automatisch angewendet

        Returns:
            LLMReviewResult oder None wenn Sample nicht gefunden
        """
        # Sample holen
        result = await db.execute(
            select(OCRTrainingSample)
            .where(OCRTrainingSample.id == sample_id)
            .where(OCRTrainingSample.deleted_at.is_(None))
        )
        sample = result.scalar_one_or_none()

        if not sample:
            logger.warning("llm_ocr_review_sample_not_found", sample_id=str(sample_id))
            return None

        return await self.review_sample(db, sample, auto_correct)

    async def batch_review(
        self,
        db: AsyncSession,
        max_samples: int = 50,
        document_type: Optional[str] = None,
        only_pending: bool = True,
    ) -> BatchReviewResult:
        """
        Batch-Review von pending Samples.

        Priorisiert nach Business-Criticality.

        Args:
            db: Datenbank-Session
            max_samples: Maximale Anzahl zu verarbeitender Samples
            document_type: Optional Filter nach Dokumenttyp
            only_pending: Nur Samples ohne bisherige LLM-Review

        Returns:
            BatchReviewResult mit Statistiken
        """
        result = BatchReviewResult()

        # Query bauen
        query = (
            select(OCRTrainingSample)
            .where(OCRTrainingSample.deleted_at.is_(None))
            .where(OCRTrainingSample.auto_accepted == False)  # Nur rejected Samples
            .where(OCRTrainingSample.ground_truth_text.isnot(None))  # Mit Text
            .order_by(OCRTrainingSample.business_priority.desc())  # Hohe Prioritaet zuerst
            .limit(max_samples)
        )

        if document_type:
            query = query.where(OCRTrainingSample.document_type == document_type)

        if only_pending:
            query = query.where(OCRTrainingSample.llm_review_status == "pending")

        samples_result = await db.execute(query)
        samples = samples_result.scalars().all()

        quality_scores = []

        for sample in samples:
            try:
                review_result = await self.review_sample(db, sample, auto_correct=True)
                result.total_processed += 1
                quality_scores.append(review_result.quality_score)

                if review_result.recommendation == "accept":
                    result.accepted += 1
                elif review_result.recommendation == "reject":
                    result.rejected += 1
                else:
                    result.needs_human += 1

                result.details.append({
                    "sample_id": str(sample.id),
                    "quality_score": review_result.quality_score,
                    "recommendation": review_result.recommendation,
                    "issues_count": len(review_result.issues_found),
                })

            except Exception as e:
                logger.error(
                    "llm_batch_review_sample_error",
                    sample_id=str(sample.id),
                    error=str(e),
                )
                result.errors += 1

        # Durchschnittliche Qualitaet berechnen
        if quality_scores:
            result.avg_quality_score = sum(quality_scores) / len(quality_scores)

        await db.commit()

        logger.info(
            "llm_batch_review_complete",
            total_processed=result.total_processed,
            accepted=result.accepted,
            rejected=result.rejected,
            needs_human=result.needs_human,
            errors=result.errors,
            avg_quality_score=result.avg_quality_score,
        )

        return result

    async def get_review_stats(
        self,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """
        Statistiken ueber LLM-Reviews.

        Returns:
            Dict mit Review-Statistiken
        """
        # Gesamtzahlen
        total_result = await db.execute(
            select(func.count(OCRTrainingSample.id))
            .where(OCRTrainingSample.deleted_at.is_(None))
        )
        total = total_result.scalar() or 0

        # Nach LLM Review Status
        status_counts = {}
        for status in ["pending", "reviewed", "accepted", "rejected", "needs_human"]:
            count_result = await db.execute(
                select(func.count(OCRTrainingSample.id))
                .where(OCRTrainingSample.deleted_at.is_(None))
                .where(OCRTrainingSample.llm_review_status == status)
            )
            status_counts[status] = count_result.scalar() or 0

        # Durchschnittliche Qualitaet der reviewed Samples
        # Lade Samples mit Results und berechne Durchschnitt im Python-Code
        reviewed_result = await db.execute(
            select(OCRTrainingSample.llm_review_result)
            .where(OCRTrainingSample.deleted_at.is_(None))
            .where(OCRTrainingSample.llm_review_status.notin_(["pending", None]))
            .where(OCRTrainingSample.llm_review_result.isnot(None))
            .limit(1000)  # Begrenze fuer Performance
        )
        reviewed_samples = reviewed_result.scalars().all()

        quality_scores = []
        for result in reviewed_samples:
            if isinstance(result, dict) and "quality_score" in result:
                try:
                    score = float(result["quality_score"])
                    quality_scores.append(score)
                except (TypeError, ValueError):
                    pass

        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else None

        # Letzte Review
        last_review_result = await db.execute(
            select(OCRTrainingSample.llm_reviewed_at)
            .where(OCRTrainingSample.llm_reviewed_at.isnot(None))
            .order_by(OCRTrainingSample.llm_reviewed_at.desc())
            .limit(1)
        )
        last_review = last_review_result.scalar()

        # Korrektur-Rate berechnen (Samples mit llm_corrected_text)
        corrected_result = await db.execute(
            select(func.count(OCRTrainingSample.id))
            .where(OCRTrainingSample.deleted_at.is_(None))
            .where(OCRTrainingSample.llm_corrected_text.isnot(None))
        )
        corrected_count = corrected_result.scalar() or 0

        total_reviewed = sum(
            v for k, v in status_counts.items()
            if k not in ["pending", None]
        )
        correction_rate = corrected_count / total_reviewed if total_reviewed > 0 else None

        return {
            "total_samples": total,
            "total_reviewed": total_reviewed,
            "pending_review": status_counts.get("pending", 0) + (total - sum(status_counts.values())),
            "by_recommendation": {
                "accepted": status_counts.get("accepted", 0),
                "rejected": status_counts.get("rejected", 0),
                "needs_human": status_counts.get("needs_human", 0),
            },
            "avg_quality_score": round(avg_quality, 2) if avg_quality else None,
            "correction_rate": round(correction_rate, 4) if correction_rate else None,
            "last_review_at": last_review.isoformat() if last_review else None,
        }

    # =========================================================================
    # INTERNAL HELPERS
    # =========================================================================

    async def _call_llm_review(
        self,
        text: str,
        doc_type: str,
    ) -> LLMReviewResult:
        """Ruft das LLM fuer die Review auf."""

        # Prompt zusammenbauen
        user_prompt = REVIEW_USER_PROMPT.format(
            doc_type=doc_type,
            text=text,
        )

        messages = [
            LLMMessage(role="system", content=REVIEW_SYSTEM_PROMPT),
            LLMMessage(role="user", content=user_prompt),
        ]

        # LLM aufrufen (mit Thinking Mode fuer bessere Analyse)
        response = await self.llm_service.generate(
            messages=messages,
            context_type=LLMContextType.EXTRACTION,
            enable_thinking=True,
            temperature=0.3,  # Niedrig fuer konsistente Bewertungen
        )

        # Antwort parsen
        return self._parse_llm_response(response.content)

    def _parse_llm_response(self, content: str) -> LLMReviewResult:
        """Parst die strukturierte LLM-Antwort."""

        # Quality Score extrahieren
        quality_match = re.search(r'<quality_score>\s*(\d+(?:\.\d+)?)\s*</quality_score>', content)
        quality_score = float(quality_match.group(1)) if quality_match else 5.0

        # Issues extrahieren
        issues_match = re.search(r'<issues>(.*?)</issues>', content, re.DOTALL)
        issues_found = []
        if issues_match:
            issues_text = issues_match.group(1).strip()
            # Parse Aufzaehlung
            for line in issues_text.split('\n'):
                line = line.strip()
                if line.startswith('-'):
                    issues_found.append(line[1:].strip())
                elif line:
                    issues_found.append(line)

        # Korrigierter Text extrahieren
        corrected_match = re.search(r'<corrected_text>(.*?)</corrected_text>', content, re.DOTALL)
        corrected_text = None
        if corrected_match:
            corrected = corrected_match.group(1).strip()
            if corrected and corrected.upper() != "UNCHANGED":
                corrected_text = corrected

        # Empfehlung extrahieren
        recommendation_match = re.search(r'<recommendation>\s*(accept|reject|needs_human)\s*</recommendation>', content)
        recommendation: Literal["accept", "reject", "needs_human"] = "needs_human"
        if recommendation_match:
            rec = recommendation_match.group(1).lower()
            if rec in ("accept", "reject", "needs_human"):
                recommendation = rec  # type: ignore

        # Reasoning extrahieren
        reasoning_match = re.search(r'<reasoning>(.*?)</reasoning>', content, re.DOTALL)
        reasoning = reasoning_match.group(1).strip() if reasoning_match else "Keine Begruendung angegeben."

        return LLMReviewResult(
            quality_score=quality_score,
            issues_found=issues_found,
            recommendation=recommendation,
            reasoning=reasoning,
            corrected_text=corrected_text,
            confidence=0.8 if quality_match and recommendation_match else 0.5,
        )

    async def _save_review_result(
        self,
        db: AsyncSession,
        sample: OCRTrainingSample,
        result: LLMReviewResult,
        auto_correct: bool,
    ) -> None:
        """Speichert das Review-Ergebnis im Sample."""

        # Review-Status setzen
        sample.llm_review_status = result.recommendation

        # Review-Ergebnis als JSON speichern
        sample.llm_review_result = {
            "quality_score": result.quality_score,
            "issues_found": result.issues_found,
            "recommendation": result.recommendation,
            "reasoning": result.reasoning,
            "confidence": result.confidence,
        }

        # Korrigierten Text speichern
        if result.corrected_text:
            sample.llm_corrected_text = result.corrected_text

            # Bei auto_correct und accept: Ground Truth aktualisieren
            if auto_correct and result.recommendation == "accept":
                sample.ground_truth_text = result.corrected_text
                sample.source = "llm_corrected"

        # Timestamp setzen
        sample.llm_reviewed_at = datetime.now(timezone.utc)

        # Bei accept: Sample als verified markieren
        if result.recommendation == "accept":
            sample.status = TrainingSampleStatus.VERIFIED.value
            sample.verified_at = datetime.now(timezone.utc)

        await db.flush()


# =============================================================================
# Singleton Instance
# =============================================================================

_llm_ocr_review_service: Optional[LLMOCRReviewService] = None


def get_llm_ocr_review_service() -> LLMOCRReviewService:
    """Holt oder erstellt Singleton-Instanz des LLMOCRReviewService."""
    global _llm_ocr_review_service
    if _llm_ocr_review_service is None:
        _llm_ocr_review_service = LLMOCRReviewService()
    return _llm_ocr_review_service
