# Kasse-Modul: Vollständige Implementierungsspezifikation

> **Status**: Ready for Implementation  
> **Version**: 1.0.0  
> **Erstellt**: 2024-12-29  
> **Priorität**: Hoch (Core Business Feature)  
> **Geschätzter Aufwand**: 8-12 Implementierungstage

---

## Executive Summary

Das Kasse-Modul digitalisiert die vollständige Bargeldverwaltung für deutsche KMUs:

- **Kassenbuchführung** nach GoBD (§146 AO) mit täglicher Erfassung und Unveränderbarkeit
- **Spesenabrechnung** mit Bewirtungskosten-Dokumentation (70% Abzug)
- **Multi-Company Support** mit PostgreSQL Row-Level Security
- **OCR-Integration** zur automatischen Belegerkennung
- **Banking-Integration** für Kassenentnahmen/-einlagen
- **DATEV-Export** für Steuerberater

---

## PHASE 0: Rechtliche Grundlagen (READ FIRST!)

### GoBD-Compliance (§146 AO)

```
PFLICHT: Tägliche Erfassung aller Kasseneinnahmen/-ausgaben
PFLICHT: Unveränderbarkeit der Einträge (APPEND-ONLY!)
PFLICHT: Kassensturz-Fähigkeit (Ist = Soll jederzeit prüfbar)
PFLICHT: Chronologische, lückenlose Nummerierung
PFLICHT: Verfahrensdokumentation
VERBOTEN: Excel als Kassenbuch!
```

### Aufbewahrungsfristen (§147 AO, NEU ab 2025)

```
8 Jahre: Kassenbelege, Quittungen, Rechnungen (verkürzt von 10!)
10 Jahre: Kassenbuch selbst, Jahresabschlüsse
6 Jahre: Geschäftsbriefe
```

### Bewirtungskosten (§4 Abs. 5 Nr. 2 EStG)

```
70% abzugsfähig als Betriebsausgabe
100% Vorsteuerabzug möglich
PFLICHT: Ort, Datum, Teilnehmer (NAMENTLICH!), konkreter Anlass
PFLICHT: Bei >250€ brutto: Name des Bewirtenden auf Rechnung
UNGÜLTIG: "Geschäftsessen", "Kundenpflege" (zu unkonkret!)
GÜLTIG: "Abstimmung Lieferbedingungen Projekt ABC"
```

### Verpflegungspauschalen 2024/2025

```
>8 Stunden: 14€
24 Stunden: 28€
An-/Abreisetag: 14€
Kürzung Frühstück: 5,60€ (20%)
Kürzung Mittag/Abend: je 11,20€ (40%)
Dreimonatsfrist beachten!
Kilometerpauschale: 0,30€/km (ab 21. km: 0,38€)
```

### SKR03/SKR04 Konten

| Kategorie | SKR03 | SKR04 |
|-----------|-------|-------|
| Kasse | 1000 | 1600 |
| Bewirtung (70% abzugsfähig) | 4650 | 6640 |
| Bewirtung (30% n. abzugsfähig) | 4654 | 6644 |
| Reisekosten Verpflegung | 4664 | 6664 |
| Reisekosten Übernachtung | 4666 | 6680 |
| Reisekosten Fahrtkosten | 4673 | 6673 |
| Bürobedarf | 4930 | 6815 |
| Porto | 4910 | 6800 |
| Tankkosten | 4530 | 6530 |
| Parkgebühren | 4676 | 6676 |
| Geschenke ≤50€ | 4630 | 6610 |
| Geschenke >50€ | 4635 | 6620 |
| Kassendifferenz + | 2709 | 4839 |
| Kassendifferenz - | 2309 | 6969 |

---

## PHASE 1: Multi-Company Architektur

### 1.1 Neue Tabelle: Company (ersetzt CompanySettings-Singleton)

**Datei: `alembic/versions/XXXX_add_multi_company_support.py`**

```python
"""Add multi-company support for Kasse module

Revision ID: XXXX
Revises: [previous]
Create Date: 2024-12-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade() -> None:
    # Company Table (Multi-Tenant Root)
    op.create_table(
        'companies',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, 
                  server_default=sa.text('gen_random_uuid()')),
        
        # Identifikation
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('short_name', sa.String(50)),
        sa.Column('display_name', sa.String(255)),
        
        # Rechtsform & Register
        sa.Column('legal_form', sa.String(50)),  # GmbH, UG, AG, etc.
        sa.Column('commercial_register', sa.String(100)),
        sa.Column('court', sa.String(100)),
        
        # Steuer
        sa.Column('vat_id', sa.String(20), unique=True),  # DE123456789
        sa.Column('tax_number', sa.String(50)),
        
        # Adresse
        sa.Column('street', sa.String(255)),
        sa.Column('street_number', sa.String(20)),
        sa.Column('postal_code', sa.String(10)),
        sa.Column('city', sa.String(100)),
        sa.Column('country', sa.String(2), server_default='DE'),
        
        # Kontakt
        sa.Column('email', sa.String(255)),
        sa.Column('phone', sa.String(50)),
        sa.Column('website', sa.String(255)),
        
        # Banking (Hauptkonto)
        sa.Column('iban', sa.String(34)),
        sa.Column('bic', sa.String(11)),
        sa.Column('bank_name', sa.String(100)),
        
        # Alternative Namen für OCR-Erkennung
        sa.Column('alternative_names', postgresql.JSONB, server_default='[]'),
        
        # Einstellungen
        sa.Column('default_currency', sa.String(3), server_default='EUR'),
        sa.Column('fiscal_year_start', sa.Integer, server_default='1'),
        sa.Column('kontenrahmen', sa.String(10), server_default='SKR03'),
        
        # Status
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('is_default', sa.Boolean, server_default='false'),
        
        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), 
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), 
                  server_default=sa.text('NOW()')),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('deleted_at', sa.DateTime(timezone=True)),
    )
    
    op.create_index('ix_companies_vat_id', 'companies', ['vat_id'])
    op.create_index('ix_companies_is_active', 'companies', ['is_active'])
    
    # User-Company Zuordnung
    op.create_table(
        'user_companies',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), 
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        
        # Rolle & Berechtigungen
        sa.Column('role', sa.String(50), server_default='member'),
        sa.Column('can_manage_cash', sa.Boolean, server_default='false'),
        sa.Column('can_approve_expenses', sa.Boolean, server_default='false'),
        sa.Column('can_export_datev', sa.Boolean, server_default='false'),
        sa.Column('can_manage_settings', sa.Boolean, server_default='false'),
        
        # Aktive Firma für Session
        sa.Column('is_current', sa.Boolean, server_default='false'),
        
        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()')),
        
        sa.UniqueConstraint('user_id', 'company_id'),
    )
    
    op.create_index('ix_user_companies_user', 'user_companies', ['user_id'])
    op.create_index('ix_user_companies_company', 'user_companies', ['company_id'])
    
    # Migration: CompanySettings -> Company
    op.execute("""
        INSERT INTO companies (name, vat_id, tax_number, street, postal_code, 
                               city, country, email, phone, website, iban, bic,
                               commercial_register, court, alternative_names, is_default)
        SELECT company_name, vat_id, tax_number, street, postal_code,
               city, country, email, phone, website, iban, bic,
               commercial_register, court, alternative_names, true
        FROM company_settings
        LIMIT 1
    """)
    
    # Enable RLS
    op.execute("ALTER TABLE companies ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE user_companies ENABLE ROW LEVEL SECURITY")
```

