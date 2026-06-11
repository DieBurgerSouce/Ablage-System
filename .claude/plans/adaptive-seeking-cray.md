> **Status (W1-048, 2026-06-11)**: 10 von 11 Fixes UMGESETZT (Commits `590bdca2` + `970e72d1`, Feb 2026; adversarial verifiziert, W1-056 im Welle-1-Register).
> Offen ist ausschließlich Fix 3 — bei Wiederaufnahme nur diesen prüfen.

# Remediation Plan: Team Workflow System - Critical Review

## Review Findings Summary

3 parallel review agents re-analyzed 2624+ lines across 9 files. Cross-referenced with project CRITICAL RULES. Found **3 CRITICAL**, **4 HIGH**, **5 MEDIUM** open issues. All bug fixes from the original plan (C1-C4, H1-H6, M4-M7, L4) are confirmed implemented. The issues below are **new findings** from the deep review pass.

---

## Wave 1: CRITICAL (Must Fix - Security + Rule Violations)

### Fix 1: Shell Injection in settings.json (CRITICAL - CWE-78)
**File**: `.claude/settings.json:84`
**Problem**: `$PROMPT` is embedded directly in `echo` command without escaping. A prompt containing `"; rm -rf /; echo "` executes arbitrary shell commands. The entire `echo "{...\"$PROMPT\"...}" | python` pattern is the injection vector.
**Fix**: Claude Code UserPromptSubmit hooks pass the user's prompt via **environment variable** `$PROMPT`. The hook script `team_router_hook.py` reads from stdin. We need a safe pipe mechanism that doesn't evaluate shell metacharacters.
```json
"command": "printf '{\"prompt\": \"%s\"}' \"$PROMPT\" | python .claude/hooks/team_router_hook.py 2>/dev/null || true"
```
**NOTE**: `printf '%s'` with double-quoted `$PROMPT` is safe from command injection because `printf` does not interpret shell metacharacters in its arguments when properly quoted. However, the truly safest approach is to have the Python script read `$PROMPT` from the environment directly:
```json
"command": "python .claude/hooks/team_router_hook.py 2>/dev/null || true"
```
And modify `team_router_hook.py` to read `os.environ.get("PROMPT", "")` instead of `sys.stdin.read()`.

### Fix 2: Path Traversal in team_executor.py (CRITICAL - CWE-22)
**File**: `.claude/helpers/team_executor.py:65-68, 76-88`
**Problem**: `--agent` parameter is used directly in filename construction without validation. `--agent "../../etc/passwd"` writes to arbitrary filesystem locations via `os.path.join(_CACHE_DIR, f"team_phase_{N}_{agent}_result.txt")`.
**Fix**: Add validation at the top of the module and apply in both `_read_phase_result()` and `_write_phase_result()`:
```python
_SAFE_AGENT_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{0,63}$")
_SAFE_GATE_PATTERN = re.compile(r"^gate_[1-6]_[a-z_]{1,32}$")

def _validate_agent_name(name: str) -> str:
    """Validate agent name against safe pattern. Raises ValueError on invalid."""
    if not _SAFE_AGENT_PATTERN.match(name):
        raise ValueError(f"Ungueltiger Agent-Name: {name}")
    return name

def _validate_gate_name(name: str) -> str:
    """Validate gate name against safe pattern. Raises ValueError on invalid."""
    if not _SAFE_GATE_PATTERN.match(name):
        raise ValueError(f"Ungueltiger Gate-Name: {name}")
    return name
```
Apply `_validate_agent_name()` in `_read_phase_result()` and `_write_phase_result()` before filename construction. Apply `_validate_gate_name()` in `cmd_gate()` before calling `run_gate()`.

### Fix 3: Type Safety Violations (CRITICAL - Rule #4)
**Files + exact lines**:

