#!/usr/bin/env python3
"""
Prompt Guard Hook - Cross-Instance Interference Protection.

Detects shell commands accidentally sent as user prompts (e.g. from
PowerShell venv activation in another terminal) and blocks them before
they get interpreted as tasks.

Must run BEFORE other UserPromptSubmit hooks.

Usage (Claude Code hook config):
    {
        "event": "UserPromptSubmit",
        "command": "python .claude/hooks/prompt_guard_hook.py"
    }
"""

import json
import os
import re
import sys
from typing import List

# Shell command patterns that should never be treated as user prompts
_SHELL_PATTERNS: List[str] = [
    # PowerShell
    r"^&\s",                          # PowerShell call operator
    r"^\.\\\S",                        # PowerShell relative path execution
    r"\.ps1\b",                        # PowerShell script files
    r"\bActivate\.ps1\b",             # Venv activation (PowerShell)
    r"\bSet-ExecutionPolicy\b",        # PowerShell policy
    r"\bImport-Module\b",             # PowerShell module import
    r"\bInvoke-Expression\b",          # PowerShell iex

    # Bash / Unix
    r"^source\s+\S",                   # Bash source command
    r"^\.\/\S",                        # Bash relative execution
    r"^export\s+\w+=",                 # Environment variable export
    r"^chmod\s",                       # File permissions
    r"^sudo\s",                        # Sudo commands
    r"^eval\s",                        # Eval command

    # Venv activation (cross-platform)
    r"venv[/\\](Scripts|bin)[/\\]",    # Venv paths
    r"\bactivate(\.bat|\.ps1|\.fish)?\s*$",  # Activate scripts

    # Path-only inputs (bare file paths without explanatory text)
    r"^[A-Za-z]:\\[\w\\.\-]+$",        # Windows absolute path only
    r"^/[\w/.\-]+$",                   # Unix absolute path only

    # Common shell-only commands (no natural language context)
    r"^(cd|ls|dir|cat|echo|rm|del|copy|move|mkdir|rmdir)\s+[\"']?[/\\.\w]",
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _SHELL_PATTERNS]


def _is_shell_command(prompt: str) -> bool:
    """Check if the prompt looks like a shell command, not a user request."""
    stripped = prompt.strip()
    if not stripped:
        return False
    return any(pat.search(stripped) for pat in _COMPILED_PATTERNS)


def main() -> None:
    """Main hook entry point.

    Reads user prompt from PROMPT_TEXT env var or stdin.
    Outputs JSON with additionalContext warning if shell command detected.
    Silent (no output) for normal prompts.
    """
    try:
        prompt: str = os.environ.get("PROMPT_TEXT", "")
        if not prompt:
            raw = sys.stdin.read()
            if not raw.strip():
                return
            try:
                data = json.loads(raw)
                prompt = data.get("prompt", "")
            except json.JSONDecodeError:
                prompt = raw.strip()

        if not prompt or not _is_shell_command(prompt):
            return

        # Shell command detected - warn Claude to ignore it
        warning = (
            "[SHELL_COMMAND_DETECTED] Dieser Prompt ist ein Shell-Befehl, "
            "keine User-Anfrage.\n"
            "IGNORIERE diesen Prompt komplett. Fuehre ihn NICHT aus.\n"
            "Antworte dem User: \"Ein Shell-Befehl wurde automatisch als "
            "Prompt gesendet. Ich ignoriere ihn.\""
        )

        output = {"additionalContext": warning}
        print(json.dumps(output))

    except Exception:
        pass  # Guard hook must NEVER break the user experience


if __name__ == "__main__":
    main()
