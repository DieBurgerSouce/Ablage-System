"""
Team Workflow System fuer Ablage-System.

Wiederverwendbares Multi-Agent-Team-Pattern fuer:
- Code Review + Quality Gates
- Parallele Feature-Entwicklung ohne Shared-File-Konflikte
- Generelles Workflow-Konzept fuer alle Tasks

Klassifiziert Tasks nach Komplexitaet x Kopplung und waehlt
automatisch das passende Team-Template.
"""

import copy
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Tuple


class Complexity(Enum):
    """Task-Komplexitaet basierend auf Datei-Anzahl."""
    C1_TRIVIAL = "c1_trivial"            # 1-2 Files
    C2_CONTAINED = "c2_contained"        # 3-8 Files
    C3_CROSS_CUTTING = "c3_cross_cutting"  # 8-20 Files
    C4_ARCHITECTURE = "c4_architecture"  # 20+ Files


class Coupling(Enum):
    """Modul-Kopplung des Tasks."""
    M1_ISOLATED = "m1_isolated"            # Keine Shared Files
    M2_LIGHT_COUPLED = "m2_light_coupled"  # 1-2 Shared Imports
    M3_SHARED_INFRA = "m3_shared_infra"    # Aenderungen an Bottleneck-Files


class TeamType(Enum):
    """Verfuegbare Team-Templates."""
    NO_TEAM_HAIKU = "no_team_haiku"
    NO_TEAM_SONNET = "no_team_sonnet"
    BUGFIX = "bugfix"
    FEATURE_SMALL = "feature_small"
    FEATURE_STANDARD = "feature_standard"
    FEATURE_FULL = "feature_full"
    REFACTOR = "refactor"
    SECURITY_AUDIT = "security_audit"
    REVIEW = "review"


class PhaseMode(Enum):
    """Ausfuehrungsmodus einer Phase."""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"


@dataclass
class AgentSpec:
    """Spezifikation eines Agents in einer Phase."""
    role: str
    subagent_type: str
    model: str  # haiku, sonnet, opus
    prompt_template: str
    description: str


@dataclass
class Phase:
    """Eine Phase im Team-Workflow."""
    name: str
    number: int
    mode: PhaseMode
    agents: List[AgentSpec]
    gate: Optional[str] = None  # Quality Gate nach dieser Phase
    description: str = ""


@dataclass
class TeamTemplate:
    """Vollstaendiges Team-Template mit allen Phasen."""
    team_type: TeamType
    name: str
    description: str
    phases: List[Phase]
    total_agents: int
    has_parallel_phases: bool
    requires_shared_file_integration: bool

    def get_phase(self, number: int) -> Optional[Phase]:
        """Gibt Phase nach Nummer zurueck."""
        for phase in self.phases:
            if phase.number == number:
                return phase
        return None

    def get_parallel_phases(self) -> List[Phase]:
        """Gibt alle parallelen Phasen zurueck."""
        return [p for p in self.phases if p.mode == PhaseMode.PARALLEL]


@dataclass
class ClassificationInput:
    """Input fuer die Team-Klassifikation."""
    task_description: str
    affected_files: List[str] = field(default_factory=list)
    is_security: bool = False
    is_review_only: bool = False
    explicit_team: Optional[TeamType] = None


@dataclass
class ClassificationOutput:
    """Ergebnis der Team-Klassifikation."""
    team_type: TeamType
    complexity: Complexity
    coupling: Coupling
    confidence: float
    reasoning: str
    template: TeamTemplate
    override_reason: Optional[str] = None


# --- Parallel Safety Zones ---

@dataclass
class SafetyZone:
    """Eine parallel-sichere Zone im Codebase."""
    name: str
    paths: List[str]
    description: str


PARALLEL_SAFE_ZONES: List[SafetyZone] = [
    SafetyZone(
        name="service_module",
        paths=[
            "app/services/{module}/",
            "app/api/v1/{module}.py",
            "tests/unit/services/{module}/",
        ],
        description="Eigenes Service-Modul mit API und Tests",
    ),
    SafetyZone(
        name="satellite_models",
        paths=["app/db/models_{feature}.py"],
        description="Eigene Satellite-Model-Datei pro Feature",
    ),
    SafetyZone(
        name="task_module",
        paths=["app/workers/tasks/{feature}_tasks.py"],
        description="Eigene Task-Datei pro Feature",
    ),
    SafetyZone(
        name="frontend_feature",
        paths=[
            "frontend/src/features/{module}/",
            "frontend/src/app/routes/{module}.*.tsx",
        ],
        description="Eigenes Frontend-Feature-Modul",
    ),
]

# Derived from the single source of truth in shared_file_protocol.py
from .shared_file_protocol import BOTTLENECK_FILES as _BOTTLENECK_FILES

SEQUENTIAL_ONLY_FILES: List[str] = list(_BOTTLENECK_FILES.keys())


# --- Team Templates ---

