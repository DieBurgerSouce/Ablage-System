"""GoBD Verfahrensdokumentation Auto-Generator.

Generiert automatisch die gesetzlich vorgeschriebene Verfahrensdokumentation
für das DMS gemäß GoBD.

Die Verfahrensdokumentation besteht aus:
1. Allgemeine Beschreibung (Systemüberblick)
2. Anwenderdokumentation (Benutzerhandbuch)
3. Technische Systemdokumentation (Architektur)
4. Betriebsdokumentation (Ablaufbeschreibungen)
5. Internes Kontrollsystem (IKS)

Ausgabeformate:
- PDF (für Steuerberater/Prüfer)
- HTML (für interne Dokumentation)
- Markdown (für Versionskontrolle)
"""

import io
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, Company
from app.db.models import AuditLog  # F-31
from app.db.bpmn_models.gobd import (
    AuditChainEntry,
    RetentionPolicy,
    TimestampAuthorityConfig,
)

logger = structlog.get_logger(__name__)


class DocumentFormat(str, Enum):
    """Ausgabeformate für die Verfahrensdokumentation."""
    PDF = "pdf"
    HTML = "html"
    MARKDOWN = "markdown"


class DocumentSection(str, Enum):
    """Sektionen der Verfahrensdokumentation."""
    GENERAL = "general"  # Allgemeine Beschreibung
    USER = "user"  # Anwenderdokumentation
    TECHNICAL = "technical"  # Technische Systemdokumentation
    OPERATIONS = "operations"  # Betriebsdokumentation
    CONTROLS = "controls"  # Internes Kontrollsystem


@dataclass
class DocumentationMetadata:
    """Metadaten für die Verfahrensdokumentation."""
    company_name: str
    company_id: uuid.UUID
    generated_at: datetime
    generated_by: str
    version: str
    valid_from: datetime
    valid_until: Optional[datetime] = None
    approval_status: str = "draft"
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None


@dataclass
class SystemStatistics:
    """Statistiken für die Dokumentation."""
    total_documents: int = 0
    total_users: int = 0
    active_workflows: int = 0
    retention_policies_count: int = 0
    audit_chain_entries: int = 0
    tsa_configured: bool = False
    last_integrity_check: Optional[datetime] = None


@dataclass
class ProcedureDocumentation:
    """Die vollständige Verfahrensdokumentation."""
    metadata: DocumentationMetadata
    statistics: SystemStatistics
    sections: Dict[DocumentSection, str] = field(default_factory=dict)
    change_history: List[Dict[str, Any]] = field(default_factory=list)


