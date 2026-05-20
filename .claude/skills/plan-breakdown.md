---
name: plan-breakdown
description: |
  Automatische Planzerlegung fuer grosse Features und Roadmaps.

  AKTIVIERE AUTOMATISCH wenn:
  - User erwaehnt: plan, roadmap, breakdown, aufteilen, planen, features, implementieren
  - User bittet um: Dokumenten-Expansion, Detail-Spezifikation, Feature-Breakdown
  - Plan-Modus ist aktiv (plan mode)
  - TodoWrite mit komplexen Items (>3 erkennbare Subtasks)
  - User fragt: wie implementieren, was brauchen wir, naechste schritte
  - Dokumente wie ROADMAP*.md oder FEATURE*.md werden gelesen
  - Nach Interview/Requirements-Gathering Sessions

  Generiert separate Feature-Dateien mit vollstaendiger Spezifikation:
  API-Specs, DB-Schema, Implementation Tasks, Test-Szenarien.
globs:
  - "**/ROADMAP*.md"
  - "**/FEATURE*.md"
  - "**/PLAN*.md"
  - "**/.claude/plans/**/*"
  - "**/docs/planning/**/*"
alwaysApply: false
---

# Plan Breakdown Skill

Autonome Planzerlegung fuer grosse Features und Roadmaps in detaillierte, ausfuehrbare Spezifikationen.

## Quick Start

```
1. ERKENNUNG
   └─ Plan-Dokument gelesen ODER Plan-Keywords im Input

2. ANALYSE
   ├─ Features aus Dokument extrahieren
   ├─ Prioritaeten identifizieren (P1/P2/P3)
   └─ Abhaengigkeiten ermitteln

3. GENERIERUNG
   ├─ Verzeichnis erstellen: .claude/plans/[plan-name]/
   ├─ PLAN_OVERVIEW.md generieren
   └─ Fuer jedes Feature:
       └─ FEATURE_XX_[name].md mit vollstaendigem Template

4. VALIDIERUNG
   ├─ Jeder Task hat Akzeptanzkriterium
   ├─ Dependencies sind identifiziert
   └─ Deutsche Sprache fuer User-Facing

5. USER INFORMIEREN
   └─ "X Feature-Dateien generiert in .claude/plans/[name]/"
```

---

## Output-Verzeichnis Struktur

```
.claude/plans/[plan-name]/
├── PLAN_OVERVIEW.md              # Haupt-Uebersicht mit Links
├── FEATURE_01_[name].md          # Feature 1 vollstaendig
├── FEATURE_02_[name].md          # Feature 2 vollstaendig
├── FEATURE_03_[name].md          # Feature 3 vollstaendig
└── ...
```

---

## PLAN_OVERVIEW.md Template

```markdown
# Plan: [PLAN_NAME]

> **Status**: In Planung | In Arbeit | Abgeschlossen
> **Erstellt**: YYYY-MM-DD
> **Geschaetzter Gesamtaufwand**: X Wochen
> **Anzahl Features**: X

---

## Executive Summary

[2-3 Saetze die den gesamten Plan zusammenfassen]

---

## Feature-Uebersicht

| # | Feature | Prioritaet | Aufwand | Status | Datei |
|---|---------|------------|---------|--------|-------|
| 01 | [Feature 1] | P1 | 4W | Geplant | [FEATURE_01_*.md](./FEATURE_01_*.md) |
| 02 | [Feature 2] | P1 | 3W | Geplant | [FEATURE_02_*.md](./FEATURE_02_*.md) |
| 03 | [Feature 3] | P2 | 2W | Geplant | [FEATURE_03_*.md](./FEATURE_03_*.md) |

---

## Abhaengigkeiten

```
Feature 01 ─────► Feature 02
     │                │
     │                ▼
     └──────────► Feature 04
```

---

## Zeitplan

### Phase 1: Foundation (Wochen 1-X)
- [ ] Feature 01: [Name]
- [ ] Feature 02: [Name]

### Phase 2: Core (Wochen X-Y)
- [ ] Feature 03: [Name]
- [ ] Feature 04: [Name]

### Phase 3: Polish (Wochen Y-Z)
- [ ] Feature 05: [Name]

---

## Risiken & Mitigationen

| Risiko | Wahrscheinlichkeit | Impact | Mitigation |
|--------|-------------------|--------|------------|
| [Risiko 1] | Mittel | Hoch | [Massnahme] |
| [Risiko 2] | Niedrig | Mittel | [Massnahme] |

---

## Erfolgskriterien

1. [ ] [Messbares Kriterium 1]
2. [ ] [Messbares Kriterium 2]
3. [ ] [Messbares Kriterium 3]
```

---

## FEATURE_XX_[name].md Template

Jede Feature-Datei folgt dieser Struktur:

### 1. Header & Uebersicht

