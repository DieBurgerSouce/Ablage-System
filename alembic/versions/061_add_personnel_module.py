"""Add Personal-Modul tables (Enterprise HR).

Revision ID: 061_add_personnel_module
Revises: 060_add_rls_policies
Create Date: 2024-12-30

Personal-Modul fuer Ablage-System:
- departments: Abteilungen mit hierarchischer Struktur
- positions: Stellen/Rollen mit Gehaltsrahmen
- employees: Mitarbeiter-Stammdaten
- employment_contracts: Arbeitsvertraege mit Versionierung
- leave_requests: Urlaubsantraege mit Workflow
- absences: Tatsaechliche Abwesenheiten
- time_entries: Zeiterfassung
- trainings: Weiterbildungen/Schulungen
- performance_reviews: Mitarbeiterbeurteilungen
- onboarding_tasks: Onboarding-Checklisten
- hr_documents: HR-Dokument-Zuordnungen

GDPR/GoBD-Compliance:
- Soft-Delete mit deleted_at fuer alle sensitiven Daten
- Audit-Trail mit created_by_id, created_at, updated_at
- Workflow-Status mit Timestamps fuer Nachvollziehbarkeit
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '061_add_personnel_module'
down_revision = '060_add_rls_policies'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add Personal-Modul tables."""

    # Check dialect for cross-database compatibility
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        uuid_type = postgresql.UUID(as_uuid=True)
        json_type = postgresql.JSONB
    else:
        uuid_type = sa.String(36)
        json_type = sa.JSON

    # =========================================================================
    # 1. DEPARTMENTS - Abteilungen
    # =========================================================================
    op.create_table(
        "departments",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("company_id", uuid_type, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_id", uuid_type, sa.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True),

        # Identifikation
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("short_name", sa.String(20), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("cost_center", sa.String(50), nullable=True),

        # Manager (FK zu employees wird spaeter hinzugefuegt)
        sa.Column("manager_id", uuid_type, nullable=True),

        # Sortierung
        sa.Column("sort_order", sa.Integer, default=0),

        # Status
        sa.Column("is_active", sa.Boolean, default=True),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("created_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index("ix_departments_company_id", "departments", ["company_id"])
    op.create_index("ix_departments_parent_id", "departments", ["parent_id"])
    op.create_index("ix_departments_is_active", "departments", ["is_active"])
    op.create_index("ix_departments_deleted_at", "departments", ["deleted_at"])
    op.create_index("ix_departments_company_name", "departments", ["company_id", "name"])

    # =========================================================================
    # 2. POSITIONS - Stellen/Rollen
    # =========================================================================
    op.create_table(
        "positions",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("company_id", uuid_type, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("department_id", uuid_type, sa.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True),

        # Bezeichnung
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("title_en", sa.String(200), nullable=True),
        sa.Column("description", sa.Text, nullable=True),

        # Klassifizierung
        sa.Column("level", sa.Integer, default=1),
        sa.Column("job_family", sa.String(100), nullable=True),

        # Gehaltsrahmen
        sa.Column("salary_band_min", sa.Numeric(10, 2), nullable=True),
        sa.Column("salary_band_max", sa.Numeric(10, 2), nullable=True),

        # Status
        sa.Column("is_active", sa.Boolean, default=True),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index("ix_positions_company_id", "positions", ["company_id"])
    op.create_index("ix_positions_department_id", "positions", ["department_id"])
    op.create_index("ix_positions_is_active", "positions", ["is_active"])
    op.create_index("ix_positions_title", "positions", ["title"])

    # =========================================================================
    # 3. EMPLOYEES - Mitarbeiter-Stammdaten
    # =========================================================================
    op.create_table(
        "employees",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("company_id", uuid_type, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),

        # Identifikation
        sa.Column("employee_number", sa.String(50), nullable=False),

        # Persoenliche Daten
        sa.Column("salutation", sa.String(20), nullable=True),
        sa.Column("title", sa.String(50), nullable=True),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("birth_name", sa.String(100), nullable=True),
        sa.Column("date_of_birth", sa.Date, nullable=True),
        sa.Column("place_of_birth", sa.String(100), nullable=True),
        sa.Column("nationality", sa.String(50), nullable=True),
        sa.Column("gender", sa.String(20), nullable=True),

        # Kontakt (geschaeftlich)
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("mobile", sa.String(50), nullable=True),

        # Kontakt (privat)
        sa.Column("private_email", sa.String(255), nullable=True),
        sa.Column("private_phone", sa.String(50), nullable=True),

        # Adresse (privat)
        sa.Column("street", sa.String(255), nullable=True),
        sa.Column("street_number", sa.String(20), nullable=True),
        sa.Column("postal_code", sa.String(10), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("country", sa.String(2), default="DE"),

        # Notfall-Kontakt
        sa.Column("emergency_contact_name", sa.String(200), nullable=True),
        sa.Column("emergency_contact_phone", sa.String(50), nullable=True),
        sa.Column("emergency_contact_relation", sa.String(50), nullable=True),

        # Organisatorisch
        sa.Column("department_id", uuid_type, sa.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("position_id", uuid_type, sa.ForeignKey("positions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("supervisor_id", uuid_type, sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),

        # Beschaeftigung
        sa.Column("employment_type", sa.String(30), default="full_time"),
        sa.Column("status", sa.String(30), default="active"),
        sa.Column("hire_date", sa.Date, nullable=True),
        sa.Column("probation_end_date", sa.Date, nullable=True),
        sa.Column("termination_date", sa.Date, nullable=True),

        # Arbeitszeit
        sa.Column("weekly_hours", sa.Numeric(5, 2), default=40),
        sa.Column("vacation_days_per_year", sa.Integer, default=30),

        # Steuer & Sozialversicherung
        sa.Column("tax_id", sa.String(20), nullable=True),
        sa.Column("tax_class", sa.String(5), nullable=True),
        sa.Column("social_security_number", sa.String(20), nullable=True),
        sa.Column("health_insurance", sa.String(100), nullable=True),
        sa.Column("health_insurance_number", sa.String(50), nullable=True),

        # Banking
        sa.Column("iban", sa.String(34), nullable=True),
        sa.Column("bic", sa.String(11), nullable=True),
        sa.Column("bank_name", sa.String(100), nullable=True),

        # Profilbild
        sa.Column("photo_path", sa.String(500), nullable=True),

        # Flexible Felder
        sa.Column("custom_fields", json_type, default=dict),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("created_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),

        # Soft-Delete (GDPR/GoBD)
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )

    op.create_index("ix_employees_company_id", "employees", ["company_id"])
    op.create_index("ix_employees_user_id", "employees", ["user_id"])
    op.create_index("ix_employees_department_id", "employees", ["department_id"])
    op.create_index("ix_employees_position_id", "employees", ["position_id"])
    op.create_index("ix_employees_supervisor_id", "employees", ["supervisor_id"])
    op.create_index("ix_employees_status", "employees", ["status"])
    op.create_index("ix_employees_employee_number", "employees", ["company_id", "employee_number"])
    op.create_index("ix_employees_email", "employees", ["email"])
    op.create_index("ix_employees_deleted_at", "employees", ["deleted_at"])
    op.create_index("ix_employees_name", "employees", ["last_name", "first_name"])

    # =========================================================================
    # 4. EMPLOYMENT_CONTRACTS - Arbeitsvertraege
    # =========================================================================
    op.create_table(
        "employment_contracts",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("employee_id", uuid_type, sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),

        # Versionierung
        sa.Column("version", sa.Integer, default=1),
        sa.Column("is_current", sa.Boolean, default=True),
        sa.Column("supersedes_id", uuid_type, sa.ForeignKey("employment_contracts.id", ondelete="SET NULL"), nullable=True),

        # Vertragsdetails
        sa.Column("contract_type", sa.String(30), nullable=False),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=True),

        # Position
        sa.Column("position_id", uuid_type, sa.ForeignKey("positions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("job_title", sa.String(200), nullable=False),
        sa.Column("job_description", sa.Text, nullable=True),

        # Arbeitszeit
        sa.Column("weekly_hours", sa.Numeric(5, 2), nullable=False),
        sa.Column("vacation_days", sa.Integer, nullable=False),

        # Verguetung
        sa.Column("salary_type", sa.String(20), default="monthly"),
        sa.Column("base_salary", sa.Numeric(10, 2), nullable=False),
        sa.Column("salary_currency", sa.String(3), default="EUR"),
        sa.Column("bonus_eligible", sa.Boolean, default=False),
        sa.Column("bonus_target", sa.Numeric(10, 2), nullable=True),

        # Zusatzleistungen
        sa.Column("benefits", json_type, default=list),

        # Kuendigung
        sa.Column("notice_period_employee", sa.String(50), nullable=True),
        sa.Column("notice_period_employer", sa.String(50), nullable=True),

        # Dokument-Referenz
        sa.Column("contract_document_id", uuid_type, sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),

        # Workflow
        sa.Column("status", sa.String(30), default="draft"),
        sa.Column("signed_date", sa.Date, nullable=True),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("created_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )

    op.create_index("ix_employment_contracts_employee_id", "employment_contracts", ["employee_id"])
    op.create_index("ix_employment_contracts_is_current", "employment_contracts", ["is_current"])
    op.create_index("ix_employment_contracts_status", "employment_contracts", ["status"])
    op.create_index("ix_employment_contracts_start_date", "employment_contracts", ["start_date"])

    # =========================================================================
    # 5. LEAVE_REQUESTS - Urlaubsantraege
    # =========================================================================
    op.create_table(
        "leave_requests",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("company_id", uuid_type, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employee_id", uuid_type, sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),

        # Zeitraum
        sa.Column("leave_type", sa.String(30), nullable=False),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("start_half_day", sa.Boolean, default=False),
        sa.Column("end_half_day", sa.Boolean, default=False),

        # Berechnung
        sa.Column("total_days", sa.Numeric(5, 2), nullable=False),

        # Beschreibung
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),

        # Vertretung
        sa.Column("substitute_id", uuid_type, sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),

        # Workflow
        sa.Column("status", sa.String(30), default="draft"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),

        sa.Column("reviewed_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_comment", sa.Text, nullable=True),

        sa.Column("approved_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),

        sa.Column("rejected_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text, nullable=True),

        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    op.create_index("ix_leave_requests_company_id", "leave_requests", ["company_id"])
    op.create_index("ix_leave_requests_employee_id", "leave_requests", ["employee_id"])
    op.create_index("ix_leave_requests_status", "leave_requests", ["status"])
    op.create_index("ix_leave_requests_dates", "leave_requests", ["start_date", "end_date"])
    op.create_index("ix_leave_requests_leave_type", "leave_requests", ["leave_type"])

    # =========================================================================
    # 6. ABSENCES - Tatsaechliche Abwesenheiten
    # =========================================================================
    op.create_table(
        "absences",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("company_id", uuid_type, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employee_id", uuid_type, sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),

        sa.Column("absence_type", sa.String(30), nullable=False),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("total_days", sa.Numeric(5, 2), nullable=False),

        # Verknuepfung zum Urlaubsantrag
        sa.Column("leave_request_id", uuid_type, sa.ForeignKey("leave_requests.id", ondelete="SET NULL"), nullable=True),

        # Bei Krankheit
        sa.Column("sick_note_received", sa.Boolean, default=False),
        sa.Column("sick_note_document_id", uuid_type, sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sick_note_valid_from", sa.Date, nullable=True),
        sa.Column("sick_note_valid_until", sa.Date, nullable=True),

        sa.Column("notes", sa.Text, nullable=True),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("created_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )

    op.create_index("ix_absences_company_id", "absences", ["company_id"])
    op.create_index("ix_absences_employee_id", "absences", ["employee_id"])
    op.create_index("ix_absences_dates", "absences", ["start_date", "end_date"])
    op.create_index("ix_absences_type", "absences", ["absence_type"])
    op.create_index("ix_absences_leave_request_id", "absences", ["leave_request_id"])

    # =========================================================================
    # 7. TIME_ENTRIES - Zeiterfassung
    # =========================================================================
    op.create_table(
        "time_entries",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("company_id", uuid_type, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employee_id", uuid_type, sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),

        sa.Column("date", sa.Date, nullable=False),
        sa.Column("start_time", sa.Time, nullable=True),
        sa.Column("end_time", sa.Time, nullable=True),
        sa.Column("break_duration_minutes", sa.Integer, default=0),

        # Berechnete Werte
        sa.Column("total_hours", sa.Numeric(5, 2), nullable=True),
        sa.Column("overtime_hours", sa.Numeric(5, 2), default=0),

        # Kategorisierung
        sa.Column("work_type", sa.String(50), default="regular"),
        sa.Column("project_id", sa.String(100), nullable=True),
        sa.Column("cost_center", sa.String(50), nullable=True),

        sa.Column("notes", sa.Text, nullable=True),

        # Status
        sa.Column("is_approved", sa.Boolean, default=False),
        sa.Column("approved_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    op.create_index("ix_time_entries_company_id", "time_entries", ["company_id"])
    op.create_index("ix_time_entries_employee_id", "time_entries", ["employee_id"])
    op.create_index("ix_time_entries_date", "time_entries", ["date"])
    op.create_index("ix_time_entries_employee_date", "time_entries", ["employee_id", "date"])
    op.create_index("ix_time_entries_is_approved", "time_entries", ["is_approved"])

    # =========================================================================
    # 8. TRAININGS - Weiterbildungen
    # =========================================================================
    op.create_table(
        "trainings",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("company_id", uuid_type, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employee_id", uuid_type, sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),

        # Details
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("provider", sa.String(200), nullable=True),
        sa.Column("location", sa.String(200), nullable=True),

        # Zeitraum
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=True),
        sa.Column("duration_hours", sa.Numeric(6, 2), nullable=True),

        # Kosten
        sa.Column("cost", sa.Numeric(10, 2), nullable=True),
        sa.Column("cost_currency", sa.String(3), default="EUR"),
        sa.Column("cost_covered_by", sa.String(50), default="company"),

        # Ergebnis
        sa.Column("status", sa.String(30), default="planned"),
        sa.Column("certificate_received", sa.Boolean, default=False),
        sa.Column("certificate_document_id", uuid_type, sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("certificate_valid_until", sa.Date, nullable=True),

        # Bewertung
        sa.Column("rating", sa.Integer, nullable=True),
        sa.Column("feedback", sa.Text, nullable=True),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("created_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )

    op.create_index("ix_trainings_company_id", "trainings", ["company_id"])
    op.create_index("ix_trainings_employee_id", "trainings", ["employee_id"])
    op.create_index("ix_trainings_status", "trainings", ["status"])
    op.create_index("ix_trainings_start_date", "trainings", ["start_date"])

    # =========================================================================
    # 9. PERFORMANCE_REVIEWS - Mitarbeiterbeurteilungen
    # =========================================================================
    op.create_table(
        "performance_reviews",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("company_id", uuid_type, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employee_id", uuid_type, sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),

        # Beurteilungszeitraum
        sa.Column("review_period_start", sa.Date, nullable=False),
        sa.Column("review_period_end", sa.Date, nullable=False),
        sa.Column("review_date", sa.Date, nullable=True),

        # Bewerter
        sa.Column("reviewer_id", uuid_type, sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=False),

        # Typ
        sa.Column("review_type", sa.String(50), default="annual"),

        # Bewertungen
        sa.Column("overall_rating", sa.Integer, nullable=True),
        sa.Column("ratings", json_type, default=dict),

        # Freitext
        sa.Column("achievements", sa.Text, nullable=True),
        sa.Column("areas_for_improvement", sa.Text, nullable=True),
        sa.Column("development_plan", sa.Text, nullable=True),
        sa.Column("employee_comments", sa.Text, nullable=True),

        # Ziele
        sa.Column("goals_previous_period", json_type, default=list),
        sa.Column("goals_next_period", json_type, default=list),

        # Workflow
        sa.Column("status", sa.String(30), default="draft"),
        sa.Column("employee_acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hr_approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hr_approved_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),

        # Dokument
        sa.Column("document_id", uuid_type, sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("created_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )

    op.create_index("ix_performance_reviews_company_id", "performance_reviews", ["company_id"])
    op.create_index("ix_performance_reviews_employee_id", "performance_reviews", ["employee_id"])
    op.create_index("ix_performance_reviews_reviewer_id", "performance_reviews", ["reviewer_id"])
    op.create_index("ix_performance_reviews_status", "performance_reviews", ["status"])
    op.create_index("ix_performance_reviews_period", "performance_reviews", ["review_period_start", "review_period_end"])

    # =========================================================================
    # 10. ONBOARDING_TASKS - Onboarding-Checkliste
    # =========================================================================
    op.create_table(
        "onboarding_tasks",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("company_id", uuid_type, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employee_id", uuid_type, sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),

        # Aufgabe
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("category", sa.String(50), default="general"),

        # Zuweisung
        sa.Column("assigned_to_id", uuid_type, sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("due_date", sa.Date, nullable=True),

        # Sortierung
        sa.Column("sort_order", sa.Integer, default=0),
        sa.Column("is_mandatory", sa.Boolean, default=True),

        # Status
        sa.Column("status", sa.String(30), default="pending"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    op.create_index("ix_onboarding_tasks_company_id", "onboarding_tasks", ["company_id"])
    op.create_index("ix_onboarding_tasks_employee_id", "onboarding_tasks", ["employee_id"])
    op.create_index("ix_onboarding_tasks_status", "onboarding_tasks", ["status"])
    op.create_index("ix_onboarding_tasks_category", "onboarding_tasks", ["category"])
    op.create_index("ix_onboarding_tasks_due_date", "onboarding_tasks", ["due_date"])

    # =========================================================================
    # 11. HR_DOCUMENTS - HR-Dokument-Zuordnung
    # =========================================================================
    op.create_table(
        "hr_documents",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("employee_id", uuid_type, sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", uuid_type, sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),

        # Kategorisierung
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("subcategory", sa.String(50), nullable=True),

        # Metadaten
        sa.Column("valid_from", sa.Date, nullable=True),
        sa.Column("valid_until", sa.Date, nullable=True),
        sa.Column("is_current", sa.Boolean, default=True),

        # Beschreibung
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )

    op.create_index("ix_hr_documents_employee_id", "hr_documents", ["employee_id"])
    op.create_index("ix_hr_documents_document_id", "hr_documents", ["document_id"])
    op.create_index("ix_hr_documents_category", "hr_documents", ["category"])
    op.create_index("ix_hr_documents_employee_category", "hr_documents", ["employee_id", "category"])
    op.create_index("ix_hr_documents_is_current", "hr_documents", ["is_current"])


def downgrade() -> None:
    """Remove Personal-Modul tables."""
    op.drop_table("hr_documents")
    op.drop_table("onboarding_tasks")
    op.drop_table("performance_reviews")
    op.drop_table("trainings")
    op.drop_table("time_entries")
    op.drop_table("absences")
    op.drop_table("leave_requests")
    op.drop_table("employment_contracts")
    op.drop_table("employees")
    op.drop_table("positions")
    op.drop_table("departments")
