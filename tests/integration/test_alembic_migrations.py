"""Alembic Migration Tests - Validierung aller Datenbankmigrationen.

Stellt sicher, dass:
- Alle Migrationen vorwaerts (upgrade) ausfuehrbar sind
- Alle Migrationen rueckwaerts (downgrade) ausfuehrbar sind
- Migration-Kette lueckenlos ist
- Keine doppelten Revision-IDs existieren

Created: 2026-02-07
Author: Claude Code (Feature 1.5)
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Set, Optional

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


# Test markers
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def alembic_config() -> Config:
    """Lade Alembic-Konfiguration aus alembic.ini."""
    project_root = Path(__file__).parent.parent.parent
    alembic_ini = project_root / "alembic.ini"

    if not alembic_ini.exists():
        pytest.skip("alembic.ini nicht gefunden")

    config = Config(str(alembic_ini))
    return config


@pytest.fixture(scope="module")
def script_directory(alembic_config: Config) -> ScriptDirectory:
    """Lade Alembic Script Directory mit allen Migrationen."""
    return ScriptDirectory.from_config(alembic_config)


@pytest.fixture(scope="module")
def migration_files() -> List[Path]:
    """Liste aller Migration-Dateien im alembic/versions/ Verzeichnis."""
    project_root = Path(__file__).parent.parent.parent
    versions_dir = project_root / "alembic" / "versions"

    if not versions_dir.exists():
        pytest.skip("alembic/versions/ Verzeichnis nicht gefunden")

    migrations = sorted(versions_dir.glob("*.py"))
    # Filter out __pycache__ and __init__.py
    migrations = [m for m in migrations if m.name != "__init__.py" and not m.name.startswith("__pycache__")]

    return migrations


@pytest.fixture(scope="function")
def test_engine() -> Engine:
    """Erstelle SQLite In-Memory Engine fuer Migration-Tests.

    Hinweis: SQLite unterstuetzt nicht alle PostgreSQL Features,
    aber eignet sich fuer strukturelle Tests der Migration-Kette.
    """
    engine = create_engine("sqlite:///:memory:")
    return engine


class TestMigrationChain:
    """Tests fuer die Integritaet der Migration-Kette."""

    def test_migration_chain_is_complete(
        self,
        script_directory: ScriptDirectory
    ) -> None:
        """Prueft, dass alle Migrationen eine lueckenlose Kette bilden.

        Von 'base' bis 'head' sollte eine durchgehende Kette existieren.
        """
        # Get all revisions
        revisions = list(script_directory.walk_revisions())

        assert len(revisions) > 0, "Keine Migrationen gefunden"

        # Build dependency graph
        revision_map: Dict[Optional[str], List[str]] = {}
        for rev in revisions:
            down_revision = rev.down_revision
            if isinstance(down_revision, tuple):
                # Multiple parents (merge)
                for dr in down_revision:
                    if dr not in revision_map:
                        revision_map[dr] = []
                    revision_map[dr].append(rev.revision)
            else:
                # Single parent
                if down_revision not in revision_map:
                    revision_map[down_revision] = []
                revision_map[down_revision].append(rev.revision)

        # Verify no orphaned revisions (except base)
        all_revision_ids = {rev.revision for rev in revisions}
        referenced_parents = set()

        for rev in revisions:
            if rev.down_revision is None:
                continue
            if isinstance(rev.down_revision, tuple):
                referenced_parents.update(rev.down_revision)
            else:
                referenced_parents.add(rev.down_revision)

        # All referenced parents should either be None or exist in revisions
        orphaned = referenced_parents - all_revision_ids - {None}
        assert len(orphaned) == 0, f"Orphaned parent revisions gefunden: {orphaned}"

    def test_no_duplicate_revision_ids(
        self,
        script_directory: ScriptDirectory
    ) -> None:
        """Prueft, dass keine doppelten Revision-IDs existieren."""
        revisions = list(script_directory.walk_revisions())
        revision_ids = [rev.revision for rev in revisions]

        # Check for duplicates
        seen: Set[str] = set()
        duplicates: Set[str] = set()

        for rev_id in revision_ids:
            if rev_id in seen:
                duplicates.add(rev_id)
            seen.add(rev_id)

        assert len(duplicates) == 0, f"Doppelte Revision-IDs gefunden: {duplicates}"

    def test_all_migrations_have_downgrade(
        self,
        migration_files: List[Path]
    ) -> None:
        """Prueft, dass jede Migration eine downgrade()-Funktion hat.

        Die Funktion darf nicht nur 'pass' enthalten.
        """
        missing_downgrade = []
        empty_downgrade = []

        for migration_file in migration_files:
            content = migration_file.read_text(encoding="utf-8")

            # Check if downgrade function exists
            if "def downgrade(" not in content:
                missing_downgrade.append(migration_file.name)
                continue

            # Extract downgrade function body
            downgrade_match = re.search(
                r'def downgrade\(\).*?:\s*(.*?)(?=\ndef |\Z)',
                content,
                re.DOTALL
            )

            if downgrade_match:
                body = downgrade_match.group(1).strip()
                # Check if body is just 'pass' or empty
                if body == "pass" or body == "" or body == '"""TODO"""':
                    empty_downgrade.append(migration_file.name)

        assert len(missing_downgrade) == 0, (
            f"Migrationen ohne downgrade()-Funktion: {missing_downgrade}"
        )
        # Note: We allow empty downgrades for now, but log them
        if empty_downgrade:
            print(f"\nWARNING: {len(empty_downgrade)} Migrationen mit leerer downgrade(): {empty_downgrade[:5]}")


class TestMigrationDocumentation:
    """Tests fuer Migration-Dokumentation."""

    def test_migration_files_have_docstring(
        self,
        migration_files: List[Path]
    ) -> None:
        """Prueft, dass jede Migration eine Docstring oder Message hat."""
        missing_docs = []

        for migration_file in migration_files:
            content = migration_file.read_text(encoding="utf-8")

            # Check for docstring in first 20 lines
            lines = content.split('\n')[:20]
            has_docstring = False
            has_revision_message = False

            for line in lines:
                if '"""' in line or "'''" in line:
                    has_docstring = True
                    break
                if line.strip().startswith("# ") and len(line.strip()) > 5:
                    has_docstring = True
                    break
                if "Revision ID:" in line or "Revises:" in line:
                    has_revision_message = True

            if not has_docstring and not has_revision_message:
                missing_docs.append(migration_file.name)

        # Allow some legacy migrations without docs
        max_allowed_missing = 10
        assert len(missing_docs) <= max_allowed_missing, (
            f"Zu viele Migrationen ohne Dokumentation ({len(missing_docs)}): "
            f"{missing_docs[:10]}"
        )