```markdown
# Feature XX: [FEATURE_NAME]

> **Status**: Ready for Implementation
> **Version**: 1.0.0
> **Erstellt**: YYYY-MM-DD
> **Prioritaet**: P1 | P2 | P3
> **Geschaetzter Aufwand**: X Implementierungstage
> **Abhaengigkeiten**: Feature YY, Feature ZZ

---

## Executive Summary

[3-5 Saetze die das Feature beschreiben und den Kernnutzen hervorheben.
Was ist das Problem? Was ist die Loesung? Was ist der Business Value?]

---

## Inhaltsverzeichnis

1. [Anforderungen](#anforderungen)
2. [API-Spezifikation](#api-spezifikation)
3. [Datenbank-Schema](#datenbank-schema)
4. [Implementation Tasks](#implementation-tasks)
5. [Test-Szenarien](#test-szenarien)
6. [Frontend-Komponenten](#frontend-komponenten)
7. [Quality Gates](#quality-gates)
```

### 2. Anforderungen

```markdown
---

## Anforderungen

### Funktionale Anforderungen

| ID | Anforderung | Prioritaet | Akzeptanzkriterium |
|----|-------------|-----------|-------------------|
| FR-01 | [Beschreibung der Anforderung] | MUSS | [Messbares Kriterium] |
| FR-02 | [Beschreibung der Anforderung] | MUSS | [Messbares Kriterium] |
| FR-03 | [Beschreibung der Anforderung] | SOLL | [Messbares Kriterium] |
| FR-04 | [Beschreibung der Anforderung] | KANN | [Messbares Kriterium] |

### Nicht-Funktionale Anforderungen

| ID | Anforderung | Metrik | Akzeptanzkriterium |
|----|-------------|--------|-------------------|
| NFR-01 | Performance | Response Time | < 200ms fuer 95% der Requests |
| NFR-02 | Skalierbarkeit | Concurrent Users | 100+ gleichzeitige Nutzer |
| NFR-03 | Sicherheit | Compliance | GDPR-konform, GoBD-konform |
| NFR-04 | Verfuegbarkeit | Uptime | 99.5% |

### Abgrenzung (Out of Scope)

- [Was NICHT Teil dieses Features ist]
- [Explizite Ausschluesse]
```

### 3. API-Spezifikation

```markdown
---

## API-Spezifikation

### Endpoints Uebersicht

| Method | Endpoint | Beschreibung | Auth |
|--------|----------|--------------|------|
| POST | `/api/v1/[resource]` | Erstellt neuen Eintrag | Required |
| GET | `/api/v1/[resource]` | Listet alle Eintraege | Required |
| GET | `/api/v1/[resource]/{id}` | Holt einzelnen Eintrag | Required |
| PUT | `/api/v1/[resource]/{id}` | Aktualisiert Eintrag | Required |
| DELETE | `/api/v1/[resource]/{id}` | Loescht Eintrag (Soft) | Required |

---

### `POST /api/v1/[resource]`

**Beschreibung**: Erstellt einen neuen [Resource] Eintrag.

**Request Headers:**
```
Authorization: Bearer <token>
Content-Type: application/json
X-Company-ID: <company_uuid>
```

**Request Body:**
```json
{
  "name": "string (required, 1-255 chars)",
  "code": "string (optional, unique, max 50 chars)",
  "description": "string (optional)",
  "config": {
    "option1": true,
    "option2": "value"
  },
  "parent_id": "uuid (optional)"
}
```

**Response (201 Created):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Example Entry",
  "code": "EX001",
  "description": null,
  "config": {
    "option1": true,
    "option2": "value"
  },
  "parent_id": null,
  "company_id": "company-uuid",
  "is_active": true,
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z",
  "created_by": {
    "id": "user-uuid",
    "name": "Max Mustermann"
  }
}
```

**Fehler-Responses:**

| Code | Beschreibung | Body |
|------|--------------|------|
| 400 | Validierungsfehler | `{"detail": "Validierungsfehler", "errors": [...]}` |
| 401 | Nicht authentifiziert | `{"detail": "Nicht authentifiziert"}` |
| 403 | Keine Berechtigung | `{"detail": "Keine Berechtigung fuer diese Aktion"}` |
| 409 | Konflikt (Duplikat) | `{"detail": "Code bereits vergeben"}` |
| 422 | Unprocessable Entity | `{"detail": "..."}` |

---

### `GET /api/v1/[resource]`

**Query Parameters:**

| Parameter | Typ | Default | Beschreibung |
|-----------|-----|---------|--------------|
| skip | int | 0 | Offset fuer Pagination |
| limit | int | 50 | Max. Anzahl (1-100) |
| search | string | - | Volltextsuche |
| is_active | bool | true | Aktiv-Filter |
| parent_id | uuid | - | Filter nach Parent |
| sort_by | string | created_at | Sortierfeld |
| sort_order | string | desc | asc oder desc |

**Response (200 OK):**
```json
{
  "items": [...],
  "total": 150,
  "skip": 0,
  "limit": 50,
  "has_more": true
}
```