def _build_bugfix_template() -> TeamTemplate:
    """Template A: Bugfix Team (3-4 Agents, sequentiell)."""
    return TeamTemplate(
        team_type=TeamType.BUGFIX,
        name="Bugfix Team",
        description="Root Cause finden, fixen, testen, reviewen",
        total_agents=4,
        has_parallel_phases=False,
        requires_shared_file_integration=False,
        phases=[
            Phase(
                name="Root Cause Analysis",
                number=1,
                mode=PhaseMode.SEQUENTIAL,
                gate="gate_1_research",
                description="Root Cause finden, betroffene Files identifizieren",
                agents=[AgentSpec(
                    role="researcher",
                    subagent_type="researcher",
                    model="sonnet",
                    prompt_template=(
                        "Analysiere den Bug: {task_description}\n\n"
                        "1. Finde die Root Cause\n"
                        "2. Identifiziere ALLE betroffenen Files (absolute Pfade)\n"
                        "3. Finde aehnliche bestehende Patterns (File:Line)\n"
                        "4. Bestimme Modul-Kopplung (M1/M2/M3)\n\n"
                        "Erstelle einen detaillierten Bericht mit:\n"
                        "- Root Cause\n- Betroffene Files\n- Vorgeschlagener Fix\n"
                        "- Potentielle Seiteneffekte"
                    ),
                    description="Root cause analysis",
                )],
            ),
            Phase(
                name="Fix Implementation",
                number=2,
                mode=PhaseMode.SEQUENTIAL,
                description="Fix implementieren",
                agents=[AgentSpec(
                    role="coder",
                    subagent_type="coder",
                    model="sonnet",
                    prompt_template=(
                        "Implementiere den Fix fuer: {task_description}\n\n"
                        "Research-Ergebnis:\n{phase_1_result}\n\n"
                        "REGELN:\n"
                        "- Type Hints auf allen Funktionen\n"
                        "- KEINE Any-Types\n"
                        "- Deutsche User-Facing Strings\n"
                        "- KEIN PII-Logging\n"
                        "- KEINE Aenderungen an Shared Files "
                        "(main.py, models.py, celery_app.py, tasks/__init__.py)"
                    ),
                    description="Bug fix implementation",
                )],
            ),
            Phase(
                name="Regression Testing",
                number=3,
                mode=PhaseMode.SEQUENTIAL,
                gate="gate_4_tests",
                description="Regression-Test schreiben, bestehende Tests pruefen",
                agents=[AgentSpec(
                    role="tester",
                    subagent_type="tester",
                    model="sonnet",
                    prompt_template=(
                        "Schreibe Tests fuer den Fix: {task_description}\n\n"
                        "Fix-Details:\n{phase_2_result}\n\n"
                        "REGELN:\n"
                        "- Tests in tests/unit/services/<modul>/ (NICHT Root!)\n"
                        "- @pytest.mark.unit und @pytest.mark.asyncio Marker\n"
                        "- Coverage >= 90%% auf neuem Code\n"
                        "- Bestehende Tests muessen unveraendert bestehen\n"
                        "- Regression-Tests fuer den spezifischen Bug"
                    ),
                    description="Regression testing",
                )],
            ),
            Phase(
                name="Review",
                number=4,
                mode=PhaseMode.SEQUENTIAL,
                gate="gate_5_review",
                description="Security, Types, Seiteneffekte pruefen",
                agents=[AgentSpec(
                    role="reviewer",
                    subagent_type="reviewer",
                    model="sonnet",
                    prompt_template=(
                        "Reviewe den Bugfix: {task_description}\n\n"
                        "Pruefe:\n"
                        "- Security (bandit, Injection-Risks)\n"
                        "- Type Safety (keine Any-Types)\n"
                        "- Seiteneffekte auf andere Module\n"
                        "- PII-Schutz in Logs\n"
                        "- Deutsche User-Facing Texte\n"
                        "- Auth-Dependencies auf Endpoints\n\n"
                        "Erstelle einen Review-Report mit BLOCK / WARN / INFO."
                    ),
                    description="Code review",
                )],
            ),
        ],
    )


