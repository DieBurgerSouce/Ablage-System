"""
Shared File Protocol for Team Workflow System

Manages coordination around 4 critical bottleneck files that must NEVER be edited in parallel:
- app/main.py (1978 lines, 175 routers, HOCH risk)
- app/db/models.py (18467 lines, 314 services, KRITISCH risk)
- app/workers/celery_app.py (3284 lines, all tasks, MITTEL risk)
- app/workers/tasks/__init__.py (215 lines, all consumers, NIEDRIG risk)

Architecture:
- Agents work in parallel-safe zones (services, models_*, tasks/*_tasks.py)
- Phase 6 coordinator handles bottleneck integration sequentially
- Manifest-based integration prevents conflicts
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import re


class RiskLevel(str, Enum):
    """Risk level für Bottleneck-Dateien"""
    NIEDRIG = "niedrig"
    MITTEL = "mittel"
    HOCH = "hoch"
    KRITISCH = "kritisch"


class IntegrationStrategy(str, Enum):
    """Strategie für Integration in Bottleneck-Dateien"""
    APPEND_ONLY = "append_only"  # Nur am Ende hinzufügen
    SATELLITE_IMPORT = "satellite_import"  # Import aus Satellit-Datei


@dataclass
class BottleneckFile:
    """
    Represents a critical file that must be coordinated.

    Attributes:
        path: Relative path from project root
        risk_level: Impact of conflicts
        line_count: Current size (for monitoring growth)
        dependency_count: Number of services/routers/tasks depending on it
        strategy: How to safely integrate changes
    """
    path: str
    risk_level: RiskLevel
    line_count: int
    dependency_count: int
    strategy: IntegrationStrategy


# Die 4 kritischen Bottleneck-Dateien
BOTTLENECK_FILES: Dict[str, BottleneckFile] = {
    "app/main.py": BottleneckFile(
        path="app/main.py",
        risk_level=RiskLevel.HOCH,
        line_count=1978,
        dependency_count=175,  # 175 routers
        strategy=IntegrationStrategy.APPEND_ONLY
    ),
    "app/db/models.py": BottleneckFile(
        path="app/db/models.py",
        risk_level=RiskLevel.KRITISCH,
        line_count=18467,
        dependency_count=314,  # 314 services
        strategy=IntegrationStrategy.SATELLITE_IMPORT
    ),
    "app/workers/celery_app.py": BottleneckFile(
        path="app/workers/celery_app.py",
        risk_level=RiskLevel.MITTEL,
        line_count=3284,
        dependency_count=50,  # Alle Task-Module
        strategy=IntegrationStrategy.APPEND_ONLY
    ),
    "app/workers/tasks/__init__.py": BottleneckFile(
        path="app/workers/tasks/__init__.py",
        risk_level=RiskLevel.NIEDRIG,
        line_count=215,
        dependency_count=30,  # Alle Task-Consumer
        strategy=IntegrationStrategy.APPEND_ONLY
    )
}


@dataclass
class RouterImport:
    """Router registration für app/main.py"""
    import_path: str  # z.B. "app.api.v1.banking.accounts"
    router_var: str   # z.B. "router"
    prefix: str       # z.B. "/api/v1/banking/accounts"


@dataclass
class ModelImport:
    """Model import für app/db/models.py (Satellite-Import Pattern)"""
    import_path: str  # z.B. "app.db.models_banking_connection"
    comment: str      # z.B. "# Banking PSD2 Connection Models"


@dataclass
class TaskModule:
    """Task module registration für celery_app.py"""
    module_path: str         # z.B. "app.workers.tasks.banking_psd2_tasks"
    beat_schedule_var: Optional[str] = None  # z.B. "BANKING_PSD2_BEAT_SCHEDULE"


@dataclass
class TaskExport:
    """Task export für tasks/__init__.py"""
    module_name: str              # z.B. "banking_psd2_tasks"
    task_names: List[str]         # z.B. ["refresh_token", "sync_accounts"]
    beat_schedule_var: Optional[str] = None  # z.B. "BANKING_PSD2_BEAT_SCHEDULE"


@dataclass
class RegistrationManifest:
    """
    Manifest of all changes that need to be integrated into bottleneck files.

    Created by agents in parallel-safe zones, consumed by Phase 6 coordinator.
    """
    router_imports: List[RouterImport] = field(default_factory=list)
    model_imports: List[ModelImport] = field(default_factory=list)
    task_modules: List[TaskModule] = field(default_factory=list)
    task_exports: List[TaskExport] = field(default_factory=list)


@dataclass
class ParallelZone:
    """
    A zone where agents can work in parallel without conflicts.

    Attributes:
        name: Zone identifier (A, B, C, D)
        file_patterns: Glob patterns with {module}/{feature} placeholders
        description: What this zone is for
    """
    name: str
    file_patterns: List[str]
    description: str


# Die 4 parallelen Zonen für konfliktfreies Arbeiten
PARALLEL_SAFE_ZONES: List[ParallelZone] = [
    ParallelZone(
        name="Zone A",
        file_patterns=[
            "app/services/{module}/*.py",
            "app/api/v1/{module}.py",
            "app/api/v1/{module}/*.py",
            "tests/unit/services/{module}/*.py",
            "tests/integration/test_{module}_*.py"
        ],
        description="Services, API endpoints, und Tests - voll parallel-sicher"
    ),
    ParallelZone(
        name="Zone B",
        file_patterns=[
            "app/db/models_{feature}.py"
        ],
        description="Satellite Model Files - isoliert von models.py"
    ),
    ParallelZone(
        name="Zone C",
        file_patterns=[
            "app/workers/tasks/{feature}_tasks.py"
        ],
        description="Feature-specific Celery Tasks - isoliert von celery_app.py"
    ),
    ParallelZone(
        name="Zone D",
        file_patterns=[
            "frontend/src/features/{module}/*.tsx",
            "frontend/src/features/{module}/*.ts",
            "frontend/src/app/routes/{module}.*.tsx"
        ],
        description="Frontend Features und Routes - voll parallel-sicher"
    )
]


@dataclass
class ValidationResult:
    """
    Result of validating agent file assignments.

    Attributes:
        is_valid: Whether all files are in parallel-safe zones
        violations: Critical errors (bottleneck file conflicts)
        warnings: Non-critical issues (best practices)
    """
    is_valid: bool
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class SharedFileProtocol:
    """
    Manages coordination around bottleneck files.

    Responsibilities:
    - Identify bottleneck files
    - Validate parallel-safe zone assignments
    - Merge manifests from multiple agents
    - Generate integration instructions for Phase 6
    """

    def __init__(self) -> None:
        """Initialize protocol with current bottleneck state."""
        self.bottlenecks = BOTTLENECK_FILES
        self.zones = PARALLEL_SAFE_ZONES

    def is_bottleneck(self, file_path: str) -> bool:
        """
        Check if a file path is a critical bottleneck.

        Args:
            file_path: Relative path from project root

        Returns:
            True if file is a bottleneck that requires coordination
        """
        # Normalize path separators
        normalized = file_path.replace("\\", "/")
        return normalized in self.bottlenecks

    def is_parallel_safe(self, file_path: str, module_name: str) -> bool:
        """
        Check if a file is in a parallel-safe zone.

        Args:
            file_path: Relative path from project root
            module_name: Module/feature name for pattern matching

        Returns:
            True if file can be edited in parallel
        """
        normalized = file_path.replace("\\", "/")

        for zone in self.zones:
            for pattern in zone.file_patterns:
                # Replace placeholders
                regex_pattern = pattern.replace("{module}", module_name)
                regex_pattern = regex_pattern.replace("{feature}", module_name)

                # Convert glob pattern to regex
                regex_pattern = regex_pattern.replace("*", "[^/]+")
                regex_pattern = f"^{regex_pattern}$"

                if re.match(regex_pattern, normalized):
                    return True

        return False

    def validate_zone_assignment(
        self,
        agent_role: str,
        files: List[str],
        module_name: str = "unknown"
    ) -> ValidationResult:
        """
        Validate that an agent's file assignments are conflict-free.

        Args:
            agent_role: Agent's role (e.g., "coder", "reviewer")
            files: List of file paths assigned to agent
            module_name: Module/feature name for zone validation

        Returns:
            ValidationResult with violations and warnings
        """
        violations: List[str] = []
        warnings: List[str] = []

        for file_path in files:
            # Check for bottleneck violations
            if self.is_bottleneck(file_path):
                bottleneck = self.bottlenecks[file_path.replace("\\", "/")]
                violations.append(
                    f"VIOLATION: {agent_role} assigned bottleneck file '{file_path}' "
                    f"({bottleneck.risk_level.value} risk, {bottleneck.dependency_count} dependencies). "
                    f"This file MUST be handled in Phase 6 by coordinator."
                )

            # Check if in parallel-safe zone
            elif not self.is_parallel_safe(file_path, module_name):
                warnings.append(
                    f"WARNING: {agent_role} assigned '{file_path}' which is not in a known parallel-safe zone. "
                    f"Verify this is intentional."
                )

        return ValidationResult(
            is_valid=len(violations) == 0,
            violations=violations,
            warnings=warnings
        )

    def merge_manifests(self, manifests: List[RegistrationManifest]) -> RegistrationManifest:
        """
        Merge multiple registration manifests into one.

        Args:
            manifests: List of manifests from different agents

        Returns:
            Combined manifest with duplicates removed
        """
        merged = RegistrationManifest()

        # Track seen items to avoid duplicates
        seen_routers: Set[Tuple[str, str, str]] = set()
        seen_models: Set[str] = set()
        seen_task_modules: Set[str] = set()
        seen_task_exports: Set[Tuple[str, Tuple[str, ...]]] = set()

        for manifest in manifests:
            # Merge router imports
            for router in manifest.router_imports:
                key = (router.import_path, router.router_var, router.prefix)
                if key not in seen_routers:
                    merged.router_imports.append(router)
                    seen_routers.add(key)

            # Merge model imports
            for model in manifest.model_imports:
                if model.import_path not in seen_models:
                    merged.model_imports.append(model)
                    seen_models.add(model.import_path)

            # Merge task modules
            for task_module in manifest.task_modules:
                if task_module.module_path not in seen_task_modules:
                    merged.task_modules.append(task_module)
                    seen_task_modules.add(task_module.module_path)

            # Merge task exports
            for task_export in manifest.task_exports:
                key = (task_export.module_name, tuple(task_export.task_names))
                if key not in seen_task_exports:
                    merged.task_exports.append(task_export)
                    seen_task_exports.add(key)

        return merged

    def generate_integration_instructions(self, manifest: RegistrationManifest) -> str:
        """
        Generate human-readable integration instructions for Phase 6 coordinator.

        Args:
            manifest: Combined manifest from all agents

        Returns:
            Formatted instructions as string
        """
        instructions: List[str] = [
            "=" * 80,
            "PHASE 6 INTEGRATION INSTRUCTIONS",
            "=" * 80,
            "",
            "The following changes must be integrated into bottleneck files SEQUENTIALLY.",
            "DO NOT edit these files in parallel!",
            ""
        ]

        # Router registrations (app/main.py)
        if manifest.router_imports:
            instructions.extend([
                "=" * 80,
                "1. ROUTER REGISTRATIONS (app/main.py)",
                "=" * 80,
                "",
                "Add the following imports at the top of app/main.py:",
                ""
            ])

            for router in manifest.router_imports:
                instructions.append(f"from {router.import_path} import {router.router_var}")

            instructions.extend([
                "",
                "Add the following router registrations in the create_application() function:",
                ""
            ])

            for router in manifest.router_imports:
                instructions.append(
                    f'app.include_router({router.router_var}, prefix="{router.prefix}", tags=["{router.prefix.split("/")[-1]}"])'
                )

            instructions.append("")

        # Model imports (app/db/models.py)
        if manifest.model_imports:
            instructions.extend([
                "=" * 80,
                "2. MODEL IMPORTS (app/db/models.py - SATELLITE PATTERN)",
                "=" * 80,
                "",
                "Add the following imports to app/db/models.py:",
                ""
            ])

            for model in manifest.model_imports:
                instructions.append(f"{model.comment}")
                instructions.append(f"from {model.import_path} import *")
                instructions.append("")

        # Task module registrations (app/workers/celery_app.py)
        if manifest.task_modules:
            instructions.extend([
                "=" * 80,
                "3. TASK MODULE REGISTRATIONS (app/workers/celery_app.py)",
                "=" * 80,
                "",
                "Add the following imports at the top:",
                ""
            ])

            for task_module in manifest.task_modules:
                instructions.append(f"from {task_module.module_path} import *")
                if task_module.beat_schedule_var:
                    instructions.append(f"from {task_module.module_path} import {task_module.beat_schedule_var}")

            instructions.extend([
                "",
                "Update the beat_schedule dict by merging the following:",
                ""
            ])

            for task_module in manifest.task_modules:
                if task_module.beat_schedule_var:
                    instructions.append(f"celery_app.conf.beat_schedule.update({task_module.beat_schedule_var})")

            instructions.append("")

        # Task exports (app/workers/tasks/__init__.py)
        if manifest.task_exports:
            instructions.extend([
                "=" * 80,
                "4. TASK EXPORTS (app/workers/tasks/__init__.py)",
                "=" * 80,
                "",
                "Add the following imports and exports:",
                ""
            ])

            for export in manifest.task_exports:
                instructions.append(f"from .{export.module_name} import (")
                for task_name in export.task_names:
                    instructions.append(f"    {task_name},")
                instructions.append(")")

                if export.beat_schedule_var:
                    instructions.append(f"from .{export.module_name} import {export.beat_schedule_var}")

                instructions.append("")

            instructions.extend([
                "Add to __all__:",
                ""
            ])

            for export in manifest.task_exports:
                for task_name in export.task_names:
                    instructions.append(f'    "{task_name}",')

            instructions.append("")

        # Final notes
        instructions.extend([
            "=" * 80,
            "INTEGRATION CHECKLIST",
            "=" * 80,
            "",
            "[ ] All imports added to bottleneck files",
            "[ ] All registrations added in correct order",
            "[ ] No syntax errors (run: ruff check .)",
            "[ ] No type errors (run: mypy app/)",
            "[ ] All tests passing (run: pytest tests/unit/ -v)",
            "[ ] Commit changes with message: 'feat: integrate [feature] (Phase 6)'",
            "",
            "=" * 80
        ])

        return "\n".join(instructions)


# Convenience functions für direkten Import
def is_bottleneck_file(file_path: str) -> bool:
    """Check if file is a critical bottleneck."""
    protocol = SharedFileProtocol()
    return protocol.is_bottleneck(file_path)


def validate_agent_files(agent_role: str, files: List[str], module_name: str = "unknown") -> ValidationResult:
    """Validate agent's file assignments."""
    protocol = SharedFileProtocol()
    return protocol.validate_zone_assignment(agent_role, files, module_name)


def merge_agent_manifests(manifests: List[RegistrationManifest]) -> RegistrationManifest:
    """Merge manifests from multiple agents."""
    protocol = SharedFileProtocol()
    return protocol.merge_manifests(manifests)


def generate_phase6_instructions(manifest: RegistrationManifest) -> str:
    """Generate Phase 6 integration instructions."""
    protocol = SharedFileProtocol()
    return protocol.generate_integration_instructions(manifest)
