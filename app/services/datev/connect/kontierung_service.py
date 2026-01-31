# -*- coding: utf-8 -*-
"""
Intelligenter Kontierungsvorschlag-Service.

ML-gestuetzte Kontierungsvorschlaege fuer DATEV:
- Regelbasierte Vorschlaege (Lieferant-Historie)
- ML-basierte Vorschlaege (Text-Analyse, Betragsklassen)
- DATEV-Kontenplan-Validierung
- Lern-Feedback-Loop

Feinpoliert und durchdacht - Intelligente Buchhaltungsassistenz.
"""

import hashlib
import threading
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# Datenklassen
# =============================================================================

@dataclass
class KontierungsInput:
    """Eingabedaten fuer Kontierungsvorschlag."""

    # Lieferant/Kunde
    entity_name: str = ""
    entity_vat_id: Optional[str] = None
    entity_iban: Optional[str] = None

    # Betraege
    betrag_brutto: Decimal = Decimal("0")
    betrag_netto: Optional[Decimal] = None
    mwst_satz: Optional[Decimal] = None
    mwst_betrag: Optional[Decimal] = None

    # Dokumenttyp
    dokument_typ: str = "invoice"  # invoice, credit_note, receipt, etc.
    richtung: str = "incoming"  # incoming, outgoing

    # Zusatzinfos aus OCR
    stichwort: Optional[str] = None
    rechnungsnummer: Optional[str] = None
    bestellnummer: Optional[str] = None

    # Kontext
    document_id: Optional[UUID] = None
    company_id: Optional[UUID] = None


@dataclass
class KontierungsSuggestion:
    """Kontierungsvorschlag."""

    # Konten
    konto: str = ""
    gegenkonto: str = ""
    bu_schluessel: str = ""
    kostenstelle: Optional[str] = None

    # Konfidenz
    confidence: float = 0.0
    source: str = "manual"  # rule, ml, history, manual

    # Erklaerung
    explanation: str = ""
    similar_buchungen: List[Dict[str, Any]] = field(default_factory=list)

    # Alternative Vorschlaege
    alternatives: List["KontierungsSuggestion"] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "konto": self.konto,
            "gegenkonto": self.gegenkonto,
            "bu_schluessel": self.bu_schluessel,
            "kostenstelle": self.kostenstelle,
            "confidence": self.confidence,
            "source": self.source,
            "explanation": self.explanation,
            "similar_buchungen": self.similar_buchungen,
            "alternatives": [a.to_dict() for a in self.alternatives] if self.alternatives else [],
        }


# =============================================================================
# Kontierungs-Service
# =============================================================================

