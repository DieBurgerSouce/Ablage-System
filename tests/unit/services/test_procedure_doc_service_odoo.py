# -*- coding: utf-8 -*-
"""Unit-Tests: Odoo-Awareness der DB-versionierten Verfahrensdokumentation.

Deckt die Revision 2026.07 (Odoo-Umstellung 08/2026) in beiden Diensten ab:
- Service 2: `app.services.procedure_doc_service.ProcedureDocService`
  (DB-versioniert, signiertes PDF, Migration 270)
- Service 3: `app.services.gobd_compliance_service` →
  `generate_verfahrensdokumentation()` (speist /api/v1/compliance/…)

Kernaussagen: Odoo 18 = führendes System, Ablage = hash-gesicherte
qualifizierte Zweitablage + Erfassungskanal; kein aktiver DATEV-Export mehr
(Modul eingefroren, DATEV läuft über Odoo/Steuerberatung).
"""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.procedure_doc_service import (
    CURRENT_SYSTEM_VERSION,
    ProcedureDocService,
)


@pytest.fixture
def service() -> ProcedureDocService:
    return ProcedureDocService()


class TestProcedureDocServiceOdoo:
    """Service 2: DB-versionierte Verfahrensdoku ist Odoo-aware."""

    def test_system_version_2_0_0(self) -> None:
        """Versions-Bump der Odoo-Umstellung."""
        assert CURRENT_SYSTEM_VERSION == "2.0.0"

    async def test_kapitelstruktur_acht_sektionen(
        self, service: ProcedureDocService
    ) -> None:
        """8 Kapitel, fortlaufend nummeriert, Systemlandschaft = Kapitel 2."""
        content = await service._generate_content(None, None)
        titles = [s["title"] for s in content["sections"]]
        assert len(titles) == 8
        for i, title in enumerate(titles, start=1):
            assert title.startswith(f"{i}. "), title
        assert titles[1] == "2. Systemlandschaft und Rollenverteilung (Stand 08/2026)"
        assert content["meta"]["version"] == "2.0.0"

    def test_systemlandschaft_kernaussagen(
        self, service: ProcedureDocService
    ) -> None:
        """GoBD-Einordnung des Spiegels (Plan §7 R3) + Push-Kanal."""
        section = service._section_systemlandschaft()
        blob = json.dumps(section, ensure_ascii=False)
        assert "Odoo 18" in blob
        assert "Führendes System" in blob
        assert "qualifizierte Zweitablage" in blob
        assert "ir.attachment.checksum" in blob
        assert "alle 30 Minuten" in blob
        assert "RFC 3161" in blob
        assert "Karenzzeit: 3 Tage" in blob
        assert "Review-Queue" in blob
        assert "eingefroren" in blob
        assert "Revision 2026.07" in blob

    def test_zweck_beschreibt_rollenverteilung(
        self, service: ProcedureDocService
    ) -> None:
        section = service._section_allgemeine_beschreibung()
        zweck = section["content"]["zweck"]
        assert "Odoo 18" in zweck
        assert "führende" in zweck
        assert "Zweitablage" in zweck
        assert "Entwurfs-Lieferantenrechnung" in zweck

    def test_ocr_backends_dez_2025_realitaet(
        self, service: ProcedureDocService
    ) -> None:
        """Produktive Backends laut Realmessung Dez 2025 — kein GOT-OCR/DeepSeek
        mehr als Produktiv-Backend (IBAN-Halluzination bzw. erfundene Inhalte)."""
        section = service._section_technische_dokumentation()
        blob = json.dumps(section, ensure_ascii=False)
        assert "Surya" in blob
        assert "PaddleOCR" in blob
        assert "GOT-OCR" not in blob
        assert "DeepSeek" not in blob

    def test_technik_enthaelt_odoo_integration(
        self, service: ProcedureDocService
    ) -> None:
        section = service._section_technische_dokumentation()
        odoo = section["content"]["odoo_integration"]
        assert "XML-RPC" in odoo["protokoll"]
        assert "ir.attachment.checksum" in odoo["spiegel"]
        assert "in_invoice" in odoo["push"]

    def test_aufbewahrungsfristen_mit_fuehrendem_system(
        self, service: ProcedureDocService
    ) -> None:
        section = service._section_aufbewahrungsfristen()
        content = section["content"]
        assert "Odoo" in content["hinweis_fuehrendes_system"]
        systeme = {k["fuehrendes_system"] for k in content["kategorien"]}
        assert any("Odoo" in s for s in systeme)
        assert any("Ablage-System" in s for s in systeme)

    async def test_kein_aktiver_datev_export(
        self, service: ProcedureDocService
    ) -> None:
        """DATEV taucht nur als eingefrorenes Modul bzw. als Übergabe-über-Odoo
        auf, nie als eigener aktiver Export-Prozess des Ablage-Systems."""
        content = await service._generate_content(None, None)
        blob = json.dumps(content, ensure_ascii=False)
        assert "DATEV-Format" not in blob
        # "DATEV-Export" darf ausschließlich im Eingefroren-Vermerk der
        # Systemlandschaft stehen — nirgendwo sonst (kein aktiver Prozess).
        for section in content["sections"]:
            section_blob = json.dumps(section, ensure_ascii=False)
            if section["title"].startswith("2. Systemlandschaft"):
                assert "DATEV-Export" in section["content"]["eingefrorene_module"]
            else:
                assert "DATEV-Export" not in section_blob, section["title"]

    async def test_render_pdf_mit_neuem_inhalt(
        self, service: ProcedureDocService
    ) -> None:
        """Der reportlab-Renderer verkraftet die neue Kapitelstruktur."""
        content = await service._generate_content(None, None)
        fake_version = SimpleNamespace(
            version="2.0.0",
            generated_at="2026-07-11T00:00:00+00:00",
            content_hash=service._compute_hash(content),
            content=content,
        )
        pdf_bytes = service._render_pdf(fake_version)  # type: ignore[arg-type]
        assert pdf_bytes.startswith(b"%PDF")
        assert len(pdf_bytes) > 2000

    async def test_markdown_export_enthaelt_systemlandschaft(
        self, service: ProcedureDocService
    ) -> None:
        content = await service._generate_content(None, None)
        markdown = service._content_to_markdown(content)
        assert "## 2. Systemlandschaft und Rollenverteilung (Stand 08/2026)" in markdown
        assert "qualifizierte Zweitablage" in markdown