### 1.2 SQLAlchemy Models

**Datei: `app/db/models/company.py`**

```python
"""Multi-Company Models für Kasse-Modul."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, String, Text,
    UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models import User


class Company(Base):
    """Firma/Mandant für Multi-Company Support.
    
    Ersetzt das bisherige CompanySettings-Singleton und ermöglicht
    die Verwaltung mehrerer Firmen pro Installation.
    """
    
    __tablename__ = "companies"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    # Identifikation
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    short_name: Mapped[Optional[str]] = mapped_column(String(50))
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Rechtsform & Register
    legal_form: Mapped[Optional[str]] = mapped_column(String(50))
    commercial_register: Mapped[Optional[str]] = mapped_column(String(100))
    court: Mapped[Optional[str]] = mapped_column(String(100))
    
    # Steuer
    vat_id: Mapped[Optional[str]] = mapped_column(String(20), unique=True)
    tax_number: Mapped[Optional[str]] = mapped_column(String(50))
    
    # Adresse
    street: Mapped[Optional[str]] = mapped_column(String(255))
    street_number: Mapped[Optional[str]] = mapped_column(String(20))
    postal_code: Mapped[Optional[str]] = mapped_column(String(10))
    city: Mapped[Optional[str]] = mapped_column(String(100))
    country: Mapped[str] = mapped_column(String(2), default="DE")
    
    # Kontakt
    email: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    website: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Banking
    iban: Mapped[Optional[str]] = mapped_column(String(34))
    bic: Mapped[Optional[str]] = mapped_column(String(11))
    bank_name: Mapped[Optional[str]] = mapped_column(String(100))
    
    # OCR-Erkennung
    alternative_names: Mapped[list] = mapped_column(JSONB, default=list)
    
    # Einstellungen
    default_currency: Mapped[str] = mapped_column(String(3), default="EUR")
    fiscal_year_start: Mapped[int] = mapped_column(Integer, default=1)
    kontenrahmen: Mapped[str] = mapped_column(String(10), default="SKR03")
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Relationships
    user_associations: Mapped[list["UserCompany"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    cash_registers: Mapped[list["CashRegister"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<Company {self.name} ({self.id})>"


class UserCompany(Base):
    """Zuordnung User <-> Company mit Berechtigungen."""
    
    __tablename__ = "user_companies"
    __table_args__ = (
        UniqueConstraint("user_id", "company_id"),
        Index("ix_user_companies_user", "user_id"),
        Index("ix_user_companies_company", "company_id"),
    )
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    
    # Rolle
    role: Mapped[str] = mapped_column(String(50), default="member")
    
    # Granulare Berechtigungen
    can_manage_cash: Mapped[bool] = mapped_column(Boolean, default=False)
    can_approve_expenses: Mapped[bool] = mapped_column(Boolean, default=False)
    can_export_datev: Mapped[bool] = mapped_column(Boolean, default=False)
    can_manage_settings: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Aktive Firma
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    
    # Relationships
    user: Mapped["User"] = relationship(back_populates="company_associations")
    company: Mapped["Company"] = relationship(back_populates="user_associations")
```

### 1.3 Company Context Middleware

**Datei: `app/middleware/company_context.py`**

```python
"""Middleware für Multi-Company Context."""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Optional

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import text

from app.db.session import AsyncSessionLocal

# Context Variable für aktuelle Company
current_company_id: ContextVar[Optional[uuid.UUID]] = ContextVar(
    "current_company_id", default=None
)


class CompanyContextMiddleware(BaseHTTPMiddleware):
    """Setzt Company-Context für Row-Level Security."""
    
    async def dispatch(self, request: Request, call_next):
        # Company aus Header oder Session
        company_id = request.headers.get("X-Company-ID")
        
        if company_id:
            try:
                company_uuid = uuid.UUID(company_id)
                current_company_id.set(company_uuid)
                
                # PostgreSQL Session Variable setzen
                async with AsyncSessionLocal() as session:
                    await session.execute(
                        text(f"SET app.current_company = '{company_uuid}'")
                    )
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Ungültige Firmen-ID im Header"
                )
        
        response = await call_next(request)
        return response


def get_current_company_id() -> Optional[uuid.UUID]:
    """Gibt aktuelle Company-ID aus Context zurück."""
    return current_company_id.get()


def require_company() -> uuid.UUID:
    """Gibt Company-ID zurück oder wirft Exception."""
    company_id = current_company_id.get()
    if not company_id:
        raise HTTPException(
            status_code=400,
            detail="Keine Firma ausgewählt. Bitte X-Company-ID Header setzen."
        )
    return company_id
```

---

## PHASE 2: Kassenbuch (Core)

### 2.1 Enums & Types

**Datei: `app/db/models/cash_enums.py`**