| File | Line | Current | Fix |
|------|------|---------|-----|
| `team_workflow.py` | 199 | `Dict[str, Dict[str, object]]` | `Dict[str, CoupledChain]` (new dataclass) |
| `team_workflow.py` | 171 | `Dict[str, Dict[str, str]]` (but contains `bool`) | `Dict[str, ModuleSpec]` (new TypedDict) |
| `team_executor.py` | 48 | `Dict[str, object]` return type | `Dict[str, Union[str, int, float, bool, Dict[str, str], None]]` or TypedDict |
| `team_executor.py` | 56 | `Dict[str, object]` param | Same |
| `team_executor.py` | 53 | `# type: ignore[no-any-return]` | Remove after fixing return type |
| `team_executor.py` | 284 | `List[Dict[str, object]]` | TypedDict `AgentOutput` |
| `team_executor.py` | 935 | `Dict[str, object]` for command_map | `Dict[str, Callable[[argparse.Namespace], None]]` |
| `team_executor.py` | 956 | `# type: ignore[operator]` | Remove after fixing command_map type |
| `quality_gates.py` | 629 | `**kwargs: object` | Keep but add GateProtocol for dispatch |
| `quality_gates.py` | 641 | `# type: ignore[union-attr]` | Use Protocol-based typing |

**New types to add in `team_workflow.py`**:
```python
@dataclass
class CoupledChain:
    """Gekoppelte Modulkette mit gemeinsamen Modellen."""
    modules: List[str]
    shared_models: List[str]

class ModuleSpec(TypedDict):
    """Spezifikation eines unabhaengigen Moduls."""
    service: str
    api: str
    own_models: bool
```

**New types to add in `team_executor.py`**:
```python
from typing import Callable

class AgentOutput(TypedDict):
    role: str
    subagent_type: str
    model: str
    prompt: str
    description: str
    run_in_background: bool
```

**Command map fix**:
```python
CommandHandler = Callable[[argparse.Namespace], None]
command_map: Dict[str, CommandHandler] = { ... }
handler = command_map.get(args.command)
handler(args)  # No type: ignore needed
```

---

## Wave 2: HIGH Priority Fixes

### Fix 4: _calculate_confidence ignores its own parameters (HIGH - Logic Bug)
**File**: `.claude/orchestration/team_workflow.py:1154-1166`
**Problem**: Method accepts `complexity: Complexity` and `coupling: Coupling` but never uses them. Confidence is always 0.7/0.8/0.9 regardless of classification difficulty. This makes confidence meaningless.
**Fix**: Factor in complexity and coupling:
```python
def _calculate_confidence(
    self,
    complexity: Complexity,
    coupling: Coupling,
    input_data: ClassificationInput,
) -> float:
    """Berechnet Confidence der Klassifikation."""
    base = 0.5
    # Mehr Dateien = bessere Klassifikationsbasis
    if len(input_data.affected_files) > 0:
        base += 0.15
    # Laengere Beschreibung = mehr Kontext
    if len(input_data.task_description) > 100:
        base += 0.1
    # Triviale Tasks sind leicht zu klassifizieren
    if complexity == Complexity.C1_TRIVIAL:
        base += 0.15
    elif complexity == Complexity.C2_CONTAINED:
        base += 0.1
    else:
        base += 0.05  # Komplexe Tasks haben mehr Ambiguitaet
    # Bekannte Kopplungsmuster erhoehen Confidence
    if coupling == Coupling.M1_ISOLATED:
        base += 0.1
    elif coupling == Coupling.M3_SHARED_INFRA:
        base += 0.05
    return min(base, 1.0)
```

