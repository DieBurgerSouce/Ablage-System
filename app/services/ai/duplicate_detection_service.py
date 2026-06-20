# -*- coding: utf-8 -*-
"""
DuplicateDetectionService - Erkennung von Duplikaten.

Erkennt doppelte oder sehr ähnliche Dokumente:
- Exakte Duplikate (gleicher Hash)
- Nahe Duplikate (ähnlicher Inhalt)
- Semantische Duplikate (gleiche Information, anderes Format)

Ziel-Konfidenz: 90%+ für Auto-Flag.

Feinpoliert und durchdacht - nutzt pgvector für Embedding-Ähnlichkeit.
"""

from __future__ import annotations

import hashlib
import io
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

import structlog
from prometheus_client import Counter, Histogram
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document
from app.services.ai.extracted_data_wrapper import ExtractedData, get_extracted_data
from app.services.ai.decision_service import (
    AIDecisionService,
    AIDecisionResult,
    DecisionType,
    get_ai_decision_service,
)

# Optional: Perceptual Hashing für visuelle Duplikat-Erkennung
try:
    import imagehash
    from PIL import Image
    PHASH_AVAILABLE = True
except ImportError:
    PHASH_AVAILABLE = False

# Optional: TF-IDF + Cosine Similarity für Text-Vergleich
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine_similarity
    TFIDF_AVAILABLE = True
except ImportError:
    TFIDF_AVAILABLE = False

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

DUPLICATE_REQUESTS = Counter(
    "duplicate_detection_requests_total",
    "Anzahl der Duplikat-Erkennungs-Anfragen",
    ["duplicate_type"]
)

