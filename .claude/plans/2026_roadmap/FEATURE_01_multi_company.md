# Feature 01: Multi-Firma Architektur

> **Status**: Ready for Implementation
> **Version**: 1.0.0
> **Erstellt**: 2026-01-02
> **Prioritaet**: P1 - Kritisch
> **Geschaetzter Aufwand**: 4-6 Wochen
> **Abhaengigkeiten**: Keine (Fundament fuer alle anderen Features)

---

## Executive Summary

Die Multi-Firma Architektur ermoeglicht die Verwaltung mehrerer Unternehmen (aktuell "Spargelmesser" und "Folie") in einer einzigen Ablage-System Instanz. Benutzer koennen zwischen Firmen wechseln, Stammdaten (Kunden, Lieferanten) werden firmenuebergreifend geteilt, waehrend Dokumente und Finanzdaten strikt getrennt bleiben.

**Business Value:**
- Eine Codebasis fuer alle Firmen
- Vereinfachte Administration
- Konsolidierte Auswertungen moeglich
- Skalierbar auf 3-4+ Firmen

---

## Inhaltsverzeichnis

1. [Anforderungen](#anforderungen)
2. [API-Spezifikation](#api-spezifikation)
3. [Datenbank-Schema](#datenbank-schema)
4. [Implementation Tasks](#implementation-tasks)
5. [Test-Szenarien](#test-szenarien)
6. [Frontend-Komponenten](#frontend-komponenten)
7. [Quality Gates](#quality-gates)

---

## Anforderungen

### Funktionale Anforderungen

| ID | Anforderung | Prioritaet | Akzeptanzkriterium |
|----|-------------|-----------|-------------------|
| FR-01 | Benutzer kann zwischen Firmen wechseln | MUSS | Switcher im Header, Wechsel < 500ms |
| FR-02 | Dokumente sind firmenspezifisch | MUSS | Firma A sieht keine Dokumente von Firma B |
| FR-03 | Kunden/Lieferanten sind teilbar | MUSS | Gleicher Kunde erscheint in beiden Firmen |
| FR-04 | Benutzer haben Firmenzuweisungen | MUSS | User X sieht nur Firmen A, B, nicht C |
| FR-05 | Admin kann Firmen verwalten | SOLL | CRUD fuer Firmen im Admin-Panel |
| FR-06 | Visuelle Unterscheidung pro Firma | SOLL | Farbe/Logo pro Firma im Header |
| FR-07 | Firmenuebergreifende Reports | KANN | Konsolidierte Auswertung fuer GF |

### Nicht-Funktionale Anforderungen

| ID | Anforderung | Metrik | Akzeptanzkriterium |
|----|-------------|--------|-------------------|
| NFR-01 | Performance | Firmen-Switch | < 500ms Response Time |
| NFR-02 | Skalierbarkeit | Anzahl Firmen | Unterstuetzt 10+ Firmen ohne Redesign |
| NFR-03 | Sicherheit | Datenisolation | Keine Cross-Tenant Data Leaks |
| NFR-04 | Verfuegbarkeit | RLS Policies | Row-Level Security immer aktiv |

### Abgrenzung (Out of Scope)

- Separate Datenbanken pro Firma (Single-DB mit RLS)
- Unterschiedliche Feature-Sets pro Firma
- Billing/Subscription pro Firma

---

## API-Spezifikation

### Endpoints Uebersicht

| Method | Endpoint | Beschreibung | Auth |
|--------|----------|--------------|------|
| GET | `/api/v1/companies` | Listet Firmen des Users | Required |
| GET | `/api/v1/companies/{id}` | Firma-Details | Required |
| POST | `/api/v1/companies` | Neue Firma erstellen | Admin |
| PUT | `/api/v1/companies/{id}` | Firma aktualisieren | Admin |
| DELETE | `/api/v1/companies/{id}` | Firma deaktivieren | Admin |
| POST | `/api/v1/companies/switch/{id}` | Aktive Firma wechseln | Required |
| GET | `/api/v1/companies/current` | Aktuelle Firma abrufen | Required |

---

### `GET /api/v1/companies`

**Beschreibung**: Listet alle Firmen, auf die der aktuelle Benutzer Zugriff hat.

**Response (200 OK):**
```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440001",
      "name": "Spargelmesser GmbH",
      "code": "SPARG",
      "color": "#2196F3",
      "logo_url": "/static/logos/spargelmesser.png",
      "is_active": true,
      "is_current": true,
      "settings": {
        "default_currency": "EUR",
        "tax_id": "DE123456789",
        "address": {
          "street": "Musterstr. 1",
          "city": "Musterstadt",
          "zip": "12345"
        }
      },
      "created_at": "2024-01-01T00:00:00Z"
    },
    {
      "id": "550e8400-e29b-41d4-a716-446655440002",
      "name": "Folie & Co KG",
      "code": "FOLIE",
      "color": "#4CAF50",
      "logo_url": null,
      "is_active": true,
      "is_current": false,
      "settings": {...},
      "created_at": "2024-06-01T00:00:00Z"
    }
  ],
  "total": 2
}
```

---

### `POST /api/v1/companies/switch/{id}`

**Beschreibung**: Wechselt die aktive Firma des Benutzers. Aktualisiert JWT-Token mit neuem Company-Context.

**Path Parameters:**
- `id` (UUID): ID der Ziel-Firma

**Response (200 OK):**
```json
{
  "message": "Firma gewechselt",
  "company": {
    "id": "550e8400-e29b-41d4-a716-446655440002",
    "name": "Folie & Co KG",
    "code": "FOLIE"
  },
  "new_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

**Fehler:**
| Code | Beschreibung |
|------|--------------|
| 403 | Benutzer hat keinen Zugriff auf diese Firma |
| 404 | Firma nicht gefunden |

---

### `POST /api/v1/companies` (Admin)

**Request Body:**
```json
{
  "name": "Neue Firma GmbH",
  "code": "NEUF",
  "color": "#FF5722",
  "settings": {
    "default_currency": "EUR",
    "tax_id": "DE987654321",
    "address": {
      "street": "Hauptstr. 10",
      "city": "Berlin",
      "zip": "10115"
    }
  }
}
```

**Response (201 Created):**
```json
{
  "id": "new-uuid",
  "name": "Neue Firma GmbH",
  "code": "NEUF",
  ...
}
```

---

## Datenbank-Schema

### Neue Tabellen

#### `companies`

```sql
-- Migration: 0001_create_companies.py

CREATE TABLE companies (
    -- Primary Key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identifikation
    name VARCHAR(255) NOT NULL UNIQUE,
    code VARCHAR(10) NOT NULL UNIQUE,

    -- Branding
    color VARCHAR(7) DEFAULT '#2196F3',  -- Hex color
    logo_url VARCHAR(500),

    -- Einstellungen (JSONB fuer Flexibilitaet)
    settings JSONB DEFAULT '{
        "default_currency": "EUR",
        "tax_id": null,
        "address": {}
    }',

    -- Status
    is_active BOOLEAN DEFAULT true NOT NULL,

    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    created_by_id UUID REFERENCES users(id),
    deleted_at TIMESTAMPTZ
);

-- Indizes
CREATE INDEX ix_companies_code ON companies(code);
CREATE INDEX ix_companies_active ON companies(is_active) WHERE deleted_at IS NULL;
```

#### `user_companies` (Many-to-Many)

```sql
-- Migration: 0002_create_user_companies.py

CREATE TABLE user_companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE NOT NULL,

    -- Berechtigungen pro Firma
    role VARCHAR(50) DEFAULT 'member',  -- admin, member, viewer
    is_default BOOLEAN DEFAULT false,   -- Standard-Firma beim Login

    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    granted_by_id UUID REFERENCES users(id),

    -- Constraints
    CONSTRAINT user_companies_unique UNIQUE (user_id, company_id)
);

-- Indizes
CREATE INDEX ix_user_companies_user ON user_companies(user_id);
CREATE INDEX ix_user_companies_company ON user_companies(company_id);
```

### Bestehende Tabellen erweitern

```sql
-- Migration: 0003_add_company_id_to_tables.py

-- Dokumente
ALTER TABLE documents ADD COLUMN company_id UUID REFERENCES companies(id);
UPDATE documents SET company_id = (SELECT id FROM companies LIMIT 1);
ALTER TABLE documents ALTER COLUMN company_id SET NOT NULL;
CREATE INDEX ix_documents_company ON documents(company_id);

-- Rechnungen
ALTER TABLE invoices ADD COLUMN company_id UUID REFERENCES companies(id);
-- ... analog

-- Buchungen
ALTER TABLE transactions ADD COLUMN company_id UUID REFERENCES companies(id);
-- ... analog

-- ABER: Kunden/Lieferanten bleiben OHNE company_id (shared)
-- Stattdessen: Verknuepfungstabelle

CREATE TABLE customer_companies (
    customer_id UUID REFERENCES customers(id) ON DELETE CASCADE,
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    customer_code_override VARCHAR(50),  -- Firmenspezifische Kundennummer
    PRIMARY KEY (customer_id, company_id)
);
```

### Row-Level Security

```sql
-- Migration: 0004_enable_rls.py

-- RLS aktivieren
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;

-- Policy: Nur eigene Firma sehen
CREATE POLICY documents_company_isolation ON documents
    USING (company_id = current_setting('app.current_company_id')::UUID);

CREATE POLICY invoices_company_isolation ON invoices
    USING (company_id = current_setting('app.current_company_id')::UUID);

CREATE POLICY transactions_company_isolation ON transactions
    USING (company_id = current_setting('app.current_company_id')::UUID);

-- Funktion zum Setzen des Company-Context
CREATE OR REPLACE FUNCTION set_company_context(company_uuid UUID)
RETURNS void AS $$
BEGIN
    PERFORM set_config('app.current_company_id', company_uuid::text, false);
END;
$$ LANGUAGE plpgsql;
```

### Alembic Migration

```python
# alembic/versions/20260101_001_multi_company_architecture.py

"""Multi-Company Architecture

Revision ID: 20260101001
Revises: [previous]
Create Date: 2026-01-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20260101001'
down_revision = '[previous]'


def upgrade() -> None:
    # 1. Create companies table
    op.create_table(
        'companies',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False, unique=True),
        sa.Column('code', sa.String(10), nullable=False, unique=True),
        sa.Column('color', sa.String(7), server_default='#2196F3'),
        sa.Column('logo_url', sa.String(500)),
        sa.Column('settings', postgresql.JSONB, server_default='{}'),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True)),
    )

    # 2. Create user_companies junction table
    op.create_table(
        'user_companies',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(50), server_default='member'),
        sa.Column('is_default', sa.Boolean(), server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.UniqueConstraint('user_id', 'company_id', name='user_companies_unique'),
    )

    # 3. Insert default companies
    op.execute("""
        INSERT INTO companies (id, name, code, color) VALUES
        (gen_random_uuid(), 'Spargelmesser GmbH', 'SPARG', '#2196F3'),
        (gen_random_uuid(), 'Folie & Co KG', 'FOLIE', '#4CAF50')
    """)

    # 4. Add company_id to existing tables
    op.add_column('documents', sa.Column('company_id', postgresql.UUID(as_uuid=True)))
    op.create_foreign_key('fk_documents_company', 'documents', 'companies',
                          ['company_id'], ['id'])

    # 5. Migrate existing data to first company
    op.execute("""
        UPDATE documents SET company_id = (SELECT id FROM companies LIMIT 1)
        WHERE company_id IS NULL
    """)

    # 6. Make company_id NOT NULL
    op.alter_column('documents', 'company_id', nullable=False)

    # 7. Create indexes
    op.create_index('ix_documents_company', 'documents', ['company_id'])


def downgrade() -> None:
    op.drop_index('ix_documents_company')
    op.drop_constraint('fk_documents_company', 'documents')
    op.drop_column('documents', 'company_id')
    op.drop_table('user_companies')
    op.drop_table('companies')
```

### SQLAlchemy Models

```python
# app/db/models/company.py

"""Company Models fuer Multi-Tenant Architektur."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, SoftDeleteMixin

if TYPE_CHECKING:
    from app.db.models import User, Document


class Company(Base, TimestampMixin, SoftDeleteMixin):
    """Firma/Mandant im Multi-Tenant System."""

    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    color: Mapped[str] = mapped_column(String(7), default="#2196F3")
    logo_url: Mapped[Optional[str]] = mapped_column(String(500))
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    user_assignments: Mapped[list["UserCompany"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    documents: Mapped[list["Document"]] = relationship(back_populates="company")

    def __repr__(self) -> str:
        return f"<Company(id={self.id}, code='{self.code}', name='{self.name}')>"


class UserCompany(Base):
    """Verknuepfung zwischen User und Firma mit Rolle."""

    __tablename__ = "user_companies"
    __table_args__ = (
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
    role: Mapped[str] = mapped_column(String(50), default="member")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="company_assignments")
    company: Mapped["Company"] = relationship(back_populates="user_assignments")
```

### Pydantic Schemas

```python
# app/api/schemas/company.py

"""Pydantic Schemas fuer Company."""

from datetime import datetime
from typing import Optional, Any
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict, field_validator
import re


class CompanySettings(BaseModel):
    """Firmen-Einstellungen."""
    default_currency: str = "EUR"
    tax_id: Optional[str] = None
    address: dict[str, str] = Field(default_factory=dict)


class CompanyBase(BaseModel):
    """Basis-Schema fuer Company."""
    name: str = Field(..., min_length=1, max_length=255)
    code: str = Field(..., min_length=2, max_length=10, pattern=r'^[A-Z0-9]+$')
    color: str = Field(default="#2196F3", pattern=r'^#[0-9A-Fa-f]{6}$')
    logo_url: Optional[str] = None
    settings: CompanySettings = Field(default_factory=CompanySettings)

    @field_validator('code')
    @classmethod
    def uppercase_code(cls, v: str) -> str:
        return v.upper()


class CompanyCreate(CompanyBase):
    """Schema fuer Firma-Erstellung."""
    pass


class CompanyUpdate(BaseModel):
    """Schema fuer Firma-Update."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    color: Optional[str] = Field(None, pattern=r'^#[0-9A-Fa-f]{6}$')
    logo_url: Optional[str] = None
    settings: Optional[CompanySettings] = None
    is_active: Optional[bool] = None


class CompanyResponse(CompanyBase):
    """Response-Schema mit allen Feldern."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_active: bool
    is_current: bool = False
    created_at: datetime
    updated_at: datetime


class CompanyListResponse(BaseModel):
    """Liste der Firmen."""
    items: list[CompanyResponse]
    total: int


class CompanySwitchResponse(BaseModel):
    """Response beim Firmenwechsel."""
    message: str
    company: CompanyResponse
    new_token: str
```

---

## Implementation Tasks

### Phase 1: Datenbank & Models (1 Woche)

| # | Task | Beschreibung | Akzeptanzkriterium | Abhaengigkeit |
|---|------|--------------|-------------------|---------------|
| 1.1 | [ ] Migration erstellen | companies, user_companies Tabellen | Migration up/down fehlerfrei | - |
| 1.2 | [ ] Bestehende Tabellen erweitern | company_id zu documents, invoices etc. | Daten korrekt migriert | 1.1 |
| 1.3 | [ ] Row-Level Security | RLS Policies fuer alle Tabellen | SELECT ohne Context gibt 0 Rows | 1.2 |
| 1.4 | [ ] SQLAlchemy Models | Company, UserCompany Models | mypy --strict clean | 1.3 |
| 1.5 | [ ] Pydantic Schemas | Create/Update/Response Schemas | Validierung funktioniert | 1.4 |

### Phase 2: Backend Services (1-2 Wochen)

| # | Task | Beschreibung | Akzeptanzkriterium | Abhaengigkeit |
|---|------|--------------|-------------------|---------------|
| 2.1 | [ ] CompanyService | CRUD fuer Firmen | Unit Tests >80% | 1.5 |
| 2.2 | [ ] Company Context Middleware | Company-ID in Request-Context | Context in allen Endpoints verfuegbar | 2.1 |
| 2.3 | [ ] JWT Token erweitern | company_id im Token | Token enthaelt aktuelle Firma | 2.2 |
| 2.4 | [ ] Switch-Logik | Firmenwechsel mit neuem Token | Wechsel < 500ms | 2.3 |
| 2.5 | [ ] RLS Helper | set_company_context() bei DB-Calls | Automatisch bei jedem Query | 2.4 |

### Phase 3: API Layer (1 Woche)

| # | Task | Beschreibung | Akzeptanzkriterium | Abhaengigkeit |
|---|------|--------------|-------------------|---------------|
| 3.1 | [ ] Company Router | CRUD Endpoints | OpenAPI Spec generiert | 2.5 |
| 3.2 | [ ] Switch Endpoint | POST /companies/switch/{id} | Token wird refreshed | 3.1 |
| 3.3 | [ ] Berechtigungen | Admin-Only fuer Create/Delete | 403 bei fehlendem Zugriff | 3.2 |
| 3.4 | [ ] Bestehende Endpoints anpassen | Company-Filter automatisch | Alle Queries gefiltert | 3.3 |

### Phase 4: Frontend (1-2 Wochen)

| # | Task | Beschreibung | Akzeptanzkriterium | Abhaengigkeit |
|---|------|--------------|-------------------|---------------|
| 4.1 | [ ] TypeScript Types | Company Interfaces | Kein any | 3.4 |
| 4.2 | [ ] Company Context | React Context fuer aktuelle Firma | Context global verfuegbar | 4.1 |
| 4.3 | [ ] Company Switcher | Dropdown im Header | Wechsel funktioniert | 4.2 |
| 4.4 | [ ] Visuelle Unterscheidung | Farbe/Logo pro Firma | Header passt sich an | 4.3 |
| 4.5 | [ ] Token Handling | Neuen Token nach Switch speichern | Auth bleibt erhalten | 4.4 |
| 4.6 | [ ] Admin UI | Firmen-Verwaltung | CRUD im Admin-Panel | 4.5 |

### Phase 5: Testing & Migration (1 Woche)

| # | Task | Beschreibung | Akzeptanzkriterium | Abhaengigkeit |
|---|------|--------------|-------------------|---------------|
| 5.1 | [ ] Unit Tests | Service + Model Tests | Coverage >80% | 4.6 |
| 5.2 | [ ] Integration Tests | API Endpoint Tests | Alle CRUD getestet | 5.1 |
| 5.3 | [ ] E2E Tests | Firmenwechsel im Browser | Switch funktioniert | 5.2 |
| 5.4 | [ ] Daten-Migration | Bestehende Daten zuordnen | Keine Datenverluste | 5.3 |
| 5.5 | [ ] Rollout-Plan | Feature Flag, Rollback | Dokumentiert | 5.4 |

---

## Test-Szenarien

### Unit Tests

```python
# tests/unit/services/test_company_service.py

import pytest
from uuid import uuid4
from app.services.company_service import CompanyService


class TestCompanyIsolation:
    """Tests fuer Datenisolation zwischen Firmen."""

    @pytest.mark.asyncio
    async def test_documents_are_company_specific(self, db_session):
        """Dokumente von Firma A sind nicht in Firma B sichtbar."""
        company_a = await create_company(db_session, "Firma A")
        company_b = await create_company(db_session, "Firma B")

        # Dokument in Firma A erstellen
        doc = await create_document(db_session, company_a.id, "Test.pdf")

        # Mit Context von Firma B suchen
        set_company_context(company_b.id)
        docs = await get_all_documents(db_session)

        assert len(docs) == 0
        assert doc.id not in [d.id for d in docs]

    @pytest.mark.asyncio
    async def test_customers_are_shared(self, db_session):
        """Kunden sind firmenuebergreifend sichtbar."""
        company_a = await create_company(db_session, "Firma A")
        company_b = await create_company(db_session, "Firma B")

        # Kunde erstellen (ohne company_id)
        customer = await create_customer(db_session, "Shared Customer")

        # Kunde ist in beiden Firmen sichtbar
        set_company_context(company_a.id)
        customers_a = await get_all_customers(db_session)

        set_company_context(company_b.id)
        customers_b = await get_all_customers(db_session)

        assert customer.id in [c.id for c in customers_a]
        assert customer.id in [c.id for c in customers_b]


class TestCompanySwitch:
    """Tests fuer Firmenwechsel."""

    @pytest.mark.asyncio
    async def test_switch_updates_token(self, service, user_with_two_companies):
        """Firmenwechsel aktualisiert JWT Token."""
        old_token = user_with_two_companies.current_token
        new_company_id = user_with_two_companies.secondary_company_id

        result = await service.switch_company(user_with_two_companies.id, new_company_id)

        assert result.new_token != old_token
        decoded = decode_jwt(result.new_token)
        assert decoded["company_id"] == str(new_company_id)

    @pytest.mark.asyncio
    async def test_switch_to_unauthorized_company_fails(self, service, user):
        """Wechsel zu nicht-autorisierter Firma schlaegt fehl."""
        unauthorized_company_id = uuid4()

        with pytest.raises(PermissionError):
            await service.switch_company(user.id, unauthorized_company_id)
```

### Integration Tests

```python
# tests/integration/test_company_api.py

@pytest.mark.integration
class TestCompanyEndpoints:

    @pytest.mark.asyncio
    async def test_list_companies_returns_only_user_companies(
        self, async_client, auth_headers_user_a
    ):
        """User sieht nur seine zugewiesenen Firmen."""
        response = await async_client.get(
            "/api/v1/companies",
            headers=auth_headers_user_a
        )

        assert response.status_code == 200
        data = response.json()

        # User A hat nur 2 Firmen
        assert data["total"] == 2
        assert all(c["is_active"] for c in data["items"])

    @pytest.mark.asyncio
    async def test_switch_company_success(self, async_client, auth_headers):
        """Erfolgreicher Firmenwechsel."""
        # Get current company
        current = await async_client.get("/api/v1/companies/current", headers=auth_headers)
        old_company_id = current.json()["id"]

        # Get other company
        companies = await async_client.get("/api/v1/companies", headers=auth_headers)
        new_company = next(c for c in companies.json()["items"] if c["id"] != old_company_id)

        # Switch
        response = await async_client.post(
            f"/api/v1/companies/switch/{new_company['id']}",
            headers=auth_headers
        )

        assert response.status_code == 200
        assert response.json()["company"]["id"] == new_company["id"]
        assert "new_token" in response.json()

    @pytest.mark.asyncio
    async def test_admin_can_create_company(self, async_client, admin_auth_headers):
        """Admin kann neue Firma erstellen."""
        response = await async_client.post(
            "/api/v1/companies",
            json={
                "name": "Neue Test GmbH",
                "code": "NEUTEST",
                "color": "#9C27B0"
            },
            headers=admin_auth_headers
        )

        assert response.status_code == 201
        assert response.json()["name"] == "Neue Test GmbH"

    @pytest.mark.asyncio
    async def test_non_admin_cannot_create_company(self, async_client, auth_headers):
        """Nicht-Admin kann keine Firma erstellen."""
        response = await async_client.post(
            "/api/v1/companies",
            json={"name": "Illegal GmbH", "code": "ILLEGAL"},
            headers=auth_headers
        )

        assert response.status_code == 403
```

### E2E Tests

```typescript
// tests/e2e/multi-company.spec.ts

test.describe('Multi-Company Feature', () => {

  test('User kann zwischen Firmen wechseln', async ({ page }) => {
    await loginAsUser(page);

    // Aktuelle Firma pruefen
    await expect(page.locator('[data-testid="company-name"]')).toContainText('Spargelmesser');

    // Switcher oeffnen
    await page.click('[data-testid="company-switcher"]');

    // Andere Firma waehlen
    await page.click('text=Folie & Co KG');

    // Pruefen dass gewechselt wurde
    await expect(page.locator('[data-testid="company-name"]')).toContainText('Folie');

    // Header-Farbe hat sich geaendert
    const header = page.locator('header');
    await expect(header).toHaveCSS('background-color', 'rgb(76, 175, 80)'); // #4CAF50
  });

  test('Dokumente sind firmenspezifisch', async ({ page }) => {
    await loginAsUser(page);

    // In Firma A: Dokument hochladen
    await page.goto('/documents');
    await uploadDocument(page, 'test-firma-a.pdf');
    await expect(page.locator('text=test-firma-a.pdf')).toBeVisible();

    // Zu Firma B wechseln
    await switchToCompany(page, 'Folie & Co KG');

    // Dokument sollte nicht sichtbar sein
    await page.goto('/documents');
    await expect(page.locator('text=test-firma-a.pdf')).not.toBeVisible();
  });

  test('Kunden sind firmenuebergreifend sichtbar', async ({ page }) => {
    await loginAsUser(page);

    // Kunde in Firma A anlegen
    await page.goto('/customers');
    await createCustomer(page, 'Shared Customer GmbH');

    // Zu Firma B wechseln
    await switchToCompany(page, 'Folie & Co KG');

    // Kunde sollte sichtbar sein
    await page.goto('/customers');
    await expect(page.locator('text=Shared Customer GmbH')).toBeVisible();
  });
});
```

---

## Frontend-Komponenten

### TypeScript Types

```typescript
// frontend/src/types/models/company.ts

export interface Company {
  id: string;
  name: string;
  code: string;
  color: string;
  logoUrl?: string;
  settings: CompanySettings;
  isActive: boolean;
  isCurrent: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface CompanySettings {
  defaultCurrency: string;
  taxId?: string;
  address: {
    street?: string;
    city?: string;
    zip?: string;
  };
}

export interface CompanyListResponse {
  items: Company[];
  total: number;
}

export interface CompanySwitchResponse {
  message: string;
  company: Company;
  newToken: string;
}
```

### Company Context

```typescript
// frontend/src/contexts/CompanyContext.tsx

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { Company } from '@/types/models/company';
import { useCompanyList, useSwitchCompany } from '@/features/company/api/company-api';

interface CompanyContextType {
  currentCompany: Company | null;
  companies: Company[];
  isLoading: boolean;
  switchCompany: (companyId: string) => Promise<void>;
}

const CompanyContext = createContext<CompanyContextType | null>(null);

export function CompanyProvider({ children }: { children: ReactNode }) {
  const { data: companiesData, isLoading } = useCompanyList();
  const switchMutation = useSwitchCompany();

  const currentCompany = companiesData?.items.find(c => c.isCurrent) ?? null;

  const switchCompany = async (companyId: string) => {
    const result = await switchMutation.mutateAsync(companyId);
    // Update token in storage
    localStorage.setItem('token', result.newToken);
    // Reload to apply new context
    window.location.reload();
  };

  return (
    <CompanyContext.Provider value={{
      currentCompany,
      companies: companiesData?.items ?? [],
      isLoading,
      switchCompany,
    }}>
      {children}
    </CompanyContext.Provider>
  );
}

export function useCompany() {
  const context = useContext(CompanyContext);
  if (!context) throw new Error('useCompany must be used within CompanyProvider');
  return context;
}
```

### Company Switcher Component

```typescript
// frontend/src/components/layout/CompanySwitcher.tsx

import { ChevronDown, Building2 } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useCompany } from '@/contexts/CompanyContext';

export function CompanySwitcher() {
  const { currentCompany, companies, switchCompany, isLoading } = useCompany();

  if (isLoading || !currentCompany) {
    return <div className="h-8 w-32 animate-pulse bg-muted rounded" />;
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="flex items-center gap-2 px-3 py-2 rounded-md hover:bg-accent">
        <div
          className="w-3 h-3 rounded-full"
          style={{ backgroundColor: currentCompany.color }}
        />
        <span className="font-medium" data-testid="company-name">
          {currentCompany.name}
        </span>
        <ChevronDown className="h-4 w-4" />
      </DropdownMenuTrigger>

      <DropdownMenuContent align="start" className="w-64">
        {companies.map((company) => (
          <DropdownMenuItem
            key={company.id}
            onClick={() => switchCompany(company.id)}
            className="flex items-center gap-3 cursor-pointer"
            disabled={company.isCurrent}
          >
            <div
              className="w-3 h-3 rounded-full"
              style={{ backgroundColor: company.color }}
            />
            <div className="flex flex-col">
              <span className="font-medium">{company.name}</span>
              <span className="text-xs text-muted-foreground">{company.code}</span>
            </div>
            {company.isCurrent && (
              <span className="ml-auto text-xs text-muted-foreground">Aktiv</span>
            )}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
```

---

## Quality Gates

### Vor PR-Erstellung

- [ ] **Datenisolation**
  - [ ] RLS Policies auf allen relevanten Tabellen
  - [ ] Kein Cross-Tenant Zugriff moeglich
  - [ ] Penetration Test fuer Datenlecks

- [ ] **Code Qualitaet**
  - [ ] mypy --strict clean
  - [ ] ruff check . clean
  - [ ] TypeScript kompiliert fehlerfrei
  - [ ] ESLint clean

- [ ] **Testing**
  - [ ] Unit Tests >80% Coverage
  - [ ] Integration Tests fuer alle Endpoints
  - [ ] E2E Tests fuer Switch-Workflow
  - [ ] Load Test fuer 100+ concurrent users

- [ ] **Migration**
  - [ ] Migration laeuft fehlerfrei (up + down)
  - [ ] Bestehende Daten korrekt migriert
  - [ ] Rollback-Plan dokumentiert

### Vor Merge

- [ ] **Review**
  - [ ] Security Review durchgefuehrt
  - [ ] Code Review durch 2 Personen

- [ ] **UI/UX**
  - [ ] Alle 4 Display-Modi getestet
  - [ ] Switcher funktioniert auf allen Viewports
  - [ ] Firmen-Farben korrekt angezeigt

### Definition of Done

1. [ ] Beide Firmen (Spargelmesser, Folie) erfolgreich angelegt
2. [ ] Alle bestehenden User zu beiden Firmen zugewiesen
3. [ ] Alle bestehenden Dokumente zu Firma 1 migriert
4. [ ] Firmenwechsel < 500ms
5. [ ] Keine Datenlecks zwischen Firmen
6. [ ] Dokumentation aktualisiert
