#!/usr/bin/env python3
"""
Team Executor CLI - Drives team workflow execution phase by phase.

Called by Claude during team workflow orchestration to:
- Classify tasks into team templates
- Resolve prompt templates for each phase
- Save/load phase results from cache
- Run quality gates between phases
- Generate integration instructions for Phase 6
- Mark workflows complete

Usage:
    python team_executor.py classify --task "Implement banking API"
    python team_executor.py phase --number 1 --task "Implement banking API"
    python team_executor.py save-result --phase 1 --result "Research findings..."
    python team_executor.py gate --name gate_1_research --phase 1
    python team_executor.py integrate --phase 6
    python team_executor.py complete
"""

import argparse
import json
import os
import re
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

# Resolve project root: go up 2 levels from .claude/helpers/
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_SCRIPT_DIR))

# Insert project root so we can import from .claude.orchestration
sys.path.insert(0, _PROJECT_ROOT)

# Cache directory for state and phase results
_CACHE_DIR = os.path.join(_PROJECT_ROOT, ".claude", "cache")
_STATE_FILE = os.path.join(_CACHE_DIR, "team_state.json")


def _ensure_cache_dir() -> None:
    """Create the cache directory if it does not exist."""
    os.makedirs(_CACHE_DIR, exist_ok=True)


def _load_state() -> Dict[str, object]:
    """Load workflow state from the cache file."""
    if not os.path.isfile(_STATE_FILE):
        return {}
    with open(_STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)  # type: ignore[no-any-return]