def _build_feature_small_template() -> TeamTemplate:
    """Template C: Feature Small (3 Agents, sequentiell)."""
    return TeamTemplate(
        team_type=TeamType.FEATURE_SMALL,
        name="Feature Team Small",
        description="Isolierte Module ohne Shared-File-Aenderungen",
        total_agents=3,
        has_parallel_phases=False,
        requires_shared_file_integration=True,
        phases=[
            Phase(
                name="Research",
                number=1,
                mode=PhaseMode.SEQUENTIAL,
                gate="gate_1_research",
                description="Requirements und bestehende Patterns finden",
                agents=[AgentSpec(
                    role="researcher",
                    subagent_type="researcher",
                    model="haiku",
                    prompt_template=(
                        "Recherchiere Requirements fuer: {task_description}\n\n"
                        "1. Finde bestehende Patterns im Codebase (File:Line)\n"
                        "2. Identifiziere alle betroffenen Files\n"
                        "3. Bestimme Modul-Kopplung\n"
                        "4. Pruefe ob Satellite-Model noetig ist"
                    ),
                    description="Requirements research",
                )],
            ),
            Phase(
                name="Implementation",
                number=2,
                mode=PhaseMode.SEQUENTIAL,
                description="Service, Models, API implementieren",
                agents=[AgentSpec(
                    role="coder",
                    subagent_type="coder",
                    model="sonnet",
                    prompt_template=(
                        "Implementiere Feature: {task_description}\n\n"
                        "Research:\n{phase_1_result}\n\n"
                        "REGELN:\n"
                        "- Satellite-Model in app/db/models_{feature}.py\n"
                        "- Service in app/services/{module}/\n"
                        "- API in app/api/v1/{module}.py\n"
                        "- Type Hints, keine Any-Types\n"
                        "- Deutsche User-Facing Strings\n"
                        "- KEINE Aenderungen an Shared Files\n\n"
                        "Erstelle ein Manifest mit benoetigten Registrierungen:\n"
                        "- Router-Import fuer main.py\n"
                        "- Model-Import fuer models.py\n"
                        "- Task-Registrierung fuer celery_app.py\n"
                        "- Re-Export fuer tasks/__init__.py"
                    ),
                    description="Feature implementation",
                )],
            ),
            Phase(
                name="Test + Review",
                number=3,
                mode=PhaseMode.SEQUENTIAL,
                gate="gate_4_tests",
                description="Tests schreiben und Code reviewen",
                agents=[AgentSpec(
                    role="tester_reviewer",
                    subagent_type="tester",
                    model="sonnet",
                    prompt_template=(
                        "Teste und reviewe Feature: {task_description}\n\n"
                        "Implementation:\n{phase_2_result}\n\n"
                        "1. Schreibe Unit-Tests in tests/unit/services/{module}/\n"
                        "2. Coverage >= 90%% auf neuem Code\n"
                        "3. @pytest.mark.unit und @pytest.mark.asyncio\n"
                        "4. Pruefe Type Safety und Security\n"
                        "5. Pruefe Deutsche Texte und PII-Schutz"
                    ),
                    description="Testing and review",
                )],
            ),
        ],
    )


def _build_feature_standard_template() -> TeamTemplate:
    """Template B: Feature Standard (5-6 Agents, teilweise parallel)."""
    return TeamTemplate(
        team_type=TeamType.FEATURE_STANDARD,
        name="Feature Team Standard",
        description="Standard-Feature mit optionaler Parallelisierung",
        total_agents=6,
        has_parallel_phases=True,
        requires_shared_file_integration=True,
        phases=[
            Phase(
                name="Research",
                number=1,
                mode=PhaseMode.SEQUENTIAL,
                gate="gate_1_research",
                description="Requirements, bestehende Patterns finden",
                agents=[AgentSpec(
                    role="researcher",
                    subagent_type="researcher",
                    model="sonnet",
                    prompt_template=(
                        "Recherchiere Requirements fuer: {task_description}\n\n"
                        "1. Finde bestehende Patterns (File:Line)\n"
                        "2. Identifiziere ALLE betroffenen Files\n"
                        "3. Bestimme Modul-Kopplung (M1/M2/M3)\n"
                        "4. Pruefe Domain-Map fuer Parallel-Safety\n"
                        "5. Dokumentiere aehnliche bestehende Implementierungen"
                    ),
                    description="Requirements research",
                )],
            ),
            Phase(
                name="Architecture",
                number=2,
                mode=PhaseMode.SEQUENTIAL,
                gate="gate_2_design",
                description="Datenmodell, API-Schema, Service-Interface",
                agents=[AgentSpec(
                    role="architect",
                    subagent_type="system-architect",
                    model="opus",
                    prompt_template=(
                        "Designe Feature: {task_description}\n\n"
                        "Research:\n{phase_1_result}\n\n"
                        "Erstelle:\n"
                        "1. Datenmodell (Fields, Types, Relationships)\n"
                        "2. API-Contract (Endpoints, Schemas, Status Codes)\n"
                        "3. Service-Interface (Methoden, Parameter, Returns)\n"
                        "4. Satellite-Model-Strategie\n\n"
                        "REGELN:\n"
                        "- Keine Any-Types\n"
                        "- Satellite-Model in models_{feature}.py\n"
                        "- Pydantic v2 Schemas\n"
                        "- SQLAlchemy 2.0+ async Patterns"
                    ),
                    description="Architecture design",
                )],
            ),
            Phase(
                name="Implementation (Parallel)",
                number=3,
                mode=PhaseMode.PARALLEL,
                description="Services+Models parallel zu API+Tasks",
                agents=[
                    AgentSpec(
                        role="coder_a",
                        subagent_type="coder",
                        model="sonnet",
                        prompt_template=(
                            "Implementiere Service-Layer + Models:\n"
                            "{task_description}\n\n"
                            "Design:\n{phase_2_result}\n\n"
                            "DEINE Zone (PARALLEL-SAFE):\n"
                            "- app/services/{module}/\n"
                            "- app/db/models_{feature}.py\n\n"
                            "NICHT anfassen:\n"
                            "- app/main.py\n- app/db/models.py\n"
                            "- app/workers/celery_app.py\n"
                            "- app/workers/tasks/__init__.py\n\n"
                            "Erstelle Manifest mit benoetigten Registrierungen."
                        ),
                        description="Coder-A: Services + Models",
                    ),
                    AgentSpec(
                        role="coder_b",
                        subagent_type="coder",
                        model="sonnet",
                        prompt_template=(
                            "Implementiere API-Endpoints + Celery-Tasks:\n"
                            "{task_description}\n\n"
                            "Design:\n{phase_2_result}\n\n"
                            "DEINE Zone (PARALLEL-SAFE):\n"
                            "- app/api/v1/{module}.py\n"
                            "- app/api/schemas/{module}.py\n"
                            "- app/workers/tasks/{feature}_tasks.py\n\n"
                            "NICHT anfassen:\n"
                            "- app/main.py\n- app/db/models.py\n"
                            "- app/workers/celery_app.py\n"
                            "- app/workers/tasks/__init__.py\n\n"
                            "Erstelle Manifest mit benoetigten Registrierungen."
                        ),
                        description="Coder-B: API + Tasks",
                    ),
                ],
            ),
            Phase(
                name="Testing",
                number=4,
                mode=PhaseMode.SEQUENTIAL,
                gate="gate_4_tests",
                description="Unit + Integration Tests",
                agents=[AgentSpec(
                    role="tester",
                    subagent_type="tester",
                    model="sonnet",
                    prompt_template=(
                        "Schreibe Tests fuer: {task_description}\n\n"
                        "Implementation:\n{phase_3_result}\n\n"
                        "REGELN:\n"
                        "- Tests in tests/unit/services/{module}/\n"
                        "- @pytest.mark.unit und @pytest.mark.asyncio\n"
                        "- Coverage >= 90%% auf neuem Code\n"
                        "- Bestehende Tests unveraendert\n"
                        "- Test-Fixtures in conftest.py"
                    ),
                    description="Testing",
                )],
            ),
            Phase(
                name="Review",
                number=5,
                mode=PhaseMode.SEQUENTIAL,
                gate="gate_5_review",
                description="Full Review",
                agents=[AgentSpec(
                    role="reviewer",
                    subagent_type="reviewer",
                    model="opus",
                    prompt_template=(
                        "Reviewe Feature: {task_description}\n\n"
                        "Pruefe:\n"
                        "- bandit Security-Scan\n"
                        "- Keine Circular Imports\n"
                        "- Auth-Dependencies auf allen Endpoints\n"
                        "- JSONB-Keys whitelisted (CWE-89)\n"
                        "- HTTP-Headers sanitized (CWE-113)\n"
                        "- Type Safety (keine Any-Types)\n"
                        "- Deutsche User-Facing Texte\n"
                        "- PII-Schutz in Logs\n\n"
                        "Erstelle Review-Report mit BLOCK / WARN / INFO."
                    ),
                    description="Full review",
                )],
            ),
            Phase(
                name="Shared File Integration",
                number=6,
                mode=PhaseMode.SEQUENTIAL,
                gate="gate_6_integration",
                description="Registrierungen in Shared Files (IMMER sequentiell)",
                agents=[AgentSpec(
                    role="integrator",
                    subagent_type="coder",
                    model="sonnet",
                    prompt_template=(
                        "Fuehre Shared-File-Integration durch.\n\n"
                        "Manifeste von Coder-A und Coder-B:\n"
                        "{phase_3_manifests}\n\n"
                        "Aenderungen (NUR Appends):\n"
                        "1. app/main.py: Router importieren + registrieren\n"
                        "2. app/db/models.py: Satellite-Import am ENDE\n"
                        "3. app/workers/celery_app.py: Task-Modul + Beat-Schedule\n"
                        "4. app/workers/tasks/__init__.py: Re-Exports\n\n"
                        "REGELN:\n"
                        "- NUR Append-Operationen\n"
                        "- KEINE bestehenden Zeilen aendern\n"
                        "- App muss fehlerfrei starten"
                    ),
                    description="Shared file integration",
                )],
            ),
        ],
    )


