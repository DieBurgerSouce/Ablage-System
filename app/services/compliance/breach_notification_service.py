# -*- coding: utf-8 -*-
"""GDPR Breach Notification Service - DSGVO Art. 33-34 Implementierung.

Automatische Datenschutz-Verletzungsmeldung nach DSGVO:
- 72-Stunden-Timer nach Erkennung (Art. 33 Abs. 1)
- Behoerden-Templates (Landesdatenschutzbeauftragte)
- Betroffenen-Benachrichtigungs-Workflow (Art. 34)
- Incident-Investigation-Tracking
- Compliance-Reporting

Gesetzliche Grundlagen:
- Art. 33 DSGVO: Meldung einer Verletzung an die Aufsichtsbehoerde
- Art. 34 DSGVO: Benachrichtigung der betroffenen Personen
- Art. 4 Nr. 12 DSGVO: Definition "Verletzung des Schutzes personenbezogener Daten"

Feinpoliert und durchdacht - Enterprise-grade GDPR Compliance.
"""

import uuid
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

import structlog
from sqlalchemy import select, func, and_, or_, update, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings
from app.db.models import AuditLog, User, AppConfig
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums & Constants
# =============================================================================

class BreachSeverity(str, Enum):
    """Schweregrad der Datenschutzverletzung."""
    LOW = "low"          # Minimales Risiko, keine Meldepflicht
    MEDIUM = "medium"    # Risiko vorhanden, Meldung an Behoerde
    HIGH = "high"        # Hohes Risiko, Meldung + Betroffenenbenachrichtigung
    CRITICAL = "critical"  # Kritisch, sofortige Eskalation


class BreachType(str, Enum):
    """Typen von Datenschutzverletzungen nach Art. 4 Nr. 12 DSGVO."""
    UNAUTHORIZED_ACCESS = "unauthorized_access"     # Unbefugter Zugriff
    DATA_THEFT = "data_theft"                       # Datendiebstahl
    DATA_LOSS = "data_loss"                         # Datenverlust
    ACCIDENTAL_DISCLOSURE = "accidental_disclosure" # Versehentliche Offenlegung
    MALWARE_ATTACK = "malware_attack"               # Malware-Angriff
    SYSTEM_BREACH = "system_breach"                 # Systemeinbruch
    INSIDER_THREAT = "insider_threat"               # Insider-Bedrohung
    PHYSICAL_BREACH = "physical_breach"             # Physischer Einbruch
    VENDOR_BREACH = "vendor_breach"                 # Drittanbieter-Verletzung


class BreachStatus(str, Enum):
    """Status einer Datenschutzverletzung."""
    DETECTED = "detected"               # Erkannt, Untersuchung laeuft
    INVESTIGATING = "investigating"     # In Untersuchung
    CONTAINED = "contained"             # Eingedaemmt
    AUTHORITY_NOTIFIED = "authority_notified"  # Behoerde benachrichtigt
    SUBJECTS_NOTIFIED = "subjects_notified"    # Betroffene benachrichtigt
    RESOLVED = "resolved"               # Abgeschlossen
    CLOSED = "closed"                   # Geschlossen (kein Risiko)


class NotificationStatus(str, Enum):
    """Status der Benachrichtigungen."""
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    NOT_REQUIRED = "not_required"


# DSGVO-konforme Fristen (in Stunden)
AUTHORITY_NOTIFICATION_DEADLINE_HOURS = 72  # Art. 33 Abs. 1 DSGVO
INTERNAL_ESCALATION_HOURS = 24              # Interne Eskalation

# Landesdatenschutzbeauftragte (exemplarisch)
SUPERVISORY_AUTHORITIES: Dict[str, Dict[str, str]] = {
    "DE-BW": {
        "name": "Landesbeauftragter fuer den Datenschutz Baden-Wuerttemberg",
        "email": "poststelle@lfdi.bwl.de",
        "phone": "+49 711 615541-0",
        "address": "Koenigstrasse 10a, 70173 Stuttgart",
        "form_url": "https://www.baden-wuerttemberg.datenschutz.de/online-beschwerde/",
    },
    "DE-BY": {
        "name": "Bayerisches Landesamt fuer Datenschutzaufsicht",
        "email": "poststelle@lda.bayern.de",
        "phone": "+49 981 180093-0",
        "address": "Promenade 18, 91522 Ansbach",
        "form_url": "https://www.lda.bayern.de/de/beschwerde.html",
    },
    "DE-BE": {
        "name": "Berliner Beauftragte fuer Datenschutz und Informationsfreiheit",
        "email": "mailbox@datenschutz-berlin.de",
        "phone": "+49 30 13889-0",
        "address": "Friedrichstrasse 219, 10969 Berlin",
        "form_url": "https://www.datenschutz-berlin.de/kontakt",
    },
    "DE-HE": {
        "name": "Hessischer Beauftragter fuer Datenschutz und Informationsfreiheit",
        "email": "poststelle@datenschutz.hessen.de",
        "phone": "+49 611 1408-0",
        "address": "Gustav-Stresemann-Ring 1, 65189 Wiesbaden",
        "form_url": "https://datenschutz.hessen.de/kontakt",
    },
    "DE-NW": {
        "name": "Landesbeauftragte fuer Datenschutz und Informationsfreiheit NRW",
        "email": "poststelle@ldi.nrw.de",
        "phone": "+49 211 38424-0",
        "address": "Kavalleriestrasse 2-4, 40213 Duesseldorf",
        "form_url": "https://www.ldi.nrw.de/kontakt",
    },
    # Fallback fuer nicht gelistete Bundeslaender
    "DE-DEFAULT": {
        "name": "Bundesbeauftragter fuer den Datenschutz und die Informationsfreiheit",
        "email": "poststelle@bfdi.bund.de",
        "phone": "+49 228 997799-0",
        "address": "Graurheindorfer Strasse 153, 53117 Bonn",
        "form_url": "https://www.bfdi.bund.de/DE/Service/Kontakt/kontakt_node.html",
    },
}


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class AffectedDataCategory:
    """Betroffene Datenkategorie."""
    category: str
    description: str
    count: int = 0
    is_sensitive: bool = False  # Besondere Kategorien nach Art. 9 DSGVO