class KontierungsvorschlagService:
    """
    Intelligenter Kontierungsvorschlag-Service.

    Kombiniert mehrere Strategien fuer optimale Vorschlaege:
    1. Exakter Match: Lieferant + Dokumenttyp aus Historie
    2. Pattern Match: Aehnliche Buchungen nach Text-Keywords
    3. Betrags-Klassen: Standard-Konten nach Betragsbereich
    4. ML-basiert: Feature-Vektor-Matching (optional)

    Die Konfidenz wird aus mehreren Faktoren berechnet:
    - Historische Erfolgsquote des Patterns
    - Anzahl aehnlicher Buchungen
    - Match-Qualitaet (exakt vs. fuzzy)

    Usage:
        service = KontierungsvorschlagService()

        suggestion = await service.suggest_kontierung(
            db=session,
            connection_id=conn_uuid,
            input_data=KontierungsInput(
                entity_name="Lieferant GmbH",
                betrag_brutto=Decimal("119.00"),
                dokument_typ="invoice",
            )
        )

        print(f"Vorschlag: {suggestion.konto} / {suggestion.gegenkonto}")
        print(f"Konfidenz: {suggestion.confidence:.0%}")
    """

    # Standard-Konten als Fallback (SKR03)
    DEFAULT_ACCOUNTS_SKR03 = {
        "incoming": {
            "default": ("4400", "1600"),  # Aufwand / Verbindlichkeiten
            "buero": ("4930", "1600"),    # Buerokosten
            "reise": ("4660", "1600"),    # Reisekosten
            "miete": ("4210", "1600"),    # Miete
            "telefon": ("4920", "1600"),  # Telefon
            "versicherung": ("4360", "1600"),  # Versicherungen
            "kfz": ("4540", "1600"),      # Kfz-Kosten
            "werbung": ("4600", "1600"),  # Werbung
            "beratung": ("4950", "1600"), # Beratungskosten
        },
        "outgoing": {
            "default": ("8400", "1400"),  # Erloese / Forderungen
            "dienstleistung": ("8400", "1400"),
            "ware": ("8200", "1400"),     # Warenerloese
        },
    }

    # Steuerschluessel
    TAX_CODES = {
        Decimal("19"): "9",   # 19% Vorsteuer
        Decimal("7"): "8",    # 7% Vorsteuer
        Decimal("0"): "",     # Steuerfrei
        Decimal("19.0"): "9",
        Decimal("7.0"): "8",
    }

    def __init__(self) -> None:
        """Initialisiert den Service."""
        self._pattern_cache: Dict[str, KontierungsSuggestion] = {}
        self._cache_lock = threading.Lock()

    async def suggest_kontierung(
        self,
        db: AsyncSession,
        connection_id: UUID,
        input_data: KontierungsInput,
    ) -> KontierungsSuggestion:
        """
        Generiert Kontierungsvorschlag.

        Args:
            db: Datenbank-Session
            connection_id: DATEV-Verbindungs-ID
            input_data: Eingabedaten

        Returns:
            KontierungsSuggestion mit Vorschlag und Alternativen
        """
        suggestions: List[KontierungsSuggestion] = []

        # 1. Exakter Entity-Match aus Historie
        history_suggestion = await self._suggest_from_history(
            db, connection_id, input_data
        )
        if history_suggestion and history_suggestion.confidence > 0:
            suggestions.append(history_suggestion)

        # 2. Pattern-Match aus gespeicherten Patterns
        pattern_suggestion = await self._suggest_from_patterns(
            db, connection_id, input_data
        )
        if pattern_suggestion and pattern_suggestion.confidence > 0:
            suggestions.append(pattern_suggestion)

        # 3. Keyword-basierter Vorschlag
        keyword_suggestion = self._suggest_from_keywords(input_data)
        if keyword_suggestion and keyword_suggestion.confidence > 0:
            suggestions.append(keyword_suggestion)

        # 4. Default-Fallback
        default_suggestion = self._get_default_suggestion(input_data)
        suggestions.append(default_suggestion)

        # Beste Suggestion waehlen
        suggestions.sort(key=lambda s: s.confidence, reverse=True)
        best = suggestions[0]

        # Alternativen hinzufuegen (ohne Duplikate)
        seen_konten = {(best.konto, best.gegenkonto)}
        for alt in suggestions[1:]:
            if (alt.konto, alt.gegenkonto) not in seen_konten:
                best.alternatives.append(alt)
                seen_konten.add((alt.konto, alt.gegenkonto))
                if len(best.alternatives) >= 3:
                    break

        logger.info(
            "datev_kontierung_suggested",
            konto=best.konto,
            gegenkonto=best.gegenkonto,
            confidence=round(best.confidence, 2),
            source=best.source,
            alternatives=len(best.alternatives),
        )

        return best

    async def learn_from_correction(
        self,
        db: AsyncSession,
        connection_id: UUID,
        buchung_id: UUID,
        corrected_konto: str,
        corrected_gegenkonto: str,
        corrected_bu_schluessel: Optional[str] = None,
        input_data: Optional[KontierungsInput] = None,
    ) -> bool:
        """
        Lernt aus User-Korrektur.

        Args:
            db: Datenbank-Session
            connection_id: DATEV-Verbindungs-ID
            buchung_id: ID der korrigierten Buchung
            corrected_konto: Korrigiertes Konto
            corrected_gegenkonto: Korrigiertes Gegenkonto
            corrected_bu_schluessel: Korrigierter Steuerschluessel
            input_data: Urspruengliche Eingabedaten (fuer Pattern-Lernen)

        Returns:
            True wenn erfolgreich
        """
        from app.db import models

        try:
            # 1. Buchung als korrigiert markieren
            buchung_result = await db.execute(
                select(models.DATEVBuchung).where(
                    models.DATEVBuchung.id == buchung_id,
                )
            )
            buchung = buchung_result.scalar_one_or_none()

            if buchung:
                # Original-Vorschlag speichern
                buchung.original_suggestion_konto = buchung.konto
                buchung.original_suggestion_gegenkonto = buchung.gegenkonto
                buchung.user_korrektur = True

                # Korrigierte Werte setzen
                buchung.konto = corrected_konto
                buchung.gegenkonto = corrected_gegenkonto
                if corrected_bu_schluessel:
                    buchung.bu_schluessel = corrected_bu_schluessel

            # 2. Pattern aktualisieren oder erstellen
            if input_data and input_data.entity_name:
                await self._update_or_create_pattern(
                    db=db,
                    connection_id=connection_id,
                    input_data=input_data,
                    konto=corrected_konto,
                    gegenkonto=corrected_gegenkonto,
                    bu_schluessel=corrected_bu_schluessel,
                )

            await db.commit()

            logger.info(
                "datev_kontierung_learned",
                buchung_id=str(buchung_id),
                corrected_konto=corrected_konto,
                corrected_gegenkonto=corrected_gegenkonto,
            )
            return True

        except Exception as e:
            logger.error(
                "datev_kontierung_learn_failed",
                buchung_id=str(buchung_id),
                **safe_error_log(e)
            )
            await db.rollback()
            return False

    async def get_similar_buchungen(
        self,
        db: AsyncSession,
        connection_id: UUID,
        entity_name: Optional[str] = None,
        amount: Optional[Decimal] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Findet aehnliche Buchungen zur Orientierung.

        Args:
            db: Datenbank-Session
            connection_id: DATEV-Verbindungs-ID
            entity_name: Firmenname (optional)
            amount: Betrag (optional, +/- 20% Toleranz)
            limit: Maximale Anzahl

        Returns:
            Liste aehnlicher Buchungen
        """
        from app.db import models

        query = select(models.DATEVBuchung).where(
            models.DATEVBuchung.connection_id == connection_id,
            models.DATEVBuchung.sync_status == "synced",
        )

        # Betragsfilter
        if amount:
            tolerance = amount * Decimal("0.2")
            query = query.where(
                models.DATEVBuchung.umsatz.between(
                    amount - tolerance,
                    amount + tolerance,
                )
            )

        # Nach neuesten zuerst
        query = query.order_by(desc(models.DATEVBuchung.created_at)).limit(limit)

        result = await db.execute(query)
        buchungen = result.scalars().all()

        return [
            {
                "id": str(b.id),
                "belegdatum": b.belegdatum.isoformat() if b.belegdatum else None,
                "umsatz": float(b.umsatz),
                "konto": b.konto,
                "gegenkonto": b.gegenkonto,
                "bu_schluessel": b.bu_schluessel,
                "buchungstext": b.buchungstext,
            }
            for b in buchungen
        ]

    async def get_pattern_statistics(
        self,
        db: AsyncSession,
        connection_id: UUID,
    ) -> Dict[str, Any]:
        """
        Liefert Statistiken ueber Kontierungs-Patterns.

        Args:
            db: Datenbank-Session
            connection_id: DATEV-Verbindungs-ID

        Returns:
            Statistik-Dictionary
        """
        from app.db import models

        # Patterns zaehlen
        pattern_count_result = await db.execute(
            select(func.count(models.DATEVKontierungPattern.id)).where(
                models.DATEVKontierungPattern.connection_id == connection_id,
                models.DATEVKontierungPattern.is_active == True,
            )
        )
        pattern_count = pattern_count_result.scalar() or 0

        # Top-Konten
        top_konten_result = await db.execute(
            select(
                models.DATEVKontierungPattern.konto,
                func.sum(models.DATEVKontierungPattern.usage_count).label("total_usage"),
            )
            .where(
                models.DATEVKontierungPattern.connection_id == connection_id,
                models.DATEVKontierungPattern.is_active == True,
            )
            .group_by(models.DATEVKontierungPattern.konto)
            .order_by(desc("total_usage"))
            .limit(10)
        )
        top_konten = [
            {"konto": row[0], "usage_count": row[1]}
            for row in top_konten_result.all()
        ]

        # Durchschnittliche Erfolgsquote
        success_result = await db.execute(
            select(
                func.avg(
                    models.DATEVKontierungPattern.success_count * 100.0 /
                    func.nullif(models.DATEVKontierungPattern.usage_count, 0)
                )
            ).where(
                models.DATEVKontierungPattern.connection_id == connection_id,
                models.DATEVKontierungPattern.usage_count > 0,
            )
        )
        avg_success_rate = success_result.scalar() or 0

        return {
            "total_patterns": pattern_count,
            "avg_success_rate": round(float(avg_success_rate), 1),
            "top_konten": top_konten,
        }

    # =========================================================================
    # Private Suggestion Methods
    # =========================================================================

    async def _suggest_from_history(
        self,
        db: AsyncSession,
        connection_id: UUID,
        input_data: KontierungsInput,
    ) -> Optional[KontierungsSuggestion]:
        """Sucht Vorschlag aus Buchungshistorie."""
        from app.db import models

        if not input_data.entity_name:
            return None

        # Suche nach aehnlichen Buchungen mit gleichem Lieferanten
        # Fuzzy-Match via LIKE
        name_pattern = f"%{input_data.entity_name[:20].lower()}%"

        result = await db.execute(
            select(
                models.DATEVBuchung.konto,
                models.DATEVBuchung.gegenkonto,
                models.DATEVBuchung.bu_schluessel,
                func.count(models.DATEVBuchung.id).label("count"),
            )
            .where(
                models.DATEVBuchung.connection_id == connection_id,
                models.DATEVBuchung.sync_status == "synced",
                func.lower(models.DATEVBuchung.buchungstext).like(name_pattern),
            )
            .group_by(
                models.DATEVBuchung.konto,
                models.DATEVBuchung.gegenkonto,
                models.DATEVBuchung.bu_schluessel,
            )
            .order_by(desc("count"))
            .limit(1)
        )
        row = result.first()

        if row:
            count = row[3]
            # Konfidenz basierend auf Anzahl aehnlicher Buchungen
            confidence = min(0.95, 0.5 + (count * 0.1))

            return KontierungsSuggestion(
                konto=row[0],
                gegenkonto=row[1],
                bu_schluessel=row[2] or "",
                confidence=confidence,
                source="history",
                explanation=f"Basierend auf {count} aehnlichen Buchungen fuer diesen Lieferanten",
            )

        return None

    async def _suggest_from_patterns(
        self,
        db: AsyncSession,
        connection_id: UUID,
        input_data: KontierungsInput,
    ) -> Optional[KontierungsSuggestion]:
        """Sucht Vorschlag aus gespeicherten Patterns."""
        from app.db import models

        # Pattern-Suche mit mehreren Kriterien
        conditions = [
            models.DATEVKontierungPattern.connection_id == connection_id,
            models.DATEVKontierungPattern.is_active == True,
        ]

        # Dokumenttyp
        if input_data.dokument_typ:
            conditions.append(
                or_(
                    models.DATEVKontierungPattern.document_type == input_data.dokument_typ,
                    models.DATEVKontierungPattern.document_type.is_(None),
                )
            )

        # Betragsbereich
        if input_data.betrag_brutto:
            conditions.append(
                or_(
                    and_(
                        models.DATEVKontierungPattern.amount_range_min <= input_data.betrag_brutto,
                        models.DATEVKontierungPattern.amount_range_max >= input_data.betrag_brutto,
                    ),
                    models.DATEVKontierungPattern.amount_range_min.is_(None),
                )
            )

        result = await db.execute(
            select(models.DATEVKontierungPattern)
            .where(and_(*conditions))
            .order_by(
                desc(models.DATEVKontierungPattern.priority),
                desc(models.DATEVKontierungPattern.usage_count),
            )
            .limit(1)
        )
        pattern = result.scalar_one_or_none()

        if pattern:
            # Erfolgsquote berechnen
            success_rate = 0.0
            if pattern.usage_count > 0:
                success_rate = pattern.success_count / pattern.usage_count

            confidence = min(0.9, 0.4 + (success_rate * 0.4) + (min(pattern.usage_count, 10) * 0.02))

            return KontierungsSuggestion(
                konto=pattern.konto,
                gegenkonto=pattern.gegenkonto,
                bu_schluessel=pattern.bu_schluessel or "",
                kostenstelle=pattern.kostenstelle,
                confidence=confidence,
                source="rule",
                explanation=f"Regel-Match: {pattern.entity_name_pattern or 'Allgemein'} (Erfolgsquote: {success_rate:.0%})",
            )

        return None

    def _suggest_from_keywords(
        self,
        input_data: KontierungsInput,
    ) -> Optional[KontierungsSuggestion]:
        """Keyword-basierter Vorschlag."""
        text = (input_data.stichwort or "").lower()
        entity = (input_data.entity_name or "").lower()
        combined = f"{text} {entity}"

        # Keyword-Mapping
        keywords = {
            "buero": ["buero", "office", "schreibwaren", "toner", "drucker"],
            "reise": ["reise", "hotel", "bahn", "flug", "taxi", "mietwagen"],
            "miete": ["miete", "pacht", "immobilie", "gewerbe"],
            "telefon": ["telefon", "telekom", "vodafone", "internet", "mobilfunk"],
            "versicherung": ["versicherung", "allianz", "axa", "haftpflicht"],
            "kfz": ["tankstelle", "benzin", "diesel", "werkstatt", "tuev"],
            "werbung": ["werbung", "marketing", "google", "facebook", "anzeige"],
            "beratung": ["beratung", "consulting", "steuerberater", "anwalt", "rechtsanwalt"],
        }

        accounts = self.DEFAULT_ACCOUNTS_SKR03.get(input_data.richtung, {})

        for category, words in keywords.items():
            if any(word in combined for word in words):
                konto, gegenkonto = accounts.get(category, accounts.get("default", ("4400", "1600")))
                return KontierungsSuggestion(
                    konto=konto,
                    gegenkonto=gegenkonto,
                    bu_schluessel=self._get_tax_code(input_data.mwst_satz),
                    confidence=0.6,
                    source="rule",
                    explanation=f"Keyword-Match: Kategorie '{category}'",
                )

        return None

    def _get_default_suggestion(
        self,
        input_data: KontierungsInput,
    ) -> KontierungsSuggestion:
        """Liefert Standard-Kontierung als Fallback."""
        accounts = self.DEFAULT_ACCOUNTS_SKR03.get(input_data.richtung, {})
        konto, gegenkonto = accounts.get("default", ("4400", "1600"))

        return KontierungsSuggestion(
            konto=konto,
            gegenkonto=gegenkonto,
            bu_schluessel=self._get_tax_code(input_data.mwst_satz),
            confidence=0.3,
            source="manual",
            explanation="Standard-Kontierung (bitte pruefen)",
        )

    def _get_tax_code(self, mwst_satz: Optional[Decimal]) -> str:
        """Ermittelt Steuerschluessel aus MwSt-Satz."""
        if mwst_satz is None:
            return "9"  # Standard 19%
        return self.TAX_CODES.get(mwst_satz, "9")

    async def _update_or_create_pattern(
        self,
        db: AsyncSession,
        connection_id: UUID,
        input_data: KontierungsInput,
        konto: str,
        gegenkonto: str,
        bu_schluessel: Optional[str],
    ) -> None:
        """Aktualisiert oder erstellt ein Kontierungs-Pattern."""
        from app.db import models
        import uuid

        # Suche nach existierendem Pattern
        pattern_result = await db.execute(
            select(models.DATEVKontierungPattern).where(
                models.DATEVKontierungPattern.connection_id == connection_id,
                models.DATEVKontierungPattern.entity_name_pattern == input_data.entity_name[:200],
                models.DATEVKontierungPattern.document_type == input_data.dokument_typ,
            )
        )
        pattern = pattern_result.scalar_one_or_none()

        if pattern:
            # Existierendes Pattern aktualisieren
            pattern.usage_count += 1
            pattern.success_count += 1  # Korrektur = erfolgreiche Verwendung
            pattern.last_used_at = utc_now()

            # Konten nur aktualisieren wenn sie sich geaendert haben
            if pattern.konto != konto or pattern.gegenkonto != gegenkonto:
                pattern.konto = konto
                pattern.gegenkonto = gegenkonto
                pattern.bu_schluessel = bu_schluessel
                pattern.pattern_source = "learned"
        else:
            # Neues Pattern erstellen
            new_pattern = models.DATEVKontierungPattern(
                id=uuid.uuid4(),
                connection_id=connection_id,
                company_id=input_data.company_id,
                entity_name_pattern=input_data.entity_name[:200],
                document_type=input_data.dokument_typ,
                konto=konto,
                gegenkonto=gegenkonto,
                bu_schluessel=bu_schluessel,
                usage_count=1,
                success_count=1,
                last_used_at=utc_now(),
                pattern_source="learned",
                is_active=True,
                priority=0,
            )
            db.add(new_pattern)


# =============================================================================
# Singleton
# =============================================================================

_kontierung_service: Optional[KontierungsvorschlagService] = None
_service_lock = threading.Lock()


def get_kontierung_service() -> KontierungsvorschlagService:
    """
    Factory fuer KontierungsvorschlagService (Thread-Safe Singleton).
    """
    global _kontierung_service
    if _kontierung_service is None:
        with _service_lock:
            if _kontierung_service is None:
                _kontierung_service = KontierungsvorschlagService()
    return _kontierung_service