---

### `GET /api/v1/[resource]/{id}`

**Response (200 OK):** Einzelnes Objekt wie bei POST Response.

**Response (404 Not Found):**
```json
{
  "detail": "Eintrag nicht gefunden"
}
```

---

### `PUT /api/v1/[resource]/{id}`

**Request Body:** Alle Felder optional (Partial Update)
```json
{
  "name": "Updated Name",
  "is_active": false
}
```

**Response (200 OK):** Aktualisiertes Objekt.

---

### `DELETE /api/v1/[resource]/{id}`

**Response (204 No Content):** Erfolgreich geloescht (Soft Delete).

**Response (404 Not Found):** Eintrag nicht gefunden.
```

### 4. Datenbank-Schema

```markdown
---

## Datenbank-Schema

### Neue Tabellen

#### `[table_name]`

```sql
-- Migration: XXXX_create_[table_name].py

CREATE TABLE [table_name] (
    -- Primary Key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identifikation
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) UNIQUE,
    description TEXT,

    -- Beziehungen
    parent_id UUID REFERENCES [table_name](id) ON DELETE SET NULL,
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE NOT NULL,

    -- Daten
    config JSONB DEFAULT '{}',

    -- Status
    is_active BOOLEAN DEFAULT true NOT NULL,

    -- Audit Fields (Standard fuer alle Tabellen)
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    created_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
    updated_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
    deleted_at TIMESTAMPTZ,  -- Soft Delete

    -- Constraints
    CONSTRAINT [table_name]_name_company_unique UNIQUE (name, company_id)
);

-- Indizes
CREATE INDEX ix_[table_name]_company ON [table_name](company_id);
CREATE INDEX ix_[table_name]_parent ON [table_name](parent_id);
CREATE INDEX ix_[table_name]_active ON [table_name](is_active) WHERE deleted_at IS NULL;
CREATE INDEX ix_[table_name]_code ON [table_name](code) WHERE code IS NOT NULL;
CREATE INDEX ix_[table_name]_created ON [table_name](created_at DESC);

-- Trigger fuer updated_at
CREATE TRIGGER update_[table_name]_updated_at
    BEFORE UPDATE ON [table_name]
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Row Level Security (Multi-Tenant)
ALTER TABLE [table_name] ENABLE ROW LEVEL SECURITY;

CREATE POLICY [table_name]_company_isolation ON [table_name]
    USING (company_id = current_setting('app.current_company_id')::UUID);
```

### Alembic Migration

```python
"""Create [table_name] table

Revision ID: XXXX
Revises: [previous_revision]
Create Date: YYYY-MM-DD HH:MM:SS
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'XXXX'
down_revision = '[previous]'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        '[table_name]',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('code', sa.String(50), unique=True),
        sa.Column('description', sa.Text()),
        sa.Column('parent_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('[table_name].id', ondelete='SET NULL')),
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('config', postgresql.JSONB, server_default='{}'),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()'), nullable=False),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('updated_by_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('deleted_at', sa.DateTime(timezone=True)),
    )

    # Indizes
    op.create_index('ix_[table_name]_company', '[table_name]', ['company_id'])
    op.create_index('ix_[table_name]_parent', '[table_name]', ['parent_id'])
    op.create_index('ix_[table_name]_active', '[table_name]', ['is_active'],
                    postgresql_where=sa.text('deleted_at IS NULL'))


def downgrade() -> None:
    op.drop_table('[table_name]')
```

### SQLAlchemy Model

```python
# app/db/models/[module].py

"""[Module] Models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional, Any

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, String, Text, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, SoftDeleteMixin

if TYPE_CHECKING:
    from app.db.models import User, Company


class [ModelName](Base, TimestampMixin, SoftDeleteMixin):
    """[Beschreibung des Models]."""

    __tablename__ = "[table_name]"
    __table_args__ = (
        UniqueConstraint('name', 'company_id', name='[table_name]_name_company_unique'),
        Index("ix_[table_name]_company", "company_id"),
        Index("ix_[table_name]_parent", "parent_id"),
    )

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Identifikation
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String(50), unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Beziehungen (Foreign Keys)
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("[table_name].id", ondelete="SET NULL")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )

    # Daten
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    company: Mapped["Company"] = relationship(back_populates="[relation_name]")
    parent: Mapped[Optional["[ModelName]"]] = relationship(
        back_populates="children", remote_side=[id]
    )
    children: Mapped[list["[ModelName]"]] = relationship(back_populates="parent")
    created_by: Mapped[Optional["User"]] = relationship(
        foreign_keys="[[ModelName].created_by_id]"
    )

    def __repr__(self) -> str:
        return f"<[ModelName](id={self.id}, name='{self.name}')>"
```

### Pydantic Schemas

