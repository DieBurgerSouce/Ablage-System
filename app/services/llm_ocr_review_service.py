# -*- coding: utf-8 -*-
"""
LLM OCR Review Service für Ablage-System.

LLM-basierte Review und Korrektur von OCR-Ergebnissen (Phase 6).

Verwendet Ollama (Qwen3-8B/14B) für:
1. Semantische Validierung (macht der Text Sinn?)
2. Fehlerkorrektur (OCR-typische Fehler beheben)
3. Qualitätsbewertung (Score 1-10)
4. Entscheidung: Accept nach Korrektur oder ablehnen

Feinpoliert und durchdacht - Enterprise-grade OCR Quality Review.
"""

import re
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Literal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    RetryError,
)
import httpx

from app.db.models import OCRTrainingSample, TrainingSampleStatus
from app.core.safe_errors import safe_error_log, safe_error_detail
from app.services.rag.llm_service import (

    LLMService,
    LLMMessage,
    LLMContextType,
    get_llm_service,
)

logger = structlog.get_logger(__name__)

# LLM Retry Konfiguration
LLM_MAX_RETRIES = 3
LLM_RETRY_MIN_WAIT = 2  # Sekunden
LLM_RETRY_MAX_WAIT = 10  # Sekunden

# Circuit Breaker Konfiguration
CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5  # Fehler bis Circuit öffnet
CIRCUIT_BREAKER_RECOVERY_TIMEOUT = 300  # Sekunden bis Half-Open
CIRCUIT_BREAKER_SUCCESS_THRESHOLD = 2  # Erfolge bis Circuit schließt


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

REVIEW_SYSTEM_PROMPT = """Du bist ein spezialisierter OCR-Qualitätsprufer für deutsche Geschäftsdokumente.

Deine Aufgabe ist es, OCR-extrahierten Text zu analysieren und NUR ECHTE FEHLER zu finden.

WICHTIG - Du darfst NUR diese Arten von Fehlern melden:
1. ECHTE OCR-Erkennungsfehler: 0/O Verwechslung, l/1/I Verwechslung, rn→m, vv→w, etc.
2. FEHLENDE oder FALSCHE Umlaute: ae statt ä, oe statt ö, ue statt ü, ss statt ß
3. UNLESBARER/KORRUPTER Text: Sonderzeichen-Muell, fehlende Woerter mitten im Satz
4. STRUKTURELLE Probleme: Komplett fehlende wichtige Dokumentteile

Du darfst NICHT als Fehler melden:
- Stilistische Praeferenzen (Kommasetzung, Formatierung)
- Korrekte deutsche Fachbegriffe und Redewendungen wie "frei Haus", "z.Hd.", "lt.", "ggf."
- Unternehmensnamen mit ungewoehnlicher Schreibweise (a.b.s., GmbH & Co. KG)
- Produktcodes, Artikelnummern, IBANs, Rechnungsnummern
- Abkürzungen die im Geschäftskontext ueblich sind

Wenn du dir nicht 100% sicher bist, dass etwas ein OCR-Fehler ist, melde es NICHT.
Erfinde NIEMALS Korrekturen. Wenn ein Wort korrekt aussieht, ist es wahrscheinlich korrekt."""

REVIEW_USER_PROMPT = """Analysiere diesen OCR-Text auf ECHTE OCR-Fehler.

Dokumenttyp: {doc_type}

OCR-Text:
<ocr_text>
{text}
</ocr_text>

Suche NUR nach diesen ECHTEN OCR-Problemen:
1. Zeichenverwechslungen: 0↔O, l↔1↔I, rn↔m, vv↔w, cl↔d
2. Falsche Umlaute: "ae" statt "ä", "oe" statt "ö", "ue" statt "ü", "ss" statt "ß"
3. Korrupter Text: Sonderzeichen-Muell, abgeschnittene Woerter
4. Komplett unlesbare Abschnitte

IGNORIERE und melde NICHT:
- "frei Haus" ist KORREKT (nicht "freihaus")
- "a.b.s." ist ein Firmenname, KEIN Fehler
- "Lt." für "Laut" ist eine korrekte Abkürzung
- "z.Hd." ist korrekt
- Artikelnummern wie "2006-R" oder "180 my" sind KEINE Fehler
- Formatierung, Kommasetzung, Stilfragen

Antworte EXAKT in diesem Format:

<quality_score>[1-10]</quality_score>

<issues>
- [NUR echte OCR-Fehler, oder "Keine OCR-Fehler gefunden"]
</issues>

<corrected_text>UNCHANGED</corrected_text>

<recommendation>[accept|reject|needs_human]</recommendation>

<reasoning>[Kurze Begruendung]</reasoning>

Bewertungskriterien:
- Score 8-10: Text ist gut lesbar und verwendbar → accept
- Score 5-7: Einige Fehler, aber Inhalt erkennbar → needs_human
- Score 1-4: Text ist stark beschaedigt oder unlesbar → reject

WICHTIG: Wenn der Text lesbar und verstaendlich ist, vergib mindestens Score 7."""