@dataclass
class BreachReport:
    """Vollstaendiger Bericht einer Datenschutzverletzung."""
    id: str
    breach_type: BreachType
    severity: BreachSeverity
    status: BreachStatus

    # Zeitpunkte
    detected_at: datetime
    occurred_at: Optional[datetime]
    contained_at: Optional[datetime]

    # Beschreibung
    description: str
    root_cause: Optional[str]
    impact_assessment: Optional[str]

    # Betroffene Daten
    affected_data_categories: List[AffectedDataCategory]
    affected_subjects_count: int
    affected_subjects_estimate: bool  # True wenn geschaetzt

    # Massnahmen
    containment_measures: List[str]
    remediation_measures: List[str]
    preventive_measures: List[str]

    # Benachrichtigungsstatus
    authority_notification: NotificationStatus
    authority_notified_at: Optional[datetime]
    subjects_notification: NotificationStatus
    subjects_notified_at: Optional[datetime]

    # Meta
    created_by: str
    company_id: Optional[str]

    # Deadline-Tracking
    deadline_72h: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_deadline_met: bool = True

    def __post_init__(self) -> None:
        """Berechne 72-Stunden-Deadline."""
        self.deadline_72h = self.detected_at + timedelta(hours=AUTHORITY_NOTIFICATION_DEADLINE_HOURS)

        # Pruefen ob Deadline eingehalten
        if self.authority_notification == NotificationStatus.SENT:
            self.is_deadline_met = (
                self.authority_notified_at is not None
                and self.authority_notified_at <= self.deadline_72h
            )
        elif self.authority_notification == NotificationStatus.PENDING:
            self.is_deadline_met = datetime.now(timezone.utc) <= self.deadline_72h


