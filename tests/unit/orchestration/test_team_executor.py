"""Tests fuer team_executor.py - CLI fuer Team-Workflow.

Testet:
- Input-Validierung (Agent-Names, Gate-Names)
- Atomare State-Writes
- Parser-Vollstaendigkeit
- Workflow-ID-Validierung und Isolation
"""

import importlib.util
import json
import os
import pytest
import sys
from pathlib import Path
from unittest.mock import patch


# Load team_executor as module (not in a package)
_executor_path = str(
    Path(__file__).parent.parent.parent.parent / ".claude" / "helpers" / "team_executor.py"
)
_spec = importlib.util.spec_from_file_location("team_executor", _executor_path)
assert _spec is not None and _spec.loader is not None
team_executor = importlib.util.module_from_spec(_spec)

# We need .claude on path for orchestration imports within team_executor
_claude_path = str(Path(__file__).parent.parent.parent.parent / ".claude")
if _claude_path not in sys.path:
    sys.path.insert(0, _claude_path)

_spec.loader.exec_module(team_executor)


class TestAgentNameValidation:

    @pytest.mark.parametrize(
        "name",
        ["coder_a", "researcher", "auditor_b", "tester123"],
    )
    def test_valid_agent_names_accepted(self, name: str) -> None:
        assert team_executor._validate_agent_name(name) == name

    @pytest.mark.parametrize(
        "name",
        [
            "../../etc/passwd",
            "../secret",
            "coder/../../root",
            "",
            "a" * 65,
            "123start",
            "coder a",
        ],
    )
    def test_invalid_agent_names_rejected(self, name: str) -> None:
        with pytest.raises(ValueError, match="Ungueltiger Agent-Name"):
            team_executor._validate_agent_name(name)


class TestGateNameValidation:

    @pytest.mark.parametrize(
        "name",
        [
            "gate_1_research",
            "gate_2_design",
            "gate_3_code_quality",
            "gate_4_tests",
            "gate_5_review",
            "gate_6_integration",
        ],
    )
    def test_valid_gate_names_accepted(self, name: str) -> None:
        assert team_executor._validate_gate_name(name) == name

    @pytest.mark.parametrize(
        "name",
        [
            "gate_7_extra",
            "not_a_gate",
            "gate_1_",
            "../gate_1_research",
            "",
        ],
    )
    def test_invalid_gate_names_rejected(self, name: str) -> None:
        with pytest.raises(ValueError, match="Ungueltiger Gate-Name"):
            team_executor._validate_gate_name(name)


