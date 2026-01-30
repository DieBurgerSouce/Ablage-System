"""
Swarm Bridge - Automatische Integration von Claude Flow V3 Swarms.

WICHTIG: Diese Bridge nutzt NICHT subprocess-Calls!
Stattdessen integriert sie sich mit:
1. Claude Code's Task-Tool (für parallele Agents)
2. MCP Orchestration Tools (für Routing/Dekomposition)
3. Hooks System (für automatische Trigger)

Die eigentliche Swarm-Ausführung erfolgt durch Claude Code selbst,
diese Bridge liefert nur die Analyse und Konfiguration.
"""

import json
import logging
import re
from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

from app.core.safe_errors import safe_error_detail, safe_error_log

logger = logging.getLogger("swarm_bridge")


class SwarmStrategy(Enum):
    """Verfügbare Swarm-Strategien."""
    AUTO = "auto"
    DEVELOPMENT = "development"
    RESEARCH = "research"
    ANALYSIS = "analysis"
    TESTING = "testing"
    OPTIMIZATION = "optimization"
    MAINTENANCE = "maintenance"
    SECURITY = "security"
    REFACTORING = "refactoring"


class SwarmTopology(Enum):
    """Swarm-Topologien."""
    HIERARCHICAL = "hierarchical"
    MESH = "mesh"
    HIERARCHICAL_MESH = "hierarchical-mesh"


class AgentType(Enum):
    """Verfügbare Agent-Typen für Task-Tool."""
    EXPLORE = "Explore"
    PLAN = "Plan"
    HAIKU_TASK = "haiku-task"
    SONNET_IMPLEMENTATION = "sonnet-implementation"
    OPUS_TASK = "opus-task"
    TESTING_EXPERT = "testing-expert"
    DATABASE_EXPERT = "database-expert"
    REFACTORING_EXPERT = "refactoring-expert"
    OCR_SPECIALIST = "ocr-specialist"


@dataclass
class SwarmAgent:
    """Definition eines Agents im Swarm."""
    role: str
    agent_type: AgentType
    model: str  # haiku, sonnet, opus
    prompt: str
    description: str
    run_in_background: bool = True
    depends_on: List[str] = field(default_factory=list)


@dataclass
class SwarmPlan:
    """Plan für einen Swarm - wird von Claude Code ausgeführt."""
    swarm_id: str
    strategy: SwarmStrategy
    topology: SwarmTopology
    agents: List[SwarmAgent]
    total_agents: int
    estimated_duration_minutes: int
    parallel_waves: int  # Anzahl paralleler Wellen
    reasoning: str

    def to_task_instructions(self) -> str:
        """Generiert Anweisungen für Claude Code Task-Tool Calls."""
        waves = self._group_into_waves()

        instructions = [
            f"# Swarm Plan: {self.swarm_id}",
            f"Strategy: {self.strategy.value}",
            f"Topology: {self.topology.value}",
            f"Total Agents: {self.total_agents}",
            f"Parallel Waves: {len(waves)}",
            "",
            "## Execution Instructions",
            "",
        ]

        for i, wave in enumerate(waves, 1):
            instructions.append(f"### Wave {i} (Parallel)")
            instructions.append("Spawn these agents IN PARALLEL using Task tool:")
            instructions.append("```")
            for agent in wave:
                instructions.append(f"Task(")
                instructions.append(f'  prompt="{agent.prompt[:100]}...",')
                instructions.append(f'  subagent_type="{agent.agent_type.value}",')
                instructions.append(f'  model="{agent.model}",')
                instructions.append(f'  description="{agent.description}",')
                instructions.append(f'  run_in_background={agent.run_in_background}')
                instructions.append(f")")
            instructions.append("```")
            instructions.append("")

        return "\n".join(instructions)

    def _group_into_waves(self) -> List[List[SwarmAgent]]:
        """Gruppiert Agents in parallele Wellen basierend auf Abhängigkeiten."""
        waves = []
        remaining = list(self.agents)
        completed_roles = set()

        while remaining:
            # Finde alle Agents ohne unerfüllte Abhängigkeiten
            wave = [
                agent for agent in remaining
                if all(dep in completed_roles for dep in agent.depends_on)
            ]

            if not wave:
                # Deadlock-Prevention: Nimm ersten verbleibenden
                wave = [remaining[0]]

            waves.append(wave)
            for agent in wave:
                remaining.remove(agent)
                completed_roles.add(agent.role)

        return waves


