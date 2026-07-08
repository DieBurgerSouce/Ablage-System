# -*- coding: utf-8 -*-
"""Unit-Tests für den GoBD-Verfahrensdokumentations-Generator.

Fokus: Abschnitt 6 „Systemlandschaft und Rollenverteilung (Stand 08/2026)"
(Odoo-Umstellung 2026-07) sowie die Kapitel-Nummerierung im Export.
"""

import uuid
from datetime import datetime, timezone
from typing import Dict

import pytest

from app.services.compliance.procedure_documentation_service import (
    DocumentSection,
    DocumentationMetadata,
    ProcedureDocumentation,
    ProcedureDocumentationService,
    SystemStatistics,
)


@pytest.fixture
def service() -> ProcedureDocumentationService:
    """Gibt eine Service-Instanz zurueck."""
    return ProcedureDocumentationService()


def _make_documentation(
    sections: Dict[DocumentSection, str],
) -> ProcedureDocumentation:
    """Baut ein Dokumentationsobjekt ohne DB-Zugriff."""
    now = datetime.now(timezone.utc)
    metadata = DocumentationMetadata(
        company_name="Testfirma GmbH",
        company_id=uuid.uuid4(),
        generated_at=now,
        generated_by="Test-User",
        version=ProcedureDocumentationService.DOCUMENT_VERSION,
        valid_from=now,
    )
    return ProcedureDocumentation(
        metadata=metadata,
        statistics=SystemStatistics(),
        sections=sections,
        change_history=[
            {
                "date": "2026-07-01",
                "version": "1.0",
                "description": "Testeintrag",
                "author": "System",
            }
        ],
    )


class TestSystemLandscapeSection:
    """Tests fuer Abschnitt 6 (Systemlandschaft, Odoo-Umstellung 08/2026)."""

    def test_enum_enthaelt_systemlandschaft_als_sechste_sektion(self) -> None:
        """Neue Sektion existiert und steht am Ende (=> Kapitel 6)."""
        assert len(DocumentSection) == 6
        assert DocumentSection.SYSTEM_LANDSCAPE.value == "system_landscape"
        # Enum-Reihenfolge bestimmt die Kapitelnummer im Export.
        assert list(DocumentSection)[-1] is DocumentSection.SYSTEM_LANDSCAPE

    def test_dokumentversion_2026_07(
        self, service: ProcedureDocumentationService
    ) -> None:
        """Versionsvermerk der Odoo-Umstellung (2026-07)."""
        assert service.DOCUMENT_VERSION == "2026.07"

    async def test_systemlandschaft_inhalt(
        self, service: ProcedureDocumentationService
    ) -> None:
        """Kernaussagen der Odoo-Umstellung sind enthalten (Plan §7 R3)."""
        content = await service._generate_system_landscape_section(
            None, uuid.uuid4()
        )
        assert content.startswith(
            "# 6. Systemlandschaft und Rollenverteilung (Stand 08/2026)"
        )
        # GoBD-Einordnung des Odoo-Spiegels:
        assert "qualifizierte Zweitablage" in content
        assert "ir.attachment.checksum" in content
        assert "RFC 3161" in content
        assert "alle 30 Minuten" in content
        # Erfassungskanal (Scan/E-Mail -> OCR -> Archiv -> Odoo-Entwurf):
        assert "Karenzzeit: 3 Tage" in content
        assert "Review-Queue" in content
        # Betriebspruefung laeuft ueber Odoo/DATEV:
        assert "Z1–Z3" in content
        # Aufbewahrungsfristen:
        assert "§ 147 AO" in content
        assert "§ 14b UStG" in content
        assert "Lexware" in content
        # Versions-/Aenderungsvermerk der Odoo-Umstellung:
        assert "Revision 2026.07" in content

    async def test_export_markdown_nummerierung(
        self, service: ProcedureDocumentationService
    ) -> None:
        """Abschnitt 6 im Export; Aenderungshistorie rueckt auf Kapitel 7."""
        landscape = await service._generate_system_landscape_section(
            None, uuid.uuid4()
        )
        doc = _make_documentation({DocumentSection.SYSTEM_LANDSCAPE: landscape})
        markdown = service._export_markdown(doc).decode("utf-8")
        assert (
            "# 6. Systemlandschaft und Rollenverteilung (Stand 08/2026)" in markdown
        )
        assert "# 7. Änderungshistorie" in markdown
        assert "# 6. Änderungshistorie" not in markdown
