# -*- coding: utf-8 -*-
"""
Data Protection Impact Assessment (DPIA) Service.

Implementierung gemäß Art. 35 DSGVO.

Features:
- DPIA Template Generierung
- Risiko-Kategorisierung (hoch/mittel/niedrig)
- Automatische Empfehlungen basierend auf Risikoprofil
- Audit-Trail für alle DPIA-Änderungen
- PDF Export für Dokumentation

Feinpoliert und durchdacht - DSGVO-konform.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.db.models import (
    DPIA as DPIAModel,
    DPIAProcessingOperation as DPIAProcessingOperationModel,
    DPIADataSubjectGroup as DPIADataSubjectGroupModel,
    DPIARisk as DPIARiskModel,
    DPIAMitigationMeasure as DPIAMitigationMeasureModel,
    DPIAConsultation as DPIAConsultationModel,
    DPIAAuditLog as DPIAAuditLogModel,
    DPIAStatus,
    DPIARiskLevel,
    DPIALegalBasis,
    DPIAMeasureType,
    DPIAImplementationStatus,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums (for Templates and Validation)
# =============================================================================


class RiskLevel(str, Enum):
    """Risiko-Stufen gemäß DSGVO."""
    VERY_HIGH = "very_high"      # Erfordert sofortige Massnahmen
    HIGH = "high"                # Erfordert DPO-Konsultation
    MEDIUM = "medium"            # Erfordert Risikobehandlung
    LOW = "low"                  # Akzeptables Risiko
    MINIMAL = "minimal"          # Vernachlaessigbares Risiko


class ProcessingBasis(str, Enum):
    """Rechtsgrundlage der Verarbeitung (Art. 6 DSGVO)."""
    CONSENT = "consent"                    # 6(1)(a) - Einwilligung
    CONTRACT = "contract"                  # 6(1)(b) - Vertragserfuellung
    LEGAL_OBLIGATION = "legal_obligation"  # 6(1)(c) - Rechtliche Verpflichtung
    VITAL_INTERESTS = "vital_interests"    # 6(1)(d) - Lebenswichtige Interessen
    PUBLIC_INTEREST = "public_interest"    # 6(1)(e) - Öffentliches Interesse
    LEGITIMATE_INTEREST = "legitimate_interest"  # 6(1)(f) - Berechtigtes Interesse


class DataCategory(str, Enum):
    """Kategorien personenbezogener Daten."""
    BASIC_IDENTITY = "basic_identity"      # Name, Adresse, etc.
    CONTACT = "contact"                    # Email, Telefon
    FINANCIAL = "financial"                # Bankdaten, Zahlungen
    EMPLOYMENT = "employment"              # Beschäftigungsdaten
    HEALTH = "health"                      # Gesundheitsdaten (Art. 9)
    BIOMETRIC = "biometric"                # Biometrische Daten (Art. 9)
    GENETIC = "genetic"                    # Genetische Daten (Art. 9)
    POLITICAL = "political"                # Politische Meinungen (Art. 9)
    RELIGIOUS = "religious"                # Religioese Überzeugungen (Art. 9)
    SEXUAL_ORIENTATION = "sexual_orientation"  # Sexuelle Orientierung (Art. 9)
    CRIMINAL = "criminal"                  # Strafrechtliche Verurteilungen (Art. 10)
    LOCATION = "location"                  # Standortdaten
    BEHAVIORAL = "behavioral"              # Verhaltensmuster
    CHILDREN = "children"                  # Kinderdaten


class MitigationMeasureType(str, Enum):
    """Typen von Risikominderungsmassnahmen."""
    TECHNICAL = "technical"                # Technische Massnahmen
    ORGANIZATIONAL = "organizational"      # Organisatorische Massnahmen
    CONTRACTUAL = "contractual"            # Vertragliche Massnahmen
    LEGAL = "legal"                        # Rechtliche Massnahmen


# =============================================================================
# Data Classes (for Templates and API)
# =============================================================================


@dataclass
class DataSubjectGroup:
    """Gruppe von Betroffenen."""
    name: str
    description: str
    estimated_count: Optional[int] = None
    includes_vulnerable: bool = False  # Kinder, Kranke, Beschäftigte
    includes_children: bool = False


@dataclass
class ProcessingOperation:
    """Eine Verarbeitungstätigkeit."""
    name: str
    description: str
    purpose: str
    legal_basis: ProcessingBasis
    data_categories: List[DataCategory]
    retention_period: str  # z.B. "10 Jahre nach Vertragsende"
    automated_decision_making: bool = False
    profiling: bool = False
    data_transfer_outside_eu: bool = False
    transfer_countries: List[str] = field(default_factory=list)


@dataclass
class RiskAssessment:
    """Risikobewertung für ein einzelnes Risiko."""
    risk_id: str
    description: str
    affected_rights: List[str]  # z.B. ["Vertraulichkeit", "Integrität"]
    likelihood: int  # 1-5
    impact: int      # 1-5
    inherent_risk: RiskLevel = RiskLevel.MEDIUM
    residual_risk: RiskLevel = RiskLevel.LOW
    mitigation_measures: List[str] = field(default_factory=list)

    @property
    def risk_score(self) -> int:
        """Berechne Risiko-Score (1-25)."""
        return self.likelihood * self.impact

    def calculate_risk_level(self) -> RiskLevel:
        """Bestimme Risiko-Level basierend auf Score."""
        score = self.risk_score
        if score >= 20:
            return RiskLevel.VERY_HIGH
        elif score >= 15:
            return RiskLevel.HIGH
        elif score >= 10:
            return RiskLevel.MEDIUM
        elif score >= 5:
            return RiskLevel.LOW
        return RiskLevel.MINIMAL


@dataclass
class MitigationMeasure:
    """Eine Risikominderungsmassnahme."""
    measure_id: str
    name: str
    description: str
    measure_type: MitigationMeasureType
    addresses_risks: List[str]  # Risk IDs
    implementation_status: str  # "planned", "in_progress", "implemented"
    responsible_person: str
    deadline: Optional[datetime] = None
    effectiveness: str = ""  # Beschreibung der Wirksamkeit


@dataclass
class DPOConsultation:
    """DPO-Konsultation."""
    dpo_name: str
    consultation_date: datetime
    opinion: str
    recommendations: List[str]
    approval: bool
    conditions: List[str] = field(default_factory=list)


@dataclass
class DPIA:
    """Vollständige Data Protection Impact Assessment."""
    id: UUID
    title: str
    description: str
    version: str
    status: DPIAStatus

    # Verantwortlichkeiten
    controller_name: str
    controller_contact: str
    dpo_name: str
    dpo_contact: str
    assessment_date: datetime
    assessor_name: str

    # Verarbeitungsbeschreibung
    processing_operations: List[ProcessingOperation]
    data_subject_groups: List[DataSubjectGroup]

    # Notwendigkeit und Verhältnismaessigkeit
    necessity_assessment: str
    proportionality_assessment: str

    # Risikobewertung
    risks: List[RiskAssessment]
    overall_risk_level: RiskLevel

    # Massnahmen
    mitigation_measures: List[MitigationMeasure]

    # DPO-Konsultation
    dpo_consultation: Optional[DPOConsultation] = None

    # Aufsichtsbehoerde (bei hohem Restrisiko)
    supervisory_authority_consultation: bool = False
    supervisory_authority_response: str = ""

    # Metadaten
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    company_id: Optional[UUID] = None
    audit_trail: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary für API/Export."""
        return {
            "id": str(self.id),
            "title": self.title,
            "description": self.description,
            "version": self.version,
            "status": self.status.value if isinstance(self.status, DPIAStatus) else self.status,
            "controller_name": self.controller_name,
            "controller_contact": self.controller_contact,
            "dpo_name": self.dpo_name,
            "dpo_contact": self.dpo_contact,
            "assessment_date": self.assessment_date.isoformat(),
            "assessor_name": self.assessor_name,
            "processing_operations": [
                {
                    "name": op.name,
                    "description": op.description,
                    "purpose": op.purpose,
                    "legal_basis": op.legal_basis.value,
                    "data_categories": [dc.value for dc in op.data_categories],
                    "retention_period": op.retention_period,
                    "automated_decision_making": op.automated_decision_making,
                    "profiling": op.profiling,
                    "data_transfer_outside_eu": op.data_transfer_outside_eu,
                    "transfer_countries": op.transfer_countries,
                }
                for op in self.processing_operations
            ],
            "data_subject_groups": [
                {
                    "name": g.name,
                    "description": g.description,
                    "estimated_count": g.estimated_count,
                    "includes_vulnerable": g.includes_vulnerable,
                    "includes_children": g.includes_children,
                }
                for g in self.data_subject_groups
            ],
            "necessity_assessment": self.necessity_assessment,
            "proportionality_assessment": self.proportionality_assessment,
            "risks": [
                {
                    "risk_id": r.risk_id,
                    "description": r.description,
                    "affected_rights": r.affected_rights,
                    "likelihood": r.likelihood,
                    "impact": r.impact,
                    "risk_score": r.risk_score,
                    "inherent_risk": r.inherent_risk.value,
                    "residual_risk": r.residual_risk.value,
                    "mitigation_measures": r.mitigation_measures,
                }
                for r in self.risks
            ],
            "overall_risk_level": self.overall_risk_level.value,
            "mitigation_measures": [
                {
                    "measure_id": m.measure_id,
                    "name": m.name,
                    "description": m.description,
                    "measure_type": m.measure_type.value,
                    "addresses_risks": m.addresses_risks,
                    "implementation_status": m.implementation_status,
                    "responsible_person": m.responsible_person,
                    "deadline": m.deadline.isoformat() if m.deadline else None,
                    "effectiveness": m.effectiveness,
                }
                for m in self.mitigation_measures
            ],
            "dpo_consultation": (
                {
                    "dpo_name": self.dpo_consultation.dpo_name,
                    "consultation_date": self.dpo_consultation.consultation_date.isoformat(),
                    "opinion": self.dpo_consultation.opinion,
                    "recommendations": self.dpo_consultation.recommendations,
                    "approval": self.dpo_consultation.approval,
                    "conditions": self.dpo_consultation.conditions,
                }
                if self.dpo_consultation
                else None
            ),
            "supervisory_authority_consultation": self.supervisory_authority_consultation,
            "supervisory_authority_response": self.supervisory_authority_response,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "company_id": str(self.company_id) if self.company_id else None,
        }