```python
# app/api/schemas/[module].py

"""Pydantic Schemas fuer [Module]."""

from datetime import datetime
from typing import Optional, Any
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict, field_validator


class [ModelName]Base(BaseModel):
    """Basis-Schema fuer [ModelName]."""

    name: str = Field(..., min_length=1, max_length=255, description="Name des Eintrags")
    code: Optional[str] = Field(None, max_length=50, description="Eindeutiger Code")
    description: Optional[str] = Field(None, description="Beschreibung")
    config: dict[str, Any] = Field(default_factory=dict, description="Konfiguration")
    parent_id: Optional[UUID] = Field(None, description="Parent-ID fuer Hierarchie")

    @field_validator('code')
    @classmethod
    def validate_code(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            # Nur alphanumerisch + Unterstrich
            if not v.replace('_', '').replace('-', '').isalnum():
                raise ValueError('Code darf nur alphanumerische Zeichen enthalten')
        return v


class [ModelName]Create([ModelName]Base):
    """Schema fuer Erstellung."""
    pass


class [ModelName]Update(BaseModel):
    """Schema fuer Updates (alle Felder optional)."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    code: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = None
    config: Optional[dict[str, Any]] = None
    parent_id: Optional[UUID] = None
    is_active: Optional[bool] = None


class [ModelName]Response([ModelName]Base):
    """Response-Schema mit allen Feldern."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by_id: Optional[UUID] = None


class [ModelName]ListResponse(BaseModel):
    """Paginierte Liste."""

    items: list[[ModelName]Response]
    total: int
    skip: int
    limit: int
    has_more: bool = False
```
```

### 5. Implementation Tasks

```markdown
---

## Implementation Tasks

### Phase 1: Datenbank & Models (X Tage)

| # | Task | Beschreibung | Akzeptanzkriterium | Abhaengigkeit |
|---|------|--------------|-------------------|---------------|
| 1.1 | [ ] Migration erstellen | Alembic Migration fuer neue Tabelle(n) | Migration laeuft fehlerfrei (up & down) | - |
| 1.2 | [ ] SQLAlchemy Model | Model mit Relationships definieren | mypy --strict clean | 1.1 |
| 1.3 | [ ] Pydantic Schemas | Create/Update/Response Schemas | Validierung funktioniert korrekt | 1.2 |
| 1.4 | [ ] DB Tests | Repository Tests schreiben | Coverage >80% | 1.3 |

### Phase 2: Business Logic (X Tage)

| # | Task | Beschreibung | Akzeptanzkriterium | Abhaengigkeit |
|---|------|--------------|-------------------|---------------|
| 2.1 | [ ] Service erstellen | CRUD + Business Logic | Unit Tests >80% Coverage | 1.4 |
| 2.2 | [ ] Business Rules | Validierung, Berechtigungen | Edge Cases behandelt | 2.1 |
| 2.3 | [ ] Events/Hooks | Benachrichtigungen, Audit-Logs | Events werden gefeuert | 2.2 |
| 2.4 | [ ] Error Handling | Custom Exceptions | Deutsche Fehlermeldungen | 2.3 |

### Phase 3: API Layer (X Tage)

| # | Task | Beschreibung | Akzeptanzkriterium | Abhaengigkeit |
|---|------|--------------|-------------------|---------------|
| 3.1 | [ ] Router erstellen | FastAPI Endpoints | OpenAPI Spec generiert | 2.4 |
| 3.2 | [ ] Berechtigungen | RBAC Integration | 403 bei fehlendem Zugriff | 3.1 |
| 3.3 | [ ] Rate Limiting | Throttling konfigurieren | Limits greifen korrekt | 3.2 |
| 3.4 | [ ] API Tests | Integration Tests | Alle Endpoints getestet | 3.3 |

### Phase 4: Frontend (X Tage)

| # | Task | Beschreibung | Akzeptanzkriterium | Abhaengigkeit |
|---|------|--------------|-------------------|---------------|
| 4.1 | [ ] TypeScript Types | Interfaces + Enums | Keine any-Types | 3.4 |
| 4.2 | [ ] API Client | TanStack Query Hooks | Caching funktioniert | 4.1 |
| 4.3 | [ ] Komponenten | UI Components (shadcn/ui) | Alle 4 Display-Modi | 4.2 |
| 4.4 | [ ] Seiten/Routes | TanStack Router Pages | Navigation funktioniert | 4.3 |
| 4.5 | [ ] Formulare | Create/Edit Forms | Validierung client-side | 4.4 |

### Phase 5: Testing & Dokumentation (X Tage)

| # | Task | Beschreibung | Akzeptanzkriterium | Abhaengigkeit |
|---|------|--------------|-------------------|---------------|
| 5.1 | [ ] Unit Tests | pytest komplett | Coverage >80% | 4.5 |
| 5.2 | [ ] Integration Tests | E2E API Flow | Happy Path + Error Cases | 5.1 |
| 5.3 | [ ] E2E Tests | Playwright Browser Tests | Kritische Flows getestet | 5.2 |
| 5.4 | [ ] API Docs | OpenAPI aktualisieren | Swagger UI funktioniert | 5.3 |
| 5.5 | [ ] User Docs | Anleitung schreiben | Deutsche Dokumentation | 5.4 |