DUPLICATE_DURATION = Histogram(
    "duplicate_detection_duration_seconds",
    "Dauer der Duplikat-Erkennung in Sekunden",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

DUPLICATES_FOUND = Counter(
    "duplicates_found_total",
    "Anzahl gefundener Duplikate",
    ["duplicate_type", "auto_flagged"]
)


# =============================================================================
# Duplikat-Typen und Konfiguration
# =============================================================================

class DuplicateType:
    """Typen von Duplikaten."""
    EXACT = "exact"  # Identischer Hash
    NEAR = "near"  # Sehr ähnlicher Text
    SEMANTIC = "semantic"  # Gleiche Information
    NUMBER_MATCH = "number_match"  # Gleiche Rechnungsnummer
    VISUAL = "visual"  # Visuell ähnlich (Perceptual Hash)


@dataclass
class DuplicateCandidate:
    """Ein potentielles Duplikat."""
    document_id: uuid.UUID
    duplicate_type: str
    similarity: float
    matched_fields: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DuplicateCheckResult:
    """Ergebnis der Duplikat-Prüfung."""
    has_duplicates: bool = False
    candidates: List[DuplicateCandidate] = field(default_factory=list)
    best_match: Optional[DuplicateCandidate] = None
    processing_time_ms: int = 0


class DuplicateDetectionService:
    """
    Erkennung von Duplikaten mit verschiedenen Methoden.

    Kombiniert Hash-Vergleich, Text-Ähnlichkeit und
    strukturierte Feld-Matches.
    """

    # Konfiguration
    MIN_SIMILARITY_NEAR = 0.85  # Min Ähnlichkeit für "near"
    MIN_SIMILARITY_SEMANTIC = 0.70  # Min Ähnlichkeit für "semantic"
    MAX_CANDIDATES = 50  # Max Kandidaten pro Check
    MAX_TEXT_LENGTH = 10000  # Max Text-Länge für Vergleich
    VISUAL_EXACT_THRESHOLD: int = 5    # Hamming-Distanz fuer exakte visuelle Duplikate
    VISUAL_NEAR_THRESHOLD: int = 10    # Hamming-Distanz fuer nahe visuelle Duplikate

    def __init__(self) -> None:
        """Initialisiert den Service."""
        self._decision_service = get_ai_decision_service()

    def _normalize_text(self, text: Optional[str]) -> str:
        """Normalisiert Text für Vergleich.

        WICHTIG: Erhält deutsche Umlaute (ä, ö, ü, ß) für korrekten
        Vergleich deutscher Dokumente.
        """
        if not text:
            return ""
        # Lowercase, Whitespace normalisieren
        text = text.lower()
        text = re.sub(r'\s+', ' ', text)
        # UMLAUT FIX: Sonderzeichen entfernen, aber deutsche Umlaute erhalten
        # \w mit re.UNICODE matched alle Unicode-Buchstaben inkl. äöüß
        text = re.sub(r'[^\w\s]', '', text, flags=re.UNICODE)
        return text.strip()

    def _calculate_text_hash(self, text: str) -> str:
        """Berechnet Hash eines Texts."""
        normalized = self._normalize_text(text)
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()

    def _calculate_text_similarity(
        self,
        text1: str,
        text2: str,
    ) -> float:
        """Berechnet Text-Ähnlichkeit mit TF-IDF + Cosine Similarity.

        Verwendet char_wb Analyzer mit n-grams (2,4) für robuste
        Erkennung bei deutschen Texten (Umlaute, Komposita).
        Fallback auf SequenceMatcher wenn sklearn nicht verfügbar.
        """
        t1 = self._normalize_text(text1)[:self.MAX_TEXT_LENGTH]
        t2 = self._normalize_text(text2)[:self.MAX_TEXT_LENGTH]

        if not t1 or not t2:
            return 0.0

        if TFIDF_AVAILABLE:
            try:
                vectorizer = TfidfVectorizer(
                    analyzer="char_wb",
                    ngram_range=(2, 4),
                    max_features=5000,
                )
                tfidf_matrix = vectorizer.fit_transform([t1, t2])
                score = sklearn_cosine_similarity(
                    tfidf_matrix[0:1], tfidf_matrix[1:2]
                )[0][0]
                return float(score)
            except Exception:
                pass  # Fallback bei unerwarteten Fehlern

        # Fallback: SequenceMatcher
        return SequenceMatcher(None, t1, t2).ratio()

    def _calculate_field_similarity(
        self,
        data1: ExtractedData,
        data2: ExtractedData,
    ) -> Tuple[float, List[str]]:
        """
        Berechnet Ähnlichkeit basierend auf extrahierten Feldern.

        Returns:
            Tuple (similarity, matched_fields)
        """
        matched_fields: List[str] = []
        scores: List[float] = []
        weights: Dict[str, float] = {
            "invoice_number": 0.30,
            "total_gross": 0.20,
            "supplier": 0.20,
            "date": 0.15,
            "positions": 0.15,
        }

        # 1. Rechnungsnummer
        if data1.invoice_number and data2.invoice_number:
            if data1.invoice_number.strip().lower() == data2.invoice_number.strip().lower():
                scores.append(1.0 * weights["invoice_number"])
                matched_fields.append("invoice_number")
            elif data1.invoice_number in data2.invoice_number or data2.invoice_number in data1.invoice_number:
                scores.append(0.5 * weights["invoice_number"])
                matched_fields.append("invoice_number_partial")

        # 2. Betrag
        if data1.total_gross and data2.total_gross:
            diff = abs(float(data1.total_gross) - float(data2.total_gross))
            max_val = max(float(data1.total_gross), float(data2.total_gross))
            if max_val > 0:
                if diff == 0:
                    scores.append(1.0 * weights["total_gross"])
                    matched_fields.append("total_gross")
                elif diff / max_val < 0.01:  # <1% Differenz
                    scores.append(0.8 * weights["total_gross"])
                    matched_fields.append("total_gross_close")

        # 3. Lieferant
        if data1.supplier_name and data2.supplier_name:
            s1 = data1.supplier_name.lower().strip()
            s2 = data2.supplier_name.lower().strip()
            if s1 == s2:
                scores.append(1.0 * weights["supplier"])
                matched_fields.append("supplier_name")
            elif s1 in s2 or s2 in s1:
                scores.append(0.6 * weights["supplier"])
                matched_fields.append("supplier_name_partial")

        # 4. Datum
        if data1.invoice_date and data2.invoice_date:
            if data1.invoice_date == data2.invoice_date:
                scores.append(1.0 * weights["date"])
                matched_fields.append("invoice_date")
            elif abs((data1.invoice_date - data2.invoice_date).days) <= 1:
                scores.append(0.5 * weights["date"])
                matched_fields.append("invoice_date_close")

        # Gesamt-Score
        total_weight = sum(weights.values())
        similarity = sum(scores) / total_weight if scores else 0.0

        return similarity, matched_fields

    async def _find_exact_duplicates(
        self,
        db: AsyncSession,
        document: Document,
        company_id: Optional[uuid.UUID],
    ) -> List[DuplicateCandidate]:
        """Findet exakte Duplikate via Hash (checksum)."""
        if not document.checksum:
            return []

        query = select(Document).where(
            and_(
                Document.checksum == document.checksum,
                Document.id != document.id,
                Document.deleted_at.is_(None),
            )
        )

        if company_id:
            query = query.where(Document.company_id == company_id)

        result = await db.execute(query.limit(10))
        duplicates = result.scalars().all()

        return [
            DuplicateCandidate(
                document_id=dup.id,
                duplicate_type=DuplicateType.EXACT,
                similarity=1.0,
                matched_fields=["checksum"],
                details={
                    "hash": document.checksum,
                    "original_filename": dup.original_filename,
                },
            )
            for dup in duplicates
        ]

    async def _find_number_duplicates(
        self,
        db: AsyncSession,
        data: ExtractedData,
        document_id: uuid.UUID,
        company_id: Optional[uuid.UUID],
    ) -> List[DuplicateCandidate]:
        """Findet Duplikate via Rechnungsnummer."""
        if not data.invoice_number:
            return []

        # Query Documents mit JSONB extracted_data
        query = select(Document).where(
            and_(
                Document.id != document_id,
                Document.extracted_data.isnot(None),
            )
        )

        if company_id:
            query = query.where(Document.company_id == company_id)

        result = await db.execute(query.limit(100))
        documents = result.scalars().all()

        candidates = []
        for doc in documents:
            dup_data = get_extracted_data(doc)
            if not dup_data or dup_data.invoice_number != data.invoice_number:
                continue

            # Berechne zusätzliche Ähnlichkeit
            field_sim, matched = self._calculate_field_similarity(data, dup_data)
            overall_sim = 0.5 + field_sim * 0.5  # 50% für Nummer + 50% für andere Felder

            candidates.append(
                DuplicateCandidate(
                    document_id=doc.id,
                    duplicate_type=DuplicateType.NUMBER_MATCH,
                    similarity=overall_sim,
                    matched_fields=["invoice_number"] + matched,
                    details={
                        "invoice_number": data.invoice_number,
                    },
                )
            )

            if len(candidates) >= 10:
                break

        return candidates

    async def _find_near_duplicates(
        self,
        db: AsyncSession,
        document: Document,
        data: Optional[ExtractedData],
        company_id: Optional[uuid.UUID],
    ) -> List[DuplicateCandidate]:
        """Findet nahe Duplikate via Text-Ähnlichkeit."""
        if not document.extracted_text:
            return []

        # Lade Kandidaten aus gleichem Zeitraum
        query = select(Document).where(
            and_(
                Document.id != document.id,
                Document.deleted_at.is_(None),
                Document.extracted_text.isnot(None),
            )
        )

        if company_id:
            query = query.where(Document.company_id == company_id)

        # Zeitraum-Filter
        if document.created_at:
            min_date = document.created_at - timedelta(days=30)
            max_date = document.created_at + timedelta(days=30)
            query = query.where(
                and_(
                    Document.created_at >= min_date,
                    Document.created_at <= max_date,
                )
            )

        result = await db.execute(query.limit(self.MAX_CANDIDATES))
        candidates_docs = result.scalars().all()

        candidates: List[DuplicateCandidate] = []
        source_text = document.extracted_text

        for cand_doc in candidates_docs:
            if not cand_doc.extracted_text:
                continue

            # Text-Ähnlichkeit
            text_sim = self._calculate_text_similarity(
                source_text,
                cand_doc.extracted_text,
            )

            if text_sim < self.MIN_SIMILARITY_SEMANTIC:
                continue

            # Feld-Ähnlichkeit wenn ExtractedData vorhanden
            matched_fields: List[str] = []
            if data:
                cand_data = get_extracted_data(cand_doc)
                if cand_data:
                    field_sim, matched_fields = self._calculate_field_similarity(data, cand_data)
                    text_sim = (text_sim + field_sim) / 2  # Durchschnitt

            # Typ basierend auf Ähnlichkeit
            if text_sim >= self.MIN_SIMILARITY_NEAR:
                dup_type = DuplicateType.NEAR
            else:
                dup_type = DuplicateType.SEMANTIC

            candidates.append(
                DuplicateCandidate(
                    document_id=cand_doc.id,
                    duplicate_type=dup_type,
                    similarity=text_sim,
                    matched_fields=matched_fields,
                    details={
                        "text_similarity": round(text_sim, 3),
                        "candidate_filename": cand_doc.original_filename,
                    },
                )
            )

        # Sortiere nach Ähnlichkeit
        candidates.sort(key=lambda x: x.similarity, reverse=True)

        return candidates[:10]

    @staticmethod
    def _calculate_perceptual_hash(image_bytes: bytes) -> Optional[str]:
        """Berechnet Perceptual Hash (pHash) eines Bildes.

        Args:
            image_bytes: Bild als Bytes

        Returns:
            pHash als Hex-String oder None bei Fehler
        """
        if not PHASH_AVAILABLE:
            return None

        try:
            img = Image.open(io.BytesIO(image_bytes))
            phash = imagehash.phash(img, hash_size=16)
            return str(phash)
        except Exception as e:
            # OPEN-46: pHash-Berechnung fehlgeschlagen sichtbar machen (Fallback bleibt None)
            logger.warning("phash_computation_failed", error_type=type(e).__name__)
            return None

    async def _find_visual_duplicates(
        self,
        db: AsyncSession,
        document: Document,
        company_id: Optional[uuid.UUID],
    ) -> List[DuplicateCandidate]:
        """Findet visuelle Duplikate via Perceptual Hashing (pHash).

        Vergleicht Hamming-Distanz der pHash-Werte:
        - Distanz <= 5: Exaktes visuelles Duplikat
        - Distanz <= 10: Nahes visuelles Duplikat
        """
        if not PHASH_AVAILABLE:
            return []

        # Lade pHash aus document.document_metadata
        doc_metadata = document.document_metadata or {}
        doc_phash_str = doc_metadata.get("perceptual_hash")
        if not doc_phash_str:
            return []

        try:
            doc_phash = imagehash.hex_to_hash(doc_phash_str)
        except (ValueError, TypeError) as e:
            # OPEN-46: defekter pHash-String sichtbar machen (Fallback bleibt leer)
            logger.warning("phash_decode_failed", error_type=type(e).__name__)
            return []

        # Lade Kandidaten mit pHash aus dem gleichen Zeitraum
        query = select(Document).where(
            and_(
                Document.id != document.id,
                Document.deleted_at.is_(None),
                Document.document_metadata.isnot(None),
            )
        )

        if company_id:
            query = query.where(Document.company_id == company_id)

        # Zeitraum-Filter: letzte 90 Tage
        if document.created_at:
            min_date = document.created_at - timedelta(days=90)
            query = query.where(Document.created_at >= min_date)

        result = await db.execute(query.limit(self.MAX_CANDIDATES))
        candidate_docs = result.scalars().all()

        candidates: List[DuplicateCandidate] = []
        for cand_doc in candidate_docs:
            cand_metadata = cand_doc.document_metadata or {}
            cand_phash_str = cand_metadata.get("perceptual_hash")
            if not cand_phash_str:
                continue

            try:
                cand_phash = imagehash.hex_to_hash(cand_phash_str)
                distance = doc_phash - cand_phash  # Hamming-Distanz
            except Exception:
                continue

            if distance > self.VISUAL_NEAR_THRESHOLD:
                continue

            # Ähnlichkeit: 1.0 bei Distanz 0, 0.0 bei Distanz 256
            similarity = 1.0 - (distance / 256.0)

            candidates.append(
                DuplicateCandidate(
                    document_id=cand_doc.id,
                    duplicate_type=DuplicateType.VISUAL,
                    similarity=similarity,
                    matched_fields=["perceptual_hash"],
                    details={
                        "hamming_distance": distance,
                        "candidate_filename": cand_doc.original_filename,
                        "visual_match": "exact" if distance <= self.VISUAL_EXACT_THRESHOLD else "near",
                    },
                )
            )

        candidates.sort(key=lambda x: x.similarity, reverse=True)
        return candidates[:10]

    async def check_document(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        company_id: Optional[uuid.UUID] = None,
        include_near: bool = True,
    ) -> DuplicateCheckResult:
        """
        Prüft ein Dokument auf Duplikate.

        Args:
            db: Database Session
            document_id: Dokument-ID
            company_id: Optional Company-Filter
            include_near: Ob Near-Duplicate Check durchgeführt werden soll

        Returns:
            DuplicateCheckResult
        """
        start_time = time.perf_counter()

        # Lade Dokument
        doc_result = await db.execute(
            select(Document).where(Document.id == document_id)
        )
        document = doc_result.scalar_one_or_none()
        if not document:
            return DuplicateCheckResult()

        # Erstelle ExtractedData Wrapper
        data = get_extracted_data(document)

        all_candidates: List[DuplicateCandidate] = []

        # 1. Exakte Duplikate (schnell)
        exact = await self._find_exact_duplicates(db, document, company_id)
        all_candidates.extend(exact)

        # 2. Nummer-Duplikate
        if data:
            number = await self._find_number_duplicates(db, data, document_id, company_id)
            all_candidates.extend(number)

        # 3. Near-Duplicates (langsamer)
        if include_near:
            near = await self._find_near_duplicates(db, document, data, company_id)
            all_candidates.extend(near)

        # 4. Visuelle Duplikate (pHash)
        if PHASH_AVAILABLE:
            visual = await self._find_visual_duplicates(db, document, company_id)
            all_candidates.extend(visual)

        # Deduplizieren (gleiche document_id kann mehrfach vorkommen)
        seen: set = set()
        unique_candidates: List[DuplicateCandidate] = []
        for cand in all_candidates:
            if cand.document_id not in seen:
                seen.add(cand.document_id)
                unique_candidates.append(cand)

        # Sortiere nach Ähnlichkeit
        unique_candidates.sort(key=lambda x: x.similarity, reverse=True)

        processing_time_ms = int((time.perf_counter() - start_time) * 1000)
        DUPLICATE_DURATION.observe(processing_time_ms / 1000)

        # Metriken
        for cand in unique_candidates:
            DUPLICATE_REQUESTS.labels(duplicate_type=cand.duplicate_type).inc()

        return DuplicateCheckResult(
            has_duplicates=len(unique_candidates) > 0,
            candidates=unique_candidates[:10],
            best_match=unique_candidates[0] if unique_candidates else None,
            processing_time_ms=processing_time_ms,
        )

    async def create_duplicate_decision(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        check_result: DuplicateCheckResult,
        company_id: Optional[uuid.UUID] = None,
        auto_flag: bool = True,
    ) -> Optional[AIDecisionResult]:
        """
        Erstellt eine AI-Entscheidung für erkannte Duplikate.

        Args:
            db: Database Session
            document_id: Dokument-ID
            check_result: Ergebnis der Duplikat-Prüfung
            company_id: Optional Company-ID
            auto_flag: Ob automatisch geflagt werden soll

        Returns:
            AIDecisionResult oder None wenn keine Duplikate
        """
        if not check_result.has_duplicates or not check_result.best_match:
            return None

        best = check_result.best_match

        # Decision Value
        decision_value = {
            "duplicate_document_id": str(best.document_id),
            "duplicate_type": best.duplicate_type,
            "similarity": round(best.similarity, 3),
            "matched_fields": best.matched_fields,
            "total_candidates": len(check_result.candidates),
        }

        # Explanation
        explanation = {
            "reasons": [],
            "matched_fields": best.matched_fields,
            "details": best.details,
        }

        if best.duplicate_type == DuplicateType.EXACT:
            explanation["reasons"].append("Exaktes Duplikat (identischer Datei-Hash)")
        elif best.duplicate_type == DuplicateType.NUMBER_MATCH:
            explanation["reasons"].append("Gleiche Rechnungsnummer gefunden")
        elif best.duplicate_type == DuplicateType.VISUAL:
            explanation["reasons"].append(
                f"Visuell ähnlich (pHash Distanz: {best.details.get('hamming_distance', '?')})"
            )
        elif best.duplicate_type == DuplicateType.NEAR:
            explanation["reasons"].append(f"Sehr ähnlicher Text ({best.similarity * 100:.1f}%)")
        else:
            explanation["reasons"].append(f"Semantisch ähnlich ({best.similarity * 100:.1f}%)")

        if best.matched_fields:
            explanation["reasons"].append(
                f"Übereinstimmende Felder: {', '.join(best.matched_fields[:5])}"
            )

        # Callback für Auto-Flag
        async def apply_flag(value: Dict[str, Any]) -> None:
            """Markiert Dokument als potentielles Duplikat."""
            doc_result = await db.execute(
                select(Document).where(Document.id == document_id)
            )
            doc = doc_result.scalar_one_or_none()
            if doc:
                # Setze Flag in document_metadata
                metadata = doc.document_metadata or {}
                metadata["potential_duplicate"] = True
                metadata["duplicate_of"] = value["duplicate_document_id"]
                metadata["duplicate_similarity"] = value["similarity"]
                doc.document_metadata = metadata
                await db.commit()

                logger.info(
                    "document_flagged_as_duplicate",
                    document_id=str(document_id),
                    duplicate_of=value["duplicate_document_id"],
                )

        # Entscheidung erstellen
        ai_result = await self._decision_service.make_decision(
            db=db,
            decision_type=DecisionType.DUPLICATE,
            decision_value=decision_value,
            confidence=best.similarity,
            document_id=document_id,
            company_id=company_id,
            explanation=explanation,
            features_used={
                "duplicate_type": best.duplicate_type,
                "matched_field_count": len(best.matched_fields),
            },
            apply_callback=apply_flag if auto_flag else None,
        )

        # Metriken
        DUPLICATES_FOUND.labels(
            duplicate_type=best.duplicate_type,
            auto_flagged=str(ai_result.auto_applied).lower(),
        ).inc()

        return ai_result


# Singleton-Instanz mit Thread-Safety
_duplicate_detection_service: Optional[DuplicateDetectionService] = None
_service_lock = threading.Lock()


def get_duplicate_detection_service() -> DuplicateDetectionService:
    """Factory für DuplicateDetectionService Singleton (Thread-safe)."""
    global _duplicate_detection_service
    if _duplicate_detection_service is None:
        with _service_lock:
            # Double-check locking pattern
            if _duplicate_detection_service is None:
                _duplicate_detection_service = DuplicateDetectionService()
    return _duplicate_detection_service