```python
"""Enums für Kasse-Modul."""

from enum import Enum


class CashEntryType(str, Enum):
    """Typ der Kassenbuchung."""
    
    # Einnahmen
    INCOME = "income"                    # Allgemeine Einnahme
    DEPOSIT = "deposit"                  # Kasseneinlage von Bank
    REFUND_RECEIVED = "refund_received"  # Erstattung erhalten
    
    # Ausgaben
    EXPENSE = "expense"                  # Allgemeine Ausgabe
    WITHDRAWAL = "withdrawal"            # Kassenentnahme zur Bank
    ENTERTAINMENT = "entertainment"      # Bewirtungskosten
    TRAVEL = "travel"                    # Reisekosten
    OFFICE = "office"                    # Bürobedarf
    FUEL = "fuel"                        # Tankkosten
    PARKING = "parking"                  # Parkgebühren
    POSTAGE = "postage"                  # Porto
    TIPS = "tips"                        # Trinkgeld
    GIFTS = "gifts"                      # Geschenke
    
    # Sonder
    DIFFERENCE_PLUS = "difference_plus"   # Kassenmehrbestand
    DIFFERENCE_MINUS = "difference_minus" # Kassenfehlbestand
    CANCELLATION = "cancellation"         # Stornobuchung
    OPENING = "opening"                   # Eröffnungsbuchung


class ExpenseReportStatus(str, Enum):
    """Status einer Spesenabrechnung."""
    
    DRAFT = "draft"           # Entwurf
    SUBMITTED = "submitted"   # Eingereicht
    IN_REVIEW = "in_review"   # In Prüfung
    APPROVED = "approved"     # Genehmigt
    REJECTED = "rejected"     # Abgelehnt
    PAID = "paid"             # Ausgezahlt


class ExpenseType(str, Enum):
    """Typ einer Spesenposition."""
    
    RECEIPT = "receipt"       # Belegausgabe
    MILEAGE = "mileage"       # Kilometergeld
    PER_DIEM = "per_diem"     # Verpflegungspauschale
    FLAT_RATE = "flat_rate"   # Sonstige Pauschale
```

### 2.2 Kassenbuch Models

**Datei: `app/db/models/cash.py`**

```python
"""Kassenbuch Models - GoBD-konform mit APPEND-ONLY Entries."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, 
    Integer, Numeric, String, Text, Time, UniqueConstraint, Index,
    Computed
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.cash_enums import CashEntryType, ExpenseReportStatus, ExpenseType

if TYPE_CHECKING:
    from app.db.models import Company, User, Document, BankAccount, BankTransaction


class CashRegister(Base):
    """Kasse/Bargeldbestand.
    
    Eine Firma kann mehrere Kassen haben (Hauptkasse, Portokasse, etc.).
    """
    
    __tablename__ = "cash_registers"
    __table_args__ = (
        UniqueConstraint("company_id", "name"),
        Index("ix_cash_registers_company", "company_id"),
    )
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )
    
    # Identifikation
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    register_number: Mapped[Optional[str]] = mapped_column(String(50))
    
    # Währung & Limits
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    max_balance: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    warning_threshold: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    
    # Aktueller Stand (denormalisiert)
    current_balance: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), default=Decimal("0.00")
    )
    balance_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_reconciliation_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    
    # Banking-Verknüpfung
    linked_bank_account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bank_accounts.id", ondelete="SET NULL")
    )
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Relationships
    company: Mapped["Company"] = relationship(back_populates="cash_registers")
    entries: Mapped[list["CashEntry"]] = relationship(
        back_populates="cash_register", order_by="CashEntry.entry_number"
    )
    linked_bank_account: Mapped[Optional["BankAccount"]] = relationship()


class CashEntry(Base):
    """Kassenbucheintrag - APPEND-ONLY für GoBD-Compliance!
    
    WICHTIG: Diese Tabelle erlaubt KEINE Updates oder Deletes!
    Stornierungen erfolgen durch Gegenbuchung mit Verweis auf Original.
    """
    
    __tablename__ = "cash_entries"
    __table_args__ = (
        UniqueConstraint("cash_register_id", "fiscal_year", "entry_number"),
        CheckConstraint("amount != 0", name="ck_cash_entries_amount_not_zero"),
        CheckConstraint("entry_date <= CURRENT_DATE", name="ck_cash_entries_no_future"),
        Index("ix_cash_entries_company", "company_id"),
        Index("ix_cash_entries_register", "cash_register_id"),
        Index("ix_cash_entries_date", "entry_date"),
        Index("ix_cash_entries_type", "entry_type"),
        Index("ix_cash_entries_document", "document_id"),
    )
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),  # RESTRICT!
        nullable=False
    )
    cash_register_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cash_registers.id", ondelete="RESTRICT"),  # RESTRICT!
        nullable=False
    )
    
    # Fortlaufende Nummer (pro Kasse/Jahr)
    entry_number: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Buchungsdaten
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    value_date: Mapped[date] = mapped_column(Date, nullable=False)
    
    # Betrag (positiv = Einnahme, negativ = Ausgabe)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    
    # Saldo NACH dieser Buchung (für Kassensturz)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    
    # Kategorisierung
    entry_type: Mapped[CashEntryType] = mapped_column(nullable=False)
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cash_categories.id")
    )
    
    # Steuer
    tax_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    tax_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    net_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    is_tax_deductible: Mapped[bool] = mapped_column(Boolean, default=True)
    deductible_percentage: Mapped[int] = mapped_column(Integer, default=100)
    
    # Beschreibung
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reference_number: Mapped[Optional[str]] = mapped_column(String(100))
    
    # Geschäftspartner
    counterparty_name: Mapped[Optional[str]] = mapped_column(String(255))
    counterparty_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("business_entities.id")
    )
    
    # Verknüpfungen
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id")
    )
    bank_transaction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bank_transactions.id")
    )
    expense_report_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expense_reports.id")
    )
    
    # Storno-Handling (Gegenbuchung statt Löschung!)
    is_cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    cancelled_by_entry_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cash_entries.id")
    )
    cancellation_reason: Mapped[Optional[str]] = mapped_column(Text)
    
    # Bewirtungskosten-Spezifika (JSON)
    entertainment_data: Mapped[Optional[dict]] = mapped_column(JSONB)
    # Schema: {participants: string[], occasion: string, location: string}
    
    # DATEV-Export
    datev_exported_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    datev_export_batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    
    # Buchungskonten
    debit_account: Mapped[Optional[str]] = mapped_column(String(10))
    credit_account: Mapped[Optional[str]] = mapped_column(String(10))
    cost_center: Mapped[Optional[str]] = mapped_column(String(50))
    
    # Audit (UNVERÄNDERBAR!)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    
    # Relationships
    cash_register: Mapped["CashRegister"] = relationship(back_populates="entries")
    category: Mapped[Optional["CashCategory"]] = relationship()
    document: Mapped[Optional["Document"]] = relationship()
    bank_transaction: Mapped[Optional["BankTransaction"]] = relationship()
    cancellation_entry: Mapped[Optional["CashEntry"]] = relationship(
        remote_side=[id]
    )


class CashCategory(Base):
    """Kategorie für Kassenausgaben mit SKR-Kontenzuordnung."""
    
    __tablename__ = "cash_categories"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE")
    )
    # NULL = System-Default Kategorien
    
    # Identifikation
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    name_en: Mapped[Optional[str]] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text)
    icon: Mapped[Optional[str]] = mapped_column(String(50))
    color: Mapped[Optional[str]] = mapped_column(String(7))
    
    # Hierarchie
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cash_categories.id")
    )
    level: Mapped[int] = mapped_column(Integer, default=0)
    path: Mapped[Optional[str]] = mapped_column(String(500))
    
    # Buchhaltung
    skr03_account: Mapped[Optional[str]] = mapped_column(String(10))
    skr04_account: Mapped[Optional[str]] = mapped_column(String(10))
    default_tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("19"))
    
    # Spezielle Typen
    category_type: Mapped[Optional[str]] = mapped_column(String(50))
    is_entertainment: Mapped[bool] = mapped_column(Boolean, default=False)
    is_travel_expense: Mapped[bool] = mapped_column(Boolean, default=False)
    deductible_percentage: Mapped[int] = mapped_column(Integer, default=100)
    
    # Vorsteuer
    allows_vat_deduction: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    
    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )


class CashCount(Base):
    """Zählprotokoll für Kassensturz."""
    
    __tablename__ = "cash_counts"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )
    cash_register_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cash_registers.id", ondelete="CASCADE"),
        nullable=False
    )
    
    # Zeitpunkt
    count_date: Mapped[date] = mapped_column(Date, nullable=False)
    count_time: Mapped[time] = mapped_column(Time, nullable=False)
    
    # Münzen (Stückzahl)
    coins_1_cent: Mapped[int] = mapped_column(Integer, default=0)
    coins_2_cent: Mapped[int] = mapped_column(Integer, default=0)
    coins_5_cent: Mapped[int] = mapped_column(Integer, default=0)
    coins_10_cent: Mapped[int] = mapped_column(Integer, default=0)
    coins_20_cent: Mapped[int] = mapped_column(Integer, default=0)
    coins_50_cent: Mapped[int] = mapped_column(Integer, default=0)
    coins_1_euro: Mapped[int] = mapped_column(Integer, default=0)
    coins_2_euro: Mapped[int] = mapped_column(Integer, default=0)
    
    # Scheine (Stückzahl)
    notes_5_euro: Mapped[int] = mapped_column(Integer, default=0)
    notes_10_euro: Mapped[int] = mapped_column(Integer, default=0)
    notes_20_euro: Mapped[int] = mapped_column(Integer, default=0)
    notes_50_euro: Mapped[int] = mapped_column(Integer, default=0)
    notes_100_euro: Mapped[int] = mapped_column(Integer, default=0)
    notes_200_euro: Mapped[int] = mapped_column(Integer, default=0)
    notes_500_euro: Mapped[int] = mapped_column(Integer, default=0)
    
    # Soll-Bestand (aus Kassenbuch)
    expected_total: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    
    # Bei Differenz
    difference_entry_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cash_entries.id")
    )
    difference_explanation: Mapped[Optional[str]] = mapped_column(Text)
    
    # Signatur
    counted_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    verified_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    notes: Mapped[Optional[str]] = mapped_column(Text)
    
    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    
    @property
    def total_coins(self) -> Decimal:
        """Berechnet Summe aller Münzen."""
        return Decimal(
            self.coins_1_cent * 0.01 +
            self.coins_2_cent * 0.02 +
            self.coins_5_cent * 0.05 +
            self.coins_10_cent * 0.10 +
            self.coins_20_cent * 0.20 +
            self.coins_50_cent * 0.50 +
            self.coins_1_euro * 1.00 +
            self.coins_2_euro * 2.00
        )
    
    @property
    def total_notes(self) -> Decimal:
        """Berechnet Summe aller Scheine."""
        return Decimal(
            self.notes_5_euro * 5 +
            self.notes_10_euro * 10 +
            self.notes_20_euro * 20 +
            self.notes_50_euro * 50 +
            self.notes_100_euro * 100 +
            self.notes_200_euro * 200 +
            self.notes_500_euro * 500
        )
    
    @property
    def counted_total(self) -> Decimal:
        """Berechnet Gesamtsumme (Ist-Bestand)."""
        return self.total_coins + self.total_notes
    
    @property
    def difference(self) -> Decimal:
        """Berechnet Differenz (Ist - Soll)."""
        return self.counted_total - self.expected_total
```