---

### Task-Details Template

Fuer komplexe Tasks, verwende dieses Format:

```markdown
#### Task X.Y: [Task Name]

**Beschreibung:**
[Detaillierte Beschreibung was zu tun ist]

**Dateien:**
- `app/services/[module]_service.py` (neu)
- `app/api/v1/[module].py` (neu)
- `tests/unit/services/test_[module]_service.py` (neu)

**Schritte:**
1. [ ] Schritt 1
2. [ ] Schritt 2
3. [ ] Schritt 3

**Akzeptanzkriterien:**
- [ ] Kriterium 1
- [ ] Kriterium 2

**Notizen:**
[Besonderheiten, Warnungen, Referenzen]
```
```

### 6. Test-Szenarien

```markdown
---

## Test-Szenarien

### Unit Tests

```python
# tests/unit/services/test_[module]_service.py

"""Unit Tests fuer [Module] Service."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.services.[module]_service import [ModelName]Service
from app.api.schemas.[module] import [ModelName]Create, [ModelName]Update


@pytest.fixture
def mock_db():
    """Mock Database Session."""
    return AsyncMock()


@pytest.fixture
def service(mock_db):
    """Service Instance mit Mock DB."""
    return [ModelName]Service(mock_db)


@pytest.fixture
def sample_create_data():
    """Beispiel-Daten fuer Erstellung."""
    return [ModelName]Create(
        name="Test Entry",
        code="TEST001",
        description="Eine Testbeschreibung"
    )


class TestCreate:
    """Tests fuer create() Methode."""

    @pytest.mark.asyncio
    async def test_create_success(self, service, sample_create_data):
        """Erfolgreiche Erstellung eines Eintrags."""
        company_id = uuid4()
        user_id = uuid4()

        result = await service.create(company_id, user_id, sample_create_data)

        assert result.name == sample_create_data.name
        assert result.code == sample_create_data.code
        assert result.company_id == company_id

    @pytest.mark.asyncio
    async def test_create_duplicate_code_fails(self, service, sample_create_data):
        """Duplikater Code wirft IntegrityError."""
        # First creation succeeds
        await service.create(uuid4(), uuid4(), sample_create_data)

        # Second creation with same code should fail
        with pytest.raises(IntegrityError):
            await service.create(uuid4(), uuid4(), sample_create_data)

    @pytest.mark.asyncio
    async def test_create_with_parent(self, service, sample_create_data):
        """Erstellung mit Parent-Beziehung."""
        parent_id = uuid4()
        sample_create_data.parent_id = parent_id

        result = await service.create(uuid4(), uuid4(), sample_create_data)

        assert result.parent_id == parent_id


class TestGetById:
    """Tests fuer get_by_id() Methode."""

    @pytest.mark.asyncio
    async def test_get_existing_entry(self, service):
        """Vorhandener Eintrag wird gefunden."""
        entry_id = uuid4()
        company_id = uuid4()

        result = await service.get_by_id(company_id, entry_id)

        assert result is not None
        assert result.id == entry_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, service):
        """Nicht vorhandener Eintrag gibt None zurueck."""
        result = await service.get_by_id(uuid4(), uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_get_wrong_company_returns_none(self, service):
        """Eintrag einer anderen Firma gibt None zurueck (Isolation)."""
        # Entry exists but belongs to different company
        result = await service.get_by_id(uuid4(), uuid4())

        assert result is None


class TestUpdate:
    """Tests fuer update() Methode."""

    @pytest.mark.asyncio
    async def test_partial_update(self, service):
        """Partial Update aendert nur angegebene Felder."""
        update_data = [ModelName]Update(name="New Name")

        result = await service.update(uuid4(), uuid4(), update_data)

        assert result.name == "New Name"
        # Other fields unchanged

    @pytest.mark.asyncio
    async def test_update_nonexistent_raises(self, service):
        """Update auf nicht existierenden Eintrag wirft NotFoundError."""
        with pytest.raises(NotFoundError):
            await service.update(uuid4(), uuid4(), [ModelName]Update(name="X"))


class TestDelete:
    """Tests fuer delete() Methode (Soft Delete)."""

    @pytest.mark.asyncio
    async def test_soft_delete_sets_deleted_at(self, service):
        """Soft Delete setzt deleted_at Timestamp."""
        entry_id = uuid4()

        await service.delete(uuid4(), entry_id)

        # Entry should have deleted_at set
        result = await service.get_by_id_include_deleted(uuid4(), entry_id)
        assert result.deleted_at is not None

    @pytest.mark.asyncio
    async def test_deleted_entry_not_in_list(self, service):
        """Geloeschte Eintraege erscheinen nicht in Listen."""
        await service.delete(uuid4(), uuid4())

        results = await service.list(uuid4())

        # Deleted entry should not be in results
        assert len([r for r in results.items if r.deleted_at]) == 0
```

