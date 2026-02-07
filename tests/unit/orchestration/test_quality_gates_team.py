"""Tests fuer quality_gates.py - Team Quality Gates.

Testet:
- Gate-Registry und Dispatch
- Unbekannte Gates -> KeyError
- Gate3 Any-Type und PII-Erkennung
- Gate6 Integration
- GateProtocol
"""

import pytest
import sys
from pathlib import Path

_claude_path = str(Path(__file__).parent.parent.parent.parent / ".claude")
if _claude_path not in sys.path:
    sys.path.insert(0, _claude_path)

from orchestration.quality_gates import (
    GATES,
    GateProtocol,
    GateResult,
    GateStatus,
    Gate1ResearchComplete,
    Gate2DesignApproved,
    Gate3CodeQuality,
    Gate4TestsPassing,
    Gate5ReviewApproved,
    Gate6IntegrationClean,
    run_gate,
)


def test_run_gate_dispatches_correctly() -> None:
    """run_gate dispatcht zum korrekten Gate."""
    result = run_gate(
        "gate_1_research",
        research_output="app/services/foo.py:42 existing pattern found, M1 kopplung",
        affected_files=["app/services/foo.py"],
    )
    assert isinstance(result, GateResult)
    assert result.gate_number == 1


def test_run_gate_unknown_raises_keyerror() -> None:
    """Unbekannter Gate-Name loest KeyError aus."""
    with pytest.raises(KeyError, match="gate_99_unknown"):
        run_gate("gate_99_unknown")


def test_all_gates_registered() -> None:
    """Alle 6 Gates muessen im Registry sein."""
    expected = {
        "gate_1_research",
        "gate_2_design",
        "gate_3_code_quality",
        "gate_4_tests",
        "gate_5_review",
        "gate_6_integration",
    }
    assert set(GATES.keys()) == expected


def test_gate3_detects_any_types() -> None:
    """Gate 3 erkennt Any-Types im Code."""
    gate = Gate3CodeQuality()
    code = (
        "from typing import Dict\n\n"
        "def process(data: Any) -> Any:\n"
        "    return data\n"
    )
    result = gate.check(code_output=code, files_changed=["app/services/foo.py"])
    any_check = next(c for c in result.checks if c.name == "no_any_types")
    assert not any_check.passed


def test_gate3_detects_pii_logging() -> None:
    """Gate 3 erkennt PII-Logging."""
    gate = Gate3CodeQuality()
    code = (
        "def save(customer_nr: str) -> None:\n"
        "    logger.info(f'Processing IBAN {iban}')\n"
    )
    result = gate.check(code_output=code, files_changed=["app/services/foo.py"])
    pii_check = next(c for c in result.checks if c.name == "no_pii_logging")
    assert not pii_check.passed


def test_gate6_passes_with_complete_integration() -> None:
    """Gate 6 besteht bei vollstaendiger Integration."""
    gate = Gate6IntegrationClean()
    output = (
        "Updated app/main.py: include_router(banking_router)\n"
        "Updated app/db/models.py: import models_banking\n"
        "Updated app/workers/celery_app.py: added task module\n"
        "Updated app/workers/tasks/__init__.py: re-exports added to __all__\n"
    )
    manifests = [
        {"type": "router", "description": "Router registration"},
        {"type": "model", "description": "Model import"},
        {"type": "task", "description": "Task registration"},
    ]
    result = gate.check(integration_output=output, manifests=manifests)
    assert result.status == GateStatus.PASSED


def test_gate_protocol_compliance() -> None:
    """Alle Gates erfuellen GateProtocol."""
    for name, gate in GATES.items():
        assert isinstance(gate, GateProtocol), (
            f"Gate '{name}' erfuellt GateProtocol nicht"
        )