### Fix 5: Overly aggressive trivial prompt detection (HIGH)
**File**: `.claude/hooks/team_router_hook.py:78-91`
**Problem**: Patterns block legitimate work requests:
- `r"^commit"` blocks `"commit all changes and deploy the banking feature"`
- `r"^(what|how|where...)\s"` blocks `"How should we refactor the OCR pipeline?"` - this is a non-trivial task that should get team classification
- `r"^(explain|describe|show...)\s"` blocks `"Explain and fix the OCR confidence bug"` - contains actionable work
**Fix**: Restrict to exact-match trivials only:
```python
trivial_patterns: List[str] = [
    r"^(hi|hello|hey|hallo)\s*$",      # Exact greetings only
    r"^/",                               # Slash commands
    r"^(yes|no|ja|nein|ok|okay)\s*$",   # Exact confirmations only
    r"^(help|hilfe)\s*$",               # Exact help only
    r"^(git|npm|docker|pytest)\s",      # Direct CLI commands
]
```

### Fix 6: Silent exception swallowing (HIGH)
**File**: `.claude/hooks/team_router_hook.py:235-238`
**Problem**: `except Exception: pass` hides all errors including ImportError, JSON parse failures, and classification bugs. Makes production debugging impossible.
**Fix**: Log to stderr (doesn't affect hook stdout output):
```python
except Exception as exc:
    print(f"team_router_hook: {exc}", file=sys.stderr)
```

### Fix 7: Atomic state writes on Windows (HIGH)
**File**: `.claude/helpers/team_executor.py:56-60`
**Problem**: `_save_state()` is not atomic. If Claude is interrupted mid-write (or two parallel agents write simultaneously), `team_state.json` gets corrupted.
**Fix**: Write to temp file, then `os.replace()` (atomic on same filesystem, works on Windows):
```python
def _save_state(state: Dict[str, object]) -> None:
    _ensure_cache_dir()
    tmp_path = _STATE_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, _STATE_FILE)
```

---

## Wave 3: Unit Tests (CRITICAL - Rule #5)

**Zero tests exist** for the 4 team workflow modules. The `tests/unit/orchestration/` directory has tests for the old orchestrator but nothing for `team_workflow.py`, `quality_gates.py`, `shared_file_protocol.py`, or `team_spawner.py`. This violates CRITICAL RULE #5.

### Fix 8: Create tests/unit/orchestration/test_team_workflow.py
```
test_classify_trivial_task          - C1xM1 -> NO_TEAM_HAIKU
test_classify_complex_task          - C3xM3 -> FEATURE_FULL
test_security_override              - security keyword -> SECURITY_AUDIT
test_review_override                - review keyword -> REVIEW
test_feature_full_deepcopy          - FEATURE_FULL independent of FEATURE_STANDARD
test_no_team_builds_fresh           - NO_TEAM doesn't mutate shared template
test_coupling_exact_path_match      - "myapp/main.py" NOT bottleneck, "app/main.py" IS
test_coupling_windows_paths         - backslash paths normalized
test_confidence_uses_parameters     - different complexity/coupling -> different scores
test_coupled_chains_typed           - COUPLED_CHAINS values are CoupledChain
test_independent_modules_typed      - INDEPENDENT_MODULES values are ModuleSpec
```

### Fix 9: Create tests/unit/orchestration/test_quality_gates_team.py
(Named `_team` to avoid collision with existing `test_quality_gate.py` for singular module)
```
test_gate1_research_passes          - valid research output passes gate 1
test_gate1_research_fails_empty     - empty output fails
test_gate3_checks_params_and_returns - both param and return type hints checked
test_run_gate_unknown_raises        - unknown gate name raises KeyError
test_gate_result_format_report      - report is human-readable
test_all_gates_registered           - GATES dict has all 6 gates
```

### Fix 10: Create tests/unit/orchestration/test_shared_file_protocol.py
```
test_is_bottleneck_exact            - "app/main.py" is bottleneck
test_is_bottleneck_windows          - "app\\main.py" is bottleneck
test_not_bottleneck_similar         - "myapp/main.py" is NOT
test_is_parallel_safe               - "app/services/banking/foo.py" is safe
test_validate_zone_bottleneck       - bottleneck assignment -> violation
test_merge_manifests_deduplicates   - duplicate routers merged
test_generate_instructions          - instructions contain all sections
```

### Fix 11: Create tests/unit/orchestration/test_team_executor.py
```
test_validate_agent_name_valid      - "coder_a" passes
test_validate_agent_name_traversal  - "../../etc" raises ValueError
test_validate_gate_name_valid       - "gate_1_research" passes
test_validate_gate_name_invalid     - "../../gate" raises ValueError
test_extract_file_paths             - regex extracts app/ and tests/ paths
test_save_and_read_result           - round-trip through cache
test_classify_outputs_json          - valid JSON with expected keys
```

---

## Wave 4: MEDIUM Improvements

### Fix 12: INDEPENDENT_MODULES type mismatch (MEDIUM - Rule #4)
**File**: `.claude/orchestration/team_workflow.py:171`
**Problem**: Declared as `Dict[str, Dict[str, str]]` but contains `bool` values (`"own_models": False`).
**Fix**: Use `ModuleSpec` TypedDict (created in Fix 3).

### Fix 13: GateProtocol to eliminate type: ignore (MEDIUM)
**File**: `.claude/orchestration/quality_gates.py:641`
**Problem**: `gate.check(**kwargs)  # type: ignore[union-attr]` because Union dispatch can't guarantee method exists.
**Fix**: Add Protocol class:
```python
class GateProtocol(Protocol):
    def check(self, **kwargs: object) -> GateResult: ...

GATES: Dict[str, GateProtocol] = { ... }
```

### Fix 14: quality_gate.py deprecation warning (MEDIUM)
**File**: `.claude/orchestration/quality_gate.py`
**Problem**: Old module co-exists with new quality_gates.py. Confusing naming.
**Fix**: Add runtime deprecation warning at module level.

---

## Files Modified (Summary)

| # | File | Action | Wave |
|---|------|--------|------|
| 1 | `.claude/settings.json` | FIX shell injection line 84 | 1 |
| 2 | `.claude/helpers/team_executor.py` | FIX path traversal + type safety + atomic writes | 1+2 |
| 3 | `.claude/orchestration/team_workflow.py` | FIX COUPLED_CHAINS/INDEPENDENT_MODULES typing + confidence calc | 1+2+4 |
| 4 | `.claude/hooks/team_router_hook.py` | FIX trivial patterns + exception logging | 2 |
| 5 | `.claude/orchestration/quality_gates.py` | FIX GateProtocol | 4 |
| 6 | `.claude/orchestration/quality_gate.py` | ADD deprecation warning | 4 |
| 7 | `tests/unit/orchestration/test_team_workflow.py` | CREATE | 3 |
| 8 | `tests/unit/orchestration/test_quality_gates_team.py` | CREATE | 3 |
| 9 | `tests/unit/orchestration/test_shared_file_protocol.py` | CREATE | 3 |
| 10 | `tests/unit/orchestration/test_team_executor.py` | CREATE | 3 |

---

## Verification Plan

1. **Syntax**: `python -m py_compile` on all modified `.py` files
2. **Type check**: `grep -rn "object\|Any\|type: ignore" .claude/orchestration/ .claude/helpers/team_executor.py` should return zero hits (except Protocol's `**kwargs: object` which is intentional)
3. **Security**: Confirm `$PROMPT` is no longer echo-piped in settings.json line 84
4. **Path traversal**: Verify `_validate_agent_name("../../etc/passwd")` raises ValueError
5. **Unit tests**: `python -m pytest tests/unit/orchestration/test_team_*.py tests/unit/orchestration/test_shared_*.py tests/unit/orchestration/test_quality_gates_team.py -v`
6. **Confidence**: Verify `_calculate_confidence(C1, M1, ...)` != `_calculate_confidence(C4, M3, ...)`
7. **Integration smoke**: `python .claude/helpers/team_executor.py classify --task "Add banking PSD2 integration"` outputs valid JSON
8. **Trivial detection**: Verify `_is_trivial_prompt("How should we refactor OCR?")` returns `False`
