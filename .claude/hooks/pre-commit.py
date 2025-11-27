#!/usr/bin/env python3
"""
Pre-commit hook for Ablage-System.
Validates code quality before commits.

Usage:
    This hook is triggered automatically when committing changes.
    It checks for:
    - Python type hints
    - German text validation
    - Security issues
    - GPU resource management patterns
"""

import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


def run_command(cmd: List[str]) -> Tuple[int, str, str]:
    """Run a command and return exit code, stdout, stderr."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def check_python_typing(files: List[str]) -> bool:
    """Check that Python files have proper type hints."""
    python_files = [f for f in files if f.endswith('.py')]
    if not python_files:
        return True

    code, stdout, stderr = run_command(['mypy', '--strict'] + python_files)
    if code != 0:
        print("FEHLER: Typ-Annotationen fehlen oder sind fehlerhaft!")
        print(stderr or stdout)
        return False
    return True


def check_german_messages(files: List[str]) -> bool:
    """Verify user-facing strings are in German."""
    issues = []
    english_patterns = [
        'Error:', 'Warning:', 'Success:', 'Failed:', 'Invalid:',
        'Not found', 'Unauthorized', 'Forbidden'
    ]

    for filepath in files:
        if not filepath.endswith('.py'):
            continue
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                for pattern in english_patterns:
                    if f'"{pattern}' in content or f"'{pattern}" in content:
                        issues.append(f"{filepath}: Englische Fehlermeldung gefunden: '{pattern}'")
        except Exception:
            pass

    if issues:
        print("WARNUNG: Englische Texte in Benutzeroberfläche gefunden:")
        for issue in issues:
            print(f"  - {issue}")
        return False
    return True


def check_security_patterns(files: List[str]) -> bool:
    """Check for security anti-patterns."""
    issues = []
    dangerous_patterns = [
        ('eval(', 'eval() ist gefährlich'),
        ('exec(', 'exec() ist gefährlich'),
        ('shell=True', 'shell=True vermeiden'),
        ('password =', 'Passwörter nicht im Code speichern'),
        ('api_key =', 'API-Keys nicht im Code speichern'),
    ]

    for filepath in files:
        if not filepath.endswith('.py'):
            continue
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f, 1):
                    for pattern, message in dangerous_patterns:
                        if pattern in line and '#' not in line.split(pattern)[0]:
                            issues.append(f"{filepath}:{i}: {message}")
        except Exception:
            pass

    if issues:
        print("SICHERHEITSWARNUNG:")
        for issue in issues:
            print(f"  - {issue}")
        return False
    return True


def check_gpu_patterns(files: List[str]) -> bool:
    """Check for proper GPU resource management."""
    issues = []

    for filepath in files:
        if not filepath.endswith('.py') or 'test' in filepath.lower():
            continue
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                # Check for GPU usage without context manager
                if '.cuda()' in content and 'gpu_memory_guard' not in content:
                    if 'torch.cuda' in content or 'import torch' in content:
                        issues.append(f"{filepath}: GPU-Nutzung ohne gpu_memory_guard")
        except Exception:
            pass

    if issues:
        print("GPU-MANAGEMENT WARNUNG:")
        for issue in issues:
            print(f"  - {issue}")
        # This is a warning, not a failure
    return True


def main() -> int:
    """Run all pre-commit checks."""
    # Get staged files
    code, stdout, _ = run_command(['git', 'diff', '--cached', '--name-only'])
    if code != 0:
        return 1

    files = [f.strip() for f in stdout.split('\n') if f.strip()]
    if not files:
        return 0

    print("=== Ablage-System Pre-Commit Prüfungen ===\n")

    all_passed = True

    # Run checks
    checks = [
        ("Typ-Annotationen", check_python_typing),
        ("Deutsche Nachrichten", check_german_messages),
        ("Sicherheitsmuster", check_security_patterns),
        ("GPU-Management", check_gpu_patterns),
    ]

    for name, check_func in checks:
        print(f"Prüfe {name}...")
        if not check_func(files):
            all_passed = False
        else:
            print(f"  ✓ {name} OK")
        print()

    if not all_passed:
        print("\n❌ Pre-Commit Prüfung fehlgeschlagen!")
        print("Bitte die oben genannten Probleme beheben.")
        return 1

    print("✓ Alle Prüfungen bestanden!")
    return 0


if __name__ == '__main__':
    sys.exit(main())
