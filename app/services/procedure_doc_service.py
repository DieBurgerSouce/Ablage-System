"""GoBD Verfahrensdokumentation Service.

Automatische Generierung und Versionierung der GoBD-Verfahrensdokumentation.

Die Verfahrensdokumentation beschreibt:
1. Allgemeine Beschreibung des Systems
2. Anwenderdokumentation (Benutzerhandbuch)
3. Technische Systemdokumentation
4. Betriebsdokumentation
5. Internes Kontrollsystem (IKS)

Erfuellt GoBD-Anforderungen:
- Automatische Versionierung bei Systemupdates
- Hash-Signatur fuer Unveraenderbarkeit
- Vollstaendige Aenderungshistorie
"""

import hashlib
import json
import uuid
from datetime import datetime
from typing import Optional

import structlog
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import ProcedureDocumentationVersion, Company

logger = structlog.get_logger(__name__)


# Aktuelle System-Version (wird bei Updates inkrementiert)
CURRENT_SYSTEM_VERSION = "1.0.0"


class ProcedureDocService:
    """Service fuer die Generierung der GoBD-Verfahrensdokumentation."""

    async def generate_documentation(
        self,
        db: AsyncSession,
        company_id: Optional[uuid.UUID] = None,
        change_summary: Optional[str] = None,
    ) -> ProcedureDocumentationVersion:
        """Generiert eine neue Version der Verfahrensdokumentation.

        Args:
            db: Datenbank-Session
            company_id: Optional - fuer firmenspezifische Dokumentation
            change_summary: Zusammenfassung der Aenderungen

        Returns:
            ProcedureDocumentationVersion: Neue Dokumentationsversion
        """
        # Vorherige Version laden
        previous_version = await self.get_latest_version(db, company_id)

        # Neue Versionsnummer berechnen
        if previous_version:
            version = self._increment_version(previous_version.version)
        else:
            version = "1.0.0"

        # Dokumentation generieren
        content = await self._generate_content(db, company_id)

        # Hash berechnen
        content_hash = self._compute_hash(content)

        # Aenderungen ermitteln
        change_details = None
        if previous_version:
            change_details = self._compute_changes(
                previous_version.content,
                content
            )

        # Neue Version erstellen
        doc_version = ProcedureDocumentationVersion(
            id=uuid.uuid4(),
            version=version,
            content=content,
            content_hash=content_hash,
            change_summary=change_summary or "Automatisch generierte Version",
            change_details=change_details,
            company_id=company_id,
            generated_by="system",
        )

        db.add(doc_version)
        await db.commit()
        await db.refresh(doc_version)

        logger.info(
            "procedure_documentation_generated",
            version=version,
            company_id=str(company_id) if company_id else "system-wide",
            content_hash=content_hash[:16],
        )

        return doc_version

    async def get_latest_version(
        self,
        db: AsyncSession,
        company_id: Optional[uuid.UUID] = None,
    ) -> Optional[ProcedureDocumentationVersion]:
        """Holt die neueste Version der Verfahrensdokumentation.

        Args:
            db: Datenbank-Session
            company_id: Optional - fuer firmenspezifische Dokumentation

        Returns:
            Neueste Version oder None
        """
        query = select(ProcedureDocumentationVersion)

        if company_id:
            query = query.where(ProcedureDocumentationVersion.company_id == company_id)
        else:
            query = query.where(ProcedureDocumentationVersion.company_id == None)

        query = query.order_by(desc(ProcedureDocumentationVersion.generated_at)).limit(1)

        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_version_history(
        self,
        db: AsyncSession,
        company_id: Optional[uuid.UUID] = None,
        limit: int = 10,
    ) -> list[ProcedureDocumentationVersion]:
        """Holt die Versionshistorie der Verfahrensdokumentation.

        Args:
            db: Datenbank-Session
            company_id: Optional - fuer firmenspezifische Dokumentation
            limit: Maximale Anzahl Versionen

        Returns:
            Liste der Versionen (neueste zuerst)
        """
        query = select(ProcedureDocumentationVersion)

        if company_id:
            query = query.where(ProcedureDocumentationVersion.company_id == company_id)
        else:
            query = query.where(ProcedureDocumentationVersion.company_id == None)

        query = query.order_by(desc(ProcedureDocumentationVersion.generated_at)).limit(limit)

        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_version_by_id(
        self,
        db: AsyncSession,
        version_id: uuid.UUID,
    ) -> Optional[ProcedureDocumentationVersion]:
        """Holt eine bestimmte Version der Verfahrensdokumentation.

        Args:
            db: Datenbank-Session
            version_id: Versions-ID

        Returns:
            Version oder None
        """
        result = await db.execute(
            select(ProcedureDocumentationVersion)
            .where(ProcedureDocumentationVersion.id == version_id)
        )
        return result.scalar_one_or_none()

    async def export_as_markdown(
        self,
        db: AsyncSession,
        version_id: uuid.UUID,
    ) -> str:
        """Exportiert die Verfahrensdokumentation als Markdown.

        Args:
            db: Datenbank-Session
            version_id: Versions-ID

        Returns:
            Markdown-String
        """
        version = await self.get_version_by_id(db, version_id)
        if not version:
            raise ValueError(f"Version {version_id} nicht gefunden")

        return self._content_to_markdown(version.content)

    # =========================================================================
    # Private Hilfsmethoden
    # =========================================================================

    async def _generate_content(
        self,
        db: AsyncSession,
        company_id: Optional[uuid.UUID],
    ) -> dict:
        """Generiert den Inhalt der Verfahrensdokumentation."""
        # Firmendaten laden wenn vorhanden
        company_info = None
        if company_id:
            result = await db.execute(
                select(Company).where(Company.id == company_id)
            )
            company = result.scalar_one_or_none()
            if company:
                company_info = {
                    "name": company.name,
                    "short_name": company.short_name,
                    "tax_id": company.tax_id if hasattr(company, 'tax_id') else None,
                }

        return {
            "meta": {
                "title": "Verfahrensdokumentation nach GoBD",
                "system": "Ablage-System OCR",
                "version": CURRENT_SYSTEM_VERSION,
                "generated_at": datetime.now().isoformat(),
                "company": company_info,
            },
            "sections": [
                self._section_allgemeine_beschreibung(),
                self._section_anwenderdokumentation(),
                self._section_technische_dokumentation(),
                self._section_betriebsdokumentation(),
                self._section_iks(),
                self._section_archivierung(),
                self._section_aufbewahrungsfristen(),
            ]
        }

    def _section_allgemeine_beschreibung(self) -> dict:
        """Kapitel 1: Allgemeine Beschreibung."""
        return {
            "title": "1. Allgemeine Beschreibung",
            "content": {
                "system_name": "Ablage-System OCR",
                "zweck": (
                    "Das Ablage-System OCR ist eine Enterprise-Plattform zur "
                    "automatisierten Verarbeitung, Archivierung und Verwaltung von "
                    "Geschaeftsdokumenten. Das System erfuellt die Anforderungen der "
                    "GoBD (Grundsaetze zur ordnungsmaessigen Fuehrung und Aufbewahrung "
                    "von Buechern, Aufzeichnungen und Unterlagen in elektronischer Form)."
                ),
                "funktionen": [
                    "Automatische Texterkennung (OCR) mit mehreren GPU-beschleunigten Backends",
                    "Revisionssichere Archivierung mit SHA-256 Signaturen",
                    "Automatische Aufbewahrungsfristen-Verwaltung",
                    "Multi-Mandanten-Faehigkeit mit strenger Datentrennung",
                    "Vollstaendiger Audit-Trail aller Dokumentenoperationen",
                    "DSGVO-konforme Datenverarbeitung",
                ],
                "rechtliche_grundlagen": [
                    "§147 AO (Abgabenordnung) - Ordnungsvorschriften fuer die Aufbewahrung von Unterlagen",
                    "§257 HGB (Handelsgesetzbuch) - Aufbewahrung von Unterlagen",
                    "§14b UStG (Umsatzsteuergesetz) - Aufbewahrung von Rechnungen",
                    "GoBD - Grundsaetze zur ordnungsmaessigen Fuehrung und Aufbewahrung",
                ],
            }
        }

    def _section_anwenderdokumentation(self) -> dict:
        """Kapitel 2: Anwenderdokumentation."""
        return {
            "title": "2. Anwenderdokumentation",
            "content": {
                "benutzerrollen": [
                    {
                        "rolle": "Administrator",
                        "berechtigungen": [
                            "Vollzugriff auf alle Systemfunktionen",
                            "Benutzerverwaltung",
                            "Systemkonfiguration",
                            "Aufbewahrungsfristen-Einstellungen",
                        ]
                    },
                    {
                        "rolle": "Benutzer",
                        "berechtigungen": [
                            "Dokumente hochladen und verarbeiten",
                            "Eigene Dokumente einsehen und bearbeiten",
                            "Dokumente archivieren",
                        ]
                    },
                    {
                        "rolle": "Steuerberater",
                        "berechtigungen": [
                            "Lesezugriff auf archivierte Dokumente",
                            "Export von Dokumenten",
                            "Zugriff zeitlich begrenzt",
                        ]
                    },
                ],
                "arbeitsablaeufe": [
                    {
                        "name": "Dokument-Upload",
                        "schritte": [
                            "Dokument ueber Web-Oberflaeche hochladen",
                            "System validiert Dateiformat und -groesse",
                            "Automatische OCR-Verarbeitung startet",
                            "Dokument wird klassifiziert und kategorisiert",
                        ]
                    },
                    {
                        "name": "Archivierung",
                        "schritte": [
                            "Dokument zur Archivierung auswaehlen",
                            "Aufbewahrungskategorie waehlen",
                            "System berechnet SHA-256 Hash",
                            "Dokument wird als unveraenderbar markiert",
                            "Aufbewahrungsfrist wird automatisch gesetzt",
                        ]
                    },
                ],
            }
        }

    def _section_technische_dokumentation(self) -> dict:
        """Kapitel 3: Technische Systemdokumentation."""
        return {
            "title": "3. Technische Systemdokumentation",
            "content": {
                "architektur": {
                    "backend": "FastAPI (Python 3.11+)",
                    "datenbank": "PostgreSQL 16 mit pgvector Extension",
                    "objektspeicher": "MinIO (S3-kompatibel)",
                    "cache": "Redis 7.x",
                    "task_queue": "Celery mit Redis Broker",
                },
                "ocr_backends": [
                    {
                        "name": "DeepSeek-Janus-Pro",
                        "typ": "Multimodal Vision-Language Model",
                        "vram": "12GB",
                        "staerken": "Beste Umlaut-Genauigkeit, Fraktur, komplexe Layouts",
                    },
                    {
                        "name": "GOT-OCR 2.0",
                        "typ": "Transformer-basiert",
                        "vram": "10GB",
                        "staerken": "Tabellen, Formeln, schnelle Verarbeitung",
                    },
                    {
                        "name": "Surya + Docling",
                        "typ": "Layout-Analyse Pipeline",
                        "vram": "0GB (CPU)",
                        "staerken": "CPU-Fallback, Layout-Erkennung",
                    },
                ],
                "sicherheit": {
                    "authentifizierung": "JWT mit httpOnly Cookies",
                    "passwort_hashing": "bcrypt (Cost Factor 12)",
                    "verschluesselung": "TLS 1.3 (in transit), MinIO SSE (at rest)",
                    "rate_limiting": "Pro Benutzer und IP-Adresse",
                },
                "datenschutz": {
                    "dsgvo_konformitaet": True,
                    "datenspeicherung": "On-Premises (keine Cloud)",
                    "audit_logging": "Alle Zugriffe werden protokolliert",
                    "recht_auf_loeschung": "Art. 17 DSGVO implementiert",
                },
            }
        }

    def _section_betriebsdokumentation(self) -> dict:
        """Kapitel 4: Betriebsdokumentation."""
        return {
            "title": "4. Betriebsdokumentation",
            "content": {
                "backup": {
                    "strategie": "Taegliche vollstaendige Backups",
                    "aufbewahrung": "30 Tage lokal, 90 Tage remote",
                    "komponenten": ["PostgreSQL", "Redis", "MinIO", "Konfiguration"],
                },
                "monitoring": {
                    "metriken": "Prometheus",
                    "dashboards": "Grafana",
                    "logging": "Loki (strukturierte Logs)",
                    "alerts": "Prometheus Alertmanager",
                },
                "wartung": {
                    "updates": "Geplante Wartungsfenster",
                    "patches": "Sicherheitspatches zeitnah",
                    "pruefungen": "Woechentliche Integritaetspruefung",
                },
            }
        }

    def _section_iks(self) -> dict:
        """Kapitel 5: Internes Kontrollsystem."""
        return {
            "title": "5. Internes Kontrollsystem (IKS)",
            "content": {
                "zugriffskontrollen": [
                    "Rollenbasierte Zugriffskontrolle (RBAC)",
                    "Mandantentrennung durch Row-Level Security",
                    "Authentifizierung ueber JWT-Token",
                    "Sitzungs-Timeout nach 15 Minuten Inaktivitaet",
                ],
                "integritaetskontrollen": [
                    "SHA-256 Hash-Signatur bei Archivierung",
                    "Woechentliche automatische Verifikation",
                    "Unveraenderbarkeit archivierter Dokumente",
                    "Audit-Trail fuer alle Aenderungen",
                ],
                "verfuegbarkeitskontrollen": [
                    "Taegliche automatische Backups",
                    "GPU-Fallback auf CPU bei Ausfall",
                    "Health-Checks alle 60 Sekunden",
                    "Automatischer Neustart bei Ausfall",
                ],
            }
        }

    def _section_archivierung(self) -> dict:
        """Kapitel 6: Archivierungskonzept."""
        return {
            "title": "6. Archivierungskonzept",
            "content": {
                "grundsaetze": {
                    "nachvollziehbarkeit": (
                        "Jede Dokumentenaktion wird im Audit-Trail protokolliert "
                        "mit Zeitstempel, Benutzer und Aenderungsdetails."
                    ),
                    "unveraenderbarkeit": (
                        "Archivierte Dokumente erhalten eine SHA-256 Hash-Signatur. "
                        "Aenderungen sind technisch gesperrt und werden bei Versuchen "
                        "mit HTTP 403 abgelehnt."
                    ),
                    "vollstaendigkeit": (
                        "Aufbewahrungsfristen werden automatisch ueberwacht. "
                        "90 Tage vor Ablauf erfolgt eine Warnung an Administratoren."
                    ),
                    "ordnung": (
                        "Dokumente werden nach Kategorien klassifiziert "
                        "(Rechnung, Vertrag, Geschaeftsbrief, etc.) mit "
                        "entsprechenden gesetzlichen Aufbewahrungsfristen."
                    ),
                },
                "hash_algorithmus": {
                    "algorithmus": "SHA-256",
                    "input": "Dateiinhalt + Metadaten + extrahierter Text",
                    "verifizierung": "Woechentliche automatische Pruefung",
                },
            }
        }

    def _section_aufbewahrungsfristen(self) -> dict:
        """Kapitel 7: Aufbewahrungsfristen."""
        return {
            "title": "7. Aufbewahrungsfristen",
            "content": {
                "kategorien": [
                    {
                        "kategorie": "Rechnungen",
                        "frist_jahre": 10,
                        "rechtsgrundlage": "§147 AO, §14b UStG",
                    },
                    {
                        "kategorie": "Vertraege",
                        "frist_jahre": 10,
                        "rechtsgrundlage": "§147 AO, §257 HGB",
                    },
                    {
                        "kategorie": "Geschaeftsbriefe",
                        "frist_jahre": 6,
                        "rechtsgrundlage": "§257 HGB",
                    },
                    {
                        "kategorie": "Buchungsbelege",
                        "frist_jahre": 10,
                        "rechtsgrundlage": "§147 AO",
                    },
                    {
                        "kategorie": "Jahresabschluesse",
                        "frist_jahre": 10,
                        "rechtsgrundlage": "§257 HGB",
                    },
                    {
                        "kategorie": "Steuerbelege",
                        "frist_jahre": 10,
                        "rechtsgrundlage": "§147 AO",
                    },
                    {
                        "kategorie": "Personalakten",
                        "frist_jahre": 10,
                        "rechtsgrundlage": "§257 HGB",
                    },
                ],
                "automatisierung": {
                    "erinnerung": "90 Tage vor Ablauf",
                    "pruefung": "Taeglich um 08:00 Uhr",
                    "loeschung": "Nur mit Admin-Genehmigung (Standard)",
                },
            }
        }

    def _increment_version(self, current_version: str) -> str:
        """Inkrementiert die Patch-Version."""
        parts = current_version.split(".")
        if len(parts) != 3:
            return "1.0.0"

        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
        return f"{major}.{minor}.{patch + 1}"

    def _compute_hash(self, content: dict) -> str:
        """Berechnet den SHA-256 Hash des Inhalts."""
        content_json = json.dumps(content, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content_json.encode("utf-8")).hexdigest()

    def _compute_changes(
        self,
        old_content: dict,
        new_content: dict,
    ) -> dict:
        """Ermittelt die Aenderungen zwischen zwei Versionen."""
        changes = {
            "added_sections": [],
            "modified_sections": [],
            "removed_sections": [],
        }

        old_sections = {s["title"]: s for s in old_content.get("sections", [])}
        new_sections = {s["title"]: s for s in new_content.get("sections", [])}

        for title in new_sections:
            if title not in old_sections:
                changes["added_sections"].append(title)
            elif new_sections[title] != old_sections[title]:
                changes["modified_sections"].append(title)

        for title in old_sections:
            if title not in new_sections:
                changes["removed_sections"].append(title)

        return changes

    def _content_to_markdown(self, content: dict) -> str:
        """Konvertiert den Inhalt zu Markdown."""
        lines = []

        # Header
        meta = content.get("meta", {})
        lines.append(f"# {meta.get('title', 'Verfahrensdokumentation')}")
        lines.append("")
        lines.append(f"**System:** {meta.get('system', 'Ablage-System')}")
        lines.append(f"**Version:** {meta.get('version', '1.0.0')}")
        lines.append(f"**Generiert:** {meta.get('generated_at', '')}")
        lines.append("")

        if meta.get("company"):
            lines.append(f"**Firma:** {meta['company'].get('name', '')}")
            lines.append("")

        lines.append("---")
        lines.append("")

        # Sections
        for section in content.get("sections", []):
            lines.append(f"## {section.get('title', '')}")
            lines.append("")
            lines.append(self._dict_to_markdown(section.get("content", {})))
            lines.append("")

        return "\n".join(lines)

    def _dict_to_markdown(self, data: dict, level: int = 0) -> str:
        """Konvertiert ein Dictionary zu Markdown."""
        lines = []
        indent = "  " * level

        for key, value in data.items():
            if isinstance(value, str):
                lines.append(f"{indent}**{key}:** {value}")
            elif isinstance(value, list):
                lines.append(f"{indent}**{key}:**")
                for item in value:
                    if isinstance(item, dict):
                        for k, v in item.items():
                            lines.append(f"{indent}  - **{k}:** {v}")
                    else:
                        lines.append(f"{indent}  - {item}")
            elif isinstance(value, dict):
                lines.append(f"{indent}**{key}:**")
                lines.append(self._dict_to_markdown(value, level + 1))
            elif isinstance(value, bool):
                lines.append(f"{indent}**{key}:** {'Ja' if value else 'Nein'}")
            else:
                lines.append(f"{indent}**{key}:** {value}")

        return "\n".join(lines)


# Singleton-Instanz
procedure_doc_service = ProcedureDocService()