def _build_feature_full_template() -> TeamTemplate:
    """Template fuer Feature Full (wie Standard aber mit staerkerem Architect)."""
    template = copy.deepcopy(_build_feature_standard_template())
    template.team_type = TeamType.FEATURE_FULL
    template.name = "Feature Team Full"
    template.description = "Cross-cutting Feature mit starkem Architecture-Review"
    return template


def _build_refactor_template() -> TeamTemplate:
    """Template D: Refactor Team (5-6 Agents)."""
    return TeamTemplate(
        team_type=TeamType.REFACTOR,
        name="Refactor Team",
        description="Callsite-Mapping, Regressions-Vermeidung, Rollback-Strategie",
        total_agents=6,
        has_parallel_phases=True,
        requires_shared_file_integration=True,
        phases=[
            Phase(
                name="Callsite Analysis",
                number=1,
                mode=PhaseMode.SEQUENTIAL,
                gate="gate_1_research",
                description="Callsite-Mapping, Impact-Analyse",
                agents=[AgentSpec(
                    role="researcher",
                    subagent_type="researcher",
                    model="sonnet",
                    prompt_template=(
                        "Analysiere Refactoring-Impact: {task_description}\n\n"
                        "1. Callsite-Mapping: Alle Aufrufer identifizieren\n"
                        "2. Import-Graph erstellen\n"
                        "3. Betroffene Tests identifizieren\n"
                        "4. Rollback-Strategie dokumentieren\n"
                        "5. Risiko-Bewertung pro Aenderung"
                    ),
                    description="Callsite analysis",
                )],
            ),
            Phase(
                name="Refactoring Strategy",
                number=2,
                mode=PhaseMode.SEQUENTIAL,
                gate="gate_2_design",
                description="Refactoring-Plan mit Rollback-Strategie",
                agents=[AgentSpec(
                    role="architect",
                    subagent_type="system-architect",
                    model="opus",
                    prompt_template=(
                        "Erstelle Refactoring-Strategie: {task_description}\n\n"
                        "Callsite-Analyse:\n{phase_1_result}\n\n"
                        "Erstelle:\n"
                        "1. Schritt-fuer-Schritt Refactoring-Plan\n"
                        "2. Rollback-Strategie pro Schritt\n"
                        "3. Parallel-sichere Zonen identifizieren\n"
                        "4. Regressions-Risiken bewerten"
                    ),
                    description="Refactoring strategy",
                )],
            ),
            Phase(
                name="Refactoring (Parallel)",
                number=3,
                mode=PhaseMode.PARALLEL,
                description="Parallel-sichere Refactoring-Zonen",
                agents=[
                    AgentSpec(
                        role="coder_a",
                        subagent_type="coder",
                        model="sonnet",
                        prompt_template=(
                            "Refactore Zone A: {zone_a_description}\n\n"
                            "Strategie:\n{phase_2_result}\n\n"
                            "REGELN:\n"
                            "- NUR deine Zone bearbeiten\n"
                            "- Shared Files NICHT anfassen\n"
                            "- Manifest fuer Registrierungen erstellen"
                        ),
                        description="Coder-A: Zone A refactoring",
                    ),
                    AgentSpec(
                        role="coder_b",
                        subagent_type="coder",
                        model="sonnet",
                        prompt_template=(
                            "Refactore Zone B: {zone_b_description}\n\n"
                            "Strategie:\n{phase_2_result}\n\n"
                            "REGELN:\n"
                            "- NUR deine Zone bearbeiten\n"
                            "- Shared Files NICHT anfassen\n"
                            "- Manifest fuer Registrierungen erstellen"
                        ),
                        description="Coder-B: Zone B refactoring",
                    ),
                ],
            ),
            Phase(
                name="Regression Testing",
                number=4,
                mode=PhaseMode.SEQUENTIAL,
                gate="gate_4_tests",
                description="Alle bestehenden + neue Tests",
                agents=[AgentSpec(
                    role="tester",
                    subagent_type="tester",
                    model="sonnet",
                    prompt_template=(
                        "Teste Refactoring: {task_description}\n\n"
                        "Aenderungen:\n{phase_3_result}\n\n"
                        "1. Alle bestehenden Tests ausfuehren\n"
                        "2. Neue Tests fuer geaenderte Interfaces\n"
                        "3. Coverage >= 90%%\n"
                        "4. Regressions-Tests explizit markieren"
                    ),
                    description="Regression testing",
                )],
            ),
            Phase(
                name="Review",
                number=5,
                mode=PhaseMode.SEQUENTIAL,
                gate="gate_5_review",
                description="Refactoring-Quality-Review",
                agents=[AgentSpec(
                    role="reviewer",
                    subagent_type="reviewer",
                    model="opus",
                    prompt_template=(
                        "Reviewe Refactoring: {task_description}\n\n"
                        "Pruefe:\n"
                        "- Keine verlorenen Funktionalitaeten\n"
                        "- Callsites korrekt aktualisiert\n"
                        "- Keine Circular Imports eingefuehrt\n"
                        "- Type Safety erhalten\n"
                        "- Rollback-Faehigkeit gegeben"
                    ),
                    description="Refactoring review",
                )],
            ),
            Phase(
                name="Shared File Integration",
                number=6,
                mode=PhaseMode.SEQUENTIAL,
                gate="gate_6_integration",
                description="Shared-File-Updates (sequentiell)",
                agents=[AgentSpec(
                    role="integrator",
                    subagent_type="coder",
                    model="sonnet",
                    prompt_template=(
                        "Fuehre Shared-File-Integration durch.\n\n"
                        "Manifeste:\n{phase_3_manifests}\n\n"
                        "NUR Appends an:\n"
                        "- app/main.py\n- app/db/models.py\n"
                        "- app/workers/celery_app.py\n"
                        "- app/workers/tasks/__init__.py"
                    ),
                    description="Shared file integration",
                )],
            ),
        ],
    )