### Integration Tests

```python
# tests/integration/test_[module]_api.py

"""Integration Tests fuer [Module] API."""

import pytest
from httpx import AsyncClient
from uuid import uuid4

from app.main import app
from tests.conftest import get_auth_headers


@pytest.mark.integration
class TestCRUDWorkflow:
    """Vollstaendiger CRUD-Workflow Test."""

    @pytest.mark.asyncio
    async def test_full_crud_lifecycle(self, async_client: AsyncClient, auth_headers):
        """Testet Create → Read → Update → Delete Zyklus."""

        # CREATE
        create_response = await async_client.post(
            "/api/v1/[module]/",
            json={
                "name": "Integration Test Entry",
                "code": f"INT{uuid4().hex[:6].upper()}",
                "description": "Created by integration test"
            },
            headers=auth_headers
        )
        assert create_response.status_code == 201
        created = create_response.json()
        entry_id = created["id"]
        assert created["name"] == "Integration Test Entry"

        # READ (single)
        get_response = await async_client.get(
            f"/api/v1/[module]/{entry_id}",
            headers=auth_headers
        )
        assert get_response.status_code == 200
        assert get_response.json()["id"] == entry_id

        # READ (list)
        list_response = await async_client.get(
            "/api/v1/[module]/",
            headers=auth_headers
        )
        assert list_response.status_code == 200
        assert any(item["id"] == entry_id for item in list_response.json()["items"])

        # UPDATE
        update_response = await async_client.put(
            f"/api/v1/[module]/{entry_id}",
            json={"name": "Updated Name"},
            headers=auth_headers
        )
        assert update_response.status_code == 200
        assert update_response.json()["name"] == "Updated Name"

        # DELETE
        delete_response = await async_client.delete(
            f"/api/v1/[module]/{entry_id}",
            headers=auth_headers
        )
        assert delete_response.status_code == 204

        # VERIFY DELETED (should 404)
        verify_response = await async_client.get(
            f"/api/v1/[module]/{entry_id}",
            headers=auth_headers
        )
        assert verify_response.status_code == 404


@pytest.mark.integration
class TestValidation:
    """Validierungs-Tests."""

    @pytest.mark.asyncio
    async def test_create_invalid_name_fails(self, async_client, auth_headers):
        """Leerer Name wird abgelehnt."""
        response = await async_client.post(
            "/api/v1/[module]/",
            json={"name": "", "code": "EMPTY"},
            headers=auth_headers
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_duplicate_code_fails(self, async_client, auth_headers):
        """Duplikater Code wird abgelehnt."""
        code = f"DUP{uuid4().hex[:6].upper()}"

        # First creation succeeds
        await async_client.post(
            "/api/v1/[module]/",
            json={"name": "First", "code": code},
            headers=auth_headers
        )

        # Second creation with same code fails
        response = await async_client.post(
            "/api/v1/[module]/",
            json={"name": "Second", "code": code},
            headers=auth_headers
        )
        assert response.status_code == 409


@pytest.mark.integration
class TestAuthorization:
    """Berechtigungs-Tests."""

    @pytest.mark.asyncio
    async def test_unauthenticated_request_fails(self, async_client):
        """Anfrage ohne Auth-Header wird abgelehnt."""
        response = await async_client.get("/api/v1/[module]/")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_cross_company_access_denied(
        self, async_client, auth_headers, other_company_entry_id
    ):
        """Zugriff auf Eintraege anderer Firma wird verweigert."""
        response = await async_client.get(
            f"/api/v1/[module]/{other_company_entry_id}",
            headers=auth_headers
        )
        assert response.status_code == 404  # Not 403 to avoid info leakage
```

### E2E Tests (Playwright)