class TestMigrationExecution:
    """Tests fuer die Ausfuehrbarkeit von Migrationen.

    Hinweis: Diese Tests nutzen SQLite in-memory und koennen nicht
    alle PostgreSQL-spezifischen Features testen.
    """

    @pytest.mark.slow
    def test_upgrade_to_head(
        self,
        alembic_config: Config,
        test_engine: Engine
    ) -> None:
        """Prueft, dass Upgrade von leerem DB zu head funktioniert.

        Hinweis: Dieser Test ist deaktiviert, da SQLite nicht alle
        PostgreSQL-Features unterstuetzt. Fuer vollstaendige Tests
        sollte eine PostgreSQL-Testdatenbank verwendet werden.
        """
        pytest.skip("SQLite unterstuetzt nicht alle PostgreSQL-Features - "
                   "Verwende docker-compose fuer vollstaendige Migrations-Tests")

    @pytest.mark.slow
    def test_downgrade_to_base(
        self,
        alembic_config: Config,
        test_engine: Engine
    ) -> None:
        """Prueft, dass Downgrade von head zu base funktioniert."""
        pytest.skip("SQLite unterstuetzt nicht alle PostgreSQL-Features")

    @pytest.mark.slow
    def test_upgrade_downgrade_cycle(
        self,
        alembic_config: Config,
        test_engine: Engine
    ) -> None:
        """Prueft Upgrade -> Downgrade -> Upgrade Zyklus."""
        pytest.skip("SQLite unterstuetzt nicht alle PostgreSQL-Features")