# =============================================================================
# DPIA Templates
# =============================================================================


class DPIATemplates:
    """Vordefinierte DPIA-Templates für häufige Szenarien."""

    @staticmethod
    def ocr_document_processing() -> Dict[str, Any]:
        """Template für OCR-Dokumentenverarbeitung."""
        return {
            "title": "DPIA - OCR-basierte Dokumentenverarbeitung",
            "description": "Datenschutz-Folgenabschätzung für die automatisierte "
                          "Verarbeitung von Geschäftsdokumenten mittels OCR.",
            "processing_operations": [
                {
                    "name": "Dokumentendigitalisierung",
                    "description": "Scannen und OCR-Verarbeitung von Papierdokumenten",
                    "purpose": "Digitalisierung und Archivierung von Geschäftsdokumenten",
                    "legal_basis": ProcessingBasis.LEGITIMATE_INTEREST,
                    "data_categories": [
                        DataCategory.BASIC_IDENTITY,
                        DataCategory.CONTACT,
                        DataCategory.FINANCIAL,
                    ],
                    "retention_period": "10 Jahre gemäß HGB/AO",
                },
                {
                    "name": "Automatische Datenextraktion",
                    "description": "KI-basierte Extraktion strukturierter Daten aus Dokumenten",
                    "purpose": "Automatisierung der Buchhaltung und Dokumentenverwaltung",
                    "legal_basis": ProcessingBasis.LEGITIMATE_INTEREST,
                    "data_categories": [
                        DataCategory.BASIC_IDENTITY,
                        DataCategory.FINANCIAL,
                    ],
                    "retention_period": "10 Jahre gemäß HGB/AO",
                    "automated_decision_making": True,
                },
            ],
            "data_subject_groups": [
                {
                    "name": "Geschäftskunden",
                    "description": "Ansprechpartner bei Geschäftskunden",
                    "includes_vulnerable": False,
                },
                {
                    "name": "Lieferanten",
                    "description": "Kontaktpersonen bei Lieferanten",
                    "includes_vulnerable": False,
                },
                {
                    "name": "Beschäftigte",
                    "description": "Mitarbeiter deren Namen auf Dokumenten erscheinen",
                    "includes_vulnerable": True,  # Beschäftigte = schutzbedürftiger
                },
            ],
            "standard_risks": [
                {
                    "risk_id": "R1",
                    "description": "Unbefugter Zugriff auf sensible Geschäftsdokumente",
                    "affected_rights": ["Vertraulichkeit"],
                    "likelihood": 2,
                    "impact": 4,
                },
                {
                    "risk_id": "R2",
                    "description": "Fehlerhafte OCR-Erkennung führt zu falschen Daten",
                    "affected_rights": ["Richtigkeit"],
                    "likelihood": 3,
                    "impact": 3,
                },
                {
                    "risk_id": "R3",
                    "description": "Datenverlust durch Systemausfall",
                    "affected_rights": ["Verfügbarkeit"],
                    "likelihood": 2,
                    "impact": 3,
                },
            ],
            "standard_measures": [
                {
                    "measure_id": "M1",
                    "name": "Zugriffskontrolle",
                    "description": "Rollenbasierte Zugriffskontrolle (RBAC) mit MFA",
                    "measure_type": MitigationMeasureType.TECHNICAL,
                    "addresses_risks": ["R1"],
                },
                {
                    "measure_id": "M2",
                    "name": "Manuelle Verifizierung",
                    "description": "Vier-Augen-Prinzip bei kritischen Dokumenten",
                    "measure_type": MitigationMeasureType.ORGANIZATIONAL,
                    "addresses_risks": ["R2"],
                },
                {
                    "measure_id": "M3",
                    "name": "Backup-Strategie",
                    "description": "Täglich inkrementelle, woechentlich volle Backups",
                    "measure_type": MitigationMeasureType.TECHNICAL,
                    "addresses_risks": ["R3"],
                },
            ],
        }

    @staticmethod
    def lexware_customer_import() -> Dict[str, Any]:
        """Template für Lexware-Kundenimport."""
        return {
            "title": "DPIA - Import von Kundendaten aus Lexware",
            "description": "Datenschutz-Folgenabschätzung für den Import von "
                          "Kunden- und Lieferantendaten aus Lexware-Systemen.",
            "processing_operations": [
                {
                    "name": "Datenimport aus Lexware",
                    "description": "Import von Kunden- und Lieferantenstammdaten",
                    "purpose": "Synchronisation der Stammdaten für Dokumentenzuordnung",
                    "legal_basis": ProcessingBasis.LEGITIMATE_INTEREST,
                    "data_categories": [
                        DataCategory.BASIC_IDENTITY,
                        DataCategory.CONTACT,
                        DataCategory.FINANCIAL,
                    ],
                    "retention_period": "Solange Geschäftsbeziehung besteht, dann 10 Jahre",
                },
            ],
            "data_subject_groups": [
                {
                    "name": "Kunden",
                    "description": "Natürliche Personen als Kunden",
                    "includes_vulnerable": False,
                },
                {
                    "name": "Ansprechpartner",
                    "description": "Kontaktpersonen bei Geschäftskunden",
                    "includes_vulnerable": False,
                },
            ],
            "standard_risks": [
                {
                    "risk_id": "R1",
                    "description": "Fehlerhafte Zuordnung von Dokumenten zu Personen",
                    "affected_rights": ["Richtigkeit"],
                    "likelihood": 2,
                    "impact": 2,
                },
                {
                    "risk_id": "R2",
                    "description": "Veraltete Daten nach Löschung in Quellsystem",
                    "affected_rights": ["Löschung"],
                    "likelihood": 3,
                    "impact": 2,
                },
            ],
            "standard_measures": [
                {
                    "measure_id": "M1",
                    "name": "Regelmäßiger Datenabgleich",
                    "description": "Woechentlicher Sync mit Quellsystem inkl. Löschprüfung",
                    "measure_type": MitigationMeasureType.TECHNICAL,
                    "addresses_risks": ["R1", "R2"],
                },
            ],
        }

    @staticmethod
    def email_import() -> Dict[str, Any]:
        """Template für Email-Import."""
        return {
            "title": "DPIA - Automatischer Email-Import",
            "description": "Datenschutz-Folgenabschätzung für den automatischen "
                          "Import von Dokumenten aus Emails.",
            "processing_operations": [
                {
                    "name": "Email-Abruf via IMAP",
                    "description": "Automatischer Abruf von Emails mit Dokumenten-Anhaengen",
                    "purpose": "Automatisierung des Dokumenteneingangs",
                    "legal_basis": ProcessingBasis.LEGITIMATE_INTEREST,
                    "data_categories": [
                        DataCategory.BASIC_IDENTITY,
                        DataCategory.CONTACT,
                    ],
                    "retention_period": "Emails werden nach Import nicht gespeichert",
                },
            ],
            "data_subject_groups": [
                {
                    "name": "Email-Absender",
                    "description": "Externe Personen die Dokumente per Email senden",
                    "includes_vulnerable": False,
                },
            ],
            "standard_risks": [
                {
                    "risk_id": "R1",
                    "description": "Verarbeitung unerwünschter Emails (Spam/Phishing)",
                    "affected_rights": ["Sicherheit"],
                    "likelihood": 3,
                    "impact": 3,
                },
                {
                    "risk_id": "R2",
                    "description": "Zugriff auf Email-Zugangsdaten",
                    "affected_rights": ["Vertraulichkeit"],
                    "likelihood": 2,
                    "impact": 4,
                },
            ],
            "standard_measures": [
                {
                    "measure_id": "M1",
                    "name": "Email-Filter",
                    "description": "Absender-Whitelist und Spam-Filterung",
                    "measure_type": MitigationMeasureType.TECHNICAL,
                    "addresses_risks": ["R1"],
                },
                {
                    "measure_id": "M2",
                    "name": "Verschlüsselte Speicherung",
                    "description": "Email-Passwoerter AES-256-GCM verschlüsselt",
                    "measure_type": MitigationMeasureType.TECHNICAL,
                    "addresses_risks": ["R2"],
                },
            ],
        }