```typescript
// tests/e2e/[module].spec.ts

import { test, expect } from '@playwright/test';

test.describe('[Module] Feature', () => {

  test.beforeEach(async ({ page }) => {
    // Login
    await page.goto('/login');
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="password"]', 'testpassword');
    await page.click('button[type="submit"]');
    await page.waitForURL('/dashboard');
  });

  test('Benutzer kann neuen Eintrag erstellen', async ({ page }) => {
    // Navigate to module
    await page.goto('/[module]');

    // Open create dialog
    await page.click('button:has-text("Neu")');

    // Fill form
    await page.fill('input[name="name"]', 'E2E Test Eintrag');
    await page.fill('input[name="code"]', 'E2ETEST');
    await page.fill('textarea[name="description"]', 'Erstellt durch E2E Test');

    // Submit
    await page.click('button:has-text("Speichern")');

    // Verify success
    await expect(page.locator('text=Erfolgreich erstellt')).toBeVisible();
    await expect(page.locator('text=E2E Test Eintrag')).toBeVisible();
  });

  test('Benutzer kann Eintrag bearbeiten', async ({ page }) => {
    await page.goto('/[module]');

    // Click on existing entry
    await page.click('tr:has-text("E2E Test Eintrag")');

    // Click edit button
    await page.click('button:has-text("Bearbeiten")');

    // Update name
    await page.fill('input[name="name"]', 'Aktualisierter Eintrag');

    // Save
    await page.click('button:has-text("Speichern")');

    // Verify
    await expect(page.locator('text=Erfolgreich aktualisiert')).toBeVisible();
    await expect(page.locator('text=Aktualisierter Eintrag')).toBeVisible();
  });

  test('Benutzer kann Eintrag loeschen', async ({ page }) => {
    await page.goto('/[module]');

    // Click on entry
    await page.click('tr:has-text("Aktualisierter Eintrag")');

    // Click delete
    await page.click('button:has-text("Loeschen")');

    // Confirm dialog
    await page.click('button:has-text("Ja, loeschen")');

    // Verify
    await expect(page.locator('text=Erfolgreich geloescht')).toBeVisible();
    await expect(page.locator('text=Aktualisierter Eintrag')).not.toBeVisible();
  });

  test('Validierung zeigt Fehlermeldungen', async ({ page }) => {
    await page.goto('/[module]');

    // Open create dialog
    await page.click('button:has-text("Neu")');

    // Submit without filling required fields
    await page.click('button:has-text("Speichern")');

    // Check for validation messages
    await expect(page.locator('text=Name ist erforderlich')).toBeVisible();
  });

  test('Display-Modi funktionieren korrekt', async ({ page }) => {
    await page.goto('/[module]');

    // Test each display mode
    const modes = ['dark', 'light', 'whitescreen', 'blackscreen'];

    for (const mode of modes) {
      await page.click('[data-testid="theme-toggle"]');
      await page.click(`[data-testid="theme-${mode}"]`);

      // Take screenshot for visual verification
      await page.screenshot({ path: `test-results/[module]-${mode}.png` });

      // Verify mode is applied
      const body = page.locator('body');
      await expect(body).toHaveAttribute('data-theme', mode);
    }
  });

  test('Deutsche Umlaute werden korrekt verarbeitet', async ({ page }) => {
    await page.goto('/[module]');

    // Create entry with German special characters
    await page.click('button:has-text("Neu")');
    await page.fill('input[name="name"]', 'Müller-Strauß GmbH');
    await page.fill('input[name="description"]', 'Größenordnung: 5m², €1.234,56');
    await page.click('button:has-text("Speichern")');

    // Verify correct display
    await expect(page.locator('text=Müller-Strauß GmbH')).toBeVisible();
    await expect(page.locator('text=Größenordnung')).toBeVisible();
    await expect(page.locator('text=€1.234,56')).toBeVisible();
  });
});
```
```

### 7. Frontend-Komponenten

```markdown
---

## Frontend-Komponenten

### TypeScript Types

```typescript
// frontend/src/types/models/[module].ts

/**
 * [Module] TypeScript Types
 */

// ============ Enums ============

export type [ModelName]Status = 'active' | 'inactive' | 'archived';


// ============ Models ============

export interface [ModelName] {
  id: string;
  name: string;
  code?: string;
  description?: string;
  config: Record<string, unknown>;
  parentId?: string;
  companyId: string;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
  createdById?: string;
}


// ============ API Request Types ============

export interface [ModelName]CreateRequest {
  name: string;
  code?: string;
  description?: string;
  config?: Record<string, unknown>;
  parentId?: string;
}

export interface [ModelName]UpdateRequest {
  name?: string;
  code?: string;
  description?: string;
  config?: Record<string, unknown>;
  parentId?: string;
  isActive?: boolean;
}


// ============ API Response Types ============

export interface [ModelName]ListResponse {
  items: [ModelName][];
  total: number;
  skip: number;
  limit: number;
  hasMore: boolean;
}


// ============ Query Parameters ============

export interface [ModelName]QueryParams {
  skip?: number;
  limit?: number;
  search?: string;
  isActive?: boolean;
  parentId?: string;
  sortBy?: string;
  sortOrder?: 'asc' | 'desc';
}
```

### TanStack Query Hooks

