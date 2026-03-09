#!/usr/bin/env python3
"""
Team Router Hook for Claude Code UserPromptSubmit.

Classifies incoming tasks and injects [TEAM_WORKFLOW_ACTIVE] directive
when a multi-agent team workflow is needed.

Usage (Claude Code hook config):
    {
        "event": "UserPromptSubmit",
        "command": "python .claude/hooks/team_router_hook.py"
    }

Reads JSON from stdin: {"prompt": "..."}
Outputs JSON to stdout ONLY when a team workflow is needed.
Outputs nothing (silent) for trivial prompts or no-team classifications.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import List

# Project root: .claude/hooks/../../ = project root
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

# .claude directory: needed for importing orchestration package
_CLAUDE_DIR = os.path.join(_PROJECT_ROOT, ".claude")


def _get_changed_files() -> List[str]:
    """Get list of changed files from git status (best-effort).

    Returns relative file paths from git status --porcelain.
    Silently returns empty list on any failure.
    """
    try:
        import subprocess

        result = subprocess.run(
            ["git", "status", "--porcelain", "-u"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=_PROJECT_ROOT,
        )
        if result.returncode != 0:
            return []

        files: List[str] = []
        for line in result.stdout.strip().splitlines():
            if len(line) > 3:
                filepath = line[3:].strip()
                # Handle renamed files: "old -> new"
                if " -> " in filepath:
                    filepath = filepath.split(" -> ")[-1]
                files.append(filepath)
        return files
    except Exception:
        return []


def _is_trivial_prompt(prompt: str) -> bool:
    """Detect prompts that should never trigger team workflow.

    Only filters truly trivial prompts:
    - Greetings (hi, hello, hallo)
    - Slash commands (/commit, /review, etc.)
    - Simple confirmations (yes, no, ok, danke)
    - Bare CLI commands (git ..., npm ..., docker ..., pytest ...)
    - Bare commit requests
    """
    trivial_patterns: List[str] = [
        r"^(hi|hello|hey|hallo|guten\s*(tag|morgen|abend))$",
        r"^/",  # Slash commands
        r"^(yes|no|ja|nein|ok|okay|mach das|go ahead|weiter|fertig|done|danke|thanks)$",
        r"^(help|hilfe)$",
        r"^commit\s*(message|msg)?$",
        r"^(git|npm|docker|pytest)\s",
        # Shell commands (cross-instance interference guard)
        r"^&\s",                         # PowerShell call operator
        r"^\.\\\S",                      # PowerShell relative path
        r"\.ps1\b",                      # PowerShell scripts
        r"^source\s",                    # Bash source command
        r"venv[/\\](Scripts|bin)",       # Venv activation paths
        r"^(cd|ls|dir|cat|echo)\s",      # Basic shell commands
        r"^export\s+\w+=",              # Env var exports
        r"^chmod\s",                     # File permissions
        r"^sudo\s",                      # Sudo commands
        r"^[A-Za-z]:\\[\w\\.\-]+$",      # Bare Windows paths
    ]
    prompt_lower = prompt.strip().lower()
    if not prompt_lower:
        return True
    return any(re.search(p, prompt_lower) for p in trivial_patterns)


def _detect_security_intent(prompt_lower: str) -> bool:
    """Check if prompt indicates a security-related task."""
    return bool(
        re.search(
            r"(security|sicherheit|audit|vulnerability|cve|injection|owasp)",
            prompt_lower,
        )
    )


def _detect_review_intent(prompt_lower: str) -> bool:
    """Check if prompt indicates a code review request."""
    return bool(
        re.search(
            r"(review\s*code|code\s*review|pruefe\s*code|qualitaetspruefung)",
            prompt_lower,
        )
    )


def _import_team_workflow():  # noqa: ANN202 - return type is module-level tuple
    """Import TeamClassifier and related types from orchestration package.

    Handles the tricky path: this file is in .claude/hooks/ but needs
    to import from .claude/orchestration/team_workflow.py.

    Returns a tuple of (TeamClassifier, ClassificationInput, TeamType).
    Raises ImportError if the orchestration package cannot be found.
    """
    # Strategy 1: Direct import from .claude/orchestration/ via sys.path
    if _CLAUDE_DIR not in sys.path:
        sys.path.insert(0, _CLAUDE_DIR)

    try:
        from orchestration.team_workflow import (
            ClassificationInput,
            TeamClassifier,
            TeamType,
        )

        return TeamClassifier, ClassificationInput, TeamType
    except ImportError:
        pass

    # Strategy 2: Add project root and try dotted import
    if _PROJECT_ROOT not in sys.path:
        sys.path.insert(0, _PROJECT_ROOT)

    # The .claude directory cannot be imported with a dot prefix via
    # normal Python imports. We use importlib to handle this edge case.
    import importlib.util

    module_path = os.path.join(_CLAUDE_DIR, "orchestration", "team_workflow.py")
    if not os.path.isfile(module_path):
        raise ImportError(
            f"team_workflow.py not found at {module_path}"
        )

    spec = importlib.util.spec_from_file_location(
        "team_workflow", module_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(
            f"Could not create module spec for {module_path}"
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module.TeamClassifier, module.ClassificationInput, module.TeamType


def main() -> None:
    """Main hook entry point.

    Reads user prompt from stdin as JSON, classifies the task,
    and outputs a JSON directive if a team workflow is needed.
    Silent (no output) on trivial prompts or no-team classifications.
    """
    try:
        # Prefer PROMPT_TEXT env var (avoids JSON escaping issues with special chars)
        prompt: str = os.environ.get("PROMPT_TEXT", "")
        if not prompt:
            raw = sys.stdin.read()
            if not raw.strip():
                return
            data = json.loads(raw)
            prompt = data.get("prompt", "")

        if not prompt or _is_trivial_prompt(prompt):
            return

        # Import classifier (may fail if orchestration package not available)
        TeamClassifier, ClassificationInput, TeamType = _import_team_workflow()

        # Get changed files for better complexity estimation
        changed_files = _get_changed_files()

        # Detect intent overrides from prompt keywords
        prompt_lower = prompt.lower()
        is_security = _detect_security_intent(prompt_lower)
        is_review = _detect_review_intent(prompt_lower)

        # Classify the task
        classifier = TeamClassifier()
        result = classifier.classify(
            ClassificationInput(
                task_description=prompt,
                affected_files=changed_files,
                is_security=is_security,
                is_review_only=is_review,
            )
        )

        # No-team types: let standard routing handle it (silent exit)
        if result.team_type in (TeamType.NO_TEAM_HAIKU, TeamType.NO_TEAM_SONNET):
            return

        # Team workflow needed: inject directive via additionalContext
        phase_count = len(result.template.phases)
        agent_count = result.template.total_agents
        requires_integration = result.template.requires_shared_file_integration

        context_lines = [
            "[TEAM_WORKFLOW_ACTIVE]",
            f"TEAM_TYPE: {result.team_type.value}",
            f"COMPLEXITY: {result.complexity.value}",
            f"COUPLING: {result.coupling.value}",
            f"CONFIDENCE: {result.confidence:.2f}",
            f"TOTAL_PHASES: {phase_count}",
            f"TOTAL_AGENTS: {agent_count}",
            f"REQUIRES_INTEGRATION: {requires_integration}",
            f"REASONING: {result.reasoning}",
            "",
            "Fuehre den Team-Workflow aus gemaess TEAM WORKFLOW PROTOCOL in CLAUDE.md.",
            'Starte: python .claude/helpers/team_executor.py classify --task "<task>"',
        ]

        output = {
            "additionalContext": "\n".join(context_lines),
        }
        print(json.dumps(output))

    except Exception as exc:
        # Hook must NEVER break the user experience.
        # Log errors to file for debugging, but never crash.
        try:
            import traceback
            log_path = os.path.join(_PROJECT_ROOT, ".claude", "cache", "team_router_hook.log")
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now(timezone.utc).isoformat()} ERROR: {exc}\n")
                f.write(traceback.format_exc() + "\n")
        except Exception:
            pass  # Logging must never crash the hook


if __name__ == "__main__":
    main()