@dataclass
class AuthorityNotificationTemplate:
    """Template fuer Behoerdenbenachrichtigung nach Art. 33 Abs. 3 DSGVO."""
    breach_id: str
    company_name: str
    company_address: str
    dpo_name: str
    dpo_contact: str

    # Art. 33 Abs. 3 Pflichtangaben
    nature_of_breach: str           # Art der Verletzung
    categories_of_data: str         # Kategorien betroffener Daten
    approximate_subjects: str       # Ungefaehre Anzahl Betroffener
    consequences: str               # Wahrscheinliche Folgen
    measures_taken: str             # Ergriffene Massnahmen

    # Kontaktdaten der Aufsichtsbehoerde
    authority_name: str
    authority_email: str
    authority_address: str

    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_text(self) -> str:
        """Generiert Text fuer die Behoerdenbenachrichtigung."""
        return f"""MELDUNG EINER VERLETZUNG DES SCHUTZES PERSONENBEZOGENER DATEN
gemäß Art. 33 DSGVO

An: {self.authority_name}
    {self.authority_address}
    {self.authority_email}

Datum: {self.generated_at.strftime('%d.%m.%Y %H:%M')} Uhr

═══════════════════════════════════════════════════════════════════════════════

1. VERANTWORTLICHER

Unternehmen: {self.company_name}
Adresse: {self.company_address}

Datenschutzbeauftragter: {self.dpo_name}
Kontakt: {self.dpo_contact}

═══════════════════════════════════════════════════════════════════════════════

2. ART DER VERLETZUNG (Art. 33 Abs. 3 lit. a DSGVO)

{self.nature_of_breach}

═══════════════════════════════════════════════════════════════════════════════

3. KATEGORIEN UND ANZAHL DER BETROFFENEN (Art. 33 Abs. 3 lit. a, b DSGVO)

Kategorien der betroffenen personenbezogenen Daten:
{self.categories_of_data}

Ungefähre Anzahl der betroffenen Personen: {self.approximate_subjects}

═══════════════════════════════════════════════════════════════════════════════

4. WAHRSCHEINLICHE FOLGEN (Art. 33 Abs. 3 lit. c DSGVO)

{self.consequences}

═══════════════════════════════════════════════════════════════════════════════

5. ERGRIFFENE MASSNAHMEN (Art. 33 Abs. 3 lit. d DSGVO)

{self.measures_taken}

═══════════════════════════════════════════════════════════════════════════════

Referenznummer: {self.breach_id}

Mit freundlichen Grüßen,

{self.dpo_name}
Datenschutzbeauftragter
{self.company_name}
"""

    def to_html(self) -> str:
        """Generiert HTML fuer die Behoerdenbenachrichtigung."""
        return f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <title>DSGVO Verletzungsmeldung - {self.breach_id}</title>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; margin: 40px; }}
        h1 {{ color: #c0392b; border-bottom: 2px solid #c0392b; padding-bottom: 10px; }}
        h2 {{ color: #2c3e50; margin-top: 30px; }}
        .section {{ background: #f9f9f9; padding: 15px; margin: 10px 0; border-left: 4px solid #3498db; }}
        .critical {{ border-left-color: #c0392b; background: #fdf2f2; }}
        .meta {{ color: #666; font-size: 0.9em; }}
        .ref {{ font-family: monospace; background: #eee; padding: 2px 6px; }}
    </style>
</head>
<body>
    <h1>Meldung einer Verletzung des Schutzes personenbezogener Daten</h1>
    <p class="meta">gemäß Art. 33 DSGVO | Datum: {self.generated_at.strftime('%d.%m.%Y %H:%M')} Uhr</p>

    <h2>1. Verantwortlicher</h2>
    <div class="section">
        <strong>{self.company_name}</strong><br>
        {self.company_address}<br><br>
        <strong>Datenschutzbeauftragter:</strong> {self.dpo_name}<br>
        <strong>Kontakt:</strong> {self.dpo_contact}
    </div>

    <h2>2. Art der Verletzung</h2>
    <div class="section critical">
        {self.nature_of_breach.replace(chr(10), '<br>')}
    </div>

    <h2>3. Betroffene Daten und Personen</h2>
    <div class="section">
        <strong>Kategorien der betroffenen Daten:</strong><br>
        {self.categories_of_data.replace(chr(10), '<br>')}<br><br>
        <strong>Geschätzte Anzahl Betroffener:</strong> {self.approximate_subjects}
    </div>

    <h2>4. Wahrscheinliche Folgen</h2>
    <div class="section">
        {self.consequences.replace(chr(10), '<br>')}
    </div>

    <h2>5. Ergriffene Maßnahmen</h2>
    <div class="section">
        {self.measures_taken.replace(chr(10), '<br>')}
    </div>

    <hr>
    <p class="meta">Referenznummer: <span class="ref">{self.breach_id}</span></p>
</body>
</html>"""


@dataclass
class SubjectNotificationTemplate:
    """Template fuer Betroffenenbenachrichtigung nach Art. 34 DSGVO."""
    breach_id: str
    company_name: str
    dpo_name: str
    dpo_contact: str

    # Art. 34 Abs. 2 Pflichtangaben
    nature_of_breach: str           # Art der Verletzung in klarer Sprache
    consequences: str               # Wahrscheinliche Folgen
    measures_taken: str             # Ergriffene Massnahmen
    recommendations: str            # Empfehlungen fuer Betroffene

    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_text(self) -> str:
        """Generiert Text fuer die Betroffenenbenachrichtigung."""
        return f"""WICHTIGE MITTEILUNG: Verletzung des Schutzes Ihrer personenbezogenen Daten

Sehr geehrte Damen und Herren,

wir müssen Sie leider über einen Vorfall informieren, bei dem möglicherweise Ihre
bei uns gespeicherten personenbezogenen Daten betroffen sind.

WAS IST PASSIERT?
{self.nature_of_breach}

WELCHE FOLGEN SIND MÖGLICH?
{self.consequences}

WAS HABEN WIR UNTERNOMMEN?
{self.measures_taken}

WAS KÖNNEN SIE TUN?
{self.recommendations}

KONTAKT FÜR RÜCKFRAGEN
Unser Datenschutzbeauftragter steht Ihnen für Fragen zur Verfügung:
{self.dpo_name}
{self.dpo_contact}

Wir bedauern diesen Vorfall zutiefst und arbeiten intensiv daran, dass sich ein
solcher Vorfall nicht wiederholt.

Mit freundlichen Grüßen,
{self.company_name}

---
Referenznummer: {self.breach_id}
Datum: {self.generated_at.strftime('%d.%m.%Y')}
"""


@dataclass
class BreachTimeline:
    """Timeline-Eintrag fuer ein Breach."""
    timestamp: datetime
    action: str
    actor: str
    details: Optional[str] = None


@dataclass
class CreateBreachResult:
    """Ergebnis der Breach-Erstellung."""
    success: bool
    breach_id: Optional[str] = None
    deadline_72h: Optional[datetime] = None
    requires_authority_notification: bool = False
    requires_subject_notification: bool = False
    error: Optional[str] = None


# =============================================================================
# Breach Notification Service
# =============================================================================

class BreachNotificationService:
    """
    Service fuer DSGVO-konforme Datenschutzverletzungs-Meldungen.

    Implementiert Art. 33-34 DSGVO:
    - 72-Stunden-Frist fuer Behoerdenbenachrichtigung
    - Risikobasierte Bewertung fuer Betroffenenbenachrichtigung
    - Templates fuer alle Landesdatenschutzbehoerden
    - Vollstaendiges Audit-Trail

    Usage:
        service = get_breach_notification_service()
        result = await service.report_breach(
            db=session,
            breach_type=BreachType.UNAUTHORIZED_ACCESS,
            severity=BreachSeverity.HIGH,
            description="Unbefugter Zugriff auf Kundendaten",
            affected_subjects_count=150,
            affected_data_categories=[
                AffectedDataCategory("name", "Vor- und Nachname", 150),
                AffectedDataCategory("email", "E-Mail-Adresse", 150),
            ],
            reported_by="admin@company.de",
        )
    """

    # Storage Key fuer AppConfig JSONB
    BREACHES_KEY = "gdpr_breach_reports"

    def __init__(self) -> None:
        """Initialisiert den Breach Notification Service."""
        self._breaches: Dict[str, BreachReport] = {}
        self._timelines: Dict[str, List[BreachTimeline]] = {}

    async def report_breach(
        self,
        db: AsyncSession,
        breach_type: BreachType,
        severity: BreachSeverity,
        description: str,
        affected_subjects_count: int,
        affected_data_categories: List[AffectedDataCategory],
        reported_by: str,
        company_id: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
        is_estimate: bool = False,
    ) -> CreateBreachResult:
        """
        Meldet eine neue Datenschutzverletzung.

        Args:
            db: Datenbank-Session
            breach_type: Art der Verletzung
            severity: Schweregrad
            description: Beschreibung des Vorfalls
            affected_subjects_count: Anzahl betroffener Personen
            affected_data_categories: Betroffene Datenkategorien
            reported_by: Melder (User-ID oder E-Mail)
            company_id: Optional Company-ID fuer Multi-Tenant
            occurred_at: Zeitpunkt des Vorfalls (falls bekannt)
            is_estimate: True wenn Anzahl geschaetzt ist

        Returns:
            CreateBreachResult mit Breach-ID und Deadlines
        """
        try:
            # Generiere eindeutige Breach-ID
            breach_id = f"BREACH-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

            now = datetime.now(timezone.utc)
            deadline_72h = now + timedelta(hours=AUTHORITY_NOTIFICATION_DEADLINE_HOURS)

            # Bestimme Meldepflichten basierend auf Schweregrad
            requires_authority = severity in [BreachSeverity.MEDIUM, BreachSeverity.HIGH, BreachSeverity.CRITICAL]
            requires_subjects = severity in [BreachSeverity.HIGH, BreachSeverity.CRITICAL]

            # Erstelle Breach-Report
            breach = BreachReport(
                id=breach_id,
                breach_type=breach_type,
                severity=severity,
                status=BreachStatus.DETECTED,
                detected_at=now,
                occurred_at=occurred_at,
                contained_at=None,
                description=description,
                root_cause=None,
                impact_assessment=None,
                affected_data_categories=affected_data_categories,
                affected_subjects_count=affected_subjects_count,
                affected_subjects_estimate=is_estimate,
                containment_measures=[],
                remediation_measures=[],
                preventive_measures=[],
                authority_notification=NotificationStatus.PENDING if requires_authority else NotificationStatus.NOT_REQUIRED,
                authority_notified_at=None,
                subjects_notification=NotificationStatus.PENDING if requires_subjects else NotificationStatus.NOT_REQUIRED,
                subjects_notified_at=None,
                created_by=reported_by,
                company_id=company_id,
            )

            # Speichere im In-Memory Cache
            self._breaches[breach_id] = breach

            # Initialisiere Timeline
            self._timelines[breach_id] = [
                BreachTimeline(
                    timestamp=now,
                    action="Datenschutzverletzung erkannt und gemeldet",
                    actor=reported_by,
                    details=f"Typ: {breach_type.value}, Schweregrad: {severity.value}"
                )
            ]

            # Persistiere in Datenbank
            await self._persist_breach(db, breach)

            # Logge mit strukturierten Daten (OHNE PII!)
            logger.warning(
                "breach_reported",
                breach_id=breach_id,
                breach_type=breach_type.value,
                severity=severity.value,
                affected_count=affected_subjects_count,
                requires_authority_notification=requires_authority,
                requires_subject_notification=requires_subjects,
                deadline_72h=deadline_72h.isoformat(),
                security_event=True,
            )

            # Starte automatische Alerts
            await self._trigger_internal_alerts(db, breach)

            return CreateBreachResult(
                success=True,
                breach_id=breach_id,
                deadline_72h=deadline_72h,
                requires_authority_notification=requires_authority,
                requires_subject_notification=requires_subjects,
            )

        except Exception as e:
            logger.error(
                "breach_report_failed",
                **safe_error_log(e),
                breach_type=breach_type.value,
            )
            return CreateBreachResult(
                success=False,
                error=safe_error_detail(e, "Datenschutzverletzung-Meldung")
            )

    async def update_breach_status(
        self,
        db: AsyncSession,
        breach_id: str,
        new_status: BreachStatus,
        updated_by: str,
        notes: Optional[str] = None,
    ) -> bool:
        """
        Aktualisiert den Status einer Datenschutzverletzung.

        Args:
            db: Datenbank-Session
            breach_id: Breach-ID
            new_status: Neuer Status
            updated_by: Akteur
            notes: Optionale Notizen

        Returns:
            True bei Erfolg
        """
        breach = await self.get_breach(db, breach_id)
        if not breach:
            logger.warning("breach_not_found", breach_id=breach_id)
            return False

        old_status = breach.status
        breach.status = new_status

        # Setze Timestamps basierend auf Status
        now = datetime.now(timezone.utc)
        if new_status == BreachStatus.CONTAINED:
            breach.contained_at = now
        elif new_status == BreachStatus.AUTHORITY_NOTIFIED:
            breach.authority_notification = NotificationStatus.SENT
            breach.authority_notified_at = now
        elif new_status == BreachStatus.SUBJECTS_NOTIFIED:
            breach.subjects_notification = NotificationStatus.SENT
            breach.subjects_notified_at = now

        # Timeline-Eintrag
        self._add_timeline_entry(
            breach_id,
            f"Status geaendert: {old_status.value} -> {new_status.value}",
            updated_by,
            notes
        )

        # Speichere Aenderungen
        self._breaches[breach_id] = breach
        await self._persist_breach(db, breach)

        logger.info(
            "breach_status_updated",
            breach_id=breach_id,
            old_status=old_status.value,
            new_status=new_status.value,
        )

        return True

    async def add_containment_measure(
        self,
        db: AsyncSession,
        breach_id: str,
        measure: str,
        added_by: str,
    ) -> bool:
        """Fuegt eine Eindaemmungsmassnahme hinzu."""
        breach = await self.get_breach(db, breach_id)
        if not breach:
            return False

        breach.containment_measures.append(measure)
        self._add_timeline_entry(
            breach_id,
            f"Eindaemmungsmassnahme hinzugefuegt: {measure[:100]}...",
            added_by
        )

        await self._persist_breach(db, breach)
        return True

    async def add_remediation_measure(
        self,
        db: AsyncSession,
        breach_id: str,
        measure: str,
        added_by: str,
    ) -> bool:
        """Fuegt eine Behebungsmassnahme hinzu."""
        breach = await self.get_breach(db, breach_id)
        if not breach:
            return False

        breach.remediation_measures.append(measure)
        self._add_timeline_entry(
            breach_id,
            f"Behebungsmassnahme hinzugefuegt: {measure[:100]}...",
            added_by
        )

        await self._persist_breach(db, breach)
        return True

    async def set_root_cause(
        self,
        db: AsyncSession,
        breach_id: str,
        root_cause: str,
        impact_assessment: str,
        updated_by: str,
    ) -> bool:
        """Setzt Root-Cause-Analyse und Impact-Assessment."""
        breach = await self.get_breach(db, breach_id)
        if not breach:
            return False

        breach.root_cause = root_cause
        breach.impact_assessment = impact_assessment

        self._add_timeline_entry(
            breach_id,
            "Root-Cause-Analyse und Impact-Assessment hinzugefuegt",
            updated_by
        )

        await self._persist_breach(db, breach)
        return True

    async def generate_authority_notification(
        self,
        db: AsyncSession,
        breach_id: str,
        state_code: str = "DE-DEFAULT",
        company_name: str = "",
        company_address: str = "",
        dpo_name: str = "",
        dpo_contact: str = "",
    ) -> Optional[AuthorityNotificationTemplate]:
        """
        Generiert die Behoerdenbenachrichtigung nach Art. 33 DSGVO.

        Args:
            db: Datenbank-Session
            breach_id: Breach-ID
            state_code: Bundesland-Code (DE-BW, DE-BY, etc.)
            company_name: Firmenname
            company_address: Firmenadresse
            dpo_name: Name des Datenschutzbeauftragten
            dpo_contact: Kontaktdaten des DSB

        Returns:
            Ausgefuelltes Template oder None
        """
        breach = await self.get_breach(db, breach_id)
        if not breach:
            return None

        # Hole Aufsichtsbehoerde
        authority = SUPERVISORY_AUTHORITIES.get(
            state_code,
            SUPERVISORY_AUTHORITIES["DE-DEFAULT"]
        )

        # Formatiere Datenkategorien
        categories = "\n".join([
            f"- {cat.category}: {cat.description} ({cat.count} Datensaetze)"
            + (" [Besondere Kategorie Art. 9]" if cat.is_sensitive else "")
            for cat in breach.affected_data_categories
        ])

        # Formatiere Massnahmen
        measures = "Eindaemmungsmassnahmen:\n" + "\n".join([
            f"- {m}" for m in breach.containment_measures
        ]) if breach.containment_measures else "Eindaemmungsmassnahmen werden ermittelt."

        if breach.remediation_measures:
            measures += "\n\nBehebungsmassnahmen:\n" + "\n".join([
                f"- {m}" for m in breach.remediation_measures
            ])

        # Bestimme wahrscheinliche Folgen basierend auf Schweregrad
        consequences = self._assess_consequences(breach)

        template = AuthorityNotificationTemplate(
            breach_id=breach_id,
            company_name=company_name or getattr(settings, "COMPANY_NAME", "Unternehmen"),
            company_address=company_address or getattr(settings, "COMPANY_ADDRESS", ""),
            dpo_name=dpo_name or getattr(settings, "DPO_NAME", "Datenschutzbeauftragter"),
            dpo_contact=dpo_contact or getattr(settings, "DPO_EMAIL", "datenschutz@unternehmen.de"),
            nature_of_breach=f"{breach.breach_type.value}: {breach.description}",
            categories_of_data=categories,
            approximate_subjects=f"{'ca. ' if breach.affected_subjects_estimate else ''}{breach.affected_subjects_count} Personen",
            consequences=consequences,
            measures_taken=measures,
            authority_name=authority["name"],
            authority_email=authority["email"],
            authority_address=authority["address"],
        )

        self._add_timeline_entry(
            breach_id,
            f"Behoerdenbenachrichtigung generiert fuer {authority['name']}",
            "system"
        )

        return template

    async def generate_subject_notification(
        self,
        db: AsyncSession,
        breach_id: str,
        company_name: str = "",
        dpo_name: str = "",
        dpo_contact: str = "",
    ) -> Optional[SubjectNotificationTemplate]:
        """
        Generiert die Betroffenenbenachrichtigung nach Art. 34 DSGVO.

        Args:
            db: Datenbank-Session
            breach_id: Breach-ID
            company_name: Firmenname
            dpo_name: Name des Datenschutzbeauftragten
            dpo_contact: Kontaktdaten des DSB

        Returns:
            Ausgefuelltes Template oder None
        """
        breach = await self.get_breach(db, breach_id)
        if not breach:
            return None

        # Klare Beschreibung fuer Betroffene
        nature = self._translate_breach_type_for_subjects(breach)
        consequences = self._assess_consequences_for_subjects(breach)
        recommendations = self._get_recommendations(breach)

        # Formatiere Massnahmen
        measures = []
        if breach.containment_measures:
            measures.extend(breach.containment_measures)
        if breach.remediation_measures:
            measures.extend(breach.remediation_measures)

        measures_text = "\n".join([f"• {m}" for m in measures]) if measures else "Massnahmen werden aktuell umgesetzt."

        template = SubjectNotificationTemplate(
            breach_id=breach_id,
            company_name=company_name or getattr(settings, "COMPANY_NAME", "Unternehmen"),
            dpo_name=dpo_name or getattr(settings, "DPO_NAME", "Datenschutzbeauftragter"),
            dpo_contact=dpo_contact or getattr(settings, "DPO_EMAIL", "datenschutz@unternehmen.de"),
            nature_of_breach=nature,
            consequences=consequences,
            measures_taken=measures_text,
            recommendations=recommendations,
        )

        self._add_timeline_entry(
            breach_id,
            "Betroffenenbenachrichtigung generiert",
            "system"
        )

        return template

    async def get_breach(
        self,
        db: AsyncSession,
        breach_id: str,
    ) -> Optional[BreachReport]:
        """Holt einen Breach-Report."""
        # Erst Cache pruefen
        if breach_id in self._breaches:
            return self._breaches[breach_id]

        # Dann Datenbank
        return await self._load_breach(db, breach_id)

    async def list_breaches(
        self,
        db: AsyncSession,
        company_id: Optional[str] = None,
        status: Optional[BreachStatus] = None,
        severity: Optional[BreachSeverity] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[BreachReport], int]:
        """
        Listet Datenschutzverletzungen mit Filterung.

        Returns:
            Tuple aus Liste der Breaches und Gesamtanzahl
        """
        breaches = list(self._breaches.values())

        # Filter anwenden
        if company_id:
            breaches = [b for b in breaches if b.company_id == company_id]
        if status:
            breaches = [b for b in breaches if b.status == status]
        if severity:
            breaches = [b for b in breaches if b.severity == severity]

        # Sortieren nach Erkennungszeitpunkt (neueste zuerst)
        breaches.sort(key=lambda b: b.detected_at, reverse=True)

        total = len(breaches)
        breaches = breaches[offset:offset + limit]

        return breaches, total

    async def get_pending_deadlines(
        self,
        db: AsyncSession,
        company_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Gibt Breaches mit anstehenden Deadlines zurueck.

        Returns:
            Liste mit Breach-ID, Deadline und verbleibender Zeit
        """
        now = datetime.now(timezone.utc)
        pending = []

        for breach_id, breach in self._breaches.items():
            if breach.authority_notification != NotificationStatus.PENDING:
                continue
            if company_id and breach.company_id != company_id:
                continue

            remaining = breach.deadline_72h - now
            hours_remaining = remaining.total_seconds() / 3600

            pending.append({
                "breach_id": breach_id,
                "severity": breach.severity.value,
                "deadline_72h": breach.deadline_72h.isoformat(),
                "hours_remaining": round(hours_remaining, 1),
                "is_overdue": hours_remaining < 0,
                "urgency": "critical" if hours_remaining < 12 else "high" if hours_remaining < 24 else "medium",
            })

        # Sortieren nach Dringlichkeit
        pending.sort(key=lambda p: p["hours_remaining"])

        return pending

    async def get_timeline(
        self,
        breach_id: str,
    ) -> List[Dict[str, Any]]:
        """Gibt die Timeline eines Breach zurueck."""
        entries = self._timelines.get(breach_id, [])
        return [
            {
                "timestamp": e.timestamp.isoformat(),
                "action": e.action,
                "actor": e.actor,
                "details": e.details,
            }
            for e in entries
        ]

    async def check_deadline_alerts(
        self,
        db: AsyncSession,
    ) -> List[Dict[str, Any]]:
        """
        Prueft alle Deadlines und gibt Alerts zurueck.

        Wird von Celery Task periodisch aufgerufen.

        Returns:
            Liste von Alerts fuer kritische Deadlines
        """
        alerts = []
        now = datetime.now(timezone.utc)

        for breach_id, breach in self._breaches.items():
            if breach.authority_notification != NotificationStatus.PENDING:
                continue

            remaining = breach.deadline_72h - now
            hours_remaining = remaining.total_seconds() / 3600

            # Alerts bei bestimmten Schwellenwerten
            if hours_remaining <= 0:
                alerts.append({
                    "breach_id": breach_id,
                    "severity": "critical",
                    "message": f"UEBERFAELLIG: 72-Stunden-Frist fuer Breach {breach_id} ist abgelaufen!",
                    "hours_overdue": abs(hours_remaining),
                })
            elif hours_remaining <= 12:
                alerts.append({
                    "breach_id": breach_id,
                    "severity": "high",
                    "message": f"DRINGEND: Nur noch {round(hours_remaining, 1)} Stunden fuer Breach {breach_id}!",
                    "hours_remaining": hours_remaining,
                })
            elif hours_remaining <= 24:
                alerts.append({
                    "breach_id": breach_id,
                    "severity": "medium",
                    "message": f"WARNUNG: Noch {round(hours_remaining, 1)} Stunden fuer Breach {breach_id}.",
                    "hours_remaining": hours_remaining,
                })

        # Logge kritische Alerts
        for alert in alerts:
            if alert["severity"] == "critical":
                logger.critical(
                    "breach_deadline_missed",
                    breach_id=alert["breach_id"],
                    hours_overdue=alert.get("hours_overdue", 0),
                    security_event=True,
                )

        return alerts

    def _add_timeline_entry(
        self,
        breach_id: str,
        action: str,
        actor: str,
        details: Optional[str] = None,
    ) -> None:
        """Fuegt einen Timeline-Eintrag hinzu."""
        if breach_id not in self._timelines:
            self._timelines[breach_id] = []

        self._timelines[breach_id].append(
            BreachTimeline(
                timestamp=datetime.now(timezone.utc),
                action=action,
                actor=actor,
                details=details,
            )
        )

    def _assess_consequences(self, breach: BreachReport) -> str:
        """Bewertet wahrscheinliche Folgen fuer Behoerdenmeldung."""
        consequences = []

        # Basierend auf Schweregrad
        if breach.severity == BreachSeverity.CRITICAL:
            consequences.append("Erhebliches Risiko fuer Rechte und Freiheiten der betroffenen Personen.")
        elif breach.severity == BreachSeverity.HIGH:
            consequences.append("Hohes Risiko fuer betroffene Personen.")
        elif breach.severity == BreachSeverity.MEDIUM:
            consequences.append("Moderates Risiko fuer betroffene Personen.")

        # Basierend auf Datentypen
        has_sensitive = any(cat.is_sensitive for cat in breach.affected_data_categories)
        if has_sensitive:
            consequences.append("Besondere Kategorien personenbezogener Daten (Art. 9 DSGVO) sind betroffen.")

        # Basierend auf Breach-Typ
        if breach.breach_type == BreachType.DATA_THEFT:
            consequences.append("Moeglicherweise Identitaetsdiebstahl oder Betrug.")
        elif breach.breach_type == BreachType.UNAUTHORIZED_ACCESS:
            consequences.append("Unbefugte koennten auf persoenliche Daten zugreifen.")
        elif breach.breach_type == BreachType.DATA_LOSS:
            consequences.append("Datenverlust kann zu eingeschraenkten Diensten fuehren.")

        return "\n".join(consequences) if consequences else "Risikobewertung wird durchgefuehrt."

    def _assess_consequences_for_subjects(self, breach: BreachReport) -> str:
        """Bewertet Folgen in klarer Sprache fuer Betroffene."""
        consequences = []

        if breach.breach_type == BreachType.DATA_THEFT:
            consequences.append("Es besteht die Moeglichkeit, dass Ihre Daten missbraucht werden koennten.")
        elif breach.breach_type == BreachType.UNAUTHORIZED_ACCESS:
            consequences.append("Unbefugte Personen koennten Zugang zu Ihren Daten erhalten haben.")
        elif breach.breach_type == BreachType.ACCIDENTAL_DISCLOSURE:
            consequences.append("Ihre Daten koennten versehentlich an Dritte gelangt sein.")

        # Kategorie-spezifisch
        categories = [cat.category.lower() for cat in breach.affected_data_categories]
        if "email" in categories:
            consequences.append("Sie koennten unerwuenschte E-Mails (Spam/Phishing) erhalten.")
        if "iban" in categories or "bankdaten" in categories:
            consequences.append("Ueberwachen Sie bitte Ihre Kontoauszuege auf ungewoehnliche Aktivitaeten.")

        return "\n".join(consequences) if consequences else "Wir analysieren moegliche Auswirkungen."

    def _translate_breach_type_for_subjects(self, breach: BreachReport) -> str:
        """Uebersetzt Breach-Typ in verstaendliche Sprache."""
        translations = {
            BreachType.UNAUTHORIZED_ACCESS: "Es gab einen unbefugten Zugriff auf unsere Systeme, bei dem möglicherweise Ihre Daten eingesehen wurden.",
            BreachType.DATA_THEFT: "Wir haben festgestellt, dass Daten unrechtmäßig kopiert wurden.",
            BreachType.DATA_LOSS: "Durch einen technischen Vorfall sind Daten verloren gegangen.",
            BreachType.ACCIDENTAL_DISCLOSURE: "Aufgrund eines Fehlers wurden Daten versehentlich offengelegt.",
            BreachType.MALWARE_ATTACK: "Unsere Systeme wurden von Schadsoftware befallen.",
            BreachType.SYSTEM_BREACH: "Ein Sicherheitsvorfall hat zu einem Systemeinbruch geführt.",
            BreachType.INSIDER_THREAT: "Ein interner Vorfall führte zur Kompromittierung von Daten.",
            BreachType.PHYSICAL_BREACH: "Es gab einen physischen Sicherheitsvorfall.",
            BreachType.VENDOR_BREACH: "Ein von uns genutzter Dienstleister hatte einen Sicherheitsvorfall.",
        }
        base = translations.get(breach.breach_type, breach.description)
        return f"{base}\n\n{breach.description}"

    def _get_recommendations(self, breach: BreachReport) -> str:
        """Generiert Empfehlungen fuer Betroffene."""
        recommendations = ["Seien Sie aufmerksam bei ungewoehnlichen Kontaktversuchen."]

        categories = [cat.category.lower() for cat in breach.affected_data_categories]

        if "passwort" in categories or "password" in categories:
            recommendations.insert(0, "Aendern Sie umgehend Ihr Passwort bei unserem Dienst und bei anderen Diensten, falls Sie das gleiche Passwort verwendet haben.")

        if "email" in categories:
            recommendations.append("Seien Sie besonders vorsichtig bei E-Mails, die vorgeben von uns zu sein. Pruefen Sie Links sorgfaeltig.")

        if "iban" in categories or "bankdaten" in categories or "kreditkarte" in categories:
            recommendations.append("Ueberwachen Sie Ihre Kontoauszuege regelmaessig und melden Sie verdaechtige Transaktionen sofort Ihrer Bank.")

        if "ausweis" in categories or "personalausweis" in categories:
            recommendations.append("Erwaegen Sie eine Auskunftssperre beim Einwohnermeldeamt und pruefen Sie regelmaessig Ihre Schufa-Auskunft.")

        return "\n".join([f"• {r}" for r in recommendations])

    async def _trigger_internal_alerts(
        self,
        db: AsyncSession,
        breach: BreachReport,
    ) -> None:
        """Loest interne Alerts aus."""
        try:
            from app.services.notification_service import NotificationService


            service = NotificationService()

            # Admin-Alert
            await service.send_admin_alert(
                subject=f"DATENSCHUTZVERLETZUNG: {breach.breach_type.value} - {breach.severity.value}",
                message=f"""Eine neue Datenschutzverletzung wurde gemeldet.

Breach-ID: {breach.id}
Typ: {breach.breach_type.value}
Schweregrad: {breach.severity.value}
Betroffene: ca. {breach.affected_subjects_count} Personen
72h-Deadline: {breach.deadline_72h.strftime('%d.%m.%Y %H:%M')} Uhr

Bitte pruefen Sie den Vorfall und leiten Sie die erforderlichen Massnahmen ein.
""",
                priority="critical" if breach.severity == BreachSeverity.CRITICAL else "high",
            )

        except Exception as e:
            logger.warning("breach_alert_failed", breach_id=breach.id, **safe_error_log(e))

    async def _persist_breach(
        self,
        db: AsyncSession,
        breach: BreachReport,
    ) -> None:
        """Persistiert Breach in der Datenbank."""
        # Serialisiere Breach fuer JSONB
        breach_data = {
            "id": breach.id,
            "breach_type": breach.breach_type.value,
            "severity": breach.severity.value,
            "status": breach.status.value,
            "detected_at": breach.detected_at.isoformat(),
            "occurred_at": breach.occurred_at.isoformat() if breach.occurred_at else None,
            "contained_at": breach.contained_at.isoformat() if breach.contained_at else None,
            "description": breach.description,
            "root_cause": breach.root_cause,
            "impact_assessment": breach.impact_assessment,
            "affected_data_categories": [
                {
                    "category": cat.category,
                    "description": cat.description,
                    "count": cat.count,
                    "is_sensitive": cat.is_sensitive,
                }
                for cat in breach.affected_data_categories
            ],
            "affected_subjects_count": breach.affected_subjects_count,
            "affected_subjects_estimate": breach.affected_subjects_estimate,
            "containment_measures": breach.containment_measures,
            "remediation_measures": breach.remediation_measures,
            "preventive_measures": breach.preventive_measures,
            "authority_notification": breach.authority_notification.value,
            "authority_notified_at": breach.authority_notified_at.isoformat() if breach.authority_notified_at else None,
            "subjects_notification": breach.subjects_notification.value,
            "subjects_notified_at": breach.subjects_notified_at.isoformat() if breach.subjects_notified_at else None,
            "created_by": breach.created_by,
            "company_id": breach.company_id,
            "deadline_72h": breach.deadline_72h.isoformat(),
        }

        # Hole oder erstelle AppConfig-Eintrag
        result = await db.execute(
            select(AppConfig).where(AppConfig.key == self.BREACHES_KEY)
        )
        config = result.scalar_one_or_none()

        if config:
            breaches = config.value or {}
            breaches[breach.id] = breach_data
            config.value = breaches
        else:
            config = AppConfig(
                key=self.BREACHES_KEY,
                value={breach.id: breach_data},
            )
            db.add(config)

        await db.commit()

    async def _load_breach(
        self,
        db: AsyncSession,
        breach_id: str,
    ) -> Optional[BreachReport]:
        """Laedt Breach aus der Datenbank."""
        result = await db.execute(
            select(AppConfig).where(AppConfig.key == self.BREACHES_KEY)
        )
        config = result.scalar_one_or_none()

        if not config or not config.value:
            return None

        breach_data = config.value.get(breach_id)
        if not breach_data:
            return None

        return self._deserialize_breach(breach_data)

    def _deserialize_breach(self, data: Dict[str, Any]) -> BreachReport:
        """Deserialisiert Breach aus JSONB-Daten."""
        return BreachReport(
            id=data["id"],
            breach_type=BreachType(data["breach_type"]),
            severity=BreachSeverity(data["severity"]),
            status=BreachStatus(data["status"]),
            detected_at=datetime.fromisoformat(data["detected_at"]),
            occurred_at=datetime.fromisoformat(data["occurred_at"]) if data.get("occurred_at") else None,
            contained_at=datetime.fromisoformat(data["contained_at"]) if data.get("contained_at") else None,
            description=data["description"],
            root_cause=data.get("root_cause"),
            impact_assessment=data.get("impact_assessment"),
            affected_data_categories=[
                AffectedDataCategory(
                    category=cat["category"],
                    description=cat["description"],
                    count=cat["count"],
                    is_sensitive=cat.get("is_sensitive", False),
                )
                for cat in data.get("affected_data_categories", [])
            ],
            affected_subjects_count=data["affected_subjects_count"],
            affected_subjects_estimate=data.get("affected_subjects_estimate", False),
            containment_measures=data.get("containment_measures", []),
            remediation_measures=data.get("remediation_measures", []),
            preventive_measures=data.get("preventive_measures", []),
            authority_notification=NotificationStatus(data["authority_notification"]),
            authority_notified_at=datetime.fromisoformat(data["authority_notified_at"]) if data.get("authority_notified_at") else None,
            subjects_notification=NotificationStatus(data["subjects_notification"]),
            subjects_notified_at=datetime.fromisoformat(data["subjects_notified_at"]) if data.get("subjects_notified_at") else None,
            created_by=data["created_by"],
            company_id=data.get("company_id"),
        )


# =============================================================================
# Singleton Instance
# =============================================================================

_breach_notification_service: Optional[BreachNotificationService] = None


def get_breach_notification_service() -> BreachNotificationService:
    """Gibt BreachNotificationService-Singleton zurueck."""
    global _breach_notification_service
    if _breach_notification_service is None:
        _breach_notification_service = BreachNotificationService()
    return _breach_notification_service


# Alias fuer Convenience
breach_notification_service = get_breach_notification_service
