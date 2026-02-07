"""Tests fuer shared_file_protocol.py - Bottleneck-Dateiverwaltung.

Testet:
- Bottleneck-Erkennung
- Typed BottleneckFile
- Zone-Validierung
- Manifest-Merge (Deduplizierung)
- Phase-6-Instructions-Generierung
"""

import pytest
import sys
from pathlib import Path

_claude_path = str(Path(__file__).parent.parent.parent.parent / ".claude")
if _claude_path not in sys.path:
    sys.path.insert(0, _claude_path)

from orchestration.shared_file_protocol import (
    BOTTLENECK_FILES,
    BottleneckFile,
    RegistrationManifest,
    RouterImport,
    ModelImport,
    TaskModule,
    TaskExport,
    SharedFileProtocol,
    is_bottleneck_file,
    validate_agent_files,
    merge_agent_manifests,
    generate_phase6_instructions,
)


@pytest.mark.parametrize(
    "path",
    [
        "app/main.py",
        "app/db/models.py",
        "app/workers/celery_app.py",
        "app/workers/tasks/__init__.py",
    ],
)
def test_identifies_bottleneck_files(path: str) -> None:
    assert is_bottleneck_file(path) is True


def test_non_bottleneck_not_flagged() -> None:
    assert is_bottleneck_file("app/services/banking/account_service.py") is False
    assert is_bottleneck_file("app/main.py.bak") is False


def test_bottleneck_files_are_typed() -> None:
    """Alle Eintraege in BOTTLENECK_FILES sind BottleneckFile-Instanzen."""
    for path, bf in BOTTLENECK_FILES.items():
        assert isinstance(bf, BottleneckFile), f"{path} ist kein BottleneckFile"
        assert bf.path == path


def test_bottleneck_file_violation() -> None:
    """Agent darf keine Bottleneck-Dateien zugewiesen bekommen."""
    result = validate_agent_files(
        agent_role="coder_a",
        files=["app/main.py", "app/services/foo/bar.py"],
        module_name="foo",
    )
    assert not result.is_valid
    assert any("VIOLATION" in v for v in result.violations)


def test_parallel_safe_zone_passes() -> None:
    """Files in Parallel-Safe-Zones sind valide."""
    result = validate_agent_files(
        agent_role="coder_a",
        files=[
            "app/services/banking/account_service.py",
            "app/api/v1/banking.py",
        ],
        module_name="banking",
    )
    assert result.is_valid


def test_merge_deduplicates() -> None:
    """Manifest-Merge entfernt Duplikate."""
    m1 = RegistrationManifest(
        router_imports=[RouterImport("app.api.v1.foo", "router", "/api/v1/foo")],
        model_imports=[ModelImport("app.db.models_foo", "# Foo Models")],
    )
    m2 = RegistrationManifest(
        router_imports=[RouterImport("app.api.v1.foo", "router", "/api/v1/foo")],
        model_imports=[ModelImport("app.db.models_bar", "# Bar Models")],
    )
    merged = merge_agent_manifests([m1, m2])
    assert len(merged.router_imports) == 1  # deduplicated
    assert len(merged.model_imports) == 2  # different


def test_generate_instructions_contains_all_sections() -> None:
    """Instructions enthalten alle 4 Sektionen."""
    manifest = RegistrationManifest(
        router_imports=[RouterImport("app.api.v1.foo", "router", "/api/v1/foo")],
        model_imports=[ModelImport("app.db.models_foo", "# Foo")],
        task_modules=[TaskModule("app.workers.tasks.foo_tasks")],
        task_exports=[TaskExport("foo_tasks", ["do_foo"])],
    )
    instructions = generate_phase6_instructions(manifest)
    assert "ROUTER REGISTRATIONS" in instructions
    assert "MODEL IMPORTS" in instructions
    assert "TASK MODULE REGISTRATIONS" in instructions
    assert "TASK EXPORTS" in instructions
    assert "INTEGRATION CHECKLIST" in instructions