def _build_security_audit_template() -> TeamTemplate:
    """Template E: Security Audit Team (4-5 Agents)."""
    return TeamTemplate(
        team_type=TeamType.SECURITY_AUDIT,
        name="Security Audit Team",
        description="OWASP, Injection, Auth, PII - parallele Auditoren",
        total_agents=5,
        has_parallel_phases=True,
        requires_shared_file_integration=False,
        phases=[
            Phase(
                name="Security Research",
                number=1,
                mode=PhaseMode.SEQUENTIAL,
                description="Threat-Modell und Attack-Surface",
                agents=[AgentSpec(
                    role="security_researcher",
                    subagent_type="researcher",
                    model="opus",
                    prompt_template=(
                        "Security-Analyse fuer: {task_description}\n\n"
                        "1. Threat-Modell erstellen\n"
                        "2. Attack-Surface identifizieren\n"
                        "3. OWASP Top 10 Checklist\n"
                        "4. Bestehende Security-Massnahmen dokumentieren\n"
                        "5. Datenfluesse mit sensiblen Daten markieren"
                    ),
                    description="Security research",
                )],
            ),
            Phase(
                name="Parallel Audit",
                number=2,
                mode=PhaseMode.PARALLEL,
                description="Injection+CRLF+PathTraversal parallel zu Auth+JWT+PII",
                agents=[
                    AgentSpec(
                        role="auditor_a",
                        subagent_type="reviewer",
                        model="sonnet",
                        prompt_template=(
                            "Security Audit A - Injection-Klasse:\n"
                            "{task_description}\n\n"
                            "Research:\n{phase_1_result}\n\n"
                            "Pruefe:\n"
                            "- SQL Injection (CWE-89)\n"
                            "- CRLF Injection (CWE-113)\n"
                            "- Path Traversal (CWE-22)\n"
                            "- Command Injection (CWE-78)\n"
                            "- XSS (CWE-79)\n"
                            "- JSONB-Key Validation\n\n"
                            "Fuer jedes Finding: Severity, Location, Fix-Vorschlag"
                        ),
                        description="Auditor-A: Injection classes",
                    ),
                    AgentSpec(
                        role="auditor_b",
                        subagent_type="reviewer",
                        model="sonnet",
                        prompt_template=(
                            "Security Audit B - Auth+PII-Klasse:\n"
                            "{task_description}\n\n"
                            "Research:\n{phase_1_result}\n\n"
                            "Pruefe:\n"
                            "- Auth-Dependencies auf Endpoints\n"
                            "- JWT Token Handling\n"
                            "- PII in Logs (Kundennr, IBAN, VAT-ID)\n"
                            "- Secrets im Code\n"
                            "- Rate Limiting\n"
                            "- CSRF Protection\n\n"
                            "Fuer jedes Finding: Severity, Location, Fix-Vorschlag"
                        ),
                        description="Auditor-B: Auth + PII",
                    ),
                ],
            ),
            Phase(
                name="Fix Critical/High",
                number=3,
                mode=PhaseMode.SEQUENTIAL,
                description="Fixes fuer Critical und High Findings",
                agents=[AgentSpec(
                    role="security_fixer",
                    subagent_type="coder",
                    model="sonnet",
                    prompt_template=(
                        "Behebe Security-Findings: {task_description}\n\n"
                        "Audit A:\n{phase_2a_result}\n"
                        "Audit B:\n{phase_2b_result}\n\n"
                        "Fixe ALLE Critical und High Findings.\n"
                        "REGELN:\n"
                        "- Type Hints\n- Keine Any-Types\n"
                        "- Deutsche Error-Messages\n"
                        "- Whitelist-Validierung fuer JSONB-Keys"
                    ),
                    description="Security fix implementation",
                )],
            ),
            Phase(
                name="Verification",
                number=4,
                mode=PhaseMode.SEQUENTIAL,
                gate="gate_5_review",
                description="Verifiziere dass alle Fixes greifen",
                agents=[AgentSpec(
                    role="verifier",
                    subagent_type="reviewer",
                    model="opus",
                    prompt_template=(
                        "Verifiziere Security-Fixes: {task_description}\n\n"
                        "Fixes:\n{phase_3_result}\n\n"
                        "1. Jedes Finding nochmal pruefen\n"
                        "2. Keine neuen Vulnerabilities eingefuehrt?\n"
                        "3. Regressions-Risiken?\n"
                        "4. bandit-Scan ausfuehren\n"
                        "5. Finaler Security-Report"
                    ),
                    description="Security verification",
                )],
            ),
        ],
    )


