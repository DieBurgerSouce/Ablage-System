"""GoBD Verfahrensdokumentation Service.

Automatische Generierung und Versionierung der GoBD-Verfahrensdokumentation.

Die Verfahrensdokumentation beschreibt:
1. Allgemeine Beschreibung des Systems
2. Systemlandschaft und Rollenverteilung (Stand 08/2026: Odoo führend,
   Ablage-System = hash-gesicherte qualifizierte Zweitablage + Erfassungskanal)
3. Anwenderdokumentation (Benutzerhandbuch)
4. Technische Systemdokumentation (inkl. Odoo-Spiegel/-Push)
5. Betriebsdokumentation
6. Internes Kontrollsystem (IKS)
7. Archivierungskonzept
8. Aufbewahrungsfristen (mit führendem System je Kategorie)

Erfuellt GoBD-Anforderungen:
- Automatische Versionierung bei Systemupdates
- Hash-Signatur für Unveränderbarkeit
- Vollständige Änderungshistorie
"""

import hashlib
import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import ProcedureDocumentationVersion, Company
from app.services.compliance.document_signer import DocumentSigner
from app.services.storage_service import get_storage_service

logger = structlog.get_logger(__name__)


# Aktuelle System-Version (wird bei Updates inkrementiert)
# 2.0.0: Odoo-Umstellung 08/2026 — Odoo 18 ist führendes ERP, das Ablage-System
# ist hash-gesicherte qualifizierte Zweitablage + Erfassungskanal (Revision 2026.07).
CURRENT_SYSTEM_VERSION = "2.0.0"