```typescript
// frontend/src/features/[module]/api/[module]-api.ts

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type {
  [ModelName],
  [ModelName]CreateRequest,
  [ModelName]UpdateRequest,
  [ModelName]ListResponse,
  [ModelName]QueryParams,
} from '@/types/models/[module]';

const QUERY_KEY = '[module]';

// ============ Query Hooks ============

export function use[ModelName]List(params?: [ModelName]QueryParams) {
  return useQuery({
    queryKey: [QUERY_KEY, 'list', params],
    queryFn: async () => {
      const response = await api.get<[ModelName]ListResponse>(
        '/api/v1/[module]/',
        { params }
      );
      return response.data;
    },
  });
}

export function use[ModelName](id: string) {
  return useQuery({
    queryKey: [QUERY_KEY, 'detail', id],
    queryFn: async () => {
      const response = await api.get<[ModelName]>(`/api/v1/[module]/${id}`);
      return response.data;
    },
    enabled: !!id,
  });
}


// ============ Mutation Hooks ============

export function useCreate[ModelName]() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: [ModelName]CreateRequest) => {
      const response = await api.post<[ModelName]>('/api/v1/[module]/', data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY] });
    },
  });
}

export function useUpdate[ModelName]() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, data }: { id: string; data: [ModelName]UpdateRequest }) => {
      const response = await api.put<[ModelName]>(`/api/v1/[module]/${id}`, data);
      return response.data;
    },
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY] });
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY, 'detail', id] });
    },
  });
}

export function useDelete[ModelName]() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/v1/[module]/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY] });
    },
  });
}
```

### Komponenten-Uebersicht

```
frontend/src/features/[module]/
├── api/
│   └── [module]-api.ts          # TanStack Query Hooks
├── components/
│   ├── [ModelName]List.tsx      # Tabellen-Ansicht
│   ├── [ModelName]Detail.tsx    # Detail-Ansicht
│   ├── [ModelName]Form.tsx      # Create/Edit Formular
│   ├── [ModelName]Dialog.tsx    # Modal Dialog
│   └── [ModelName]Filters.tsx   # Filter-Komponente
├── pages/
│   ├── [ModelName]ListPage.tsx  # Listen-Seite
│   └── [ModelName]DetailPage.tsx # Detail-Seite
└── index.ts                      # Exports
```
```

### 8. Quality Gates

```markdown
---

## Quality Gates

### Vor PR-Erstellung

- [ ] **Code Qualitaet**
  - [ ] mypy --strict clean (keine Type-Errors)
  - [ ] ruff check . clean (keine Linting-Errors)
  - [ ] TypeScript kompiliert fehlerfrei (tsc --noEmit)
  - [ ] ESLint clean

- [ ] **Testing**
  - [ ] Unit Tests geschrieben und bestanden
  - [ ] Coverage >80% fuer neue Code
  - [ ] Integration Tests fuer API Endpoints
  - [ ] E2E Tests fuer kritische User Flows

- [ ] **Sicherheit**
  - [ ] Keine Secrets im Code
  - [ ] Input-Validierung vorhanden
  - [ ] SQL Injection geschuetzt (SQLAlchemy)
  - [ ] XSS geschuetzt (React escaping)
  - [ ] CSRF geschuetzt

- [ ] **Performance**
  - [ ] API Response Time <200ms
  - [ ] Keine N+1 Query Probleme
  - [ ] Pagination implementiert

- [ ] **Dokumentation**
  - [ ] Docstrings fuer alle public Functions
  - [ ] OpenAPI Spec aktualisiert
  - [ ] README falls noetig

### Vor Merge

- [ ] **Review**
  - [ ] Code Review durch mindestens 1 Person
  - [ ] Alle Review-Kommentare adressiert

- [ ] **UI/UX**
  - [ ] Alle 4 Display-Modi getestet (dark, light, whitescreen, blackscreen)
  - [ ] Responsive Design geprueft
  - [ ] Deutsche Texte fuer User-Facing
  - [ ] Umlaute korrekt dargestellt (ae, oe, ue, ss → ä, ö, ü, ß)

- [ ] **CI/CD**
  - [ ] Alle CI Checks bestanden
  - [ ] Branch ist up-to-date mit main

### Definition of Done

Dieses Feature gilt als fertig wenn:

1. [ ] Alle funktionalen Anforderungen (FR-*) erfuellt
2. [ ] Alle nicht-funktionalen Anforderungen (NFR-*) erfuellt
3. [ ] Alle Quality Gates bestanden
4. [ ] Dokumentation vollstaendig
5. [ ] In Staging-Umgebung getestet
6. [ ] Product Owner hat abgenommen
```

---

## Checkliste fuer Feature-Generierung

Wenn ein neues Feature generiert wird, stelle sicher:

| Check | Beschreibung |
|-------|--------------|
| [ ] Header vollstaendig | Status, Version, Prioritaet, Aufwand, Abhaengigkeiten |
| [ ] Anforderungen strukturiert | FR-XX und NFR-XX Format mit Akzeptanzkriterien |
| [ ] API vollstaendig | Alle CRUD Endpoints mit Request/Response |
| [ ] DB Schema vorhanden | CREATE TABLE, Indizes, Migration |
| [ ] Tasks haben Akzeptanzkriterien | Jeder Task messbar |
| [ ] Tests definiert | Unit, Integration, E2E |
| [ ] Frontend spezifiziert | Types, Hooks, Komponenten |
| [ ] Quality Gates klar | Checkliste vor Merge |
| [ ] Deutsche Sprache | User-Facing Content auf Deutsch |
| [ ] Abhaengigkeiten identifiziert | Was muss vorher fertig sein |
