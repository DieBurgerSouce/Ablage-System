# Feature XX: [NAME]

> **Status**: Template - Replace all [placeholders]
> **Version**: 1.0.0
> **Priorit\u00e4t**: [P1/P2/P3]
> **Gesch\u00e4tzter Aufwand**: [X Wochen]
> **Abh\u00e4ngigkeiten**: [Feature YY, Feature ZZ]
> **Typ**: Database / Schema

---

## \u00dcbersicht

[Kurze Beschreibung der DB-\u00c4nderungen - 2-3 S\u00e4tze]

## Schema-Definitionen

### Tabellen

```sql
-- [Table 1]
CREATE TABLE [table_name] (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    [field1] VARCHAR(255) NOT NULL,
    [field2] INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    deleted_at TIMESTAMP NULL  -- Soft delete

    CONSTRAINT [constraint_name] UNIQUE([field1])
);

-- Indizes
CREATE INDEX idx_[table]_[field] ON [table_name]([field]);
CREATE INDEX idx_[table]_created ON [table_name](created_at);
```

### Relationen

```sql
ALTER TABLE [table_name]
ADD CONSTRAINT fk_[name]
FOREIGN KEY ([foreign_key])
REFERENCES [other_table](id)
ON DELETE CASCADE;
```

## SQLAlchemy Models

```python
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base_class import Base

class [ModelName](Base):
    __tablename__ = "[table_name]"

    id = Column(UUID, primary_key=True, server_default=text("gen_random_uuid()"))
    [field1] = Column(String(255), nullable=False)
    [field2] = Column(Integer)
    created_at = Column(DateTime, server_default=text("NOW()"))
    updated_at = Column(DateTime, server_default=text("NOW()"), onupdate=text("NOW()"))

    # Relationships
    [related] = relationship("[RelatedModel]", back_populates="[this]")
```

## Pydantic Schemas

```python
from pydantic import BaseModel
from datetime import datetime

class [ModelName]Base(BaseModel):
    [field1]: str
    [field2]: int | None = None

class [ModelName]Create([ModelName]Base):
    pass

class [ModelName]Update([ModelName]Base):
    [field1]: str | None = None

class [ModelName]InDB([ModelName]Base):
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
```

## Migrations

### Alembic Migration

```python
\"\"\"[Migration description]

Revision ID: [revision_id]
Revises: [previous_revision]
Create Date: [date]
\"\"\"
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table(
        '[table_name]',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('[field1]', sa.String(255), nullable=False),
        # ...
        sa.PrimaryKeyConstraint('id')
    )

def downgrade():
    op.drop_table('[table_name]')
```

## Indizierungs-Strategie

| Index | Spalte(n) | Typ | Grund |
|-------|-----------|-----|-------|
| idx_[name] | [column] | B-Tree | [Beschreibung] |
| idx_[name]_gin | [column] | GIN | Full-text search |

## Performance

- **Erwartete Gr\u00f6\u00dfe**: [X Mio Rows]
- **Wachstum**: [X Rows/Tag]
- **Query Performance**: [Target < X ms]

## Tests

### Schema Tests

```python
def test_[model]_create():
    # Test object creation
    pass

def test_[model]_relationships():
    # Test relationships work
    pass
```

## Implementation Tasks

| # | Task | Status | Assignee |
|---|------|--------|----------|
| 1 | Migration schreiben | Pending | - |
| 2 | SQLAlchemy Models | Pending | - |
| 3 | Pydantic Schemas | Pending | - |
| 4 | Indizes erstellen | Pending | - |
| 5 | Tests schreiben | Pending | - |
| 6 | Performance testen | Pending | - |

## Rollback Strategy

```sql
-- Rollback steps
DROP TABLE IF EXISTS [table_name];
```

## Quality Gates

- [ ] Migration tested (up & down)
- [ ] Models tested
- [ ] Indexes verified
- [ ] Performance targets met
- [ ] Data validation working
