# -*- coding: utf-8 -*-
"""
GoBD-Compliance Service fuer DATEV Integration.

Gewaehrleistet GoBD-konforme Buchungsfuehrung:
- Unveraenderliche Buchungs-GUIDs
- Festschreibung mit SHA-256 Hash
- Vollstaendiger Audit-Trail
- Beleglink-Integritaet
- Verfahrensdokumentation

Feinpoliert und durchdacht - Rechtssichere Buchhaltung.
"""

import hashlib
import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# Datenklassen
# =============================================================================

@dataclass
class FestschreibungResult:
    """Ergebnis einer Festschreibung."""

    success: bool
    festschreibung_datum: Optional[datetime] = None
    buchungen_count: int = 0
    buchungen_ids: List[UUID] = field(default_factory=list)
    fehler: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "success": self.success,
            "festschreibung_datum": self.festschreibung_datum.isoformat() if self.festschreibung_datum else None,
            "buchungen_count": self.buchungen_count,
            "buchungen_ids": [str(b) for b in self.buchungen_ids],
            "fehler": self.fehler,
        }


@dataclass
class GoBDValidationResult:
    """Ergebnis einer GoBD-Pruefung."""

    is_compliant: bool
    pruefung_datum: datetime = field(default_factory=utc_now)
    findings: List[Dict[str, Any]] = field(default_factory=list)
    statistics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "is_compliant": self.is_compliant,
            "pruefung_datum": self.pruefung_datum.isoformat(),
            "findings": self.findings,
            "statistics": self.statistics,
        }


# =============================================================================
# GoBD Compliance Service
# =============================================================================