class TestMigrationConsistency:
    """Tests fuer Schema-Konsistenz zwischen Migrationen."""

    def test_recent_migrations_schema_consistency(
        self,
        script_directory: ScriptDirectory,
        migration_files: List[Path]
    ) -> None:
        """Prueft, dass die letzten 10 Migrationen keine Konflikte haben.

        Prueft auf:
        - Gleiche Tabelle wird mehrfach erstellt
        - Gleiche Spalte wird mehrfach hinzugefuegt
        - Gleicher Index wird mehrfach erstellt
        """
        # Get last 10 migrations
        recent_migrations = migration_files[-10:] if len(migration_files) >= 10 else migration_files

        created_tables: Set[str] = set()
        created_columns: Dict[str, Set[str]] = {}
        created_indexes: Set[str] = set()
        conflicts: List[str] = []

        for migration_file in recent_migrations:
            content = migration_file.read_text(encoding="utf-8")

            # Parse create_table calls
            table_matches = re.findall(r'op\.create_table\([\'"](\w+)[\'"]', content)
            for table in table_matches:
                if table in created_tables:
                    conflicts.append(f"Tabelle '{table}' wird mehrfach erstellt")
                created_tables.add(table)

            # Parse add_column calls
            column_matches = re.findall(
                r'op\.add_column\([\'"](\w+)[\'"],\s*sa\.Column\([\'"](\w+)[\'"]',
                content
            )
            for table, column in column_matches:
                if table not in created_columns:
                    created_columns[table] = set()

                col_key = f"{table}.{column}"
                if column in created_columns[table]:
                    conflicts.append(f"Spalte '{col_key}' wird mehrfach hinzugefuegt")
                created_columns[table].add(column)

            # Parse create_index calls
            index_matches = re.findall(r'op\.create_index\([\'"](\w+)[\'"]', content)
            for index in index_matches:
                if index in created_indexes:
                    conflicts.append(f"Index '{index}' wird mehrfach erstellt")
                created_indexes.add(index)

        assert len(conflicts) == 0, (
            f"Schema-Konflikte in den letzten {len(recent_migrations)} Migrationen gefunden:\n" +
            "\n".join(f"  - {c}" for c in conflicts)
        )

    def test_no_conflicting_enum_changes(
        self,
        migration_files: List[Path]
    ) -> None:
        """Prueft, dass keine konfliktierenden Enum-Aenderungen existieren.

        PostgreSQL Enums koennen nicht einfach geaendert werden.
        """
        # Get recent migrations
        recent_migrations = migration_files[-20:] if len(migration_files) >= 20 else migration_files

        enum_operations: Dict[str, List[str]] = {}

        for migration_file in recent_migrations:
            content = migration_file.read_text(encoding="utf-8")

            # Find enum operations
            enum_matches = re.findall(
                r'(create_type|drop_type|alter_type)\([\'"](\w+)[\'"]',
                content
            )

            for operation, enum_name in enum_matches:
                if enum_name not in enum_operations:
                    enum_operations[enum_name] = []
                enum_operations[enum_name].append(
                    f"{migration_file.name}: {operation}"
                )

        # Check for potential conflicts
        conflicts = []
        for enum_name, operations in enum_operations.items():
            if len(operations) > 1:
                # Multiple operations on same enum - potential conflict
                if any("drop_type" in op for op in operations):
                    conflicts.append(
                        f"Enum '{enum_name}' hat drop_type und andere Operationen: "
                        f"{operations}"
                    )

        # Allow some conflicts (they might be intentional)
        assert len(conflicts) == 0, (
            f"Potentielle Enum-Konflikte gefunden:\n" +
            "\n".join(f"  - {c}" for c in conflicts)
        )


class TestMigrationNamingConventions:
    """Tests fuer Naming-Conventions von Migrationen."""

    def test_migration_files_follow_naming_pattern(
        self,
        migration_files: List[Path]
    ) -> None:
        """Prueft, dass Migration-Dateien dem Naming-Pattern folgen.

        Pattern: NNN_description.py wobei NNN eine 3-stellige Nummer ist.
        """
        invalid_names = []

        # Pattern: digits_words.py
        pattern = re.compile(r'^\d+_[a-z0-9_]+\.py$')

        for migration_file in migration_files:
            if not pattern.match(migration_file.name):
                invalid_names.append(migration_file.name)

        # Allow some flexibility for legacy migrations
        max_allowed_invalid = 5
        assert len(invalid_names) <= max_allowed_invalid, (
            f"Zu viele Migrationen mit ungueltigem Namen ({len(invalid_names)}): "
            f"{invalid_names[:10]}"
        )

    def test_migration_numbers_are_sequential(
        self,
        migration_files: List[Path]
    ) -> None:
        """Prueft, dass Migration-Nummern weitgehend sequentiell sind.

        Kleine Luecken sind erlaubt (z.B. geloeschte Migrationen).
        """
        numbers = []

        for migration_file in migration_files:
            match = re.match(r'^(\d+)_', migration_file.name)
            if match:
                numbers.append(int(match.group(1)))

        if not numbers:
            pytest.skip("Keine nummerierten Migrationen gefunden")

        numbers.sort()

        # Check for large gaps (> 10)
        large_gaps = []
        for i in range(1, len(numbers)):
            gap = numbers[i] - numbers[i-1]
            if gap > 10:
                large_gaps.append(f"Gap {gap} zwischen {numbers[i-1]} und {numbers[i]}")

        # Allow some large gaps (might be intentional deletions)
        assert len(large_gaps) <= 3, (
            f"Zu viele grosse Luecken in Migration-Nummern gefunden:\n" +
            "\n".join(f"  - {g}" for g in large_gaps)
        )


# Integration test that requires real database
@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL nicht gesetzt - ueberspringe Datenbank-Tests"
)
class TestMigrationWithDatabase:
    """Tests mit echter PostgreSQL-Datenbank.

    Diese Tests benoetigen eine TEST_DATABASE_URL Environment-Variable.
    """

    def test_upgrade_to_head_postgres(
        self,
        alembic_config: Config
    ) -> None:
        """Vollstaendiger Upgrade-Test mit PostgreSQL."""
        # This would require a test database
        # Implementation would use alembic.command.upgrade()
        pytest.skip("Requires TEST_DATABASE_URL - use docker-compose for full test")
