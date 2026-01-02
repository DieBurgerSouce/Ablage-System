# Feature 02: GoBD-Zertifizierung

> **Status**: Ready for Implementation
> **Version**: 1.0.0
> **Erstellt**: 2026-01-02
> **Prioritaet**: P1 - Kritisch
> **Geschaetzter Aufwand**: 3-4 Wochen
> **Abhaengigkeiten**: Feature 01 (Multi-Firma)

---

## Executive Summary

Die GoBD-Zertifizierung (Grundsaetze zur ordnungsmaessigen Fuehrung und Aufbewahrung von Buechern, Aufzeichnungen und Unterlagen in elektronischer Form) ist eine rechtliche Notwendigkeit fuer alle steuerrelevanten Dokumente. Dieses Feature implementiert revisionssichere Archivierung, automatische Verfahrensdokumentation und Aufbewahrungsfristen-Management.

**Business Value:**
- Rechtliche Absicherung bei Betriebspruefungen
- Automatische Compliance ohne manuellen Aufwand
- Steuerberater-Zugang fuer effiziente Zusammenarbeit
- Basis fuer offizielle GoBD-Zertifizierung

---

## Inhaltsverzeichnis

1. [Anforderungen](#anforderungen)
2. [API-Spezifikation](#api-spezifikation)
3. [Datenbank-Schema](#datenbank-schema)
4. [Implementation Tasks](#implementation-tasks)
5. [Test-Szenarien](#test-szenarien)
6. [Quality Gates](#quality-gates)

---

## Anforderungen

### Funktionale Anforderungen

| ID | Anforderung | Prioritaet | Akzeptanzkriterium |
|----|-------------|-----------|-------------------|
| FR-01 | Dokumente werden nach Archivierung unveraenderbar | MUSS | Hash-Signatur bei Archivierung, keine Aenderung moeglich |
| FR-02 | Automatische Verfahrensdokumentation | MUSS | Dokument wird automatisch generiert und aktuell gehalten |
| FR-03 | Aufbewahrungsfristen-Management | MUSS | Warnung X Tage vor Ablauf, optionale Auto-Loeschung |
| FR-04 | Steuerberater-Rolle | MUSS | Read-Only Zugang, zeitlich begrenzbar |
| FR-05 | Vollstaendiger Audit-Trail | MUSS | Alle Aktionen nachvollziehbar |
| FR-06 | Zeitstempel-Signatur | SOLL | Qualifizierte Signatur oder Blockchain-Hash |
| FR-07 | Export fuer Pruefung | SOLL | GoBD-konformer Export (GDPDU/GDPdU) |

### Nicht-Funktionale Anforderungen

| ID | Anforderung | Metrik | Akzeptanzkriterium |
|----|-------------|--------|-------------------|
| NFR-01 | Unveraenderbarkeit | Integritaet | Kein Dokument nach Archivierung aenderbar |
| NFR-02 | Aufbewahrung | Dauer | 10+ Jahre ohne Datenverlust |
| NFR-03 | Nachvollziehbarkeit | Audit | Jede Aktion mit Timestamp + User |
| NFR-04 | Performance | Signatur | < 1s pro Dokument |

### GoBD-Anforderungen Mapping

| GoBD-Kriterium | Status | Implementierung |
|----------------|--------|-----------------|
| Nachvollziehbarkeit | Vorhanden | Audit-Logs (erweitern) |
| Nachpruefbarkeit | Teilweise | Verfahrensdokumentation |
| Unveraenderbarkeit | Fehlt | Hash-Signatur System |
| Vollstaendigkeit | Vorhanden | Alle Dokumente erfasst |
| Ordnung | Vorhanden | Strukturierte Ablage |
| Zeitgerechte Buchung | Teilweise | Automatisieren |
| Aufbewahrung | Fehlt | Fristen-Management |

---

## API-Spezifikation

### Endpoints Uebersicht

| Method | Endpoint | Beschreibung | Auth |
|--------|----------|--------------|------|
| POST | `/api/v1/archive/documents/{id}` | Dokument archivieren | Required |
| GET | `/api/v1/archive/documents/{id}/signature` | Signatur abrufen | Required |
| POST | `/api/v1/archive/documents/{id}/verify` | Integritaet pruefen | Required |
| GET | `/api/v1/archive/retention-schedule` | Aufbewahrungsfristen | Required |
| PUT | `/api/v1/archive/retention-settings` | Einstellungen anpassen | Admin |
| GET | `/api/v1/archive/procedure-documentation` | Verfahrensdoku abrufen | Required |
| POST | `/api/v1/archive/export/gdpdu` | GDPdU Export | Admin |
| POST | `/api/v1/users/invite/tax-advisor` | Steuerberater einladen | Admin |

---

### `POST /api/v1/archive/documents/{id}`

**Beschreibung**: Archiviert ein Dokument und macht es unveraenderbar.

**Response (200 OK):**
```json
{
  "id": "doc-uuid",
  "archived_at": "2026-01-15T10:30:00Z",
  "signature": {
    "algorithm": "SHA-256",
    "hash": "a948904f2f0f479b8f8564cbf12dac6b3fbf8bcf",
    "timestamp": "2026-01-15T10:30:00Z",
    "certificate": "TSA-qualified"
  },
  "retention": {
    "category": "invoice",
    "years": 10,
    "expires_at": "2036-01-15"
  },
  "is_immutable": true
}
```

---

### `POST /api/v1/archive/documents/{id}/verify`

**Beschreibung**: Verifiziert die Integritaet eines archivierten Dokuments.

**Response (200 OK):**
```json
{
  "document_id": "doc-uuid",
  "verification_status": "valid",
  "original_hash": "a948904f2f0f479b8f8564cbf12dac6b3fbf8bcf",
  "current_hash": "a948904f2f0f479b8f8564cbf12dac6b3fbf8bcf",
  "match": true,
  "verified_at": "2026-06-01T14:00:00Z"
}
```

**Bei Manipulation:**
```json
{
  "document_id": "doc-uuid",
  "verification_status": "compromised",
  "original_hash": "a948904f2f0f479b8f8564cbf12dac6b3fbf8bcf",
  "current_hash": "different-hash-value",
  "match": false,
  "alert": "WARNUNG: Dokument wurde nach Archivierung veraendert!"
}
```

---

### `GET /api/v1/archive/procedure-documentation`

**Beschreibung**: Ruft die automatisch generierte Verfahrensdokumentation ab.

**Response (200 OK):**
```json
{
  "version": "2.1.0",
  "generated_at": "2026-01-15T00:00:00Z",
  "sections": {
    "system_description": "Ablage-System OCR v4.2.0...",
    "data_flows": [...],
    "authorization_concept": {...},
    "archiving_rules": {...},
    "change_history": [...]
  },
  "pdf_url": "/api/v1/archive/procedure-documentation/pdf"
}
```

---

### `POST /api/v1/users/invite/tax-advisor`

**Beschreibung**: Laedt einen Steuerberater mit zeitlich begrenztem Zugang ein.

**Request:**
```json
{
  "email": "steuerberater@kanzlei.de",
  "name": "Dr. Max Mustermann",
  "access_until": "2026-03-31",
  "permissions": {
    "documents": ["view", "export"],
    "invoices": ["view"],
    "reports": ["view", "export"]
  }
}
```

**Response (201 Created):**
```json
{
  "id": "user-uuid",
  "email": "steuerberater@kanzlei.de",
  "role": "tax_advisor",
  "access_until": "2026-03-31",
  "invite_link": "https://system.example.com/invite/token...",
  "status": "pending"
}
```

---

## Datenbank-Schema

### Neue Tabellen

#### `document_archives`

```sql
CREATE TABLE document_archives (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Referenz
    document_id UUID REFERENCES documents(id) ON DELETE RESTRICT NOT NULL,
    company_id UUID REFERENCES companies(id) NOT NULL,

    -- Signatur
    content_hash VARCHAR(128) NOT NULL,
    hash_algorithm VARCHAR(20) DEFAULT 'SHA-256',
    signature_timestamp TIMESTAMPTZ NOT NULL,
    signature_certificate TEXT,  -- TSA Zertifikat oder NULL

    -- Aufbewahrung
    retention_category VARCHAR(50) NOT NULL,  -- invoice, contract, correspondence
    retention_years INTEGER NOT NULL DEFAULT 10,
    retention_expires_at DATE NOT NULL,
    retention_reminder_sent BOOLEAN DEFAULT false,

    -- Status
    is_verified BOOLEAN DEFAULT true,
    last_verification_at TIMESTAMPTZ,

    -- Audit
    archived_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    archived_by_id UUID REFERENCES users(id) NOT NULL,

    -- Constraints
    CONSTRAINT document_archives_unique UNIQUE (document_id)
);

CREATE INDEX ix_archives_company ON document_archives(company_id);
CREATE INDEX ix_archives_expires ON document_archives(retention_expires_at);
CREATE INDEX ix_archives_category ON document_archives(retention_category);
```

#### `audit_logs` (erweitert)

```sql
-- Erweiterung der bestehenden Audit-Tabelle

ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS gobd_relevant BOOLEAN DEFAULT false;
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS document_hash VARCHAR(128);
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS action_details JSONB DEFAULT '{}';

-- Index fuer GoBD-relevante Aktionen
CREATE INDEX ix_audit_gobd ON audit_logs(gobd_relevant) WHERE gobd_relevant = true;
```

#### `procedure_documentation_versions`

```sql
CREATE TABLE procedure_documentation_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Versionierung
    version VARCHAR(20) NOT NULL,
    content JSONB NOT NULL,

    -- Metadaten
    generated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    generated_by VARCHAR(50) DEFAULT 'system',

    -- Signatur
    content_hash VARCHAR(128) NOT NULL,

    -- Aenderungen
    change_summary TEXT
);

CREATE INDEX ix_procedure_docs_version ON procedure_documentation_versions(version);
```

### SQLAlchemy Models

```python
# app/db/models/archive.py

"""Archive Models fuer GoBD-Compliance."""

from __future__ import annotations

import uuid
import hashlib
from datetime import datetime, date
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Date, ForeignKey, String, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models import Document, User, Company


class DocumentArchive(Base):
    """Archivierungs-Metadaten fuer GoBD-Compliance."""

    __tablename__ = "document_archives"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Referenzen
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=False, unique=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False
    )

    # Signatur
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    hash_algorithm: Mapped[str] = mapped_column(String(20), default="SHA-256")
    signature_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    signature_certificate: Mapped[Optional[str]] = mapped_column(Text)

    # Aufbewahrung
    retention_category: Mapped[str] = mapped_column(String(50), nullable=False)
    retention_years: Mapped[int] = mapped_column(Integer, default=10)
    retention_expires_at: Mapped[date] = mapped_column(Date, nullable=False)
    retention_reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    # Status
    is_verified: Mapped[bool] = mapped_column(Boolean, default=True)
    last_verification_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )

    # Audit
    archived_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    archived_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # Relationships
    document: Mapped["Document"] = relationship(back_populates="archive")
    company: Mapped["Company"] = relationship()
    archived_by: Mapped["User"] = relationship()

    def verify_integrity(self, current_content: bytes) -> bool:
        """Verifiziert die Integritaet des Dokuments."""
        current_hash = hashlib.sha256(current_content).hexdigest()
        return current_hash == self.content_hash
```

---

## Implementation Tasks

### Phase 1: Signatur-System (1 Woche)

| # | Task | Beschreibung | Akzeptanzkriterium | Abhaengigkeit |
|---|------|--------------|-------------------|---------------|
| 1.1 | [ ] Archive-Tabelle erstellen | Migration + Model | Migration fehlerfrei | - |
| 1.2 | [ ] Hash-Service implementieren | SHA-256 Content Hashing | Hash in < 100ms | 1.1 |
| 1.3 | [ ] TSA-Integration | Qualifizierter Zeitstempel (optional) | Zertifikat gespeichert | 1.2 |
| 1.4 | [ ] Immutability enforcing | Dokument nach Archivierung readonly | 403 bei Edit-Versuch | 1.3 |

### Phase 2: Aufbewahrungsfristen (1 Woche)

| # | Task | Beschreibung | Akzeptanzkriterium | Abhaengigkeit |
|---|------|--------------|-------------------|---------------|
| 2.1 | [ ] Retention-Kategorien | invoice, contract, correspondence | Konfigurierbar | 1.4 |
| 2.2 | [ ] Fristen-Berechnung | Automatisch basierend auf Kategorie | Korrekte Berechnung | 2.1 |
| 2.3 | [ ] Reminder-System | Benachrichtigung X Tage vor Ablauf | E-Mail wird gesendet | 2.2 |
| 2.4 | [ ] Auto-Delete Option | Optionale Loeschung nach Ablauf | Admin-konfigurierbar | 2.3 |

### Phase 3: Verfahrensdokumentation (1 Woche)

| # | Task | Beschreibung | Akzeptanzkriterium | Abhaengigkeit |
|---|------|--------------|-------------------|---------------|
| 3.1 | [ ] Template erstellen | Markdown/JSON Template | Alle Sektionen vorhanden | 2.4 |
| 3.2 | [ ] Auto-Generierung | System-Info automatisch befuellen | Aktuell bei Abruf | 3.1 |
| 3.3 | [ ] PDF-Export | Verfahrensdoku als PDF | PDF korrekt formatiert | 3.2 |
| 3.4 | [ ] Versionierung | Aenderungen tracken | History abrufbar | 3.3 |

### Phase 4: Steuerberater-Zugang (0.5 Woche)

| # | Task | Beschreibung | Akzeptanzkriterium | Abhaengigkeit |
|---|------|--------------|-------------------|---------------|
| 4.1 | [ ] tax_advisor Rolle | Neue Rolle mit Read-Only | Keine Write-Berechtigung | 3.4 |
| 4.2 | [ ] Zeitliche Begrenzung | access_until Feld | Zugang nach Datum gesperrt | 4.1 |
| 4.3 | [ ] Invite-Flow | E-Mail Einladung | Link funktioniert | 4.2 |

### Phase 5: Testing & Export (0.5 Woche)

| # | Task | Beschreibung | Akzeptanzkriterium | Abhaengigkeit |
|---|------|--------------|-------------------|---------------|
| 5.1 | [ ] Unit Tests | Service Tests | Coverage >80% | 4.3 |
| 5.2 | [ ] Integration Tests | API Tests | Alle Endpoints | 5.1 |
| 5.3 | [ ] GDPdU Export | Export-Format fuer Pruefung | Valides XML | 5.2 |
| 5.4 | [ ] Dokumentation | GoBD-Leitfaden | Fuer Pruefung bereit | 5.3 |

---

## Test-Szenarien

### Unit Tests

```python
# tests/unit/services/test_archive_service.py

import pytest
import hashlib
from app.services.archive_service import ArchiveService


class TestArchiving:
    """Tests fuer Dokument-Archivierung."""

    @pytest.mark.asyncio
    async def test_archive_creates_hash(self, service, sample_document):
        """Archivierung erstellt korrekten Hash."""
        result = await service.archive_document(sample_document.id)

        expected_hash = hashlib.sha256(sample_document.content).hexdigest()
        assert result.content_hash == expected_hash

    @pytest.mark.asyncio
    async def test_archived_document_is_immutable(self, service, archived_document):
        """Archiviertes Dokument kann nicht geaendert werden."""
        with pytest.raises(ImmutableDocumentError):
            await service.update_document(archived_document.id, {"name": "New Name"})

    @pytest.mark.asyncio
    async def test_verify_integrity_success(self, service, archived_document):
        """Integritaetspruefung erfolgreich bei unveraendertem Dokument."""
        result = await service.verify_integrity(archived_document.id)

        assert result.verification_status == "valid"
        assert result.match is True

    @pytest.mark.asyncio
    async def test_verify_integrity_detects_tampering(
        self, service, archived_document, tampered_content
    ):
        """Integritaetspruefung erkennt Manipulation."""
        # Simuliere Manipulation (in DB direkt aendern)
        result = await service.verify_integrity(archived_document.id)

        assert result.verification_status == "compromised"
        assert result.match is False


class TestRetention:
    """Tests fuer Aufbewahrungsfristen."""

    @pytest.mark.asyncio
    async def test_retention_calculated_correctly(self, service):
        """Aufbewahrungsfrist wird korrekt berechnet."""
        result = await service.archive_document(
            document_id,
            retention_category="invoice"
        )

        expected_expiry = date.today() + timedelta(days=365*10)
        assert result.retention_expires_at == expected_expiry

    @pytest.mark.asyncio
    async def test_reminder_sent_before_expiry(self, service, near_expiry_document):
        """Erinnerung wird vor Ablauf gesendet."""
        await service.check_retention_reminders()

        # Notification sollte erstellt worden sein
        notifications = await get_notifications_for_document(near_expiry_document.id)
        assert len(notifications) > 0
        assert "Aufbewahrungsfrist" in notifications[0].message
```

### Integration Tests

```python
# tests/integration/test_gobd_api.py

@pytest.mark.integration
class TestGoBDEndpoints:

    @pytest.mark.asyncio
    async def test_archive_document_flow(self, async_client, auth_headers, document_id):
        """Vollstaendiger Archivierungs-Flow."""
        # Archivieren
        response = await async_client.post(
            f"/api/v1/archive/documents/{document_id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["is_immutable"] is True

        # Verifizieren
        verify_response = await async_client.post(
            f"/api/v1/archive/documents/{document_id}/verify",
            headers=auth_headers
        )
        assert verify_response.status_code == 200
        assert verify_response.json()["verification_status"] == "valid"

        # Edit sollte fehlschlagen
        edit_response = await async_client.put(
            f"/api/v1/documents/{document_id}",
            json={"name": "Changed"},
            headers=auth_headers
        )
        assert edit_response.status_code == 403
        assert "archiviert" in edit_response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_tax_advisor_access(self, async_client, admin_headers):
        """Steuerberater-Einladung und Zugang."""
        # Einladen
        invite_response = await async_client.post(
            "/api/v1/users/invite/tax-advisor",
            json={
                "email": "test@steuerberater.de",
                "name": "Test Berater",
                "access_until": "2026-12-31"
            },
            headers=admin_headers
        )
        assert invite_response.status_code == 201

        # Login als Steuerberater
        tax_headers = await login_as_invited_user(invite_response.json()["invite_link"])

        # Kann Dokumente sehen
        docs_response = await async_client.get(
            "/api/v1/documents",
            headers=tax_headers
        )
        assert docs_response.status_code == 200

        # Kann NICHT bearbeiten
        edit_response = await async_client.put(
            f"/api/v1/documents/{document_id}",
            json={"name": "Changed"},
            headers=tax_headers
        )
        assert edit_response.status_code == 403
```

---

## Quality Gates

### Vor PR-Erstellung

- [ ] **GoBD-Konformitaet**
  - [ ] Signatur-System implementiert und getestet
  - [ ] Unveraenderbarkeit durchgesetzt
  - [ ] Audit-Trail vollstaendig
  - [ ] Verfahrensdokumentation generiert

- [ ] **Code Qualitaet**
  - [ ] mypy --strict clean
  - [ ] ruff check . clean
  - [ ] Security Review durchgefuehrt

- [ ] **Testing**
  - [ ] Unit Tests >80% Coverage
  - [ ] Integritaetspruefung getestet
  - [ ] Manipulations-Erkennung getestet

### Vor Merge

- [ ] **Compliance**
  - [ ] Steuerberater-Review der Verfahrensdokumentation
  - [ ] Alle GoBD-Kriterien erfuellt

- [ ] **Dokumentation**
  - [ ] GoBD-Leitfaden fuer Endbenutzer
  - [ ] Technische Dokumentation fuer Pruefung

### Definition of Done

1. [ ] Alle steuerrelevanten Dokumente archivierbar
2. [ ] Integritaetspruefung funktioniert zuverlaessig
3. [ ] Verfahrensdokumentation automatisch aktuell
4. [ ] Steuerberater kann eingeladen werden
5. [ ] Aufbewahrungsfristen-Warnungen aktiv
6. [ ] Bereit fuer offizielle GoBD-Pruefung (Q4 2026)