---

## PHASE 3: Spesenabrechnung

### 3.1 Expense Report Models

**Datei: `app/db/models/expense.py`**

```python
"""Spesenabrechnung Models."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text,
    Index
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.cash_enums import ExpenseReportStatus, ExpenseType

if TYPE_CHECKING:
    from app.db.models import Company, User, Document, CashEntry, CashCategory


class ExpenseReport(Base):
    """Spesenabrechnung eines Mitarbeiters."""
    
    __tablename__ = "expense_reports"
    __table_args__ = (
        Index("ix_expense_reports_company", "company_id"),
        Index("ix_expense_reports_employee", "employee_id"),
        Index("ix_expense_reports_status", "status"),
        Index("ix_expense_reports_period", "period_start", "period_end"),
    )
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )
    
    # Identifikation
    report_number: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Zeitraum
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    
    # Mitarbeiter
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    employee_name: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Beträge (berechnet aus Positionen)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0"))
    total_vat: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0"))
    total_deductible: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0"))
    
    # Reisekosten-Pauschalen
    travel_days: Mapped[int] = mapped_column(Integer, default=0)
    travel_allowance_total: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), default=Decimal("0")
    )
    
    # Kilometergeld
    total_kilometers: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    mileage_allowance_total: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), default=Decimal("0")
    )
    
    # Status-Workflow
    status: Mapped[ExpenseReportStatus] = mapped_column(
        default=ExpenseReportStatus.DRAFT
    )
    
    # Workflow-Timestamps
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    submitted_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    reviewed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    review_notes: Mapped[Optional[str]] = mapped_column(Text)
    
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    approved_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    rejected_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text)
    
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    paid_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    payment_method: Mapped[Optional[str]] = mapped_column(String(50))
    payment_reference: Mapped[Optional[str]] = mapped_column(String(100))
    
    # Verknüpfung zu Kassenbuch
    cash_entry_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cash_entries.id")
    )
    
    # DATEV
    datev_exported_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    
    # Relationships
    company: Mapped["Company"] = relationship()
    employee: Mapped["User"] = relationship(foreign_keys=[employee_id])
    items: Mapped[list["ExpenseItem"]] = relationship(
        back_populates="expense_report", 
        cascade="all, delete-orphan",
        order_by="ExpenseItem.expense_date"
    )
    cash_entry: Mapped[Optional["CashEntry"]] = relationship()


class ExpenseItem(Base):
    """Einzelposition einer Spesenabrechnung."""
    
    __tablename__ = "expense_items"
    __table_args__ = (
        Index("ix_expense_items_report", "expense_report_id"),
        Index("ix_expense_items_date", "expense_date"),
        Index("ix_expense_items_document", "document_id"),
    )
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    expense_report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("expense_reports.id", ondelete="CASCADE"),
        nullable=False
    )
    
    # Kategorisierung
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cash_categories.id")
    )
    expense_type: Mapped[ExpenseType] = mapped_column(nullable=False)
    
    # Datum
    expense_date: Mapped[date] = mapped_column(Date, nullable=False)
    
    # Betrag
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    
    # Steuer
    tax_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    tax_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    net_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    
    # Abzugsfähigkeit
    is_deductible: Mapped[bool] = mapped_column(Boolean, default=True)
    deductible_percentage: Mapped[int] = mapped_column(Integer, default=100)
    deductible_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    
    # Beschreibung
    description: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Beleg
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id")
    )
    receipt_number: Mapped[Optional[str]] = mapped_column(String(100))
    
    # Geschäftspartner
    vendor_name: Mapped[Optional[str]] = mapped_column(String(255))
    vendor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("business_entities.id")
    )
    
    # Bewirtung
    entertainment_participants: Mapped[Optional[list]] = mapped_column(ARRAY(String))
    entertainment_occasion: Mapped[Optional[str]] = mapped_column(Text)
    entertainment_location: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Kilometergeld
    mileage_from: Mapped[Optional[str]] = mapped_column(String(255))
    mileage_to: Mapped[Optional[str]] = mapped_column(String(255))
    mileage_kilometers: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    mileage_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.30"))
    mileage_vehicle_type: Mapped[Optional[str]] = mapped_column(String(50))
    mileage_license_plate: Mapped[Optional[str]] = mapped_column(String(20))
    
    # Verpflegungspauschale
    per_diem_hours: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 1))
    per_diem_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    per_diem_breakfast_provided: Mapped[bool] = mapped_column(Boolean, default=False)
    per_diem_lunch_provided: Mapped[bool] = mapped_column(Boolean, default=False)
    per_diem_dinner_provided: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Buchhaltung
    skr_account: Mapped[Optional[str]] = mapped_column(String(10))
    cost_center: Mapped[Optional[str]] = mapped_column(String(50))
    
    # Sortierung
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    
    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
    
    # Relationships
    expense_report: Mapped["ExpenseReport"] = relationship(back_populates="items")
    category: Mapped[Optional["CashCategory"]] = relationship()
    document: Mapped[Optional["Document"]] = relationship()
```