def _build_review_template() -> TeamTemplate:
    """Template F: Review Team (3 Agents, voll parallel)."""
    return TeamTemplate(
        team_type=TeamType.REVIEW,
        name="Review Team",
        description="Structural + Quality + Security Review parallel",
        total_agents=3,
        has_parallel_phases=True,
        requires_shared_file_integration=False,
        phases=[
            Phase(
                name="Parallel Review",
                number=1,
                mode=PhaseMode.PARALLEL,
                gate="gate_5_review",
                description="3 Reviewer gleichzeitig auf verschiedenen Aspekten",
                agents=[
                    AgentSpec(
                        role="structural_reviewer",
                        subagent_type="code-analyzer",
                        model="sonnet",
                        prompt_template=(
                            "Structural Review:\n{task_description}\n\n"
                            "Pruefe:\n"
                            "- Architektur-Compliance (FastAPI + SQLAlchemy Pattern)\n"
                            "- Import-Patterns (keine Circular Imports)\n"
                            "- Datei-Organisation (Services, API, Models getrennt)\n"
                            "- Satellite-Model-Strategie eingehalten\n"
                            "- Shared-File-Protocol eingehalten\n\n"
                            "Output: BLOCK / WARN / INFO Kategorien"
                        ),
                        description="Structural review",
                    ),
                    AgentSpec(
                        role="quality_reviewer",
                        subagent_type="reviewer",
                        model="sonnet",
                        prompt_template=(
                            "Quality Review:\n{task_description}\n\n"
                            "Pruefe:\n"
                            "- Type Hints vollstaendig (keine Any-Types)\n"
                            "- Coverage >= 90%%\n"
                            "- Deutsche User-Facing Texte\n"
                            "- Error Handling Patterns\n"
                            "- Pydantic v2 Validation\n"
                            "- Conventional Commit Messages\n\n"
                            "Output: BLOCK / WARN / INFO Kategorien"
                        ),
                        description="Quality review",
                    ),
                    AgentSpec(
                        role="security_reviewer",
                        subagent_type="reviewer",
                        model="sonnet",
                        prompt_template=(
                            "Security Review:\n{task_description}\n\n"
                            "Pruefe:\n"
                            "- PII-Schutz (Kundennr, IBAN, VAT-ID NICHT loggen)\n"
                            "- Auth-Dependencies auf allen Endpoints\n"
                            "- SQL/JSONB Injection (CWE-89)\n"
                            "- CRLF Injection (CWE-113)\n"
                            "- Path Traversal (CWE-22)\n"
                            "- Secrets nicht im Code\n"
                            "- Rate Limiting\n\n"
                            "Output: BLOCK / WARN / INFO Kategorien"
                        ),
                        description="Security review",
                    ),
                ],
            ),
        ],
    )


