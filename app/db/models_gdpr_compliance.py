"""GDPR, DPIA und Compliance-Modelle - extrahiert aus models.py (Modularisierung Phase 1.1)."""
import uuid
from datetime import datetime
from enum import Enum
from sqlalchemy import Column, String, Integer, BigInteger, Boolean, DateTime, Date, Text, Float, ForeignKey, Index, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.models_base import Base, CrossDBJSON


# ==================== GDPR Models (lines ~1082-1286) ====================

class GDPRDeletionRequestStatus(str, Enum):
    """Status für GDPR Löschanfragen (Art. 17 DSGVO)."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class GDPRDeletionRequest(Base):
    """
    GDPR Löschanfrage (Art. 17 DSGVO - Recht auf Löschung).

    Verfolgt Löschanfragen von Benutzern und deren Bearbeitungsstatus.
    Anfragen müssen innerhalb von 30 Tagen bearbeitet werden.
    """
    __tablename__ = "gdpr_deletion_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Request details
    status = Column(String(50), default=GDPRDeletionRequestStatus.PENDING, nullable=False)
    reason = Column(Text, nullable=True)  # Optionaler Grund des Benutzers
    deletion_deadline = Column(DateTime(timezone=True), nullable=False)  # 30 Tage Frist

    # Timestamps
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Audit
    processed_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    deletion_reason = Column(String(255), nullable=True)  # Warum abgelehnt (falls rejected)

    # Statistics
    documents_deleted = Column(Integer, default=0)
    audit_entries_anonymized = Column(Integer, default=0)

    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="gdpr_deletion_requests")
    processed_by = relationship("User", foreign_keys=[processed_by_id])

    # Indexes
    __table_args__ = (
        Index("ix_gdpr_deletion_requests_user_id", "user_id"),
        Index("ix_gdpr_deletion_requests_status", "status"),
        Index("ix_gdpr_deletion_requests_deadline", "deletion_deadline"),
    )


class GDPRBreachLog(Base):
    """
    GDPR Datenschutzvorfall-Log (Art. 33/34 DSGVO).

    Dokumentiert Datenschutzvorfälle und deren Meldung:
    - Art. 33: Meldung an Aufsichtsbehörde (72 Stunden)
    - Art. 34: Meldung an betroffene Personen (bei hohem Risiko)
    """
    __tablename__ = "gdpr_breach_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    breach_id = Column(String(32), unique=True, nullable=False)  # Eindeutige Breach-ID

    # Breach details
    breach_type = Column(String(100), nullable=False)  # unauthorized_access, data_loss, etc.
    affected_records = Column(Integer, default=0)
    description = Column(Text, nullable=False)
    severity = Column(String(20), default="medium")  # low, medium, high, critical

    # Detection & Timeline
    detected_at = Column(DateTime(timezone=True), server_default=func.now())
    notification_deadline = Column(DateTime(timezone=True), nullable=False)  # 72 Stunden

    # Notification status
    authority_notified = Column(Boolean, default=False)
    authority_notification_date = Column(DateTime(timezone=True), nullable=True)
    users_notified = Column(Integer, default=0)
    user_notification_date = Column(DateTime(timezone=True), nullable=True)

    # Response
    containment_measures = Column(Text, nullable=True)
    remediation_status = Column(String(50), default="investigating")  # investigating, contained, resolved
    resolution_date = Column(DateTime(timezone=True), nullable=True)

    # Audit
    reported_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    reported_by = relationship("User", backref="reported_breaches")

    # Indexes
    __table_args__ = (
        Index("ix_gdpr_breach_logs_breach_id", "breach_id"),
        Index("ix_gdpr_breach_logs_detected_at", "detected_at"),
        Index("ix_gdpr_breach_logs_severity", "severity"),
        Index("ix_gdpr_breach_logs_remediation_status", "remediation_status"),
    )


class GDPRConsentLog(Base):
    """
    GDPR Einwilligungsprotokoll (Art. 7 DSGVO).

    Dokumentiert Einwilligungen der Benutzer für verschiedene Zwecke.
    """
    __tablename__ = "gdpr_consent_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Consent details
    consent_type = Column(String(100), nullable=False)  # data_processing, marketing, analytics
    purpose = Column(String(255), nullable=False)  # Zweck der Einwilligung
    consent_given = Column(Boolean, nullable=False)
    consent_text = Column(Text, nullable=True)  # Text der Einwilligung zum Zeitpunkt

    # Timestamps
    consent_date = Column(DateTime(timezone=True), server_default=func.now())
    withdrawal_date = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)  # Einwilligung läuft ab

    # Source
    source = Column(String(50), default="web")  # web, api, admin
    ip_address = Column(String(45), nullable=True)  # IPv4/IPv6

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", backref="gdpr_consent_logs")

    # Indexes
    __table_args__ = (
        Index("ix_gdpr_consent_logs_user_id", "user_id"),
        Index("ix_gdpr_consent_logs_consent_type", "consent_type"),
        Index("ix_gdpr_consent_logs_consent_date", "consent_date"),
    )


class GDPRProcessingActivity(Base):
    """
    GDPR Verarbeitungsverzeichnis (Art. 30 DSGVO).

    Dokumentiert alle Verarbeitungstätigkeiten gemäß Rechenschaftspflicht.
    Ersetzt die In-Memory-Speicherung in GDPRComplianceManager.

    SECURITY: Dieses Verzeichnis muss bei Audits vorgelegt werden können.
    """
    __tablename__ = "gdpr_processing_activities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    activity_id = Column(String(32), unique=True, nullable=False)  # Hash-basierte ID

    # Document reference
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)

    # Subject (anonymized after processing)
    subject_id = Column(String(64), nullable=True)  # Hash des User-IDs

    # Processing details (Art. 30 DSGVO Pflichtangaben)
    data_categories = Column(CrossDBJSON, default=[])  # personal_identifiable, financial, etc.
    processing_purpose = Column(String(100), nullable=False)  # document_digitization, ocr_processing
    legal_basis = Column(String(255), nullable=False)  # Art. 6(1)(b) Contract, etc.

    # Retention
    retention_period_days = Column(Integer, nullable=False)
    retention_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Processing metadata
    processed_by_system = Column(String(100), default="ablage-system-ocr")
    processing_backend = Column(String(50), nullable=True)  # deepseek, got_ocr, etc.

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Data transfer (Art. 30(1)(e) DSGVO)
    data_recipients = Column(CrossDBJSON, default=[])  # Empty if no transfer
    third_country_transfer = Column(Boolean, default=False)

    # Technical measures (Art. 32 DSGVO)
    encryption_applied = Column(Boolean, default=True)
    pseudonymization_applied = Column(Boolean, default=False)

    # Relationships
    document = relationship("Document", backref="gdpr_activities")

    # Indexes
    __table_args__ = (
        Index("ix_gdpr_processing_activities_activity_id", "activity_id"),
        Index("ix_gdpr_processing_activities_document_id", "document_id"),
        Index("ix_gdpr_processing_activities_subject_id", "subject_id"),
        Index("ix_gdpr_processing_activities_created_at", "created_at"),
        Index("ix_gdpr_processing_activities_purpose", "processing_purpose"),
        Index("ix_gdpr_processing_activities_retention", "retention_expires_at"),
    )


# ==================== GoBD / Retention / Tax Advisor Models (lines ~4823-5428) ====================

class RetentionCategory(str, Enum):
    """GoBD Aufbewahrungskategorien nach deutschem Recht."""
    INVOICE = "invoice"                    # Rechnungen - 10 Jahre (§147 AO, §14b UStG)
    CONTRACT = "contract"                  # Verträge - 10 Jahre (§147 AO, §257 HGB)
    CORRESPONDENCE = "correspondence"      # Geschäftsbriefe - 6 Jahre (§257 HGB)
    BOOKING_DOCUMENT = "booking_document"  # Buchungsbelege - 10 Jahre (§147 AO)
    ANNUAL_REPORT = "annual_report"        # Jahresabschluesse - 10 Jahre (§257 HGB)
    TAX_DOCUMENT = "tax_document"          # Steuerbelege - 10 Jahre (§147 AO)
    EMPLOYEE_DOCUMENT = "employee_document"  # Personalakten - 10 Jahre (§257 HGB)
    OTHER = "other"                        # Sonstiges - 6 Jahre (§147 AO)


class HashAlgorithm(str, Enum):
    """Unterstützte Hash-Algorithmen für Dokumentensignaturen."""
    SHA256 = "SHA-256"
    SHA384 = "SHA-384"
    SHA512 = "SHA-512"


class DocumentAccessType(str, Enum):
    """Typen von Dokumentzugriffen für GoBD Audit-Trail."""
    VIEW = "view"                    # Dokument angesehen (Metadaten)
    DOWNLOAD = "download"            # Dokument heruntergeladen
    PREVIEW = "preview"              # Vorschau/Thumbnail angezeigt
    PRINT = "print"                  # Dokument gedruckt
    EXPORT = "export"                # Dokument exportiert (DATEV, PDF, etc.)
    SHARE = "share"                  # Dokument geteilt
    SEARCH_HIT = "search_hit"        # In Suchergebnis aufgetaucht
    OCR_ACCESS = "ocr_access"        # OCR-Text abgerufen
    METADATA_UPDATE = "metadata_update"  # Metadaten geändert (erlaubt!)
    ANNOTATION = "annotation"        # Anmerkung hinzugefuegt


class DocumentAccessLog(Base):
    """GoBD-konformes Dokumenten-Zugriffsprotokoll.

    Erfasst JEDEN Zugriff auf ein Dokument für:
    - GoBD-Nachvollziehbarkeit: Wer hat wann was zugegriffen?
    - DSGVO Art. 30: Verarbeitungsverzeichnis
    - Interne Compliance: Zugriffskontrolle und Reporting

    WICHTIG: Diese Tabelle sollte IMMUTABLE sein (kein UPDATE/DELETE).
    """
    __tablename__ = "document_access_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referenzen
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )

    # Zugriffsdetails
    access_type = Column(
        String(30),
        nullable=False,
        comment="Art des Zugriffs: view, download, export, etc."
    )
    access_reason = Column(
        String(255),
        nullable=True,
        comment="Optionaler Grund/Kontext des Zugriffs"
    )

    # Request-Kontext (für Audit)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    request_id = Column(
        String(36),
        nullable=True,
        comment="Korrelations-ID zur Request-Verfolgung"
    )

    # Ergebnis
    success = Column(Boolean, nullable=False, default=True)
    error_message = Column(String(500), nullable=True)
    bytes_transferred = Column(
        BigInteger,
        nullable=True,
        comment="Übertragene Bytes (bei Download/Export)"
    )

    # Zeitstempel (immutable!)
    accessed_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # Zusätzliche Metadaten
    access_metadata = Column(
        CrossDBJSON,
        default=dict,
        comment="Zusätzliche Kontext-Infos (Format, Export-Typ, etc.)"
    )

    # Sequenznummer für Immutabilitaets-Nachweis
    sequence_number = Column(
        BigInteger,
        unique=True,
        nullable=True,
        comment="Aufsteigende Sequenz für Lückendetektion"
    )

    # Relationships
    document = relationship("Document", backref="access_logs")
    user = relationship("User", backref="document_accesses")
    company = relationship("Company", backref="document_access_logs")

    __table_args__ = (
        Index("ix_document_access_logs_document_id", "document_id"),
        Index("ix_document_access_logs_user_id", "user_id"),
        Index("ix_document_access_logs_company_id", "company_id"),
        Index("ix_document_access_logs_accessed_at", "accessed_at"),
        Index("ix_document_access_logs_access_type", "access_type"),
        Index("ix_document_access_logs_sequence", "sequence_number"),
        # Composite index für typische Abfragen
        Index(
            "ix_document_access_logs_doc_time",
            "document_id", "accessed_at"
        ),
        {"comment": "GoBD-konformes Dokumenten-Zugriffsprotokoll"}
    )

    def __repr__(self) -> str:
        return f"<DocumentAccessLog {self.id} doc={self.document_id} type={self.access_type}>"


class DocumentArchive(Base):
    """GoBD-konforme Archivierung: Revisionssichere Speicherung mit Hash-Signatur.

    Erfuellt GoBD-Kriterien:
    - Nachvollziehbarkeit: Vollständiger Audit-Trail
    - Unveränderbarkeit: SHA-256 Hash-Signatur des Dokument-Inhalts
    - Vollständigkeit: Aufbewahrungsfristen-Management
    - Ordnung: Kategorisierung nach Dokumenttyp
    """
    __tablename__ = "document_archives"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referenzen (RESTRICT: Archivierte Dokumente dürfen nicht gelöscht werden)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False
    )

    # Signatur (GoBD: Unveränderbarkeit)
    content_hash = Column(
        String(128),
        nullable=False,
        comment="SHA-256 Hash des Dokument-Inhalts"
    )
    hash_algorithm = Column(
        String(20),
        nullable=False,
        default=HashAlgorithm.SHA256.value
    )
    signature_timestamp = Column(DateTime(timezone=True), nullable=False)
    signature_certificate = Column(
        Text,
        nullable=True,
        comment="TSA-Zertifikat (optional für qualifizierte Zeitstempel)"
    )

    # Aufbewahrungsfristen (GoBD: Ordnung + Aufbewahrung)
    retention_category = Column(
        String(50),
        nullable=False,
        comment="Kategorie: invoice, contract, correspondence, etc."
    )
    retention_years = Column(Integer, nullable=False, default=10)
    retention_expires_at = Column(Date, nullable=False)
    retention_reminder_sent = Column(Boolean, nullable=False, default=False)
    retention_reminder_at = Column(DateTime(timezone=True), nullable=True)

    # Verifikationsstatus
    is_verified = Column(Boolean, nullable=False, default=True)
    last_verification_at = Column(DateTime(timezone=True), nullable=True)
    verification_failed_reason = Column(Text, nullable=True)

    # Audit (GoBD: Nachvollziehbarkeit)
    archived_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    archived_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Metadaten
    archive_metadata = Column(CrossDBJSON, default=dict)

    # Relationships
    document = relationship("Document", back_populates="archive")
    company = relationship("Company", backref="document_archives")
    archived_by = relationship("User", backref="archived_documents")

    __table_args__ = (
        Index("ix_document_archives_company_id", "company_id"),
        Index("ix_document_archives_retention_expires", "retention_expires_at"),
        Index("ix_document_archives_retention_category", "retention_category"),
        Index("ix_document_archives_is_verified", "is_verified"),
        Index("ix_document_archives_archived_at", "archived_at"),
        {"comment": "GoBD-konforme Archivierung: Revisionssichere Speicherung mit Hash-Signatur"}
    )

    def __repr__(self) -> str:
        return f"<DocumentArchive {self.id} doc={self.document_id} hash={self.content_hash[:16]}...>"


class ProcedureDocumentationVersion(Base):
    """GoBD Verfahrensdokumentation: Automatisch generierte und versionierte Systemdokumentation.

    Die Verfahrensdokumentation beschreibt:
    - Wie Dokumente im System verarbeitet werden
    - Welche Sicherheitsmassnahmen implementiert sind
    - Wie die Aufbewahrungsfristen eingehalten werden
    - Änderungshistorie des Systems

    Wird automatisch bei relevanten Systemupdates generiert.
    """
    __tablename__ = "procedure_documentation_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Versionierung
    version = Column(
        String(20),
        nullable=False,
        comment="Semantic Version (z.B. 2.1.0)"
    )
    content = Column(
        CrossDBJSON,
        nullable=False,
        comment="Verfahrensdokumentation als strukturiertes JSON"
    )

    # Metadaten
    generated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    generated_by = Column(String(50), nullable=False, default="system")

    # Signatur für Unveränderbarkeit
    content_hash = Column(String(128), nullable=False)

    # Änderungshistorie
    change_summary = Column(
        Text,
        nullable=True,
        comment="Zusammenfassung der Änderungen zur Vorversion"
    )
    change_details = Column(CrossDBJSON, nullable=True)

    # Referenz zur Company (Multi-Tenant, NULL = System-weit)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True
    )

    # Relationships
    company = relationship("Company", backref="procedure_documentation_versions")

    __table_args__ = (
        Index("ix_procedure_docs_version", "version"),
        Index("ix_procedure_docs_company_id", "company_id"),
        Index("ix_procedure_docs_generated_at", "generated_at"),
        {"comment": "GoBD Verfahrensdokumentation: Automatisch generierte Systemdokumentation"}
    )

    def __repr__(self) -> str:
        return f"<ProcedureDocVersion {self.version} generated={self.generated_at}>"


class RetentionSetting(Base):
    """GoBD Aufbewahrungsfristen-Konfiguration pro Dokumentkategorie.

    Definiert die gesetzlichen Aufbewahrungsfristen nach deutschem Recht:
    - §147 AO (Abgabenordnung): 10 Jahre für Buchführungsunterlagen
    - §257 HGB (Handelsgesetzbuch): 6-10 Jahre je nach Dokumenttyp
    - §14b UStG (Umsatzsteuergesetz): 10 Jahre für Rechnungen
    """
    __tablename__ = "retention_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Kategorie-Definition
    category = Column(
        String(50),
        nullable=False,
        unique=True,
        comment="Technischer Name: invoice, contract, correspondence, etc."
    )
    display_name = Column(
        String(100),
        nullable=False,
        comment="Anzeigename auf Deutsch"
    )
    description = Column(Text, nullable=True)

    # Aufbewahrungsfristen
    retention_years = Column(Integer, nullable=False, default=10)
    legal_basis = Column(
        String(255),
        nullable=True,
        comment="Gesetzliche Grundlage: z.B. §147 AO, §257 HGB"
    )

    # Warnungen und Auto-Aktionen
    reminder_days_before = Column(
        Integer,
        nullable=False,
        default=90,
        comment="Tage vor Ablauf für Erinnerung"
    )
    auto_delete_enabled = Column(Boolean, nullable=False, default=False)
    requires_approval_for_delete = Column(Boolean, nullable=False, default=True)

    # Audit
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    updated_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relationships
    updated_by = relationship("User", backref="retention_setting_updates")

    __table_args__ = (
        {"comment": "GoBD Aufbewahrungsfristen-Konfiguration pro Dokumentkategorie"}
    )

    def __repr__(self) -> str:
        return f"<RetentionSetting {self.category} years={self.retention_years}>"


# ============================================================================
# GoBD Phase 4: Steuerberater-Zugang (Tax Advisor Access)
# ============================================================================

class TaxAdvisorInviteStatus(str, Enum):
    """Status einer Steuerberater-Einladung."""
    PENDING = "pending"       # Einladung gesendet, noch nicht akzeptiert
    ACCEPTED = "accepted"     # Einladung akzeptiert, Benutzer erstellt
    EXPIRED = "expired"       # Token abgelaufen
    REVOKED = "revoked"       # Einladung widerrufen


class TaxAdvisorInvite(Base):
    """GoBD Steuerberater-Einladungen für temporaeren Prüferzugang.

    Ermöglicht Administratoren, Steuerberatern zeitlich begrenzten
    Lesezugriff auf archivierte Dokumente zu gewähren.

    Flow:
    1. Admin erstellt Einladung mit E-Mail des Steuerberaters
    2. Steuerberater erhaelt E-Mail mit Einladungslink
    3. Steuerberater registriert sich über den Link
    4. Nach Registrierung hat Steuerberater access_duration_days Tage Zugang
    5. Nach Ablauf wird Zugang automatisch deaktiviert

    GoBD-Konformitaet:
    - Nachvollziehbarkeit: Alle Aktivitaeten werden protokolliert
    - Zeitliche Begrenzung: Zugang läuft automatisch ab
    - Eingeschraenkter Zugriff: Nur Lesezugriff auf relevante Dokumente
    """
    __tablename__ = "tax_advisor_invites"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Invite-Token (SHA-256 Hash für Sicherheit)
    token_hash = Column(
        String(128),
        unique=True,
        nullable=False,
        comment="SHA-256 Hash des Invite-Tokens"
    )

    # Referenzen
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Firma, für die der Zugang gilt"
    )
    invited_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Einladender Admin"
    )

    # Steuerberater-Daten
    email = Column(
        String(255),
        nullable=False,
        index=True,
        comment="E-Mail des Steuerberaters"
    )
    full_name = Column(
        String(255),
        nullable=True,
        comment="Name des Steuerberaters"
    )
    tax_firm_name = Column(
        String(255),
        nullable=True,
        comment="Name der Steuerkanzlei"
    )
    tax_advisor_id = Column(
        String(50),
        nullable=True,
        comment="Steuerberater-ID der Kammer (optional)"
    )

    # Zugangsparameter
    access_duration_days = Column(
        Integer,
        nullable=False,
        default=30,
        comment="Zugang in Tagen ab Akzeptierung"
    )
    access_scope = Column(
        CrossDBJSON,
        nullable=True,
        comment="Eingeschraenkter Zugriff (z.B. nur bestimmte Zeiträume, Dokumenttypen)"
    )

    # Status
    status = Column(
        String(20),
        nullable=False,
        default=TaxAdvisorInviteStatus.PENDING.value,
        index=True
    )
    expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="Ablaufdatum des Invite-Tokens (Standard: 7 Tage)"
    )

    # Audit
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    accepted_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Zeitpunkt der Akzeptierung"
    )
    accepted_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Erstellter Benutzer nach Akzeptierung"
    )

    # Relationships
    company = relationship("Company", backref="tax_advisor_invites")
    invited_by = relationship(
        "User",
        foreign_keys=[invited_by_id],
        backref="sent_tax_advisor_invites"
    )
    accepted_user = relationship(
        "User",
        foreign_keys=[accepted_user_id],
        backref="tax_advisor_invite"
    )

    __table_args__ = (
        Index("ix_tax_advisor_invites_status_expires", "status", "expires_at"),
        {"comment": "GoBD Steuerberater-Einladungen für temporaeren Prüferzugang"}
    )

    def __repr__(self) -> str:
        return f"<TaxAdvisorInvite {self.email} status={self.status}>"


class TaxAdvisorAccessLog(Base):
    """GoBD Steuerberater-Zugriffsprotokolle (revisionssicher).

    Protokolliert alle Aktivitaeten von Steuerberatern für:
    - GoBD-konforme Nachvollziehbarkeit
    - Prüfungsrelevante Dokumentation
    - Sicherheitsmonitoring

    Diese Logs sind revisionssicher und können nicht geändert werden.
    """
    __tablename__ = "tax_advisor_access_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referenzen
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Aktion
    action = Column(
        String(50),
        nullable=False,
        index=True,
        comment="document_view, archive_export, integrity_check, etc."
    )
    resource_type = Column(
        String(50),
        nullable=False,
        comment="document, archive, procedure_doc"
    )
    resource_id = Column(
        UUID(as_uuid=True),
        nullable=True,
        comment="ID der zugegriffenen Ressource"
    )

    # Details
    details = Column(
        CrossDBJSON,
        nullable=True,
        comment="Zusätzliche Metadaten (Dateiname, Exportformat, etc.)"
    )
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)

    # Timestamp (immutable)
    accessed_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )

    # Relationships
    user = relationship("User", backref="tax_advisor_access_logs")
    company = relationship("Company", backref="tax_advisor_access_logs")

    __table_args__ = (
        Index("ix_tax_advisor_logs_user_action", "user_id", "action"),
        Index("ix_tax_advisor_logs_company_date", "company_id", "accessed_at"),
        {"comment": "GoBD Steuerberater-Zugriffsprotokolle (revisionssicher)"}
    )

    def __repr__(self) -> str:
        return f"<TaxAdvisorAccessLog {self.action} user={self.user_id}>"


# ==================== GDPR Consent Versioning Models (lines ~10976-11316) ====================

class GDPRConsentVersion(Base):
    """Versionierte Consent-Texte für DSGVO-konforme Einwilligungen.

    Speichert verschiedene Versionen von Einwilligungstexten mit SHA-256 Hash
    zur Nachweisbarkeit welchen Text der User akzeptiert hat.
    """
    __tablename__ = "gdpr_consent_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Scope und Version
    scope = Column(String(100), nullable=False, index=True,
                   comment="Consent-Scope (personal_data, financial_data, etc.)")
    version = Column(String(50), nullable=False,
                     comment="Versionsnummer z.B. '1.0', '2.0'")

    # Consent-Text
    title = Column(String(255), nullable=False,
                   comment="Titel der Einwilligung")
    description = Column(Text, nullable=False,
                         comment="Kurzbeschreibung")
    full_text = Column(Text, nullable=False,
                       comment="Vollständiger Consent-Text")
    text_hash = Column(String(64), nullable=False, index=True,
                       comment="SHA-256 Hash des Textes")

    # Sprache und Status
    language = Column(String(10), nullable=False, default="de",
                      comment="Sprachcode (de, en, etc.)")
    is_active = Column(Boolean, nullable=False, default=True, index=True,
                       comment="Aktive Version für diesen Scope")

    # Gültigkeit
    effective_from = Column(DateTime(timezone=True), nullable=False,
                            default=func.now(),
                            comment="Ab wann gültig")
    effective_until = Column(DateTime(timezone=True), nullable=True,
                             comment="Bis wann gültig (NULL = unbegrenzt)")

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by_id = Column(UUID(as_uuid=True),
                           ForeignKey("users.id", ondelete="SET NULL"),
                           nullable=True)

    # Relationships
    created_by = relationship("User", backref="created_consent_versions")
    consent_scopes = relationship("GDPRConsentScope", back_populates="consent_version")

    __table_args__ = (
        UniqueConstraint("scope", "version", name="uq_gdpr_consent_versions_scope_version"),
        Index("ix_gdpr_consent_versions_scope_active", "scope", "is_active",
              postgresql_where=text("is_active = true")),
        {"comment": "Versionierte DSGVO Consent-Texte"}
    )

    def __repr__(self) -> str:
        return f"<GDPRConsentVersion {self.scope} v{self.version}>"


class GDPRConsentScope(Base):
    """Granulare Einwilligungen pro User und Scope.

    Speichert für jeden User welche Einwilligungen erteilt oder
    widerrufen wurden, mit vollständigem Audit-Trail.
    """
    __tablename__ = "gdpr_consent_scopes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # User und Company
    user_id = Column(UUID(as_uuid=True),
                     ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    company_id = Column(UUID(as_uuid=True),
                        ForeignKey("companies.id", ondelete="CASCADE"),
                        nullable=True, index=True,
                        comment="Optional für company-spezifische Consents")

    # Scope und Status
    scope = Column(String(100), nullable=False, index=True,
                   comment="personal_data, financial_data, analytics, marketing, etc.")
    consent_given = Column(Boolean, nullable=False, default=False,
                           comment="True wenn Einwilligung erteilt")

    # Referenz auf akzeptierte Version
    consent_version_id = Column(UUID(as_uuid=True),
                                ForeignKey("gdpr_consent_versions.id", ondelete="SET NULL"),
                                nullable=True)
    consent_text_hash = Column(String(64), nullable=True,
                               comment="SHA-256 des akzeptierten Textes")

    # Zeitstempel
    granted_at = Column(DateTime(timezone=True), nullable=True,
                        comment="Wann erteilt")
    withdrawn_at = Column(DateTime(timezone=True), nullable=True,
                          comment="Wann widerrufen")
    valid_from = Column(DateTime(timezone=True), nullable=False,
                        default=func.now())
    valid_until = Column(DateTime(timezone=True), nullable=True,
                         comment="Ablaufdatum der Einwilligung")

    # Einwilligungsmethode
    consent_method = Column(String(50), nullable=True,
                            comment="web_form, api, paper, verbal, double_opt_in")
    ip_address = Column(String(45), nullable=True,
                        comment="IPv4/IPv6 bei Erteilung")
    user_agent = Column(String(500), nullable=True,
                        comment="Browser User-Agent")

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now())

    # Relationships
    user = relationship("User", backref="gdpr_consent_scopes")
    company = relationship("Company", backref="company_gdpr_consent_scopes")
    consent_version = relationship("GDPRConsentVersion", back_populates="consent_scopes")
    history = relationship("GDPRConsentHistory", back_populates="consent_scope",
                           order_by="desc(GDPRConsentHistory.created_at)")

    __table_args__ = (
        Index("ix_gdpr_consent_scopes_user_scope_active", "user_id", "scope",
              postgresql_where=text("withdrawn_at IS NULL")),
        {"comment": "Granulare DSGVO Einwilligungen pro User/Scope"}
    )

    def __repr__(self) -> str:
        status = "granted" if self.consent_given and not self.withdrawn_at else "withdrawn"
        return f"<GDPRConsentScope {self.scope} ({status})>"


class GDPRDataSubjectRequest(Base):
    """Betroffenenrechte-Anfragen nach DSGVO Art. 15-21.

    Trackt Anfragen von Betroffenen zu:
    - Art. 15: Auskunftsrecht
    - Art. 16: Recht auf Berichtigung
    - Art. 17: Recht auf Löschung
    - Art. 18: Recht auf Einschränkung
    - Art. 20: Recht auf Datenübertragbarkeit
    - Art. 21: Widerspruchsrecht
    """
    __tablename__ = "gdpr_data_subject_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Betroffener
    user_id = Column(UUID(as_uuid=True),
                     ForeignKey("users.id", ondelete="SET NULL"),
                     nullable=True, index=True)
    company_id = Column(UUID(as_uuid=True),
                        ForeignKey("companies.id", ondelete="SET NULL"),
                        nullable=True, index=True)

    # Anfragetyp (Art. 15-21 DSGVO)
    request_type = Column(String(50), nullable=False, index=True,
                          comment="access, erasure, rectification, portability, restriction, objection")
    status = Column(String(50), nullable=False, default="pending", index=True,
                    comment="pending, in_progress, completed, rejected, cancelled")

    # Antragsdaten
    requester_email = Column(String(255), nullable=False,
                             comment="Email des Antragstellers")
    requester_name = Column(String(255), nullable=True)
    verification_token = Column(String(255), nullable=True,
                                comment="Token zur Verifizierung der Identität")
    verified_at = Column(DateTime(timezone=True), nullable=True)

    # Details
    description = Column(Text, nullable=True,
                         comment="Beschreibung der Anfrage")
    affected_data_categories = Column(CrossDBJSON, nullable=True,
                                      comment='["personal", "financial", "documents"]')
    rectification_details = Column(CrossDBJSON, nullable=True,
                                   comment="Details für Art. 16 Berichtigung")

    # Bearbeitung
    assigned_to_id = Column(UUID(as_uuid=True),
                            ForeignKey("users.id", ondelete="SET NULL"),
                            nullable=True)
    response_notes = Column(Text, nullable=True,
                            comment="Interne Notizen zur Bearbeitung")
    rejection_reason = Column(Text, nullable=True,
                              comment="Grund bei Ablehnung")

    # Ergebnis
    export_file_path = Column(String(500), nullable=True,
                              comment="Pfad zum Export bei Portabilität")
    export_format = Column(String(20), nullable=True,
                           comment="json, csv, xml")

    # Zeitstempel (DSGVO: 30 Tage Frist!)
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    due_date = Column(DateTime(timezone=True), nullable=False,
                      comment="Frist: requested_at + 30 Tage")
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now())

    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="dsr_requests")
    assigned_to = relationship("User", foreign_keys=[assigned_to_id],
                               backref="assigned_dsr_requests")
    company = relationship("Company", backref="dsr_requests")
    exports = relationship("GDPRDataExport", back_populates="request")

    __table_args__ = (
        Index("ix_gdpr_dsr_pending_overdue", "due_date", "status",
              postgresql_where=text("status IN ('pending', 'in_progress')")),
        {"comment": "DSGVO Betroffenenrechte-Anfragen (Art. 15-21)"}
    )

    def __repr__(self) -> str:
        return f"<GDPRDataSubjectRequest {self.request_type} ({self.status})>"


class GDPRDataExport(Base):
    """Datenexport-Logs für DSGVO Art. 20 Portabilität.

    Trackt alle Datenexporte die im Rahmen von Betroffenenrechte-Anfragen
    oder auf Userwunsch erstellt wurden.
    """
    __tablename__ = "gdpr_data_exports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Betroffener
    user_id = Column(UUID(as_uuid=True),
                     ForeignKey("users.id", ondelete="SET NULL"),
                     nullable=True, index=True)
    company_id = Column(UUID(as_uuid=True),
                        ForeignKey("companies.id", ondelete="SET NULL"),
                        nullable=True, index=True)
    request_id = Column(UUID(as_uuid=True),
                        ForeignKey("gdpr_data_subject_requests.id", ondelete="SET NULL"),
                        nullable=True, index=True,
                        comment="Referenz auf DSR falls vorhanden")

    # Export-Details
    export_type = Column(String(50), nullable=False,
                         comment="full, partial, category")
    data_categories = Column(CrossDBJSON, nullable=False,
                             comment='["documents", "comments", "settings"]')
    format = Column(String(20), nullable=False, default="json",
                    comment="json, csv, xml")

    # Datei
    file_path = Column(String(500), nullable=True,
                       comment="Pfad zur Export-Datei")
    file_size_bytes = Column(BigInteger, nullable=True)
    file_hash = Column(String(64), nullable=True,
                       comment="SHA-256 der Export-Datei")

    # Status
    status = Column(String(50), nullable=False, default="pending", index=True,
                    comment="pending, processing, completed, failed, expired, downloaded")
    error_message = Column(Text, nullable=True)

    # Download-Tracking
    download_count = Column(Integer, nullable=False, default=0)
    last_downloaded_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False,
                        comment="Export verfaellt nach 7 Tagen")

    # Zeitstempel
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", backref="gdpr_exports")
    company = relationship("Company", backref="gdpr_exports")
    request = relationship("GDPRDataSubjectRequest", back_populates="exports")

    __table_args__ = (
        Index("ix_gdpr_exports_expired", "expires_at", "status",
              postgresql_where=text("status = 'completed'")),
        {"comment": "DSGVO Datenexport-Logs (Art. 20 Portabilität)"}
    )

    def __repr__(self) -> str:
        return f"<GDPRDataExport {self.export_type} ({self.status})>"


class GDPRConsentHistory(Base):
    """Audit-Trail für Einwilligungsänderungen.

    Dokumentiert jede Änderung an Einwilligungen für
    vollständige Nachweisbarkeit (DSGVO Art. 7).
    """
    __tablename__ = "gdpr_consent_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referenzen
    consent_scope_id = Column(UUID(as_uuid=True),
                              ForeignKey("gdpr_consent_scopes.id", ondelete="CASCADE"),
                              nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True),
                     ForeignKey("users.id", ondelete="SET NULL"),
                     nullable=True, index=True)

    # Änderung
    action = Column(String(50), nullable=False, index=True,
                    comment="granted, withdrawn, updated, expired, version_changed")
    previous_value = Column(Boolean, nullable=True,
                            comment="Vorheriger Consent-Status")
    new_value = Column(Boolean, nullable=False,
                       comment="Neuer Consent-Status")
    consent_version_id = Column(UUID(as_uuid=True),
                                ForeignKey("gdpr_consent_versions.id", ondelete="SET NULL"),
                                nullable=True)

    # Kontext
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    reason = Column(Text, nullable=True,
                    comment="Grund bei Widerruf")

    # Timestamp (immutable)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    consent_scope = relationship("GDPRConsentScope", back_populates="history")
    user = relationship("User", backref="consent_history")
    consent_version = relationship("GDPRConsentVersion", backref="history_entries")

    __table_args__ = (
        Index("ix_gdpr_consent_history_created_at", "created_at"),
        {"comment": "Audit-Trail für DSGVO Einwilligungsänderungen"}
    )

    def __repr__(self) -> str:
        return f"<GDPRConsentHistory {self.action} at {self.created_at}>"


# =============================================================================
# DPIA (Data Protection Impact Assessment) Models (lines ~11517-11831)
# =============================================================================

class DPIAStatus(str, Enum):
    """DPIA Status enum."""
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class DPIARiskLevel(str, Enum):
    """DPIA Risk Level enum."""
    VERY_HIGH = "very_high"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    MINIMAL = "minimal"


class DPIALegalBasis(str, Enum):
    """DPIA Legal Basis enum (Art. 6 DSGVO)."""
    CONSENT = "consent"
    CONTRACT = "contract"
    LEGAL_OBLIGATION = "legal_obligation"
    VITAL_INTERESTS = "vital_interests"
    PUBLIC_INTEREST = "public_interest"
    LEGITIMATE_INTEREST = "legitimate_interest"


class DPIAMeasureType(str, Enum):
    """DPIA Mitigation Measure Type enum."""
    TECHNICAL = "technical"
    ORGANIZATIONAL = "organizational"
    CONTRACTUAL = "contractual"
    LEGAL = "legal"


class DPIAImplementationStatus(str, Enum):
    """DPIA Implementation Status enum."""
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    IMPLEMENTED = "implemented"


class DPIA(Base):
    """
    Data Protection Impact Assessment (Art. 35 DSGVO).

    Vollständige DPIA-Dokumentation mit Risikobewertung,
    Massnahmen und DPO-Konsultation.
    """
    __tablename__ = "dpias"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    version = Column(String(20), nullable=False, default="1.0")
    status = Column(
        String(20),
        nullable=False,
        default=DPIAStatus.DRAFT.value
    )

    # Verantwortlichkeiten
    controller_name = Column(String(255), nullable=False)
    controller_contact = Column(String(255), nullable=True)
    dpo_name = Column(String(255), nullable=False)
    dpo_contact = Column(String(255), nullable=True)
    assessment_date = Column(DateTime(timezone=True), nullable=True)
    assessor_name = Column(String(255), nullable=True)

    # Bewertungen
    necessity_assessment = Column(Text, nullable=True)
    proportionality_assessment = Column(Text, nullable=True)
    overall_risk_level = Column(
        String(20),
        nullable=True,
        default=DPIARiskLevel.MEDIUM.value
    )

    # Aufsichtsbehoerde
    supervisory_authority_consultation = Column(Boolean, default=False)
    supervisory_authority_response = Column(Text, nullable=True)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company", backref="dpias")
    created_by = relationship("User", foreign_keys=[created_by_id])
    processing_operations = relationship(
        "DPIAProcessingOperation",
        back_populates="dpia",
        cascade="all, delete-orphan"
    )
    data_subject_groups = relationship(
        "DPIADataSubjectGroup",
        back_populates="dpia",
        cascade="all, delete-orphan"
    )
    risks = relationship(
        "DPIARisk",
        back_populates="dpia",
        cascade="all, delete-orphan"
    )
    mitigation_measures = relationship(
        "DPIAMitigationMeasure",
        back_populates="dpia",
        cascade="all, delete-orphan"
    )
    consultation = relationship(
        "DPIAConsultation",
        back_populates="dpia",
        uselist=False,
        cascade="all, delete-orphan"
    )
    audit_logs = relationship(
        "DPIAAuditLog",
        back_populates="dpia",
        cascade="all, delete-orphan",
        order_by="desc(DPIAAuditLog.created_at)"
    )

    __table_args__ = (
        Index("ix_dpias_company_status", "company_id", "status"),
        {"comment": "Data Protection Impact Assessments (Art. 35 DSGVO)"}
    )

    def __repr__(self) -> str:
        return f"<DPIA {self.id} title={self.title} status={self.status}>"


class DPIAProcessingOperation(Base):
    """Verarbeitungstätigkeit innerhalb einer DPIA."""
    __tablename__ = "dpia_processing_operations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dpia_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dpias.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    purpose = Column(Text, nullable=True)
    legal_basis = Column(String(50), nullable=True)
    data_categories = Column(CrossDBJSON, default=list)  # Array of strings
    retention_period = Column(String(255), nullable=True)
    automated_decision_making = Column(Boolean, default=False)
    profiling = Column(Boolean, default=False)
    data_transfer_outside_eu = Column(Boolean, default=False)
    transfer_countries = Column(CrossDBJSON, default=list)  # Array of strings
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    dpia = relationship("DPIA", back_populates="processing_operations")

    def __repr__(self) -> str:
        return f"<DPIAProcessingOperation {self.id} name={self.name}>"


class DPIADataSubjectGroup(Base):
    """Betroffenengruppe innerhalb einer DPIA."""
    __tablename__ = "dpia_data_subject_groups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dpia_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dpias.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    estimated_count = Column(Integer, nullable=True)
    includes_vulnerable = Column(Boolean, default=False)
    includes_children = Column(Boolean, default=False)

    # Relationship
    dpia = relationship("DPIA", back_populates="data_subject_groups")

    def __repr__(self) -> str:
        return f"<DPIADataSubjectGroup {self.id} name={self.name}>"


class DPIARisk(Base):
    """Risikobewertung innerhalb einer DPIA."""
    __tablename__ = "dpia_risks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dpia_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dpias.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    risk_id = Column(String(50), nullable=False)  # e.g., R1, R2
    description = Column(Text, nullable=False)
    affected_rights = Column(CrossDBJSON, default=list)  # Array of strings
    likelihood = Column(Integer, nullable=False)  # 1-5
    impact = Column(Integer, nullable=False)  # 1-5
    inherent_risk = Column(String(20), nullable=True)
    residual_risk = Column(String(20), nullable=True)
    mitigation_measures = Column(CrossDBJSON, default=list)  # Array of measure IDs

    # Relationship
    dpia = relationship("DPIA", back_populates="risks")

    @property
    def risk_score(self) -> int:
        """Berechne Risiko-Score (1-25)."""
        return self.likelihood * self.impact

    def __repr__(self) -> str:
        return f"<DPIARisk {self.id} risk_id={self.risk_id}>"


class DPIAMitigationMeasure(Base):
    """Risikominderungsmassnahme innerhalb einer DPIA."""
    __tablename__ = "dpia_mitigation_measures"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dpia_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dpias.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    measure_id = Column(String(50), nullable=False)  # e.g., M1, M2
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    measure_type = Column(String(30), nullable=True)
    addresses_risks = Column(CrossDBJSON, default=list)  # Array of risk IDs
    implementation_status = Column(
        String(30),
        default=DPIAImplementationStatus.PLANNED.value
    )
    responsible_person = Column(String(255), nullable=True)
    deadline = Column(DateTime(timezone=True), nullable=True)
    effectiveness = Column(Text, nullable=True)

    # Relationship
    dpia = relationship("DPIA", back_populates="mitigation_measures")

    def __repr__(self) -> str:
        return f"<DPIAMitigationMeasure {self.id} measure_id={self.measure_id}>"


class DPIAConsultation(Base):
    """DPO-Konsultation zu einer DPIA."""
    __tablename__ = "dpia_consultations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dpia_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dpias.id", ondelete="CASCADE"),
        nullable=False,
        unique=True  # One consultation per DPIA
    )
    dpo_name = Column(String(255), nullable=False)
    consultation_date = Column(DateTime(timezone=True), nullable=False)
    opinion = Column(Text, nullable=True)
    recommendations = Column(CrossDBJSON, default=list)  # Array of strings
    approval = Column(Boolean, nullable=False)
    conditions = Column(CrossDBJSON, default=list)  # Array of strings

    # Relationship
    dpia = relationship("DPIA", back_populates="consultation")

    def __repr__(self) -> str:
        return f"<DPIAConsultation {self.id} approval={self.approval}>"


class DPIAAuditLog(Base):
    """Audit-Trail für DPIA-Änderungen."""
    __tablename__ = "dpia_audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dpia_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dpias.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    action = Column(String(50), nullable=False)
    user_name = Column(String(255), nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    dpia = relationship("DPIA", back_populates="audit_logs")

    def __repr__(self) -> str:
        return f"<DPIAAuditLog {self.id} action={self.action}>"
