"""ISO 27001 Gap-Analyse-Service."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Union

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class AnnexAControl:
    """ISO 27001 Annex A Kontrolle."""

    control_id: str
    control_group: str
    control_name: str
    description: str
    status: str  # "erfuellt", "teilweise", "offen"
    evidence: List[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class GapAnalysisReport:
    """Gap-Analyse-Bericht."""

    report_id: str
    generated_at: str
    controls: List[AnnexAControl]
    compliance_score: float
    group_scores: Dict[str, float]
    summary: str


class ISO27001GapAnalysis:
    """ISO 27001 Gap-Analyse-Service."""

    # ISO 27001:2022 Annex A Controls
    ANNEX_A_CONTROLS: Dict[str, List[Dict[str, str]]] = {
        "A.5 Informationssicherheitsrichtlinien": [
            {
                "id": "A.5.1",
                "name": "Richtlinien fuer Informationssicherheit",
                "description": (
                    "Eine Gesamtrichtlinie und "
                    "themenspezifische Richtlinien fuer "
                    "Informationssicherheit sollten definiert, "
                    "von der Geschaeftsleitung genehmigt und "
                    "veroeffentlicht werden."
                ),
            },
            {
                "id": "A.5.2",
                "name": "Ueberpruefung der Richtlinien",
                "description": (
                    "Die Richtlinien fuer "
                    "Informationssicherheit sollten in "
                    "regelmaessigen Abstaenden oder bei "
                    "wesentlichen Aenderungen ueberprueft "
                    "werden."
                ),
            },
        ],
        "A.6 Organisation der Informationssicherheit": [
            {
                "id": "A.6.1",
                "name": (
                    "Verantwortlichkeiten fuer "
                    "Informationssicherheit"
                ),
                "description": (
                    "Alle Verantwortlichkeiten fuer "
                    "Informationssicherheit sollten "
                    "definiert und zugewiesen werden."
                ),
            },
            {
                "id": "A.6.2",
                "name": "Aufgabentrennung",
                "description": (
                    "Widerspruechliche Aufgaben und "
                    "Verantwortungsbereiche sollten "
                    "getrennt werden."
                ),
            },
        ],
        "A.8 Asset-Management": [
            {
                "id": "A.8.1",
                "name": "Inventarisierung von Assets",
                "description": (
                    "Assets, die mit Informationen und "
                    "Informationsverarbeitungseinrichtungen "
                    "verbunden sind, sollten identifiziert "
                    "werden."
                ),
            },
            {
                "id": "A.8.2",
                "name": "Klassifizierung von Informationen",
                "description": (
                    "Informationen sollten nach rechtlichen "
                    "Anforderungen, Wert, Kritikalitaet und "
                    "Sensitivitaet klassifiziert werden."
                ),
            },
        ],
        "A.9 Zugriffskontrolle": [
            {
                "id": "A.9.1",
                "name": "Richtlinien zur Zugriffskontrolle",
                "description": (
                    "Eine Richtlinie zur Zugriffskontrolle "
                    "sollte etabliert, dokumentiert und "
                    "ueberprueft werden."
                ),
            },
            {
                "id": "A.9.2",
                "name": "Verwaltung von Benutzerzugriffen",
                "description": (
                    "Ein formales Verfahren zur Registrierung "
                    "und Abmeldung von Benutzern sollte "
                    "implementiert werden."
                ),
            },
            {
                "id": "A.9.3",
                "name": "Verwaltung von Systemzugriffen",
                "description": (
                    "Der Zugriff auf Systeme und Anwendungen "
                    "sollte in Uebereinstimmung mit der "
                    "Zugriffskontrollrichtlinie kontrolliert "
                    "werden."
                ),
            },
        ],
        "A.10 Kryptographie": [
            {
                "id": "A.10.1",
                "name": "Kryptographische Massnahmen",
                "description": (
                    "Richtlinien zur Verwendung "
                    "kryptographischer Massnahmen sollten "
                    "entwickelt und implementiert werden."
                ),
            },
            {
                "id": "A.10.2",
                "name": "Schluesselmanagement",
                "description": (
                    "Richtlinien zur Verwendung, zum Schutz "
                    "und zur Lebensdauer kryptographischer "
                    "Schluessel sollten entwickelt und "
                    "implementiert werden."
                ),
            },
        ],
        "A.12 Betriebssicherheit": [
            {
                "id": "A.12.1",
                "name": "Dokumentierte Betriebsverfahren",
                "description": (
                    "Betriebsverfahren sollten dokumentiert "
                    "und allen Benutzern zugaenglich gemacht "
                    "werden."
                ),
            },
            {
                "id": "A.12.2",
                "name": "Schutz vor Malware",
                "description": (
                    "Erkennungs-, Praevention- und "
                    "Wiederherstellungsmassnahmen zum Schutz "
                    "vor Malware sollten implementiert "
                    "werden."
                ),
            },
            {
                "id": "A.12.3",
                "name": "Datensicherung",
                "description": (
                    "Sicherungskopien von Informationen, "
                    "Software und Systemabbildern sollten "
                    "regelmaessig erstellt und getestet "
                    "werden."
                ),
            },
        ],
        "A.14 Systementwicklung": [
            {
                "id": "A.14.1",
                "name": "Sicherheitsanforderungen",
                "description": (
                    "Informationssicherheitsanforderungen "
                    "sollten in Anforderungen fuer neue "
                    "Informationssysteme einbezogen werden."
                ),
            },
            {
                "id": "A.14.2",
                "name": "Sicherheit in Testdaten",
                "description": (
                    "Testdaten sollten sorgfaeltig "
                    "ausgewaehlt, geschuetzt und "
                    "kontrolliert werden."
                ),
            },
        ],
        "A.16 Informationssicherheitsvorfaelle": [
            {
                "id": "A.16.1",
                "name": "Verantwortlichkeiten und Verfahren",
                "description": (
                    "Verantwortlichkeiten und Verfahren "
                    "fuer ein schnelles und effektives "
                    "Management von "
                    "Informationssicherheitsvorfaellen "
                    "sollten etabliert werden."
                ),
            },
            {
                "id": "A.16.2",
                "name": (
                    "Meldung von "
                    "Informationssicherheitsereignissen"
                ),
                "description": (
                    "Informationssicherheitsereignisse "
                    "sollten durch geeignete "
                    "Managementkanaele so schnell wie "
                    "moeglich gemeldet werden."
                ),
            },
        ],
        "A.18 Compliance": [
            {
                "id": "A.18.1",
                "name": "Einhaltung rechtlicher Anforderungen",
                "description": (
                    "Alle relevanten gesetzlichen, "
                    "regulatorischen und vertraglichen "
                    "Anforderungen sollten identifiziert "
                    "und dokumentiert werden."
                ),
            },
            {
                "id": "A.18.2",
                "name": "Ueberpruefung der Informationssicherheit",
                "description": (
                    "Die Informationssicherheit sollte "
                    "regelmaessig ueberprueft werden."
                ),
            },
        ],
    }

    def __init__(self) -> None:
        """Initialisiert den Gap-Analyse-Service."""
        self.logger = logger.bind(service="iso27001_gap_analysis")

    async def run_gap_analysis(self) -> GapAnalysisReport:
        """Fuehrt vollstaendige Gap-Analyse gegen ISO 27001 Annex A Kontrollen durch.

        Returns:
            GapAnalysisReport mit Bewertung aller Kontrollen.
        """
        self.logger.info("gap_analysis_started")

        controls: List[AnnexAControl] = []

        # Evaluate all controls
        for group_name, group_controls in self.ANNEX_A_CONTROLS.items():
            for control_def in group_controls:
                control = await self._evaluate_control(
                    control_id=control_def["id"],
                    control_group=group_name,
                    control_name=control_def["name"],
                    description=control_def["description"],
                )
                controls.append(control)

        # Calculate scores
        compliance_score = self._calculate_compliance_score(controls)
        group_scores = self._calculate_group_scores(controls)

        report = GapAnalysisReport(
            report_id=str(uuid.uuid4()),
            generated_at=datetime.now(timezone.utc).isoformat(),
            controls=controls,
            compliance_score=compliance_score,
            group_scores=group_scores,
            summary=self.generate_summary(controls, compliance_score),
        )

        self.logger.info(
            "gap_analysis_completed",
            compliance_score=compliance_score,
            total_controls=len(controls),
        )

        return report

    async def _evaluate_control(
        self,
        control_id: str,
        control_group: str,
        control_name: str,
        description: str,
    ) -> AnnexAControl:
        """Bewertet eine einzelne Kontrolle gegen die Systemimplementierung.

        Args:
            control_id: Kontroll-Identifikator (z.B. "A.9.2").
            control_group: Name der Kontrollgruppe.
            control_name: Name der Kontrolle.
            description: Beschreibung der Kontrolle.

        Returns:
            AnnexAControl mit Bewertungsergebnis.
        """
        # Map controls to actual system features
        evaluation_map: Dict[str, Dict[str, Union[str, List[str]]]] = {
            # A.5 - Policies (mostly missing formal ISMS)
            "A.5.1": {
                "status": "offen",
                "evidence": [],
                "notes": (
                    "Keine formale ISMS-Dokumentation "
                    "vorhanden. Technische "
                    "Sicherheitsmassnahmen implementiert, "
                    "aber nicht in Richtlinien dokumentiert."
                ),
            },
            "A.5.2": {
                "status": "offen",
                "evidence": [],
                "notes": (
                    "Keine regelmaessige "
                    "Richtlinienueberpruefung etabliert."
                ),
            },
            # A.6 - Organization
            "A.6.1": {
                "status": "teilweise",
                "evidence": [
                    "RBAC System",
                    "Benutzerrollen definiert",
                ],
                "notes": (
                    "Technische Verantwortlichkeiten klar "
                    "(RBAC), organisatorische "
                    "ISMS-Verantwortlichkeiten nicht "
                    "formalisiert."
                ),
            },
            "A.6.2": {
                "status": "erfuellt",
                "evidence": [
                    "RBAC Rollen-Trennung",
                    "Multi-User Permissions",
                ],
                "notes": (
                    "Aufgabentrennung durch "
                    "RBAC-System technisch umgesetzt."
                ),
            },
            # A.8 - Asset Management
            "A.8.1": {
                "status": "teilweise",
                "evidence": [
                    "Dokumenten-Inventar",
                    "MinIO Storage Management",
                ],
                "notes": (
                    "Dokumente werden inventarisiert, aber "
                    "kein umfassendes IT-Asset-Management."
                ),
            },
            "A.8.2": {
                "status": "teilweise",
                "evidence": [
                    "Folder-basierte Klassifizierung",
                    "Entity-Kategorien",
                ],
                "notes": (
                    "Informationsklassifizierung durch "
                    "Folder-Struktur, aber keine formale "
                    "Klassifizierungsrichtlinie."
                ),
            },
            # A.9 - Access Control (well implemented)
            "A.9.1": {
                "status": "erfuellt",
                "evidence": [
                    "JWT Authentication",
                    "RBAC System",
                    "Rate Limiting",
                ],
                "notes": (
                    "Zugriffskontrolle technisch "
                    "vollstaendig implementiert mit JWT, "
                    "RBAC und Rate Limiting."
                ),
            },
            "A.9.2": {
                "status": "erfuellt",
                "evidence": [
                    "Benutzerregistrierung mit Approval",
                    "JWT Token Management (15min/7d)",
                    "Session Management",
                ],
                "notes": (
                    "Formales "
                    "Benutzer-Lifecycle-Management mit "
                    "Token-Expiration und Session-Kontrolle."
                ),
            },
            "A.9.3": {
                "status": "erfuellt",
                "evidence": [
                    "RBAC Permissions",
                    "Document Owner Checks",
                    "Sharing Permissions",
                ],
                "notes": (
                    "Systemzugriff durch granulare "
                    "Permissions kontrolliert."
                ),
            },
            # A.10 - Cryptography (well implemented)
            "A.10.1": {
                "status": "erfuellt",
                "evidence": [
                    "TLS/HTTPS",
                    "PostgreSQL Encryption at Rest",
                    "bcrypt Password Hashing (cost 12)",
                ],
                "notes": (
                    "Kryptographie umfassend implementiert: "
                    "TLS, DB-Verschluesselung, bcrypt."
                ),
            },
            "A.10.2": {
                "status": "erfuellt",
                "evidence": [
                    "JWT Secret Management",
                    "PostgreSQL Encryption Keys",
                    "Environment Variables fuer Secrets",
                ],
                "notes": (
                    "Schluessel werden sicher in Environment "
                    "Variables verwaltet, keine Hardcoding."
                ),
            },
            # A.12 - Operations
            "A.12.1": {
                "status": "teilweise",
                "evidence": [
                    "API Dokumentation",
                    "Runbooks (19 Stueck)",
                ],
                "notes": (
                    "Technische Dokumentation vorhanden "
                    "(Runbooks, API Docs), aber nicht alle "
                    "Betriebsverfahren formal dokumentiert."
                ),
            },
            "A.12.2": {
                "status": "teilweise",
                "evidence": [
                    "File Upload Validation",
                    "MIME Type Checks",
                ],
                "notes": (
                    "Grundlegender Malware-Schutz durch "
                    "Validierung, aber kein dedizierter "
                    "Antivirus-Scanner."
                ),
            },
            "A.12.3": {
                "status": "teilweise",
                "evidence": [
                    "PostgreSQL Backup-Konfiguration",
                    "MinIO Storage",
                ],
                "notes": (
                    "Backup-Infrastruktur vorhanden, aber "
                    "kein dokumentierter Backup-Test-Plan."
                ),
            },
            # A.14 - Development
            "A.14.1": {
                "status": "erfuellt",
                "evidence": [
                    "Security Requirements in CLAUDE.md",
                    "Type Safety (mypy strict)",
                    "Input Validation (Pydantic)",
                ],
                "notes": (
                    "Sicherheitsanforderungen von Anfang an "
                    "in Entwicklung integriert."
                ),
            },
            "A.14.2": {
                "status": "erfuellt",
                "evidence": [
                    "Test Isolation",
                    "Pytest Fixtures",
                    "Mock Data",
                ],
                "notes": (
                    "Testdaten werden durch Fixtures und "
                    "Mocks von Produktionsdaten getrennt."
                ),
            },
            # A.16 - Incident Management
            "A.16.1": {
                "status": "teilweise",
                "evidence": [
                    "Alert Center",
                    "Slack Integration",
                    "Notification System",
                ],
                "notes": (
                    "Alert Center vorhanden, aber kein "
                    "formaler Incident-Response-Plan "
                    "dokumentiert."
                ),
            },
            "A.16.2": {
                "status": "teilweise",
                "evidence": [
                    "Alert Center",
                    "Slack Notifications",
                    "Email Alerts",
                ],
                "notes": (
                    "Automatische Meldung von "
                    "Sicherheitsereignissen ueber Alert "
                    "Center, aber keine formalen "
                    "Meldekanaele definiert."
                ),
            },
            # A.18 - Compliance
            "A.18.1": {
                "status": "teilweise",
                "evidence": [
                    "GDPR Compliance Module",
                    "Data Retention Policies",
                    "Audit Logging",
                ],
                "notes": (
                    "GDPR-Anforderungen teilweise umgesetzt, "
                    "aber keine umfassende rechtliche "
                    "Compliance-Dokumentation."
                ),
            },
            "A.18.2": {
                "status": "teilweise",
                "evidence": [
                    "Audit Logs",
                    "Structured Logging (structlog)",
                ],
                "notes": (
                    "Technisches Audit-Logging vorhanden, "
                    "aber keine regelmaessigen formalen "
                    "Security Reviews."
                ),
            },
        }

        eval_result = evaluation_map.get(control_id, {
            "status": "offen",
            "evidence": [],
            "notes": "Keine Evaluierung verfuegbar.",
        })

        return AnnexAControl(
            control_id=control_id,
            control_group=control_group,
            control_name=control_name,
            description=description,
            status=str(eval_result["status"]),
            evidence=list(eval_result.get("evidence", [])),
            notes=str(eval_result.get("notes", "")),
        )

    def _calculate_compliance_score(self, controls: List[AnnexAControl]) -> float:
        """Berechnet den Gesamt-Compliance-Score.

        Args:
            controls: Liste der bewerteten Kontrollen.

        Returns:
            Compliance-Score 0-100.
        """
        if not controls:
            return 0.0

        total_points = 0.0
        max_points = len(controls) * 100.0

        for control in controls:
            if control.status == "erfuellt":
                total_points += 100.0
            elif control.status == "teilweise":
                total_points += 50.0
            # "offen" = 0 points

        return round((total_points / max_points) * 100, 2)

    def _calculate_group_scores(
        self, controls: List[AnnexAControl]
    ) -> Dict[str, float]:
        """Berechnet Compliance-Scores pro Kontrollgruppe.

        Args:
            controls: Liste der bewerteten Kontrollen.

        Returns:
            Dictionary mit Gruppennamen und zugehoerigen Compliance-Scores.
        """
        group_scores: Dict[str, float] = {}

        for group_name in self.ANNEX_A_CONTROLS.keys():
            group_controls = [c for c in controls if c.control_group == group_name]
            if group_controls:
                group_scores[group_name] = self._calculate_compliance_score(
                    group_controls
                )

        return group_scores

    def generate_summary(
        self, controls: List[AnnexAControl], compliance_score: float
    ) -> str:
        """Generiert deutsche Zusammenfassung der Gap-Analyse.

        Args:
            controls: Liste der bewerteten Kontrollen.
            compliance_score: Gesamt-Compliance-Score.

        Returns:
            Deutsche Zusammenfassung als Text.
        """
        erfuellt = sum(1 for c in controls if c.status == "erfuellt")
        teilweise = sum(1 for c in controls if c.status == "teilweise")
        offen = sum(1 for c in controls if c.status == "offen")

        # Dynamische Staerken und Verbesserungsbereiche
        staerken: List[str] = []
        verbesserungen: List[str] = []

        for group_name in self.ANNEX_A_CONTROLS.keys():
            group_controls = [c for c in controls if c.control_group == group_name]
            if not group_controls:
                continue

            all_erfuellt = all(c.status == "erfuellt" for c in group_controls)
            has_offen = any(c.status == "offen" for c in group_controls)

            if all_erfuellt:
                evidence = []
                for c in group_controls:
                    evidence.extend(c.evidence)
                evidence_str = ", ".join(evidence[:3]) if evidence else "Implementiert"
                staerken.append(f"- {group_name}: {evidence_str}")
            elif has_offen:
                offen_notes = [c.notes for c in group_controls if c.status == "offen"]
                note = offen_notes[0] if offen_notes else "Massnahmen erforderlich"
                verbesserungen.append(f"- {group_name}: {note}")
            else:
                teilweise_notes = [c.notes for c in group_controls if c.status == "teilweise"]
                note = teilweise_notes[0] if teilweise_notes else "Teilweise implementiert"
                verbesserungen.append(f"- {group_name}: {note}")

        staerken_text = (
            "\n".join(staerken) if staerken
            else "- Keine Kontrollgruppen vollstaendig erfuellt"
        )
        verbesserungen_text = (
            "\n".join(verbesserungen) if verbesserungen
            else "- Keine Verbesserungsbereiche identifiziert"
        )

        summary = f"""ISO 27001 Gap Analysis - Zusammenfassung

Gesamtbewertung: {compliance_score:.1f}% konform

Kontrollen-Status:
- Erfuellt: {erfuellt} ({erfuellt/len(controls)*100:.1f}%)
- Teilweise erfuellt: {teilweise} ({teilweise/len(controls)*100:.1f}%)
- Offen: {offen} ({offen/len(controls)*100:.1f}%)

Staerken:
{staerken_text}

Verbesserungsbereiche:
{verbesserungen_text}
"""
        return summary


# Singleton instance
_gap_analysis_service: Optional[ISO27001GapAnalysis] = None


def get_gap_analysis_service() -> ISO27001GapAnalysis:
    """Gibt die Singleton Gap-Analyse-Service-Instanz zurueck.

    Returns:
        ISO27001GapAnalysis-Instanz.
    """
    global _gap_analysis_service
    if _gap_analysis_service is None:
        _gap_analysis_service = ISO27001GapAnalysis()
    return _gap_analysis_service