def _build_no_team_template(model: str) -> TeamTemplate:
    """Template fuer Solo-Agent ohne Team-Koordination."""
    team_type = TeamType.NO_TEAM_HAIKU if model == "haiku" else TeamType.NO_TEAM_SONNET
    return TeamTemplate(
        team_type=team_type,
        name=f"Solo Agent ({model})",
        description="Einfacher Task ohne Team-Koordination",
        total_agents=1,
        has_parallel_phases=False,
        requires_shared_file_integration=False,
        phases=[Phase(
            name="Direct Execution",
            number=1,
            mode=PhaseMode.SEQUENTIAL,
            description="Direkte Ausfuehrung ohne Team",
            agents=[AgentSpec(
                role="solo",
                subagent_type="coder",
                model=model,
                prompt_template="{task_description}",
                description="Solo agent execution",
            )],
        )],
    )


# --- Template Registry ---

TEAM_TEMPLATES: Dict[TeamType, TeamTemplate] = {
    TeamType.BUGFIX: _build_bugfix_template(),
    TeamType.FEATURE_SMALL: _build_feature_small_template(),
    TeamType.FEATURE_STANDARD: _build_feature_standard_template(),
    TeamType.FEATURE_FULL: _build_feature_full_template(),
    TeamType.REFACTOR: _build_refactor_template(),
    TeamType.SECURITY_AUDIT: _build_security_audit_template(),
    TeamType.REVIEW: _build_review_template(),
}


# --- Klassifikationsmatrix ---

CLASSIFICATION_MATRIX: Dict[Tuple[Complexity, Coupling], TeamType] = {
    # C1 Trivial
    (Complexity.C1_TRIVIAL, Coupling.M1_ISOLATED): TeamType.NO_TEAM_HAIKU,
    (Complexity.C1_TRIVIAL, Coupling.M2_LIGHT_COUPLED): TeamType.NO_TEAM_SONNET,
    (Complexity.C1_TRIVIAL, Coupling.M3_SHARED_INFRA): TeamType.BUGFIX,
    # C2 Contained
    (Complexity.C2_CONTAINED, Coupling.M1_ISOLATED): TeamType.FEATURE_SMALL,
    (Complexity.C2_CONTAINED, Coupling.M2_LIGHT_COUPLED): TeamType.FEATURE_STANDARD,
    (Complexity.C2_CONTAINED, Coupling.M3_SHARED_INFRA): TeamType.FEATURE_STANDARD,
    # C3 Cross-cutting
    (Complexity.C3_CROSS_CUTTING, Coupling.M1_ISOLATED): TeamType.FEATURE_STANDARD,
    (Complexity.C3_CROSS_CUTTING, Coupling.M2_LIGHT_COUPLED): TeamType.FEATURE_FULL,
    (Complexity.C3_CROSS_CUTTING, Coupling.M3_SHARED_INFRA): TeamType.FEATURE_FULL,
    # C4 Architecture
    (Complexity.C4_ARCHITECTURE, Coupling.M1_ISOLATED): TeamType.REFACTOR,
    (Complexity.C4_ARCHITECTURE, Coupling.M2_LIGHT_COUPLED): TeamType.REFACTOR,
    (Complexity.C4_ARCHITECTURE, Coupling.M3_SHARED_INFRA): TeamType.REFACTOR,
}