# =============================================================================
# DPIA Service
# =============================================================================


class DPIAService:
    """
    Service für Data Protection Impact Assessments (DPIA).

    Gemäß Art. 35 DSGVO erforderlich bei:
    - Systematischer Überwachung
    - Verarbeitung besonderer Kategorien (Art. 9)
    - Automatisierter Entscheidungsfindung mit rechtlicher Wirkung
    - Neuen Technologien
    - Grossflaechiger Verarbeitung
    """

    # Kriterien die DPIA erfordern (Art. 35 Abs. 3)
    DPIA_TRIGGERS = {
        "automated_decisions": "Automatisierte Entscheidungsfindung mit rechtlicher Wirkung",
        "special_categories": "Verarbeitung besonderer Kategorien personenbezogener Daten",
        "criminal_data": "Verarbeitung von Daten über Straftaten",
        "large_scale": "Grossflaechige Verarbeitung personenbezogener Daten",
        "systematic_monitoring": "Systematische Überwachung öffentlicher Bereiche",
        "vulnerable_groups": "Verarbeitung von Daten schutzbedürftiger Personen",
        "new_technology": "Einsatz neuer Technologien",
        "cross_matching": "Abgleich oder Zusammenführung von Datensätzen",
        "prevents_rights": "Verarbeitung verhindert Ausuebung von Rechten",
    }

    # Besondere Datenkategorien (Art. 9)
    SPECIAL_CATEGORIES = {
        DataCategory.HEALTH,
        DataCategory.BIOMETRIC,
        DataCategory.GENETIC,
        DataCategory.POLITICAL,
        DataCategory.RELIGIOUS,
        DataCategory.SEXUAL_ORIENTATION,
    }

    def __init__(self) -> None:
        """Initialisiere DPIA Service."""
        self._templates = DPIATemplates()
        logger.info("DPIAService initialisiert")

    def needs_dpia(
        self,
        processing_operations: List[ProcessingOperation],
        data_subject_groups: List[DataSubjectGroup],
    ) -> Dict[str, Any]:
        """
        Prüfe ob eine DPIA erforderlich ist.

        Args:
            processing_operations: Geplante Verarbeitungstätigkeiten
            data_subject_groups: Betroffene Personengruppen

        Returns:
            Dict mit "required": bool und "reasons": List[str]
        """
        reasons = []

        for op in processing_operations:
            # Automatisierte Entscheidungen
            if op.automated_decision_making:
                reasons.append(self.DPIA_TRIGGERS["automated_decisions"])

            # Profiling
            if op.profiling:
                reasons.append("Profiling wird durchgeführt")

            # Besondere Kategorien
            special = set(op.data_categories) & self.SPECIAL_CATEGORIES
            if special:
                reasons.append(
                    f"{self.DPIA_TRIGGERS['special_categories']}: "
                    f"{', '.join(c.value for c in special)}"
                )

            # Strafrechtliche Daten
            if DataCategory.CRIMINAL in op.data_categories:
                reasons.append(self.DPIA_TRIGGERS["criminal_data"])

            # Datentransfer ausserhalb EU
            if op.data_transfer_outside_eu:
                reasons.append(
                    f"Datentransfer in Drittländer: {', '.join(op.transfer_countries)}"
                )

        # Schutzbeduertige Gruppen
        for group in data_subject_groups:
            if group.includes_vulnerable or group.includes_children:
                reasons.append(self.DPIA_TRIGGERS["vulnerable_groups"])
                break

        return {
            "required": len(reasons) >= 2,  # Mindestens 2 Kriterien
            "reasons": list(set(reasons)),
            "criteria_met": len(reasons),
        }

    async def create_from_template(
        self,
        db: AsyncSession,
        template_name: str,
        controller_name: str,
        controller_contact: str,
        dpo_name: str,
        dpo_contact: str,
        assessor_name: str,
        company_id: UUID,
        created_by_id: Optional[UUID] = None,
    ) -> DPIA:
        """
        Erstelle DPIA aus Template.

        Args:
            db: Database session
            template_name: Name des Templates (ocr_document_processing, etc.)
            controller_name: Name des Verantwortlichen
            controller_contact: Kontakt des Verantwortlichen
            dpo_name: Name des DSB
            dpo_contact: Kontakt des DSB
            assessor_name: Name des Durchführenden
            company_id: Company-ID
            created_by_id: Optional User-ID des Erstellers

        Returns:
            Neue DPIA Instanz
        """
        # Template laden
        template_method = getattr(self._templates, template_name, None)
        if not template_method:
            raise ValueError(f"Unbekanntes Template: {template_name}")

        template = template_method()

        # Processing Operations erstellen
        operations = []
        for op_data in template.get("processing_operations", []):
            operations.append(ProcessingOperation(
                name=op_data["name"],
                description=op_data["description"],
                purpose=op_data["purpose"],
                legal_basis=op_data["legal_basis"],
                data_categories=op_data["data_categories"],
                retention_period=op_data["retention_period"],
                automated_decision_making=op_data.get("automated_decision_making", False),
                profiling=op_data.get("profiling", False),
                data_transfer_outside_eu=op_data.get("data_transfer_outside_eu", False),
                transfer_countries=op_data.get("transfer_countries", []),
            ))

        # Data Subject Groups erstellen
        groups = []
        for group_data in template.get("data_subject_groups", []):
            groups.append(DataSubjectGroup(
                name=group_data["name"],
                description=group_data["description"],
                estimated_count=group_data.get("estimated_count"),
                includes_vulnerable=group_data.get("includes_vulnerable", False),
                includes_children=group_data.get("includes_children", False),
            ))

        # Risiken erstellen
        risks = []
        for risk_data in template.get("standard_risks", []):
            risk = RiskAssessment(
                risk_id=risk_data["risk_id"],
                description=risk_data["description"],
                affected_rights=risk_data["affected_rights"],
                likelihood=risk_data["likelihood"],
                impact=risk_data["impact"],
            )
            risk.inherent_risk = risk.calculate_risk_level()
            risks.append(risk)

        # Massnahmen erstellen
        measures = []
        for measure_data in template.get("standard_measures", []):
            measures.append(MitigationMeasure(
                measure_id=measure_data["measure_id"],
                name=measure_data["name"],
                description=measure_data["description"],
                measure_type=measure_data["measure_type"],
                addresses_risks=measure_data["addresses_risks"],
                implementation_status="planned",
                responsible_person=assessor_name,
            ))

        # Gesamt-Risiko berechnen
        if risks:
            max_risk_score = max(r.risk_score for r in risks)
            if max_risk_score >= 20:
                overall_risk = RiskLevel.VERY_HIGH
            elif max_risk_score >= 15:
                overall_risk = RiskLevel.HIGH
            elif max_risk_score >= 10:
                overall_risk = RiskLevel.MEDIUM
            elif max_risk_score >= 5:
                overall_risk = RiskLevel.LOW
            else:
                overall_risk = RiskLevel.MINIMAL
        else:
            overall_risk = RiskLevel.LOW

        # DB-Model erstellen
        dpia_model = DPIAModel(
            id=uuid4(),
            title=template["title"],
            description=template["description"],
            version="1.0",
            status=DPIAStatus.DRAFT.value,
            controller_name=controller_name,
            controller_contact=controller_contact,
            dpo_name=dpo_name,
            dpo_contact=dpo_contact,
            assessment_date=datetime.utcnow(),
            assessor_name=assessor_name,
            necessity_assessment="",
            proportionality_assessment="",
            overall_risk_level=overall_risk.value,
            company_id=company_id,
            created_by_id=created_by_id,
        )

        # Processing Operations speichern
        for op in operations:
            op_model = DPIAProcessingOperationModel(
                dpia_id=dpia_model.id,
                name=op.name,
                description=op.description,
                purpose=op.purpose,
                legal_basis=op.legal_basis.value,
                data_categories=[dc.value for dc in op.data_categories],
                retention_period=op.retention_period,
                automated_decision_making=op.automated_decision_making,
                profiling=op.profiling,
                data_transfer_outside_eu=op.data_transfer_outside_eu,
                transfer_countries=op.transfer_countries,
            )
            dpia_model.processing_operations.append(op_model)

        # Data Subject Groups speichern
        for group in groups:
            group_model = DPIADataSubjectGroupModel(
                dpia_id=dpia_model.id,
                name=group.name,
                description=group.description,
                estimated_count=group.estimated_count,
                includes_vulnerable=group.includes_vulnerable,
                includes_children=group.includes_children,
            )
            dpia_model.data_subject_groups.append(group_model)

        # Risiken speichern
        for risk in risks:
            risk_model = DPIARiskModel(
                dpia_id=dpia_model.id,
                risk_id=risk.risk_id,
                description=risk.description,
                affected_rights=risk.affected_rights,
                likelihood=risk.likelihood,
                impact=risk.impact,
                inherent_risk=risk.inherent_risk.value,
                residual_risk=risk.residual_risk.value,
                mitigation_measures=risk.mitigation_measures,
            )
            dpia_model.risks.append(risk_model)

        # Massnahmen speichern
        for measure in measures:
            measure_model = DPIAMitigationMeasureModel(
                dpia_id=dpia_model.id,
                measure_id=measure.measure_id,
                name=measure.name,
                description=measure.description,
                measure_type=measure.measure_type.value,
                addresses_risks=measure.addresses_risks,
                implementation_status=measure.implementation_status,
                responsible_person=measure.responsible_person,
                deadline=measure.deadline,
                effectiveness=measure.effectiveness,
            )
            dpia_model.mitigation_measures.append(measure_model)

        # In DB speichern
        db.add(dpia_model)
        await db.flush()

        # Audit Trail
        await self._add_audit_entry(
            db,
            dpia_model,
            "CREATED",
            assessor_name,
            f"DPIA erstellt aus Template: {template_name}"
        )

        await db.commit()
        await db.refresh(dpia_model)

        logger.info(
            "dpia_created",
            dpia_id=str(dpia_model.id),
            title=dpia_model.title,
            template=template_name,
            overall_risk=overall_risk.value,
        )

        # Konvertiere zu Dataclass
        return await self._model_to_dataclass(dpia_model)

    async def get_by_id(
        self,
        db: AsyncSession,
        dpia_id: UUID,
        company_id: Optional[UUID] = None,
    ) -> Optional[DPIA]:
        """Hole DPIA nach ID.

        Multi-Tenant: Wenn company_id uebergeben wird, MUSS die DPIA zu
        dieser Company gehoeren. NULL-company_id auf der Row laesst keinen
        Zugriff durch (defense-in-depth gegen Legacy-Rows ohne Tenant).
        """
        conditions = [DPIAModel.id == dpia_id]
        if company_id is not None:
            conditions.append(DPIAModel.company_id == company_id)

        stmt = (
            select(DPIAModel)
            .options(
                selectinload(DPIAModel.processing_operations),
                selectinload(DPIAModel.data_subject_groups),
                selectinload(DPIAModel.risks),
                selectinload(DPIAModel.mitigation_measures),
                selectinload(DPIAModel.consultation),
                selectinload(DPIAModel.audit_logs),
            )
            .where(and_(*conditions))
        )
        result = await db.execute(stmt)
        dpia_model = result.scalar_one_or_none()

        if not dpia_model:
            return None

        return await self._model_to_dataclass(dpia_model)

    async def list_dpias(
        self,
        db: AsyncSession,
        company_id: Optional[UUID] = None,
        status: Optional[DPIAStatus] = None,
    ) -> List[DPIA]:
        """Liste DPIAs mit Filterung."""
        stmt = (
            select(DPIAModel)
            .options(
                selectinload(DPIAModel.processing_operations),
                selectinload(DPIAModel.data_subject_groups),
                selectinload(DPIAModel.risks),
                selectinload(DPIAModel.mitigation_measures),
                selectinload(DPIAModel.consultation),
                selectinload(DPIAModel.audit_logs),
            )
        )

        conditions = []
        if company_id:
            conditions.append(DPIAModel.company_id == company_id)
        if status:
            conditions.append(DPIAModel.status == status.value)

        if conditions:
            stmt = stmt.where(and_(*conditions))

        result = await db.execute(stmt)
        dpia_models = result.scalars().all()

        return [await self._model_to_dataclass(model) for model in dpia_models]

    async def update_status(
        self,
        db: AsyncSession,
        dpia_id: UUID,
        new_status: DPIAStatus,
        user_name: str,
        comment: str = "",
        company_id: Optional[UUID] = None,
    ) -> DPIA:
        """
        Aktualisiere DPIA Status.

        Multi-Tenant: Wenn company_id uebergeben wird, MUSS die DPIA zu
        dieser Company gehoeren. Cross-Tenant-Zugriff = ValueError (404).
        """
        conditions = [DPIAModel.id == dpia_id]
        if company_id is not None:
            conditions.append(DPIAModel.company_id == company_id)
        stmt = select(DPIAModel).where(and_(*conditions))
        result = await db.execute(stmt)
        dpia_model = result.scalar_one_or_none()

        if not dpia_model:
            raise ValueError(f"DPIA nicht gefunden: {dpia_id}")

        old_status = dpia_model.status
        dpia_model.status = new_status.value
        dpia_model.updated_at = datetime.utcnow()

        await self._add_audit_entry(
            db,
            dpia_model,
            "STATUS_CHANGE",
            user_name,
            f"Status geändert von {old_status} zu {new_status.value}. {comment}".strip()
        )

        await db.commit()
        await db.refresh(dpia_model)

        logger.info(
            "dpia_status_updated",
            dpia_id=str(dpia_id),
            old_status=old_status,
            new_status=new_status.value,
        )

        return await self._model_to_dataclass(dpia_model)

    async def add_dpo_consultation(
        self,
        db: AsyncSession,
        dpia_id: UUID,
        dpo_name: str,
        opinion: str,
        recommendations: List[str],
        approval: bool,
        conditions: List[str] = None,
        company_id: Optional[UUID] = None,
    ) -> DPIA:
        """
        Fuege DPO-Konsultation hinzu.

        Multi-Tenant: Wenn company_id uebergeben wird, MUSS die DPIA zu
        dieser Company gehoeren. Cross-Tenant-Zugriff = ValueError (404).
        """
        where_conditions = [DPIAModel.id == dpia_id]
        if company_id is not None:
            where_conditions.append(DPIAModel.company_id == company_id)
        stmt = select(DPIAModel).where(and_(*where_conditions))
        result = await db.execute(stmt)
        dpia_model = result.scalar_one_or_none()

        if not dpia_model:
            raise ValueError(f"DPIA nicht gefunden: {dpia_id}")

        # Bestehende Konsultation löschen falls vorhanden
        if dpia_model.consultation:
            await db.delete(dpia_model.consultation)

        # Neue Konsultation erstellen
        consultation = DPIAConsultationModel(
            dpia_id=dpia_id,
            dpo_name=dpo_name,
            consultation_date=datetime.utcnow(),
            opinion=opinion,
            recommendations=recommendations,
            approval=approval,
            conditions=conditions or [],
        )
        db.add(consultation)

        dpia_model.updated_at = datetime.utcnow()

        if approval:
            dpia_model.status = DPIAStatus.APPROVED.value
        else:
            dpia_model.status = DPIAStatus.REJECTED.value

        await self._add_audit_entry(
            db,
            dpia_model,
            "DPO_CONSULTATION",
            dpo_name,
            f"DPO-Konsultation: {'Genehmigt' if approval else 'Abgelehnt'}",
        )

        await db.commit()
        await db.refresh(dpia_model)

        logger.info(
            "dpia_dpo_consultation_added",
            dpia_id=str(dpia_id),
            approval=approval,
        )

        return await self._model_to_dataclass(dpia_model)

    def get_recommendations(self, dpia: DPIA) -> List[Dict[str, Any]]:
        """
        Generiere Empfehlungen basierend auf Risikoprofil.

        Args:
            dpia: DPIA Instanz

        Returns:
            Liste von Empfehlungen
        """
        recommendations = []

        # Hohes Restrisiko -> DPO-Konsultation
        if dpia.overall_risk_level in (RiskLevel.HIGH, RiskLevel.VERY_HIGH):
            recommendations.append({
                "priority": "high",
                "category": "consultation",
                "title": "DPO-Konsultation erforderlich",
                "description": (
                    "Bei hohem Risiko ist gemäß Art. 35 Abs. 2 DSGVO "
                    "die Konsultation des Datenschutzbeauftragten erforderlich."
                ),
                "action": "DPO zur Stellungnahme einladen",
            })

        # Sehr hohes Restrisiko -> Aufsichtsbehoerde
        if dpia.overall_risk_level == RiskLevel.VERY_HIGH:
            recommendations.append({
                "priority": "critical",
                "category": "regulatory",
                "title": "Konsultation der Aufsichtsbehoerde prüfen",
                "description": (
                    "Gemäß Art. 36 DSGVO ist bei sehr hohem Restrisiko "
                    "die Aufsichtsbehoerde vor Verarbeitungsbeginn zu konsultieren."
                ),
                "action": "Kontakt mit zuständiger Aufsichtsbehoerde aufnehmen",
            })

        # Besondere Datenkategorien
        has_special = False
        for op in dpia.processing_operations:
            if set(op.data_categories) & self.SPECIAL_CATEGORIES:
                has_special = True
                break

        if has_special:
            recommendations.append({
                "priority": "high",
                "category": "legal",
                "title": "Rechtsgrundlage für Art. 9 Daten dokumentieren",
                "description": (
                    "Die Verarbeitung besonderer Kategorien erfordert "
                    "eine zusätzliche Rechtsgrundlage nach Art. 9 Abs. 2 DSGVO."
                ),
                "action": "Rechtliche Prüfung der Verarbeitungsgrundlage",
            })

        # Datentransfer Drittland
        for op in dpia.processing_operations:
            if op.data_transfer_outside_eu:
                recommendations.append({
                    "priority": "medium",
                    "category": "legal",
                    "title": "Garantien für Drittlandtransfer dokumentieren",
                    "description": (
                        f"Der Transfer nach {', '.join(op.transfer_countries)} "
                        "erfordert geeignete Garantien (z.B. SCC, BCR, Angemessenheitsbeschluss)."
                    ),
                    "action": "Transfermechanismus dokumentieren",
                })
                break

        # Automatisierte Entscheidungen
        for op in dpia.processing_operations:
            if op.automated_decision_making:
                recommendations.append({
                    "priority": "medium",
                    "category": "rights",
                    "title": "Information über automatisierte Entscheidungen",
                    "description": (
                        "Betroffene müssen gemäß Art. 13/14 DSGVO "
                        "über automatisierte Entscheidungsfindung informiert werden."
                    ),
                    "action": "Datenschutzerklärung aktualisieren",
                })
                break

        # Unimplementierte Massnahmen
        pending_measures = [
            m for m in dpia.mitigation_measures
            if m.implementation_status in ("planned", "in_progress")
        ]
        if pending_measures:
            recommendations.append({
                "priority": "medium",
                "category": "measures",
                "title": f"{len(pending_measures)} Massnahmen noch nicht implementiert",
                "description": (
                    "Vor Verarbeitungsbeginn sollten alle Risikominderungsmassnahmen "
                    "implementiert sein."
                ),
                "action": "Implementierungsplan erstellen",
            })

        return recommendations

    async def _add_audit_entry(
        self,
        db: AsyncSession,
        dpia_model: DPIAModel,
        action: str,
        user_name: str,
        details: str,
    ) -> None:
        """Fuege Audit-Trail Eintrag hinzu."""
        audit_log = DPIAAuditLogModel(
            dpia_id=dpia_model.id,
            action=action,
            user_name=user_name,
            details=details,
        )
        db.add(audit_log)

    async def _model_to_dataclass(self, model: DPIAModel) -> DPIA:
        """Konvertiere DB-Model zu Dataclass."""
        # Processing Operations
        operations = []
        for op in model.processing_operations:
            operations.append(ProcessingOperation(
                name=op.name,
                description=op.description or "",
                purpose=op.purpose or "",
                legal_basis=ProcessingBasis(op.legal_basis),
                data_categories=[DataCategory(dc) for dc in op.data_categories],
                retention_period=op.retention_period or "",
                automated_decision_making=op.automated_decision_making,
                profiling=op.profiling,
                data_transfer_outside_eu=op.data_transfer_outside_eu,
                transfer_countries=op.transfer_countries or [],
            ))

        # Data Subject Groups
        groups = []
        for group in model.data_subject_groups:
            groups.append(DataSubjectGroup(
                name=group.name,
                description=group.description or "",
                estimated_count=group.estimated_count,
                includes_vulnerable=group.includes_vulnerable,
                includes_children=group.includes_children,
            ))

        # Risks
        risks = []
        for risk in model.risks:
            risks.append(RiskAssessment(
                risk_id=risk.risk_id,
                description=risk.description,
                affected_rights=risk.affected_rights or [],
                likelihood=risk.likelihood,
                impact=risk.impact,
                inherent_risk=RiskLevel(risk.inherent_risk) if risk.inherent_risk else RiskLevel.MEDIUM,
                residual_risk=RiskLevel(risk.residual_risk) if risk.residual_risk else RiskLevel.LOW,
                mitigation_measures=risk.mitigation_measures or [],
            ))

        # Mitigation Measures
        measures = []
        for measure in model.mitigation_measures:
            measures.append(MitigationMeasure(
                measure_id=measure.measure_id,
                name=measure.name,
                description=measure.description or "",
                measure_type=MitigationMeasureType(measure.measure_type),
                addresses_risks=measure.addresses_risks or [],
                implementation_status=measure.implementation_status,
                responsible_person=measure.responsible_person or "",
                deadline=measure.deadline,
                effectiveness=measure.effectiveness or "",
            ))

        # DPO Consultation
        dpo_consultation = None
        if model.consultation:
            dpo_consultation = DPOConsultation(
                dpo_name=model.consultation.dpo_name,
                consultation_date=model.consultation.consultation_date,
                opinion=model.consultation.opinion or "",
                recommendations=model.consultation.recommendations or [],
                approval=model.consultation.approval,
                conditions=model.consultation.conditions or [],
            )

        # Audit Trail
        audit_trail = []
        for log in model.audit_logs:
            audit_trail.append({
                "timestamp": log.created_at.isoformat(),
                "action": log.action,
                "user": log.user_name or "",
                "details": log.details or "",
            })

        return DPIA(
            id=model.id,
            title=model.title,
            description=model.description or "",
            version=model.version,
            status=DPIAStatus(model.status),
            controller_name=model.controller_name,
            controller_contact=model.controller_contact or "",
            dpo_name=model.dpo_name,
            dpo_contact=model.dpo_contact or "",
            assessment_date=model.assessment_date or datetime.utcnow(),
            assessor_name=model.assessor_name or "",
            processing_operations=operations,
            data_subject_groups=groups,
            necessity_assessment=model.necessity_assessment or "",
            proportionality_assessment=model.proportionality_assessment or "",
            risks=risks,
            overall_risk_level=RiskLevel(model.overall_risk_level),
            mitigation_measures=measures,
            dpo_consultation=dpo_consultation,
            supervisory_authority_consultation=model.supervisory_authority_consultation,
            supervisory_authority_response=model.supervisory_authority_response or "",
            created_at=model.created_at,
            updated_at=model.updated_at,
            company_id=model.company_id,
            audit_trail=audit_trail,
        )

    def get_available_templates(self) -> List[Dict[str, str]]:
        """Liste verfügbarer Templates."""
        return [
            {
                "name": "ocr_document_processing",
                "title": "OCR-basierte Dokumentenverarbeitung",
                "description": "Template für automatisierte Dokumentenverarbeitung mit OCR",
            },
            {
                "name": "lexware_customer_import",
                "title": "Import von Kundendaten aus Lexware",
                "description": "Template für Synchronisation von Stammdaten",
            },
            {
                "name": "email_import",
                "title": "Automatischer Email-Import",
                "description": "Template für automatischen Dokumenteneingang per Email",
            },
        ]


# =============================================================================
# Singleton
# =============================================================================


_dpia_service: Optional[DPIAService] = None


def get_dpia_service() -> DPIAService:
    """Hole globale DPIAService-Instanz."""
    global _dpia_service
    if _dpia_service is None:
        _dpia_service = DPIAService()
    return _dpia_service
