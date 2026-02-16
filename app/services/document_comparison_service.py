# -*- coding: utf-8 -*-
"""
Document Comparison Service - Vergleich von Dokumenten.

Phase 9.1: Dream Features

Ermöglicht:
- Textbasierte Vergleiche (Diff)
- Strukturierte Feld-Vergleiche
- Ähnlichkeitserkennung
- Versions-Vergleiche eines Dokuments
- Visual Diff Reports

Anwendungsfaelle:
- Zwei Rechnungen vergleichen
- Änderungen zwischen Versionen erkennen
- Ähnliche Dokumente finden
- Duplikat-Erkennung
"""

from __future__ import annotations

import difflib
import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Tuple, Set, Union
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, BusinessEntity
from app.db.models_versioning import DocumentVersion

logger = structlog.get_logger(__name__)


# ============================================================================
# Enums and Types
# ============================================================================


class ComparisonType(str, Enum):
    """Typ des Vergleichs."""
    TEXT = "text"  # Reiner Text-Vergleich
    STRUCTURED = "structured"  # Strukturierte Felder vergleichen
    VISUAL = "visual"  # Visueller Vergleich (Bild-basiert)
    HYBRID = "hybrid"  # Text + Strukturiert kombiniert


class DifferenceType(str, Enum):
    """Art der Abweichung."""
    ADDED = "added"  # Neu hinzugefuegt
    REMOVED = "removed"  # Entfernt
    CHANGED = "changed"  # Geändert
    UNCHANGED = "unchanged"  # Unverändert


class FieldCategory(str, Enum):
    """Kategorie des verglichenen Feldes."""
    IDENTIFIER = "identifier"  # Rechnungsnr, Bestellnr
    AMOUNT = "amount"  # Betraege
    DATE = "date"  # Datumsfelder
    ENTITY = "entity"  # Firmen, Personen
    ADDRESS = "address"  # Adressen
    TEXT = "text"  # Freitext
    METADATA = "metadata"  # Metadaten


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class TextDifference:
    """Einzelne Text-Differenz."""
    diff_type: DifferenceType
    line_number: Optional[int]
    old_text: Optional[str]
    new_text: Optional[str]
    context_before: Optional[str] = None
    context_after: Optional[str] = None


@dataclass
class FieldChange:
    """Änderung in einem strukturierten Feld."""
    field_name: str
    field_category: FieldCategory
    old_value: object
    new_value: object
    diff_type: DifferenceType
    confidence: float = 1.0
    is_critical: bool = False  # Kritische Änderung (z.B. Betrag)


@dataclass
class SimilarDocument:
    """Ähnliches Dokument."""
    document_id: UUID
    filename: str
    document_type: str
    similarity_score: float
    matching_fields: List[str]
    entity_name: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass
class ComparisonResult:
    """Ergebnis eines Dokumenten-Vergleichs."""
    document_1_id: UUID
    document_2_id: UUID
    comparison_type: ComparisonType

    # Scores
    overall_similarity: float  # 0.0 - 1.0
    text_similarity: float
    structure_similarity: float

    # Differenzen
    text_differences: List[TextDifference]
    field_changes: List[FieldChange]

    # Statistiken
    total_changes: int
    critical_changes: int
    additions: int
    removals: int
    modifications: int

    # Metadaten
    comparison_time_ms: int
    warnings: List[str] = field(default_factory=list)


@dataclass
class DiffReport:
    """Vollständiger Diff-Report."""
    comparison: ComparisonResult
    document_1_info: Dict[str, object]
    document_2_info: Dict[str, object]
    summary: str
    recommendations: List[str]
    generated_at: datetime = field(default_factory=datetime.utcnow)


# ============================================================================
# Document Comparison Service
# ============================================================================