class TeamClassifier:
    """Klassifiziert Tasks und waehlt das passende Team-Template."""

    SECURITY_PATTERNS: List[str] = [
        r"security",
        r"sicherheit",
        r"vulnerability",
        r"audit",
        r"cve[-\s]?\d+",
        r"injection",
        r"cwe[-\s]?\d+",
        r"owasp",
        r"penetration",
        r"sicherheitsaudit",
    ]

    REVIEW_PATTERNS: List[str] = [
        r"review\s*(code|pull|pr|merge)",
        r"code\s*review",
        r"qualitaets?(pruefung|check)",
        r"pruefe\s*(code|aenderungen|changes)",
    ]

    REFACTOR_PATTERNS: List[str] = [
        r"refactor",
        r"umstrukturier",
        r"restructure",
        r"reorgani[sz]",
        r"migration",
    ]

    def classify(self, input_data: ClassificationInput) -> ClassificationOutput:
        """Klassifiziert einen Task und waehlt das Team-Template."""

        # Explicit override
        if input_data.explicit_team:
            template = TEAM_TEMPLATES.get(input_data.explicit_team)
            if template:
                return ClassificationOutput(
                    team_type=input_data.explicit_team,
                    complexity=Complexity.C2_CONTAINED,
                    coupling=Coupling.M2_LIGHT_COUPLED,
                    confidence=1.0,
                    reasoning="Explizit angefordertes Team",
                    template=template,
                    override_reason="explicit",
                )

        task_lower = input_data.task_description.lower()

        # Security override
        if input_data.is_security or self._matches_patterns(
            task_lower, self.SECURITY_PATTERNS
        ):
            template = TEAM_TEMPLATES[TeamType.SECURITY_AUDIT]
            return ClassificationOutput(
                team_type=TeamType.SECURITY_AUDIT,
                complexity=self._determine_complexity(input_data),
                coupling=self._determine_coupling(input_data),
                confidence=0.95,
                reasoning="Security-Aenderung erkannt",
                template=template,
                override_reason="security",
            )

        # Review override
        if input_data.is_review_only or self._matches_patterns(
            task_lower, self.REVIEW_PATTERNS
        ):
            template = TEAM_TEMPLATES[TeamType.REVIEW]
            return ClassificationOutput(
                team_type=TeamType.REVIEW,
                complexity=self._determine_complexity(input_data),
                coupling=self._determine_coupling(input_data),
                confidence=0.9,
                reasoning="Review-Anfrage erkannt",
                template=template,
                override_reason="review",
            )

        # Standard classification via matrix
        complexity = self._determine_complexity(input_data)
        coupling = self._determine_coupling(input_data)

        # Refactor override for C3/C4
        if complexity in (
            Complexity.C3_CROSS_CUTTING,
            Complexity.C4_ARCHITECTURE,
        ) and self._matches_patterns(task_lower, self.REFACTOR_PATTERNS):
            team_type = TeamType.REFACTOR
        else:
            team_type = CLASSIFICATION_MATRIX.get(
                (complexity, coupling), TeamType.FEATURE_STANDARD
            )

        # No-team types get a minimal solo-agent template
        if team_type in (TeamType.NO_TEAM_HAIKU, TeamType.NO_TEAM_SONNET):
            model = "haiku" if team_type == TeamType.NO_TEAM_HAIKU else "sonnet"
            template = _build_no_team_template(model)
        else:
            template = TEAM_TEMPLATES[team_type]

        return ClassificationOutput(
            team_type=team_type,
            complexity=complexity,
            coupling=coupling,
            confidence=self._calculate_confidence(complexity, coupling, input_data),
            reasoning=self._build_reasoning(complexity, coupling, team_type),
            template=template,
        )

    def _determine_complexity(self, input_data: ClassificationInput) -> Complexity:
        """Bestimmt die Komplexitaet basierend auf Datei-Anzahl."""
        file_count = len(input_data.affected_files)
        if file_count <= 2:
            return Complexity.C1_TRIVIAL
        if file_count <= 8:
            return Complexity.C2_CONTAINED
        if file_count <= 20:
            return Complexity.C3_CROSS_CUTTING
        return Complexity.C4_ARCHITECTURE

    def _determine_coupling(self, input_data: ClassificationInput) -> Coupling:
        """Bestimmt die Kopplung basierend auf Shared-File-Nutzung."""
        shared_count = 0
        for f in input_data.affected_files:
            normalized = f.replace("\\", "/")
            if any(
                normalized == sf or normalized.endswith("/" + sf)
                for sf in SEQUENTIAL_ONLY_FILES
            ):
                shared_count += 1
        if shared_count == 0:
            return Coupling.M1_ISOLATED
        if shared_count <= 2:
            return Coupling.M2_LIGHT_COUPLED
        return Coupling.M3_SHARED_INFRA

    def _matches_patterns(self, text: str, patterns: List[str]) -> bool:
        """Prueft ob Text auf mindestens ein Pattern matcht."""
        return any(re.search(p, text, re.IGNORECASE) for p in patterns)

    def _calculate_confidence(
        self,
        complexity: Complexity,
        coupling: Coupling,
        input_data: ClassificationInput,
    ) -> float:
        """Berechnet Confidence der Klassifikation."""
        base = 0.7
        if len(input_data.affected_files) > 0:
            base += 0.1
        if len(input_data.task_description) > 100:
            base += 0.1
        return min(base, 1.0)

    def _build_reasoning(
        self,
        complexity: Complexity,
        coupling: Coupling,
        team_type: TeamType,
    ) -> str:
        """Erstellt Begruendung fuer die Klassifikation."""
        return (
            f"Komplexitaet={complexity.value}, "
            f"Kopplung={coupling.value} "
            f"-> {team_type.value}"
        )


def get_team_template(team_type: TeamType) -> TeamTemplate:
    """Gibt das Template fuer einen TeamType zurueck."""
    return TEAM_TEMPLATES[team_type]


def classify_task(
    task_description: str,
    affected_files: Optional[List[str]] = None,
    is_security: bool = False,
    is_review_only: bool = False,
) -> ClassificationOutput:
    """Convenience-Funktion fuer Task-Klassifikation."""
    classifier = TeamClassifier()
    return classifier.classify(ClassificationInput(
        task_description=task_description,
        affected_files=affected_files or [],
        is_security=is_security,
        is_review_only=is_review_only,
    ))
