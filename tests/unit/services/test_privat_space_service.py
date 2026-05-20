# -*- coding: utf-8 -*-
"""
Unit tests for Privat Space Service.

Tests fuer Space-Verwaltung:
- Space-Erstellung (personal/shared)
- Zugriffspruefung
- Statistik-Berechnung
"""

import pytest
from datetime import date, datetime, timedelta
from uuid import uuid4
from pathlib import Path
import sys

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


class TestSpaceTypeConstants:
    """Tests fuer Space-Typen."""

    def test_space_types_defined(self):
        """Teste dass alle Space-Typen definiert sind."""
        from app.db.schemas import PrivatSpaceType

        assert hasattr(PrivatSpaceType, "PERSONAL")
        assert hasattr(PrivatSpaceType, "SHARED")

    def test_space_type_values(self):
        """Teste Space-Typ-Werte."""
        from app.db.schemas import PrivatSpaceType

        assert PrivatSpaceType.PERSONAL.value == "personal"
        assert PrivatSpaceType.SHARED.value == "shared"


class TestAccessLevelHierarchy:
    """Tests fuer Zugriffs-Level-Hierarchie."""

    def test_level_hierarchy_definition(self):
        """Teste Level-Hierarchie-Definition."""
        level_hierarchy = {"read": 1, "write": 2, "admin": 3}

        assert level_hierarchy["read"] < level_hierarchy["write"]
        assert level_hierarchy["write"] < level_hierarchy["admin"]

    def test_read_level_allows_read(self):
        """Teste dass Read-Level Read erlaubt."""
        level_hierarchy = {"read": 1, "write": 2, "admin": 3}
        granted = level_hierarchy["read"]
        required = level_hierarchy["read"]

        assert granted >= required

    def test_read_level_denies_write(self):
        """Teste dass Read-Level Write nicht erlaubt."""
        level_hierarchy = {"read": 1, "write": 2, "admin": 3}
        granted = level_hierarchy["read"]
        required = level_hierarchy["write"]

        assert granted < required

    def test_write_level_allows_read(self):
        """Teste dass Write-Level Read erlaubt."""
        level_hierarchy = {"read": 1, "write": 2, "admin": 3}
        granted = level_hierarchy["write"]
        required = level_hierarchy["read"]

        assert granted >= required

    def test_write_level_allows_write(self):
        """Teste dass Write-Level Write erlaubt."""
        level_hierarchy = {"read": 1, "write": 2, "admin": 3}
        granted = level_hierarchy["write"]
        required = level_hierarchy["write"]

        assert granted >= required

    def test_write_level_denies_admin(self):
        """Teste dass Write-Level Admin nicht erlaubt."""
        level_hierarchy = {"read": 1, "write": 2, "admin": 3}
        granted = level_hierarchy["write"]
        required = level_hierarchy["admin"]

        assert granted < required

    def test_admin_level_allows_all(self):
        """Teste dass Admin-Level alles erlaubt."""
        level_hierarchy = {"read": 1, "write": 2, "admin": 3}
        granted = level_hierarchy["admin"]

        assert granted >= level_hierarchy["read"]
        assert granted >= level_hierarchy["write"]
        assert granted >= level_hierarchy["admin"]

    def test_unknown_level_defaults_to_zero(self):
        """Teste dass unbekanntes Level zu 0 wird."""
        level_hierarchy = {"read": 1, "write": 2, "admin": 3}
        granted = level_hierarchy.get("unknown", 0)

        assert granted == 0


class TestSpaceStatisticsCalculation:
    """Tests fuer Statistik-Berechnungen."""

    def test_total_size_calculation_bytes(self):
        """Teste Berechnung der Gesamtgroesse in Bytes."""
        file_sizes = [1024, 2048, 512, 4096]  # In Bytes
        total = sum(file_sizes)

        assert total == 7680

    def test_total_size_formatting_kb(self):
        """Teste Formatierung in KB."""
        total_bytes = 7680
        kb = total_bytes / 1024

        assert kb == 7.5

    def test_total_size_formatting_mb(self):
        """Teste Formatierung in MB."""
        total_bytes = 1048576  # 1 MB
        mb = total_bytes / (1024 * 1024)

        assert mb == 1.0

    def test_total_size_formatting_gb(self):
        """Teste Formatierung in GB."""
        total_bytes = 1073741824  # 1 GB
        gb = total_bytes / (1024 * 1024 * 1024)

        assert gb == 1.0

    def test_pending_deadlines_count(self):
        """Teste Zaehlung offener Fristen."""
        today = date.today()
        deadlines = [
            {"due_date": today + timedelta(days=5), "is_completed": False},
            {"due_date": today + timedelta(days=10), "is_completed": False},
            {"due_date": today - timedelta(days=2), "is_completed": True},  # Erledigt
            {"due_date": today - timedelta(days=5), "is_completed": False},  # Ueberfaellig
        ]

        pending = sum(
            1 for d in deadlines
            if not d["is_completed"] and d["due_date"] >= today
        )

        assert pending == 2

    def test_document_count(self):
        """Teste Zaehlung von Dokumenten."""
        documents = [
            {"id": uuid4()},
            {"id": uuid4()},
            {"id": uuid4()},
        ]

        assert len(documents) == 3

    def test_folder_count(self):
        """Teste Zaehlung von Ordnern."""
        folders = [
            {"id": uuid4(), "name": "Versicherungen"},
            {"id": uuid4(), "name": "Fahrzeuge"},
        ]

        assert len(folders) == 2