---

## PHASE 4: API Endpoints

### 4.1 Company Endpoints

**Datei: `app/api/v1/companies.py`**

```python
"""Multi-Company API Endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.db.models import User
from app.db.models.company import Company, UserCompany
from app.schemas.company import (
    CompanyCreate, CompanyUpdate, CompanyResponse, CompanyListResponse,
    UserCompanyCreate, UserCompanyResponse
)

router = APIRouter(prefix="/companies", tags=["Firmen"])


@router.get("", response_model=CompanyListResponse)
async def list_companies(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    include_inactive: bool = False,
) -> CompanyListResponse:
    """Listet alle Firmen des aktuellen Benutzers."""
    
    query = (
        select(Company)
        .join(UserCompany, UserCompany.company_id == Company.id)
        .where(UserCompany.user_id == current_user.id)
        .where(Company.deleted_at.is_(None))
    )
    
    if not include_inactive:
        query = query.where(Company.is_active == True)
    
    query = query.offset(skip).limit(limit)
    
    result = await db.execute(query)
    companies = result.scalars().all()
    
    # Count total
    count_query = (
        select(func.count())
        .select_from(Company)
        .join(UserCompany, UserCompany.company_id == Company.id)
        .where(UserCompany.user_id == current_user.id)
        .where(Company.deleted_at.is_(None))
    )
    if not include_inactive:
        count_query = count_query.where(Company.is_active == True)
    
    total = await db.scalar(count_query)
    
    return CompanyListResponse(
        items=[CompanyResponse.model_validate(c) for c in companies],
        total=total,
        skip=skip,
        limit=limit
    )


@router.post("", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
async def create_company(
    data: CompanyCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CompanyResponse:
    """Erstellt eine neue Firma."""
    
    # Prüfen ob VAT-ID bereits existiert
    if data.vat_id:
        existing = await db.scalar(
            select(Company).where(Company.vat_id == data.vat_id)
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Firma mit USt-IdNr. {data.vat_id} existiert bereits"
            )
    
    company = Company(
        **data.model_dump(),
        created_by_id=current_user.id
    )
    db.add(company)
    
    # User als Owner zuordnen
    user_company = UserCompany(
        user_id=current_user.id,
        company_id=company.id,
        role="owner",
        can_manage_cash=True,
        can_approve_expenses=True,
        can_export_datev=True,
        can_manage_settings=True,
        is_current=True
    )
    db.add(user_company)
    
    await db.commit()
    await db.refresh(company)
    
    return CompanyResponse.model_validate(company)


@router.get("/current", response_model=CompanyResponse)
async def get_current_company(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CompanyResponse:
    """Gibt die aktuelle Firma des Benutzers zurück."""
    
    result = await db.execute(
        select(Company)
        .join(UserCompany, UserCompany.company_id == Company.id)
        .where(UserCompany.user_id == current_user.id)
        .where(UserCompany.is_current == True)
    )
    company = result.scalar_one_or_none()
    
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine aktive Firma ausgewählt"
        )
    
    return CompanyResponse.model_validate(company)


@router.post("/current/{company_id}")
async def set_current_company(
    company_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Setzt die aktive Firma für den Benutzer."""
    
    # Prüfen ob Zugriff
    user_company = await db.scalar(
        select(UserCompany)
        .where(UserCompany.user_id == current_user.id)
        .where(UserCompany.company_id == company_id)
    )
    
    if not user_company:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Kein Zugriff auf diese Firma"
        )
    
    # Alle anderen auf nicht-aktuell setzen
    await db.execute(
        UserCompany.__table__.update()
        .where(UserCompany.user_id == current_user.id)
        .values(is_current=False)
    )
    
    # Diese auf aktuell setzen
    user_company.is_current = True
    await db.commit()
    
    return {"message": "Aktive Firma geändert", "company_id": str(company_id)}
```