class TestAtomicStateWrites:

    def test_save_state_creates_file(self, tmp_path: Path) -> None:
        state_file = str(tmp_path / "team_state.json")
        with patch.object(team_executor, "_STATE_FILE", state_file), \
             patch.object(team_executor, "_CACHE_DIR", str(tmp_path)):
            team_executor._save_state({"status": "test"})
        assert os.path.isfile(state_file)
        with open(state_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["status"] == "test"

    def test_save_state_no_tmp_residue(self, tmp_path: Path) -> None:
        state_file = str(tmp_path / "team_state.json")
        with patch.object(team_executor, "_STATE_FILE", state_file), \
             patch.object(team_executor, "_CACHE_DIR", str(tmp_path)):
            team_executor._save_state({"key": "value"})
        tmp_file = state_file + ".tmp"
        assert not os.path.exists(tmp_file)


class TestWorkflowIdValidation:

    @pytest.mark.parametrize(
        "wid",
        ["abcd1234", "00ff00ff", "deadbeef"],
    )
    def test_valid_workflow_ids_accepted(self, wid: str) -> None:
        assert team_executor._validate_workflow_id(wid) == wid

    @pytest.mark.parametrize(
        "wid",
        [
            "../hack",
            "",
            "ABCD1234",
            "abcd123",       # too short (7 chars)
            "abcd12345",     # too long (9 chars)
            "abcd-123",      # hyphen not allowed
            "abcd 123",      # space not allowed
        ],
    )
    def test_invalid_workflow_ids_rejected(self, wid: str) -> None:
        with pytest.raises(ValueError, match="Ungueltige Workflow-ID"):
            team_executor._validate_workflow_id(wid)


class TestWorkflowIsolation:

    def test_state_file_for_with_id(self, tmp_path: Path) -> None:
        with patch.object(team_executor, "_CACHE_DIR", str(tmp_path)):
            result = team_executor._state_file_for("abcd1234")
        assert result.endswith("team_state_abcd1234.json")

    def test_state_file_for_without_id(self) -> None:
        result = team_executor._state_file_for(None)
        assert result == team_executor._STATE_FILE

    def test_phase_result_files_isolated(self, tmp_path: Path) -> None:
        with patch.object(team_executor, "_CACHE_DIR", str(tmp_path)):
            path_a = team_executor._write_phase_result(1, "A", workflow_id="aaaa1111")
            path_b = team_executor._write_phase_result(1, "B", workflow_id="bbbb2222")
        assert path_a != path_b
        assert "aaaa1111" in path_a
        assert "bbbb2222" in path_b
        with patch.object(team_executor, "_CACHE_DIR", str(tmp_path)):
            assert team_executor._read_phase_result(1, workflow_id="aaaa1111") == "A"
            assert team_executor._read_phase_result(1, workflow_id="bbbb2222") == "B"

    def test_read_phase_result_validates_workflow_id(self, tmp_path: Path) -> None:
        with patch.object(team_executor, "_CACHE_DIR", str(tmp_path)):
            with pytest.raises(ValueError, match="Ungueltige Workflow-ID"):
                team_executor._read_phase_result(1, workflow_id="../hack")

    def test_write_phase_result_validates_workflow_id(self, tmp_path: Path) -> None:
        with patch.object(team_executor, "_CACHE_DIR", str(tmp_path)):
            with pytest.raises(ValueError, match="Ungueltige Workflow-ID"):
                team_executor._write_phase_result(1, "data", workflow_id="../hack")

    def test_load_state_follows_pointer(self, tmp_path: Path) -> None:
        """Sequential callers without --workflow-id get redirected to latest workflow."""
        wid = "abcd1234"
        full_state = {
            "workflow_id": wid,
            "status": "classified",
            "template_serialized": {"phases": []},
        }
        pointer_state = {"latest_workflow_id": wid}
        state_file = str(tmp_path / "team_state.json")
        with patch.object(team_executor, "_CACHE_DIR", str(tmp_path)), \
             patch.object(team_executor, "_STATE_FILE", state_file):
            team_executor._save_state(full_state, workflow_id=wid)
            team_executor._save_state(pointer_state, workflow_id=None)
            # Load without workflow_id -> should follow pointer
            loaded = team_executor._load_state(workflow_id=None)
        assert loaded["workflow_id"] == wid
        assert loaded["status"] == "classified"

    def test_load_state_pointer_not_followed_when_full_state(self, tmp_path: Path) -> None:
        """If default state has template_serialized, it is NOT a pointer - use as-is."""
        full_state = {
            "workflow_id": "aaaa1111",
            "status": "classified",
            "latest_workflow_id": "bbbb2222",
            "template_serialized": {"phases": []},
        }
        state_file = str(tmp_path / "team_state.json")
        with patch.object(team_executor, "_CACHE_DIR", str(tmp_path)), \
             patch.object(team_executor, "_STATE_FILE", state_file):
            team_executor._save_state(full_state, workflow_id=None)
            loaded = team_executor._load_state(workflow_id=None)
        assert loaded["workflow_id"] == "aaaa1111"

    def test_empty_string_workflow_id_rejected_by_state_file_for(self, tmp_path: Path) -> None:
        """Empty string workflow_id must not silently fall through to global state."""
        with patch.object(team_executor, "_CACHE_DIR", str(tmp_path)):
            with pytest.raises(ValueError, match="Ungueltige Workflow-ID"):
                team_executor._state_file_for("")

    def test_empty_string_workflow_id_rejected_by_read(self, tmp_path: Path) -> None:
        """Empty string workflow_id must not silently fall through in _read_phase_result."""
        with patch.object(team_executor, "_CACHE_DIR", str(tmp_path)):
            with pytest.raises(ValueError, match="Ungueltige Workflow-ID"):
                team_executor._read_phase_result(1, workflow_id="")

    def test_empty_string_workflow_id_rejected_by_write(self, tmp_path: Path) -> None:
        """Empty string workflow_id must not silently fall through in _write_phase_result."""
        with patch.object(team_executor, "_CACHE_DIR", str(tmp_path)):
            with pytest.raises(ValueError, match="Ungueltige Workflow-ID"):
                team_executor._write_phase_result(1, "data", workflow_id="")

    def test_load_state_pointer_to_missing_file_returns_empty(self, tmp_path: Path) -> None:
        """Pointer to nonexistent workflow file returns empty dict (graceful degradation)."""
        pointer_state = {"latest_workflow_id": "abcd1234"}
        state_file = str(tmp_path / "team_state.json")
        with patch.object(team_executor, "_CACHE_DIR", str(tmp_path)), \
             patch.object(team_executor, "_STATE_FILE", state_file):
            team_executor._save_state(pointer_state, workflow_id=None)
            # Workflow-specific file does NOT exist
            loaded = team_executor._load_state(workflow_id=None)
        assert loaded == {}

    def test_load_state_malicious_pointer_not_followed(self, tmp_path: Path) -> None:
        """Malicious pointer value is rejected by regex, returns raw pointer dict."""
        pointer_state = {"latest_workflow_id": "../../../etc/passwd"}
        state_file = str(tmp_path / "team_state.json")
        with patch.object(team_executor, "_CACHE_DIR", str(tmp_path)), \
             patch.object(team_executor, "_STATE_FILE", state_file):
            team_executor._save_state(pointer_state, workflow_id=None)
            loaded = team_executor._load_state(workflow_id=None)
        # Should NOT follow malicious pointer - returns raw pointer dict
        assert loaded == {"latest_workflow_id": "../../../etc/passwd"}


class TestParser:

    def test_build_parser_has_all_commands(self) -> None:
        parser = team_executor.build_parser()
        # Parse each command to verify it exists (will raise if missing)
        expected = ["classify", "phase", "save-result", "gate", "integrate", "complete"]
        for cmd in expected:
            # Build minimal valid args per command
            if cmd == "classify":
                args = parser.parse_args(["classify", "--task", "test"])
            elif cmd == "phase":
                args = parser.parse_args(["phase", "--number", "1", "--task", "t"])
            elif cmd == "save-result":
                args = parser.parse_args(["save-result", "--phase", "1", "--result", "r"])
            elif cmd == "gate":
                args = parser.parse_args(["gate", "--name", "gate_1_research", "--phase", "1"])
            elif cmd == "integrate":
                args = parser.parse_args(["integrate"])
            elif cmd == "complete":
                args = parser.parse_args(["complete"])
            assert args.command == cmd

    def test_workflow_id_in_all_subcommands(self) -> None:
        parser = team_executor.build_parser()
        commands_with_wid = {
            "phase": ["phase", "--number", "1", "--workflow-id", "abcd1234"],
            "save-result": ["save-result", "--phase", "1", "--result", "r", "--workflow-id", "abcd1234"],
            "gate": ["gate", "--name", "gate_1_research", "--phase", "1", "--workflow-id", "abcd1234"],
            "integrate": ["integrate", "--workflow-id", "abcd1234"],
            "complete": ["complete", "--workflow-id", "abcd1234"],
        }
        for cmd, argv in commands_with_wid.items():
            args = parser.parse_args(argv)
            assert args.workflow_id == "abcd1234", f"--workflow-id not parsed for '{cmd}'"