def _save_state(state: Dict[str, object]) -> None:
    """Save workflow state to the cache file."""
    _ensure_cache_dir()
    with open(_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def _read_phase_result(phase_number: int, agent: Optional[str] = None) -> str:
    """Read a cached phase result file. Returns empty string if not found."""
    if agent:
        filename = f"team_phase_{phase_number}_{agent}_result.txt"
    else:
        filename = f"team_phase_{phase_number}_result.txt"
    filepath = os.path.join(_CACHE_DIR, filename)
    if not os.path.isfile(filepath):
        return ""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def _write_phase_result(
    phase_number: int, result: str, agent: Optional[str] = None
) -> str:
    """Write a phase result to cache. Returns the filepath written."""
    _ensure_cache_dir()
    if agent:
        filename = f"team_phase_{phase_number}_{agent}_result.txt"
    else:
        filename = f"team_phase_{phase_number}_result.txt"
    filepath = os.path.join(_CACHE_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(result)
    return filepath


# ---------------------------------------------------------------------------
# Command: classify
# ---------------------------------------------------------------------------

def cmd_classify(args: argparse.Namespace) -> None:
    """Classify a task and output the team template as JSON."""
    try:
        from _claude.orchestration.team_workflow import (
            ClassificationInput,
            TeamClassifier,
        )
    except ImportError:
        try:
            # Fallback: direct module path
            sys.path.insert(0, os.path.join(_PROJECT_ROOT, ".claude"))
            from orchestration.team_workflow import (  # type: ignore[no-redef]
                ClassificationInput,
                TeamClassifier,
            )
        except ImportError as exc:
            print(
                json.dumps(
                    {
                        "error": "ImportError",
                        "message": (
                            f"Could not import team_workflow from orchestration package. "
                            f"Ensure .claude/orchestration/ exists. Details: {exc}"
                        ),
                    }
                )
            )
            sys.exit(1)

    affected_files: List[str] = []
    if args.files:
        affected_files = [f.strip() for f in args.files.split(",") if f.strip()]

    classifier = TeamClassifier()
    classification_input = ClassificationInput(
        task_description=args.task,
        affected_files=affected_files,
    )
    result = classifier.classify(classification_input)

    # Build first phase instructions preview
    first_phase_instructions = ""
    if result.template.phases:
        first_phase = result.template.phases[0]
        first_phase_instructions = (
            f"Phase {first_phase.number}: {first_phase.name} "
            f"({first_phase.mode.value}) - "
            f"{len(first_phase.agents)} agent(s)"
        )

    # Save initial state with serialized template for consistent phase lookups
    state: Dict[str, object] = {
        "task_description": args.task,
        "team_type": result.team_type.value,
        "current_phase": 0,
        "total_phases": len(result.template.phases),
        "status": "classified",
        "phase_results": {},
        "classified_at": datetime.now(timezone.utc).isoformat(),
        "template_serialized": {
            "name": result.template.name,
            "team_type": result.team_type.value,
            "total_agents": result.template.total_agents,
            "has_parallel_phases": result.template.has_parallel_phases,
            "requires_shared_file_integration": result.template.requires_shared_file_integration,
            "phases": [
                {
                    "number": p.number,
                    "name": p.name,
                    "mode": p.mode.value,
                    "gate": p.gate,
                    "description": p.description,
                    "agents": [
                        {
                            "role": a.role,
                            "subagent_type": a.subagent_type,
                            "model": a.model,
                            "prompt_template": a.prompt_template,
                            "description": a.description,
                        }
                        for a in p.agents
                    ],
                }
                for p in result.template.phases
            ],
        },
    }
    _save_state(state)

    output = {
        "team_type": result.team_type.value,
        "complexity": result.complexity.value,
        "coupling": result.coupling.value,
        "confidence": result.confidence,
        "reasoning": result.reasoning,
        "total_phases": len(result.template.phases),
        "total_agents": result.template.total_agents,
        "has_parallel_phases": result.template.has_parallel_phases,
        "requires_shared_file_integration": result.template.requires_shared_file_integration,
        "first_phase_instructions": first_phase_instructions,
        "phases_overview": [
            {
                "number": p.number,
                "name": p.name,
                "mode": p.mode.value,
                "agents": len(p.agents),
                "gate": p.gate,
            }
            for p in result.template.phases
        ],
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Command: phase
# ---------------------------------------------------------------------------

def cmd_phase(args: argparse.Namespace) -> None:
    """Get resolved prompts for a specific phase.

    Reads the template from cached state (saved during classify) to avoid
    re-classification which could produce different results if git state changed.
    Falls back to re-classification for backwards compatibility.
    """
    state = _load_state()
    if not state:
        print(
            json.dumps(
                {
                    "error": "NoState",
                    "message": (
                        "No team state found. Run 'classify' first to initialize "
                        "the workflow state."
                    ),
                }
            )
        )
        sys.exit(1)

    task_description: str = str(state.get("task_description", args.task))
    phase_number = args.number

    # Try to read template from state (cached during classify)
    template_data = state.get("template_serialized")
    if isinstance(template_data, dict) and template_data.get("phases"):
        phases_data: List[Dict[str, object]] = template_data["phases"]  # type: ignore[assignment]
        if phase_number < 1 or phase_number > len(phases_data):
            print(
                json.dumps(
                    {
                        "error": "InvalidPhase",
                        "message": (
                            f"Phase {phase_number} not found in template "
                            f"'{template_data.get('name', 'unknown')}'. "
                            f"Total phases: {len(phases_data)}"
                        ),
                    }
                )
            )
            sys.exit(1)

        phase_data = phases_data[phase_number - 1]
        phase_mode = str(phase_data.get("mode", "sequential"))
        phase_gate = phase_data.get("gate")
        phase_name = str(phase_data.get("name", f"Phase {phase_number}"))
        agents_data: List[Dict[str, str]] = phase_data.get("agents", [])  # type: ignore[assignment]

    else:
        # Fallback: re-classify (backwards compat for states without template_serialized)
        try:
            from _claude.orchestration.team_workflow import (
                ClassificationInput,
                PhaseMode,
                TeamClassifier,
            )
        except ImportError:
            try:
                sys.path.insert(0, os.path.join(_PROJECT_ROOT, ".claude"))
                from orchestration.team_workflow import (  # type: ignore[no-redef]
                    ClassificationInput,
                    PhaseMode,
                    TeamClassifier,
                )
            except ImportError as exc:
                print(
                    json.dumps(
                        {"error": "ImportError", "message": str(exc)}
                    )
                )
                sys.exit(1)

        classifier = TeamClassifier()
        classification = classifier.classify(
            ClassificationInput(task_description=task_description)
        )
        phase_obj = classification.template.get_phase(phase_number)
        if phase_obj is None:
            print(
                json.dumps(
                    {
                        "error": "InvalidPhase",
                        "message": (
                            f"Phase {phase_number} not found in template "
                            f"'{classification.template.name}'. "
                            f"Total phases: {len(classification.template.phases)}"
                        ),
                    }
                )
            )
            sys.exit(1)

        phase_mode = phase_obj.mode.value
        phase_gate = phase_obj.gate
        phase_name = phase_obj.name
        agents_data = [
            {
                "role": a.role,
                "subagent_type": a.subagent_type,
                "model": a.model,
                "prompt_template": a.prompt_template,
                "description": a.description,
            }
            for a in phase_obj.agents
        ]

    # Build context from previous phase results
    context: Dict[str, str] = {
        "task_description": task_description,
    }

    # Load all previous phase results
    for prev_phase_num in range(1, phase_number):
        result_text = _read_phase_result(prev_phase_num)
        context[f"phase_{prev_phase_num}_result"] = result_text

    # Special handling for phase_3_manifests (used by Phase 6 integration)
    # Collect all coder outputs from the implementation phase
    if phase_number >= 6:
        impl_phase = _find_implementation_phase(state)
        manifests_parts: List[str] = []
        impl_main = _read_phase_result(impl_phase)
        if impl_main:
            manifests_parts.append(impl_main)
        # Also check for parallel agent results
        for agent_suffix in ["coder_a", "coder_b", "coder_c", "coder_d"]:
            agent_result = _read_phase_result(impl_phase, agent=agent_suffix)
            if agent_result:
                manifests_parts.append(f"--- {agent_suffix} ---\n{agent_result}")
        context["phase_3_manifests"] = "\n\n".join(manifests_parts) if manifests_parts else "(no manifests found)"

    # Special handling for security audit parallel phases (phase_2a_result, phase_2b_result)
    for suffix in ["a", "b", "c", "d"]:
        agent_role = f"auditor_{suffix}"
        agent_result = _read_phase_result(2, agent=agent_role)
        if agent_result:
            context[f"phase_2{suffix}_result"] = agent_result

    # Resolve prompts for each agent
    is_parallel = phase_mode == "parallel"
    agents_output: List[Dict[str, object]] = []
    for agent_data in agents_data:
        prompt_template = str(agent_data.get("prompt_template", ""))
        resolved_prompt = prompt_template
        for key, value in context.items():
            placeholder = "{" + key + "}"
            resolved_prompt = resolved_prompt.replace(placeholder, value)

        agents_output.append(
            {
                "role": str(agent_data.get("role", "")),
                "subagent_type": str(agent_data.get("subagent_type", "")),
                "model": str(agent_data.get("model", "")),
                "prompt": resolved_prompt,
                "description": str(agent_data.get("description", "")),
                "run_in_background": is_parallel,
            }
        )

    # Update state
    state["current_phase"] = phase_number
    state["status"] = "in_progress"
    _save_state(state)

    output = {
        "phase_number": phase_number,
        "phase_name": phase_name,
        "mode": "parallel" if is_parallel else "sequential",
        "gate": phase_gate,
        "agents": agents_output,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Command: save-result
# ---------------------------------------------------------------------------

def cmd_save_result(args: argparse.Namespace) -> None:
    """Save a phase result to cache and update state."""
    phase_number: int = args.phase
    agent_role: Optional[str] = args.agent if hasattr(args, "agent") else None
    result_text: str = args.result

    filepath = _write_phase_result(phase_number, result_text, agent=agent_role)

    # Update state
    state = _load_state()
    if state:
        state["current_phase"] = phase_number
        state["status"] = "in_progress"
        phase_results = state.get("phase_results", {})
        if not isinstance(phase_results, dict):
            phase_results = {}
        key = f"phase_{phase_number}" if not agent_role else f"phase_{phase_number}_{agent_role}"
        phase_results[key] = {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "length": len(result_text),
            "file": filepath,
        }
        state["phase_results"] = phase_results
        _save_state(state)

    output = {
        "status": "saved",
        "phase": phase_number,
        "agent": agent_role,
        "file": filepath,
        "length": len(result_text),
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Command: gate
# ---------------------------------------------------------------------------

def cmd_gate(args: argparse.Namespace) -> None:
    """Run a quality gate on the result of a phase."""
    try:
        from _claude.orchestration.quality_gates import GateStatus, run_gate
    except ImportError:
        try:
            sys.path.insert(0, os.path.join(_PROJECT_ROOT, ".claude"))
            from orchestration.quality_gates import (  # type: ignore[no-redef]
                GateStatus,
                run_gate,
            )
        except ImportError as exc:
            print(
                json.dumps(
                    {"error": "ImportError", "message": str(exc)}
                )
            )
            sys.exit(1)

    gate_name: str = args.name
    phase_number: int = args.phase

    # Read the phase result
    result_text = _read_phase_result(phase_number)
    if not result_text:
        print(
            json.dumps(
                {
                    "error": "NoResult",
                    "message": (
                        f"No result found for phase {phase_number}. "
                        f"Run 'save-result --phase {phase_number}' first."
                    ),
                }
            )
        )
        sys.exit(1)

    # Build kwargs based on gate name
    kwargs: Dict[str, object] = {}

    if gate_name == "gate_1_research":
        kwargs["research_output"] = result_text
        kwargs["affected_files"] = _extract_file_paths(result_text)

    elif gate_name == "gate_2_design":
        kwargs["design_output"] = result_text

    elif gate_name == "gate_3_code_quality":
        kwargs["code_output"] = result_text
        kwargs["files_changed"] = _extract_file_paths(result_text)

    elif gate_name == "gate_4_tests":
        kwargs["test_output"] = result_text
        kwargs["test_files"] = _extract_test_files(result_text)

    elif gate_name == "gate_5_review":
        kwargs["review_output"] = result_text
        # Gate 5 also needs code_output from phase 3
        code_result = _read_phase_result(3)
        if not code_result:
            # Try phase 2 as fallback (for bugfix templates where code is phase 2)
            code_result = _read_phase_result(2)
        kwargs["code_output"] = code_result if code_result else ""

    elif gate_name == "gate_6_integration":
        kwargs["integration_output"] = result_text
        kwargs["manifests"] = _extract_manifests_for_gate(result_text)

    else:
        # Pass result as first keyword for unknown gates
        kwargs["result"] = result_text

    try:
        gate_result = run_gate(gate_name, **kwargs)
    except KeyError as exc:
        print(
            json.dumps(
                {
                    "error": "UnknownGate",
                    "message": str(exc),
                }
            )
        )
        sys.exit(1)

    # Output the formatted report
    report = gate_result.format_report()
    print(report)
    print()

    # Also output machine-readable summary
    summary = {
        "gate_name": gate_result.gate_name,
        "gate_number": gate_result.gate_number,
        "status": gate_result.status.value,
        "blocks": len(gate_result.blocks),
        "warnings": len(gate_result.warnings),
        "total_checks": len(gate_result.checks),
        "passed_checks": len([c for c in gate_result.checks if c.passed]),
    }
    print("--- JSON SUMMARY ---")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def _find_implementation_phase(state: Dict[str, object]) -> int:
    """Find the implementation/coding phase number from cached state.

    Looks for a parallel phase or one named 'implementation' in the template.
    Falls back to 3 (the conventional implementation phase).
    """
    template = state.get("template_serialized", {})
    phases = template.get("phases", []) if isinstance(template, dict) else []
    for p in phases:
        if not isinstance(p, dict):
            continue
        mode = str(p.get("mode", "")).lower()
        name = str(p.get("name", "")).lower()
        if "parallel" in mode:
            return int(p.get("number", 3))
        if "implementation" in name:
            return int(p.get("number", 3))
    return 3  # Default fallback


def _extract_file_paths(text: str) -> List[str]:
    """Extract file paths from text output (heuristic)."""
    # Match common project file paths
    patterns = [
        r"(app/[a-zA-Z0-9_/]+\.py)",
        r"(tests/[a-zA-Z0-9_/]+\.py)",
        r"(frontend/[a-zA-Z0-9_/]+\.(?:tsx?|jsx?))",
        r"(alembic/[a-zA-Z0-9_/]+\.py)",
    ]
    found: List[str] = []
    for pattern in patterns:
        found.extend(re.findall(pattern, text))
    # Deduplicate while preserving order
    seen: Set[str] = set()
    result: List[str] = []
    for path in found:
        if path not in seen:
            seen.add(path)
            result.append(path)
    return result


def _extract_test_files(text: str) -> List[str]:
    """Extract test file paths from text output."""
    patterns = [
        r"(tests/[a-zA-Z0-9_/]*test_[a-zA-Z0-9_]+\.py)",
        r"(test_[a-zA-Z0-9_]+\.py)",
    ]
    found: List[str] = []
    for pattern in patterns:
        found.extend(re.findall(pattern, text))
    seen: Set[str] = set()
    result: List[str] = []
    for path in found:
        if path not in seen:
            seen.add(path)
            result.append(path)
    return result


def _extract_manifests_for_gate(text: str) -> List[Dict[str, str]]:
    """Extract manifest entries for Gate 6 from integration output."""
    manifests: List[Dict[str, str]] = []
    # Look for router, model, task keywords
    if re.search(r"(router|include_router)", text, re.IGNORECASE):
        manifests.append({"type": "router", "description": "Router registration"})
    if re.search(r"(models_\w+|satellite.*model)", text, re.IGNORECASE):
        manifests.append({"type": "model", "description": "Model import"})
    if re.search(r"(task|celery|beat_schedule)", text, re.IGNORECASE):
        manifests.append({"type": "task", "description": "Task registration"})
    return manifests


# ---------------------------------------------------------------------------
# Command: integrate
# ---------------------------------------------------------------------------

def cmd_integrate(args: argparse.Namespace) -> None:
    """Generate Phase 6 integration instructions from collected manifests."""
    try:
        from _claude.orchestration.shared_file_protocol import (
            ModelImport,
            RegistrationManifest,
            RouterImport,
            SharedFileProtocol,
            TaskExport,
            TaskModule,
        )
    except ImportError:
        try:
            sys.path.insert(0, os.path.join(_PROJECT_ROOT, ".claude"))
            from orchestration.shared_file_protocol import (  # type: ignore[no-redef]
                ModelImport,
                RegistrationManifest,
                RouterImport,
                SharedFileProtocol,
                TaskExport,
                TaskModule,
            )
        except ImportError as exc:
            print(
                json.dumps(
                    {"error": "ImportError", "message": str(exc)}
                )
            )
            sys.exit(1)

    phase_number: int = args.phase

    # Determine the implementation phase from state (not hardcoded to 3)
    state = _load_state()
    impl_phase = _find_implementation_phase(state)

    # Collect all parallel coder outputs from the implementation phase
    coder_outputs: List[str] = []

    # Check the main phase result
    main_result = _read_phase_result(impl_phase)
    if main_result:
        coder_outputs.append(main_result)

    # Check agent-specific results
    for agent_suffix in ["coder_a", "coder_b", "coder_c", "coder_d"]:
        agent_result = _read_phase_result(impl_phase, agent=agent_suffix)
        if agent_result:
            coder_outputs.append(agent_result)

    if not coder_outputs:
        print(
            json.dumps(
                {
                    "error": "NoCoderOutputs",
                    "message": (
                        f"No coder outputs found for implementation phase {impl_phase}. "
                        f"Save coder results with: "
                        f"save-result --phase {impl_phase} --agent coder_a --result '...'"
                    ),
                }
            )
        )
        sys.exit(1)

    # Attempt to extract manifest JSON from coder outputs
    manifests: List[RegistrationManifest] = []
    for output_text in coder_outputs:
        manifest = _parse_manifest_from_output(
            output_text,
            RouterImport,
            ModelImport,
            TaskModule,
            TaskExport,
            RegistrationManifest,
        )
        if manifest:
            manifests.append(manifest)

    protocol = SharedFileProtocol()

    if manifests:
        merged = protocol.merge_manifests(manifests)
    else:
        # Create empty manifest with best-effort extraction
        merged = _best_effort_manifest(
            coder_outputs,
            RouterImport,
            ModelImport,
            TaskModule,
            TaskExport,
            RegistrationManifest,
        )

    instructions = protocol.generate_integration_instructions(merged)

    output = {
        "phase": phase_number,
        "manifests_found": len(manifests),
        "coder_outputs_collected": len(coder_outputs),
        "router_imports": len(merged.router_imports),
        "model_imports": len(merged.model_imports),
        "task_modules": len(merged.task_modules),
        "task_exports": len(merged.task_exports),
        "instructions": instructions,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


def _parse_manifest_from_output(
    text: str,
    router_import_cls: type,
    model_import_cls: type,
    task_module_cls: type,
    task_export_cls: type,
    manifest_cls: type,
) -> Optional[object]:
    """Try to find and parse a JSON manifest block from coder output."""
    # Look for JSON blocks in the output
    json_blocks = re.findall(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    for block in json_blocks:
        try:
            data = json.loads(block)
            if isinstance(data, dict) and any(
                key in data
                for key in ["router_imports", "model_imports", "task_modules", "task_exports"]
            ):
                return _dict_to_manifest(
                    data,
                    router_import_cls,
                    model_import_cls,
                    task_module_cls,
                    task_export_cls,
                    manifest_cls,
                )
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    return None


def _dict_to_manifest(
    data: Dict[str, object],
    router_import_cls: type,
    model_import_cls: type,
    task_module_cls: type,
    task_export_cls: type,
    manifest_cls: type,
) -> object:
    """Convert a dict to a RegistrationManifest instance."""
    manifest = manifest_cls()

    router_list = data.get("router_imports", [])
    if isinstance(router_list, list):
        for item in router_list:
            if isinstance(item, dict):
                manifest.router_imports.append(  # type: ignore[attr-defined]
                    router_import_cls(
                        import_path=str(item.get("import_path", "")),
                        router_var=str(item.get("router_var", "router")),
                        prefix=str(item.get("prefix", "")),
                    )
                )

    model_list = data.get("model_imports", [])
    if isinstance(model_list, list):
        for item in model_list:
            if isinstance(item, dict):
                manifest.model_imports.append(  # type: ignore[attr-defined]
                    model_import_cls(
                        import_path=str(item.get("import_path", "")),
                        comment=str(item.get("comment", "")),
                    )
                )

    task_mod_list = data.get("task_modules", [])
    if isinstance(task_mod_list, list):
        for item in task_mod_list:
            if isinstance(item, dict):
                manifest.task_modules.append(  # type: ignore[attr-defined]
                    task_module_cls(
                        module_path=str(item.get("module_path", "")),
                        beat_schedule_var=item.get("beat_schedule_var"),
                    )
                )

    task_exp_list = data.get("task_exports", [])
    if isinstance(task_exp_list, list):
        for item in task_exp_list:
            if isinstance(item, dict):
                task_names_raw = item.get("task_names", [])
                task_names = (
                    [str(t) for t in task_names_raw]
                    if isinstance(task_names_raw, list)
                    else []
                )
                manifest.task_exports.append(  # type: ignore[attr-defined]
                    task_export_cls(
                        module_name=str(item.get("module_name", "")),
                        task_names=task_names,
                        beat_schedule_var=item.get("beat_schedule_var"),
                    )
                )

    return manifest


def _best_effort_manifest(
    coder_outputs: List[str],
    router_import_cls: type,
    model_import_cls: type,
    task_module_cls: type,
    task_export_cls: type,
    manifest_cls: type,
) -> object:
    """Build a best-effort manifest by regex extraction from coder outputs."""
    manifest = manifest_cls()
    combined = "\n".join(coder_outputs)

    # Extract router imports
    router_matches = re.findall(
        r"from\s+(app\.api\.v1\.\w+)\s+import\s+(\w+)", combined
    )
    for import_path, router_var in router_matches:
        # Guess prefix from import path
        module_name = import_path.split(".")[-1]
        prefix = f"/api/v1/{module_name}"
        manifest.router_imports.append(  # type: ignore[attr-defined]
            router_import_cls(
                import_path=import_path,
                router_var=router_var,
                prefix=prefix,
            )
        )

    # Extract model imports
    model_matches = re.findall(
        r"from\s+(app\.db\.models_\w+)\s+import", combined
    )
    for import_path in model_matches:
        feature = import_path.split("models_")[-1]
        manifest.model_imports.append(  # type: ignore[attr-defined]
            model_import_cls(
                import_path=import_path,
                comment=f"# {feature} Models",
            )
        )

    # Extract task modules
    task_matches = re.findall(
        r"from\s+(app\.workers\.tasks\.\w+_tasks)\s+import", combined
    )
    for module_path in task_matches:
        manifest.task_modules.append(  # type: ignore[attr-defined]
            task_module_cls(module_path=module_path)
        )

    return manifest


# ---------------------------------------------------------------------------
# Command: complete
# ---------------------------------------------------------------------------

def cmd_complete(args: argparse.Namespace) -> None:
    """Mark the workflow as complete and output a summary."""
    state = _load_state()
    if not state:
        print(
            json.dumps(
                {
                    "error": "NoState",
                    "message": "No team state found. Nothing to complete.",
                }
            )
        )
        sys.exit(1)

    state["status"] = "completed"
    state["completed_at"] = datetime.now(timezone.utc).isoformat()
    _save_state(state)

    phase_results = state.get("phase_results", {})
    phases_completed = len(phase_results) if isinstance(phase_results, dict) else 0

    output = {
        "status": "completed",
        "team_type": state.get("team_type", "unknown"),
        "task_description": state.get("task_description", ""),
        "total_phases": state.get("total_phases", 0),
        "phases_with_results": phases_completed,
        "classified_at": state.get("classified_at", ""),
        "completed_at": state.get("completed_at", ""),
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Argument Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="team_executor",
        description="CLI tool for driving team workflow execution phase by phase.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # classify
    p_classify = subparsers.add_parser(
        "classify",
        help="Classify a task and select the appropriate team template.",
    )
    p_classify.add_argument(
        "--task", required=True, help="Task description to classify."
    )
    p_classify.add_argument(
        "--files",
        default=None,
        help="Comma-separated list of affected files.",
    )

    # phase
    p_phase = subparsers.add_parser(
        "phase",
        help="Get resolved prompts for a specific phase.",
    )
    p_phase.add_argument(
        "--number",
        type=int,
        required=True,
        help="Phase number (1-based).",
    )
    p_phase.add_argument(
        "--task",
        default="",
        help="Task description (overrides state if provided).",
    )

    # save-result
    p_save = subparsers.add_parser(
        "save-result",
        help="Save a phase result to cache.",
    )
    p_save.add_argument(
        "--phase",
        type=int,
        required=True,
        help="Phase number.",
    )
    p_save.add_argument(
        "--agent",
        default=None,
        help="Agent role (for parallel phases, e.g. coder_a).",
    )
    p_save.add_argument(
        "--result",
        required=True,
        help="Result text to save.",
    )

    # gate
    p_gate = subparsers.add_parser(
        "gate",
        help="Run a quality gate on a phase result.",
    )
    p_gate.add_argument(
        "--name",
        required=True,
        help="Gate name (e.g. gate_1_research, gate_4_tests).",
    )
    p_gate.add_argument(
        "--phase",
        type=int,
        required=True,
        help="Phase number whose result to check.",
    )

    # integrate
    p_integrate = subparsers.add_parser(
        "integrate",
        help="Generate Phase 6 integration instructions from coder manifests.",
    )
    p_integrate.add_argument(
        "--phase",
        type=int,
        default=6,
        help="Phase number for integration (default: 6).",
    )

    # complete
    subparsers.add_parser(
        "complete",
        help="Mark the workflow as completed.",
    )

    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point for the team executor CLI."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    _ensure_cache_dir()

    command_map: Dict[str, object] = {
        "classify": cmd_classify,
        "phase": cmd_phase,
        "save-result": cmd_save_result,
        "gate": cmd_gate,
        "integrate": cmd_integrate,
        "complete": cmd_complete,
    }

    handler = command_map.get(args.command)
    if handler is None:
        print(
            json.dumps(
                {
                    "error": "UnknownCommand",
                    "message": f"Unknown command: {args.command}",
                }
            )
        )
        sys.exit(1)

    handler(args)  # type: ignore[operator]


if __name__ == "__main__":
    main()