# =============================================================================
# LLM OCR Review Service
# =============================================================================

class LLMOCRReviewService:
    """
    LLM-basierte Review und Korrektur von OCR-Ergebnissen.

    Verwendet Ollama (Qwen3) für:
    1. Semantische Validierung (macht der Text Sinn?)
    2. Fehlerkorrektur (OCR-typische Fehler beheben)
    3. Qualitätsbewertung (Score 1-10)
    4. Entscheidung: Accept nach Korrektur oder ablehnen

    Circuit Breaker Pattern:
    - CLOSED: Normal operation
    - OPEN: Fast-fail after repeated failures (5 min timeout)
    - HALF_OPEN: Test with single request
    """

    # Maximale Textlänge für LLM-Review (Token-Limit beachten)
    MAX_TEXT_LENGTH = 8000

    # Minimale Textlänge für sinnvolle Review
    MIN_TEXT_LENGTH = 20

    # Circuit Breaker States (class-level for singleton pattern)
    _circuit_state: Literal["closed", "open", "half_open"] = "closed"
    _failure_count: int = 0
    _success_count: int = 0
    _last_failure_time: Optional[datetime] = None

    def __init__(self, llm_service: Optional[LLMService] = None):
        """Initialisiere LLM OCR Review Service."""
        self.llm_service = llm_service or get_llm_service()

    def _check_circuit_breaker(self) -> bool:
        """
        Prüft ob Circuit Breaker Anfragen erlaubt.

        Returns:
            True wenn Anfrage erlaubt, False wenn Circuit offen
        """
        if self._circuit_state == "closed":
            return True

        if self._circuit_state == "open":
            # Prüfe ob Recovery-Timeout abgelaufen
            if self._last_failure_time:
                elapsed = (datetime.now(timezone.utc) - self._last_failure_time).total_seconds()
                if elapsed >= CIRCUIT_BREAKER_RECOVERY_TIMEOUT:
                    # Wechsel zu Half-Open - teste mit einer Anfrage
                    LLMOCRReviewService._circuit_state = "half_open"
                    LLMOCRReviewService._success_count = 0
                    logger.info("circuit_breaker_half_open", elapsed_seconds=elapsed)
                    return True
            return False

        # half_open - erlaube Anfragen zum Testen
        return True

    def _record_success(self) -> None:
        """Aufzeichnen eines erfolgreichen Aufrufs."""
        if self._circuit_state == "half_open":
            LLMOCRReviewService._success_count += 1
            if self._success_count >= CIRCUIT_BREAKER_SUCCESS_THRESHOLD:
                # Genug Erfolge - schließe Circuit
                LLMOCRReviewService._circuit_state = "closed"
                LLMOCRReviewService._failure_count = 0
                logger.info("circuit_breaker_closed", success_count=self._success_count)
        elif self._circuit_state == "closed":
            # Reset failure count bei Erfolg
            LLMOCRReviewService._failure_count = 0

    def _record_failure(self) -> None:
        """Aufzeichnen eines fehlgeschlagenen Aufrufs."""
        LLMOCRReviewService._failure_count += 1
        LLMOCRReviewService._last_failure_time = datetime.now(timezone.utc)

        if self._circuit_state == "half_open":
            # Fehler in Half-Open - zurück zu Open
            LLMOCRReviewService._circuit_state = "open"
            logger.warning("circuit_breaker_reopened", failure_count=self._failure_count)
        elif self._circuit_state == "closed":
            if self._failure_count >= CIRCUIT_BREAKER_FAILURE_THRESHOLD:
                # Zu viele Fehler - öffne Circuit
                LLMOCRReviewService._circuit_state = "open"
                logger.warning(
                    "circuit_breaker_opened",
                    failure_count=self._failure_count,
                    recovery_timeout_seconds=CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
                )

    def get_circuit_status(self) -> Dict[str, Any]:
        """
        Gibt den aktuellen Circuit Breaker Status zurück.

        Nützlich für Monitoring, Health-Checks und Prometheus-Metriken.

        Returns:
            Dict mit circuit_state, failure_count, last_failure_time, etc.
        """
        elapsed_since_failure = None
        time_until_recovery = None

        if self._last_failure_time:
            elapsed_since_failure = (
                datetime.now(timezone.utc) - self._last_failure_time
            ).total_seconds()
            if self._circuit_state == "open":
                time_until_recovery = max(
                    0,
                    CIRCUIT_BREAKER_RECOVERY_TIMEOUT - elapsed_since_failure
                )

        return {
            "circuit_state": self._circuit_state,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "failure_threshold": CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            "success_threshold": CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
            "recovery_timeout_seconds": CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
            "last_failure_time": self._last_failure_time.isoformat() if self._last_failure_time else None,
            "elapsed_since_failure_seconds": elapsed_since_failure,
            "time_until_recovery_seconds": time_until_recovery,
            "is_accepting_requests": self._check_circuit_breaker(),
        }

    def reset_circuit_breaker(self) -> None:
        """
        Setzt den Circuit Breaker manuell zurück.

        Sollte nur für Debugging/Admin-Zwecke verwendet werden.
        """
        logger.info(
            "circuit_breaker_manual_reset",
            previous_state=self._circuit_state,
            previous_failure_count=self._failure_count,
        )
        LLMOCRReviewService._circuit_state = "closed"
        LLMOCRReviewService._failure_count = 0
        LLMOCRReviewService._success_count = 0
        LLMOCRReviewService._last_failure_time = None

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
        Prüft ein Sample mit LLM.

        Args:
            db: Datenbank-Session
            sample: OCR Training Sample zum Prüfen
            auto_correct: Wenn True, werden Korrekturen automatisch angewendet

        Returns:
            LLMReviewResult mit Bewertung und ggf. Korrekturen
        """
        start_time = datetime.now(timezone.utc)

        # Text für Review vorbereiten
        text = sample.ground_truth_text or ""

        # Validierung
        if len(text) < self.MIN_TEXT_LENGTH:
            return LLMReviewResult(
                quality_score=0.0,
                issues_found=["Text zu kurz für Review"],
                recommendation="reject",
                reasoning="Der OCR-Text ist zu kurz für eine sinnvolle Bewertung.",
                confidence=1.0,
            )

        # Text kürzen wenn noetig
        if len(text) > self.MAX_TEXT_LENGTH:
            text = text[:self.MAX_TEXT_LENGTH] + "\n[...Text gekürzt...]"

        # LLM-Review durchführen
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
                **safe_error_log(e),
            )
            return LLMReviewResult(
                quality_score=0.0,
                issues_found=[f"LLM-Review fehlgeschlagen: {str(e)}"],
                recommendation="needs_human",
                reasoning=safe_error_detail(e, "LLM-Review"),
                confidence=0.0,
            )

    async def review_sample_by_id(
        self,
        db: AsyncSession,
        sample_id: UUID,
        auto_correct: bool = True,
    ) -> Optional[LLMReviewResult]:
        """
        Prüft ein Sample anhand seiner ID.

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
            .order_by(OCRTrainingSample.business_priority.desc())  # Hohe Priorität zuerst
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
                    **safe_error_log(e),
                )
                result.errors += 1

        # Durchschnittliche Qualität berechnen
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
        Statistiken über LLM-Reviews.

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

        # Durchschnittliche Qualität der reviewed Samples
        # Lade Samples mit Results und berechne Durchschnitt im Python-Code
        reviewed_result = await db.execute(
            select(OCRTrainingSample.llm_review_result)
            .where(OCRTrainingSample.deleted_at.is_(None))
            .where(OCRTrainingSample.llm_review_status.notin_(["pending", None]))
            .where(OCRTrainingSample.llm_review_result.isnot(None))
            .limit(1000)  # Begrenze für Performance
        )
        reviewed_samples = reviewed_result.scalars().all()

        quality_scores = []
        for result in reviewed_samples:
            if isinstance(result, dict) and "quality_score" in result:
                try:
                    score = float(result["quality_score"])
                    quality_scores.append(score)
                except (TypeError, ValueError) as e:
                    logger.debug(
                        "quality_score_parse_failed",
                        error_type=type(e).__name__,
                    )

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

    @retry(
        stop=stop_after_attempt(LLM_MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=LLM_RETRY_MIN_WAIT, max=LLM_RETRY_MAX_WAIT),
        retry=retry_if_exception_type((
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.ReadError,
            ConnectionError,
            asyncio.TimeoutError,
        )),
        before_sleep=before_sleep_log(logger, log_level=30),  # WARNING level
        reraise=True,
    )
    async def _call_llm_review_with_retry(
        self,
        text: str,
        doc_type: str,
    ) -> LLMReviewResult:
        """Ruft das LLM für die Review auf mit automatischem Retry.

        Retry bei:
        - Timeout (Ollama nicht erreichbar)
        - Connection Errors (Service neu gestartet)
        - Read Errors (Verbindung unterbrochen)

        Args:
            text: OCR-Text zur Prüfung
            doc_type: Dokumenttyp

        Returns:
            LLMReviewResult mit Bewertung

        Raises:
            RetryError: Nach allen fehlgeschlagenen Versuchen
        """
        # Prompt zusammenbauen
        user_prompt = REVIEW_USER_PROMPT.format(
            doc_type=doc_type,
            text=text,
        )

        messages = [
            LLMMessage(role="system", content=REVIEW_SYSTEM_PROMPT),
            LLMMessage(role="user", content=user_prompt),
        ]

        # LLM aufrufen (mit Thinking Mode für bessere Analyse)
        response = await self.llm_service.generate(
            messages=messages,
            context_type=LLMContextType.EXTRACTION,
            enable_thinking=True,
            temperature=0.3,  # Niedrig für konsistente Bewertungen
        )

        # Antwort parsen
        return self._parse_llm_response(response.content)

    async def _call_llm_review(
        self,
        text: str,
        doc_type: str,
    ) -> LLMReviewResult:
        """Ruft das LLM für die Review auf.

        Wrapper mit Circuit Breaker und Error-Handling für Retry-Failures.
        Bei geöffnetem Circuit wird direkt ein Fallback-Ergebnis zurückgegeben,
        um Blocking zu vermeiden wenn Ollama nicht erreichbar ist.
        """
        # Circuit Breaker prüfen
        if not self._check_circuit_breaker():
            logger.warning(
                "llm_review_circuit_open",
                doc_type=doc_type,
                text_length=len(text),
                circuit_state=self._circuit_state,
            )
            # Fast-fail: Circuit ist offen, gib Fallback zurück
            return LLMReviewResult(
                quality_score=5.0,  # Neutraler Score
                issues_found=["LLM-Service temporär nicht verfügbar (Circuit Breaker offen)"],
                recommendation="needs_human",
                reasoning=(
                    "Der LLM-Service ist temporär nicht erreichbar. "
                    "Manuelle Review erforderlich. "
                    f"Nächster Versuch in {CIRCUIT_BREAKER_RECOVERY_TIMEOUT}s."
                ),
                confidence=0.0,
            )

        try:
            result = await self._call_llm_review_with_retry(text, doc_type)
            # Erfolg aufzeichnen
            self._record_success()
            return result
        except RetryError as e:
            # Fehler aufzeichnen
            self._record_failure()
            logger.error(
                "llm_review_all_retries_failed",
                doc_type=doc_type,
                text_length=len(text),
                error=str(e.last_attempt.exception()) if e.last_attempt else "unknown",
                circuit_state=self._circuit_state,
                failure_count=self._failure_count,
            )
            # Fallback: Menschliche Review erforderlich
            return LLMReviewResult(
                quality_score=0.0,
                issues_found=["LLM-Review nach mehreren Versuchen fehlgeschlagen"],
                recommendation="needs_human",
                reasoning=f"Technischer Fehler: LLM nicht erreichbar nach {LLM_MAX_RETRIES} Versuchen",
                confidence=0.0,
            )
        except Exception as e:
            # Fehler aufzeichnen
            self._record_failure()
            logger.error(
                "llm_review_unexpected_error",
                doc_type=doc_type,
                **safe_error_log(e),
                circuit_state=self._circuit_state,
                failure_count=self._failure_count,
            )
            return LLMReviewResult(
                quality_score=0.0,
                issues_found=[f"Unerwarteter Fehler: {str(e)}"],
                recommendation="needs_human",
                reasoning=safe_error_detail(e, "LLM-Review"),
                confidence=0.0,
            )

    def _parse_llm_response(self, content: str) -> LLMReviewResult:
        """Parst die strukturierte LLM-Antwort."""

        # Quality Score extrahieren mit Validierung
        quality_match = re.search(r'<quality_score>\s*(\d+(?:\.\d+)?)\s*</quality_score>', content)
        quality_score = 5.0  # Default
        if quality_match:
            try:
                parsed_score = float(quality_match.group(1))
                # Validierung: Score muss zwischen 0 und 10 liegen
                if 0.0 <= parsed_score <= 10.0:
                    quality_score = parsed_score
                else:
                    logger.warning(
                        "llm_review_invalid_quality_score",
                        parsed_score=parsed_score,
                        using_default=5.0
                    )
            except (ValueError, TypeError):
                logger.warning("llm_review_score_parse_failed")

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