class DocumentComparisonService:
    """Service für Dokumenten-Vergleiche.

    Vergleicht zwei Dokumente auf verschiedenen Ebenen:
    - Text-Level: Zeilenweiser Vergleich
    - Struktur-Level: Extrahierte Felder vergleichen
    - Semantik-Level: Ähnlichkeitsberechnung

    Anwendung:
    - Versions-Vergleiche
    - Duplikat-Erkennung
    - Anomalie-Detection
    """

    # Kritische Felder die bei Änderung markiert werden
    CRITICAL_FIELDS: Set[str] = {
        "total_gross", "total_net", "vat_amount", "invoice_number",
        "order_number", "iban", "bic", "vat_id", "customer_number"
    }

    # Felder die für Ähnlichkeitsberechnung relevant sind
    SIMILARITY_FIELDS: List[str] = [
        "invoice_number", "customer_number", "total_gross", "invoice_date",
        "vendor_name", "customer_name", "vat_id"
    ]

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Service.

        Args:
            db: Async Database Session
        """
        self.db = db

    # ========================================================================
    # Main Comparison Methods
    # ========================================================================

    async def compare_documents(
        self,
        doc_id_1: UUID,
        doc_id_2: UUID,
        comparison_type: ComparisonType = ComparisonType.HYBRID,
        include_context: bool = True
    ) -> ComparisonResult:
        """Vergleicht zwei Dokumente.

        Args:
            doc_id_1: ID des ersten Dokuments
            doc_id_2: ID des zweiten Dokuments
            comparison_type: Art des Vergleichs
            include_context: Kontext um Änderungen anzeigen

        Returns:
            ComparisonResult mit allen Differenzen

        Raises:
            ValueError: Wenn ein Dokument nicht gefunden wird
        """
        import time
        start_time = time.time()

        # Dokumente laden
        doc1 = await self._get_document(doc_id_1)
        doc2 = await self._get_document(doc_id_2)

        if not doc1:
            raise ValueError(f"Dokument {doc_id_1} nicht gefunden")
        if not doc2:
            raise ValueError(f"Dokument {doc_id_2} nicht gefunden")

        # Text-Vergleich
        text_diffs: List[TextDifference] = []
        text_similarity = 0.0

        if comparison_type in (ComparisonType.TEXT, ComparisonType.HYBRID):
            text_diffs, text_similarity = self._compare_text(
                doc1.extracted_text or "",
                doc2.extracted_text or "",
                include_context
            )

        # Struktur-Vergleich
        field_changes: List[FieldChange] = []
        structure_similarity = 0.0

        if comparison_type in (ComparisonType.STRUCTURED, ComparisonType.HYBRID):
            field_changes, structure_similarity = self._compare_structure(
                doc1.extracted_data or {},
                doc2.extracted_data or {}
            )

        # Gesamt-Ähnlichkeit berechnen
        if comparison_type == ComparisonType.TEXT:
            overall_similarity = text_similarity
        elif comparison_type == ComparisonType.STRUCTURED:
            overall_similarity = structure_similarity
        else:
            # Hybrid: Gewichteter Durchschnitt
            overall_similarity = (text_similarity * 0.4 + structure_similarity * 0.6)

        # Statistiken
        additions = sum(1 for d in text_diffs if d.diff_type == DifferenceType.ADDED)
        additions += sum(1 for f in field_changes if f.diff_type == DifferenceType.ADDED)

        removals = sum(1 for d in text_diffs if d.diff_type == DifferenceType.REMOVED)
        removals += sum(1 for f in field_changes if f.diff_type == DifferenceType.REMOVED)

        modifications = sum(1 for d in text_diffs if d.diff_type == DifferenceType.CHANGED)
        modifications += sum(1 for f in field_changes if f.diff_type == DifferenceType.CHANGED)

        critical_changes = sum(1 for f in field_changes if f.is_critical)

        processing_time = int((time.time() - start_time) * 1000)

        logger.info(
            "document_comparison_complete",
            doc_1=str(doc_id_1),
            doc_2=str(doc_id_2),
            overall_similarity=round(overall_similarity, 3),
            total_changes=additions + removals + modifications,
            critical_changes=critical_changes,
            processing_time_ms=processing_time
        )

        return ComparisonResult(
            document_1_id=doc_id_1,
            document_2_id=doc_id_2,
            comparison_type=comparison_type,
            overall_similarity=overall_similarity,
            text_similarity=text_similarity,
            structure_similarity=structure_similarity,
            text_differences=text_diffs,
            field_changes=field_changes,
            total_changes=additions + removals + modifications,
            critical_changes=critical_changes,
            additions=additions,
            removals=removals,
            modifications=modifications,
            comparison_time_ms=processing_time
        )

    async def generate_diff_report(
        self,
        doc_id_1: UUID,
        doc_id_2: UUID,
        comparison_type: ComparisonType = ComparisonType.HYBRID
    ) -> DiffReport:
        """Generiert einen vollständigen Diff-Report.

        Args:
            doc_id_1: ID des ersten Dokuments
            doc_id_2: ID des zweiten Dokuments
            comparison_type: Art des Vergleichs

        Returns:
            DiffReport mit Zusammenfassung und Empfehlungen
        """
        # Vergleich durchführen
        comparison = await self.compare_documents(
            doc_id_1, doc_id_2, comparison_type
        )

        # Dokument-Infos laden
        doc1 = await self._get_document(doc_id_1)
        doc2 = await self._get_document(doc_id_2)

        doc1_info = {
            "id": str(doc_id_1),
            "filename": doc1.filename if doc1 else "Unbekannt",
            "document_type": doc1.document_type if doc1 else "Unbekannt",
            "created_at": doc1.created_at.isoformat() if doc1 and doc1.created_at else None,
        }

        doc2_info = {
            "id": str(doc_id_2),
            "filename": doc2.filename if doc2 else "Unbekannt",
            "document_type": doc2.document_type if doc2 else "Unbekannt",
            "created_at": doc2.created_at.isoformat() if doc2 and doc2.created_at else None,
        }

        # Zusammenfassung generieren
        summary = self._generate_summary(comparison)

        # Empfehlungen generieren
        recommendations = self._generate_recommendations(comparison)

        return DiffReport(
            comparison=comparison,
            document_1_info=doc1_info,
            document_2_info=doc2_info,
            summary=summary,
            recommendations=recommendations
        )

    async def find_similar_documents(
        self,
        doc_id: UUID,
        threshold: float = 0.8,
        limit: int = 10,
        company_id: Optional[UUID] = None,
        same_type_only: bool = True
    ) -> List[SimilarDocument]:
        """Findet ähnliche Dokumente.

        Args:
            doc_id: ID des Referenz-Dokuments
            threshold: Mindest-Ähnlichkeit (0.0-1.0)
            limit: Maximale Anzahl Ergebnisse
            company_id: Optional: Nur Dokumente dieser Company
            same_type_only: Nur gleichen Dokumenttyp vergleichen

        Returns:
            Liste ähnlicher Dokumente mit Scores
        """
        # Referenz-Dokument laden
        ref_doc = await self._get_document(doc_id)
        if not ref_doc:
            raise ValueError(f"Dokument {doc_id} nicht gefunden")

        # Query für Kandidaten
        stmt = (
            select(Document, BusinessEntity.name.label("entity_name"))
            .outerjoin(BusinessEntity, Document.business_entity_id == BusinessEntity.id)
            .where(Document.id != doc_id)
            .where(Document.deleted_at.is_(None))
        )

        if company_id:
            stmt = stmt.where(Document.company_id == company_id)

        if same_type_only and ref_doc.document_type:
            stmt = stmt.where(Document.document_type == ref_doc.document_type)

        # Limit höher setzen da wir nachher filtern
        stmt = stmt.limit(limit * 5)

        result = await self.db.execute(stmt)
        candidates = result.all()

        # Ähnlichkeit berechnen
        similar_docs: List[SimilarDocument] = []
        ref_data = ref_doc.extracted_data or {}

        for row in candidates:
            candidate_doc = row[0]
            entity_name = row[1]

            candidate_data = candidate_doc.extracted_data or {}

            # Schneller Struktur-Vergleich
            similarity, matching_fields = self._calculate_quick_similarity(
                ref_data, candidate_data
            )

            if similarity >= threshold:
                similar_docs.append(SimilarDocument(
                    document_id=candidate_doc.id,
                    filename=candidate_doc.filename,
                    document_type=candidate_doc.document_type or "unknown",
                    similarity_score=similarity,
                    matching_fields=matching_fields,
                    entity_name=entity_name,
                    created_at=candidate_doc.created_at
                ))

        # Nach Ähnlichkeit sortieren
        similar_docs.sort(key=lambda x: x.similarity_score, reverse=True)

        logger.info(
            "similar_documents_found",
            reference_doc=str(doc_id),
            candidates_checked=len(candidates),
            matches_found=len(similar_docs[:limit]),
            threshold=threshold
        )

        return similar_docs[:limit]

    # ========================================================================
    # Version Comparison Methods
    # ========================================================================

    async def compare_document_versions(
        self,
        document_id: UUID,
        version_a_id: UUID,
        version_b_id: UUID,
        user_id: UUID
    ) -> ComparisonResult:
        """Vergleicht zwei spezifische Versionen eines Dokuments.

        Args:
            document_id: UUID des Dokuments
            version_a_id: UUID der ersten Version
            version_b_id: UUID der zweiten Version
            user_id: UUID des anfordernden Benutzers

        Returns:
            ComparisonResult mit strukturiertem Diff

        Raises:
            ValueError: Wenn Dokument nicht gefunden oder keine Berechtigung
            ValueError: Wenn Versionen nicht gefunden
        """
        logger.info(
            "Vergleiche Dokumentversionen",
            document_id=str(document_id),
            version_a_id=str(version_a_id),
            version_b_id=str(version_b_id),
            user_id=str(user_id)
        )

        # Dokument laden und Berechtigung prüfen
        document = await self._get_document(document_id)
        if not document:
            raise ValueError("Dokument nicht gefunden")

        if document.user_id != user_id:
            raise ValueError("Keine Berechtigung für dieses Dokument")

        # Beide Versionen laden
        stmt = select(DocumentVersion).where(
            DocumentVersion.id.in_([version_a_id, version_b_id])
        )
        result = await self.db.execute(stmt)
        versions = result.scalars().all()

        if len(versions) != 2:
            raise ValueError("Eine oder beide Versionen nicht gefunden")

        # Versionen zuordnen
        version_a = next((v for v in versions if v.id == version_a_id), None)
        version_b = next((v for v in versions if v.id == version_b_id), None)

        if not version_a or not version_b:
            raise ValueError("Versionen konnten nicht zugeordnet werden")

        # Texte extrahieren
        text_a = await self._get_version_text(document, version_a)
        text_b = await self._get_version_text(document, version_b)

        # Text-Diff berechnen
        text_diffs, text_similarity = self._compare_text(text_a, text_b, True)

        # Statistiken
        additions = sum(1 for d in text_diffs if d.diff_type == DifferenceType.ADDED)
        removals = sum(1 for d in text_diffs if d.diff_type == DifferenceType.REMOVED)
        modifications = sum(1 for d in text_diffs if d.diff_type == DifferenceType.CHANGED)

        logger.info(
            "Versionsvergleich abgeschlossen",
            document_id=str(document_id),
            version_a=version_a.version_number,
            version_b=version_b.version_number,
            text_similarity=round(text_similarity, 3),
            total_changes=additions + removals + modifications
        )

        return ComparisonResult(
            document_1_id=version_a_id,
            document_2_id=version_b_id,
            comparison_type=ComparisonType.TEXT,
            overall_similarity=text_similarity,
            text_similarity=text_similarity,
            structure_similarity=0.0,
            text_differences=text_diffs,
            field_changes=[],
            total_changes=additions + removals + modifications,
            critical_changes=0,
            additions=additions,
            removals=removals,
            modifications=modifications,
            comparison_time_ms=0,
            warnings=[]
        )

    async def compare_with_original_version(
        self,
        document_id: UUID,
        user_id: UUID
    ) -> ComparisonResult:
        """Vergleicht die aktuelle Version mit der Originalversion.

        Args:
            document_id: UUID des Dokuments
            user_id: UUID des anfordernden Benutzers

        Returns:
            ComparisonResult (aktuell vs. Version 1)

        Raises:
            ValueError: Wenn Dokument nicht gefunden oder keine Versionen
        """
        logger.info(
            "Vergleiche mit Originalversion",
            document_id=str(document_id),
            user_id=str(user_id)
        )

        # Dokument laden
        document = await self._get_document(document_id)
        if not document:
            raise ValueError("Dokument nicht gefunden")

        if document.user_id != user_id:
            raise ValueError("Keine Berechtigung für dieses Dokument")

        # Original-Version (version_number = 1) laden
        original_stmt = (
            select(DocumentVersion)
            .where(
                DocumentVersion.document_id == document_id,
                DocumentVersion.version_number == 1
            )
        )
        original_result = await self.db.execute(original_stmt)
        original_version = original_result.scalar_one_or_none()

        if not original_version:
            raise ValueError("Keine Versionen vorhanden")

        # Aktuelle Version laden (is_current = True)
        current_stmt = (
            select(DocumentVersion)
            .where(
                DocumentVersion.document_id == document_id,
                DocumentVersion.is_current == True
            )
        )
        current_result = await self.db.execute(current_stmt)
        current_version = current_result.scalar_one_or_none()

        if not current_version:
            # Fallback: Verwende die Version mit der hoechsten version_number
            latest_stmt = (
                select(DocumentVersion)
                .where(DocumentVersion.document_id == document_id)
                .order_by(DocumentVersion.version_number.desc())
                .limit(1)
            )
            latest_result = await self.db.execute(latest_stmt)
            current_version = latest_result.scalar_one_or_none()

        if not current_version:
            raise ValueError("Keine aktuelle Version gefunden")

        # Vergleiche die beiden Versionen
        return await self.compare_document_versions(
            document_id, original_version.id, current_version.id, user_id
        )

    async def list_document_versions(
        self,
        document_id: UUID,
        user_id: UUID
    ) -> List[Dict[str, object]]:
        """Listet alle Versionen eines Dokuments für Vergleich auf.

        Args:
            document_id: UUID des Dokuments
            user_id: UUID des anfordernden Benutzers

        Returns:
            Liste von Version-Infos (id, number, change_type, created_at, created_by)

        Raises:
            ValueError: Wenn Dokument nicht gefunden oder keine Berechtigung
        """
        logger.info(
            "Liste Versionen für Vergleich",
            document_id=str(document_id),
            user_id=str(user_id)
        )

        # Dokument laden und Berechtigung prüfen
        document = await self._get_document(document_id)
        if not document:
            raise ValueError("Dokument nicht gefunden")

        if document.user_id != user_id:
            raise ValueError("Keine Berechtigung für dieses Dokument")

        # Versionen laden
        versions_stmt = (
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number.asc())
        )
        versions_result = await self.db.execute(versions_stmt)
        versions = versions_result.scalars().all()

        return [
            {
                "id": str(v.id),
                "version_number": v.version_number,
                "change_type": v.change_type,
                "change_summary": v.change_summary,
                "created_at": v.created_at.isoformat(),
                "created_by_id": str(v.created_by_id) if v.created_by_id else None,
                "is_current": v.is_current,
                "file_size": v.file_size,
                "file_hash": v.file_hash[:16] + "..." if v.file_hash else None  # Shortened for display
            }
            for v in versions
        ]

    async def _get_version_text(
        self,
        document: Document,
        version: DocumentVersion
    ) -> str:
        """Extrahiert den Text einer Version.

        HINWEIS: DocumentVersion hat kein extracted_text Feld.
        Diese Implementierung ist ein Platzhalter. In einer vollständigen
        Implementierung müssten wir:
        1. Die tatsaechliche Datei von version.file_path lesen
        2. OCR erneut ausführen (teuer)
        3. Einen separaten Text-Snapshot speichern

        Für jetzt: Wenn is_current, nutze document.extracted_text,
        sonst verwende change_summary als Platzhalter.
        """
        if version.is_current and document.extracted_text:
            return document.extracted_text

        # Platzhalter für nicht-aktuelle Versionen
        return f"[Version {version.version_number}: {version.change_summary or 'Keine Textdaten verfügbar'}]"

    # ========================================================================
    # Internal Methods
    # ========================================================================

    async def _get_document(self, doc_id: UUID) -> Optional[Document]:
        """Laedt ein Dokument aus der Datenbank."""
        stmt = select(Document).where(Document.id == doc_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    def _compare_text(
        self,
        text1: str,
        text2: str,
        include_context: bool = True
    ) -> Tuple[List[TextDifference], float]:
        """Vergleicht zwei Texte zeilenweise.

        Args:
            text1: Erster Text
            text2: Zweiter Text
            include_context: Kontext-Zeilen einbeziehen

        Returns:
            Tuple aus (Differenzen, Ähnlichkeitsscore)
        """
        differences: List[TextDifference] = []

        # Normalisieren
        lines1 = text1.splitlines()
        lines2 = text2.splitlines()

        # Ähnlichkeit berechnen
        similarity = difflib.SequenceMatcher(None, text1, text2).ratio()

        # Differenzen finden
        differ = difflib.unified_diff(
            lines1, lines2,
            lineterm='',
            n=2 if include_context else 0
        )

        line_number = 0
        for line in differ:
            if line.startswith('@@'):
                # Position extrahieren
                match = re.match(r'^@@ -(\d+)', line)
                if match:
                    line_number = int(match.group(1))
                continue

            if line.startswith('---') or line.startswith('+++'):
                continue

            if line.startswith('-'):
                differences.append(TextDifference(
                    diff_type=DifferenceType.REMOVED,
                    line_number=line_number,
                    old_text=line[1:],
                    new_text=None
                ))
                line_number += 1
            elif line.startswith('+'):
                differences.append(TextDifference(
                    diff_type=DifferenceType.ADDED,
                    line_number=line_number,
                    old_text=None,
                    new_text=line[1:]
                ))
            elif line.startswith(' '):
                line_number += 1

        return differences, similarity

    def _compare_structure(
        self,
        data1: Dict[str, object],
        data2: Dict[str, object]
    ) -> Tuple[List[FieldChange], float]:
        """Vergleicht strukturierte Daten.

        Args:
            data1: Erste Daten-Struktur
            data2: Zweite Daten-Struktur

        Returns:
            Tuple aus (Feld-Änderungen, Ähnlichkeitsscore)
        """
        changes: List[FieldChange] = []

        all_keys = set(data1.keys()) | set(data2.keys())
        matching_fields = 0
        total_fields = len(all_keys)

        for key in all_keys:
            val1 = data1.get(key)
            val2 = data2.get(key)

            # Kategorie bestimmen
            category = self._get_field_category(key)
            is_critical = key in self.CRITICAL_FIELDS

            if key not in data1:
                # Feld wurde hinzugefuegt
                changes.append(FieldChange(
                    field_name=key,
                    field_category=category,
                    old_value=None,
                    new_value=val2,
                    diff_type=DifferenceType.ADDED,
                    is_critical=is_critical
                ))
            elif key not in data2:
                # Feld wurde entfernt
                changes.append(FieldChange(
                    field_name=key,
                    field_category=category,
                    old_value=val1,
                    new_value=None,
                    diff_type=DifferenceType.REMOVED,
                    is_critical=is_critical
                ))
            elif not self._values_equal(val1, val2):
                # Feld wurde geändert
                changes.append(FieldChange(
                    field_name=key,
                    field_category=category,
                    old_value=val1,
                    new_value=val2,
                    diff_type=DifferenceType.CHANGED,
                    is_critical=is_critical
                ))
            else:
                # Feld ist gleich
                matching_fields += 1

        # Ähnlichkeit berechnen
        similarity = matching_fields / total_fields if total_fields > 0 else 1.0

        return changes, similarity

    def _get_field_category(self, field_name: str) -> FieldCategory:
        """Bestimmt die Kategorie eines Feldes."""
        field_lower = field_name.lower()

        if any(x in field_lower for x in ["number", "nr", "id", "nummer"]):
            return FieldCategory.IDENTIFIER
        if any(x in field_lower for x in ["amount", "total", "gross", "net", "vat", "betrag"]):
            return FieldCategory.AMOUNT
        if any(x in field_lower for x in ["date", "datum"]):
            return FieldCategory.DATE
        if any(x in field_lower for x in ["name", "firma", "company", "vendor", "customer"]):
            return FieldCategory.ENTITY
        if any(x in field_lower for x in ["address", "adresse", "street", "city", "plz"]):
            return FieldCategory.ADDRESS

        return FieldCategory.TEXT

    def _values_equal(self, val1: object, val2: object) -> bool:
        """Prüft ob zwei Werte gleich sind (mit Toleranz für Zahlen)."""
        # None-Handling
        if val1 is None and val2 is None:
            return True
        if val1 is None or val2 is None:
            return False

        # Zahlen: Mit Toleranz vergleichen
        if isinstance(val1, (int, float, Decimal)) and isinstance(val2, (int, float, Decimal)):
            return abs(float(val1) - float(val2)) < 0.01

        # Strings: Normalisiert vergleichen
        if isinstance(val1, str) and isinstance(val2, str):
            return val1.strip().lower() == val2.strip().lower()

        # Listen
        if isinstance(val1, list) and isinstance(val2, list):
            return val1 == val2

        # Dicts rekursiv
        if isinstance(val1, dict) and isinstance(val2, dict):
            if set(val1.keys()) != set(val2.keys()):
                return False
            return all(self._values_equal(val1[k], val2[k]) for k in val1.keys())

        return val1 == val2

    def _calculate_quick_similarity(
        self,
        data1: Dict[str, object],
        data2: Dict[str, object]
    ) -> Tuple[float, List[str]]:
        """Berechnet schnelle Ähnlichkeit basierend auf wichtigen Feldern.

        Args:
            data1: Erste Daten
            data2: Zweite Daten

        Returns:
            Tuple aus (Ähnlichkeit, Liste der übereinstimmenden Felder)
        """
        matching_fields: List[str] = []
        total_weight = 0.0
        matched_weight = 0.0

        # Gewichtungen für verschiedene Felder
        weights = {
            "invoice_number": 3.0,
            "customer_number": 2.5,
            "total_gross": 2.0,
            "invoice_date": 1.5,
            "vendor_name": 1.5,
            "customer_name": 1.5,
            "vat_id": 1.0,
        }

        for field, weight in weights.items():
            total_weight += weight

            val1 = data1.get(field)
            val2 = data2.get(field)

            if val1 is not None and val2 is not None:
                if self._values_equal(val1, val2):
                    matched_weight += weight
                    matching_fields.append(field)
                elif isinstance(val1, str) and isinstance(val2, str):
                    # Fuzzy String Matching
                    ratio = difflib.SequenceMatcher(None, val1.lower(), val2.lower()).ratio()
                    if ratio > 0.8:
                        matched_weight += weight * ratio
                        matching_fields.append(field)

        similarity = matched_weight / total_weight if total_weight > 0 else 0.0

        return similarity, matching_fields

    def _generate_summary(self, comparison: ComparisonResult) -> str:
        """Generiert eine Zusammenfassung des Vergleichs."""
        similarity_pct = int(comparison.overall_similarity * 100)

        if comparison.total_changes == 0:
            return f"Die Dokumente sind identisch (Ähnlichkeit: {similarity_pct}%)."

        summary_parts = [
            f"Ähnlichkeit: {similarity_pct}%.",
            f"Insgesamt {comparison.total_changes} Änderungen gefunden:"
        ]

        if comparison.additions > 0:
            summary_parts.append(f"- {comparison.additions} Hinzufuegungen")
        if comparison.removals > 0:
            summary_parts.append(f"- {comparison.removals} Entfernungen")
        if comparison.modifications > 0:
            summary_parts.append(f"- {comparison.modifications} Modifikationen")

        if comparison.critical_changes > 0:
            summary_parts.append(
                f"\n⚠️ ACHTUNG: {comparison.critical_changes} kritische Änderungen "
                "(Betraege, Rechnungsnummern, etc.)"
            )

        return "\n".join(summary_parts)

    def _generate_recommendations(self, comparison: ComparisonResult) -> List[str]:
        """Generiert Empfehlungen basierend auf dem Vergleich."""
        recommendations: List[str] = []

        if comparison.overall_similarity > 0.95 and comparison.total_changes > 0:
            recommendations.append(
                "Sehr hohe Ähnlichkeit - Prüfen Sie, ob es sich um ein Duplikat handelt."
            )

        if comparison.critical_changes > 0:
            recommendations.append(
                "Kritische Änderungen erkannt - Bitte manuell verifizieren."
            )

        # Spezifische Empfehlungen basierend auf Feld-Änderungen
        for change in comparison.field_changes:
            if change.is_critical and change.diff_type == DifferenceType.CHANGED:
                if change.field_category == FieldCategory.AMOUNT:
                    recommendations.append(
                        f"Betrags-Änderung in '{change.field_name}': "
                        f"{change.old_value} → {change.new_value}"
                    )
                elif change.field_category == FieldCategory.IDENTIFIER:
                    recommendations.append(
                        f"Identifikator-Änderung in '{change.field_name}': "
                        f"Prüfen Sie, ob dies beabsichtigt ist."
                    )

        if comparison.overall_similarity < 0.5:
            recommendations.append(
                "Geringe Ähnlichkeit - Die Dokumente unterscheiden sich stark."
            )

        if not recommendations:
            recommendations.append("Keine besonderen Empfehlungen.")

        return recommendations


# ============================================================================
# Factory Functions
# ============================================================================


async def get_document_comparison_service(db: AsyncSession) -> DocumentComparisonService:
    """Factory-Funktion für DocumentComparisonService.

    Args:
        db: Async Database Session

    Returns:
        Konfigurierter DocumentComparisonService
    """
    return DocumentComparisonService(db=db)