### 4.2 Cash Register Endpoints

**Datei: `app/api/v1/cash.py`**

```python
"""Kassenbuch API Endpoints."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.db.models import User
from app.db.models.cash import CashRegister, CashEntry, CashCategory, CashCount
from app.db.models.cash_enums import CashEntryType
from app.middleware.company_context import require_company
from app.schemas.cash import (
    CashRegisterCreate, CashRegisterUpdate, CashRegisterResponse,
    CashEntryCreate, CashEntryResponse, CashEntryListResponse,
    CashCountCreate, CashCountResponse,
    CashBookSummary, DailySummary
)
from app.services.cash import CashService

router = APIRouter(prefix="/cash", tags=["Kasse"])


# ============ Cash Register ============

@router.get("/registers", response_model=list[CashRegisterResponse])
async def list_cash_registers(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    include_inactive: bool = False,
) -> list[CashRegisterResponse]:
    """Listet alle Kassen der aktuellen Firma."""
    
    company_id = require_company()
    
    query = select(CashRegister).where(
        CashRegister.company_id == company_id,
        CashRegister.deleted_at.is_(None)
    )
    
    if not include_inactive:
        query = query.where(CashRegister.is_active == True)
    
    result = await db.execute(query.order_by(CashRegister.name))
    registers = result.scalars().all()
    
    return [CashRegisterResponse.model_validate(r) for r in registers]


@router.post("/registers", response_model=CashRegisterResponse, 
             status_code=status.HTTP_201_CREATED)
async def create_cash_register(
    data: CashRegisterCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CashRegisterResponse:
    """Erstellt eine neue Kasse."""
    
    company_id = require_company()
    
    register = CashRegister(
        **data.model_dump(),
        company_id=company_id,
        created_by_id=current_user.id
    )
    db.add(register)
    await db.commit()
    await db.refresh(register)
    
    return CashRegisterResponse.model_validate(register)


# ============ Cash Entries ============

@router.get("/entries", response_model=CashEntryListResponse)
async def list_cash_entries(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    register_id: Optional[uuid.UUID] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    entry_type: Optional[CashEntryType] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> CashEntryListResponse:
    """Listet Kassenbucheinträge mit Filterung."""
    
    company_id = require_company()
    
    query = select(CashEntry).where(
        CashEntry.company_id == company_id,
        CashEntry.is_cancelled == False
    )
    
    if register_id:
        query = query.where(CashEntry.cash_register_id == register_id)
    if date_from:
        query = query.where(CashEntry.entry_date >= date_from)
    if date_to:
        query = query.where(CashEntry.entry_date <= date_to)
    if entry_type:
        query = query.where(CashEntry.entry_type == entry_type)
    
    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)
    
    # Fetch
    query = query.order_by(
        CashEntry.entry_date.desc(), 
        CashEntry.entry_number.desc()
    ).offset(skip).limit(limit)
    
    result = await db.execute(query)
    entries = result.scalars().all()
    
    return CashEntryListResponse(
        items=[CashEntryResponse.model_validate(e) for e in entries],
        total=total,
        skip=skip,
        limit=limit
    )


@router.post("/entries", response_model=CashEntryResponse,
             status_code=status.HTTP_201_CREATED)
async def create_cash_entry(
    data: CashEntryCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CashEntryResponse:
    """Erstellt einen neuen Kassenbucheintrag.
    
    WICHTIG: Einträge sind nach Erstellung UNVERÄNDERBAR (GoBD-Compliance).
    Stornierungen erfolgen über den /cancel Endpoint.
    """
    
    company_id = require_company()
    
    service = CashService(db)
    entry = await service.create_entry(
        company_id=company_id,
        user_id=current_user.id,
        data=data
    )
    
    return CashEntryResponse.model_validate(entry)


@router.post("/entries/{entry_id}/cancel", response_model=CashEntryResponse)
async def cancel_cash_entry(
    entry_id: uuid.UUID,
    reason: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CashEntryResponse:
    """Storniert einen Kassenbucheintrag durch Gegenbuchung.
    
    Der Originaleintrag wird als storniert markiert,
    ein neuer Eintrag mit umgekehrtem Betrag wird erstellt.
    """
    
    company_id = require_company()
    
    service = CashService(db)
    cancellation_entry = await service.cancel_entry(
        company_id=company_id,
        entry_id=entry_id,
        user_id=current_user.id,
        reason=reason
    )
    
    return CashEntryResponse.model_validate(cancellation_entry)


# ============ Cash Count (Kassensturz) ============

@router.post("/count", response_model=CashCountResponse,
             status_code=status.HTTP_201_CREATED)
async def create_cash_count(
    data: CashCountCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CashCountResponse:
    """Führt einen Kassensturz durch.
    
    Zählt Münzen und Scheine, vergleicht mit Soll-Bestand
    und erstellt bei Differenz automatisch eine Buchung.
    """
    
    company_id = require_company()
    
    service = CashService(db)
    count = await service.perform_cash_count(
        company_id=company_id,
        user_id=current_user.id,
        data=data
    )
    
    return CashCountResponse.model_validate(count)


# ============ Reports ============

@router.get("/summary", response_model=CashBookSummary)
async def get_cash_summary(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    register_id: Optional[uuid.UUID] = None,
    year: Optional[int] = None,
    month: Optional[int] = None,
) -> CashBookSummary:
    """Gibt Kassenbuch-Zusammenfassung zurück."""
    
    company_id = require_company()
    
    service = CashService(db)
    return await service.get_summary(
        company_id=company_id,
        register_id=register_id,
        year=year or datetime.now().year,
        month=month
    )


@router.get("/daily", response_model=list[DailySummary])
async def get_daily_summaries(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    register_id: uuid.UUID,
    date_from: date,
    date_to: date,
) -> list[DailySummary]:
    """Gibt tägliche Kassenzusammenfassungen zurück."""
    
    company_id = require_company()
    
    service = CashService(db)
    return await service.get_daily_summaries(
        company_id=company_id,
        register_id=register_id,
        date_from=date_from,
        date_to=date_to
    )
```