class ProcedureDocService:
    """Service für die Generierung der GoBD-Verfahrensdokumentation."""

    async def generate_documentation(
        self,
        db: AsyncSession,
        company_id: Optional[uuid.UUID] = None,
        change_summary: Optional[str] = None,
    ) -> ProcedureDocumentationVersion:
        """Generiert eine neue Version der Verfahrensdokumentation.

        Args:
            db: Datenbank-Session
            company_id: Optional - für firmenspezifische Dokumentation
            change_summary: Zusammenfassung der Änderungen

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

        # Änderungen ermitteln
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

    async def generate_signed_pdf(
        self,
        db: AsyncSession,
        company_id: Optional[uuid.UUID] = None,
    ) -> ProcedureDocumentationVersion:
        """Rendert die neueste Verfahrensdokumentation als PDF, signiert sie intern
        (RSA-PSS, on-premises) und legt sie in MinIO ab. Signatur-Metadaten +
        Objektschluessel werden auf der Version persistiert. Ohne Version wird erst eine
        erzeugt. Ohne MinIO -> RuntimeError (ehrlich: ohne Storage keine Persistenz).
        """
        version = await self.get_latest_version(db, company_id)
        if version is None:
            version = await self.generate_documentation(db, company_id)

        pdf_bytes = self._render_pdf(version)
        pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
        sig = DocumentSigner().sign(pdf_bytes)

        storage = get_storage_service()
        result = await storage.upload_document(
            file_data=pdf_bytes,
            filename=f"verfahrensdokumentation_v{version.version}.pdf",
            content_type="application/pdf",
            user_id=str(company_id) if company_id else "system",
            metadata={
                "gobd": "verfahrensdokumentation",
                "version": str(version.version),
                "content-hash": version.content_hash,
                "pdf-sha256": pdf_sha256,
                "signature-alg": sig["alg"],
                "signing-cert-serial": sig["cert_serial"],
            },
        )
        object_key = (
            result.get("object_key")
            or result.get("storage_path")
            or result.get("path")
            or result.get("key")
        )

        version.pdf_object_key = object_key
        version.pdf_sha256 = pdf_sha256
        version.pdf_signature = sig["signature"]
        version.pdf_signature_alg = sig["alg"]
        version.pdf_signing_cert_serial = sig["cert_serial"]
        version.pdf_signed_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(version)

        logger.info(
            "procedure_documentation_pdf_signed",
            version=version.version,
            company_id=str(company_id) if company_id else "system-wide",
            pdf_sha256=pdf_sha256[:16],
            object_key=object_key,
        )
        return version

    def _render_pdf(self, version: ProcedureDocumentationVersion) -> bytes:
        """Rendert die Verfahrensdokumentation als PDF (reportlab)."""
        from io import BytesIO
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

        buf = BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
            title=f"GoBD-Verfahrensdokumentation v{version.version}",
        )
        styles = getSampleStyleSheet()
        story = [
            Paragraph("GoBD-Verfahrensdokumentation", styles["Title"]),
            Paragraph(f"Version {self._xml(version.version)}", styles["Heading2"]),
            Paragraph(f"Erzeugt: {self._xml(str(version.generated_at))}", styles["Normal"]),
            Paragraph(
                f"Inhalts-Hash (SHA-256): {self._xml(version.content_hash)}",
                styles["Normal"],
            ),
            Spacer(1, 12),
        ]
        self._content_flowables(version.content, story, styles, level=0)
        doc.build(story)
        return buf.getvalue()

    @staticmethod
    def _xml(text) -> str:
        """XML-escape fuer reportlab-Paragraphs."""
        return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _content_flowables(self, obj, story, styles, level: int) -> None:
        """Rendert den JSON-Inhalt rekursiv in reportlab-Flowables."""
        from reportlab.platypus import Paragraph, Spacer

        heading = styles["Heading%d" % min(level + 2, 4)]
        if isinstance(obj, dict):
            for key, val in obj.items():
                story.append(Paragraph(self._xml(key), heading))
                self._content_flowables(val, story, styles, level + 1)
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                self._content_flowables(item, story, styles, level)
        else:
            story.append(Paragraph(self._xml(obj), styles["Normal"]))
            story.append(Spacer(1, 4))

    async def get_latest_version(
        self,
        db: AsyncSession,
        company_id: Optional[uuid.UUID] = None,
    ) -> Optional[ProcedureDocumentationVersion]:
        """Holt die neueste Version der Verfahrensdokumentation.

        Args:
            db: Datenbank-Session
            company_id: Optional - für firmenspezifische Dokumentation

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
            company_id: Optional - für firmenspezifische Dokumentation
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
                self._section_systemlandschaft(),
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
                    "Das Ablage-System OCR ist eine Plattform zur automatisierten "
                    "Verarbeitung, Archivierung und Verwaltung von Geschäftsdokumenten. "
                    "Seit dem 01.08.2026 ist Odoo 18 das führende ERP-System für die "
                    "Geschäftsprozesse und die Aufbewahrung der dort erzeugten Belege; "
                    "das Ablage-System wird daneben als hash-gesicherte qualifizierte "
                    "Zweitablage (vollständiger Spiegel aller Odoo-Belege), als "
                    "Erfassungskanal für den Papier- und E-Mail-Eingang (lokale OCR, "
                    "Übergabe als Entwurfs-Lieferantenrechnung an Odoo) und als "
                    "Aufbewahrungsort für Nicht-Odoo-Dokumente betrieben. Das System "
                    "erfuellt die Anforderungen der GoBD (Grundsätze zur "
                    "ordnungsmaessigen Führung und Aufbewahrung von Buechern, "
                    "Aufzeichnungen und Unterlagen in elektronischer Form)."
                ),
                "funktionen": [
                    "Automatische Texterkennung (OCR) mit mehreren GPU-beschleunigten Backends",
                    "Revisionssichere Archivierung mit SHA-256 Signaturen",
                    "Automatische Aufbewahrungsfristen-Verwaltung",
                    "Multi-Mandanten-Fähigkeit mit strenger Datentrennung",
                    "Vollständiger Audit-Trail aller Dokumentenoperationen",
                    "DSGVO-konforme Datenverarbeitung",
                ],
                "rechtliche_grundlagen": [
                    "§147 AO (Abgabenordnung) - Ordnungsvorschriften für die Aufbewahrung von Unterlagen",
                    "§257 HGB (Handelsgesetzbuch) - Aufbewahrung von Unterlagen",
                    "§14b UStG (Umsatzsteuergesetz) - Aufbewahrung von Rechnungen",
                    "GoBD - Grundsätze zur ordnungsmaessigen Führung und Aufbewahrung",
                ],
            }
        }

    def _section_systemlandschaft(self) -> dict:
        """Kapitel 2: Systemlandschaft und Rollenverteilung (Stand 08/2026).

        Inhaltlich synchron zur Markdown-Fassung in
        `compliance/procedure_documentation_service._generate_system_landscape_section`
        (Revision 2026.07) — beide beschreiben dieselbe Odoo-Rollenverteilung.
        """
        return {
            "title": "2. Systemlandschaft und Rollenverteilung (Stand 08/2026)",
            "content": {
                "beteiligte_systeme": [
                    {
                        "system": "Odoo 18 (ERP)",
                        "betriebsform": "SaaS",
                        "rolle": (
                            "Führendes System: Verkauf, Einkauf, Fakturierung, "
                            "offene Posten, Bankabgleich, Mahnwesen, E-Rechnung, "
                            "DATEV-Übergabe; Aufbewahrung der in Odoo erzeugten "
                            "Belege inkl. ZUGFeRD-Originale"
                        ),
                    },
                    {
                        "system": "Ablage-System (dieses DMS)",
                        "betriebsform": "On-Premises",
                        "rolle": (
                            "Hash-gesicherte qualifizierte Zweitablage aller "
                            "Odoo-Belege; Erfassungskanal für Papier- und "
                            "E-Mail-Eingang; Aufbewahrungsort für "
                            "Nicht-Odoo-Dokumente und private Unterlagen"
                        ),
                    },
                    {
                        "system": "Lexware (Altsystem)",
                        "betriebsform": "Lokal",
                        "rolle": (
                            "Alt-Archiv der Belege bis zur Umstellung; "
                            "ausschließlich Lesezugriff bis zum Auslauf"
                        ),
                    },
                ],
                "datenzugriff_betriebspruefung": (
                    "Die Auskunftserteilung bei Betriebsprüfungen (Datenzugriff "
                    "Z1–Z3) erfolgt über Odoo bzw. den DATEV-Bestand der "
                    "Steuerberatung. Das Archiv des Ablage-Systems dient als "
                    "Recherche-, Sicherungs- und SaaS-Exit-Ebene (vollständige "
                    "lokale Kopie aller Belege)."
                ),
                "eingefrorene_module": (
                    "Die früher im Ablage-System vorgesehenen ERP-Doppelfunktionen "
                    "(u. a. Mahnwesen, Banking, DATEV-Export, "
                    "E-Rechnungs-Erzeugung) sind eingefroren und deaktiviert "
                    "(Modul-Registry; deaktivierte Endpunkte liefern HTTP 404)."
                ),
                "spiegel_pull_odoo_zu_ablage": {
                    "beschreibung": (
                        "Alle in Odoo erzeugten oder geänderten Belege werden "
                        "automatisch in das Ablage-System gespiegelt und dort "
                        "GoBD-konform archiviert."
                    ),
                    "abrufintervall": (
                        "alle 30 Minuten (Celery-Beat, inkrementeller Cursor auf "
                        "dem Odoo-Änderungsdatum)"
                    ),
                    "hash_verifikation": (
                        "SHA-256-Prüfung jedes Anhangs gegen die von Odoo "
                        "gelieferte Prüfsumme (ir.attachment.checksum)"
                    ),
                    "idempotenz": (
                        "Dreistufige Duplikatprüfung (externe Odoo-ID, "
                        "Datei-Hash, nie überschreiben) — es entstehen keine "
                        "Duplikate"
                    ),
                    "archivierung": (
                        "Aufnahme in die Merkle-Audit-Chain, optional "
                        "qualifizierter Zeitstempel nach RFC 3161 (TSA)"
                    ),
                },
                "beleg_push_ablage_zu_odoo": {
                    "beschreibung": (
                        "Der Papier- und E-Mail-Eingang wird im Ablage-System "
                        "erfasst und als Entwurfs-Lieferantenrechnung an Odoo "
                        "übergeben."
                    ),
                    "schritte": [
                        "Erfassung: Scanner-Hotfolder (Scan-to-Ablage) bzw. zentrale Rechnungs-Mailadresse (IMAP-Import)",
                        "Verarbeitung: lokale OCR-Texterkennung (On-Premises, kein Cloud-Dienst), Klassifizierung, Datenextraktion",
                        "Archivierung: automatischer GoBD-Archivierungslauf (Karenzzeit: 3 Tage für Korrekturen)",
                        "Übergabe: Entwurfs-Lieferantenrechnung in Odoo mit Partner-Matching; nur eindeutige Zuordnungen werden übertragen",
                        "Review-Queue: nicht eindeutig zuordenbare Rechnungen werden als Aufgabe manuell nachbearbeitet",
                        "Idempotenz: Duplikatprüfung verhindert doppelte Rechnungsentwürfe in Odoo",
                    ],
                },
                "verantwortlichkeiten": [
                    {
                        "aufgabe": "Systemadministration, Benutzerverwaltung, Freigaben",
                        "verantwortlich": "Administrator (Systemverantwortlicher)",
                    },
                    {
                        "aufgabe": "Belegerfassung (Scan/E-Mail), Bearbeitung der Review-Queue",
                        "verantwortlich": "Büro-Team (Sachbearbeitung)",
                    },
                    {
                        "aufgabe": "Buchführung, Jahresabschluss, DATEV-Übergabe",
                        "verantwortlich": "Externe Steuerberatung (über Odoo/DATEV)",
                    },
                ],
                "aenderungsvermerk": (
                    "Revision 2026.07 (Juli 2026, Odoo-Umstellung): Kapitel "
                    "Systemlandschaft neu aufgenommen; Odoo 18 ab 01.08.2026 "
                    "führendes System; Ablage-System als hash-gesicherte "
                    "qualifizierte Zweitablage und Erfassungskanal; "
                    "ERP-Doppelfunktionen eingefroren."
                ),
            },
        }

    def _section_anwenderdokumentation(self) -> dict:
        """Kapitel 3: Anwenderdokumentation."""
        return {
            "title": "3. Anwenderdokumentation",
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
                "arbeitsabläufe": [
                    {
                        "name": "Dokument-Upload",
                        "schritte": [
                            "Dokument über Web-Oberflaeche hochladen",
                            "System validiert Dateiformat und -größe",
                            "Automatische OCR-Verarbeitung startet",
                            "Dokument wird klassifiziert und kategorisiert",
                        ]
                    },
                    {
                        "name": "Beleg-Eingang (Scan/E-Mail) mit Odoo-Übergabe",
                        "schritte": [
                            "Papierbeleg über Scanner-Hotfolder bzw. E-Rechnung/PDF über die zentrale Rechnungs-Mailadresse (IMAP) erfassen",
                            "Lokale OCR-Texterkennung, Klassifizierung und Datenextraktion (On-Premises)",
                            "Automatische GoBD-Archivierung nach Karenzzeit von 3 Tagen (täglicher Auto-Archivierungslauf)",
                            "Anlage einer Entwurfs-Lieferantenrechnung in Odoo (Partner-Matching, nur eindeutige Treffer)",
                            "Ohne eindeutige Zuordnung: Aufgabe in der Review-Queue zur manuellen Nachbearbeitung",
                        ]
                    },
                    {
                        "name": "Archivierung",
                        "schritte": [
                            "Dokument zur Archivierung auswählen",
                            "Aufbewahrungskategorie wählen",
                            "System berechnet SHA-256 Hash",
                            "Dokument wird als unveränderbar markiert",
                            "Aufbewahrungsfrist wird automatisch gesetzt",
                        ]
                    },
                ],
            }
        }

    def _section_technische_dokumentation(self) -> dict:
        """Kapitel 4: Technische Systemdokumentation."""
        return {
            "title": "4. Technische Systemdokumentation",
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
                        "name": "Surya (GPU)",
                        "typ": "Layout-Analyse + Texterkennung",
                        "vram": "ca. 4GB",
                        "einsatz": "Produktiver Standard (Realmessung Dez 2025: korrekte IBAN/BIC, keine Halluzinationen)",
                    },
                    {
                        "name": "PaddleOCR",
                        "typ": "CNN-basiert (Docker-Container)",
                        "vram": "GPU optional",
                        "einsatz": "Präzisions-Backend für 100% Umlaut-Genauigkeit",
                    },
                    {
                        "name": "Surya + Docling (CPU)",
                        "typ": "Layout-Analyse Pipeline",
                        "vram": "0GB (CPU)",
                        "einsatz": "CPU-Fallback bei GPU-Ausfall",
                    },
                ],
                "odoo_integration": {
                    "protokoll": "XML-RPC (Odoo External API), API-Key-Authentifizierung",
                    "spiegel": (
                        "Inkrementeller Pull aller Odoo-Belege alle 30 Minuten "
                        "(Cursor auf write_date, 5-Minuten-Overlap); "
                        "SHA-256-Verifikation gegen ir.attachment.checksum; "
                        "GoBD-Einbuchung jedes gespiegelten Belegs"
                    ),
                    "push": (
                        "Anlage von Entwurfs-Lieferantenrechnungen (account.move, "
                        "move_type=in_invoice) inklusive PDF-Hauptanhang; "
                        "Partner-Matching-Kaskade, nur eindeutige Treffer"
                    ),
                    "mandanten_kontext": (
                        "Odoo-Company-Kontext (allowed_company_ids) je Verbindung; "
                        "Rate-Limit und Fehler-Backoff über die "
                        "Verbindungs-Konfiguration"
                    ),
                },
                "sicherheit": {
                    "authentifizierung": "JWT mit httpOnly Cookies",
                    "passwort_hashing": "bcrypt (Cost Factor 12)",
                    "verschlüsselung": "TLS 1.3 (in transit), MinIO SSE (at rest)",
                    "rate_limiting": "Pro Benutzer und IP-Adresse",
                },
                "datenschutz": {
                    "dsgvo_konformität": True,
                    "datenspeicherung": "On-Premises (keine Cloud)",
                    "audit_logging": "Alle Zugriffe werden protokolliert",
                    "recht_auf_löschung": "Art. 17 DSGVO implementiert",
                },
            }
        }

    def _section_betriebsdokumentation(self) -> dict:
        """Kapitel 5: Betriebsdokumentation."""
        return {
            "title": "5. Betriebsdokumentation",
            "content": {
                "backup": {
                    "strategie": (
                        "restic-Snapshots nach 3-2-1-Prinzip: lokales Repository "
                        "(NAS/USB) + client-verschlüsseltes Cloud-Repository"
                    ),
                    "aufbewahrung": (
                        "Retention-Policy im Backup-Skript (restic forget --prune); "
                        "woechentlicher restic-Integritätscheck; "
                        "vierteljährliche Restore-Tests (DR-Runbook)"
                    ),
                    "komponenten": ["PostgreSQL (pg_dump)", "MinIO-Objektbestand", "Konfiguration (.env)"],
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
                    "prüfungen": "Woechentliche Integritätsprüfung",
                },
            }
        }

    def _section_iks(self) -> dict:
        """Kapitel 6: Internes Kontrollsystem."""
        return {
            "title": "6. Internes Kontrollsystem (IKS)",
            "content": {
                "zugriffskontrollen": [
                    "Rollenbasierte Zugriffskontrolle (RBAC)",
                    "Mandantentrennung durch Row-Level Security",
                    "Authentifizierung über JWT-Token",
                    "Sitzungs-Timeout nach 15 Minuten Inaktivität",
                ],
                "integritätskontrollen": [
                    "SHA-256 Hash-Signatur bei Archivierung",
                    "Woechentliche automatische Verifikation",
                    "Unveränderbarkeit archivierter Dokumente",
                    "Audit-Trail für alle Änderungen",
                ],
                "verfügbarkeitskontrollen": [
                    "Tägliche automatische Backups",
                    "GPU-Fallback auf CPU bei Ausfall",
                    "Health-Checks alle 60 Sekunden",
                    "Automatischer Neustart bei Ausfall",
                ],
            }
        }

    def _section_archivierung(self) -> dict:
        """Kapitel 7: Archivierungskonzept."""
        return {
            "title": "7. Archivierungskonzept",
            "content": {
                "grundsätze": {
                    "nachvollziehbarkeit": (
                        "Jede Dokumentenaktion wird im Audit-Trail protokolliert "
                        "mit Zeitstempel, Benutzer und Änderungsdetails."
                    ),
                    "unveränderbarkeit": (
                        "Archivierte Dokumente erhalten eine SHA-256 Hash-Signatur. "
                        "Änderungen sind technisch gesperrt und werden bei Versuchen "
                        "mit HTTP 403 abgelehnt."
                    ),
                    "vollständigkeit": (
                        "Aufbewahrungsfristen werden automatisch überwacht. "
                        "90 Tage vor Ablauf erfolgt eine Warnung an Administratoren."
                    ),
                    "ordnung": (
                        "Dokumente werden nach Kategorien klassifiziert "
                        "(Rechnung, Vertrag, Geschäftsbrief, etc.) mit "
                        "entsprechenden gesetzlichen Aufbewahrungsfristen."
                    ),
                },
                "hash_algorithmus": {
                    "algorithmus": "SHA-256",
                    "input": "Dateiinhalt + Metadaten + extrahierter Text",
                    "verifizierung": "Woechentliche automatische Prüfung",
                },
            }
        }

    def _section_aufbewahrungsfristen(self) -> dict:
        """Kapitel 8: Aufbewahrungsfristen."""
        return {
            "title": "8. Aufbewahrungsfristen",
            "content": {
                "hinweis_fuehrendes_system": (
                    "Für die in Odoo erzeugten Belege (Ein-/Ausgangsrechnungen "
                    "inkl. ZUGFeRD-Originale) ist Odoo das führende "
                    "Aufbewahrungssystem; das Ablage-System hält den "
                    "hash-gesicherten Spiegel. Für Papier-/E-Mail-Eingang, "
                    "Verträge, Personal, Alt-Archiv (Lexware/WA-WE 2008–2026) "
                    "und private Unterlagen ist das Ablage-System das führende "
                    "Aufbewahrungssystem."
                ),
                "kategorien": [
                    {
                        "kategorie": "Rechnungen (Odoo-Belege)",
                        "fuehrendes_system": "Odoo (Ablage-System = Spiegel)",
                        "frist_jahre": 10,
                        "rechtsgrundlage": "§147 AO, §14b UStG",
                    },
                    {
                        "kategorie": "Rechnungen (Papier-/E-Mail-Eingang)",
                        "fuehrendes_system": "Ablage-System",
                        "frist_jahre": 10,
                        "rechtsgrundlage": "§147 AO, §14b UStG",
                    },
                    {
                        "kategorie": "Verträge",
                        "fuehrendes_system": "Ablage-System",
                        "frist_jahre": 10,
                        "rechtsgrundlage": "§147 AO, §257 HGB",
                    },
                    {
                        "kategorie": "Geschäftsbriefe",
                        "fuehrendes_system": "Ablage-System",
                        "frist_jahre": 6,
                        "rechtsgrundlage": "§257 HGB",
                    },
                    {
                        "kategorie": "Buchungsbelege",
                        "fuehrendes_system": "Ablage-System",
                        "frist_jahre": 10,
                        "rechtsgrundlage": "§147 AO",
                    },
                    {
                        "kategorie": "Jahresabschluesse",
                        "fuehrendes_system": "Odoo/DATEV (Steuerberatung)",
                        "frist_jahre": 10,
                        "rechtsgrundlage": "§257 HGB",
                    },
                    {
                        "kategorie": "Steuerbelege",
                        "fuehrendes_system": "Ablage-System",
                        "frist_jahre": 10,
                        "rechtsgrundlage": "§147 AO",
                    },
                    {
                        "kategorie": "Personalakten",
                        "fuehrendes_system": "Ablage-System",
                        "frist_jahre": 10,
                        "rechtsgrundlage": "§257 HGB",
                    },
                    {
                        "kategorie": "Alt-Archiv (Lexware / WA-WE 2008–2026)",
                        "fuehrendes_system": "Ablage-System",
                        "frist_jahre": 10,
                        "rechtsgrundlage": "§147 AO (bis Fristablauf der Belegjahre)",
                    },
                ],
                "automatisierung": {
                    "erinnerung": "90 Tage vor Ablauf",
                    "prüfung": "Täglich um 08:00 Uhr",
                    "löschung": "Nur mit Admin-Genehmigung (Standard)",
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
        """Ermittelt die Änderungen zwischen zwei Versionen."""
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


# Singleton-Instanz mit Thread-Safety (Double-Check Locking)
_procedure_doc_service: Optional[ProcedureDocService] = None
_procedure_doc_service_lock = threading.Lock()


def get_procedure_doc_service() -> ProcedureDocService:
    """Factory für ProcedureDocService Singleton mit Thread-Safety."""
    global _procedure_doc_service
    if _procedure_doc_service is None:
        with _procedure_doc_service_lock:
            # Double-Check Locking: Erneut prüfen nach Lock-Erwerb
            if _procedure_doc_service is None:
                _procedure_doc_service = ProcedureDocService()
    return _procedure_doc_service


# Rückwärtskompatibilität: Lazy Property für direkten Import
class _LazyProcedureDocService:
    """Lazy Wrapper für Rückwärtskompatibilität."""

    def __getattr__(self, name: str):
        return getattr(get_procedure_doc_service(), name)


procedure_doc_service = _LazyProcedureDocService()