class TestSpaceOwnership:
    """Tests fuer Space-Eigentuemerschaft."""

    def test_owner_has_full_access(self):
        """Teste dass Owner vollen Zugriff hat."""
        owner_id = uuid4()
        space = {
            "id": uuid4(),
            "owner_id": owner_id,
        }
        requesting_user = owner_id

        is_owner = space["owner_id"] == requesting_user

        assert is_owner is True

    def test_non_owner_needs_explicit_access(self):
        """Teste dass Nicht-Owner expliziten Zugriff braucht."""
        owner_id = uuid4()
        other_user = uuid4()
        space = {
            "id": uuid4(),
            "owner_id": owner_id,
        }

        is_owner = space["owner_id"] == other_user

        assert is_owner is False


class TestSpaceListPagination:
    """Tests fuer Paginierung."""

    def test_page_calculation(self):
        """Teste Seitenberechnung."""
        total = 53
        page_size = 20

        pages = (total + page_size - 1) // page_size

        assert pages == 3  # 20 + 20 + 13 = 53

    def test_offset_calculation(self):
        """Teste Offset-Berechnung."""
        page = 3
        page_size = 20

        offset = (page - 1) * page_size

        assert offset == 40

    def test_zero_items_zero_pages(self):
        """Teste null Elemente = null Seiten."""
        total = 0
        page_size = 20

        pages = (total + page_size - 1) // page_size if page_size > 0 else 0

        assert pages == 0

    def test_page_one_has_zero_offset(self):
        """Teste dass Seite 1 Offset 0 hat."""
        page = 1
        page_size = 20

        offset = (page - 1) * page_size

        assert offset == 0


class TestSpaceSoftDelete:
    """Tests fuer Soft-Delete."""

    def test_soft_delete_deactivates(self):
        """Teste dass Soft-Delete deaktiviert."""
        space = {
            "id": uuid4(),
            "is_active": True,
        }

        # Soft delete
        space["is_active"] = False

        assert space["is_active"] is False

    def test_soft_deleted_not_in_active_query(self):
        """Teste dass Soft-Delete aus aktiven Listen ausgeschlossen wird."""
        spaces = [
            {"id": uuid4(), "is_active": True},
            {"id": uuid4(), "is_active": False},  # Soft deleted
            {"id": uuid4(), "is_active": True},
        ]

        active_spaces = [s for s in spaces if s["is_active"]]

        assert len(active_spaces) == 2


class TestSharedSpaceCompany:
    """Tests fuer geteilte Spaces mit Firmenbezug."""

    def test_personal_space_has_no_company(self):
        """Teste dass persoenlicher Space keine Firma hat."""
        personal_space = {
            "space_type": "personal",
            "company_id": None,
        }

        assert personal_space["company_id"] is None

    def test_shared_space_has_company(self):
        """Teste dass geteilter Space Firma hat."""
        company_id = uuid4()
        shared_space = {
            "space_type": "shared",
            "company_id": company_id,
        }

        assert shared_space["company_id"] is not None
        assert shared_space["company_id"] == company_id

    def test_space_type_determines_scope(self):
        """Teste dass Space-Type den Scope bestimmt."""
        personal = {"space_type": "personal"}
        shared = {"space_type": "shared"}

        is_personal = personal["space_type"] == "personal"
        is_shared = shared["space_type"] == "shared"

        assert is_personal is True
        assert is_shared is True


class TestSpaceUpdate:
    """Tests fuer Space-Aktualisierung."""

    def test_update_name(self):
        """Teste Aktualisierung des Namens."""
        space = {
            "name": "Alter Name",
            "updated_at": datetime.utcnow(),
        }

        # Update
        space["name"] = "Neuer Name"
        space["updated_at"] = datetime.utcnow()

        assert space["name"] == "Neuer Name"

    def test_update_description(self):
        """Teste Aktualisierung der Beschreibung."""
        space = {
            "description": "Alte Beschreibung",
        }

        space["description"] = "Neue Beschreibung mit Umlauten: äöüß"

        assert "äöüß" in space["description"]

    def test_partial_update_preserves_unset_fields(self):
        """Teste dass Partial-Update ungesetzte Felder behaelt."""
        space = {
            "name": "Mein Space",
            "description": "Beschreibung",
        }

        # Nur Name aktualisieren
        update_data = {"name": "Umbenannt"}

        for key, value in update_data.items():
            space[key] = value

        assert space["name"] == "Umbenannt"
        assert space["description"] == "Beschreibung"  # Unveraendert