class TestGoBDComplianceVerfahrensdokuOdoo:
    """Service 3: Compliance-Endpoint-Doku ist Odoo-aware."""

    @pytest.fixture
    def gobd_service(self):
        from app.services.gobd_compliance_service import GoBDComplianceService

        return GoBDComplianceService()

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db.get = AsyncMock(
            return_value=SimpleNamespace(name="Testfirma GmbH")
        )
        return db

    async def _generate(self, gobd_service, mock_db) -> dict:
        return await gobd_service.generate_verfahrensdokumentation(
            mock_db,
            uuid.uuid4(),
            include_system_info=True,
            include_user_roles=False,
            include_change_history=False,
        )

    async def test_version_2026_07(self, gobd_service, mock_db) -> None:
        doc = await self._generate(gobd_service, mock_db)
        assert doc["meta"]["version"] == "2026.07"

    async def test_odoo_rollenverteilung_in_systembeschreibung(
        self, gobd_service, mock_db
    ) -> None:
        doc = await self._generate(gobd_service, mock_db)
        beschreibung = doc["system_beschreibung"]["beschreibung"]
        assert "Odoo 18" in beschreibung
        assert "Zweitablage" in beschreibung
        einsatz = json.dumps(
            doc["system_beschreibung"]["einsatzzweck"], ensure_ascii=False
        )
        assert "Odoo" in einsatz
        assert "DATEV-Export" not in einsatz

    async def test_prozesse_spiegel_und_push_statt_datev(
        self, gobd_service, mock_db
    ) -> None:
        doc = await self._generate(gobd_service, mock_db)
        prozesse = {p["prozess_id"]: p for p in doc["prozess_beschreibungen"]}
        assert "Odoo-Beleg-Spiegel" in prozesse["P005"]["name"]
        assert "Odoo" in prozesse["P007"]["name"]
        blob = json.dumps(doc["prozess_beschreibungen"], ensure_ascii=False)
        assert "DATEV-Export" not in blob
        assert "DATEV-Format" not in blob
        assert "ir.attachment.checksum" in blob
        assert "Review-Queue" in blob

    async def test_architektur_mit_odoo_ohne_verworfene_backends(
        self, gobd_service, mock_db
    ) -> None:
        doc = await self._generate(gobd_service, mock_db)
        blob = json.dumps(doc["system_architektur"], ensure_ascii=False)
        assert "Odoo-Anbindung" in blob
        assert "Surya" in blob
        assert "GOT-OCR" not in blob
        assert "DeepSeek" not in blob
        assert "restic" in blob