---

## PHASE 5: TypeScript Types (Frontend)

**Datei: `frontend/src/types/models/cash.ts`**

```typescript
/**
 * Kasse-Modul TypeScript Types
 * 
 * @module types/models/cash
 * @description Vollständige Typdefinitionen für Kassenbuch und Spesenabrechnung
 */

// ============ Enums ============

/** Typ der Kassenbuchung */
export type CashEntryType =
  | 'income'           // Allgemeine Einnahme
  | 'deposit'          // Kasseneinlage von Bank
  | 'refund_received'  // Erstattung erhalten
  | 'expense'          // Allgemeine Ausgabe
  | 'withdrawal'       // Kassenentnahme zur Bank
  | 'entertainment'    // Bewirtungskosten
  | 'travel'           // Reisekosten
  | 'office'           // Bürobedarf
  | 'fuel'             // Tankkosten
  | 'parking'          // Parkgebühren
  | 'postage'          // Porto
  | 'tips'             // Trinkgeld
  | 'gifts'            // Geschenke
  | 'difference_plus'  // Kassenmehrbestand
  | 'difference_minus' // Kassenfehlbestand
  | 'cancellation'     // Stornobuchung
  | 'opening';         // Eröffnungsbuchung

/** Status einer Spesenabrechnung */
export type ExpenseReportStatus =
  | 'draft'      // Entwurf
  | 'submitted'  // Eingereicht
  | 'in_review'  // In Prüfung
  | 'approved'   // Genehmigt
  | 'rejected'   // Abgelehnt
  | 'paid';      // Ausgezahlt

/** Typ einer Spesenposition */
export type ExpenseType =
  | 'receipt'    // Belegausgabe
  | 'mileage'    // Kilometergeld
  | 'per_diem'   // Verpflegungspauschale
  | 'flat_rate'; // Sonstige Pauschale


// ============ Company (Multi-Tenant) ============

/** Firma/Mandant */
export interface Company {
  id: string;
  name: string;
  shortName?: string;
  displayName?: string;
  
  // Rechtsform
  legalForm?: string;
  commercialRegister?: string;
  court?: string;
  
  // Steuer
  vatId?: string;
  taxNumber?: string;
  
  // Adresse
  street?: string;
  streetNumber?: string;
  postalCode?: string;
  city?: string;
  country: string;
  
  // Kontakt
  email?: string;
  phone?: string;
  website?: string;
  
  // Banking
  iban?: string;
  bic?: string;
  bankName?: string;
  
  // OCR-Erkennung
  alternativeNames: string[];
  
  // Einstellungen
  defaultCurrency: string;
  fiscalYearStart: number;
  kontenrahmen: 'SKR03' | 'SKR04';
  
  // Status
  isActive: boolean;
  isDefault: boolean;
  
  // Audit
  createdAt: string;
  updatedAt: string;
}

/** User-Company Zuordnung */
export interface UserCompany {
  id: string;
  userId: string;
  companyId: string;
  role: 'owner' | 'admin' | 'member' | 'viewer';
  
  // Berechtigungen
  canManageCash: boolean;
  canApproveExpenses: boolean;
  canExportDatev: boolean;
  canManageSettings: boolean;
  
  isCurrent: boolean;
  createdAt: string;
}


// ============ Cash Register ============

/** Kasse */
export interface CashRegister {
  id: string;
  companyId: string;
  
  name: string;
  description?: string;
  registerNumber?: string;
  
  currency: string;
  maxBalance?: number;
  warningThreshold?: number;
  
  currentBalance: number;
  balanceDate?: string;
  lastReconciliationDate?: string;
  
  linkedBankAccountId?: string;
  
  isActive: boolean;
  isDefault: boolean;
  
  createdAt: string;
  updatedAt: string;
}

/** Kassenbucheintrag (UNVERÄNDERBAR nach Erstellung!) */
export interface CashEntry {
  id: string;
  companyId: string;
  cashRegisterId: string;
  
  entryNumber: number;
  fiscalYear: number;
  
  entryDate: string;
  valueDate: string;
  
  amount: number;
  currency: string;
  balanceAfter: number;
  
  entryType: CashEntryType;
  categoryId?: string;
  
  // Steuer
  taxRate?: number;
  taxAmount?: number;
  netAmount?: number;
  isTaxDeductible: boolean;
  deductiblePercentage: number;
  
  description: string;
  referenceNumber?: string;
  
  counterpartyName?: string;
  counterpartyId?: string;
  
  // Verknüpfungen
  documentId?: string;
  bankTransactionId?: string;
  expenseReportId?: string;
  
  // Storno
  isCancelled: boolean;
  cancelledByEntryId?: string;
  cancellationReason?: string;
  
  // Bewirtung
  entertainmentData?: EntertainmentData;
  
  // DATEV
  datevExportedAt?: string;
  
  // Buchhaltung
  debitAccount?: string;
  creditAccount?: string;
  costCenter?: string;
  
  createdAt: string;
  createdById: string;
}

/** Bewirtungskosten-Details */
export interface EntertainmentData {
  /** Teilnehmer (PFLICHT: namentlich!) */
  participants: string[];
  /** Anlass (PFLICHT: konkret!) */
  occasion: string;
  /** Ort */
  location?: string;
}


// ============ Cash Category ============

/** Kategorie für Kassenausgaben */
export interface CashCategory {
  id: string;
  companyId?: string;
  
  name: string;
  nameEn?: string;
  description?: string;
  icon?: string;
  color?: string;
  
  parentId?: string;
  level: number;
  path?: string;
  
  skr03Account?: string;
  skr04Account?: string;
  defaultTaxRate: number;
  
  categoryType?: string;
  isEntertainment: boolean;
  isTravelExpense: boolean;
  deductiblePercentage: number;
  
  allowsVatDeduction: boolean;
  
  isActive: boolean;
  isSystem: boolean;
  sortOrder: number;
}


// ============ Cash Count (Kassensturz) ============

/** Zählprotokoll */
export interface CashCount {
  id: string;
  companyId: string;
  cashRegisterId: string;
  
  countDate: string;
  countTime: string;
  
  // Münzen
  coins1Cent: number;
  coins2Cent: number;
  coins5Cent: number;
  coins10Cent: number;
  coins20Cent: number;
  coins50Cent: number;
  coins1Euro: number;
  coins2Euro: number;
  
  // Scheine
  notes5Euro: number;
  notes10Euro: number;
  notes20Euro: number;
  notes50Euro: number;
  notes100Euro: number;
  notes200Euro: number;
  notes500Euro: number;
  
  // Berechnete Werte
  totalCoins: number;
  totalNotes: number;
  countedTotal: number;
  expectedTotal: number;
  difference: number;
  
  differenceEntryId?: string;
  differenceExplanation?: string;
  
  countedById: string;
  verifiedById?: string;
  verifiedAt?: string;
  
  notes?: string;
  createdAt: string;
}


// ============ Expense Report ============

/** Spesenabrechnung */
export interface ExpenseReport {
  id: string;
  companyId: string;
  
  reportNumber: string;
  title: string;
  description?: string;
  
  periodStart: string;
  periodEnd: string;
  
  employeeId: string;
  employeeName?: string;
  
  totalAmount: number;
  totalVat: number;
  totalDeductible: number;
  
  travelDays: number;
  travelAllowanceTotal: number;
  
  totalKilometers: number;
  mileageAllowanceTotal: number;
  
  status: ExpenseReportStatus;
  
  // Workflow
  submittedAt?: string;
  submittedById?: string;
  reviewedAt?: string;
  reviewedById?: string;
  reviewNotes?: string;
  approvedAt?: string;
  approvedById?: string;
  rejectedAt?: string;
  rejectedById?: string;
  rejectionReason?: string;
  paidAt?: string;
  paidById?: string;
  paymentMethod?: string;
  paymentReference?: string;
  
  cashEntryId?: string;
  datevExportedAt?: string;
  
  createdAt: string;
  updatedAt: string;
  
  items?: ExpenseItem[];
}

/** Spesenposition */
export interface ExpenseItem {
  id: string;
  expenseReportId: string;
  
  categoryId?: string;
  expenseType: ExpenseType;
  expenseDate: string;
  
  amount: number;
  currency: string;
  
  taxRate?: number;
  taxAmount?: number;
  netAmount?: number;
  
  isDeductible: boolean;
  deductiblePercentage: number;
  deductibleAmount?: number;
  
  description: string;
  
  documentId?: string;
  receiptNumber?: string;
  
  vendorName?: string;
  vendorId?: string;
  
  // Bewirtung
  entertainmentParticipants?: string[];
  entertainmentOccasion?: string;
  entertainmentLocation?: string;
  
  // Kilometergeld
  mileageFrom?: string;
  mileageTo?: string;
  mileageKilometers?: number;
  mileageRate: number;
  mileageVehicleType?: string;
  mileageLicensePlate?: string;
  
  // Verpflegungspauschale
  perDiemHours?: number;
  perDiemRate?: number;
  perDiemBreakfastProvided: boolean;
  perDiemLunchProvided: boolean;
  perDiemDinnerProvided: boolean;
  
  skrAccount?: string;
  costCenter?: string;
  
  sortOrder: number;
  createdAt: string;
  updatedAt: string;
}


// ============ API Request/Response Types ============

/** Neue Kasse erstellen */
export interface CashRegisterCreateRequest {
  name: string;
  description?: string;
  registerNumber?: string;
  currency?: string;
  maxBalance?: number;
  warningThreshold?: number;
  linkedBankAccountId?: string;
  isDefault?: boolean;
}

/** Kassenbucheintrag erstellen */
export interface CashEntryCreateRequest {
  cashRegisterId: string;
  entryDate: string;
  valueDate?: string;
  amount: number;
  entryType: CashEntryType;
  categoryId?: string;
  description: string;
  referenceNumber?: string;
  counterpartyName?: string;
  counterpartyId?: string;
  documentId?: string;
  bankTransactionId?: string;
  entertainmentData?: EntertainmentData;
  costCenter?: string;
}

/** Kassensturz durchführen */
export interface CashCountCreateRequest {
  cashRegisterId: string;
  countDate: string;
  countTime: string;
  
  coins1Cent?: number;
  coins2Cent?: number;
  coins5Cent?: number;
  coins10Cent?: number;
  coins20Cent?: number;
  coins50Cent?: number;
  coins1Euro?: number;
  coins2Euro?: number;
  
  notes5Euro?: number;
  notes10Euro?: number;
  notes20Euro?: number;
  notes50Euro?: number;
  notes100Euro?: number;
  notes200Euro?: number;
  notes500Euro?: number;
  
  notes?: string;
}

/** Spesenabrechnung erstellen */
export interface ExpenseReportCreateRequest {
  title: string;
  description?: string;
  periodStart: string;
  periodEnd: string;
}

/** Spesenposition hinzufügen */
export interface ExpenseItemCreateRequest {
  categoryId?: string;
  expenseType: ExpenseType;
  expenseDate: string;
  amount: number;
  description: string;
  documentId?: string;
  receiptNumber?: string;
  vendorName?: string;
  
  // Bewirtung (wenn expense_type = receipt & category = entertainment)
  entertainmentParticipants?: string[];
  entertainmentOccasion?: string;
  entertainmentLocation?: string;
  
  // Kilometergeld (wenn expense_type = mileage)
  mileageFrom?: string;
  mileageTo?: string;
  mileageKilometers?: number;
  mileageVehicleType?: string;
  mileageLicensePlate?: string;
  
  // Verpflegungspauschale (wenn expense_type = per_diem)
  perDiemHours?: number;
  perDiemBreakfastProvided?: boolean;
  perDiemLunchProvided?: boolean;
  perDiemDinnerProvided?: boolean;
  
  costCenter?: string;
}


// ============ Summary Types ============

/** Kassenbuch-Zusammenfassung */
export interface CashBookSummary {
  registerId: string;
  registerName: string;
  
  period: {
    year: number;
    month?: number;
  };
  
  openingBalance: number;
  closingBalance: number;
  
  totalIncome: number;
  totalExpenses: number;
  netChange: number;
  
  entryCount: number;
  
  byCategory: CategorySummary[];
  byType: TypeSummary[];
}

/** Zusammenfassung nach Kategorie */
export interface CategorySummary {
  categoryId: string;
  categoryName: string;
  totalAmount: number;
  entryCount: number;
  percentage: number;
}

/** Zusammenfassung nach Typ */
export interface TypeSummary {
  entryType: CashEntryType;
  totalAmount: number;
  entryCount: number;
}

/** Tages-Zusammenfassung */
export interface DailySummary {
  date: string;
  openingBalance: number;
  closingBalance: number;
  totalIncome: number;
  totalExpenses: number;
  entryCount: number;
}
```

