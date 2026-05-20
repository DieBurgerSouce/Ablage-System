"""
Quality Gates fuer Team-Workflow.

6 Quality Gates die zwischen Phasen pruefen:
- Gate 1: Research Complete
- Gate 2: Design Approved
- Gate 3: Code Quality
- Gate 4: Tests Passing
- Gate 5: Review Approved
- Gate 6: Integration Clean
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Protocol, Union, runtime_checkable
from pathlib import Path

from .shared_file_protocol import BOTTLENECK_FILES as _BOTTLENECK_FILES


class GateStatus(Enum):
    """Status eines Quality Gates."""
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"


class CheckSeverity(Enum):
    """Schweregrad eines Check-Ergebnisses."""
    BLOCK = "BLOCK"
    WARN = "WARN"
    INFO = "INFO"


@runtime_checkable
class GateProtocol(Protocol):
    """Protocol fuer alle Quality Gates."""

    def check(self, **kwargs: object) -> "GateResult": ...


@dataclass
class CheckResult:
    """Ergebnis eines einzelnen Checks."""
    name: str
    passed: bool
    severity: CheckSeverity
    message: str
    details: Optional[str] = None


@dataclass
class GateResult:
    """Ergebnis eines Quality Gates."""
    gate_name: str
    gate_number: int
    status: GateStatus
    checks: List[CheckResult] = field(default_factory=list)
    summary: str = ""

    @property
    def blocks(self) -> List[CheckResult]:
        """Gibt alle BLOCK-Findings zurueck."""
        return [c for c in self.checks if c.severity == CheckSeverity.BLOCK and not c.passed]

    @property
    def warnings(self) -> List[CheckResult]:
        """Gibt alle WARN-Findings zurueck."""
        return [c for c in self.checks if c.severity == CheckSeverity.WARN and not c.passed]

    @property
    def infos(self) -> List[CheckResult]:
        """Gibt alle INFO-Findings zurueck."""
        return [c for c in self.checks if c.severity == CheckSeverity.INFO]

    def format_report(self) -> str:
        """Formatiert den Gate-Report."""
        lines = [
            f"Quality Gate {self.gate_number}: {self.gate_name}",
            f"Status: {self.status.value.upper()}",
            "",
        ]

        if self.blocks:
            lines.append(f"BLOCK ({len(self.blocks)}):")
            for check in self.blocks:
                lines.append(f"  - {check.name}: {check.message}")
                if check.details:
                    lines.append(f"    Details: {check.details}")

        if self.warnings:
            lines.append(f"WARN ({len(self.warnings)}):")
            for check in self.warnings:
                lines.append(f"  - {check.name}: {check.message}")

        passed = [c for c in self.checks if c.passed]
        if passed:
            lines.append(f"PASSED ({len(passed)}):")
            for check in passed:
                lines.append(f"  - {check.name}")

        return "\n".join(lines)


class Gate1ResearchComplete:
    """Gate 1: Research-Phase abgeschlossen."""

    def check(self, research_output: str, affected_files: List[str]) -> GateResult:
        """Prueft ob Research vollstaendig ist."""
        checks: List[CheckResult] = []

        # Check: Betroffene Files identifiziert
        has_files = len(affected_files) > 0 or re.search(
            r"(app/|tests/|frontend/)", research_output
        )
        checks.append(CheckResult(
            name="files_identified",
            passed=bool(has_files),
            severity=CheckSeverity.BLOCK,
            message="Betroffene Files identifiziert" if has_files
            else "Keine betroffenen Files identifiziert",
        ))

        # Check: Bestehende Patterns gefunden
        has_patterns = bool(re.search(
            r"(File:Line|\w+\.py:\d+|bestehend|pattern|muster)", research_output, re.IGNORECASE
        ))
        checks.append(CheckResult(
            name="patterns_found",
            passed=has_patterns,
            severity=CheckSeverity.WARN,
            message="Bestehende Patterns dokumentiert" if has_patterns
            else "Keine bestehenden Patterns referenziert",
        ))

        # Check: Modul-Kopplung bestimmt
        has_coupling = bool(re.search(
            r"(M[123]|isoliert|gekoppelt|shared|kopplung)", research_output, re.IGNORECASE
        ))
        checks.append(CheckResult(
            name="coupling_determined",
            passed=has_coupling,
            severity=CheckSeverity.WARN,
            message="Modul-Kopplung bestimmt" if has_coupling
            else "Modul-Kopplung nicht bestimmt",
        ))

        blocks = [c for c in checks if c.severity == CheckSeverity.BLOCK and not c.passed]
        status = GateStatus.FAILED if blocks else (
            GateStatus.WARNING if any(not c.passed for c in checks) else GateStatus.PASSED
        )

        return GateResult(
            gate_name="Research Complete",
            gate_number=1,
            status=status,
            checks=checks,
            summary=f"{len([c for c in checks if c.passed])}/{len(checks)} Checks bestanden",
        )


class Gate2DesignApproved:
    """Gate 2: Design-Phase abgeschlossen."""

    def check(self, design_output: str) -> GateResult:
        """Prueft ob Design vollstaendig ist."""
        checks: List[CheckResult] = []

        # Check: Datenmodell definiert
        has_model = bool(re.search(
            r"(model|tabelle|field|column|relationship|datenmodell)",
            design_output, re.IGNORECASE
        ))
        checks.append(CheckResult(
            name="data_model",
            passed=has_model,
            severity=CheckSeverity.BLOCK,
            message="Datenmodell definiert" if has_model
            else "Kein Datenmodell definiert",
        ))

        # Check: API-Contract definiert
        has_api = bool(re.search(
            r"(endpoint|api|route|GET|POST|PUT|PATCH|DELETE|schema)",
            design_output, re.IGNORECASE
        ))
        checks.append(CheckResult(
            name="api_contract",
            passed=has_api,
            severity=CheckSeverity.BLOCK,
            message="API-Contract definiert" if has_api
            else "Kein API-Contract definiert",
        ))

        # Check: Keine Any-Types
        has_any = bool(re.search(r"\bAny\b", design_output))
        checks.append(CheckResult(
            name="no_any_types",
            passed=not has_any,
            severity=CheckSeverity.BLOCK,
            message="Keine Any-Types im Design" if not has_any
            else "Any-Types im Design gefunden",
        ))

        # Check: Satellite-Model-Strategie
        has_satellite = bool(re.search(
            r"(satellite|models_|eigene.*model|separate.*model)",
            design_output, re.IGNORECASE
        ))
        checks.append(CheckResult(
            name="satellite_strategy",
            passed=has_satellite,
            severity=CheckSeverity.WARN,
            message="Satellite-Model-Strategie definiert" if has_satellite
            else "Keine Satellite-Model-Strategie",
        ))

        blocks = [c for c in checks if c.severity == CheckSeverity.BLOCK and not c.passed]
        status = GateStatus.FAILED if blocks else (
            GateStatus.WARNING if any(not c.passed for c in checks) else GateStatus.PASSED
        )

        return GateResult(
            gate_name="Design Approved",
            gate_number=2,
            status=status,
            checks=checks,
        )


class Gate3CodeQuality:
    """Gate 3: Code-Qualitaet."""

    def check(self, code_output: str, files_changed: List[str]) -> GateResult:
        """Prueft Code-Qualitaet."""
        checks: List[CheckResult] = []

        # Check: Keine Any-Types in Code
        any_count = len(re.findall(r"\bAny\b", code_output))
        # Erlaubt in Imports und Type-Ignores
        import_any = len(re.findall(r"from typing import.*\bAny\b", code_output))
        real_any = any_count - import_any
        checks.append(CheckResult(
            name="no_any_types",
            passed=real_any <= 0,
            severity=CheckSeverity.BLOCK,
            message=f"Keine Any-Types im Code" if real_any <= 0
            else f"{real_any} Any-Types gefunden",
        ))

        # Check: Deutsche User-Facing Strings (only match string literals, not comments)
        english_errors = re.findall(
            r'["\'](?:Error|Warning|Success|Failed|Invalid|Not found|Unauthorized|'
            r'Forbidden|Bad request|Internal server error)[:\s]',
            code_output, re.IGNORECASE
        )
        checks.append(CheckResult(
            name="german_strings",
            passed=len(english_errors) == 0,
            severity=CheckSeverity.BLOCK,
            message="Alle User-Facing Strings auf Deutsch" if not english_errors
            else f"Englische Strings gefunden: {english_errors[:3]}",
        ))

        # Check: Kein PII-Logging
        pii_patterns = [
            r"log.*customer.*number",
            r"log.*kundennummer",
            r"log.*iban",
            r"log.*vat.?id",
            r"logger\.(info|debug|warning|error).*iban",
            r"logger\.(info|debug|warning|error).*kundennr",
        ]
        pii_found = any(
            re.search(p, code_output, re.IGNORECASE) for p in pii_patterns
        )
        checks.append(CheckResult(
            name="no_pii_logging",
            passed=not pii_found,
            severity=CheckSeverity.BLOCK,
            message="Kein PII-Logging" if not pii_found
            else "PII-Logging gefunden (Kundennr, IBAN, VAT-ID)",
        ))

        # Check: Keine Cloud-Dependencies
        cloud_patterns = [
            r"import boto3",
            r"from google\.cloud",
            r"from azure\.",
            r"aws_access_key",
        ]
        cloud_found = any(
            re.search(p, code_output, re.IGNORECASE) for p in cloud_patterns
        )
        checks.append(CheckResult(
            name="no_cloud_deps",
            passed=not cloud_found,
            severity=CheckSeverity.BLOCK,
            message="Keine Cloud-Dependencies" if not cloud_found
            else "Cloud-Dependencies gefunden (On-Premises Only!)",
        ))

        # Check: Type Hints vorhanden (return annotations + parameter annotations)
        all_functions = re.findall(
            r"def \w+\([^)]*\)\s*(?:->.*?)?:", code_output
        )
        functions_with_return = re.findall(
            r"def \w+\([^)]*\)\s*->\s*\w", code_output
        )
        # Check parameter annotations: params with ": type" syntax
        param_blocks = re.findall(r"def \w+\(([^)]*)\)", code_output)
        annotated_params = 0
        total_params = 0
        for block in param_blocks:
            params = [p.strip() for p in block.split(",") if p.strip()]
            for param in params:
                name = param.split("=")[0].strip().split(":")[0].strip()
                if name in ("self", "cls", "*", "**"):
                    continue
                total_params += 1
                if ":" in param.split("=")[0]:
                    annotated_params += 1
        return_ratio = (
            len(functions_with_return) / max(len(all_functions), 1)
        )
        param_ratio = annotated_params / max(total_params, 1)
        hint_ratio = (return_ratio + param_ratio) / 2
        checks.append(CheckResult(
            name="type_hints",
            passed=hint_ratio >= 0.8,
            severity=CheckSeverity.WARN,
            message=f"Type Hints: {hint_ratio:.0%} (returns: {return_ratio:.0%}, params: {param_ratio:.0%})"
            if hint_ratio >= 0.8
            else f"Unzureichende Type Hints: {hint_ratio:.0%} (returns: {return_ratio:.0%}, params: {param_ratio:.0%})",
        ))

        blocks = [c for c in checks if c.severity == CheckSeverity.BLOCK and not c.passed]
        status = GateStatus.FAILED if blocks else (
            GateStatus.WARNING if any(not c.passed for c in checks) else GateStatus.PASSED
        )

        return GateResult(
            gate_name="Code Quality",
            gate_number=3,
            status=status,
            checks=checks,
        )


class Gate4TestsPassing:
    """Gate 4: Tests bestehen."""

    def check(
        self,
        test_output: str,
        test_files: List[str],
    ) -> GateResult:
        """Prueft Test-Qualitaet."""
        checks: List[CheckResult] = []

        # Check: Tests nicht im Root-Ordner
        root_tests = [
            f for f in test_files
            if re.match(r"^tests?/test_", f) or re.match(r"^test_", f)
        ]
        checks.append(CheckResult(
            name="tests_not_in_root",
            passed=len(root_tests) == 0,
            severity=CheckSeverity.BLOCK,
            message="Tests korrekt organisiert" if not root_tests
            else f"Tests im Root-Ordner: {root_tests[:3]}",
        ))

        # Check: Pytest-Marker vorhanden
        has_markers = bool(re.search(
            r"@pytest\.mark\.(unit|asyncio|integration)",
            test_output
        ))
        checks.append(CheckResult(
            name="pytest_markers",
            passed=has_markers,
            severity=CheckSeverity.WARN,
            message="Pytest-Marker vorhanden" if has_markers
            else "Fehlende Pytest-Marker (@pytest.mark.unit, @pytest.mark.asyncio)",
        ))

        # Check: Tests in richtigen Verzeichnissen
        correct_paths = all(
            re.search(r"tests/(unit|integration)/", f) for f in test_files
        ) if test_files else True
        checks.append(CheckResult(
            name="test_organization",
            passed=correct_paths,
            severity=CheckSeverity.WARN,
            message="Tests korrekt in tests/unit/ oder tests/integration/"
            if correct_paths
            else "Tests nicht in korrekten Verzeichnissen",
        ))

        # Check: Bestehende Tests nicht geaendert (heuristisch)
        modified_existing = bool(re.search(
            r"(modified|geaendert|updated).*existing.*test",
            test_output, re.IGNORECASE
        ))
        checks.append(CheckResult(
            name="existing_tests_unchanged",
            passed=not modified_existing,
            severity=CheckSeverity.WARN,
            message="Bestehende Tests unveraendert" if not modified_existing
            else "Bestehende Tests wurden moeglicherweise geaendert",
        ))

        blocks = [c for c in checks if c.severity == CheckSeverity.BLOCK and not c.passed]
        status = GateStatus.FAILED if blocks else (
            GateStatus.WARNING if any(not c.passed for c in checks) else GateStatus.PASSED
        )

        return GateResult(
            gate_name="Tests Passing",
            gate_number=4,
            status=status,
            checks=checks,
        )


class Gate5ReviewApproved:
    """Gate 5: Review bestanden."""

    def check(self, review_output: str, code_output: str) -> GateResult:
        """Prueft Review-Ergebnis."""
        checks: List[CheckResult] = []

        # Check: Keine Circular Imports
        circular = bool(re.search(
            r"circular.*import|import.*circular|zirkulaer",
            review_output, re.IGNORECASE
        ))
        checks.append(CheckResult(
            name="no_circular_imports",
            passed=not circular,
            severity=CheckSeverity.BLOCK,
            message="Keine Circular Imports" if not circular
            else "Circular Imports erkannt",
        ))

        # Check: Auth-Dependencies
        has_auth_issue = bool(re.search(
            r"(missing|fehlend).*auth|no.*auth.*depend|ohne.*authentifizierung",
            review_output, re.IGNORECASE
        ))
        checks.append(CheckResult(
            name="auth_dependencies",
            passed=not has_auth_issue,
            severity=CheckSeverity.BLOCK,
            message="Auth-Dependencies vorhanden" if not has_auth_issue
            else "Fehlende Auth-Dependencies auf Endpoints",
        ))

        # Check: JSONB-Keys whitelisted (CWE-89)
        jsonb_issue = bool(re.search(
            r"(jsonb|json).*(?:unsanitized|unvalidated|nicht.*validiert|injection)",
            review_output, re.IGNORECASE
        ))
        checks.append(CheckResult(
            name="jsonb_whitelist",
            passed=not jsonb_issue,
            severity=CheckSeverity.BLOCK,
            message="JSONB-Keys validiert (CWE-89)" if not jsonb_issue
            else "JSONB-Keys nicht whitelisted (CWE-89 Risiko)",
        ))

        # Check: HTTP Headers sanitized (CWE-113)
        header_issue = bool(re.search(
            r"(header|crlf).*(?:unsanitized|injection|nicht.*sanitized)",
            review_output, re.IGNORECASE
        ))
        checks.append(CheckResult(
            name="headers_sanitized",
            passed=not header_issue,
            severity=CheckSeverity.BLOCK,
            message="HTTP-Headers sanitized (CWE-113)" if not header_issue
            else "HTTP-Headers nicht sanitized (CWE-113 Risiko)",
        ))

        # Check: BLOCK findings in review
        block_count = len(re.findall(r"\bBLOCK\b", review_output))
        checks.append(CheckResult(
            name="no_block_findings",
            passed=block_count == 0,
            severity=CheckSeverity.BLOCK,
            message="Keine BLOCK-Findings im Review" if block_count == 0
            else f"{block_count} BLOCK-Finding(s) im Review",
        ))

        blocks = [c for c in checks if c.severity == CheckSeverity.BLOCK and not c.passed]
        status = GateStatus.FAILED if blocks else (
            GateStatus.WARNING if any(not c.passed for c in checks) else GateStatus.PASSED
        )

        return GateResult(
            gate_name="Review Approved",
            gate_number=5,
            status=status,
            checks=checks,
        )


class Gate6IntegrationClean:
    """Gate 6: Shared-File-Integration sauber."""

    SHARED_FILES: List[str] = list(_BOTTLENECK_FILES.keys())

    def check(
        self,
        integration_output: str,
        manifests: List[Dict[str, str]],
    ) -> GateResult:
        """Prueft Shared-File-Integration."""
        checks: List[CheckResult] = []

        # Check: main.py Router registriert
        has_router = bool(re.search(
            r"(include_router|router.*import|main\.py.*registriert)",
            integration_output, re.IGNORECASE
        ))
        checks.append(CheckResult(
            name="main_py_router",
            passed=has_router,
            severity=CheckSeverity.BLOCK,
            message="Router in main.py registriert" if has_router
            else "Router nicht in main.py registriert",
        ))

        # Check: models.py Satellite-Import
        has_model_import = bool(re.search(
            r"(models_\w+|satellite.*import|models\.py.*import)",
            integration_output, re.IGNORECASE
        ))
        needs_model = any(
            "model" in m.get("type", "").lower() for m in manifests
        ) if manifests else False
        checks.append(CheckResult(
            name="models_py_import",
            passed=has_model_import or not needs_model,
            severity=CheckSeverity.BLOCK if needs_model else CheckSeverity.INFO,
            message="Satellite-Import in models.py" if has_model_import
            else "Kein Model-Import noetig" if not needs_model
            else "Satellite-Import fehlt in models.py",
        ))

        # Check: celery_app.py Task-Modul
        has_task_module = bool(re.search(
            r"(celery_app|task.*module|beat.*schedule|autodiscover)",
            integration_output, re.IGNORECASE
        ))
        needs_tasks = any(
            "task" in m.get("type", "").lower() for m in manifests
        ) if manifests else False
        checks.append(CheckResult(
            name="celery_task_module",
            passed=has_task_module or not needs_tasks,
            severity=CheckSeverity.BLOCK if needs_tasks else CheckSeverity.INFO,
            message="Task-Modul in celery_app.py registriert" if has_task_module
            else "Kein Task-Modul noetig" if not needs_tasks
            else "Task-Modul fehlt in celery_app.py",
        ))

        # Check: tasks/__init__.py Re-Exports
        has_reexport = bool(re.search(
            r"(tasks/__init__|re-?export|__all__)",
            integration_output, re.IGNORECASE
        ))
        checks.append(CheckResult(
            name="tasks_init_exports",
            passed=has_reexport or not needs_tasks,
            severity=CheckSeverity.WARN if needs_tasks else CheckSeverity.INFO,
            message="Re-Exports in tasks/__init__.py" if has_reexport
            else "Keine Re-Exports noetig" if not needs_tasks
            else "Re-Exports fehlen in tasks/__init__.py",
        ))

        # Check: Nur Append-Operationen
        has_destructive = bool(re.search(
            r"(removed|deleted|replaced|geloescht|ersetzt)",
            integration_output, re.IGNORECASE
        ))
        checks.append(CheckResult(
            name="append_only",
            passed=not has_destructive,
            severity=CheckSeverity.BLOCK,
            message="Nur Append-Operationen" if not has_destructive
            else "Moeglicherweise destruktive Aenderungen an Shared Files",
        ))

        blocks = [c for c in checks if c.severity == CheckSeverity.BLOCK and not c.passed]
        status = GateStatus.FAILED if blocks else (
            GateStatus.WARNING if any(not c.passed for c in checks) else GateStatus.PASSED
        )

        return GateResult(
            gate_name="Integration Clean",
            gate_number=6,
            status=status,
            checks=checks,
        )


# --- Gate Type Alias ---

GateType = Union[
    Gate1ResearchComplete,
    Gate2DesignApproved,
    Gate3CodeQuality,
    Gate4TestsPassing,
    Gate5ReviewApproved,
    Gate6IntegrationClean,
]


# --- Gate Registry ---

GATES: Dict[str, GateProtocol] = {
    "gate_1_research": Gate1ResearchComplete(),
    "gate_2_design": Gate2DesignApproved(),
    "gate_3_code_quality": Gate3CodeQuality(),
    "gate_4_tests": Gate4TestsPassing(),
    "gate_5_review": Gate5ReviewApproved(),
    "gate_6_integration": Gate6IntegrationClean(),
}


def run_gate(gate_name: str, **kwargs: object) -> GateResult:
    """Fuehrt ein Quality Gate aus.

    Raises:
        KeyError: Wenn der Gate-Name nicht im Registry existiert.
    """
    if gate_name not in GATES:
        raise KeyError(
            f"Gate '{gate_name}' nicht gefunden. "
            f"Verfuegbare Gates: {', '.join(sorted(GATES.keys()))}"
        )
    gate = GATES[gate_name]
    return gate.check(**kwargs)
