"""HR-Modelle: Personal, Abteilungen, Positionen, Zeiterfassung.

Extrahiert aus models.py als Teil der Modularisierung (Phase 1.1).
Enthaelt alle Mitarbeiter-bezogenen Modelle fuer das HR-Modul.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models_base import Base, CrossDBJSON, SoftDeleteMixin

# =============================================================================
# HR ENUMS
# =============================================================================

class EmploymentType(str, Enum):
    """Beschaeftigungsart."""
    FULL_TIME = "full_time"               # Vollzeit
    PART_TIME = "part_time"               # Teilzeit
    MINI_JOB = "mini_job"                 # Minijob (520 EUR)
    TEMPORARY = "temporary"               # Befristet
    TRAINEE = "trainee"                   # Auszubildender
    INTERN = "intern"                     # Praktikant
    FREELANCE = "freelance"               # Freiberuflich
    WORKING_STUDENT = "working_student"   # Werkstudent


class EmployeeStatus(str, Enum):
    """Mitarbeiter-Status."""
    ONBOARDING = "onboarding"             # In Einarbeitung
    ACTIVE = "active"                     # Aktiv
    ON_LEAVE = "on_leave"                 # Beurlaubt
    SICK = "sick"                         # Langzeitkrank
    NOTICE_PERIOD = "notice_period"       # In Kuendigung
    TERMINATED = "terminated"             # Ausgeschieden


class LeaveType(str, Enum):
    """Abwesenheitstyp."""
    VACATION = "vacation"                 # Urlaub
    SICK = "sick"                         # Krank
    SICK_CHILD = "sick_child"             # Kind krank
    PARENTAL = "parental"                 # Elternzeit
    SPECIAL = "special"                   # Sonderurlaub
    UNPAID = "unpaid"                     # Unbezahlter Urlaub
    TRAINING = "training"                 # Weiterbildung
    BUSINESS_TRIP = "business_trip"       # Dienstreise
    HOME_OFFICE = "home_office"           # Homeoffice


class LeaveRequestStatus(str, Enum):
    """Urlaubsantrag-Status."""
    DRAFT = "draft"                       # Entwurf
    SUBMITTED = "submitted"               # Eingereicht
    APPROVED = "approved"                 # Genehmigt
    REJECTED = "rejected"                 # Abgelehnt
    CANCELLED = "cancelled"               # Storniert


class HRContractStatus(str, Enum):
    """Arbeitsvertrag-Status."""
    DRAFT = "draft"                       # Entwurf
    PENDING_SIGNATURE = "pending_signature"  # Warten auf Unterschrift
    ACTIVE = "active"                     # Aktiv
    TERMINATED = "terminated"             # Beendet


class TrainingStatus(str, Enum):
    """Weiterbildungs-Status."""
    PLANNED = "planned"                   # Geplant
    REGISTERED = "registered"             # Angemeldet
    IN_PROGRESS = "in_progress"           # Laufend
    COMPLETED = "completed"               # Abgeschlossen
    CANCELLED = "cancelled"               # Abgebrochen


class ReviewStatus(str, Enum):
    """Beurteilungs-Status."""
    DRAFT = "draft"                       # Entwurf
    PENDING_EMPLOYEE = "pending_employee" # Warten auf Mitarbeiter-Kommentar
    PENDING_HR = "pending_hr"             # Warten auf HR-Freigabe
    COMPLETED = "completed"               # Abgeschlossen


class OnboardingTaskStatus(str, Enum):
    """Onboarding-Aufgaben-Status."""
    PENDING = "pending"                   # Ausstehend
    IN_PROGRESS = "in_progress"           # In Bearbeitung
    COMPLETED = "completed"               # Erledigt
    SKIPPED = "skipped"                   # Uebersprungen


class HRDocumentCategory(str, Enum):
    """HR-Dokument Kategorien."""
    VERTRAEGE = "verträge"               # Vertraege & Stammdaten
    STAMMDATEN = "stammdaten"             # Stammdaten
    LOHN = "lohn"                         # Lohn & Gehalt
    URLAUB = "urlaub"                     # Urlaub & Abwesenheit
    WEITERBILDUNG = "weiterbildung"       # Weiterbildung
    BEURTEILUNG = "beurteilung"           # Beurteilung
    SONSTIGES = "sonstiges"               # Sonstiges


# Backward-compatible alias
ContractStatus = HRContractStatus


# =============================================================================
# HR MODELS
# =============================================================================

class Department(SoftDeleteMixin, Base):
    """Abteilung mit hierarchischer Struktur.

    Ermoeglicht die Abbildung einer Organisationsstruktur mit
    beliebig tiefer Verschachtelung (parent_id).
    """

    __tablename__ = "departments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )
    parent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True
    )

    # Identifikation
    name = Column(String(100), nullable=False)
    short_name = Column(String(20), nullable=True)
    description = Column(Text, nullable=True)
    cost_center = Column(String(50), nullable=True)

    # Manager (wird spaeter gesetzt, da Employee noch nicht existiert)
    manager_id = Column(UUID(as_uuid=True), nullable=True)

    # Sortierung
    sort_order = Column(Integer, default=0)

    # Status
    is_active = Column(Boolean, default=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    company = relationship("Company")
    parent = relationship("Department", remote_side=[id], backref="children")

    __table_args__ = (
        Index("ix_departments_company_id", "company_id"),
        Index("ix_departments_parent_id", "parent_id"),
        Index("ix_departments_is_active", "is_active"),
        Index("ix_departments_deleted_at", "deleted_at"),
        Index("ix_departments_company_name", "company_id", "name"),
    )

    def __repr__(self) -> str:
        return f"<Department {self.name}>"


class Position(SoftDeleteMixin, Base):
    """Stelle/Rolle innerhalb einer Firma.

    Definiert Stellenbezeichnungen mit optionalem Gehaltsrahmen
    und Zuordnung zu einer Abteilung.
    """

    __tablename__ = "positions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )
    department_id = Column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True
    )

    # Bezeichnung
    title = Column(String(200), nullable=False)
    title_en = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)

    # Klassifizierung
    level = Column(Integer, default=1)  # Hierarchie-Ebene
    job_family = Column(String(100), nullable=True)  # z.B. "Engineering", "Sales"

    # Gehaltsrahmen
    salary_band_min = Column(Numeric(10, 2), nullable=True)
    salary_band_max = Column(Numeric(10, 2), nullable=True)

    # Status
    is_active = Column(Boolean, default=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company")
    department = relationship("Department")

    __table_args__ = (
        Index("ix_positions_company_id", "company_id"),
        Index("ix_positions_department_id", "department_id"),
        Index("ix_positions_is_active", "is_active"),
        Index("ix_positions_title", "title"),
    )

    def __repr__(self) -> str:
        return f"<Position {self.title}>"


class Employee(SoftDeleteMixin, Base):
    """Mitarbeiter-Stammdaten.

    Zentrale Entitaet fuer alle HR-Daten eines Mitarbeiters.
    Kann optional mit einem User-Account verknuepft sein.
    """

    __tablename__ = "employees"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )

    # Verknuepfung zum User (falls Mitarbeiter auch Systemzugang hat)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Identifikation
    employee_number = Column(String(50), nullable=False)  # Personalnummer

    # Persoenliche Daten
    salutation = Column(String(20), nullable=True)  # Herr/Frau
    title = Column(String(50), nullable=True)  # Dr., Prof., etc.
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    birth_name = Column(String(100), nullable=True)
    date_of_birth = Column(Date, nullable=True)
    place_of_birth = Column(String(100), nullable=True)
    nationality = Column(String(50), nullable=True)
    gender = Column(String(20), nullable=True)

    # Kontakt (geschaeftlich)
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    mobile = Column(String(50), nullable=True)

    # Kontakt (privat)
    private_email = Column(String(255), nullable=True)
    private_phone = Column(String(50), nullable=True)

    # Adresse (privat)
    street = Column(String(255), nullable=True)
    street_number = Column(String(20), nullable=True)
    postal_code = Column(String(10), nullable=True)
    city = Column(String(100), nullable=True)
    country = Column(String(2), default="DE")

    # Notfall-Kontakt
    emergency_contact_name = Column(String(200), nullable=True)
    emergency_contact_phone = Column(String(50), nullable=True)
    emergency_contact_relation = Column(String(50), nullable=True)

    # Organisatorisch
    department_id = Column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True
    )
    position_id = Column(
        UUID(as_uuid=True),
        ForeignKey("positions.id", ondelete="SET NULL"),
        nullable=True
    )
    supervisor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True
    )

    # Beschaeftigung
    employment_type = Column(String(30), default=EmploymentType.FULL_TIME.value)
    status = Column(String(30), default=EmployeeStatus.ACTIVE.value)
    hire_date = Column(Date, nullable=True)
    probation_end_date = Column(Date, nullable=True)
    termination_date = Column(Date, nullable=True)

    # Arbeitszeit
    weekly_hours = Column(Numeric(5, 2), default=40)
    vacation_days_per_year = Column(Integer, default=30)

    # Steuer & Sozialversicherung
    tax_id = Column(String(20), nullable=True)  # Steuer-ID
    tax_class = Column(String(5), nullable=True)  # Steuerklasse
    social_security_number = Column(String(20), nullable=True)
    health_insurance = Column(String(100), nullable=True)
    health_insurance_number = Column(String(50), nullable=True)

    # Banking
    iban = Column(String(34), nullable=True)
    bic = Column(String(11), nullable=True)
    bank_name = Column(String(100), nullable=True)

    # Profilbild
    photo_path = Column(String(500), nullable=True)

    # Flexible Felder
    custom_fields = Column(CrossDBJSON, default=dict)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Soft-Delete (GDPR/GoBD)
    deleted_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    company = relationship("Company")
    user = relationship("User", foreign_keys=[user_id])
    department = relationship("Department", foreign_keys=[department_id])
    position = relationship("Position")
    supervisor = relationship("Employee", remote_side=[id], foreign_keys=[supervisor_id])

    # Bidirectional relationships
    contracts = relationship("EmploymentContract", back_populates="employee", order_by="EmploymentContract.start_date.desc()")
    leave_requests = relationship("LeaveRequest", back_populates="employee", foreign_keys="LeaveRequest.employee_id", order_by="LeaveRequest.start_date.desc()")
    absences = relationship("Absence", back_populates="employee", order_by="Absence.start_date.desc()")
    time_entries = relationship("TimeEntry", back_populates="employee", order_by="TimeEntry.date.desc()")
    trainings = relationship("Training", back_populates="employee", order_by="Training.start_date.desc()")
    performance_reviews = relationship("PerformanceReview", back_populates="employee", foreign_keys="PerformanceReview.employee_id")
    onboarding_tasks = relationship("OnboardingTask", back_populates="employee", foreign_keys="OnboardingTask.employee_id", order_by="OnboardingTask.sort_order")
    hr_documents = relationship("HRDocument", back_populates="employee")

    __table_args__ = (
        Index("ix_employees_company_id", "company_id"),
        Index("ix_employees_user_id", "user_id"),
        Index("ix_employees_department_id", "department_id"),
        Index("ix_employees_position_id", "position_id"),
        Index("ix_employees_supervisor_id", "supervisor_id"),
        Index("ix_employees_status", "status"),
        Index("ix_employees_employee_number", "company_id", "employee_number"),
        Index("ix_employees_email", "email"),
        Index("ix_employees_deleted_at", "deleted_at"),
        Index("ix_employees_name", "last_name", "first_name"),
    )

    @property
    def full_name(self) -> str:
        """Vollstaendiger Name."""
        parts = []
        if self.title:
            parts.append(self.title)
        parts.append(self.first_name)
        parts.append(self.last_name)
        return " ".join(parts)

    @property
    def is_deleted(self) -> bool:
        """Prueft ob Mitarbeiter geloescht ist."""
        return self.deleted_at is not None

    def __repr__(self) -> str:
        return f"<Employee {self.employee_number}: {self.first_name} {self.last_name}>"


class EmploymentContract(Base):
    """Arbeitsvertrag mit Versionshistorie.

    Jede Vertragsaenderung erzeugt eine neue Version.
    is_current markiert den aktuell gueltigen Vertrag.
    """

    __tablename__ = "employment_contracts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False
    )

    # Versionierung
    version = Column(Integer, default=1)
    is_current = Column(Boolean, default=True)
    supersedes_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employment_contracts.id", ondelete="SET NULL"),
        nullable=True
    )

    # Vertragsdetails
    contract_type = Column(String(30), nullable=False)  # EmploymentType
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)  # Null = unbefristet

    # Position
    position_id = Column(
        UUID(as_uuid=True),
        ForeignKey("positions.id", ondelete="SET NULL"),
        nullable=True
    )
    job_title = Column(String(200), nullable=False)
    job_description = Column(Text, nullable=True)

    # Arbeitszeit
    weekly_hours = Column(Numeric(5, 2), nullable=False)
    vacation_days = Column(Integer, nullable=False)

    # Verguetung
    salary_type = Column(String(20), default="monthly")  # monthly, hourly
    base_salary = Column(Numeric(10, 2), nullable=False)
    salary_currency = Column(String(3), default="EUR")
    bonus_eligible = Column(Boolean, default=False)
    bonus_target = Column(Numeric(10, 2), nullable=True)

    # Zusatzleistungen
    benefits = Column(CrossDBJSON, default=list)  # ["company_car", "phone", "pension"]

    # Kuendigung
    notice_period_employee = Column(String(50), nullable=True)  # z.B. "1 Monat zum Monatsende"
    notice_period_employer = Column(String(50), nullable=True)

    # Dokument-Referenz
    contract_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True
    )

    # Workflow
    status = Column(String(30), default=HRContractStatus.DRAFT.value)
    signed_date = Column(Date, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    employee = relationship("Employee", back_populates="contracts")
    position = relationship("Position")
    supersedes = relationship("EmploymentContract", remote_side=[id])
    contract_document = relationship("Document")

    __table_args__ = (
        Index("ix_employment_contracts_employee_id", "employee_id"),
        Index("ix_employment_contracts_is_current", "is_current"),
        Index("ix_employment_contracts_status", "status"),
        Index("ix_employment_contracts_start_date", "start_date"),
    )

    def __repr__(self) -> str:
        return f"<EmploymentContract v{self.version} {self.job_title}>"


class LeaveRequest(Base):
    """Urlaubsantrag mit Workflow.

    Status-Workflow: draft -> submitted -> approved/rejected -> cancelled
    """

    __tablename__ = "leave_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )
    employee_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False
    )

    # Zeitraum
    leave_type = Column(String(30), nullable=False)  # LeaveType
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    start_half_day = Column(Boolean, default=False)  # Erster Tag nur halbtags
    end_half_day = Column(Boolean, default=False)    # Letzter Tag nur halbtags

    # Berechnung
    total_days = Column(Numeric(5, 2), nullable=False)

    # Beschreibung
    reason = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    # Vertretung
    substitute_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True
    )

    # Workflow
    status = Column(String(30), default=LeaveRequestStatus.DRAFT.value)

    submitted_at = Column(DateTime(timezone=True), nullable=True)

    reviewed_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_comment = Column(Text, nullable=True)

    approved_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    rejected_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)

    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company")
    employee = relationship("Employee", back_populates="leave_requests", foreign_keys=[employee_id])
    substitute = relationship("Employee", foreign_keys=[substitute_id])

    __table_args__ = (
        Index("ix_leave_requests_company_id", "company_id"),
        Index("ix_leave_requests_employee_id", "employee_id"),
        Index("ix_leave_requests_status", "status"),
        Index("ix_leave_requests_dates", "start_date", "end_date"),
        Index("ix_leave_requests_leave_type", "leave_type"),
    )

    def __repr__(self) -> str:
        return f"<LeaveRequest {self.leave_type} {self.start_date} - {self.end_date}>"


class Absence(Base):
    """Tatsaechliche Abwesenheit (aus genehmigtem Antrag oder Krankheit).

    Wird automatisch aus genehmigten LeaveRequests erzeugt oder
    manuell fuer Krankheitsfaelle angelegt.
    """

    __tablename__ = "absences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )
    employee_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False
    )

    absence_type = Column(String(30), nullable=False)  # LeaveType
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    total_days = Column(Numeric(5, 2), nullable=False)

    # Verknuepfung zum Urlaubsantrag (optional)
    leave_request_id = Column(
        UUID(as_uuid=True),
        ForeignKey("leave_requests.id", ondelete="SET NULL"),
        nullable=True
    )

    # Bei Krankheit
    sick_note_received = Column(Boolean, default=False)
    sick_note_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True
    )
    sick_note_valid_from = Column(Date, nullable=True)
    sick_note_valid_until = Column(Date, nullable=True)

    notes = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    company = relationship("Company")
    employee = relationship("Employee", back_populates="absences")
    leave_request = relationship("LeaveRequest")
    sick_note_document = relationship("Document")

    __table_args__ = (
        Index("ix_absences_company_id", "company_id"),
        Index("ix_absences_employee_id", "employee_id"),
        Index("ix_absences_dates", "start_date", "end_date"),
        Index("ix_absences_type", "absence_type"),
        Index("ix_absences_leave_request_id", "leave_request_id"),
    )

    def __repr__(self) -> str:
        return f"<Absence {self.absence_type} {self.start_date} - {self.end_date}>"


class TimeEntry(Base):
    """Zeiterfassung.

    Erfasst Arbeitszeiten eines Mitarbeiters mit optionaler
    Genehmigung durch den Vorgesetzten.
    """

    __tablename__ = "time_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )
    employee_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False
    )

    date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)
    break_duration_minutes = Column(Integer, default=0)

    # Berechnete Werte
    total_hours = Column(Numeric(5, 2), nullable=True)
    overtime_hours = Column(Numeric(5, 2), default=0)

    # Kategorisierung
    work_type = Column(String(50), default="regular")  # regular, overtime, holiday, on_call
    project_id = Column(String(100), nullable=True)
    cost_center = Column(String(50), nullable=True)

    notes = Column(Text, nullable=True)

    # Status
    is_approved = Column(Boolean, default=False)
    approved_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company")
    employee = relationship("Employee", back_populates="time_entries")

    __table_args__ = (
        Index("ix_time_entries_company_id", "company_id"),
        Index("ix_time_entries_employee_id", "employee_id"),
        Index("ix_time_entries_date", "date"),
        Index("ix_time_entries_employee_date", "employee_id", "date"),
        Index("ix_time_entries_is_approved", "is_approved"),
    )

    def __repr__(self) -> str:
        return f"<TimeEntry {self.date} {self.total_hours}h>"


class Training(Base):
    """Weiterbildung/Schulung.

    Erfasst Schulungen, Zertifizierungen und Fortbildungen
    eines Mitarbeiters.
    """

    __tablename__ = "trainings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )
    employee_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False
    )

    # Details
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    provider = Column(String(200), nullable=True)
    location = Column(String(200), nullable=True)

    # Zeitraum
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    duration_hours = Column(Numeric(6, 2), nullable=True)

    # Kosten
    cost = Column(Numeric(10, 2), nullable=True)
    cost_currency = Column(String(3), default="EUR")
    cost_covered_by = Column(String(50), default="company")  # company, employee, shared

    # Ergebnis
    status = Column(String(30), default=TrainingStatus.PLANNED.value)
    certificate_received = Column(Boolean, default=False)
    certificate_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True
    )
    certificate_valid_until = Column(Date, nullable=True)

    # Bewertung
    rating = Column(Integer, nullable=True)  # 1-5
    feedback = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    company = relationship("Company")
    employee = relationship("Employee", back_populates="trainings")
    certificate_document = relationship("Document")

    __table_args__ = (
        Index("ix_trainings_company_id", "company_id"),
        Index("ix_trainings_employee_id", "employee_id"),
        Index("ix_trainings_status", "status"),
        Index("ix_trainings_start_date", "start_date"),
    )

    def __repr__(self) -> str:
        return f"<Training {self.title}>"


class PerformanceReview(Base):
    """Mitarbeiterbeurteilung.

    Erfasst Leistungsbeurteilungen mit Ratings, Zielen
    und Entwicklungsplaenen.
    """

    __tablename__ = "performance_reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )
    employee_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False
    )

    # Beurteilungszeitraum
    review_period_start = Column(Date, nullable=False)
    review_period_end = Column(Date, nullable=False)
    review_date = Column(Date, nullable=True)

    # Bewerter
    reviewer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=False
    )

    # Typ
    review_type = Column(String(50), default="annual")  # annual, probation, project, ad_hoc

    # Bewertungen
    overall_rating = Column(Integer, nullable=True)  # 1-5
    ratings = Column(CrossDBJSON, default=dict)  # {"performance": 4, "teamwork": 5, ...}

    # Freitext
    achievements = Column(Text, nullable=True)
    areas_for_improvement = Column(Text, nullable=True)
    development_plan = Column(Text, nullable=True)
    employee_comments = Column(Text, nullable=True)

    # Ziele
    goals_previous_period = Column(CrossDBJSON, default=list)
    goals_next_period = Column(CrossDBJSON, default=list)

    # Workflow
    status = Column(String(30), default=ReviewStatus.DRAFT.value)

    employee_acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    hr_approved_at = Column(DateTime(timezone=True), nullable=True)
    hr_approved_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Dokument
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True
    )

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    company = relationship("Company")
    employee = relationship("Employee", back_populates="performance_reviews", foreign_keys=[employee_id])
    reviewer = relationship("Employee", foreign_keys=[reviewer_id])
    document = relationship("Document")

    __table_args__ = (
        Index("ix_performance_reviews_company_id", "company_id"),
        Index("ix_performance_reviews_employee_id", "employee_id"),
        Index("ix_performance_reviews_reviewer_id", "reviewer_id"),
        Index("ix_performance_reviews_status", "status"),
        Index("ix_performance_reviews_period", "review_period_start", "review_period_end"),
    )

    def __repr__(self) -> str:
        return f"<PerformanceReview {self.review_type} {self.review_period_start}>"


class OnboardingTask(Base):
    """Onboarding-Aufgabe fuer neue Mitarbeiter.

    Definiert Checklisten-Elemente fuer den Onboarding-Prozess.
    """

    __tablename__ = "onboarding_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )
    employee_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False
    )

    # Aufgabe
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), default="general")  # it, hr, department, training, general

    # Zuweisung
    assigned_to_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True
    )
    due_date = Column(Date, nullable=True)

    # Sortierung
    sort_order = Column(Integer, default=0)
    is_mandatory = Column(Boolean, default=True)

    # Status
    status = Column(String(30), default=OnboardingTaskStatus.PENDING.value)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    completed_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company")
    employee = relationship("Employee", back_populates="onboarding_tasks", foreign_keys=[employee_id])
    assigned_to = relationship("Employee", foreign_keys=[assigned_to_id])

    __table_args__ = (
        Index("ix_onboarding_tasks_company_id", "company_id"),
        Index("ix_onboarding_tasks_employee_id", "employee_id"),
        Index("ix_onboarding_tasks_status", "status"),
        Index("ix_onboarding_tasks_category", "category"),
        Index("ix_onboarding_tasks_due_date", "due_date"),
    )

    def __repr__(self) -> str:
        return f"<OnboardingTask {self.title}>"


class HRDocument(Base):
    """HR-Dokument-Zuordnung mit Kategorien.

    Verknuepft Dokumente mit Mitarbeitern und kategorisiert sie
    nach HR-spezifischen Kategorien.
    """

    __tablename__ = "hr_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False
    )
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False
    )

    # Kategorisierung
    category = Column(String(50), nullable=False)  # HRDocumentCategory
    subcategory = Column(String(50), nullable=True)

    # Metadaten
    valid_from = Column(Date, nullable=True)
    valid_until = Column(Date, nullable=True)
    is_current = Column(Boolean, default=True)

    # Beschreibung
    title = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    employee = relationship("Employee", back_populates="hr_documents")
    document = relationship("Document")

    __table_args__ = (
        Index("ix_hr_documents_employee_id", "employee_id"),
        Index("ix_hr_documents_document_id", "document_id"),
        Index("ix_hr_documents_category", "category"),
        Index("ix_hr_documents_employee_category", "employee_id", "category"),
        Index("ix_hr_documents_is_current", "is_current"),
    )