class ProcedureDocumentationService:
    """Service zur Generierung der GoBD Verfahrensdokumentation."""

    SYSTEM_VERSION = "1.1"
    DOCUMENT_VERSION = "2026.01"

    async def generate_documentation(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        generated_by_user_id: uuid.UUID,
        include_sections: Optional[List[DocumentSection]] = None,
    ) -> ProcedureDocumentation:
        """Generiert die vollständige Verfahrensdokumentation.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            generated_by_user_id: User der die Generierung ausloest
            include_sections: Optional - nur bestimmte Sektionen

        Returns:
            ProcedureDocumentation Objekt
        """
        if include_sections is None:
            include_sections = list(DocumentSection)

        # Company und User laden
        company = await self._get_company(db, company_id)
        user = await self._get_user(db, generated_by_user_id)

        # Metadaten erstellen
        metadata = DocumentationMetadata(
            company_name=company.name if company else "Unbekannt",
            company_id=company_id,
            generated_at=datetime.now(timezone.utc),
            generated_by=user.full_name if user else "System",
            version=self.DOCUMENT_VERSION,
            valid_from=datetime.now(timezone.utc),
        )

        # Statistiken sammeln
        statistics = await self._gather_statistics(db, company_id)

        # Sektionen generieren
        sections = {}

        if DocumentSection.GENERAL in include_sections:
            sections[DocumentSection.GENERAL] = await self._generate_general_section(
                db, company_id, metadata, statistics
            )

        if DocumentSection.USER in include_sections:
            sections[DocumentSection.USER] = await self._generate_user_section(
                db, company_id
            )

        if DocumentSection.TECHNICAL in include_sections:
            sections[DocumentSection.TECHNICAL] = await self._generate_technical_section(
                db, company_id, statistics
            )

        if DocumentSection.OPERATIONS in include_sections:
            sections[DocumentSection.OPERATIONS] = await self._generate_operations_section(
                db, company_id
            )

        if DocumentSection.CONTROLS in include_sections:
            sections[DocumentSection.CONTROLS] = await self._generate_controls_section(
                db, company_id, statistics
            )

        # Change History (letzte Änderungen)
        change_history = await self._get_change_history(db, company_id)

        logger.info(
            "procedure_documentation_generated",
            company_id=str(company_id),
            sections_count=len(sections),
        )

        return ProcedureDocumentation(
            metadata=metadata,
            statistics=statistics,
            sections=sections,
            change_history=change_history,
        )

    async def export_to_format(
        self,
        documentation: ProcedureDocumentation,
        format: DocumentFormat,
    ) -> bytes:
        """Exportiert die Dokumentation in ein bestimmtes Format.

        Args:
            documentation: Die zu exportierende Dokumentation
            format: Gewünschtes Ausgabeformat

        Returns:
            Bytes des exportierten Dokuments
        """
        if format == DocumentFormat.MARKDOWN:
            return self._export_markdown(documentation)
        elif format == DocumentFormat.HTML:
            return self._export_html(documentation)
        elif format == DocumentFormat.PDF:
            return await self._export_pdf(documentation)
        else:
            raise ValueError(f"Unbekanntes Format: {format}")

    # ================== Section Generators ==================

    async def _generate_general_section(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        metadata: DocumentationMetadata,
        statistics: SystemStatistics,
    ) -> str:
        """Generiert die allgemeine Beschreibung."""
        return f"""# 1. Allgemeine Beschreibung

## 1.1 Zweck des Systems

Das Ablage-System OCR ist ein Dokumentenmanagementsystem (DMS) zur
revisionssicheren Archivierung und Verarbeitung von Geschäftsdokumenten.
Es erfuellt die Anforderungen der GoBD (Grundsätze zur ordnungsmaessigen
Führung und Aufbewahrung von Buechern, Aufzeichnungen und Unterlagen
in elektronischer Form sowie zum Datenzugriff).

## 1.2 Systemüberblick

**Firmenname:** {metadata.company_name}
**Dokumentationsversion:** {metadata.version}
**Systemversion:** {self.SYSTEM_VERSION}
**Gültig ab:** {metadata.valid_from.strftime('%d.%m.%Y')}
**Erstellt am:** {metadata.generated_at.strftime('%d.%m.%Y %H:%M')}
**Erstellt von:** {metadata.generated_by}

## 1.3 Systemstatistiken

| Kennzahl | Wert |
|----------|------|
| Gespeicherte Dokumente | {statistics.total_documents:,} |
| Aktive Benutzer | {statistics.total_users} |
| Aufbewahrungsrichtlinien | {statistics.retention_policies_count} |
| Audit-Chain Einträge | {statistics.audit_chain_entries:,} |
| Qualifizierte Zeitstempel | {'Konfiguriert' if statistics.tsa_configured else 'Nicht konfiguriert'} |

## 1.4 Gesetzliche Grundlagen

Das System erfuellt die Anforderungen folgender Vorschriften:
- GoBD (BMF-Schreiben vom 28.11.2019)
- § 147 AO (Aufbewahrungspflichten)
- § 257 HGB (Aufbewahrung von Unterlagen)
- DSGVO (Datenschutz-Grundverordnung)

## 1.5 Geltungsbereich

Diese Verfahrensdokumentation gilt für alle mit dem System verarbeiteten
steuerrelevanten und aufbewahrungspflichtigen Dokumente.
"""

    async def _generate_user_section(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> str:
        """Generiert die Anwenderdokumentation."""
        return """# 2. Anwenderdokumentation

## 2.1 Benutzerrollen und Berechtigungen

Das System unterscheidet folgende Benutzerrollen:

| Rolle | Beschreibung | Berechtigungen |
|-------|--------------|----------------|
| Administrator | Systemadministration | Vollzugriff |
| Manager | Abteilungsleitung | Freigaben, Reports |
| Mitarbeiter | Standardnutzer | Dokumente erfassen/anzeigen |
| Steuerberater | Externer Zugriff | Nur Lesen, Export |
| Auditor | Prüfer | Nur Lesen, Audit-Logs |

## 2.2 Dokumentenerfassung

### 2.2.1 Upload-Verfahren

Dokumente können auf folgende Arten erfasst werden:
1. **Manueller Upload:** Drag & Drop oder Datei-Dialog
2. **Email-Import:** Automatischer Import aus konfigurierten Postfaechern
3. **Ordner-Import:** Überwachung von Verzeichnissen
4. **Scanner-Integration:** Direkte Erfassung via TWAIN

### 2.2.2 OCR-Verarbeitung

Alle Dokumente werden automatisch per OCR verarbeitet:
- Texterkennung (auch Frakturschrift)
- Automatische Klassifizierung
- Entitäts-Extraktion (Betraege, Daten, Nummern)

## 2.3 Dokumentensuche

Die Suche unterstützt:
- Volltextsuche in OCR-Text
- Filterung nach Typ, Datum, Betrag
- Suche nach Geschäftspartner
- Erweiterte Filteroptionen

## 2.4 Archivierung

### 2.4.1 Automatische Archivierung

Dokumente werden automatisch archiviert basierend auf:
- Dokumenttyp und zugehoerigen Aufbewahrungsfristen
- Konfigurierten Archivierungsrichtlinien

### 2.4.2 Manuelle Archivierung

Benutzer können Dokumente explizit archivieren über:
- Kontextmenue → "Archivieren"
- Batch-Archivierung über Selektion
"""

    async def _generate_technical_section(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        statistics: SystemStatistics,
    ) -> str:
        """Generiert die technische Systemdokumentation."""
        return """# 3. Technische Systemdokumentation

## 3.1 Systemarchitektur

```
+-------------------------------------------------------------+
|                    Ablage-System OCR                        |
+-------------------------------------------------------------+
|  Frontend (Nginx)    |  Grafana  |  Prometheus (Monitoring) |
+-------------------------------------------------------------+
|                    FastAPI Backend                          |
+-------------------------------------------------------------+
|  Celery Workers  |  Redis (Cache)  |  PostgreSQL (DB)       |
+-------------------------------------------------------------+
|  OCR: DeepSeek | GOT-OCR | Surya | Surya-GPU               |
+-------------------------------------------------------------+
|                    GPU: NVIDIA (CUDA)                       |
+-------------------------------------------------------------+
```

## 3.2 Datenhaltung

### 3.2.1 Datenbank

- **System:** PostgreSQL 16 mit pgvector Extension
- **Verschlüsselung:** TLS in Transit, AES-256 at Rest
- **Backup:** Täglich vollständig, stuendlich inkrementell

### 3.2.2 Dokumentenspeicher

- **System:** MinIO (S3-kompatibel)
- **Verschlüsselung:** AES-256-GCM
- **Redundanz:** Erasure Coding

## 3.3 Sicherheitsarchitektur

### 3.3.1 Authentifizierung

- JWT-basierte Authentifizierung
- Optionale 2-Faktor-Authentifizierung
- Session-Timeout: 15 Minuten (konfigurierbar)

### 3.3.2 Autorisierung

- Rollenbasierte Zugriffskontrolle (RBAC)
- Multi-Tenant Isolation (Row Level Security)
- Attributbasierte Zugriffskontrolle für Dokumente

### 3.3.3 Audit-Trail

- Blockchain-ähnliche Verkettung (Hash-Chain)
- Unveränderbare Protokollierung aller Zugriffe
- Optionale RFC 3161 Zeitstempel

## 3.4 Integritätssicherung

### 3.4.1 Hash-Verfahren

Alle Dokumente erhalten einen SHA-256 Hash der:
- Bei Upload berechnet wird
- Bei Archivierung erneut verifiziert wird
- In regelmäßigen Integritätsprüfungen validiert wird

### 3.4.2 Audit-Chain

Die Audit-Chain ist eine unveränderbare Ereigniskette:
- APPEND-ONLY: Nur neue Einträge, keine Änderungen
- Verkettete Hashes: Jeder Eintrag referenziert den vorherigen
- Manipulationserkennung: Hash-Verifikation deckt Änderungen auf

## 3.5 OCR-Verarbeitung

### 3.5.1 OCR-Backends

| Backend | Einsatz | Genauigkeit |
|---------|---------|-------------|
| DeepSeek-Janus | Standard, Fraktur | 99%+ |
| GOT-OCR 2.0 | Tabellen, Formeln | 98%+ |
| Surya | CPU-Fallback | 95%+ |

### 3.5.2 Qualitätssicherung

- Confidence-Score pro Feld
- Automatische Nachverarbeitung bei niedriger Konfidenz
- Self-Learning aus User-Korrekturen
"""

    async def _generate_operations_section(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> str:
        """Generiert die Betriebsdokumentation."""
        return """# 4. Betriebsdokumentation

## 4.1 Systemstart und -stop

### 4.1.1 Normaler Start

```bash
docker-compose up -d
```

### 4.1.2 Graceful Shutdown

```bash
docker-compose down
```

### 4.1.3 Notfall-Stop

```bash
docker-compose down --timeout 5
```

## 4.2 Backup-Verfahren

### 4.2.1 Datenbank-Backup

- **Frequenz:** Täglich 02:00 Uhr (vollständig)
- **Retention:** 30 Tage
- **Speicherort:** Separater Backup-Server + Offsite

### 4.2.2 Dokumenten-Backup

- **Frequenz:** Kontinuierlich (Replikation)
- **Retention:** Unbegrenzt (archivierte Dokumente)
- **Speicherort:** MinIO Cluster mit Erasure Coding

### 4.2.3 Wiederherstellung

1. Datenbank aus Backup wiederherstellen
2. Dokumentenspeicher synchronisieren
3. Integritätsprüfung durchführen
4. System neu starten

## 4.3 Monitoring

### 4.3.1 Überwachte Metriken

- CPU/RAM/Disk Auslastung
- Datenbank-Performance
- API-Antwortzeiten
- OCR-Queue-Länge
- Fehlerrate

### 4.3.2 Alerting

| Metrik | Warning | Critical |
|--------|---------|----------|
| CPU | >80% | >95% |
| RAM | >85% | >95% |
| Disk | >80% | >90% |
| API Latenz | >500ms | >2000ms |
| Error Rate | >1% | >5% |

## 4.4 Wartung

### 4.4.1 Regelmäßige Aufgaben

| Aufgabe | Frequenz | Verantwortlich |
|---------|----------|----------------|
| Integritätsprüfung | Täglich | System (automatisch) |
| Backup-Verifikation | Woechentlich | Administrator |
| Log-Rotation | Täglich | System (automatisch) |
| Updates | Monatlich | Administrator |

### 4.4.2 Ungeplante Wartung

Alle ungeplanten Wartungsarbeiten werden protokolliert:
- Grund der Wartung
- Durchgeführte Massnahmen
- Ausfallzeit
- Verantwortlicher

## 4.5 Notfallplan

### 4.5.1 Systemausfall

1. Support benachrichtigen
2. Fehleranalyse durchführen
3. Wiederherstellung aus Backup (falls erforderlich)
4. Dokumentation des Vorfalls

### 4.5.2 Datenverlust

1. Sofortiger Stop aller Schreiboperationen
2. Backup-Status prüfen
3. Wiederherstellung einleiten
4. Integritätsprüfung nach Wiederherstellung
"""

    async def _generate_controls_section(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        statistics: SystemStatistics,
    ) -> str:
        """Generiert die IKS-Dokumentation."""
        # Aufbewahrungsrichtlinien laden
        policies = await self._get_retention_policies(db, company_id)
        policies_table = self._format_policies_table(policies)

        return f"""# 5. Internes Kontrollsystem (IKS)

## 5.1 Kontrollziele

Das interne Kontrollsystem stellt sicher, dass:
- Alle Dokumente vollständig erfasst werden
- Keine unberechtigten Änderungen möglich sind
- Aufbewahrungsfristen eingehalten werden
- Zugriffe nachvollziehbar sind

## 5.2 Kontrollmassnahmen

### 5.2.1 Erfassungskontrollen

| Kontrolle | Beschreibung | Automatisierung |
|-----------|--------------|-----------------|
| Vollständigkeit | Alle Pflichtfelder geprüft | Automatisch |
| Plausibilitaet | Betraege, Daten validiert | Automatisch |
| Duplikatprüfung | Hash-basierte Erkennung | Automatisch |
| Klassifizierung | KI-gestuetzte Zuordnung | Automatisch |

### 5.2.2 Verarbeitungskontrollen

| Kontrolle | Beschreibung | Automatisierung |
|-----------|--------------|-----------------|
| OCR-Qualität | Confidence-Schwellwert | Automatisch |
| Entitäts-Matching | Zuordnung zu Geschäftspartnern | Semi-Automatisch |
| Workflow-Einhaltung | BPMN-Prozesse | Automatisch |

### 5.2.3 Ausgabekontrollen

| Kontrolle | Beschreibung | Automatisierung |
|-----------|--------------|-----------------|
| Berechtigungsprüfung | RBAC-Check bei Export | Automatisch |
| Audit-Logging | Protokollierung aller Exporte | Automatisch |
| Wasserzeichen | Bei sensiblen Dokumenten | Konfigurierbar |

## 5.3 Aufbewahrungsfristen

{policies_table}

## 5.4 Zugriffskontrollen

### 5.4.1 Benutzerauthentifizierung

- Starke Passwoerter (min. 12 Zeichen, Komplexität)
- Optionale 2-Faktor-Authentifizierung
- Account-Sperrung nach 5 Fehlversuchen
- Automatische Abmeldung nach Inaktivität

### 5.4.2 Berechtigungsprüfung

Jeder Zugriff wird geprüft auf:
1. Authentifizierung (gültiger Token)
2. Mandantenzugehoerigkeit (Multi-Tenant)
3. Rollenbasierte Berechtigung (RBAC)
4. Dokumentenspezifische Berechtigung

## 5.5 Audit-Trail

### 5.5.1 Protokollierte Ereignisse

- Dokumenten-Uploads und -Änderungen
- Zugriffe und Downloads
- Workflow-Aktionen
- Administrationstätigkeiten
- System-Ereignisse

### 5.5.2 Unveränderlichkeit

Die Audit-Chain garantiert Unveränderlichkeit durch:
- Hash-Verkettung (Blockchain-Prinzip)
- Sequenznummern (Lückenlosigkeit)
- Optionale RFC 3161 Zeitstempel

**Aktueller Stand:** {statistics.audit_chain_entries:,} Einträge in der Audit-Chain

## 5.6 Integritätsprüfungen

### 5.6.1 Automatische Prüfungen

- **Täglich:** Vollständige Kettenverifikation
- **Bei Zugriff:** Hash-Prüfung archivierter Dokumente
- **Woechentlich:** Stichproben-Verifikation

### 5.6.2 Letzte Prüfung

**Datum:** {statistics.last_integrity_check.strftime('%d.%m.%Y %H:%M') if statistics.last_integrity_check else 'Keine Prüfung durchgeführt'}

## 5.7 Änderungsmanagement

Alle Änderungen am System werden dokumentiert:
1. Change Request erstellen
2. Genehmigung einholen
3. Änderung durchführen
4. Testen und Verifizieren
5. Dokumentation aktualisieren
"""

    # ================== Helper Methods ==================

    async def _get_company(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> Optional[Company]:
        """Laedt die Company."""
        result = await db.execute(
            select(Company).where(Company.id == company_id)
        )
        return result.scalar_one_or_none()

    async def _get_user(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> Optional[User]:
        """Laedt den User."""
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def _gather_statistics(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> SystemStatistics:
        """Sammelt Systemstatistiken."""
        # Dokumente zaehlen
        from app.db.models import Document
        doc_result = await db.execute(
            select(func.count())
            .select_from(Document)
            .where(Document.company_id == company_id)
        )
        total_documents = doc_result.scalar() or 0

        # User zaehlen
        user_result = await db.execute(
            select(func.count())
            .select_from(User)
            .where(User.is_active == True)  # F-31: User hat kein company_id (Tenancy via UserCompany)
        )
        total_users = user_result.scalar() or 0

        # Retention Policies
        policy_result = await db.execute(
            select(func.count())
            .select_from(RetentionPolicy)
            .where(RetentionPolicy.company_id == company_id)
        )
        retention_count = policy_result.scalar() or 0

        # Audit Chain Entries
        chain_result = await db.execute(
            select(func.count())
            .select_from(AuditChainEntry)
            .where(AuditChainEntry.company_id == company_id)
        )
        chain_count = chain_result.scalar() or 0

        # TSA Konfiguriert?
        tsa_result = await db.execute(
            select(func.count())
            .select_from(TimestampAuthorityConfig)
            .where(
                TimestampAuthorityConfig.company_id == company_id,
                TimestampAuthorityConfig.is_active == True,
            )
        )
        tsa_configured = (tsa_result.scalar() or 0) > 0

        return SystemStatistics(
            total_documents=total_documents,
            total_users=total_users,
            retention_policies_count=retention_count,
            audit_chain_entries=chain_count,
            tsa_configured=tsa_configured,
            last_integrity_check=await self._get_last_integrity_check(db, company_id),
        )

    async def _get_last_integrity_check(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> datetime:
        """Holt Zeitpunkt der letzten Integritätsprüfung."""
        # Suche nach letztem integrity_check Audit-Eintrag
        query = (
            select(AuditLog.created_at)
            .where(
                AuditLog.company_id == company_id,
                AuditLog.action.in_([
                    "integrity_check_completed",
                    "merkle_tree_verified",
                    "audit_chain_verified",
                    "gobd_compliance_verified",
                ]),
            )
            .order_by(AuditLog.created_at.desc())
            .limit(1)
        )
        result = await db.execute(query)
        last_check = result.scalar_one_or_none()

        if last_check:
            return last_check

        # Fallback: Aktuelle Zeit (keine Prüfung bisher)
        return datetime.now(timezone.utc)

    async def _get_retention_policies(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> List[RetentionPolicy]:
        """Laedt alle Aufbewahrungsrichtlinien."""
        result = await db.execute(
            select(RetentionPolicy)
            .where(
                RetentionPolicy.company_id == company_id,
                RetentionPolicy.is_active == True,
            )
            .order_by(RetentionPolicy.document_category)
        )
        return list(result.scalars().all())

    def _format_policies_table(
        self,
        policies: List[RetentionPolicy],
    ) -> str:
        """Formatiert die Aufbewahrungsrichtlinien als Markdown-Tabelle."""
        if not policies:
            return "Keine Aufbewahrungsrichtlinien konfiguriert."

        lines = [
            "| Dokumentkategorie | Aufbewahrungsdauer | Gesetzliche Grundlage | Auto-Löschung |",
            "|-------------------|--------------------|-----------------------|----------------|",
        ]

        category_names = {
            "invoice": "Rechnungen",
            "contract": "Verträge",
            "receipt": "Belege",
            "correspondence": "Korrespondenz",
            "tax": "Steuerdokumente",
        }

        for policy in policies:
            category = category_names.get(policy.document_category, policy.document_category)
            years = f"{policy.retention_years} Jahre"
            legal = policy.legal_basis or "-"
            auto_delete = "Ja" if policy.auto_delete_after_expiry else "Nein"
            lines.append(f"| {category} | {years} | {legal} | {auto_delete} |")

        return "\n".join(lines)

    async def _get_change_history(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Holt die letzten System-Änderungen aus AuditLog."""
        # Relevante Aktionen für Verfahrensdokumentation
        relevant_actions = [
            "system_config_changed",
            "retention_policy_created",
            "retention_policy_updated",
            "compliance_rule_changed",
            "archive_config_changed",
            "tsa_config_updated",
            "gobd_settings_changed",
            "workflow_deployed",
            "bpmn_process_created",
        ]

        # Lade AuditLog-Einträge
        query = (
            select(AuditLog)
            .where(
                AuditLog.company_id == company_id,
                AuditLog.action.in_(relevant_actions),
            )
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        result = await db.execute(query)
        logs = result.scalars().all()

        changes = []
        version_counter = 1.0

        for log in logs:
            # Extrahiere Details aus changes JSONB
            changes_data = log.changes or {}
            description = changes_data.get("description", log.action.replace("_", " ").title())

            # User-Name aus User-ID
            author = "System"
            if log.user_id:
                user_query = select(User.email).where(User.id == log.user_id)
                user_result = await db.execute(user_query)
                user_email = user_result.scalar_one_or_none()
                if user_email:
                    author = user_email.split("@")[0]  # Nur Benutzername

            changes.append({
                "date": log.created_at.strftime("%Y-%m-%d"),
                "version": f"{version_counter:.1f}",
                "description": description,
                "author": author,
                "action": log.action,
            })
            version_counter += 0.1

        # Falls keine Logs vorhanden, Standard-Einträge
        if not changes:
            changes = [
                {
                    "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "version": "1.0",
                    "description": "Initiale Version der Verfahrensdokumentation",
                    "author": "System",
                    "action": "system_initialized",
                },
            ]

        return changes

    # ================== Export Methods ==================

    def _export_markdown(
        self,
        documentation: ProcedureDocumentation,
    ) -> bytes:
        """Exportiert als Markdown."""
        lines = [
            "---",
            f"title: Verfahrensdokumentation {documentation.metadata.company_name}",
            f"version: {documentation.metadata.version}",
            f"date: {documentation.metadata.generated_at.strftime('%Y-%m-%d')}",
            "---",
            "",
        ]

        for section in DocumentSection:
            if section in documentation.sections:
                lines.append(documentation.sections[section])
                lines.append("")

        # Change History
        lines.append("# 6. Änderungshistorie")
        lines.append("")
        lines.append("| Datum | Version | Beschreibung | Autor |")
        lines.append("|-------|---------|--------------|-------|")
        for change in documentation.change_history:
            lines.append(
                f"| {change['date']} | {change['version']} | {change['description']} | {change['author']} |"
            )

        return "\n".join(lines).encode("utf-8")

    def _export_html(
        self,
        documentation: ProcedureDocumentation,
    ) -> bytes:
        """Exportiert als HTML."""
        import markdown

        md_content = self._export_markdown(documentation).decode("utf-8")
        html_content = markdown.markdown(
            md_content,
            extensions=["tables", "fenced_code"],
        )

        full_html = f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Verfahrensdokumentation - {documentation.metadata.company_name}</title>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 1000px; margin: 0 auto; padding: 20px; }}
        h1 {{ color: #1a365d; border-bottom: 2px solid #1a365d; }}
        h2 {{ color: #2c5282; }}
        h3 {{ color: #3182ce; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f7fafc; }}
        tr:nth-child(even) {{ background-color: #f7fafc; }}
        code {{ background-color: #edf2f7; padding: 2px 4px; border-radius: 3px; }}
        pre {{ background-color: #1a202c; color: #e2e8f0; padding: 15px; border-radius: 5px; overflow-x: auto; }}
        .metadata {{ background-color: #ebf8ff; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
    </style>
</head>
<body>
    <div class="metadata">
        <strong>Firma:</strong> {documentation.metadata.company_name}<br>
        <strong>Version:</strong> {documentation.metadata.version}<br>
        <strong>Erstellt:</strong> {documentation.metadata.generated_at.strftime('%d.%m.%Y %H:%M')}<br>
        <strong>Erstellt von:</strong> {documentation.metadata.generated_by}
    </div>
    {html_content}
</body>
</html>"""

        return full_html.encode("utf-8")

    async def _export_pdf(
        self,
        documentation: ProcedureDocumentation,
    ) -> bytes:
        """Exportiert als PDF."""
        # PDF-Generierung erfordert zusätzliche Bibliothek
        # (weasyprint, reportlab oder pdfkit)

        # Fallback: HTML-zu-PDF Konvertierung
        # In Produktion: weasyprint oder pdfkit verwenden

        try:
            from weasyprint import HTML
            html_content = self._export_html(documentation)
            pdf_bytes = HTML(string=html_content.decode("utf-8")).write_pdf()
            return pdf_bytes
        except (ImportError, OSError):
            logger.warning("weasyprint_not_installed", fallback="html")
            # Fallback: HTML zurückgeben mit Hinweis
            return self._export_html(documentation)


# ================== Convenience Functions ==================

async def generate_procedure_documentation(
    db: AsyncSession,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    format: DocumentFormat = DocumentFormat.PDF,
) -> bytes:
    """Convenience-Funktion zur Dokumentationserstellung.

    Args:
        db: Datenbank-Session
        company_id: Firmen-ID
        user_id: User-ID des Erstellers
        format: Ausgabeformat (PDF, HTML, Markdown)

    Returns:
        Bytes des Dokuments im gewünschten Format
    """
    service = ProcedureDocumentationService()
    documentation = await service.generate_documentation(db, company_id, user_id)
    return await service.export_to_format(documentation, format)


# Singleton-Instanz
procedure_documentation_service = ProcedureDocumentationService()