@dataclass
class SwarmConfig:
    """Konfiguration für einen Swarm."""
    strategy: SwarmStrategy = SwarmStrategy.AUTO
    topology: SwarmTopology = SwarmTopology.HIERARCHICAL_MESH
    max_agents: int = 8
    parallel: bool = True
    review: bool = True
    testing: bool = True


@dataclass
class ComplexityAnalysis:
    """Ergebnis der Komplexitäts-Analyse."""
    needs_swarm: bool
    complexity_score: int
    confidence: float
    recommended_strategy: SwarmStrategy
    recommended_agents: List[str]
    reasoning: str
    file_count: int
    estimated_agents: int


class TaskComplexityAnalyzer:
    """Analysiert Task-Komplexität um zu entscheiden ob ein Swarm nötig ist."""

    # Keywords die auf hohe Komplexität hindeuten (gewichtet)
    HIGH_COMPLEXITY_PATTERNS: Dict[str, Tuple[int, SwarmStrategy]] = {
        # Security (höchste Priorität)
        r"security\s*audit": (4, SwarmStrategy.SECURITY),
        r"vulnerability": (4, SwarmStrategy.SECURITY),
        r"penetration\s*test": (4, SwarmStrategy.SECURITY),
        r"cve[-\s]?\d+": (3, SwarmStrategy.SECURITY),
        r"sicherheitsaudit": (4, SwarmStrategy.SECURITY),
        # Refactoring
        r"refactor\s*(all|entire|complete)": (4, SwarmStrategy.REFACTORING),
        r"restructure": (3, SwarmStrategy.REFACTORING),
        r"migration": (4, SwarmStrategy.REFACTORING),
        r"umstrukturieren": (3, SwarmStrategy.REFACTORING),
        # Multi-File
        r"(all|alle)\s*(files?|dateien)": (3, SwarmStrategy.DEVELOPMENT),
        r"across\s*(the\s*)?(codebase|project)": (4, SwarmStrategy.DEVELOPMENT),
        r"entire\s*(codebase|project|system)": (4, SwarmStrategy.DEVELOPMENT),
        r"(umfassend|vollständig|komplett)": (3, SwarmStrategy.DEVELOPMENT),
        # Architecture
        r"architect(ure)?": (3, SwarmStrategy.DEVELOPMENT),
        r"system\s*design": (3, SwarmStrategy.DEVELOPMENT),
        r"infrastructure": (3, SwarmStrategy.DEVELOPMENT),
        # Performance
        r"optimi(ze|sieren)\s*(all|performance)": (3, SwarmStrategy.OPTIMIZATION),
        r"bottleneck": (2, SwarmStrategy.OPTIMIZATION),
        r"profiling": (2, SwarmStrategy.OPTIMIZATION),
        # Testing
        r"comprehensive\s*test": (3, SwarmStrategy.TESTING),
        r"e2e\s*(test)?": (3, SwarmStrategy.TESTING),
        r"integration\s*test\s*suite": (3, SwarmStrategy.TESTING),
        r"test\s*coverage": (2, SwarmStrategy.TESTING),
        # Research
        r"research\s*(and\s*)?analyz": (3, SwarmStrategy.RESEARCH),
        r"investigate": (2, SwarmStrategy.RESEARCH),
        r"compare\s*(approach|option|solution)": (2, SwarmStrategy.RESEARCH),
    }

    # Keywords die auf niedrige Komplexität hindeuten
    LOW_COMPLEXITY_PATTERNS: List[str] = [
        r"fix\s*(typo|tippfehler)",
        r"update\s*comment",
        r"rename\s*(variable|function|class)",
        r"simple\s*(fix|change|update)",
        r"quick\s*(fix|change)",
        r"single\s*file",
        r"one\s*file",
        r"eine\s*datei",
        r"einfach(e|er|es)?",
        r"schnell(e|er|es)?",
    ]

    SWARM_FILE_THRESHOLD = 5
    SWARM_COMPLEXITY_THRESHOLD = 3

    def analyze(self, task: str, affected_files: List[str] = None) -> ComplexityAnalysis:
        """
        Analysiert ob ein Task einen Swarm benötigt.

        Returns:
            ComplexityAnalysis mit Entscheidung und Begründung
        """
        affected_files = affected_files or []
        task_lower = task.lower()

        complexity_score = 0
        reasons = []
        detected_strategy = SwarmStrategy.AUTO
        max_strategy_weight = 0

        # Check High Complexity Patterns
        for pattern, (weight, strategy) in self.HIGH_COMPLEXITY_PATTERNS.items():
            if re.search(pattern, task_lower):
                complexity_score += weight
                reasons.append(f"Pattern: {pattern[:30]}")
                if weight > max_strategy_weight:
                    max_strategy_weight = weight
                    detected_strategy = strategy

        # Check Low Complexity Patterns
        for pattern in self.LOW_COMPLEXITY_PATTERNS:
            if re.search(pattern, task_lower):
                complexity_score -= 3
                reasons.append(f"Einfach: {pattern[:20]}")

        # File Count Analysis
        file_count = len(affected_files)
        if file_count > self.SWARM_FILE_THRESHOLD:
            file_bonus = min(5, file_count // 3)
            complexity_score += file_bonus
            reasons.append(f"{file_count} Dateien (+{file_bonus})")

        # Task Length Analysis
        if len(task) > 500:
            complexity_score += 1
            reasons.append("Lange Beschreibung")
        if len(task) > 1000:
            complexity_score += 1

        # Calculate confidence
        confidence = min(1.0, 0.5 + (abs(complexity_score) * 0.08))

        # Determine if swarm needed
        needs_swarm = complexity_score >= self.SWARM_COMPLEXITY_THRESHOLD

        # Estimate agent count
        estimated_agents = self._estimate_agent_count(
            complexity_score, file_count, detected_strategy
        )

        # Recommend agents
        recommended_agents = self._recommend_agents(detected_strategy)

        return ComplexityAnalysis(
            needs_swarm=needs_swarm,
            complexity_score=complexity_score,
            confidence=confidence,
            recommended_strategy=detected_strategy,
            recommended_agents=recommended_agents,
            reasoning="; ".join(reasons) if reasons else "Standard-Analyse",
            file_count=file_count,
            estimated_agents=estimated_agents,
        )

    def _estimate_agent_count(
        self,
        score: int,
        file_count: int,
        strategy: SwarmStrategy
    ) -> int:
        """Schätzt optimale Agent-Anzahl."""
        base = 3

        # Score-basiert
        if score >= 6:
            base = 5
        elif score >= 4:
            base = 4

        # File-basiert
        if file_count > 20:
            base += 2
        elif file_count > 10:
            base += 1

        # Strategy-basiert
        if strategy == SwarmStrategy.SECURITY:
            base = max(base, 4)  # Security braucht mindestens 4
        elif strategy == SwarmStrategy.DEVELOPMENT:
            base = max(base, 5)  # Development braucht 5+

        return min(8, base)  # Max 8 Agents

    def _recommend_agents(self, strategy: SwarmStrategy) -> List[str]:
        """Empfiehlt Agent-Typen basierend auf Strategie."""
        recommendations = {
            SwarmStrategy.SECURITY: [
                "Explore (Codebase-Analyse)",
                "Plan (Security-Assessment)",
                "opus-task (Vulnerability-Analyse)",
                "sonnet-implementation (Fixes)",
                "testing-expert (Security-Tests)",
            ],
            SwarmStrategy.REFACTORING: [
                "Explore (Pattern-Erkennung)",
                "Plan (Refactoring-Strategie)",
                "refactoring-expert (Durchführung)",
                "testing-expert (Regressions-Tests)",
            ],
            SwarmStrategy.DEVELOPMENT: [
                "Explore (Requirements)",
                "Plan (Architektur)",
                "sonnet-implementation (Code)",
                "testing-expert (Tests)",
                "haiku-task (Docs)",
            ],
            SwarmStrategy.TESTING: [
                "Explore (Code-Coverage)",
                "testing-expert (Test-Suite)",
                "sonnet-implementation (Fixtures)",
            ],
            SwarmStrategy.OPTIMIZATION: [
                "Explore (Bottleneck-Analyse)",
                "Plan (Optimierungs-Strategie)",
                "opus-task (Algorithmen)",
                "sonnet-implementation (Umsetzung)",
            ],
            SwarmStrategy.RESEARCH: [
                "Explore (Recherche)",
                "Plan (Synthese)",
                "haiku-task (Dokumentation)",
            ],
        }
        return recommendations.get(strategy, recommendations[SwarmStrategy.DEVELOPMENT])


class SwarmPlanner:
    """Erstellt Swarm-Pläne basierend auf Analyse."""

    def create_plan(
        self,
        task: str,
        analysis: ComplexityAnalysis,
        config: SwarmConfig = None
    ) -> SwarmPlan:
        """
        Erstellt einen Swarm-Plan basierend auf der Analyse.

        Der Plan enthält konkrete Agent-Definitionen die Claude Code
        mit dem Task-Tool ausführen kann.
        """
        config = config or SwarmConfig(strategy=analysis.recommended_strategy)
        swarm_id = f"swarm_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"

        agents = self._create_agents(task, analysis, config)

        return SwarmPlan(
            swarm_id=swarm_id,
            strategy=config.strategy,
            topology=config.topology,
            agents=agents,
            total_agents=len(agents),
            estimated_duration_minutes=self._estimate_duration(agents),
            parallel_waves=self._count_waves(agents),
            reasoning=f"Basierend auf: {analysis.reasoning}",
        )

    def _create_agents(
        self,
        task: str,
        analysis: ComplexityAnalysis,
        config: SwarmConfig
    ) -> List[SwarmAgent]:
        """Erstellt Agent-Definitionen basierend auf Strategie."""
        strategy = config.strategy
        agents = []

        # Wave 1: Exploration (immer zuerst)
        agents.append(SwarmAgent(
            role="explorer",
            agent_type=AgentType.EXPLORE,
            model="sonnet",
            prompt=f"Analysiere die Codebase für: {task[:200]}. "
                   f"Finde relevante Dateien, Patterns und Abhängigkeiten.",
            description="Codebase exploration",
            depends_on=[],
        ))

        # Wave 2: Planning
        agents.append(SwarmAgent(
            role="planner",
            agent_type=AgentType.PLAN,
            model="sonnet",
            prompt=f"Erstelle einen detaillierten Plan für: {task[:200]}. "
                   f"Berücksichtige die Ergebnisse der Exploration.",
            description="Implementation planning",
            depends_on=["explorer"],
        ))

        # Wave 3: Strategy-spezifische Agents
        if strategy == SwarmStrategy.SECURITY:
            agents.extend(self._create_security_agents(task))
        elif strategy == SwarmStrategy.REFACTORING:
            agents.extend(self._create_refactoring_agents(task))
        elif strategy == SwarmStrategy.TESTING:
            agents.extend(self._create_testing_agents(task))
        elif strategy == SwarmStrategy.OPTIMIZATION:
            agents.extend(self._create_optimization_agents(task))
        else:
            agents.extend(self._create_development_agents(task))

        # Optional: Review Agent
        if config.review and len(agents) > 2:
            agents.append(SwarmAgent(
                role="reviewer",
                agent_type=AgentType.OPUS_TASK,
                model="opus",
                prompt="Reviewe alle Änderungen auf Qualität, Security und Best Practices.",
                description="Final review",
                depends_on=[a.role for a in agents if a.role not in ["explorer", "planner"]],
            ))

        return agents[:config.max_agents]

    def _create_security_agents(self, task: str) -> List[SwarmAgent]:
        """Erstellt Security-spezifische Agents."""
        return [
            SwarmAgent(
                role="security_analyst",
                agent_type=AgentType.OPUS_TASK,
                model="opus",
                prompt=f"Führe Security-Analyse durch für: {task[:150]}. "
                       f"Identifiziere Vulnerabilities (OWASP Top 10, CWE).",
                description="Security analysis",
                depends_on=["planner"],
            ),
            SwarmAgent(
                role="security_fixer",
                agent_type=AgentType.SONNET_IMPLEMENTATION,
                model="sonnet",
                prompt="Implementiere Security-Fixes basierend auf der Analyse.",
                description="Security fixes",
                depends_on=["security_analyst"],
            ),
            SwarmAgent(
                role="security_tester",
                agent_type=AgentType.TESTING_EXPERT,
                model="sonnet",
                prompt="Erstelle Security-Tests für alle Fixes.",
                description="Security tests",
                depends_on=["security_fixer"],
            ),
        ]

    def _create_refactoring_agents(self, task: str) -> List[SwarmAgent]:
        """Erstellt Refactoring-spezifische Agents."""
        return [
            SwarmAgent(
                role="refactor_analyst",
                agent_type=AgentType.REFACTORING_EXPERT,
                model="sonnet",
                prompt=f"Analysiere Refactoring-Möglichkeiten für: {task[:150]}. "
                       f"Identifiziere Code-Smells und Verbesserungen.",
                description="Refactoring analysis",
                depends_on=["planner"],
            ),
            SwarmAgent(
                role="refactor_impl",
                agent_type=AgentType.SONNET_IMPLEMENTATION,
                model="sonnet",
                prompt="Führe das Refactoring durch. Behalte Funktionalität bei.",
                description="Refactoring implementation",
                depends_on=["refactor_analyst"],
            ),
            SwarmAgent(
                role="refactor_tester",
                agent_type=AgentType.TESTING_EXPERT,
                model="sonnet",
                prompt="Stelle sicher dass alle Tests nach Refactoring bestehen.",
                description="Regression testing",
                depends_on=["refactor_impl"],
            ),
        ]

    def _create_testing_agents(self, task: str) -> List[SwarmAgent]:
        """Erstellt Testing-spezifische Agents."""
        return [
            SwarmAgent(
                role="test_analyst",
                agent_type=AgentType.TESTING_EXPERT,
                model="sonnet",
                prompt=f"Analysiere Test-Coverage für: {task[:150]}. "
                       f"Identifiziere fehlende Tests.",
                description="Test analysis",
                depends_on=["planner"],
            ),
            SwarmAgent(
                role="test_writer",
                agent_type=AgentType.TESTING_EXPERT,
                model="sonnet",
                prompt="Schreibe fehlende Unit- und Integration-Tests.",
                description="Test writing",
                depends_on=["test_analyst"],
            ),
        ]

    def _create_optimization_agents(self, task: str) -> List[SwarmAgent]:
        """Erstellt Optimization-spezifische Agents."""
        return [
            SwarmAgent(
                role="perf_analyst",
                agent_type=AgentType.OPUS_TASK,
                model="opus",
                prompt=f"Analysiere Performance-Bottlenecks für: {task[:150]}.",
                description="Performance analysis",
                depends_on=["planner"],
            ),
            SwarmAgent(
                role="perf_optimizer",
                agent_type=AgentType.SONNET_IMPLEMENTATION,
                model="sonnet",
                prompt="Implementiere Performance-Optimierungen.",
                description="Performance optimization",
                depends_on=["perf_analyst"],
            ),
        ]

    def _create_development_agents(self, task: str) -> List[SwarmAgent]:
        """Erstellt Standard-Development-Agents."""
        return [
            SwarmAgent(
                role="implementer",
                agent_type=AgentType.SONNET_IMPLEMENTATION,
                model="sonnet",
                prompt=f"Implementiere: {task[:150]}",
                description="Implementation",
                depends_on=["planner"],
            ),
            SwarmAgent(
                role="tester",
                agent_type=AgentType.TESTING_EXPERT,
                model="sonnet",
                prompt="Schreibe Tests für die Implementierung.",
                description="Test creation",
                depends_on=["implementer"],
            ),
        ]

    def _estimate_duration(self, agents: List[SwarmAgent]) -> int:
        """Schätzt Dauer in Minuten."""
        # Basis: 2 Minuten pro Agent, parallelisiert
        waves = self._count_waves(agents)
        return waves * 3  # 3 Minuten pro Welle

    def _count_waves(self, agents: List[SwarmAgent]) -> int:
        """Zählt parallele Wellen."""
        if not agents:
            return 0

        waves = 0
        completed = set()
        remaining = set(a.role for a in agents)
        agent_map = {a.role: a for a in agents}

        while remaining:
            wave = {
                role for role in remaining
                if all(dep in completed for dep in agent_map[role].depends_on)
            }
            if not wave:
                wave = {next(iter(remaining))}

            waves += 1
            completed.update(wave)
            remaining -= wave

        return waves


class SwarmBridge:
    """
    Bridge zwischen Claude Code und Swarm-Orchestration.

    WICHTIG: Diese Bridge führt KEINE Swarms direkt aus!
    Sie analysiert Tasks und erstellt Pläne, die Claude Code
    dann mit dem Task-Tool ausführt.
    """

    SWARM_STATE_FILE = Path(".claude-flow/swarm-state.json")

    def __init__(self):
        self.analyzer = TaskComplexityAnalyzer()
        self.planner = SwarmPlanner()
        self.swarm_history: Dict[str, Dict] = {}
        self._load_state()

    def _load_state(self) -> None:
        """Lädt Swarm-State von Disk."""
        if self.SWARM_STATE_FILE.exists():
            try:
                with open(self.SWARM_STATE_FILE, 'r', encoding='utf-8') as f:
                    self.swarm_history = json.load(f)
            except Exception as e:
                logger.warning("swarm_state_load_failed", extra=safe_error_log(e))
                self.swarm_history = {}

    def _save_state(self) -> None:
        """Speichert Swarm-State."""
        self.SWARM_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.SWARM_STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.swarm_history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning("swarm_state_save_failed", extra=safe_error_log(e))

    def analyze_task(self, task: str, files: List[str] = None) -> ComplexityAnalysis:
        """Analysiert ob für einen Task ein Swarm nötig ist."""
        return self.analyzer.analyze(task, files)

    def create_swarm_plan(
        self,
        task: str,
        files: List[str] = None,
        config: SwarmConfig = None
    ) -> Tuple[ComplexityAnalysis, Optional[SwarmPlan]]:
        """
        Erstellt einen Swarm-Plan wenn nötig.

        Returns:
            Tuple von (Analyse, Plan oder None wenn kein Swarm nötig)
        """
        analysis = self.analyze_task(task, files)

        if not analysis.needs_swarm:
            return analysis, None

        # Config basierend auf Analyse
        if config is None:
            config = SwarmConfig(
                strategy=analysis.recommended_strategy,
                max_agents=analysis.estimated_agents,
            )

        plan = self.planner.create_plan(task, analysis, config)

        # Speichere Plan in History
        self.swarm_history[plan.swarm_id] = {
            "task": task[:500],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "analysis": asdict(analysis),
            "plan_summary": {
                "strategy": plan.strategy.value,
                "agents": plan.total_agents,
                "waves": plan.parallel_waves,
            },
            "status": "planned",
        }
        self._save_state()

        return analysis, plan

    def get_task_instructions(self, task: str, files: List[str] = None) -> str:
        """
        Generiert Anweisungen für Claude Code.

        Dies ist die Hauptmethode - sie gibt Instruktionen zurück
        die Claude Code direkt ausführen kann.
        """
        analysis, plan = self.create_swarm_plan(task, files)

        if plan is None:
            return f"""## Keine Swarm-Orchestration nötig

**Analyse:**
- Komplexitäts-Score: {analysis.complexity_score}
- Confidence: {analysis.confidence:.0%}
- Begründung: {analysis.reasoning}

**Empfehlung:** Führe die Task mit einem einzelnen Agent aus.
"""

        return plan.to_task_instructions()

    def mark_completed(self, swarm_id: str, success: bool = True) -> None:
        """Markiert einen Swarm als abgeschlossen."""
        if swarm_id in self.swarm_history:
            self.swarm_history[swarm_id]["status"] = "completed" if success else "failed"
            self.swarm_history[swarm_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
            self._save_state()


# Singleton Instance
_swarm_bridge: Optional[SwarmBridge] = None


def get_swarm_bridge() -> SwarmBridge:
    """Holt globale SwarmBridge Instanz."""
    global _swarm_bridge
    if _swarm_bridge is None:
        _swarm_bridge = SwarmBridge()
    return _swarm_bridge


def analyze_for_swarm(task: str, files: List[str] = None) -> Dict[str, Any]:
    """
    Analysiert ob ein Task einen Swarm benötigt.

    Returns:
        Dict mit Analyse-Ergebnissen
    """
    bridge = get_swarm_bridge()
    analysis = bridge.analyze_task(task, files)
    return asdict(analysis)


def get_swarm_instructions(task: str, files: List[str] = None) -> str:
    """
    Generiert Swarm-Instruktionen für Claude Code.

    Beispiel:
        instructions = get_swarm_instructions(
            "Refactor all API endpoints for security",
            files=["app/api/v1/*.py"]
        )
        print(instructions)  # Zeigt Task-Tool Calls an
    """
    bridge = get_swarm_bridge()
    return bridge.get_task_instructions(task, files)