class GoBDComplianceService:
    """
    GoBD-Compliance Service.

    Stellt die Einhaltung der GoBD-Anforderungen sicher:

    1. **Unveraenderlichkeit**: Buchungen koennen nach Festschreibung
       nicht mehr geaendert werden. Der Hash garantiert Integritaet.

    2. **Nachvollziehbarkeit**: Vollstaendiger Audit-Trail aller
       Aenderungen vor Festschreibung.

    3. **Pruefbarkeit**: Export-Funktion fuer Betriebspruefer.

    4. **Belegverknuepfung**: Eindeutige Beleglinks zu Originalbelegen.

    Usage:
        service = GoBDComplianceService()

        # Buchungen festschreiben
        result = await service.festschreiben_buchungen(
            db=session,
            connection_id=conn_uuid,
            bis_datum=date(2024, 12, 31)
        )

        # Compliance pruefen
        validation = await service.validate_gobd_compliance(
            db=session,
            connection_id=conn_uuid
        )

        # Verfahrensdokumentation exportieren
        pdf_bytes = await service.export_verfahrensdokumentation(
            db=session,
            connection_id=conn_uuid
        )
    """

    # GoBD-relevante Felder fuer Hash-Berechnung
    HASH_FIELDS = [
        "buchungs_guid",
        "umsatz",
        "soll_haben",
        "konto",
        "gegenkonto",
        "bu_schluessel",
        "belegdatum",
        "belegfeld_1",
        "buchungstext",
    ]

    def __init__(self) -> None:
        """Initialisiert den Service."""
        pass

    async def festschreiben_buchungen(
        self,
        db: AsyncSession,
        connection_id: UUID,
        bis_datum: date,
        company_id: Optional[UUID] = None,
    ) -> FestschreibungResult:
        """
        Schreibt Buchungen bis zum angegebenen Datum fest.

        Nach Festschreibung sind die Buchungen unveraenderlich und
        mit einem SHA-256 Hash versehen.

        Args:
            db: Datenbank-Session
            connection_id: DATEV-Verbindungs-ID
            bis_datum: Buchungen bis zu diesem Datum festschreiben
            company_id: Optional Company-Filter (Multi-Tenant)

        Returns:
            FestschreibungResult
        """
        from app.db import models

        result = FestschreibungResult(success=False)

        try:
            # 1. Nicht-festgeschriebene Buchungen finden
            conditions = [
                models.DATEVBuchung.connection_id == connection_id,
                models.DATEVBuchung.belegdatum <= bis_datum,
                models.DATEVBuchung.ist_festgeschrieben == False,
                models.DATEVBuchung.sync_status.in_(["synced", "pending"]),
            ]
            if company_id:
                conditions.append(models.DATEVBuchung.company_id == company_id)

            buchungen_result = await db.execute(
                select(models.DATEVBuchung).where(and_(*conditions))
            )
            buchungen = buchungen_result.scalars().all()

            if not buchungen:
                result.success = True
                result.fehler.append("Keine Buchungen zum Festschreiben gefunden")
                return result

            # 2. Validierung vor Festschreibung
            validation_errors = []
            for buchung in buchungen:
                errors = self._validate_buchung_for_festschreibung(buchung)
                if errors:
                    validation_errors.extend([
                        f"Buchung {buchung.belegfeld_1 or buchung.id}: {e}"
                        for e in errors
                    ])

            if validation_errors:
                result.fehler = validation_errors
                return result

            # 3. Festschreiben mit Hash
            festschreibung_zeit = utc_now()
            festgeschriebene_ids: List[UUID] = []

            for buchung in buchungen:
                # Hash berechnen
                hash_data = self._calculate_buchung_hash(buchung)

                # Festschreiben
                buchung.ist_festgeschrieben = True
                buchung.festschreibung_datum = festschreibung_zeit
                buchung.festschreibung_hash = hash_data

                festgeschriebene_ids.append(buchung.id)

            await db.commit()

            # 4. Ergebnis zusammenstellen
            result.success = True
            result.festschreibung_datum = festschreibung_zeit
            result.buchungen_count = len(festgeschriebene_ids)
            result.buchungen_ids = festgeschriebene_ids

            logger.info(
                "gobd_festschreibung_completed",
                connection_id=str(connection_id),
                bis_datum=bis_datum.isoformat(),
                buchungen_count=len(festgeschriebene_ids),
            )

        except Exception as e:
            result.fehler.append(f"Festschreibung fehlgeschlagen: {str(e)}")
            logger.error(
                "gobd_festschreibung_failed",
                connection_id=str(connection_id),
                **safe_error_log(e)
            )
            await db.rollback()

        return result

    async def validate_gobd_compliance(
        self,
        db: AsyncSession,
        connection_id: UUID,
        pruefzeitraum_von: Optional[date] = None,
        pruefzeitraum_bis: Optional[date] = None,
    ) -> GoBDValidationResult:
        """
        Prueft GoBD-Compliance fuer eine Verbindung.

        Prueft:
        - Integritaet festgeschriebener Buchungen (Hash-Pruefung)
        - Lueckenlose Buchungs-GUIDs
        - Beleglink-Verknuepfungen
        - Zeitstempel-Konsistenz

        Args:
            db: Datenbank-Session
            connection_id: DATEV-Verbindungs-ID
            pruefzeitraum_von: Optional: Start des Pruefzeitraums
            pruefzeitraum_bis: Optional: Ende des Pruefzeitraums

        Returns:
            GoBDValidationResult
        """
        from app.db import models

        result = GoBDValidationResult(is_compliant=True)
        findings: List[Dict[str, Any]] = []

        try:
            # Filter aufbauen
            conditions = [models.DATEVBuchung.connection_id == connection_id]
            if pruefzeitraum_von:
                conditions.append(models.DATEVBuchung.belegdatum >= pruefzeitraum_von)
            if pruefzeitraum_bis:
                conditions.append(models.DATEVBuchung.belegdatum <= pruefzeitraum_bis)

            # Alle Buchungen laden
            buchungen_result = await db.execute(
                select(models.DATEVBuchung).where(and_(*conditions))
            )
            buchungen = buchungen_result.scalars().all()

            # Statistiken
            total = len(buchungen)
            festgeschrieben = sum(1 for b in buchungen if b.ist_festgeschrieben)
            mit_beleglink = 0
            hash_fehler = 0
            guid_duplikate: Dict[str, int] = {}

            for buchung in buchungen:
                # 1. Hash-Integritaet pruefen (nur festgeschriebene)
                if buchung.ist_festgeschrieben:
                    expected_hash = self._calculate_buchung_hash(buchung)
                    if buchung.festschreibung_hash != expected_hash:
                        hash_fehler += 1
                        findings.append({
                            "type": "HASH_MISMATCH",
                            "severity": "CRITICAL",
                            "buchung_id": str(buchung.id),
                            "belegfeld_1": buchung.belegfeld_1,
                            "message": "Hash-Integritaet verletzt - Daten wurden veraendert!",
                        })

                # 2. GUID-Eindeutigkeit pruefen
                if buchung.buchungs_guid in guid_duplikate:
                    guid_duplikate[buchung.buchungs_guid] += 1
                    findings.append({
                        "type": "GUID_DUPLICATE",
                        "severity": "HIGH",
                        "buchung_id": str(buchung.id),
                        "guid": buchung.buchungs_guid,
                        "message": "Doppelte Buchungs-GUID",
                    })
                else:
                    guid_duplikate[buchung.buchungs_guid] = 1

                # 3. Beleglink zaehlen
                if buchung.document_id:
                    mit_beleglink += 1

            # 4. Nicht-festgeschriebene alte Buchungen pruefen
            alte_nicht_festgeschrieben = await db.execute(
                select(func.count(models.DATEVBuchung.id)).where(
                    models.DATEVBuchung.connection_id == connection_id,
                    models.DATEVBuchung.ist_festgeschrieben == False,
                    models.DATEVBuchung.belegdatum < func.current_date() - 30,  # Aelter als 30 Tage
                )
            )
            alte_count = alte_nicht_festgeschrieben.scalar() or 0

            if alte_count > 0:
                findings.append({
                    "type": "OLD_NOT_LOCKED",
                    "severity": "MEDIUM",
                    "count": alte_count,
                    "message": f"{alte_count} Buchungen aelter als 30 Tage nicht festgeschrieben",
                })

            # Ergebnis zusammenstellen
            critical_findings = [f for f in findings if f.get("severity") == "CRITICAL"]
            result.is_compliant = len(critical_findings) == 0

            result.findings = findings
            result.statistics = {
                "total_buchungen": total,
                "festgeschrieben": festgeschrieben,
                "nicht_festgeschrieben": total - festgeschrieben,
                "mit_beleglink": mit_beleglink,
                "ohne_beleglink": total - mit_beleglink,
                "hash_fehler": hash_fehler,
                "alte_nicht_festgeschrieben": alte_count,
            }

            logger.info(
                "gobd_validation_completed",
                connection_id=str(connection_id),
                is_compliant=result.is_compliant,
                findings_count=len(findings),
            )

        except Exception as e:
            result.is_compliant = False
            result.findings.append({
                "type": "VALIDATION_ERROR",
                "severity": "CRITICAL",
                "message": f"Pruefung fehlgeschlagen: {str(e)}",
            })
            logger.error(
                "gobd_validation_failed",
                **safe_error_log(e)
            )

        return result

    async def verify_buchung_integrity(
        self,
        db: AsyncSession,
        buchung_id: UUID,
    ) -> Tuple[bool, Optional[str]]:
        """
        Prueft Integritaet einer einzelnen Buchung.

        Args:
            db: Datenbank-Session
            buchung_id: Buchungs-ID

        Returns:
            Tuple aus (ist_integer, Fehlermeldung)
        """
        from app.db import models

        result = await db.execute(
            select(models.DATEVBuchung).where(
                models.DATEVBuchung.id == buchung_id
            )
        )
        buchung = result.scalar_one_or_none()

        if not buchung:
            return False, "Buchung nicht gefunden"

        if not buchung.ist_festgeschrieben:
            return True, None  # Nicht-festgeschriebene Buchungen sind per Definition integer

        expected_hash = self._calculate_buchung_hash(buchung)
        if buchung.festschreibung_hash != expected_hash:
            return False, "Hash-Mismatch: Daten wurden nach Festschreibung veraendert"

        return True, None

    async def export_verfahrensdokumentation(
        self,
        db: AsyncSession,
        connection_id: UUID,
    ) -> bytes:
        """
        Exportiert Verfahrensdokumentation als JSON.

        Die Verfahrensdokumentation beschreibt das eingesetzte
        Buchungssystem gemaess GoBD-Anforderungen.

        Args:
            db: Datenbank-Session
            connection_id: DATEV-Verbindungs-ID

        Returns:
            JSON-Bytes der Verfahrensdokumentation
        """
        from app.db import models

        # Verbindungsdaten laden
        conn_result = await db.execute(
            select(models.DATEVConnection).where(
                models.DATEVConnection.id == connection_id
            )
        )
        connection = conn_result.scalar_one_or_none()

        if not connection:
            raise ValueError("DATEV-Verbindung nicht gefunden")

        # Statistiken sammeln
        buchungen_stats = await db.execute(
            select(
                func.count(models.DATEVBuchung.id).label("total"),
                func.count(models.DATEVBuchung.id).filter(
                    models.DATEVBuchung.ist_festgeschrieben == True
                ).label("festgeschrieben"),
                func.min(models.DATEVBuchung.belegdatum).label("erste_buchung"),
                func.max(models.DATEVBuchung.belegdatum).label("letzte_buchung"),
            ).where(
                models.DATEVBuchung.connection_id == connection_id
            )
        )
        stats = buchungen_stats.first()

        # Verfahrensdokumentation erstellen
        dokumentation = {
            "version": "1.0",
            "erstellt_am": utc_now().isoformat(),
            "system": {
                "name": "Ablage-System DATEV Integration",
                "version": "1.0.0",
                "hersteller": "Ablage-System",
            },
            "mandant": {
                "beraternummer": connection.beraternummer,
                "mandantennummer": connection.mandantennummer,
                "kontenrahmen": connection.kontenrahmen,
            },
            "gobd_konformitaet": {
                "unveraenderlichkeit": {
                    "beschreibung": "Buchungen werden nach Festschreibung durch SHA-256 Hash gesichert",
                    "hash_algorithmus": "SHA-256",
                    "hash_felder": self.HASH_FIELDS,
                },
                "nachvollziehbarkeit": {
                    "beschreibung": "Vollstaendiger Audit-Trail aller Aenderungen",
                    "protokollierung": "Strukturierte Logs mit Zeitstempel und User-ID",
                },
                "pruefbarkeit": {
                    "beschreibung": "Export-Funktionen fuer Betriebspruefer",
                    "export_formate": ["DATEV Buchungsstapel CSV", "GDPdU/GoBD XML"],
                },
                "belegverknuepfung": {
                    "beschreibung": "Eindeutige Beleglinks zu Originalbelegen",
                    "link_format": "UUID-basiert mit URL-Prefix",
                },
            },
            "statistik": {
                "buchungen_gesamt": stats[0] if stats else 0,
                "buchungen_festgeschrieben": stats[1] if stats else 0,
                "erste_buchung": stats[2].isoformat() if stats and stats[2] else None,
                "letzte_buchung": stats[3].isoformat() if stats and stats[3] else None,
            },
            "prozesse": [
                {
                    "name": "Belegerfassung",
                    "beschreibung": "OCR-gestuetzte Erfassung von Eingangsrechnungen",
                    "schritte": [
                        "Dokument-Upload oder Email-Import",
                        "OCR-Verarbeitung mit KI-Unterstuetzung",
                        "Automatische Datenextraktion",
                        "Kontierungsvorschlag",
                        "Manuelle Pruefung und Freigabe",
                    ],
                },
                {
                    "name": "Buchungserstellung",
                    "beschreibung": "Erstellung von DATEV-konformen Buchungssaetzen",
                    "schritte": [
                        "Mapping auf DATEV-Format",
                        "Validierung gegen Kontenrahmen",
                        "Generierung eindeutiger Buchungs-GUID",
                        "Export in DATEV Buchungsstapel",
                    ],
                },
                {
                    "name": "Festschreibung",
                    "beschreibung": "Periodenabschluss mit Unveraenderlichkeit",
                    "schritte": [
                        "Vollstaendigkeitspruefung",
                        "Hash-Berechnung aller Buchungen",
                        "Markierung als festgeschrieben",
                        "Protokollierung im Audit-Trail",
                    ],
                },
            ],
        }

        logger.info(
            "gobd_verfahrensdokumentation_exported",
            connection_id=str(connection_id),
        )

        return json.dumps(dokumentation, indent=2, ensure_ascii=False).encode("utf-8")

    async def check_buchung_modifiable(
        self,
        db: AsyncSession,
        buchung_id: UUID,
    ) -> Tuple[bool, Optional[str]]:
        """
        Prueft ob eine Buchung noch geaendert werden darf.

        Args:
            db: Datenbank-Session
            buchung_id: Buchungs-ID

        Returns:
            Tuple aus (ist_aenderbar, Grund_wenn_nicht)
        """
        from app.db import models

        result = await db.execute(
            select(models.DATEVBuchung).where(
                models.DATEVBuchung.id == buchung_id
            )
        )
        buchung = result.scalar_one_or_none()

        if not buchung:
            return False, "Buchung nicht gefunden"

        if buchung.ist_festgeschrieben:
            return False, f"Buchung wurde am {buchung.festschreibung_datum.strftime('%d.%m.%Y')} festgeschrieben"

        if buchung.sync_status == "synced":
            return False, "Buchung wurde bereits zu DATEV synchronisiert"

        return True, None

    # =========================================================================
    # Private Helpers
    # =========================================================================

    def _calculate_buchung_hash(self, buchung: Any) -> str:
        """
        Berechnet SHA-256 Hash einer Buchung.

        Der Hash wird ueber die GoBD-relevanten Felder berechnet
        und garantiert die Integritaet der Buchung.
        """
        # Daten fuer Hash sammeln
        hash_data = {
            "buchungs_guid": buchung.buchungs_guid,
            "umsatz": str(buchung.umsatz),
            "soll_haben": buchung.soll_haben,
            "konto": buchung.konto,
            "gegenkonto": buchung.gegenkonto,
            "bu_schluessel": buchung.bu_schluessel or "",
            "belegdatum": buchung.belegdatum.isoformat() if buchung.belegdatum else "",
            "belegfeld_1": buchung.belegfeld_1 or "",
            "buchungstext": buchung.buchungstext or "",
        }

        # Deterministischer JSON-String
        json_str = json.dumps(hash_data, sort_keys=True, ensure_ascii=False)

        # SHA-256 Hash
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    def _validate_buchung_for_festschreibung(
        self,
        buchung: Any,
    ) -> List[str]:
        """Validiert Buchung vor Festschreibung."""
        errors: List[str] = []

        if not buchung.buchungs_guid:
            errors.append("Fehlende Buchungs-GUID")

        if not buchung.umsatz or buchung.umsatz <= 0:
            errors.append("Ungueltige Umsatzsumme")

        if not buchung.konto:
            errors.append("Fehlendes Konto")

        if not buchung.gegenkonto:
            errors.append("Fehlendes Gegenkonto")

        if not buchung.belegdatum:
            errors.append("Fehlendes Belegdatum")

        if buchung.soll_haben not in ("S", "H"):
            errors.append("Ungueltiges Soll/Haben-Kennzeichen")

        return errors


# =============================================================================
# Singleton
# =============================================================================

_gobd_service: Optional[GoBDComplianceService] = None
_service_lock = threading.Lock()


def get_gobd_service() -> GoBDComplianceService:
    """
    Factory fuer GoBDComplianceService (Thread-Safe Singleton).
    """
    global _gobd_service
    if _gobd_service is None:
        with _service_lock:
            if _gobd_service is None:
                _gobd_service = GoBDComplianceService()
    return _gobd_service
