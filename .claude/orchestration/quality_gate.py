"""
Quality Gate für Multi-Model Orchestration.

Validiert Output von Subagents und entscheidet über Eskalation:
- Type-Hints Validierung
- Deutsche Nachrichten Check
- GPU-Pattern Validierung
- Security Anti-Pattern Detection
"""

import re
import ast
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Callable, Dict, Any
from enum import Enum
from pathlib import Path


class QualityLevel(Enum):
    """Quality-Level für Validierungsergebnisse."""
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"


@dataclass
class QualityResult:
    """Ergebnis der Quality-Validierung."""
    level: QualityLevel
    checks_passed: List[str]
    checks_failed: List[str]
    warnings: List[str]
    should_escalate: bool
    escalation_reason: Optional[str] = None
    details: Dict[str, Any] = None


class QualityGate:
    """Validiert Output von Subagents."""

    def __init__(self):
        self.checks: List[Callable] = [
            self._check_type_hints,
            self._check_german_messages,
            self._check_gpu_patterns,
            self._check_security_patterns,
            self._check_imports,
            self._check_syntax,
        ]

    def validate(
        self,
        code: str,
        file_path: str,
        model_used: str,
        context: Dict[str, Any] = None
    ) -> QualityResult:
        """
        Führt alle Quality Checks durch.

        Args:
            code: Zu validierender Code
            file_path: Pfad der Datei
            model_used: Verwendetes Modell
            context: Zusätzlicher Kontext

        Returns:
            QualityResult mit Validierungsergebnis
        """

        passed = []
        failed = []
        warnings = []
        context = context or {}

        for check in self.checks:
            try:
                result = check(code, file_path, context)
                if result["status"] == "passed":
                    passed.append(result["name"])
                elif result["status"] == "warning":
                    warnings.append(f"{result['name']}: {result['message']}")
                else:
                    failed.append(f"{result['name']}: {result['message']}")
            except Exception as e:
                warnings.append(f"Check-Fehler ({check.__name__}): {e}")

        # Entscheide über Eskalation
        should_escalate = len(failed) > 0
        escalation_reason = None

        if should_escalate:
            escalation_reason = f"Quality Gate fehlgeschlagen: {', '.join(failed)}"

        # Bei Haiku: Auch Warnings führen zur Eskalation
        if model_used == "haiku" and warnings and not should_escalate:
            should_escalate = True
            escalation_reason = f"Haiku-Warnings: {', '.join(warnings)}"

        # Bei kritischen Pfaden: Strengere Validierung
        if self._is_critical_path(file_path) and warnings:
            should_escalate = True
            escalation_reason = f"Kritischer Pfad mit Warnings: {file_path}"

        return QualityResult(
            level=QualityLevel.FAILED if failed else (
                QualityLevel.WARNING if warnings else QualityLevel.PASSED
            ),
            checks_passed=passed,
            checks_failed=failed,
            warnings=warnings,
            should_escalate=should_escalate,
            escalation_reason=escalation_reason,
            details={
                "model_used": model_used,
                "file_path": file_path,
                "total_checks": len(self.checks),
            }
        )

    def _is_critical_path(self, file_path: str) -> bool:
        """Prüft ob Pfad kritisch ist."""
        critical_paths = [
            "app/core/",
            "app/security/",
            "app/agents/ocr/",
            "alembic/versions/",
        ]
        return any(cp in file_path for cp in critical_paths)

    def _check_syntax(self, code: str, path: str, context: Dict) -> Dict:
        """Prüft Python-Syntax."""
        if not path.endswith('.py'):
            return {"name": "syntax", "status": "passed"}

        try:
            ast.parse(code)
            return {"name": "syntax", "status": "passed"}
        except SyntaxError as e:
            return {
                "name": "syntax",
                "status": "failed",
                "message": f"Syntax-Fehler: {e.msg} (Zeile {e.lineno})"
            }

    def _check_type_hints(self, code: str, path: str, context: Dict) -> Dict:
        """Prüft Type-Hints in Python-Code."""
        if not path.endswith('.py'):
            return {"name": "type_hints", "status": "passed"}

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return {"name": "type_hints", "status": "failed", "message": "Syntax-Fehler"}

        functions = []
        missing_hints = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                functions.append(node.name)

                # Prüfe Return-Type
                if node.returns is None and node.name != "__init__":
                    missing_hints.append(f"Funktion '{node.name}' ohne Return-Type")

                # Prüfe Parameter-Types
                for arg in node.args.args:
                    if arg.annotation is None and arg.arg != "self":
                        missing_hints.append(f"Parameter '{arg.arg}' in '{node.name}' ohne Type-Hint")

        if missing_hints:
            return {
                "name": "type_hints",
                "status": "failed",
                "message": f"{len(missing_hints)} fehlende Type-Hints: {missing_hints[:3]}"
            }

        return {"name": "type_hints", "status": "passed"}

    def _check_german_messages(self, code: str, path: str, context: Dict) -> Dict:
        """Prüft auf englische User-Facing Strings."""
        english_patterns = [
            r'"Error\s*:',
            r'"Warning\s*:',
            r'"Success\s*:',
            r'"Failed\s*:',
            r'"Invalid\s*:',
            r'"Not found"',
            r'"Unauthorized"',
            r'"Forbidden"',
            r'"Bad request"',
            r'"Internal server error"',
        ]

        found_english = []

        for pattern in english_patterns:
            matches = re.finditer(pattern, code, re.IGNORECASE)
            for match in matches:
                # Prüfe ob es in einem Kommentar oder Docstring ist
                line_start = code.rfind('\n', 0, match.start()) + 1
                line = code[line_start:code.find('\n', match.start())]

                if not (line.strip().startswith('#') or '"""' in line or "'''" in line):
                    found_english.append(match.group())

        if found_english:
            return {
                "name": "german_messages",
                "status": "failed",
                "message": f"Englische Texte gefunden: {found_english[:3]}"
            }

        return {"name": "german_messages", "status": "passed"}

    def _check_gpu_patterns(self, code: str, path: str, context: Dict) -> Dict:
        """Prüft GPU-Management Patterns."""
        gpu_usage_patterns = [
            r'\.cuda\(\)',
            r'torch\.cuda',
            r'device\s*=\s*["\']cuda["\']',
            r'to\(["\']cuda["\']\)',
        ]

        has_gpu_usage = any(re.search(pattern, code) for pattern in gpu_usage_patterns)

        if has_gpu_usage:
            # Prüfe auf gpu_memory_guard
            if 'gpu_memory_guard' not in code:
                return {
                    "name": "gpu_patterns",
                    "status": "warning",
                    "message": "GPU-Nutzung ohne gpu_memory_guard Context Manager"
                }

            # Prüfe auf VRAM-Limits
            if 'vram' not in code.lower() and '16gb' not in code.lower():
                return {
                    "name": "gpu_patterns",
                    "status": "warning",
                    "message": "GPU-Code ohne VRAM-Limit Berücksichtigung"
                }

        return {"name": "gpu_patterns", "status": "passed"}

    def _check_security_patterns(self, code: str, path: str, context: Dict) -> Dict:
        """Prüft Sicherheits-Anti-Patterns."""
        dangerous_patterns = [
            (r'\beval\s*\(', 'eval() ist gefährlich'),
            (r'\bexec\s*\(', 'exec() ist gefährlich'),
            (r'shell\s*=\s*True', 'shell=True vermeiden'),
            (r'subprocess\.call\([^)]*shell\s*=\s*True', 'subprocess mit shell=True'),
            (r'os\.system\s*\(', 'os.system() ist unsicher'),
            (r'pickle\.loads?\s*\(', 'pickle.load() kann unsicher sein'),
        ]

        found_issues = []

        for pattern, message in dangerous_patterns:
            if re.search(pattern, code):
                # Prüfe ob es in einem Kommentar ist
                matches = re.finditer(pattern, code)
                for match in matches:
                    line_start = code.rfind('\n', 0, match.start()) + 1
                    line = code[line_start:code.find('\n', match.start())]

                    if not line.strip().startswith('#'):
                        found_issues.append(message)
                        break

        if found_issues:
            return {
                "name": "security",
                "status": "failed",
                "message": f"Sicherheitsprobleme: {', '.join(found_issues)}"
            }

        # Prüfe auf Secrets im Code
        secret_patterns = [
            r'password\s*=\s*["\'][^"\']+["\']',
            r'api_key\s*=\s*["\'][^"\']+["\']',
            r'secret\s*=\s*["\'][^"\']+["\']',
            r'token\s*=\s*["\'][^"\']+["\']',
        ]

        for pattern in secret_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                return {
                    "name": "security",
                    "status": "failed",
                    "message": "Mögliche Secrets im Code gefunden"
                }

        return {"name": "security", "status": "passed"}

    def _check_imports(self, code: str, path: str, context: Dict) -> Dict:
        """Prüft Import-Sortierung und -Struktur."""
        if not path.endswith('.py'):
            return {"name": "imports", "status": "passed"}

        lines = code.split('\n')
        import_lines = []

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('import ') or stripped.startswith('from '):
                import_lines.append((i, stripped))

        if not import_lines:
            return {"name": "imports", "status": "passed"}

        # Einfache Checks
        issues = []

        # Prüfe auf relative Imports vor absoluten
        has_relative = False
        has_absolute_after_relative = False

        for _, import_line in import_lines:
            if import_line.startswith('from .'):
                has_relative = True
            elif has_relative and import_line.startswith('import '):
                has_absolute_after_relative = True

        if has_absolute_after_relative:
            issues.append("Absolute Imports nach relativen Imports")

        # Prüfe auf doppelte Imports
        import_modules = set()
        for _, import_line in import_lines:
            if import_line in import_modules:
                issues.append("Doppelte Imports gefunden")
            import_modules.add(import_line)

        if issues:
            return {
                "name": "imports",
                "status": "warning",
                "message": f"Import-Probleme: {', '.join(issues)}"
            }

        return {"name": "imports", "status": "passed"}

    def get_quality_report(self, result: QualityResult) -> str:
        """
        Generiert einen formatierten Quality-Report.

        Args:
            result: QualityResult

        Returns:
            Formatierter Report
        """
        report = f"""
🔍 Quality Gate Report:

Status: {result.level.value.upper()}
Eskalation erforderlich: {'Ja' if result.should_escalate else 'Nein'}
"""

        if result.escalation_reason:
            report += f"Eskalationsgrund: {result.escalation_reason}\n"

        if result.checks_passed:
            report += f"\n✅ Bestanden ({len(result.checks_passed)}):\n"
            for check in result.checks_passed:
                report += f"  - {check}\n"

        if result.warnings:
            report += f"\n⚠️  Warnungen ({len(result.warnings)}):\n"
            for warning in result.warnings:
                report += f"  - {warning}\n"

        if result.checks_failed:
            report += f"\n❌ Fehlgeschlagen ({len(result.checks_failed)}):\n"
            for failed in result.checks_failed:
                report += f"  - {failed}\n"

        return report.strip()
